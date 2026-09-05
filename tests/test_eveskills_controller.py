"""SkillsController: the single writer of the skills state document.

Every test here is headless. No network (the ESI client is a fake), no
sockets, no browser, no real threads unless the test says so, and `tmp_path`
for the state file, the id cache, and the plans folder.
"""

import json
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from wingman.eveauth import application as eveauth_application
from wingman.eveauth import state as authority_state_mod
from wingman.eveauth.controller import (
    AccessTokenResult,
    AuthorityCharacter,
    AuthorityController,
    AuthorizationCommandResult,
    MutationResult,
)
from wingman.eveskills import application
from wingman.eveskills import controller as controller_mod
from wingman.eveskills import esi as esi_mod
from wingman.eveskills import evaluator as evaluator_mod
from wingman.eveskills import jwt as jwt_mod
from wingman.eveskills import loopback as loopback_mod
from wingman.eveskills import skillids as skillids_mod
from wingman.eveskills import sso as sso_mod
from wingman.eveskills import state as state_mod
from wingman.eveskills import training as training_mod
from wingman.eveskills.controller import SkillsController

T0 = datetime(2026, 8, 24, 12, 0, 0, tzinfo=UTC)


class Clock:
    """A `now` that only moves when a test moves it."""

    def __init__(self, start=T0):
        self.value = start

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value = self.value + timedelta(seconds=seconds)


class FakeAuthority:
    """Shared-authority seam; authentication details have their own suite."""

    def __init__(self, characters=(), *, token_results=None):
        self._characters = {
            character.character_id: character for character in characters
        }
        self._participant = None
        self._auth_in_progress = False
        self.token_results = list(token_results or ())
        self.access_calls = []
        self.lifecycle_calls = []
        self.forget_calls = []
        self.shutdown_calls = 0

    @property
    def characters(self):
        return tuple(self._characters.values())

    @property
    def auth_in_progress(self):
        return self._auth_in_progress

    def character(self, character_id):
        return self._characters.get(int(character_id))

    def capability_status(self, character_id, capability):
        character = self.character(character_id)
        if character is None:
            return "missing"
        if character.needs_reauth:
            return "reauthenticate"
        required = eveauth_application.CAPABILITY_SCOPES[capability]
        return "enabled" if required.issubset(character.scopes) else "enable"

    @contextmanager
    def lifecycle(self, character_id, capability):
        self.lifecycle_calls.append((character_id, capability))
        if self.capability_status(character_id, capability) != "enabled":
            raise PermissionError("capability not enabled")
        yield SimpleNamespace(
            character=self.character(character_id), capability=capability
        )

    def access_token(self, character_id, capability, *, rejected_token=None):
        self.access_calls.append((character_id, capability, rejected_token))
        if self.token_results:
            result = self.token_results.pop(0)
            if self.token_results:
                return result
            self.token_results.append(result)
            return result
        token = "access-2" if rejected_token is not None else "access-1"
        return AccessTokenResult(token, "", False)

    def start_full_authorization(self):
        return AuthorizationCommandResult(True, "")

    def cancel_authorization(self):
        return AuthorizationCommandResult(True, "")

    def forget(self, character_id):
        character_id = int(character_id)
        self.forget_calls.append(character_id)
        if self._participant is not None:
            prepared = self._participant.prepare_forget(character_id)
            if not prepared.applied:
                return prepared
        self._characters.pop(character_id, None)
        if self._participant is not None:
            self._participant.authority_removed(character_id)
        return MutationResult(True, True, "")

    def register_participant(self, capability, participant):
        assert capability == eveauth_application.SKILLS
        self._participant = participant
        participant.reconcile_characters(self.characters)

    def shutdown(self):
        self.shutdown_calls += 1


class DeferredSpawn:
    """Captures worker targets instead of starting threads.

    Deliberately does NOT run the target on `.start()`: the single-flight
    latch can only be tested if the first worker is still notionally in
    flight when the second request arrives.
    """

    def __init__(self):
        self.targets = []

    def __call__(self, *, target, daemon=False):
        self.targets.append(target)
        return SimpleNamespace(start=lambda: None)

    def run_next(self):
        self.targets.pop(0)()


def build(
    tmp_path,
    *,
    plans=None,
    characters=(),
    selected="",
    authority_characters=None,
    **kwargs,
):
    """A controller over a fresh tmp state dir, with its pushes recorded."""
    plans_dir = tmp_path / "skill_plans"
    plans_dir.mkdir(exist_ok=True)  # Exists, so nothing is seeded.
    for name, body in (plans or {}).items():
        (plans_dir / f"{name}.txt").write_text(body, encoding="utf-8")

    if characters or selected:
        seed = state_mod.SkillsState(
            characters=list(characters), selected_plan_name=selected
        )
        state_mod.save(seed, tmp_path / "eve_skills.json")

    pushed = []
    alerts = []
    now = kwargs.pop("now", Clock())
    authority = kwargs.pop("authority", None)
    sso = kwargs.pop("sso", None)
    roster = authority_characters
    if roster is None:
        authority_source = list(characters)
        if not authority_source and (tmp_path / "eve_skills.json").exists():
            loaded, _warnings = state_mod.load(tmp_path / "eve_skills.json")
            authority_source = loaded.characters
        roster = [
            AuthorityCharacter(
                character_id=character.character_id,
                character_name=f"Character {character.character_id}",
                owner_hash="",
                scopes=tuple(sorted(eveauth_application.SKILLS_SCOPES)),
                authenticated_utc=T0,
                needs_reauth=False,
                generation=0,
            )
            for character in authority_source
        ]
    if authority is None and sso is not None:
        persistent = authority_state_mod.AuthorityState(
            [
                authority_state_mod.AuthorityCharacter(
                    character_id=character.character_id,
                    character_name=character.character_name,
                    owner_hash=character.owner_hash,
                    scopes=character.scopes,
                    authenticated_utc=character.authenticated_utc,
                    needs_reauth=character.needs_reauth,
                    refresh_token_blob="blob",
                )
                for character in roster
            ]
        )
        authority_path = tmp_path / "eve_authority.json"
        authority_state_mod.save_authority(authority_path, persistent)
        validate = kwargs.pop("validate_token", None)
        if validate is None and hasattr(sso, "identity_for"):
            validate = sso.identity_for
        authority = AuthorityController(
            state_path=authority_path,
            authority=persistent,
            alert=lambda kind, title, body: alerts.append((kind, title, body)),
            changed=lambda: None,
            key_source=kwargs.pop("key_source", None),
            spawn=kwargs.get("spawn", threading.Thread),
            launch_browser=kwargs.pop("launch_browser", lambda _url: None),
            now=now,
            sso=sso,
            listener_factory=kwargs.pop("listener_factory", None),
            validate_token=validate,
            wrap_token=lambda token: token,
            unwrap_token=lambda blob: blob or None,
        )
    elif authority is None:
        authority = FakeAuthority(roster)
    for obsolete in (
        "validate_token",
        "key_source",
        "listener_factory",
        "launch_browser",
    ):
        kwargs.pop(obsolete, None)
    controller = SkillsController(
        state_path=tmp_path / "eve_skills.json",
        cache_path=tmp_path / "eve_skills_cache.json",
        plans_dir=plans_dir,
        push=lambda handler, payload: pushed.append((handler, payload)),
        alert=lambda kind, title, body: alerts.append((kind, title, body)),
        authority=authority,
        client=kwargs.pop("client", None) or object(),
        now=now,
        **kwargs,
    )
    authority.register_participant(eveauth_application.SKILLS, controller)
    pushed.clear()  # Registration reconciliation is startup, not a page event.
    return controller, pushed, alerts


def test_skills_state_contains_only_feature_data():
    """Moving credential writes out of Skills is incomplete if a feature
    row can still retain shared identity or credential fields."""
    character = state_mod.Character(character_id=95)

    for field in (
        "character_name",
        "owner_hash",
        "scopes",
        "authenticated_utc",
        "needs_reauth",
        "refresh_token_blob",
    ):
        assert not hasattr(character, field)


def test_character_identity_is_joined_from_shared_authority(tmp_path):
    """A stale name in Skills must never win over the app-wide identity."""
    authority = FakeAuthority(
        [
            AuthorityCharacter(
                character_id=95,
                character_name="Authority Name",
                owner_hash="owner",
                scopes=tuple(sorted(eveauth_application.SKILLS_SCOPES)),
                authenticated_utc=T0,
                needs_reauth=False,
                generation=3,
            )
        ]
    )
    controller, _, _ = build(
        tmp_path,
        characters=[state_mod.Character(character_id=95)],
        authority=authority,
    )

    row = controller.state_payload()["characters"][0]

    assert row["character_name"] == "Authority Name"
    assert row["needs_reauth"] is False


def test_refresh_body_key_error_is_not_mistaken_for_missing_authority(tmp_path):
    controller, _, _ = build(
        tmp_path,
        characters=[state_mod.Character(character_id=95)],
    )

    def fail_after_lease(_character_id):
        raise KeyError("malformed ESI payload")

    controller._refresh_one_leased = fail_after_lease

    with pytest.raises(KeyError, match="malformed ESI payload"):
        controller._refresh_one(95)


def test_owner_change_mapping_uses_reason_not_human_text(tmp_path):
    authority = FakeAuthority(
        [
            AuthorityCharacter(
                character_id=95,
                character_name="Aiga",
                owner_hash="old-owner",
                scopes=tuple(sorted(eveauth_application.SKILLS_SCOPES)),
                authenticated_utc=T0,
                needs_reauth=False,
                generation=0,
            )
        ],
        token_results=[
            AccessTokenResult(
                None,
                "This wording no longer mentions the classification.",
                True,
                "owner_changed",
            )
        ],
    )
    controller, _, _ = build(
        tmp_path,
        characters=[state_mod.Character(character_id=95)],
        authority=authority,
    )

    token, error, invalidated = controller._access_token(95)

    assert token is None
    assert invalidated is True
    assert error == "Character ownership changed. Re-authenticate this character."


def test_authority_persistence_warning_survives_a_skills_error(tmp_path):
    authority = FakeAuthority(
        [
            AuthorityCharacter(
                character_id=95,
                character_name="Aiga",
                owner_hash="owner",
                scopes=tuple(sorted(eveauth_application.SKILLS_SCOPES)),
                authenticated_utc=T0,
                needs_reauth=False,
                generation=0,
                persistence_error="The rotated EVE token could not be saved.",
            )
        ]
    )
    controller, _, _ = build(
        tmp_path,
        characters=[state_mod.Character(character_id=95, error="ESI is unavailable.")],
        authority=authority,
    )

    error = controller.state_payload()["characters"][0]["error"]

    assert "ESI is unavailable." in error
    assert "token could not be saved" in error


def test_refresh_requests_only_skills_and_ignores_missing_fitting_scopes(tmp_path):
    authority = FakeAuthority(
        [
            AuthorityCharacter(
                character_id=95,
                character_name="Skills Pilot",
                owner_hash="owner",
                scopes=tuple(sorted(eveauth_application.SKILLS_SCOPES)),
                authenticated_utc=T0,
                needs_reauth=False,
                generation=0,
            )
        ]
    )
    controller, _, _ = build(
        tmp_path,
        characters=[state_mod.Character(character_id=95)],
        authority=authority,
        client=FakeEsi(),
        spawn=DirectSpawn(),
    )

    controller.refresh_characters()

    assert authority.capability_status(95, eveauth_application.FITTINGS) == "enable"
    assert authority.lifecycle_calls == [(95, eveauth_application.SKILLS)]
    assert authority.access_calls
    assert {capability for _, capability, _ in authority.access_calls} == {
        eveauth_application.SKILLS
    }
    assert controller.state_payload()["characters"][0]["needs_reauth"] is False


def test_startup_reconciliation_save_warning_survives_until_route_read(
    tmp_path, monkeypatch
):
    """A pre-WebView alert is dropped, so startup failures belong in state."""
    authority = FakeAuthority([])
    controller, _pushed, _alerts = build(
        tmp_path,
        characters=[state_mod.Character(character_id=95)],
        authority=authority,
    )
    # Recreate the first registration path because build() registers once.
    controller._reconciled_once = False
    controller._state.upsert(state_mod.Character(character_id=95))
    monkeypatch.setattr(
        state_mod,
        "save",
        lambda *_args: (_ for _ in ()).throw(OSError("disk")),
    )

    controller.reconcile_characters(())

    assert any(
        "reconciliation could not be saved" in warning
        for warning in controller.state_payload()["warnings"]
    )


def test_failed_addition_reconciliation_keeps_the_new_row_live_for_refresh(
    tmp_path, monkeypatch
):
    authority = FakeAuthority([])
    esi = FakeEsi()
    controller, _pushed, alerts = build(
        tmp_path,
        authority=authority,
        client=esi,
        spawn=DirectSpawn(),
    )
    authority._characters[95] = AuthorityCharacter(
        character_id=95,
        character_name="Aiga",
        owner_hash="owner",
        scopes=tuple(sorted(eveauth_application.SKILLS_SCOPES)),
        authenticated_utc=T0,
        needs_reauth=False,
        generation=0,
    )
    original_save = state_mod.save
    calls = 0

    def fail_once(state, path):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("disk")
        original_save(state, path)

    monkeypatch.setattr(state_mod, "save", fail_once)

    controller.reconcile_characters(authority.characters)

    character = controller._state.find(95)
    assert character is not None
    assert character.fetched_utc == T0
    assert authority.lifecycle_calls == [(95, eveauth_application.SKILLS)]
    assert any(call[0].endswith("/skills/") for call in esi.calls)
    assert alerts == [
        (
            "warning",
            "Skills roster not saved",
            "Shared EVE characters are available for this session, but the "
            "Skills roster reconciliation could not be saved.",
        )
    ]


def test_failed_mixed_reconciliation_defers_both_removal_and_addition_until_retry(
    tmp_path, monkeypatch
):
    authority = FakeAuthority(
        [
            AuthorityCharacter(
                character_id=42,
                character_name="Old Pilot",
                owner_hash="old-owner",
                scopes=tuple(sorted(eveauth_application.SKILLS_SCOPES)),
                authenticated_utc=T0,
                needs_reauth=False,
                generation=0,
            )
        ]
    )
    esi = FakeEsi()
    controller, pushed, alerts = build(
        tmp_path,
        characters=[with_snapshot(character_id=42)],
        authority=authority,
        client=esi,
        spawn=DirectSpawn(),
    )
    authority._characters = {
        95: AuthorityCharacter(
            character_id=95,
            character_name="New Pilot",
            owner_hash="new-owner",
            scopes=tuple(sorted(eveauth_application.SKILLS_SCOPES)),
            authenticated_utc=T0,
            needs_reauth=False,
            generation=0,
        )
    }
    original_save = state_mod.save
    calls = 0

    def fail_once(state, path):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("disk")
        original_save(state, path)

    monkeypatch.setattr(state_mod, "save", fail_once)

    verification = controller.reconcile_characters(authority.characters)

    assert verification.blocked_character_ids == frozenset({42})
    assert controller._state.find(42) is not None
    assert controller._state.find(95) is None
    assert pushed == []
    assert authority.lifecycle_calls == []
    assert esi.calls == []
    assert alerts == [
        (
            "warning",
            "Skills roster not saved",
            "Shared EVE characters are available for this session, but the "
            "Skills roster reconciliation could not be saved.",
        )
    ]

    controller.reconcile_characters(authority.characters)

    assert controller._state.find(42) is None
    assert controller._state.find(95) is not None
    assert authority.lifecycle_calls == [(95, eveauth_application.SKILLS)]
    assert any(handler == "onSkills" for handler, _payload in pushed)
    skill_pushes = [payload for handler, payload in pushed if handler == "onSkills"]
    assert skill_pushes[-1]["characters"][0]["character_id"] == 95


