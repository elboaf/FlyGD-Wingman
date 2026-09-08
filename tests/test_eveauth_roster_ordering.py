"""Whole-roster authority ordering with real Skills/Fittings persistence."""

import copy
import threading
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace

import pytest

from tests.test_eveauth_lifecycle import (
    T0,
    DeferredSpawn,
    build,
    full_identity,
    stored_character,
)
from wingman.eveauth import CleanupVerification, application
from wingman.eveauth import state as authority_state
from wingman.eveesi import EsiResponse
from wingman.evefittings import store as fittings_store
from wingman.evefittings.controller import FittingsController
from wingman.evefittings.model import CharacterSnapshot, FittingsState
from wingman.eveskills import state as skills_state
from wingman.eveskills.controller import SkillsController


@contextmanager
def running(target, *, name):
    errors = []

    def run():
        try:
            target()
        except BaseException as exc:  # noqa: BLE001 -- re-raise worker failures in the caller.
            errors.append(exc)

    thread = threading.Thread(target=run, name=name, daemon=True)
    thread.start()
    try:
        yield thread
    finally:
        thread.join(timeout=5)
        assert not thread.is_alive(), f"{name} did not finish"
        if errors:
            raise errors[0]


@pytest.fixture
def roster(tmp_path, monkeypatch, request):
    auth_spawn = DeferredSpawn()
    # Production Skills starts a separate Thread, not an inline refresh under
    # its caller's locks. Most tests leave that independent work queued.
    skills_spawn = DeferredSpawn()
    authority, alerts, _, _ = build(
        tmp_path,
        characters=[stored_character(scopes=application.FULL_AUTH_SCOPES)],
        spawn=auth_spawn,
        returned_identity=full_identity(43, owner_hash="owner-43"),
    )
    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()
    skills_path = tmp_path / "skills.json"
    fittings_path = tmp_path / "fittings.json"
    skills_state.save(
        skills_state.SkillsState(characters=[skills_state.Character(42)]),
        skills_path,
    )
    fittings_store.save_fittings(
        fittings_path,
        FittingsState(snapshots=(CharacterSnapshot(42, fetched_utc=T0),)),
    )
    saved_skills = []
    saved_fittings = []
    saved_authority = []
    save_authority = authority._save_authority

    def record_authority(path, state):
        saved_authority.append(copy.deepcopy(state))
        save_authority(path, state)

    authority._save_authority = record_authority
    save_skills = skills_state.save

    def record_skills(state, path):
        saved_skills.append(copy.deepcopy(state))
        save_skills(state, path)

    def record_fittings(path, state):
        saved_fittings.append(state)
        fittings_store.save_fittings(path, state)

    monkeypatch.setattr(skills_state, "save", record_skills)
    skills = SkillsController(
        state_path=skills_path,
        cache_path=tmp_path / "skillids.json",
        plans_dir=plans_dir,
        push=lambda *args: None,
        alert=lambda *args: None,
        authority=authority,
        client=object(),
        spawn=skills_spawn,
        now=lambda: T0,
    )
    fittings = FittingsController(
        state_path=fittings_path,
        names_path=tmp_path / "names.json",
        authority=authority,
        client=SimpleNamespace(
            get=lambda path, **kwargs: EsiResponse(200, [], "", '"fresh"', "GET", path)
        ),
        save_state=record_fittings,
        now=lambda: T0,
    )
    if application.SKILLS not in getattr(request, "param", ()):
        authority.register_participant(application.SKILLS, skills)
    authority.register_participant(application.FITTINGS, fittings)

    def consent(character_id):
        authority._validate_token = lambda *args, **kwargs: full_identity(
            character_id, owner_hash=f"owner-{character_id}"
        )
        assert authority.start_full_authorization().accepted
        return auth_spawn.targets.pop(0)

    return SimpleNamespace(
        authority=authority,
        skills=skills,
        fittings=fittings,
        consent=consent,
        skills_spawn=skills_spawn,
        saved_skills=saved_skills,
        saved_fittings=saved_fittings,
        saved_authority=saved_authority,
        skills_path=skills_path,
        fittings_path=fittings_path,
        authority_path=tmp_path / "eve_authority.json",
        alerts=alerts,
    )


@pytest.mark.parametrize("later", ["consent", "forget", "forget_then_consent"])
def test_delayed_consent_completion_cannot_publish_an_older_roster(
    roster, monkeypatch, later
):
    """An old worker tail must neither prune newer rows nor undo a forget."""
    committed = threading.Event()
    release = threading.Event()
    original = roster.authority._run_auth

    def delay_older_worker(**kwargs):
        result = original(**kwargs)
        if threading.current_thread().name == "older-consent":
            committed.set()
            assert release.wait(timeout=5)
        return result

    monkeypatch.setattr(roster.authority, "_run_auth", delay_older_worker)
    with running(roster.consent(43), name="older-consent"):
        try:
            assert committed.wait(timeout=5)
            if later != "consent":
                assert roster.authority.forget(43).persisted
            if later != "forget":
                roster.consent(44)()
                assert roster.skills.set_character_group(44, "Keep this group")
                assert roster.fittings.refresh([44])["ok"]
        finally:
            release.set()

    expected = {
        "consent": [42, 43, 44],
        "forget": [42],
        "forget_then_consent": [42, 44],
    }[later]
    persisted_authority, _ = authority_state.load_authority(roster.authority_path)
    persisted_skills, _ = skills_state.load(roster.skills_path)
    assert [row.character_id for row in roster.authority.characters] == expected
    assert [row.character_id for row in persisted_authority.characters] == expected
    assert [
        row["character_id"] for row in roster.skills.state_payload()["characters"]
    ] == expected
    assert [row.character_id for row in persisted_skills.characters] == expected
    assert [row.character_id for row in roster.saved_skills[-1].characters] == expected
    if later != "forget":
        assert persisted_skills.find(44).group == "Keep this group"
        persisted_fittings, _ = fittings_store.load_fittings(roster.fittings_path)
        assert [row.character_id for row in roster.fittings.state.snapshots] == [42, 44]
        assert [row.character_id for row in persisted_fittings.snapshots] == [42, 44]
        assert [row.character_id for row in roster.saved_fittings[-1].snapshots] == [
            42,
            44,
        ]


class ObservedRosterGate:
    """Expose attempted entry, not a sleep-based guess that a worker ran."""

    def __init__(self, authority, contender):
        self.lock = authority._roster_gate
        self.authority = authority
        self.contender = contender
        self.waiting = threading.Event()

    def __enter__(self):
        assert not self.authority._lock._is_owned()
        if threading.current_thread().name == self.contender:
            self.waiting.set()
        self.lock.acquire()
        return self

    def __exit__(self, *args):
        self.lock.release()


def observe_gate(roster, monkeypatch, contender):
    authority = roster.authority
    gate = ObservedRosterGate(authority, contender)
    monkeypatch.setattr(authority, "_roster_gate", gate)
    original = authority._lifecycle_gate

    def lifecycle(character_id):
        assert not gate.lock._is_owned(), "lifecycle entered under roster gate"
        return original(character_id)

    monkeypatch.setattr(authority, "_lifecycle_gate", lifecycle)
    return gate