def test_the_state_lock_is_re_entrant(tmp_path):
    """A plain Lock would deadlock, not raise.

    Commit paths mutate the roster and then call helpers that save, and the
    save path takes the same lock. With `threading.Lock` the first such
    nesting hangs the worker forever with no traceback and no log line --
    the app simply never finishes a refresh. `RLock` is therefore a
    correctness requirement, not a convenience, and is asserted rather than
    trusted to survive a future edit.
    """
    controller, _, _ = build(tmp_path)

    with controller._lock, controller._lock:  # Deadlocks here under threading.Lock.
        assert True


def test_a_missing_state_file_is_an_empty_roster_not_an_error(tmp_path):
    """First launch has no document at all. state.load is tolerant, and the
    controller must surface that as an empty roster rather than refusing to
    construct -- the route has to render before a character can be added."""
    controller, _, _ = build(tmp_path)

    payload = controller.state_payload()
    assert payload["characters"] == []
    assert payload["selected_plan_name"] == ""


def test_a_character_with_no_snapshot_is_unscored_with_zero_counts(tmp_path):
    """Every newly authorised character is Unscored until its first refresh
    lands, and so is any character whose first refresh failed. The row must
    still render -- the expanded row is the ONLY surface for forgetting or
    re-authenticating, so a character with no row is a character that cannot
    be repaired."""
    character = state_mod.Character(character_id=95)
    controller, _, _ = build(
        tmp_path,
        characters=[character],
        plans={"Interceptor": "Navigation V\n"},
        selected="Interceptor",
    )

    row = controller.state_payload()["characters"][0]

    assert row["readiness"] == "Unscored"
    assert row["fetched_utc"] == ""
    assert (row["active_count"], row["missing_count"], row["unknown_count"]) == (
        0,
        0,
        0,
    )


def test_with_no_plan_selected_every_character_is_unscored(tmp_path):
    """Not an error state: the route opens with nothing selected, and forty
    rows reading Unscored is the correct first frame."""
    character = state_mod.Character(character_id=95, fetched_utc=T0)
    controller, _, _ = build(
        tmp_path, characters=[character], plans={"Interceptor": "Navigation V\n"}
    )

    payload = controller.state_payload()

    assert payload["selected_plan_name"] == ""
    assert payload["characters"][0]["readiness"] == "Unscored"


def test_plan_rows_carry_their_size_and_their_ready_count(tmp_path):
    """The left rail shows a ready ratio per plan, so the payload has to
    score every character against every plan, not only the selected one."""
    controller, _, _ = build(
        tmp_path,
        plans={
            "Interceptor": "Navigation V\nSpaceship Command III\n",
            "Hauler": "Navigation I\n",
        },
    )

    rows = {row["name"]: row for row in controller.state_payload()["plans"]}

    assert rows["Interceptor"]["requirement_count"] == 2
    assert rows["Hauler"]["requirement_count"] == 1
    assert rows["Interceptor"]["ready_count"] == 0  # No characters at all.


def test_a_rejected_plan_file_becomes_a_plan_issue(tmp_path):
    """Any diagnostic rejects the whole file. The row still appears in the
    rail with zero requirements, and the reason rolls up into plan_issues --
    a plan that silently vanished would look like a missing file."""
    controller, _, _ = build(tmp_path, plans={"Broken": "Navigation +5\n"})

    payload = controller.state_payload()

    assert payload["plan_issues"][0]["file_name"] == "Broken.txt"
    assert payload["plan_issues"][0]["diagnostics"][0]["line"] == 1


def test_selecting_a_plan_is_case_insensitive_and_stores_the_file_spelling(tmp_path):
    """All comparisons on plan names are case-insensitive, but what is
    persisted is the file's own spelling -- the rail renders from the stored
    name, and echoing the caller's casing would make the selected row look
    different from the same row unselected."""
    controller, _, _ = build(tmp_path, plans={"Interceptor": "Navigation V\n"})

    assert controller.select_plan("iNtErCePtOr") is True
    assert controller.state_payload()["selected_plan_name"] == "Interceptor"


def test_selecting_an_unknown_plan_reports_failure(tmp_path):
    """The page can hold a stale plan list across a reload that deleted the
    file. False is the honest answer; the forced push that does not happen
    is deliberate, because nothing changed."""
    controller, pushed, _ = build(tmp_path, plans={"Interceptor": "Navigation V\n"})

    assert controller.select_plan("Gone") is False
    assert pushed == []


def test_a_save_failure_rolls_back_the_selection_and_warns(tmp_path):
    """Mirrors TriffSkillsController.cs:331-341's SelectPlan: a save failure
    must not leave the page believing an unsaved selection is durable.

    Without the rollback, the in-memory value would diverge from disk with
    nothing shown -- the selection would silently revert on the next
    unrelated save, or on the next launch, with no warning ever having
    appeared."""
    controller, _, alerts = build(tmp_path, plans={"Interceptor": "Navigation V\n"})
    controller._save_locked = lambda: False  # Simulate an unwritable disk.

    assert controller.select_plan("Interceptor") is False
    assert controller._state.selected_plan_name == ""  # Rolled back.
    assert alerts and alerts[-1][0] == "warning"


def test_selecting_persists_across_a_reconstruction(tmp_path):
    """The selection lives in the state document, not in the page. Reopening
    Wingman must land on the plan the user was last looking at."""
    controller, _, _ = build(tmp_path, plans={"Interceptor": "Navigation V\n"})
    controller.select_plan("Interceptor")

    reopened, _, _ = build(tmp_path, plans={"Interceptor": "Navigation V\n"})
    assert reopened.state_payload()["selected_plan_name"] == "Interceptor"


def test_an_identical_push_is_skipped_but_a_mutation_always_pushes(tmp_path):
    """onSkills carries the whole world and is the largest payload in the
    app. Mutation handlers push it on both success and failure paths, so an
    unchanged re-push is common -- and a full serialise plus a roster rebuild
    for an identical payload is pure cost.

    Mutations force the push regardless, because the dedupe is an
    optimisation and must never be the reason a committed change fails to
    reach the page."""
    controller, pushed, _ = build(tmp_path, plans={"A": "Navigation I\n"})

    controller._push_state()
    controller._push_state()  # Identical: skipped.
    assert len(pushed) == 1

    controller.select_plan("A")  # Mutation: forced.
    controller.select_plan("A")  # Same value, still forced.
    assert len(pushed) == 3


def test_reload_plans_sees_a_file_added_since_construction(tmp_path):
    """The whole point of the button: the user drops a .txt in the folder
    with Wingman already running."""
    controller, _, _ = build(tmp_path, plans={"A": "Navigation I\n"})
    (tmp_path / "skill_plans" / "B.txt").write_text("Navigation II\n", encoding="utf-8")

    controller.reload_plans()

    assert [p["name"] for p in controller.state_payload()["plans"]] == ["A", "B"]


def test_open_plans_folder_uses_the_injected_opener(tmp_path):
    """os.startfile does not exist off Windows, so the shell call is
    injected and the suite asserts the path rather than the platform."""
    opened = []
    controller, _, _ = build(tmp_path, open_folder=opened.append)

    controller.open_plans_folder()

    assert opened == [tmp_path / "skill_plans"]


def test_a_failing_opener_warns_instead_of_raising(tmp_path):
    """This runs on the bridge thread. An exception here surfaces only as a
    rejected promise in a page nobody is debugging, so it becomes the alert
    channel that already exists."""

    def boom(path):
        raise OSError("no shell")

    controller, _, alerts = build(tmp_path, open_folder=boom)

    controller.open_plans_folder()

    assert alerts and alerts[0][0] == "warning"


# ----- refresh worker fakes -------------------------------------------------


def esi_response(status, data=None, etag="", error="", path="/x/"):
    return esi_mod.EsiResponse(
        status=status, data=data, error=error, etag=etag, method="GET", path=path
    )


SKILLS_BODY = {
    "skills": [
        {
            "skill_id": 3327,
            "active_skill_level": 4,
            "trained_skill_level": 5,
            "skillpoints_in_skill": 200000,
        }
    ]
}
# Exactly the five learning attributes the estimator needs. Real ESI sends
# remap dates and counts alongside them; the parser drops those, and
# `test_extra_attribute_fields_are_dropped_not_stored` pins that it must --
# state.py only accepts a map that is exactly these five keys.
ATTRIBUTES_BODY = {
    "charisma": 19,
    "intelligence": 20,
    "memory": 20,
    "perception": 27,
    "willpower": 21,
}
QUEUE_BODY = [
    {
        "skill_id": 3327,
        "finished_level": 5,
        "queue_position": 0,
        "start_date": "2026-08-24T12:00:00Z",
        "finish_date": "2026-08-26T12:00:00Z",
    }
]

# Name -> dogma attribute id, inverted from skillids' own table rather than
# retyped: a fixture that disagreed with the decoder would pass by
# describing a response ESI never sends.
_ATTRIBUTE_IDS = {name: aid for aid, name in skillids_mod.ATTRIBUTE_ID_TO_NAME.items()}


def _type_body(rank: int, primary: str, secondary: str) -> dict:
    """One /v3/universe/types/{id}/ body carrying a skill's training dogma.

    275 is rank (skillTimeConstant); 180/181 are REFERENCES to one of the
    five attribute ids, which is why the values here are ids and not the
    attribute names the decoded metadata carries.
    """
    return {
        "group_id": 255,
        "dogma_attributes": [
            {"attribute_id": skillids_mod.DOGMA_SKILL_TIME_CONSTANT, "value": rank},
            {
                "attribute_id": skillids_mod.DOGMA_PRIMARY_ATTRIBUTE,
                "value": _ATTRIBUTE_IDS[primary],
            },
            {
                "attribute_id": skillids_mod.DOGMA_SECONDARY_ATTRIBUTE,
                "value": _ATTRIBUTE_IDS[secondary],
            },
        ],
    }


class FakeEsi:
    """Replays scripted responses per path suffix, and records every call.

    Keyed on the suffix rather than the whole path so a test does not have
    to repeat the character id. A path with no script is an assertion
    failure, not a default -- an unexpected ESI call is exactly the bug
    these tests exist to catch.
    """

    def __init__(self, skills=None, queue=None, attributes=None, types=None):
        self.skills = list(skills or [esi_response(200, SKILLS_BODY, etag='"s1"')])
        self.queue = list(queue or [esi_response(200, QUEUE_BODY, etag='"q1"')])
        self.attributes = list(
            attributes or [esi_response(200, ATTRIBUTES_BODY, etag='"a1"')]
        )
        # Public type details, keyed by type id rather than scripted in
        # order: the metadata backfill fetches them concurrently, so there
        # is no call order for a list to stand for.
        self.types = dict(types or {})
        self.calls = []
        self.on_get = None
        self.on_type = None
        self._hooked = False

    def get(self, path, *, token=None, etag=None):
        self.calls.append((path, token, etag))
        if self.on_get is not None and not self._hooked:
            self._hooked = True  # Fires once, or the test never ends.
            self.on_get(path)
        if "/universe/types/" in path:
            # Checked first, and by id rather than by suffix: an unrouted
            # type call would otherwise be answered by the queue script and
            # silently look like a malformed type body.
            if self.on_type is not None:
                self.on_type(path)
            type_id = int(path.rstrip("/").rsplit("/", 1)[-1])
            assert type_id in self.types, f"unscripted ESI type call: {path}"
            return self.types[type_id]
        if path.endswith("/skills/"):
            script = self.skills
        elif path.endswith("/attributes/"):
            script = self.attributes
        else:
            script = self.queue
        assert script, f"unscripted ESI call: {path}"
        return script.pop(0) if len(script) > 1 else script[0]

    def post(self, path, body, *, token=None):
        raise AssertionError(f"unexpected POST {path}")


class FakeSso:
    """sso.refresh_token without a network.

    Only the functions the controller calls are defined. OAuthError itself
    is NOT faked: the controller's `except` clause names the real class from
    the real module, so a fake raising anything else would pass a test the
    production path would fail.
    """

    def __init__(self, expires_in=1200, raises=None, identities=None):
        self.expires_in = expires_in
        self.raises = raises
        self.refreshes = []
        # (character_id, owner_hash) per successful refresh, cycled by call
        # order -- refreshes happen strictly in character order (Task 13's
        # refresh pass is sequential), so this is enough to give a
        # multi-character test a matching identity per call without the
        # fake having to be told which character it is minting for.
        self.identities = list(identities or [(95, "")])

    def refresh_token(self, token, **kwargs):
        self.refreshes.append(token)
        if self.raises is not None:
            raise self.raises
        return sso_mod.TokenSet(
            access_token=f"access-{len(self.refreshes)}",
            refresh_token=f"refresh-{len(self.refreshes)}",
            expires_in=self.expires_in,
        )

    def identity_for(self, token, **kwargs):
        """The default `validate_token` fake: a matching, valid identity.

        `build()` wires this in automatically so existing tests that never
        asked to exercise identity/owner-hash checks are not broken by
        item 3's real-by-default `jwt_mod.validate` call.
        """
        character_id, owner_hash = self.identities[
            (len(self.refreshes) - 1) % len(self.identities)
        ]
        return jwt_mod.EveIdentity(
            character_id=character_id,
            name="Test Pilot",
            owner_hash=owner_hash,
            scopes=frozenset(application.SCOPES),
        )


class DirectSpawn:
    """Runs the worker inline on `.start()`, so no test waits on a thread."""

    def __init__(self):
        self.started = 0

    def __call__(self, *, target, daemon=False):
        self.started += 1
        return SimpleNamespace(start=target)


@pytest.fixture(autouse=True)
def plaintext_tokens(monkeypatch):
    """DPAPI is Windows-only, so the crypt seam is bypassed for the suite.

    tokens.py's own tests cover wrap/unwrap and the undecryptable blob.
    Here the token is a value the controller carries, and encrypting it
    would only make the assertions unreadable.
    """
    from wingman.eveskills import tokens as tokens_mod

    monkeypatch.setattr(tokens_mod, "wrap", lambda token, **kw: token)
    monkeypatch.setattr(tokens_mod, "unwrap", lambda blob, **kw: blob or None)


def test_two_concurrent_refreshes_produce_exactly_one_worker(tmp_path):
    """Ported from TriffSkillsController.cs:358. A second worker would send
    two ESI calls per character for the same data, doubling the pressure on
    the error-limit budget to compute the same answer twice -- and both
    workers would commit into the same roster."""
    spawn = DeferredSpawn()
    controller, _, _ = build(tmp_path, spawn=spawn)

    controller.refresh_characters()
    controller.refresh_characters()

    assert len(spawn.targets) == 1