@pytest.mark.parametrize("action", ["cancel", "shutdown"])
def test_stalled_consent_hooks_allow_reads_and_cancellation_of_a_waiting_consent(
    roster, monkeypatch, action
):
    gate = observe_gate(roster, monkeypatch, "waiting-consent")
    entered = threading.Event()
    release = threading.Event()
    original = roster.skills.reconcile_characters

    def stalled(characters):
        result = original(characters)
        if threading.current_thread().name == "committed-consent":
            assert gate.lock._is_owned()
            assert not roster.authority._lock._is_owned()
            entered.set()
            assert release.wait(timeout=5)
        return result

    monkeypatch.setattr(roster.skills, "reconcile_characters", stalled)
    with running(roster.consent(43), name="committed-consent"):
        try:
            assert entered.wait(timeout=5)
            # The first durable commit still wins cancellation, even though its
            # participants have not finished. The next attempt can be cancelled.
            assert not roster.authority.cancel_authorization().accepted
            with running(roster.consent(44), name="waiting-consent"):
                try:
                    assert gate.waiting.wait(timeout=5)
                    done = threading.Event()

                    def read_and_cancel():
                        assert [
                            row.character_id for row in roster.authority.characters
                        ] == [42, 43]
                        assert roster.authority.character(43) is not None
                        assert (
                            len(roster.authority.management_state()["characters"]) == 2
                        )
                        assert (
                            roster.authority.capability_status(43, application.SKILLS)
                            == "enabled"
                        )
                        if action == "shutdown":
                            roster.authority.shutdown()
                        else:
                            assert roster.authority.cancel_authorization().accepted
                        done.set()

                    with running(read_and_cancel, name="reader-canceller"):
                        assert done.wait(timeout=5)
                    assert roster.authority.character(44) is None
                finally:
                    release.set()
        finally:
            release.set()

    assert [row.character_id for row in roster.authority.characters] == [42, 43]
    assert [
        [row.character_id for row in candidate.characters]
        for candidate in roster.saved_authority
    ] == [[42, 43]]
    assert not roster.authority.auth_in_progress
    assert not roster.alerts


@pytest.mark.parametrize("roster", [(application.SKILLS,)], indirect=True)
def test_registration_finishes_projection_before_a_new_consent(roster, monkeypatch):
    gate = observe_gate(roster, monkeypatch, "new-consent")
    entered = threading.Event()
    release = threading.Event()
    original = roster.skills.reconcile_characters
    results = []

    def stalled(characters):
        if threading.current_thread().name == "registration":
            entered.set()
            assert release.wait(timeout=5)
        return original(characters)

    monkeypatch.setattr(roster.skills, "reconcile_characters", stalled)

    def register():
        results.append(
            roster.authority.register_participant(application.SKILLS, roster.skills)
        )

    with running(register, name="registration"):
        try:
            assert entered.wait(timeout=5)
            with running(roster.consent(43), name="new-consent"):
                try:
                    assert gate.waiting.wait(timeout=5)
                    assert roster.authority.character(43) is None
                finally:
                    release.set()
        finally:
            release.set()

    assert results == [CleanupVerification(True, frozenset())]
    persisted, _ = skills_state.load(roster.skills_path)
    assert [row.character_id for row in persisted.characters] == [42, 43]
    assert [row.character_id for row in roster.saved_skills[-1].characters] == [42, 43]


@pytest.mark.parametrize("later", ["consent", "failed_forget"])
def test_unknown_verification_cannot_publish_over_a_later_membership_transaction(
    roster, monkeypatch, later
):
    roster.consent(43)()
    assert roster.fittings.refresh([43])["ok"]
    gate = observe_gate(roster, monkeypatch, "later-membership")
    for capability in application.FULL_AUTH_CAPABILITIES:
        roster.authority._store_cleanup_verification(
            capability, CleanupVerification(False)
        )
    entered = threading.Event()
    release = threading.Event()
    original = roster.skills.reconcile_characters
    results = []

    def stalled(characters):
        result = original(characters)
        if threading.current_thread().name == "unknown-verification":
            # Stall AFTER the participant computed its result, BEFORE authority
            # stores it. An old clean result must not erase a newer failure.
            entered.set()
            assert release.wait(timeout=5)
        return result

    monkeypatch.setattr(roster.skills, "reconcile_characters", stalled)

    with running(
        lambda: roster.authority._verify_unknown_character(77),
        name="unknown-verification",
    ):
        try:
            assert entered.wait(timeout=5)
            if later == "consent":
                target = roster.consent(44)
            else:

                def fail_skills(state, path):
                    raise OSError("skills disk unavailable")

                def fail_fittings(path, state):
                    raise OSError("fittings disk unavailable")

                monkeypatch.setattr(skills_state, "save", fail_skills)
                monkeypatch.setattr(roster.fittings, "_save_state", fail_fittings)

                def target():
                    results.append(roster.authority.forget(43))

            with running(target, name="later-membership"):
                try:
                    assert gate.waiting.wait(timeout=5)
                finally:
                    release.set()
        finally:
            release.set()

    persisted_skills, _ = skills_state.load(roster.skills_path)
    if later == "consent":
        assert [row.character_id for row in persisted_skills.characters] == [42, 43, 44]
        assert [row.character_id for row in roster.saved_skills[-1].characters] == [
            42,
            43,
            44,
        ]
    else:
        assert results[0].applied and not results[0].persisted
        assert roster.authority.character(43) is None
        # Failed removal keeps the old feature state as cleanup evidence, both
        # live and on disk. Neither participant's failed result can be erased.
        assert [row.character_id for row in persisted_skills.characters] == [42, 43]
        persisted_fittings, _ = fittings_store.load_fittings(roster.fittings_path)
        assert [row.character_id for row in persisted_fittings.snapshots] == [42, 43]
        assert [row.character_id for row in roster.fittings.state.snapshots] == [42, 43]
        for capability in application.FULL_AUTH_CAPABILITIES:
            verification = roster.authority._cleanup_verification[capability]
            assert verification.verified
            assert verification.blocked_character_ids == frozenset({43})
        assert not roster.authority._verify_unknown_character(43).applied
        assert roster.authority._verify_unknown_character(77).applied


def test_production_skills_spawner_does_not_reenter_lifecycle_under_roster_gate(
    roster, monkeypatch
):
    gate = observe_gate(roster, monkeypatch, "unused-contender")
    monkeypatch.setattr(roster.skills, "_spawn", threading.Thread)
    with roster.authority._lock:
        roster.authority._access_tokens[42] = ("access-42", T0 + timedelta(hours=1))
    requests = []
    caller = threading.current_thread()

    def get(path, **kwargs):
        assert threading.current_thread() is not caller
        assert not gate.lock._is_owned()
        requests.append(path)
        if path.endswith("/skills/"):
            data = {"skills": []}
        elif path.endswith("/skillqueue/"):
            data = []
        else:
            assert path.endswith("/attributes/")
            data = dict.fromkeys(
                ["intelligence", "memory", "perception", "willpower", "charisma"], 20
            )
        return EsiResponse(200, data, "", '"fresh"', "GET", path)

    monkeypatch.setattr(roster.skills, "_client", SimpleNamespace(get=get))
    roster.consent(43)()
    assert roster.skills._refresh_idle.wait(timeout=5)
    persisted, _ = skills_state.load(roster.skills_path)
    assert persisted.find(42).fetched_utc == T0
    assert persisted.find(43).fetched_utc == T0
    assert len(requests) == 6


@pytest.mark.parametrize("roster", [(application.SKILLS,)], indirect=True)
def test_cleanup_eligibility_is_rechecked_after_token_wrapping(roster, monkeypatch):
    """A formerly unavailable participant can become ready during wrapping."""
    gate = observe_gate(roster, monkeypatch, "unused-contender")

    def wrap(token):
        assert not gate.lock._is_owned()
        assert not roster.authority._lock._is_owned()
        assert roster.authority.register_participant(
            application.SKILLS, roster.skills
        ).verified
        return token

    monkeypatch.setattr(roster.authority, "_wrap_token", wrap)
    roster.consent(43)()
    assert [row.character_id for row in roster.authority.characters] == [42, 43]
    persisted, _ = skills_state.load(roster.skills_path)
    assert [row.character_id for row in persisted.characters] == [42, 43]
    assert not roster.alerts