def test_refresh_spawn_failure_restores_idle_shutdown_state(tmp_path):
    def fail_spawn(**_kwargs):
        raise RuntimeError("thread unavailable")

    controller, _, _ = build(tmp_path, spawn=fail_spawn)

    with pytest.raises(RuntimeError, match="thread unavailable"):
        controller.refresh_characters()

    assert controller._refresh_in_flight is False
    assert controller._refresh_idle.is_set()


def test_the_running_pass_re_enters_when_one_was_requested_during_it(tmp_path):
    """The latch drops the *worker*, never the *request*. A refresh clicked
    while one is running must still produce fresh data -- otherwise the
    button silently does nothing during the twenty seconds a forty-character
    pass takes, which reads as a broken button."""
    character = state_mod.Character(character_id=95)
    esi = FakeEsi()
    controller = None
    esi.on_get = lambda path: controller.refresh_characters()  # once; see below
    controller, _, _ = build(
        tmp_path, characters=[character], client=esi, sso=FakeSso(), spawn=DirectSpawn()
    )

    controller.refresh_characters()

    # Two passes over the one character: two skills calls, and (since both
    # core halves succeed each time) two attributes calls behind them.
    assert len([c for c in esi.calls if c[0].endswith("/skills/")]) == 2
    assert len([c for c in esi.calls if c[0].endswith("/attributes/")]) == 2


def test_a_request_that_arrives_during_a_pass_that_then_blows_up_is_not_dropped(
    tmp_path,
):
    """Round 2 review, item 7 (Minor). The exception handler used to clear
    `_refresh_again` and stop -- so a refresh clicked while the running pass
    was about to fail vanished silently, unlike a refresh clicked during a
    pass that succeeds. Ported from TriffSkillsController.cs:385, which
    re-kicks on any exit path as long as a request is still pending, not
    only on a clean one."""
    character = state_mod.Character(character_id=95)
    esi = FakeEsi()
    controller = None

    def blow_up_once(path):
        controller.refresh_characters()  # arrives while this pass is "in flight"
        raise RuntimeError("boom")

    esi.on_get = blow_up_once
    controller, _, _ = build(
        tmp_path, characters=[character], client=esi, sso=FakeSso(), spawn=DirectSpawn()
    )

    controller.refresh_characters()

    # The failed pass's one (raising) skills call, plus a second pass that
    # runs to completion: the request was not dropped just because the
    # first pass blew up instead of finishing cleanly. Only the completed
    # pass reaches the queue and the supplemental attributes call.
    assert len([c for c in esi.calls if c[0].endswith("/skills/")]) == 2
    assert len([c for c in esi.calls if c[0].endswith("skillqueue/")]) == 1
    assert len([c for c in esi.calls if c[0].endswith("/attributes/")]) == 1
    assert controller._refresh_in_flight is False
    assert controller._refresh_again is False


def with_snapshot(**kwargs):
    """A character that already has committed data, so a later refresh has
    something to preserve or overwrite.

    skill_points/skill_points_complete default to a valid, complete map so
    the stored skills_etag stays valid under from_dict's migration rule
    (state.py: an ETag survives a load only alongside a complete SP map) --
    keeping every existing conditional-request test representative of a
    modern snapshot. The attributes triplet defaults the same way.
    """
    for authority_field in (
        "character_name",
        "owner_hash",
        "scopes",
        "authenticated_utc",
        "needs_reauth",
        "refresh_token_blob",
    ):
        kwargs.pop(authority_field, None)
    defaults = dict(
        character_id=95,
        fetched_utc=T0,
        active_levels={3327: 3},
        trained_levels={3327: 3},
        skills_etag='"old-s"',
        queue_etag='"old-q"',
        skill_points={3327: 1000},
        skill_points_complete=True,
        attributes=dict(ATTRIBUTES_BODY),
        attributes_fetched_utc=T0,
        attributes_etag='"old-a"',
    )
    defaults.update(kwargs)
    return state_mod.Character(**defaults)


def run_refresh(tmp_path, esi, character=None, clock=None, **kwargs):
    clock = clock or Clock()
    controller, pushed, _alerts = build(
        tmp_path,
        characters=[character or with_snapshot()],
        client=esi,
        sso=FakeSso(),
        spawn=DirectSpawn(),
        now=clock,
        **kwargs,
    )
    controller.refresh_characters()
    return controller, pushed, clock


def test_200_responses_commit_core_and_attributes(tmp_path):
    """The ordinary path. fetched_utc moves, all three etags are stored, the
    estimate inputs (SP and attributes) land with them, and any previous
    error is cleared."""
    clock = Clock()
    clock.advance(3600)
    esi = FakeEsi()
    controller, _, _ = run_refresh(tmp_path, esi, clock=clock)

    row = controller.state_payload()["characters"][0]
    ch = controller._state.characters[0]
    assert row["fetched_utc"] == clock.value.isoformat()
    assert ch.active_levels == {3327: 4} and ch.trained_levels == {3327: 5}
    assert (ch.skills_etag, ch.queue_etag) == ('"s1"', '"q1"')
    assert row["error"] == "" and row["stale"] is False
    assert ch.skill_points == {3327: 200000}
    assert ch.skill_points_complete is True
    assert ch.attributes == ATTRIBUTES_BODY
    assert ch.attributes_etag == '"a1"'
    assert ch.attributes_fetched_utc == clock.value
    assert ch.attributes_error == ""


def test_304_and_304_keeps_the_data_and_still_advances_fetched_utc(tmp_path):
    """fetched_utc means "both halves were confirmed current at this time",
    not "both halves were re-downloaded". Nothing being modified is a
    successful confirmation, not a skipped one -- and if it did NOT advance,
    a character whose skills never change would drift toward looking stale
    forever."""
    clock = Clock()
    clock.advance(3600)
    esi = FakeEsi(skills=[esi_response(304)], queue=[esi_response(304)])
    controller, _, _ = run_refresh(tmp_path, esi, clock=clock)

    ch = controller._state.characters[0]
    assert ch.fetched_utc == clock.value
    assert ch.active_levels == {3327: 3}  # Untouched.
    assert ch.skills_etag == '"old-s"'  # A 304 carries no new etag.


def test_200_and_304_commits_the_fresh_half_and_keeps_the_stored_one(tmp_path):
    """Per-endpoint freshness is the hazard conditional requests introduce.
    The rule that makes it safe: a 304 means the stored half is already
    current, so the pair is still one coherent snapshot."""
    esi = FakeEsi(queue=[esi_response(304)])
    controller, _, _ = run_refresh(tmp_path, esi)

    ch = controller._state.characters[0]
    assert ch.active_levels == {3327: 4}  # Fresh skills committed.
    assert ch.queue_etag == '"old-q"'  # Stored queue kept.
    assert ch.error == ""


def test_a_legacy_snapshot_refetches_skills_unconditionally(tmp_path):
    """A document written before this package tracked SP has a skills ETag
    and no SP. Sending that ETag would earn a 304 -- a confirmation that
    levels already in hand are current -- and the SP that is missing would
    never arrive, so the estimate would stay unavailable forever. state.py
    drops such an ETag on load; this pins that the refresh built from that
    load really does send an unconditional request and really does backfill.

    Built from a document on disk rather than from a saved `Character`,
    because the migration rule this depends on lives in `from_dict` and a
    freshly constructed object never passes through it.
    """
    legacy = {
        "version": 1,
        "characters": [
            {
                "character_id": 95,
                "character_name": "Aiga Otsolen",
                "refresh_token_blob": "blob",
                "fetched_utc": T0.isoformat(),
                "active_levels": {"3327": 3},
                "trained_levels": {"3327": 3},
                "skills_etag": '"old-s"',
                "queue_etag": '"old-q"',
            }
        ],
    }
    (tmp_path / "eve_skills.json").write_text(json.dumps(legacy), encoding="utf-8")
    esi = FakeEsi()
    controller, _, _ = build(tmp_path, client=esi, sso=FakeSso(), spawn=DirectSpawn())

    controller.refresh_characters()

    skills_calls = [c for c in esi.calls if c[0].endswith("/skills/")]
    assert [c[2] for c in skills_calls] == [None], "no conditional header"
    ch = controller._state.characters[0]
    assert ch.skill_points == {3327: 200000}
    assert ch.skill_points_complete is True
    assert ch.skills_etag == '"s1"', "and the fresh ETag is worth keeping"


def test_an_incomplete_sp_body_keeps_readiness_and_retries_unconditionally(tmp_path):
    """The two halves of a skills response have different failure rules.
    Levels stay tolerant -- one bad row costs one skill, which is all
    readiness needs -- while SP is all-or-nothing, because a partial SP map
    cannot say it is partial and would be summed into a confidently wrong
    training estimate. The ETag goes with the SP: keeping it would earn a
    304 next time and lock the character out of ever getting a complete
    body."""
    incomplete = {
        "skills": [
            {
                "skill_id": 3327,
                "active_skill_level": 4,
                "trained_skill_level": 5,
                "skillpoints_in_skill": 200000,
            },
            # Valid to the level parser, no SP at all: NOT zero SP.
            {"skill_id": 3300, "active_skill_level": 2, "trained_skill_level": 2},
        ]
    }
    esi = FakeEsi(
        skills=[
            esi_response(200, incomplete, etag='"s2"'),
            esi_response(200, SKILLS_BODY, etag='"s3"'),
        ]
    )
    controller, _, _ = run_refresh(tmp_path, esi)

    ch = controller._state.characters[0]
    assert ch.active_levels, "readiness levels still follow tolerant parsing"
    assert ch.active_levels == {3327: 4, 3300: 2}
    assert ch.skill_points == {}
    assert ch.skill_points_complete is False
    assert ch.skills_etag == "", "the next refresh must fetch another body"

    controller.refresh_characters()

    skills_calls = [c for c in esi.calls if c[0].endswith("/skills/")]
    assert skills_calls[1][2] is None, "the retry is unconditional"
    ch = controller._state.characters[0]
    assert ch.skill_points == {3327: 200000}
    assert ch.skill_points_complete is True
    assert ch.skills_etag == '"s3"'


def test_extra_attribute_fields_are_dropped_not_stored(tmp_path):
    """ESI sends remap dates and counts alongside the five learning
    attributes. state.py accepts a map that is EXACTLY the five, so storing
    the response whole would load back as no attributes at all on the next
    launch -- a refresh that looks successful and silently stops working
    when the app restarts."""
    esi = FakeEsi(
        attributes=[
            esi_response(
                200,
                dict(
                    ATTRIBUTES_BODY,
                    bonus_remaps=2,
                    last_remap_date="2026-01-01T00:00:00Z",
                    accrued_remap_cooldown_date="2026-02-01T00:00:00Z",
                ),
                etag='"a1"',
            )
        ]
    )
    controller, _, _ = run_refresh(
        tmp_path,
        esi,
        # No stored attributes to fall back on, so this can only pass by
        # actually parsing the response.
        character=with_snapshot(
            attributes={}, attributes_fetched_utc=None, attributes_etag=""
        ),
    )

    assert controller._state.characters[0].attributes == ATTRIBUTES_BODY
    reloaded, _ = state_mod.load(tmp_path / "eve_skills.json")
    assert reloaded.find(95).attributes == ATTRIBUTES_BODY


def test_committed_estimate_inputs_survive_a_reload(tmp_path):
    """Attributes and their timestamp are persisted as a pair, and state.py
    loads them only when BOTH are valid. A commit that wrote one without the
    other would look right in memory and come back empty next launch, which
    is the failure mode nothing in memory can catch."""
    clock = Clock()
    clock.advance(3600)
    esi = FakeEsi()
    run_refresh(tmp_path, esi, clock=clock)

    reloaded, _ = state_mod.load(tmp_path / "eve_skills.json")
    ch = reloaded.find(95)
    assert ch.attributes == ATTRIBUTES_BODY
    assert ch.attributes_fetched_utc == clock.value
    assert ch.attributes_etag == '"a1"'
    assert ch.skill_points == {3327: 200000}
    assert ch.skill_points_complete is True
    assert ch.skills_etag == '"s1"'


@pytest.mark.parametrize(
    "response",
    [
        pytest.param(esi_response(500, error="upstream"), id="server_error"),
        pytest.param(esi_response(403, error="forbidden"), id="forbidden"),
        pytest.param(
            esi_response(200, {"charisma": 19}, etag='"a2"'), id="malformed_body"
        ),
    ],
)
def test_a_failed_attributes_call_still_commits_the_core_snapshot(tmp_path, response):
    """Attributes are supplemental. Discarding a good skills-and-queue
    refresh because a training estimate could not be computed would trade
    the feature the route exists for against a number beside it -- and the
    403 case would additionally delete a working refresh token, costing a
    re-authentication for a request readiness never needed."""
    clock = Clock()
    clock.advance(3600)
    esi = FakeEsi(attributes=[response])
    controller, pushed, _ = run_refresh(tmp_path, esi, clock=clock)

    ch = controller._state.characters[0]
    assert ch.active_levels == {3327: 4}, "the core snapshot still commits"
    assert ch.skill_points == {3327: 200000}
    assert ch.fetched_utc == clock.value
    assert (ch.skills_etag, ch.queue_etag) == ('"s1"', '"q1"')
    assert ch.error == ""
    authority = controller._authority.character(95)
    assert authority.needs_reauth is False
    assert controller._authority._state.characters[0].refresh_token_blob.startswith(
        "refresh-"
    ), "the shared grant is untouched"
    assert controller.state_payload()["characters"][0]["stale"] is False
    progress = [p for handler, p in pushed if handler == "onSkillsProgress"]
    assert [p["error"] for p in progress] == [""], "not a per-character failure"
    # Unusable for an estimate, and honest about why: the stored attributes
    # are kept for recovery and diagnostics, but their confirmed time does
    # NOT move, so nothing can pair them with the SP just downloaded.
    assert ch.attributes_error
    assert ch.attributes == ATTRIBUTES_BODY
    assert ch.attributes_fetched_utc == T0
    assert ch.attributes_fetched_utc < ch.fetched_utc


def test_a_supplemental_failure_persists_beside_the_unmoved_pair(tmp_path):
    """The failure has to outlive the process for the same reason the
    success does: a restart that lost `attributes_error` would present a
    stale attribute snapshot as if it had just been confirmed."""
    clock = Clock()
    clock.advance(3600)
    esi = FakeEsi(attributes=[esi_response(500, error="upstream")])
    run_refresh(tmp_path, esi, clock=clock)

    reloaded, _ = state_mod.load(tmp_path / "eve_skills.json")
    ch = reloaded.find(95)
    assert ch.attributes_error
    assert ch.attributes == ATTRIBUTES_BODY
    assert ch.attributes_fetched_utc == T0


def test_a_304_attributes_response_reconfirms_the_stored_snapshot(tmp_path):
    """Same rule as the core 304: nothing being modified is a successful
    confirmation, not a skipped one. Without the stamp a character whose
    attributes never change (most of them, most of the time) would drift
    toward looking permanently unconfirmed."""
    clock = Clock()
    clock.advance(3600)
    esi = FakeEsi(attributes=[esi_response(304)])
    controller, _, _ = run_refresh(
        tmp_path,
        esi,
        character=with_snapshot(attributes_error="a previous fetch failed"),
        clock=clock,
    )

    attribute_calls = [c for c in esi.calls if c[0].endswith("/attributes/")]
    assert [c[2] for c in attribute_calls] == ['"old-a"'], "conditional request"
    ch = controller._state.characters[0]
    assert ch.attributes == ATTRIBUTES_BODY
    assert ch.attributes_etag == '"old-a"', "a 304 carries no new etag"
    assert ch.attributes_fetched_utc == clock.value
    assert ch.attributes_error == "", "the stale failure is cleared"


def test_an_attributes_200_without_an_etag_does_not_invent_one(tmp_path):
    """An empty ETag header only means the next request is unconditional,
    which is wasteful rather than wrong -- but clearing the stored one, or
    keeping it as if it described this new body, would be either a wasted
    request forever or a 304 answering for a body it never saw."""
    clock = Clock()
    clock.advance(3600)
    esi = FakeEsi(attributes=[esi_response(200, ATTRIBUTES_BODY)])
    controller, _, _ = run_refresh(tmp_path, esi, clock=clock)

    ch = controller._state.characters[0]
    assert ch.attributes_etag == '"old-a"'
    assert ch.attributes_fetched_utc == clock.value
    assert ch.attributes_error == ""


def test_a_failing_queue_call_commits_nothing_at_all(tmp_path):
    """THE critical rule. Current skills evaluated against a stale queue
    produce a Training verdict with an ETA drawn from a queue the character
    has since changed -- and the row shows no error, because the skills call
    succeeded. Quiet and wrong is worse than loud and stale."""
    clock = Clock()
    clock.advance(3600)
    esi = FakeEsi(queue=[esi_response(500, error="upstream")])
    controller, _, _ = run_refresh(tmp_path, esi, clock=clock)

    ch = controller._state.characters[0]
    assert ch.active_levels == {3327: 3}, "the fresh skills must NOT be kept"
    assert ch.skills_etag == '"old-s"', "nor the etag that would hide it next time"
    assert ch.fetched_utc == T0, "fetched_utc must not move"
    assert ch.error
    row = controller.state_payload()["characters"][0]
    assert row["needs_reauth"] is False
    assert row["stale"] is True
    assert not [c for c in esi.calls if c[0].endswith("/attributes/")], (
        "no snapshot is being committed, so the supplemental call has "
        "nothing to attach to"
    )


def test_a_failing_skills_call_skips_the_queue_call_entirely(tmp_path):
    """Ported short-circuit. The queue result could not be committed on its
    own, so spending the request only burns error-limit budget -- and the
    supplemental attributes call is skipped for the same reason."""
    esi = FakeEsi(skills=[esi_response(503, error="busy")])
    controller, _, _ = run_refresh(tmp_path, esi)

    assert [c[0] for c in esi.calls] == ["/v4/characters/95/skills/"]
    assert controller._state.characters[0].fetched_utc == T0


def test_cached_skill_data_survives_a_failure(tmp_path):
    """A transient ESI blip must not look like data loss. This is what makes
    `stale` mean "you are looking at last-good data" rather than "empty"."""
    esi = FakeEsi(skills=[esi_response(503, error="busy")])
    controller, _, _ = run_refresh(tmp_path, esi)

    assert controller._state.characters[0].active_levels == {3327: 3}


@pytest.mark.parametrize("status", [401, 403])
def test_an_endpoint_rejection_does_not_delete_the_shared_grant(tmp_path, status):
    """An endpoint response is a Skills operation error, not OAuth evidence.
    The shared grant may still be valid for Skills and Fittings, so only an
    SSO refresh or validated identity outcome may invalidate it."""
    esi = FakeEsi(skills=[esi_response(status, error="denied")])
    controller, _, _ = run_refresh(tmp_path, esi)

    ch = controller._state.characters[0]
    authority = controller._authority.character(95)
    assert authority.needs_reauth is False
    assert controller._authority._state.characters[0].refresh_token_blob.startswith(
        "refresh-"
    )
    assert ch.error == (
        "EVE rejected the stored authorisation. Re-authenticate this character."
    )
    assert ch.active_levels == {3327: 3}, "last-good data still stays visible"


def test_a_transient_failure_does_not_ask_for_re_authentication(tmp_path):
    """A 5xx is ESI having a bad minute. Showing a re-authenticate banner
    for it would send the user through a consent screen that fixes nothing
    and costs them their cached snapshot.

    The 503 is from the ESI call, not the SSO one -- the token refresh
    itself still succeeds, and EVE still rotates the refresh token on that
    success (TriffSkillsAuthentication.cs:170 does the same unconditional
    rotation whenever the new token is non-blank). So the blob legitimately
    becomes the new one; what must NOT happen is needs_reauth or a deleted
    token, which only a definitive failure causes.
    """
    esi = FakeEsi(skills=[esi_response(503, error="busy")])
    controller, _, _ = run_refresh(tmp_path, esi)

    authority = controller._authority.character(95)
    assert authority.needs_reauth is False
    assert controller._authority._state.characters[0].refresh_token_blob == "refresh-1"


def test_a_definitive_oauth_error_is_definitive_here_too(tmp_path):
    """invalid_grant means the refresh token is revoked or already used.
    OAuthError.definitive is the classification; this asserts the controller
    honours it rather than inventing a second one."""
    esi = FakeEsi()
    controller, _, _ = build(
        tmp_path,
        characters=[with_snapshot()],
        client=esi,
        sso=FakeSso(raises=sso_mod.OAuthError(400, "invalid_grant", "revoked")),
        spawn=DirectSpawn(),
    )
    controller.refresh_characters()

    authority = controller._authority.character(95)
    snapshot = controller._state.find(95)
    assert authority.needs_reauth is True
    assert controller._authority._state.characters[0].refresh_token_blob == ""
    assert snapshot.fetched_utc is None
    assert snapshot.active_levels == {}
    assert snapshot.trained_levels == {}
    assert snapshot.queue == ()
    assert snapshot.skills_etag == snapshot.queue_etag == ""
    assert esi.calls == [], "no ESI call is worth making without a token"


def test_a_transient_oauth_error_keeps_the_token(tmp_path):
    """An SSO 503 is not a revoked grant. Deleting the token here would cost
    the user a re-authentication for CCP's downtime."""
    controller, _, _ = build(
        tmp_path,
        characters=[with_snapshot()],
        client=FakeEsi(),
        sso=FakeSso(raises=sso_mod.OAuthError(503, "server_error", "down")),
        spawn=DirectSpawn(),
    )
    controller.refresh_characters()

    authority = controller._authority.character(95)
    assert authority.needs_reauth is False
    assert controller._authority._state.characters[0].refresh_token_blob == "blob"


def test_a_cached_token_is_reused_across_every_call(tmp_path):
    """Three ESI calls per character must not mean three token refreshes. At
    forty characters that is eighty wasted SSO round trips per click."""
    sso = FakeSso()
    controller, _, _ = build(
        tmp_path,
        characters=[with_snapshot()],
        client=FakeEsi(),
        sso=sso,
        spawn=DirectSpawn(),
    )
    controller.refresh_characters()

    assert len(sso.refreshes) == 1


def test_a_401_forces_exactly_one_refresh_and_one_retry(tmp_path):
    """The stampede fix. A forced refresh only actually refreshes when the
    cached token is still the one ESI rejected -- so callers queued behind
    the first find a token that no longer matches and reuse it, and one
    stale token produces one refresh rather than N."""
    sso = FakeSso()
    esi = FakeEsi(
        skills=[
            esi_response(401, error="expired"),
            esi_response(200, SKILLS_BODY, etag='"s1"'),
        ]
    )
    controller, _, _ = build(
        tmp_path, characters=[with_snapshot()], client=esi, sso=sso, spawn=DirectSpawn()
    )
    controller.refresh_characters()

    skills_calls = [c for c in esi.calls if c[0].endswith("/skills/")]
    assert len(skills_calls) == 2  # One 401, one retry.
    assert skills_calls[0][1] != skills_calls[1][1]  # A different token.
    # Two refreshes total: the initial mint, and the one the 401 forced.
    # The queue and attributes calls that follow reuse the second and add
    # none.
    assert len(sso.refreshes) == 2


def test_an_expiring_token_is_refreshed_before_it_is_used(tmp_path):
    """A token that is valid when checked and expired when it lands is a
    401 the user pays a retry for. The margin covers the round trip."""
    sso = FakeSso(expires_in=10)  # Inside TOKEN_EXPIRY_MARGIN_S.
    controller, _, _ = build(
        tmp_path,
        characters=[with_snapshot()],
        client=FakeEsi(),
        sso=sso,
        spawn=DirectSpawn(),
    )
    controller.refresh_characters()

    assert len(sso.refreshes) == 3, "the later calls must not reuse it"


def test_omitted_refresh_token_does_not_wipe_the_stored_one(tmp_path):
    """MANDATORY CORRECTION 1. EVE sometimes omits the refresh token on a
    refresh response, meaning the previous one is still valid. sso.py
    reports that as refresh_token="" -- faithful to EveSso.cs, which does
    not distinguish "omitted" from "empty" at that layer either -- and
    tokens.wrap("") returns "", the no-token sentinel. Writing that straight
    into refresh_token_blob would silently erase a valid stored credential;
    the character then fails definitively on the NEXT refresh with nothing
    explaining why."""

    class OmittingSso:
        def __init__(self):
            self.refreshes = []

        def refresh_token(self, token, **kwargs):
            self.refreshes.append(token)
            return sso_mod.TokenSet(
                access_token="access-1", refresh_token="", expires_in=1200
            )

        def identity_for(self, token, **kwargs):
            return jwt_mod.EveIdentity(
                character_id=95,
                name="Test Pilot",
                owner_hash="",
                scopes=frozenset(application.SCOPES),
            )

    sso = OmittingSso()
    controller, _, _ = build(
        tmp_path,
        characters=[with_snapshot()],
        client=FakeEsi(),
        sso=sso,
        spawn=DirectSpawn(),
    )
    controller.refresh_characters()

    assert len(sso.refreshes) == 1
    assert controller._authority._state.characters[0].refresh_token_blob == "blob"


def test_a_whitespace_only_refresh_token_does_not_wipe_the_stored_one(tmp_path):
    """MANDATORY CORRECTION 2 (round 2 review). `if token_set.refresh_token:`
    catches "" but not "   " -- EVE has never been observed sending a
    whitespace-only value, but IsNullOrWhiteSpace
    (TriffSkillsAuthentication.cs:170) is the actual contract, and the same
    reasoning as the omitted-token case above applies: bare truthiness would
    let "   " sail through and overwrite a valid stored credential."""

    class WhitespaceSso:
        def __init__(self):
            self.refreshes = []

        def refresh_token(self, token, **kwargs):
            self.refreshes.append(token)
            return sso_mod.TokenSet(
                access_token="access-1", refresh_token="   ", expires_in=1200
            )

        def identity_for(self, token, **kwargs):
            return jwt_mod.EveIdentity(
                character_id=95,
                name="Test Pilot",
                owner_hash="",
                scopes=frozenset(application.SCOPES),
            )

    sso = WhitespaceSso()
    controller, _, _ = build(
        tmp_path,
        characters=[with_snapshot()],
        client=FakeEsi(),
        sso=sso,
        spawn=DirectSpawn(),
    )
    controller.refresh_characters()

    assert len(sso.refreshes) == 1
    assert controller._authority._state.characters[0].refresh_token_blob == "blob"


def test_a_failed_save_during_token_rotation_is_surfaced_not_swallowed(tmp_path):
    """Round 2 review, Critical item 1. The only existing save-failure test
    covers select_plan. A rotated refresh token that fails to persist must
    not vanish silently -- the refresh itself still succeeds (the new token
    is correct in memory), but until the write reaches disk the NEXT launch
    would authenticate with a stale one, and nothing on the row said so.

    Calls _access_token directly rather than through refresh_characters():
    _commit_success's own save runs moments later in the same pass and
    would overwrite ch.error on any success, masking exactly the failure
    this test exists to catch.
    """
    character = with_snapshot()
    controller, _, _ = build(
        tmp_path,
        characters=[character],
        client=FakeEsi(),
        sso=FakeSso(),
        spawn=DirectSpawn(),
    )

    def fail_save(_path, _authority):
        raise OSError("disk full")

    controller._authority._save_authority = fail_save

    token, warning, invalidated = controller._access_token(character.character_id)

    assert token == "access-1", "the refresh itself still succeeded"
    assert invalidated is False
    assert "could not be saved" in warning
    assert (
        controller._authority._state.characters[0].refresh_token_blob == "refresh-1"
    ), "rotated correctly in memory"
    assert "could not be saved" in controller.state_payload()["characters"][0]["error"]


def test_a_refreshed_token_for_a_different_character_forces_reauth(tmp_path):
    """Round 2 review, Important item 3. Ground truth:
    TriffSkillsAuthentication.cs:152-155. A token that validates fine but
    names a different character_id than the one being refreshed must never
    be trusted -- CCP's own session confusion, or a stale cache entry, must
    not let one character's row start showing another's data."""

    def wrong_identity(token, **kwargs):
        return jwt_mod.EveIdentity(
            character_id=999,
            name="Someone Else",
            owner_hash="",
            scopes=frozenset(application.SCOPES),
        )

    esi = FakeEsi()
    controller, _, _ = build(
        tmp_path,
        characters=[with_snapshot()],
        client=esi,
        sso=FakeSso(),
        validate_token=wrong_identity,
        spawn=DirectSpawn(),
    )
    controller.refresh_characters()

    authority = controller._authority.character(95)
    assert authority.needs_reauth is True
    assert controller._authority._state.characters[0].refresh_token_blob == ""
    assert esi.calls == [], "no ESI call is worth making on an untrusted token"


def test_a_changed_owner_hash_forces_reauth(tmp_path):
    """Round 2 review, Important item 3. Ground truth:
    TriffSkillsAuthentication.cs:156-161. Both the stored hash and the
    refreshed token's hash are non-blank here, so a mismatch is real
    evidence the character changed hands -- the stored grant is deleted,
    matching every other definitive failure."""

    def transferred_identity(token, **kwargs):
        return jwt_mod.EveIdentity(
            character_id=95,
            name="Aiga Otsolen",
            owner_hash="new-owner",
            scopes=frozenset(application.SCOPES),
        )

    esi = FakeEsi()
    controller, _, _ = build(
        tmp_path,
        characters=[with_snapshot()],
        authority_characters=[
            AuthorityCharacter(
                character_id=95,
                character_name="Aiga Otsolen",
                owner_hash="old-owner",
                scopes=tuple(sorted(eveauth_application.SKILLS_SCOPES)),
                authenticated_utc=T0,
                needs_reauth=False,
                generation=0,
            )
        ],
        client=esi,
        sso=FakeSso(),
        validate_token=transferred_identity,
        spawn=DirectSpawn(),
    )
    controller.refresh_characters()

    ch = controller._state.characters[0]
    authority = controller._authority.character(95)
    assert authority.needs_reauth is True
    assert controller._authority._state.characters[0].refresh_token_blob == ""
    assert ch.error == "Character ownership changed. Re-authenticate this character."
    assert esi.calls == []