@pytest.mark.parametrize("phase", ["preliminary", "final"])
def test_shutdown_during_precommit_cleanup_prevents_authority_save(
    roster, monkeypatch, phase
):
    observe_gate(roster, monkeypatch, "unused-contender")

    def invalidate_verification():
        roster.authority._store_cleanup_verification(
            application.SKILLS, CleanupVerification(False)
        )

    if phase == "preliminary":
        invalidate_verification()
    else:
        # Force a real participant retry only AFTER the preliminary check and
        # wrapping, so shutdown lands between final eligibility and durable save.
        def wrap(token):
            invalidate_verification()
            return token

        monkeypatch.setattr(roster.authority, "_wrap_token", wrap)
    entered = threading.Event()
    release = threading.Event()
    stopped = threading.Event()
    original = roster.skills.reconcile_characters

    def stalled(characters):
        result = original(characters)
        entered.set()
        assert release.wait(timeout=5)
        return result

    def stop():
        roster.authority.shutdown()
        stopped.set()

    monkeypatch.setattr(roster.skills, "reconcile_characters", stalled)
    with running(roster.consent(43), name="precommit-consent"):
        try:
            assert entered.wait(timeout=5)
            with running(stop, name="shutdown"):
                assert stopped.wait(timeout=5)
        finally:
            release.set()
    assert roster.authority.character(43) is None
    assert not roster.saved_authority
    assert not roster.alerts


@pytest.mark.parametrize("action", ["cancel", "shutdown"])
def test_cancelled_waiter_cannot_begin_preliminary_feature_cleanup(
    roster, monkeypatch, action
):
    """A cancelled worker must not retry blocked cleanup after it obtains R."""
    save_skills = skills_state.save
    save_fittings = roster.fittings._save_state

    def fail_save(*args):
        raise OSError("disk unavailable")

    monkeypatch.setattr(skills_state, "save", fail_save)
    monkeypatch.setattr(roster.fittings, "_save_state", fail_save)
    forgotten = roster.authority.forget(42)
    assert forgotten.applied and not forgotten.persisted
    # Both real participants retain 42 as evidence of failed cleanup. A retry
    # would now succeed, making any work by the cancelled waiter observable.
    monkeypatch.setattr(skills_state, "save", save_skills)
    monkeypatch.setattr(roster.fittings, "_save_state", save_fittings)
    wrapped = []

    def wrap(token):
        wrapped.append(token)
        return token

    monkeypatch.setattr(roster.authority, "_wrap_token", wrap)
    gate = observe_gate(roster, monkeypatch, "cancelled-waiter")
    held = threading.Event()
    release = threading.Event()

    def hold_gate():
        with gate:
            held.set()
            assert release.wait(timeout=5)

    with running(hold_gate, name="roster-holder"):
        try:
            assert held.wait(timeout=5)
            with running(roster.consent(43), name="cancelled-waiter"):
                try:
                    assert gate.waiting.wait(timeout=5)
                    if action == "shutdown":
                        roster.authority.shutdown()
                    else:
                        assert roster.authority.cancel_authorization().accepted
                finally:
                    release.set()
        finally:
            release.set()

    persisted_skills, _ = skills_state.load(roster.skills_path)
    persisted_fittings, _ = fittings_store.load_fittings(roster.fittings_path)
    assert [row.character_id for row in persisted_skills.characters] == [42]
    assert [row.character_id for row in persisted_fittings.snapshots] == [42]
    assert not roster.saved_skills
    assert not roster.saved_fittings
    assert len(roster.saved_authority) == 1  # Only the completed Forget.
    assert not roster.authority.characters
    assert not wrapped
    for capability in application.FULL_AUTH_CAPABILITIES:
        assert roster.authority._cleanup_verification[
            capability
        ].blocked_character_ids == frozenset({42})