def test_a_blank_owner_hash_on_either_side_skips_the_comparison(tmp_path):
    """Round 2 review, Important item 3. Ground truth:
    TriffSkillsAuthentication.cs:156-158's guard -- the comparison only
    runs when BOTH sides are non-blank. An older stored row with no hash
    yet, or a token that omits the claim, is missing information, not
    evidence of a transfer, and must not force a reauth on its own."""

    def blank_hash_identity(token, **kwargs):
        return jwt_mod.EveIdentity(
            character_id=95,
            name="Aiga Otsolen",
            owner_hash="",
            scopes=frozenset(application.SCOPES),
        )

    controller, _, _ = build(
        tmp_path,
        characters=[with_snapshot()],
        authority_characters=[
            AuthorityCharacter(
                character_id=95,
                character_name="Aiga Otsolen",
                owner_hash="old-owner",
                scopes=tuple(sorted(eveauth_application.SKILLS_SCOPES)),
                authenticated_utc=T0,
                needs_reauth=False,
                generation=0,
            )
        ],
        client=FakeEsi(),
        sso=FakeSso(),
        validate_token=blank_hash_identity,
        spawn=DirectSpawn(),
    )
    controller.refresh_characters()

    assert controller._authority.character(95).needs_reauth is False
    assert controller._state.characters[0].error == ""


def test_esi_calls_happen_with_the_state_lock_released(tmp_path):
    """Round 2 review, Test item 5. THE headline contract of the refresh
    worker: eighty sequential HTTP requests must never hold the lock every
    other read of state needs. Pinned as a real concurrency probe rather
    than trusted to single-threaded DirectSpawn tests -- moving
    `self._client.get` inside `with self._lock:` would pass every other
    test in this file, since RLock lets the SAME thread re-enter and
    nothing single-threaded can observe that regression."""
    controller = None
    released = []

    class LockCheckingEsi(FakeEsi):
        def get(self, path, *, token=None, etag=None):
            def probe():
                held = controller._lock.acquire(blocking=False)
                released.append(held)
                if held:
                    controller._lock.release()

            thread = threading.Thread(target=probe)
            thread.start()
            thread.join(timeout=5)
            return super().get(path, token=token, etag=etag)

    esi = LockCheckingEsi()
    controller, _, _ = build(
        tmp_path,
        characters=[with_snapshot()],
        client=esi,
        sso=FakeSso(),
        spawn=DirectSpawn(),
    )

    controller.refresh_characters()

    assert released, "the probe thread never ran"
    assert all(released), (
        "a second thread must be able to take the state lock while an ESI "
        "call is in flight -- the lock must not be held across it"
    )


def test_a_character_forgotten_mid_refresh_stays_forgotten(tmp_path):
    """Auth, refresh, forget and plan selection can all be in flight at
    once. A forget completing during a refresh would be silently undone by
    the refresh's save -- the character reappears, with data, and the only
    way to remove it is to click forget again and hope."""
    esi = FakeEsi()
    controller = None

    def forget_during_the_fetch(path):
        controller._authority.forget(95)

    esi.on_get = forget_during_the_fetch
    controller, _, _ = build(
        tmp_path,
        characters=[with_snapshot()],
        client=esi,
        sso=FakeSso(),
        spawn=DirectSpawn(),
    )

    controller.refresh_characters()

    assert controller.state_payload()["characters"] == []


def test_progress_is_pushed_once_per_character(tmp_path):
    """A forty-character pass is eighty sequential requests. Without a
    per-character push the window looks hung for the duration."""
    characters = [with_snapshot(character_id=1), with_snapshot(character_id=2)]
    authority_characters = [
        AuthorityCharacter(
            character_id=1,
            character_name="A",
            owner_hash="",
            scopes=tuple(sorted(eveauth_application.SKILLS_SCOPES)),
            authenticated_utc=T0,
            needs_reauth=False,
            generation=0,
        ),
        AuthorityCharacter(
            character_id=2,
            character_name="B",
            owner_hash="",
            scopes=tuple(sorted(eveauth_application.SKILLS_SCOPES)),
            authenticated_utc=T0,
            needs_reauth=False,
            generation=0,
        ),
    ]
    controller, pushed, _ = build(
        tmp_path,
        characters=characters,
        authority_characters=authority_characters,
        client=FakeEsi(),
        spawn=DirectSpawn(),
    )

    controller.refresh_characters()

    progress = [p for handler, p in pushed if handler == "onSkillsProgress"]
    assert [(p["completed"], p["total"]) for p in progress] == [(1, 2), (2, 2)]
    assert [p["character_name"] for p in progress] == ["A", "B"]
    assert all(p["error"] == "" for p in progress)


def test_a_refresh_resolves_plan_names_that_are_not_in_the_cache(tmp_path):
    """One unresolved name poisons a whole plan's readiness to Unknown for
    every character, so resolution has to happen somewhere -- and refresh is
    the only place with both a worker thread and an ESI client."""
    resolved = []

    def fake_resolve(cache, names, client, **kwargs):
        resolved.append(sorted(names))
        cache.merge({name: 3327 for name in names})
        return {}

    controller, _, _ = build(
        tmp_path,
        characters=[with_snapshot()],
        # A name resolved in this pass has no training metadata yet, so the
        # backfill that runs behind resolution asks for its type detail.
        client=FakeEsi(
            types={3327: esi_response(200, _type_body(1, "perception", "willpower"))}
        ),
        sso=FakeSso(),
        spawn=DirectSpawn(),
        plans={"Interceptor": "Navigation V\n"},
    )
    controller._resolve = fake_resolve

    controller.refresh_characters()

    assert resolved == [["Navigation"]]
    assert controller._cache.get("navigation") == 3327


# ----- shared-authority forget integration -----------------------------


def test_authority_forget_removes_the_character_and_its_token_in_one_write(tmp_path):
    """The roster row and its wrapped refresh token live in the same
    document, so removing the row removes the token with it -- there is no
    separate credential store to leave an orphaned secret behind in."""
    controller, _, _ = build(tmp_path, characters=[with_snapshot()])

    assert controller._authority.forget(95) == MutationResult(True, True, "")

    assert controller.state_payload()["characters"] == []
    reloaded, _ = state_mod.load(tmp_path / "eve_skills.json")
    assert reloaded.characters == []


def test_authority_forgetting_a_character_that_is_not_there_is_idempotent(tmp_path):
    """The shared Forget action can race a stale roster. Forgetting an
    already-removed character still reports success."""
    controller, _, _ = build(tmp_path)

    assert controller._authority.forget(95) == MutationResult(True, True, "")


def test_authority_forget_pushes_skills_state(tmp_path):
    """Authority owns the command, but Skills still has to repaint when its
    participant row disappears."""
    controller, pushed, _ = build(tmp_path, characters=[with_snapshot()])

    controller._authority.forget(95)

    assert any(handler == "onSkills" for handler, _ in pushed)


def test_prepare_forget_is_check_only_until_authority_removal(tmp_path):
    """There is no participant abort hook, so prepare must not mutate or save."""
    controller, _, _ = build(tmp_path, characters=[with_snapshot()])
    controller._save_locked = lambda: (_ for _ in ()).throw(
        AssertionError("prepare must not save")
    )

    result = controller.prepare_forget(95)

    assert result == MutationResult(True, True, "")
    assert controller._state.find(95) is not None


def test_failed_authority_removal_save_reports_the_exact_blocked_character(
    tmp_path, monkeypatch
):
    character = state_mod.Character(character_id=42)
    controller, _pushed, _alerts = build(tmp_path, characters=(character,))
    monkeypatch.setattr(
        state_mod,
        "save",
        lambda *_args: (_ for _ in ()).throw(OSError("disk")),
    )

    result = controller.authority_removed(42)

    assert result == MutationResult(True, False, "Could not save Skills cleanup.")
    assert controller._state.find(42) is not None
    verification = controller.reconcile_characters(tuple())
    assert verification.verified is True
    assert verification.blocked_character_ids == frozenset({42})


def test_successful_retry_clears_the_skills_cleanup_block(tmp_path, monkeypatch):
    character = state_mod.Character(character_id=42)
    controller, _pushed, _alerts = build(tmp_path, characters=(character,))
    original_save = state_mod.save
    calls = 0

    def fail_once(state, path):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("disk")
        original_save(state, path)

    monkeypatch.setattr(state_mod, "save", fail_once)

    assert controller.authority_removed(42).persisted is False
    assert controller._state.find(42) is not None
    assert controller.reconcile_characters(tuple()).blocked_character_ids == frozenset()
    assert controller._state.find(42) is None


# ----- interactive sign-in ------------------------------------------------

IDENTITY = jwt_mod.EveIdentity(
    character_id=95,
    name="Aiga Otsolen",
    owner_hash="hash-1",
    scopes=frozenset(application.SCOPES),
)


class FakeListener:
    """loopback.LoopbackListener without a socket.

    `bound` records the order events happen in relative to the browser
    launch, which is the only thing the race-avoidance test cares about.
    `on_wait`, when given, runs from inside `wait()` -- the same spot a
    real cancel_authorization() call would land in, from another thread,
    while the real listener blocks on accept().
    """

    def __init__(self, events, callback=None, error_to_raise=None, on_wait=None):
        self.events = events
        self.callback = callback
        self.error_to_raise = error_to_raise
        self.on_wait = on_wait
        self.cancelled = False

    def __call__(self, *, host, port, path):
        return self

    def __enter__(self):
        self.events.append("bound")
        return self

    def __exit__(self, *exc_info):
        return False

    def wait(self, expected_state, *, timeout_s=None):
        if self.on_wait is not None:
            self.on_wait()
        # Checked AFTER on_wait(), since that is where a real
        # cancel_authorization() call lands from another thread while the
        # real listener blocks in
        # accept(). Ignoring this and falling through to error_to_raise or
        # the callback -- the old behaviour -- meant a test built on top of
        # a cancelling on_wait never actually reached the CallbackCancelled
        # branch it was trying to exercise.
        if self.cancelled:
            raise loopback_mod.CallbackCancelled()
        if self.error_to_raise is not None:
            raise self.error_to_raise
        return self.callback

    def cancel(self):
        self.cancelled = True
        self.events.append("cancelled")


class FakeAuthSso:
    """sso.generate_pkce/authorize_url/exchange_code without a network."""

    def __init__(self, token_set=None, raises=None):
        self.token_set = token_set or sso_mod.TokenSet(
            access_token="access-1", refresh_token="refresh-1", expires_in=1200
        )
        self.raises = raises
        self.exchanged = []

    def generate_pkce(self):
        return sso_mod.Pkce(
            state="state-1", verifier="verifier-1", challenge="challenge-1"
        )

    def authorize_url(self, pkce, scopes):
        return f"https://login.eveonline.com/v2/oauth/authorize?state={pkce.state}"

    def exchange_code(self, code, verifier):
        self.exchanged.append((code, verifier))
        if self.raises is not None:
            raise self.raises
        return self.token_set


def build_auth(
    tmp_path,
    monkeypatch,
    *,
    events=None,
    callback=None,
    listener_error=None,
    on_wait=None,
    sso=None,
    validate_token=None,
    **kwargs,
):
    # Pinned rather than inherited from application.py: these tests
    # exercise authenticate()'s own behaviour, and must not start
    # failing the day the registered client id is rotated or a fork
    # blanks it back to the placeholder. Patched on the owning module
    # (`wingman.eveauth.application`) -- `controller.py` now imports
    # `application` from there directly, not through the
    # `wingman.eveskills.application` compatibility re-export, so that
    # module's `CLIENT_ID` is not what `authenticate()`'s
    # `is_configured()` check reads any more.
    monkeypatch.setattr(eveauth_application, "CLIENT_ID", "test-client-id")
    events = events if events is not None else []
    listener = FakeListener(
        events,
        callback=callback or loopback_mod.Callback(code="code-1", error=""),
        error_to_raise=listener_error,
        on_wait=on_wait,
    )
    launched = []
    controller, pushed, alerts = build(
        tmp_path,
        sso=sso or FakeAuthSso(),
        listener_factory=listener,
        launch_browser=launched.append,
        validate_token=validate_token or (lambda *a, **k: IDENTITY),
        spawn=kwargs.pop("spawn", DirectSpawn()),
        **kwargs,
    )

    class CleanFittingsParticipant:
        def prepare_forget(self, character_id):
            del character_id
            return MutationResult(True, True, "")

        def authority_removed(self, character_id):
            del character_id
            return MutationResult(True, True, "")

        def grant_invalidated(self, character_id):
            del character_id

        def reconcile_characters(self, characters):
            del characters
            from wingman.eveauth import CleanupVerification

            return CleanupVerification(True, frozenset())

    controller._authority.register_participant(
        eveauth_application.FITTINGS,
        CleanFittingsParticipant(),
    )
    return controller, pushed, alerts, events, launched


def test_a_successful_sign_in_adds_the_character(tmp_path, monkeypatch):
    controller, _pushed, alerts, _, _ = build_auth(tmp_path, monkeypatch)

    controller._authority.start_full_authorization()

    characters = controller.state_payload()["characters"]
    assert [c["character_id"] for c in characters] == [95]
    assert alerts == []


def test_the_listener_is_bound_before_the_browser_launches(tmp_path, monkeypatch):
    """Binding first avoids a race: a browser that reaches the redirect
    before anything is listening shows a connection-refused page instead
    of completing the sign-in."""
    events = []
    controller, _, _, events, launched = build_auth(
        tmp_path, monkeypatch, events=events
    )

    controller._authority.start_full_authorization()

    assert events[0] == "bound"
    assert launched, "the browser was never launched"


def test_a_successful_sign_in_kicks_off_a_refresh(tmp_path, monkeypatch):
    """A newly authorised character is Unscored until its first refresh
    lands, so a sign-in that stopped short of one would look like it did
    nothing."""
    esi = FakeEsi()
    controller, _pushed, _, _, _ = build_auth(tmp_path, monkeypatch, client=esi)

    controller._authority.start_full_authorization()

    assert controller.state_payload()["characters"][0]["fetched_utc"] != ""


def test_only_one_interactive_sign_in_at_a_time(tmp_path, monkeypatch):
    """Two authorisations would fight over the same fixed loopback port,
    and there is no second port registered with CCP to fall back to."""
    controller, _pushed, alerts, _, _ = build_auth(
        tmp_path, monkeypatch, spawn=DeferredSpawn()
    )

    controller._authority.start_full_authorization()
    controller._authority.start_full_authorization()

    assert any("already in progress" in title for _, title, _ in alerts)


def test_cancel_authorization_cancels_the_listener(tmp_path, monkeypatch):
    """cancel_authorization() reaches the listener while it is still
    blocked in wait() -- the same spot a real accept() loop parks in for
    up to five minutes."""
    events = []
    controller = None

    def cancel_from_inside_wait():
        controller._authority.cancel_authorization()

    controller, _, _, events, _ = build_auth(
        tmp_path, monkeypatch, events=events, on_wait=cancel_from_inside_wait
    )

    controller._authority.start_full_authorization()

    assert "cancelled" in events


def test_a_callback_carrying_an_error_adds_nothing(tmp_path, monkeypatch):
    controller, _pushed, alerts, _, _ = build_auth(
        tmp_path,
        monkeypatch,
        callback=loopback_mod.Callback(code="", error="access_denied"),
    )

    controller._authority.start_full_authorization()

    assert controller.state_payload()["characters"] == []
    assert any("refused" in title for _, title, _ in alerts)


def test_re_authenticating_the_same_character_keeps_its_data(tmp_path, monkeypatch):
    """The same owner signing back in must not look like a transfer -- the
    cached snapshot is still theirs."""
    controller, _, _alerts, _, _ = build_auth(
        tmp_path,
        monkeypatch,
        characters=[
            with_snapshot(
                owner_hash="hash-1",
                skill_points={3327: 1000},
                skill_points_complete=True,
                attributes={
                    "charisma": 19,
                    "intelligence": 20,
                    "memory": 20,
                    "perception": 27,
                    "willpower": 21,
                },
                attributes_fetched_utc=T0,
                attributes_error="",
                attributes_etag='"old-attrs"',
            )
        ],
        validate_token=lambda *a, **k: IDENTITY,
    )

    controller._authority.start_full_authorization()

    reloaded, _ = state_mod.load(tmp_path / "eve_skills.json")
    found = reloaded.find(95)
    assert found.active_levels == {3327: 3}
    assert found.error == ""
    assert found.skill_points == {3327: 1000}
    assert found.skill_points_complete is True
    assert found.attributes == {
        "charisma": 19,
        "intelligence": 20,
        "memory": 20,
        "perception": 27,
        "willpower": 21,
    }
    assert found.attributes_fetched_utc == T0
    assert found.attributes_etag == '"old-attrs"'


def test_re_authentication_still_kicks_off_a_skills_refresh(tmp_path, monkeypatch):
    """The shared authority move must not leave a repaired row stale."""
    esi = FakeEsi()
    controller, _, _alerts, _, _ = build_auth(
        tmp_path,
        monkeypatch,
        characters=[with_snapshot()],
        client=esi,
        validate_token=lambda *a, **k: IDENTITY,
    )

    controller._authority.start_full_authorization()

    assert [call[0] for call in esi.calls] == [
        "/v4/characters/95/skills/",
        "/v2/characters/95/skillqueue/",
        "/v1/characters/95/attributes/",
    ]


def test_an_ownership_change_refuses_the_full_auth_adapter_unchanged(
    tmp_path, monkeypatch
):
    """Task 5's generic full-authorization flow no longer treats the old
    row-specific sign-in as permission to replace a transferred identity.
    Two present, unequal owner hashes now refuse unchanged and tell the
    user to forget first, leaving the cached snapshot intact."""
    controller, _, alerts, _, _ = build_auth(
        tmp_path,
        monkeypatch,
        characters=[with_snapshot(attributes_etag='"old-attrs"')],
        authority_characters=[
            AuthorityCharacter(
                character_id=95,
                character_name="Aiga Otsolen",
                owner_hash="old-hash",
                scopes=tuple(sorted(eveauth_application.SKILLS_SCOPES)),
                authenticated_utc=T0,
                needs_reauth=False,
                generation=0,
            )
        ],
        validate_token=lambda *a, **k: IDENTITY,
    )

    controller._authority.start_full_authorization()

    reloaded, _ = state_mod.load(tmp_path / "eve_skills.json")
    found = reloaded.find(95)
    assert found.active_levels == {3327: 3}
    assert found.trained_levels == {3327: 3}
    assert found.queue == ()
    assert found.fetched_utc == T0
    assert found.skills_etag == '"old-s"'
    assert found.queue_etag == '"old-q"'
    assert found.skill_points == {3327: 1000}
    assert found.skill_points_complete is True
    assert found.attributes == ATTRIBUTES_BODY
    assert found.attributes_fetched_utc == T0
    assert found.attributes_error == ""
    assert found.attributes_etag == '"old-attrs"'
    assert found.error == ""
    assert controller._authority.character(95).owner_hash == "old-hash"
    assert any("forget" in body.lower() for _, _, body in alerts)


def test_signing_in_a_new_character_past_the_cap_is_refused(tmp_path, monkeypatch):
    """state.SkillsState.upsert() raises at MAX_CHARACTERS for a genuinely
    new id; the roster is left untouched rather than partially written."""
    full_roster = [
        with_snapshot(character_id=n) for n in range(1, state_mod.MAX_CHARACTERS + 1)
    ]
    controller, _, alerts, _, _ = build_auth(
        tmp_path,
        monkeypatch,
        characters=full_roster,
        validate_token=lambda *a, **k: IDENTITY,
    )

    controller._authority.start_full_authorization()

    assert any("Too many characters" in title for _, title, _ in alerts)
    reloaded, _ = state_mod.load(tmp_path / "eve_skills.json")
    assert reloaded.find(IDENTITY.character_id) is None
    assert len(reloaded.characters) == state_mod.MAX_CHARACTERS


def test_a_blank_incoming_owner_hash_is_not_a_transfer(tmp_path, monkeypatch):
    """A refreshed token that omits the owner claim (jwt.py:234-239 -- a
    normal, unremarkable thing) must not read as a different owner just
    because a hash was stored last time, and must not blank that stored
    hash out from under future checks."""
    blank_identity = jwt_mod.EveIdentity(
        character_id=95,
        name="Aiga Otsolen",
        owner_hash="",
        scopes=frozenset(application.SCOPES),
    )
    controller, _, alerts, _, _ = build_auth(
        tmp_path,
        monkeypatch,
        characters=[with_snapshot()],
        authority_characters=[
            AuthorityCharacter(
                character_id=95,
                character_name="Aiga Otsolen",
                owner_hash="hash-1",
                scopes=tuple(sorted(eveauth_application.SKILLS_SCOPES)),
                authenticated_utc=T0,
                needs_reauth=False,
                generation=0,
            )
        ],
        validate_token=lambda *a, **k: blank_identity,
    )

    controller._authority.start_full_authorization()

    reloaded, _ = state_mod.load(tmp_path / "eve_skills.json")
    found = reloaded.find(95)
    assert found.active_levels == {3327: 3}
    assert found.error == ""
    assert controller._authority.character(95).owner_hash == "hash-1"
    assert not any("ownership" in body.lower() for _, _, body in alerts)


def test_a_sign_in_save_failure_rolls_back_a_new_character(tmp_path, monkeypatch):
    controller, _, alerts, _, _ = build_auth(tmp_path, monkeypatch)

    def fail_authority_save(_path, _authority):
        raise OSError("disk full")

    controller._authority._save_authority = fail_authority_save

    controller._authority.start_full_authorization()

    assert controller.state_payload()["characters"] == []
    assert alerts and alerts[-1][0] == "warning"


def test_a_sign_in_save_failure_rolls_back_an_existing_character(tmp_path, monkeypatch):
    """ch is the SAME object as the live roster row when the character
    already exists, so its fields land on the live state immediately, save
    or no save. A failed save must restore the pre-mutation snapshot, not
    just skip an append."""
    controller, _, alerts, _, _ = build_auth(
        tmp_path,
        monkeypatch,
        characters=[with_snapshot(owner_hash="hash-1")],
        validate_token=lambda *a, **k: IDENTITY,
    )

    def fail_authority_save(_path, _authority):
        raise OSError("disk full")

    controller._authority._save_authority = fail_authority_save

    controller._authority.start_full_authorization()

    reloaded, _ = state_mod.load(tmp_path / "eve_skills.json")
    found = reloaded.find(95)
    assert found.active_levels == {3327: 3}
    assert alerts and alerts[-1][0] == "warning"


def test_forgetting_a_character_mid_auth_is_not_undone(tmp_path, monkeypatch):
    """The character is on the roster when the browser opens and gone by
    the time the callback resolves -- forgotten while the consent screen
    was up. Committing here would silently resurrect it."""
    controller = None

    def forget_during_wait():
        controller._authority.forget(95)

    controller, _, alerts, _, _ = build_auth(
        tmp_path,
        monkeypatch,
        characters=[with_snapshot(owner_hash="hash-1")],
        validate_token=lambda *a, **k: IDENTITY,
        on_wait=forget_during_wait,
    )

    controller._authority.start_full_authorization()

    assert controller.state_payload()["characters"] == []
    assert any("forgotten" in body.lower() for _, _, body in alerts)


def test_a_cancelled_sign_in_produces_no_alert(tmp_path, monkeypatch):
    """The cancel button's entire user-facing contract: cancelling must
    never look like a failure."""
    controller = None

    def cancel_from_inside_wait():
        controller._authority.cancel_authorization()

    controller, _, alerts, _, _ = build_auth(
        tmp_path, monkeypatch, on_wait=cancel_from_inside_wait
    )

    controller._authority.start_full_authorization()

    assert alerts == []
    assert controller.state_payload()["characters"] == []


def test_a_timed_out_sign_in_alerts(tmp_path, monkeypatch):
    controller, _, alerts, _, _ = build_auth(
        tmp_path, monkeypatch, listener_error=loopback_mod.CallbackTimeout()
    )

    controller._authority.start_full_authorization()

    assert any("timed out" in title.lower() for _, title, _ in alerts)


def test_an_oauth_error_during_exchange_alerts(tmp_path, monkeypatch):
    controller, _, alerts, _, _ = build_auth(
        tmp_path,
        monkeypatch,
        sso=FakeAuthSso(raises=sso_mod.OAuthError(400, "invalid_grant", "bad code")),
    )

    controller._authority.start_full_authorization()

    assert any("refused" in title.lower() for _, title, _ in alerts)
    assert controller.state_payload()["characters"] == []


def test_a_jwt_error_during_validation_alerts(tmp_path, monkeypatch):
    def raising_validate(*a, **k):
        raise jwt_mod.JwtError("signature verification failed")

    controller, _, alerts, _, _ = build_auth(
        tmp_path, monkeypatch, validate_token=raising_validate
    )

    controller._authority.start_full_authorization()

    assert any("cannot trust" in title.lower() for _, title, _ in alerts)
    assert controller.state_payload()["characters"] == []


def test_an_unexpected_exception_during_sign_in_alerts(tmp_path, monkeypatch):
    def raising_validate(*a, **k):
        raise RuntimeError("boom")

    controller, _, alerts, _, _ = build_auth(
        tmp_path, monkeypatch, validate_token=raising_validate
    )

    controller._authority.start_full_authorization()

    assert any("Sign-in failed" in title for _, title, _ in alerts)
    assert controller.state_payload()["characters"] == []


def test_a_spawn_failure_releases_the_latch(tmp_path, monkeypatch):
    """Nothing runs _auth_worker's own finally if starting the thread
    itself raises -- authenticate() has to release the latch and clear the
    in-progress flag itself in that window, or sign-in is dead until
    restart."""

    class RaisingSpawn:
        def __call__(self, target, daemon=True):
            raise OSError("could not start thread")

    controller, _, alerts, _, _ = build_auth(
        tmp_path, monkeypatch, spawn=RaisingSpawn()
    )

    controller._authority.start_full_authorization()

    assert any("Sign-in failed" in title for _, title, _ in alerts)
    assert controller._authority.auth_in_progress is False
    assert controller._authority._auth_latch.acquire(blocking=False)


# ----- character_detail ---------------------------------------------------


def test_character_detail_includes_active_requirements(tmp_path):
    """Active requirements are included in the payload; the page filters
    the expanded row, not the controller."""
    controller, _, _ = build(
        tmp_path,
        characters=[with_snapshot()],
        plans={"Interceptor": "Navigation III\n"},
    )
    controller._cache.merge({"navigation": 3327})

    detail = controller.character_detail(95, "Interceptor")

    assert detail["ok"] is True
    assert detail["requirements"][0]["skill_name"] == "Navigation"
    assert detail["requirements"][0]["active_level"] == 3


def test_character_detail_matches_the_plan_name_case_insensitively(tmp_path):
    controller, _, _ = build(
        tmp_path,
        characters=[with_snapshot()],
        plans={"Interceptor": "Navigation III\n"},
    )
    controller._cache.merge({"navigation": 3327})

    detail = controller.character_detail(95, "iNtErCePtOr")

    assert detail["ok"] is True
    assert detail["plan_name"] == "Interceptor"


def test_character_detail_for_a_forgotten_character_says_so(tmp_path):
    controller, _, _ = build(tmp_path, plans={"Interceptor": "Navigation III\n"})

    detail = controller.character_detail(95, "Interceptor")

    assert detail["ok"] is False
    assert detail["message"] == "That character is no longer in the roster."


def test_character_detail_for_a_missing_plan_says_so(tmp_path):
    """planstore.list_plans excludes any file that fails to parse from
    self._plans entirely (it becomes a PlanIssue instead), so a PlanFile
    reachable from _find_plan_locked is `ok` by construction -- there is no
    reachable "the plan has errors" branch here, only "not found"."""
    controller, _, _ = build(
        tmp_path, characters=[with_snapshot()], plans={"Broken": "Navigation +5\n"}
    )

    detail = controller.character_detail(95, "Broken")

    assert detail["ok"] is False
    assert detail["message"] == "That plan is no longer available. Reload plans."


def test_character_detail_reports_levels_as_integers(tmp_path):
    """Plain ints across the bridge: the page compares these arithmetically,
    and `null > 3` is quietly false in JavaScript rather than an error."""
    controller, _, _ = build(
        tmp_path,
        characters=[with_snapshot()],
        plans={"Interceptor": "Navigation III\nSpaceship Command III\n"},
    )
    controller._cache.merge({"navigation": 3327})

    detail = controller.character_detail(95, "Interceptor")

    for req in detail["requirements"]:
        assert isinstance(req["active_level"], int)
        assert isinstance(req["trained_level"], int)


# ----- shutdown -----------------------------------------------------------


def test_shutdown_is_safe_with_no_sign_in_running(tmp_path):
    controller, _, _ = build(tmp_path)

    controller.shutdown()  # Must not raise.


def test_shutdown_swallows_a_failing_listener(tmp_path):
    """Whatever cancel() does, shutdown must not be the thing that raises
    -- it runs on every exit path, after the window is already gone."""
    controller, _, _ = build(tmp_path)

    class FailingListener:
        def cancel(self):
            raise RuntimeError("boom")

    controller._listener = FailingListener()

    controller.shutdown()  # Must not raise.


def test_shutdown_refuses_new_refresh_work(tmp_path):
    spawn = DeferredSpawn()
    controller, _, _ = build(tmp_path, spawn=spawn)

    controller.shutdown()
    controller.refresh_characters()

    assert spawn.targets == []
    assert controller._refresh_in_flight is False


def test_shutdown_waits_for_the_active_refresh_worker(tmp_path):
    started = threading.Event()
    release = threading.Event()

    class BlockingEsi(FakeEsi):
        def get(self, path, *, token=None, etag=None):
            if not started.is_set():
                started.set()
                assert release.wait(timeout=2)
            return super().get(path, token=token, etag=etag)

    controller, _, _ = build(
        tmp_path,
        characters=[with_snapshot()],
        client=BlockingEsi(),
        sso=FakeSso(),
        spawn=threading.Thread,
    )
    shutdown_finished = threading.Event()
    controller.refresh_characters()
    assert started.wait(timeout=2)

    worker = threading.Thread(
        target=lambda: (controller.shutdown(), shutdown_finished.set())
    )
    worker.start()
    assert not shutdown_finished.wait(timeout=0.1)

    release.set()
    worker.join(timeout=2)

    assert shutdown_finished.is_set()
    assert controller._refresh_in_flight is False


def test_shutdown_stops_a_refresh_pass_between_characters(tmp_path):
    """The stop flag is checked between characters, not just at the start
    -- a shutdown mid-pass must not block the process on a refresh that
    keeps going after the window closed."""
    esi = FakeEsi()
    controller, _, _ = build(
        tmp_path,
        characters=[
            with_snapshot(character_id=95),
            with_snapshot(character_id=96),
        ],
        client=esi,
        sso=FakeSso(),
        spawn=DirectSpawn(),
    )

    seen = []

    def stop_after_first(path):
        seen.append(path)
        if len(seen) == 1:
            controller.shutdown()

    esi.on_get = stop_after_first

    controller.refresh_characters()

    # Exactly the first character's two calls (skills + queue) happened;
    # the second character was never fetched.
    assert len(seen) <= 2


def test_plan_text_renders_the_selected_plans_requirements(tmp_path):
    """S7: the whole plan on the clipboard, because EVE drops the skills a
    character has already trained on import -- so no per-character diffing
    is needed and none is done here. Case-insensitive on the name, like
    every other plan lookup."""
    controller, _, _ = build(
        tmp_path, plans={"Ishtar": "Navigation 4\nGallente Cruiser V\n"}
    )

    assert controller.plan_text("ishtar") == "Navigation IV\nGallente Cruiser V\n"


def test_plan_text_is_empty_for_a_plan_that_is_no_longer_there(tmp_path):
    """The page can hold a plan list a reload invalidated -- select_plan
    documents the same race. "" is never "an empty plan": parse() rejects a
    file with no requirements, so a listed plan always has at least one."""
    controller, _, _ = build(tmp_path, plans={"Ishtar": "Navigation 4\n"})

    assert controller.plan_text("Loki") == ""
    assert controller.plan_text("") == ""
    assert controller.plan_text(None) == ""


NAVIGATION_ID = 3449
PLAN_ONE_SKILL = "Navigation I\n"


def _seed_cache(tmp_path, mapping):
    """Write the skill-id cache the controller reads at construction.

    Without this every requirement is unresolvable, so nobody scores Ready
    and ready_count is 0 whoever is in which group -- the scoping assertion
    would pass for the wrong reason today and start failing the moment the
    scoping actually worked. Keys are folded, matching SkillIdCache's own
    storage; version and category are read from the module, not retyped.
    """
    document = {
        "version": skillids_mod.CACHE_VERSION,
        "entries": [
            {
                "name": name,
                "type_id": type_id,
                "category_id": skillids_mod.SKILL_CATEGORY_ID,
            }
            for name, type_id in mapping.items()
        ],
    }
    (tmp_path / "eve_skills_cache.json").write_text(
        json.dumps(document), encoding="utf-8"
    )


def _ch(character_id, name, group="", ready=False):
    """A character with a snapshot, so it scores rather than reading Unscored."""
    levels = {NAVIGATION_ID: 5} if ready else {}
    del name  # Display identity comes from shared authority in build().
    return state_mod.Character(
        character_id=character_id,
        group=group,
        fetched_utc=T0,
        active_levels=dict(levels),
        trained_levels=dict(levels),
    )


def test_the_group_list_is_derived_from_the_roster_and_sorted(tmp_path):
    controller, _, _ = build(
        tmp_path,
        characters=[
            _ch(1, "Aiga", "Wolfpack"),
            _ch(2, "Zuelo", "Wolfpack"),
            _ch(3, "Kaska", "Logi Wing"),
            _ch(4, "Delen", ""),
        ],
    )

    payload = controller.state_payload()

    assert payload["groups"] == [
        {"name": "Logi Wing", "member_count": 1},
        {"name": "Wolfpack", "member_count": 2},
    ]


def test_two_spellings_of_one_group_are_one_row_keeping_the_first(tmp_path):
    """The rail showing `Wolfpack` and `wolfpack` as two crews looks like a
    bug, and _find_plan_locked already casefolds for the same reason."""
    controller, _, _ = build(
        tmp_path,
        characters=[_ch(1, "Aiga", "Wolfpack"), _ch(2, "Zuelo", "wolfpack")],
    )

    payload = controller.state_payload()

    assert payload["groups"] == [{"name": "Wolfpack", "member_count": 2}]


def test_a_selected_group_nobody_holds_is_reported_as_no_selection(tmp_path):
    """Same shape as a deleted plan file: reported as unselected so the
    screen falls back to All, with the stored value left alone in case the
    group comes back."""
    seed = state_mod.SkillsState(
        characters=[_ch(1, "Aiga", "Wolfpack")], selected_group="Mining"
    )
    state_mod.save(seed, tmp_path / "eve_skills.json")
    controller, _, _ = build(tmp_path)

    assert controller.state_payload()["selected_group"] == ""


def test_the_ready_count_counts_only_the_selected_groups_members(tmp_path):
    """The whole point of the feature: the rail answers `what can this crew
    fly`, not `what can anyone fly`."""
    _seed_cache(tmp_path, {"navigation": NAVIGATION_ID})
    seed = state_mod.SkillsState(
        characters=[
            _ch(1, "Aiga", "Wolfpack", ready=True),
            _ch(2, "Zuelo", "Mining", ready=True),
        ],
        selected_group="Wolfpack",
    )
    state_mod.save(seed, tmp_path / "eve_skills.json")
    controller, _, _ = build(tmp_path, plans={"Ishtar": PLAN_ONE_SKILL})

    payload = controller.state_payload()

    assert payload["selected_group"] == "Wolfpack"
    assert payload["plans"][0]["ready_count"] == 1


def test_every_character_row_carries_its_own_group(tmp_path):
    controller, _, _ = build(tmp_path, characters=[_ch(1, "Aiga", "Wolfpack")])

    assert controller.state_payload()["characters"][0]["group"] == "Wolfpack"


def test_assigning_a_character_creates_the_group_implicitly(tmp_path):
    controller, pushed, _ = build(tmp_path, characters=[_ch(1, "Aiga")])

    assert controller.set_character_group(1, "Wolfpack") is True

    payload = controller.state_payload()
    assert payload["groups"] == [{"name": "Wolfpack", "member_count": 1}]
    assert pushed[-1][0] == "onSkills"


def test_joining_keeps_the_spelling_already_on_the_roster(tmp_path):
    """`wolfpack` typed into a roster holding `Wolfpack` joins it. Without
    this the rail grows a near-duplicate row that reads as a bug."""
    controller, _, _ = build(
        tmp_path, characters=[_ch(1, "Aiga", "Wolfpack"), _ch(2, "Zuelo")]
    )

    assert controller.set_character_group(2, "wolfpack") is True

    assert controller.state_payload()["groups"] == [
        {"name": "Wolfpack", "member_count": 2}
    ]


def test_an_empty_group_name_clears_membership(tmp_path):
    controller, _, _ = build(tmp_path, characters=[_ch(1, "Aiga", "Wolfpack")])

    assert controller.set_character_group(1, "") is True

    payload = controller.state_payload()
    assert payload["groups"] == []
    assert payload["characters"][0]["group"] == ""


def test_an_over_long_group_name_is_refused_not_shortened(tmp_path):
    controller, _, alerts = build(tmp_path, characters=[_ch(1, "Aiga")])
    long_name = "W" * (state_mod.MAX_GROUP_NAME_CHARS + 1)

    assert controller.set_character_group(1, long_name) is False

    assert controller.state_payload()["characters"][0]["group"] == ""
    # The page never reads set_character_group's return value and has no
    # cap of its own to enforce client-side, so a refusal that only logged
    # would be indistinguishable from nothing happening at all.
    assert alerts and alerts[-1][0] == "warning"
    assert str(state_mod.MAX_GROUP_NAME_CHARS) in alerts[-1][2]


def test_assigning_an_unknown_character_is_refused(tmp_path):
    controller, _, _ = build(tmp_path, characters=[_ch(1, "Aiga")])

    assert controller.set_character_group(99, "Wolfpack") is False


def test_a_failed_save_rolls_the_assignment_back(tmp_path, monkeypatch):
    controller, _, alerts = build(tmp_path, characters=[_ch(1, "Aiga")])
    monkeypatch.setattr(controller, "_save_locked", lambda: False)

    assert controller.set_character_group(1, "Wolfpack") is False

    assert controller.state_payload()["characters"][0]["group"] == ""
    assert alerts and alerts[-1][0] == "warning"


def test_selecting_a_group_scopes_the_payload(tmp_path):
    controller, _, _ = build(
        tmp_path, characters=[_ch(1, "Aiga", "Wolfpack"), _ch(2, "Zuelo", "Mining")]
    )

    assert controller.select_group("Wolfpack") is True

    assert controller.state_payload()["selected_group"] == "Wolfpack"


def test_selecting_the_empty_string_returns_to_all(tmp_path):
    seed = state_mod.SkillsState(
        characters=[_ch(1, "Aiga", "Wolfpack")], selected_group="Wolfpack"
    )
    state_mod.save(seed, tmp_path / "eve_skills.json")
    controller, _, _ = build(tmp_path)

    assert controller.select_group("") is True

    assert controller.state_payload()["selected_group"] == ""


def test_selecting_a_group_nobody_holds_is_refused(tmp_path):
    """The page can hold a stale rail across a change that emptied the
    group. Reported rather than coerced to All, which would silently
    discard a click."""
    controller, _, _ = build(tmp_path, characters=[_ch(1, "Aiga", "Wolfpack")])

    assert controller.select_group("Mining") is False

    assert controller.state_payload()["selected_group"] == ""


def test_selecting_stores_the_rosters_spelling_not_the_callers(tmp_path):
    controller, _, _ = build(tmp_path, characters=[_ch(1, "Aiga", "Wolfpack")])

    assert controller.select_group("wolfpack") is True

    assert controller.state_payload()["selected_group"] == "Wolfpack"


def test_selecting_an_over_long_name_is_refused_with_an_alert(tmp_path):
    controller, _, alerts = build(tmp_path, characters=[_ch(1, "Aiga", "Wolfpack")])
    long_name = "W" * (state_mod.MAX_GROUP_NAME_CHARS + 1)

    assert controller.select_group(long_name) is False

    assert controller.state_payload()["selected_group"] == ""
    assert alerts and alerts[-1][0] == "warning"
    assert str(state_mod.MAX_GROUP_NAME_CHARS) in alerts[-1][2]


def test_a_failed_save_rolls_the_selection_back(tmp_path, monkeypatch):
    controller, _, alerts = build(tmp_path, characters=[_ch(1, "Aiga", "Wolfpack")])
    monkeypatch.setattr(controller, "_save_locked", lambda: False)

    assert controller.select_group("Wolfpack") is False

    assert controller.state_payload()["selected_group"] == ""
    assert alerts and alerts[-1][0] == "warning"


def _seeded(tmp_path, characters, selected_group=""):
    seed = state_mod.SkillsState(
        characters=list(characters), selected_group=selected_group
    )
    state_mod.save(seed, tmp_path / "eve_skills.json")
    return build(tmp_path)


def test_renaming_moves_every_member(tmp_path):
    controller, _, _ = _seeded(
        tmp_path, [_ch(1, "Aiga", "Wolfpack"), _ch(2, "Zuelo", "Wolfpack")]
    )

    assert controller.rename_group("Wolfpack", "Nightcrew") is True

    assert controller.state_payload()["groups"] == [
        {"name": "Nightcrew", "member_count": 2}
    ]


def test_renaming_the_selected_group_carries_the_selection(tmp_path):
    """Membership and selected_group are two representations of one name.
    Rewriting only the members would leave the selection pointing at a name
    nobody holds, and the screen would drop to All mid-rename."""
    controller, _, _ = _seeded(
        tmp_path, [_ch(1, "Aiga", "Wolfpack")], selected_group="Wolfpack"
    )

    assert controller.rename_group("Wolfpack", "Nightcrew") is True

    assert controller.state_payload()["selected_group"] == "Nightcrew"


def test_renaming_onto_an_existing_group_merges_them(tmp_path):
    controller, _, _ = _seeded(
        tmp_path, [_ch(1, "Aiga", "Wolfpack"), _ch(2, "Zuelo", "Mining")]
    )

    assert controller.rename_group("Wolfpack", "Mining") is True

    assert controller.state_payload()["groups"] == [
        {"name": "Mining", "member_count": 2}
    ]


def test_a_case_only_rename_rewrites_the_spelling_for_everyone(tmp_path):
    """Not a merge: one group, respelled. The page shows no merge confirm
    for this, so the controller must not treat it as joining a second."""
    controller, _, _ = _seeded(
        tmp_path, [_ch(1, "Aiga", "Wolfpack"), _ch(2, "Zuelo", "Wolfpack")]
    )

    assert controller.rename_group("Wolfpack", "WOLFPACK") is True

    assert controller.state_payload()["groups"] == [
        {"name": "WOLFPACK", "member_count": 2}
    ]


def test_a_merge_adopts_the_surviving_groups_spelling(tmp_path):
    """Renaming onto `mining` when the roster holds `Mining` must not leave
    two spellings behind. _groups_locked collapses them into one row and
    keeps whichever it meets first, so without normalising here the rail's
    label would depend on the order characters happen to sit in."""
    controller, _, _ = _seeded(
        tmp_path, [_ch(1, "Aiga", "Wolfpack"), _ch(2, "Zuelo", "Mining")]
    )

    assert controller.rename_group("Wolfpack", "mining") is True

    assert controller.state_payload()["groups"] == [
        {"name": "Mining", "member_count": 2}
    ]


def test_renaming_a_group_nobody_holds_is_refused(tmp_path):
    controller, _, _ = _seeded(tmp_path, [_ch(1, "Aiga", "Wolfpack")])

    assert controller.rename_group("Mining", "Nightcrew") is False


def test_renaming_to_an_empty_name_is_refused(tmp_path):
    """Delete is its own command with its own confirmation. A rename that
    silently became one would bypass it."""
    controller, _, _ = _seeded(tmp_path, [_ch(1, "Aiga", "Wolfpack")])

    assert controller.rename_group("Wolfpack", "   ") is False

    assert controller.state_payload()["groups"] == [
        {"name": "Wolfpack", "member_count": 1}
    ]


def test_renaming_onto_an_over_long_name_is_refused_with_an_alert(tmp_path):
    controller, _, alerts = _seeded(tmp_path, [_ch(1, "Aiga", "Wolfpack")])
    long_name = "W" * (state_mod.MAX_GROUP_NAME_CHARS + 1)

    assert controller.rename_group("Wolfpack", long_name) is False

    assert controller.state_payload()["groups"] == [
        {"name": "Wolfpack", "member_count": 1}
    ]
    assert alerts and alerts[-1][0] == "warning"
    assert str(state_mod.MAX_GROUP_NAME_CHARS) in alerts[-1][2]


def test_deleting_clears_every_member_and_the_selection(tmp_path):
    controller, _, _ = _seeded(
        tmp_path,
        [_ch(1, "Aiga", "Wolfpack"), _ch(2, "Zuelo", "Wolfpack")],
        selected_group="Wolfpack",
    )

    assert controller.delete_group("Wolfpack") is True

    payload = controller.state_payload()
    assert payload["groups"] == []
    assert payload["selected_group"] == ""
    assert [c["group"] for c in payload["characters"]] == ["", ""]


def test_deleting_leaves_other_groups_alone(tmp_path):
    controller, _, _ = _seeded(
        tmp_path, [_ch(1, "Aiga", "Wolfpack"), _ch(2, "Zuelo", "Mining")]
    )

    assert controller.delete_group("Wolfpack") is True

    assert controller.state_payload()["groups"] == [
        {"name": "Mining", "member_count": 1}
    ]


def test_a_failed_rename_restores_members_and_selection_together(tmp_path, monkeypatch):
    """A partial rollback is the same dangling pointer arrived at from the
    other direction, so both fields are asserted."""
    controller, _, alerts = _seeded(
        tmp_path, [_ch(1, "Aiga", "Wolfpack")], selected_group="Wolfpack"
    )
    monkeypatch.setattr(controller, "_save_locked", lambda: False)

    assert controller.rename_group("Wolfpack", "Nightcrew") is False

    payload = controller.state_payload()
    assert payload["groups"] == [{"name": "Wolfpack", "member_count": 1}]
    assert payload["selected_group"] == "Wolfpack"
    assert alerts and alerts[-1][0] == "warning"


def test_a_failed_delete_restores_members_and_selection_together(tmp_path, monkeypatch):
    controller, _, alerts = _seeded(
        tmp_path, [_ch(1, "Aiga", "Wolfpack")], selected_group="Wolfpack"
    )
    monkeypatch.setattr(controller, "_save_locked", lambda: False)

    assert controller.delete_group("Wolfpack") is False

    payload = controller.state_payload()
    assert payload["groups"] == [{"name": "Wolfpack", "member_count": 1}]
    assert payload["selected_group"] == "Wolfpack"
    assert alerts and alerts[-1][0] == "warning"


# ----- training metadata backfill and estimates -------------------------

GUNNERY_ID = 3300
# Gunnery V at rank 1 is 256,000 SP. with_snapshot's attributes give
# perception 27 / willpower 21, which is the Omega rate 27 + 21/2 = 37.5
# SP per minute: 256000 / 37.5 = 6826.67 minutes = 409,600 seconds, which
# rounds to the two-unit label below. Written out rather than recomputed
# from training.py's own formula, which would only assert that the code
# agrees with itself.
GUNNERY_V_SECONDS = 409600
GUNNERY_V_LABEL = "4d 17h"


def _meta(fetched_utc):
    """Gunnery's decoded training metadata, stamped when the caller says."""
    return training_mod.SkillTrainingMetadata(1, "perception", "willpower", fetched_utc)


def _estimate_character(**kwargs):
    """with_snapshot(), but with nothing trained and nothing queued.

    The plan's target is then entirely untrained, so the estimate under
    test is the whole skill rather than an arbitrary remainder.
    """
    defaults = dict(active_levels={}, trained_levels={}, skill_points={}, queue=())
    defaults.update(kwargs)
    return with_snapshot(**defaults)


def _estimating(
    tmp_path,
    character=None,
    *,
    plan="Gunnery V\n",
    selected="Gunnery",
    metadata=T0,
    clock=None,
):
    """A controller holding every estimate input, so a test varies one.

    `metadata=None` leaves the id cache enriched with nothing, which is the
    "never backfilled" case; any other value is the stamp the metadata
    carries, so an expired record is one argument away.
    """
    clock = clock or Clock()
    _seed_cache(tmp_path, {"gunnery": GUNNERY_ID})
    controller, _, _ = build(
        tmp_path,
        characters=[character if character is not None else _estimate_character()],
        plans={"Gunnery": plan},
        selected=selected,
        now=clock,
    )
    if metadata is not None:
        assert controller._cache.merge_metadata({GUNNERY_ID: _meta(metadata)}) == 1
    return controller


def _estimate_row(controller):
    return controller.state_payload()["characters"][0]


def test_metadata_backfill_enriches_an_id_only_cache_entry(tmp_path):
    """Ids were resolved long before training metadata existed, so a real
    user's cache is entirely id-only. Without a backfill pass their
    estimates would stay unavailable forever -- resolve() never revisits a
    name it has already answered."""
    clock = Clock()
    _seed_cache(tmp_path, {"gunnery": GUNNERY_ID})
    esi = FakeEsi(
        types={GUNNERY_ID: esi_response(200, _type_body(1, "perception", "willpower"))}
    )
    controller, _, _ = run_refresh(
        tmp_path,
        esi,
        character=_estimate_character(),
        clock=clock,
        plans={"Gunnery": "Gunnery V\n"},
        selected="Gunnery",
    )

    assert controller._cache.get("Gunnery") == GUNNERY_ID
    assert controller._cache.training_metadata(clock.value)[GUNNERY_ID].rank == 1
    # Saved in the same lock hold, or the next launch pays for it again.
    reloaded, warnings = skillids_mod.load(tmp_path / "eve_skills_cache.json")
    assert warnings == []
    assert reloaded.training_metadata(clock.value)[GUNNERY_ID].rank == 1


def test_metadata_backfill_publishes_every_answer_or_none(tmp_path):
    """A payload built halfway through a two-type backfill would score one
    plan skill with an estimate and the other without, so the row would
    show a number that is confidently too small. The fetch is staged and
    merged once, and it happens with the state lock released."""
    clock = Clock()
    _seed_cache(tmp_path, {"gunnery": GUNNERY_ID, "navigation": NAVIGATION_ID})
    esi = FakeEsi(
        types={
            GUNNERY_ID: esi_response(200, _type_body(1, "perception", "willpower")),
            NAVIGATION_ID: esi_response(200, _type_body(1, "intelligence", "memory")),
        }
    )
    controller = None
    observed = []
    lock_free = []
    # The probes themselves are serialized. Two of them run concurrently on
    # the fetch's worker threads, and one probe holding the state lock
    # would make the other's non-blocking acquire fail -- reporting the
    # test's own instrumentation as the production bug it is looking for.
    probe_gate = threading.Lock()

    def observe(path):
        # Runs on the backfill's own worker threads, i.e. WHILE it is in
        # flight. A lock it cannot take here is a lock the fetch is holding
        # across the network, which is the rule this asserts rather than
        # hangs on.
        with probe_gate:
            taken = controller._lock.acquire(blocking=False)
            lock_free.append(taken)
            if not taken:
                # Return, do not read the payload: state_payload() takes
                # the same lock BLOCKING, and the thread that already
                # holds it is waiting on this pool to finish -- so the
                # regression this test exists to catch would hang the
                # suite instead of failing it. The assertion below is what
                # reports it.
                return
            try:
                # Both reads happen under the lock this probe just proved
                # was free: a merge cannot land between the payload and
                # the count, so a half-merged pass cannot be sampled as a
                # whole one.
                controller.state_payload()
                observed.append(len(controller._cache.training_metadata(clock.value)))
            finally:
                controller._lock.release()

    controller, _, _ = build(
        tmp_path,
        characters=[_estimate_character()],
        client=esi,
        sso=FakeSso(),
        spawn=DirectSpawn(),
        now=clock,
        plans={"Gunnery": "Gunnery V\nNavigation I\n"},
        selected="Gunnery",
    )
    esi.on_type = observe

    controller.refresh_characters()

    assert lock_free == [True, True], "the fetch held the state lock across ESI"
    assert len(observed) == 2
    assert set(observed) <= {0, 2}  # never one entry of a two-entry merge
    assert len(controller._cache.training_metadata(clock.value)) == 2


def test_metadata_backfill_failure_only_stops_the_estimate(tmp_path):
    """Public metadata is not character data. A type call that fails must
    leave readiness -- the answer the whole screen exists for -- exactly
    where a successful refresh put it."""
    clock = Clock()
    _seed_cache(tmp_path, {"gunnery": GUNNERY_ID})
    esi = FakeEsi(types={GUNNERY_ID: esi_response(500, error="upstream")})
    controller, _, _ = run_refresh(
        tmp_path,
        esi,
        character=_estimate_character(),
        clock=clock,
        plans={"Gunnery": "Gunnery V\n"},
        selected="Gunnery",
    )

    row = _estimate_row(controller)
    assert (row["readiness"], row["missing_count"]) == ("Missing", 1)
    assert row["error"] == "" and row["stale"] is False
    assert row["training_remaining_seconds"] is None
    assert row["training_remaining_label"] == ""
    assert row["training_estimate_status"] == training_mod.METADATA_UNAVAILABLE


@pytest.mark.parametrize(
    ("age", "expected_calls"),
    [
        pytest.param(timedelta(0), 0, id="fresh"),
        pytest.param(skillids_mod.METADATA_MAX_AGE, 1, id="expired"),
    ],
)
def test_metadata_backfill_spends_a_request_only_on_an_aged_record(
    tmp_path, age, expected_calls
):
    """Thirty days of freshness is the point of caching it at all: a
    refresh that re-fetched every plan skill's type detail would spend one
    public request per skill, per click, forever. Both directions are
    asserted together -- a backfill that never fired would satisfy the
    fresh case for entirely the wrong reason."""
    clock = Clock()
    esi = FakeEsi(
        types={GUNNERY_ID: esi_response(200, _type_body(1, "perception", "willpower"))}
    )
    _seed_cache(tmp_path, {"gunnery": GUNNERY_ID})
    controller, _, _ = build(
        tmp_path,
        characters=[_estimate_character()],
        client=esi,
        sso=FakeSso(),
        spawn=DirectSpawn(),
        now=clock,
        plans={"Gunnery": "Gunnery V\n"},
        selected="Gunnery",
    )
    controller._cache.merge_metadata({GUNNERY_ID: _meta(clock.value - age)})

    controller.refresh_characters()

    assert len([c for c in esi.calls if "/universe/types/" in c[0]]) == expected_calls
    # Either way the record ends the pass fresh and usable, so the estimate
    # an expired record suppressed is restored by the same refresh.
    assert _estimate_row(controller)["training_estimate_status"] == (
        training_mod.AVAILABLE
    )


def test_training_remaining_is_published_for_the_selected_plan(tmp_path):
    """The whole feature: raw seconds for the page to sort on, a formatted
    label for it to print, and a status word that says which."""
    controller = _estimating(tmp_path)

    row = _estimate_row(controller)

    assert row["training_remaining_seconds"] == GUNNERY_V_SECONDS
    assert row["training_remaining_label"] == GUNNERY_V_LABEL
    assert row["training_estimate_status"] == training_mod.AVAILABLE


def test_training_remaining_needs_a_complete_sp_snapshot(tmp_path):
    """A partial SP map reads every absent skill as zero, which inflates
    the estimate rather than admitting it does not know."""
    controller = _estimating(tmp_path, _estimate_character(skill_points_complete=False))

    row = _estimate_row(controller)

    assert row["training_remaining_seconds"] is None
    assert row["training_remaining_label"] == ""
    assert row["training_estimate_status"] == training_mod.REFRESH_REQUIRED


def test_training_remaining_needs_attributes_that_were_confirmed(tmp_path):
    """Attributes carry their own freshness. An unconfirmed set beside
    newly refreshed SP is exactly the silent mismatch the supplemental
    timestamp exists to prevent."""
    controller = _estimating(tmp_path)
    controller._state.characters[0].attributes_fetched_utc = None

    row = _estimate_row(controller)

    assert row["training_remaining_seconds"] is None
    assert row["training_estimate_status"] == training_mod.ATTRIBUTES_UNAVAILABLE


def test_training_remaining_needs_attributes_that_did_not_fail(tmp_path):
    """A recorded attributes_error means the stored map is last-known, not
    current, so it must not feed a number the row presents as a fact."""
    controller = _estimating(
        tmp_path,
        _estimate_character(attributes_error=controller_mod.MSG_ATTRIBUTES_UNREADABLE),
    )

    row = _estimate_row(controller)

    assert row["training_remaining_seconds"] is None
    assert row["training_estimate_status"] == training_mod.ATTRIBUTES_UNAVAILABLE


def test_the_attributes_error_text_never_reaches_the_payload(tmp_path):
    """attributes_error carries transport wording and can carry the
    re-authenticate message for a scope-shaped 403 -- on a character whose
    core refresh succeeded and whose token is fine. Putting that on the
    roster would tell the user to fix an account that is not broken."""
    controller = _estimating(
        tmp_path, _estimate_character(attributes_error=controller_mod.MSG_REAUTH)
    )

    payload = controller.state_payload()

    assert controller_mod.MSG_REAUTH not in json.dumps(payload, default=str)
    assert payload["characters"][0]["needs_reauth"] is False
    assert (
        payload["characters"][0]["training_estimate_status"]
        == training_mod.ATTRIBUTES_UNAVAILABLE
    )


def test_training_remaining_needs_metadata_that_was_resolved(tmp_path):
    controller = _estimating(tmp_path, metadata=None)

    row = _estimate_row(controller)

    assert row["training_remaining_seconds"] is None
    assert row["training_estimate_status"] == training_mod.METADATA_UNAVAILABLE


def test_training_remaining_needs_metadata_that_has_not_expired(tmp_path):
    """Expiry has to be enforced where the estimate is READ, not only where
    the backfill decides what to fetch: a refresh that failed to renew an
    aged record must not leave the last render's number standing."""
    controller = _estimating(tmp_path, metadata=T0 - skillids_mod.METADATA_MAX_AGE)

    row = _estimate_row(controller)

    assert row["training_remaining_seconds"] is None
    assert row["training_estimate_status"] == training_mod.METADATA_UNAVAILABLE


def test_training_remaining_includes_queued_requirements(tmp_path):
    """Queued is not trained. The SP is still owed, so it stays in the
    duration -- and estimated_finish_utc stays EVE's own queue fact rather
    than being recomputed from it."""
    finish = T0 + timedelta(days=2)
    queued = _estimate_character(
        queue=(evaluator_mod.QueueEntry(GUNNERY_ID, 5, T0, finish, 0),)
    )
    controller = _estimating(tmp_path, queued)

    row = _estimate_row(controller)

    assert (row["readiness"], row["queued_count"]) == ("Training", 1)
    assert row["training_remaining_seconds"] == GUNNERY_V_SECONDS
    assert row["estimated_finish_utc"] == finish.isoformat()


def test_training_remaining_is_zero_for_a_target_already_trained(tmp_path):
    """Trained-but-inactive is an Omega lapse, not missing SP: the skill is
    paid for, so it contributes no training time even though the row is not
    Ready."""
    trained = _estimate_character(
        trained_levels={GUNNERY_ID: 5},
        skill_points={GUNNERY_ID: training_mod.skill_point_threshold(1, 5)},
    )
    controller = _estimating(tmp_path, trained)

    row = _estimate_row(controller)

    assert row["trained_inactive_count"] == 1
    assert row["training_remaining_seconds"] == 0
    assert row["training_remaining_label"] == "0m"
    assert row["training_estimate_status"] == training_mod.AVAILABLE


def test_training_remaining_is_empty_with_no_plan_selected(tmp_path):
    """Nothing was asked for, so nothing is unavailable. The row keeps its
    existing Unscored shape and the estimate fields are simply empty."""
    controller = _estimating(tmp_path, selected="")

    row = _estimate_row(controller)

    assert row["readiness"] == "Unscored"
    assert row["training_remaining_seconds"] is None
    assert row["training_remaining_label"] == ""
    assert row["training_estimate_status"] == ""
