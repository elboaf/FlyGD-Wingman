"""SkillsController: the single writer of the skills state document.

Every test here is headless. No network (the ESI client is a fake), no
sockets, no browser, no real threads unless the test says so, and `tmp_path`
for the state file, the id cache, and the plans folder.
"""
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from obs_youtube_uploader.eveskills import esi as esi_mod
from obs_youtube_uploader.eveskills import sso as sso_mod
from obs_youtube_uploader.eveskills import state as state_mod
from obs_youtube_uploader.eveskills.controller import SkillsController

UTC = timezone.utc
T0 = datetime(2026, 8, 24, 12, 0, 0, tzinfo=UTC)


class Clock:
    """A `now` that only moves when a test moves it."""

    def __init__(self, start=T0):
        self.value = start

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value = self.value + timedelta(seconds=seconds)


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


def build(tmp_path, *, plans=None, characters=(), selected="", **kwargs):
    """A controller over a fresh tmp state dir, with its pushes recorded."""
    plans_dir = tmp_path / "skill_plans"
    plans_dir.mkdir(exist_ok=True)          # Exists, so nothing is seeded.
    for name, body in (plans or {}).items():
        (plans_dir / f"{name}.txt").write_text(body, encoding="utf-8")

    if characters or selected:
        seed = state_mod.SkillsState(characters=list(characters),
                                     selected_plan_name=selected)
        state_mod.save(seed, tmp_path / "eve_skills.json")

    pushed = []
    alerts = []
    controller = SkillsController(
        state_path=tmp_path / "eve_skills.json",
        cache_path=tmp_path / "eve_skills_cache.json",
        plans_dir=plans_dir,
        push=lambda handler, payload: pushed.append((handler, payload)),
        alert=lambda kind, title, body: alerts.append((kind, title, body)),
        client=kwargs.pop("client", None) or object(),
        now=kwargs.pop("now", Clock()),
        **kwargs)
    return controller, pushed, alerts


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

    with controller._lock:
        with controller._lock:          # Deadlocks here under threading.Lock.
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
    character = state_mod.Character(character_id=95, character_name="Zuelo Parvi")
    controller, _, _ = build(tmp_path, characters=[character],
                             plans={"Interceptor": "Navigation V\n"},
                             selected="Interceptor")

    row = controller.state_payload()["characters"][0]

    assert row["readiness"] == "Unscored"
    assert row["fetched_utc"] == ""
    assert (row["active_count"], row["missing_count"],
            row["unknown_count"]) == (0, 0, 0)


def test_with_no_plan_selected_every_character_is_unscored(tmp_path):
    """Not an error state: the route opens with nothing selected, and forty
    rows reading Unscored is the correct first frame."""
    character = state_mod.Character(character_id=95, character_name="Aiga",
                                    fetched_utc=T0)
    controller, _, _ = build(tmp_path, characters=[character],
                             plans={"Interceptor": "Navigation V\n"})

    payload = controller.state_payload()

    assert payload["selected_plan_name"] == ""
    assert payload["characters"][0]["readiness"] == "Unscored"


def test_plan_rows_carry_their_size_and_their_ready_count(tmp_path):
    """The left rail shows a ready ratio per plan, so the payload has to
    score every character against every plan, not only the selected one."""
    controller, _, _ = build(tmp_path, plans={
        "Interceptor": "Navigation V\nSpaceship Command III\n",
        "Hauler": "Navigation I\n"})

    rows = {row["name"]: row for row in controller.state_payload()["plans"]}

    assert rows["Interceptor"]["requirement_count"] == 2
    assert rows["Hauler"]["requirement_count"] == 1
    assert rows["Interceptor"]["ready_count"] == 0   # No characters at all.


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
    controller._save_locked = lambda: False   # Simulate an unwritable disk.

    assert controller.select_plan("Interceptor") is False
    assert controller._state.selected_plan_name == ""      # Rolled back.
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
    controller._push_state()                 # Identical: skipped.
    assert len(pushed) == 1

    controller.select_plan("A")              # Mutation: forced.
    controller.select_plan("A")              # Same value, still forced.
    assert len(pushed) == 3


def test_reload_plans_sees_a_file_added_since_construction(tmp_path):
    """The whole point of the button: the user drops a .txt in the folder
    with Wingman already running."""
    controller, _, _ = build(tmp_path, plans={"A": "Navigation I\n"})
    (tmp_path / "skill_plans" / "B.txt").write_text("Navigation II\n",
                                                    encoding="utf-8")

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
    return esi_mod.EsiResponse(status=status, data=data, error=error,
                               etag=etag, method="GET", path=path)


SKILLS_BODY = {"skills": [{"skill_id": 3327, "active_skill_level": 4,
                           "trained_skill_level": 5}]}
QUEUE_BODY = [{"skill_id": 3327, "finished_level": 5, "queue_position": 0,
               "start_date": "2026-08-24T12:00:00Z",
               "finish_date": "2026-08-26T12:00:00Z"}]


class FakeEsi:
    """Replays scripted responses per path suffix, and records every call.

    Keyed on the suffix rather than the whole path so a test does not have
    to repeat the character id. A path with no script is an assertion
    failure, not a default -- an unexpected ESI call is exactly the bug
    these tests exist to catch.
    """

    def __init__(self, skills=None, queue=None):
        self.skills = list(skills or [esi_response(200, SKILLS_BODY, etag='"s1"')])
        self.queue = list(queue or [esi_response(200, QUEUE_BODY, etag='"q1"')])
        self.calls = []
        self.on_get = None
        self._hooked = False

    def get(self, path, *, token=None, etag=None):
        self.calls.append((path, token, etag))
        if self.on_get is not None and not self._hooked:
            self._hooked = True          # Fires once, or the test never ends.
            self.on_get(path)
        script = self.skills if path.endswith("/skills/") else self.queue
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

    def __init__(self, expires_in=1200, raises=None):
        self.expires_in = expires_in
        self.raises = raises
        self.refreshes = []

    def refresh_token(self, token, **kwargs):
        self.refreshes.append(token)
        if self.raises is not None:
            raise self.raises
        return sso_mod.TokenSet(access_token=f"access-{len(self.refreshes)}",
                                refresh_token=f"refresh-{len(self.refreshes)}",
                                expires_in=self.expires_in)


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
    from obs_youtube_uploader.eveskills import tokens as tokens_mod
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


def test_the_running_pass_re_enters_when_one_was_requested_during_it(tmp_path):
    """The latch drops the *worker*, never the *request*. A refresh clicked
    while one is running must still produce fresh data -- otherwise the
    button silently does nothing during the twenty seconds a forty-character
    pass takes, which reads as a broken button."""
    character = state_mod.Character(character_id=95, refresh_token_blob="blob")
    esi = FakeEsi()
    controller = None
    esi.on_get = lambda path: controller.refresh_characters()  # once; see below
    controller, _, _ = build(tmp_path, characters=[character], client=esi,
                             sso=FakeSso(), spawn=DirectSpawn())

    controller.refresh_characters()

    # Two passes over the one character: two skills calls, two queue calls.
    assert len([c for c in esi.calls if c[0].endswith("/skills/")]) == 2


def with_snapshot(**kwargs):
    """A character that already has committed data, so a later refresh has
    something to preserve or overwrite."""
    defaults = dict(character_id=95, character_name="Aiga Otsolen",
                    refresh_token_blob="blob", fetched_utc=T0,
                    active_levels={3327: 3}, trained_levels={3327: 3},
                    skills_etag='"old-s"', queue_etag='"old-q"')
    defaults.update(kwargs)
    return state_mod.Character(**defaults)


def run_refresh(tmp_path, esi, character=None, clock=None, **kwargs):
    clock = clock or Clock()
    controller, pushed, alerts = build(
        tmp_path, characters=[character or with_snapshot()], client=esi,
        sso=FakeSso(), spawn=DirectSpawn(), now=clock, **kwargs)
    controller.refresh_characters()
    return controller, pushed, clock


def test_200_and_200_commits_both_halves(tmp_path):
    """The ordinary path. fetched_utc moves, both etags are stored, and any
    previous error is cleared."""
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
    assert ch.active_levels == {3327: 3}          # Untouched.
    assert ch.skills_etag == '"old-s"'            # A 304 carries no new etag.


def test_200_and_304_commits_the_fresh_half_and_keeps_the_stored_one(tmp_path):
    """Per-endpoint freshness is the hazard conditional requests introduce.
    The rule that makes it safe: a 304 means the stored half is already
    current, so the pair is still one coherent snapshot."""
    esi = FakeEsi(queue=[esi_response(304)])
    controller, _, _ = run_refresh(tmp_path, esi)

    ch = controller._state.characters[0]
    assert ch.active_levels == {3327: 4}          # Fresh skills committed.
    assert ch.queue_etag == '"old-q"'             # Stored queue kept.
    assert ch.error == ""


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
    assert ch.error and ch.needs_reauth is False
    assert controller.state_payload()["characters"][0]["stale"] is True


def test_a_failing_skills_call_skips_the_queue_call_entirely(tmp_path):
    """Ported short-circuit. The queue result could not be committed on its
    own, so spending the request only burns error-limit budget."""
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
def test_a_definitive_failure_needs_reauth_and_deletes_the_token(tmp_path, status):
    """403, and 401 that survives one retry, are definitive: the grant is
    gone or no longer carries the scope, and only a fresh consent screen
    fixes either. Keeping the token would retry a dead grant on every
    refresh forever."""
    esi = FakeEsi(skills=[esi_response(status, error="denied")])
    controller, _, _ = run_refresh(tmp_path, esi)

    ch = controller._state.characters[0]
    assert ch.needs_reauth is True
    assert ch.refresh_token_blob == ""
    assert ch.error == (
        "EVE rejected the stored authorisation. Re-authenticate this character.")
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

    ch = controller._state.characters[0]
    assert ch.needs_reauth is False
    assert ch.refresh_token_blob == "refresh-1"


def test_a_definitive_oauth_error_is_definitive_here_too(tmp_path):
    """invalid_grant means the refresh token is revoked or already used.
    OAuthError.definitive is the classification; this asserts the controller
    honours it rather than inventing a second one."""
    esi = FakeEsi()
    controller, _, _ = build(
        tmp_path, characters=[with_snapshot()], client=esi,
        sso=FakeSso(raises=sso_mod.OAuthError(400, "invalid_grant", "revoked")),
        spawn=DirectSpawn())
    controller.refresh_characters()

    ch = controller._state.characters[0]
    assert ch.needs_reauth is True and ch.refresh_token_blob == ""
    assert esi.calls == [], "no ESI call is worth making without a token"


def test_a_transient_oauth_error_keeps_the_token(tmp_path):
    """An SSO 503 is not a revoked grant. Deleting the token here would cost
    the user a re-authentication for CCP's downtime."""
    controller, _, _ = build(
        tmp_path, characters=[with_snapshot()], client=FakeEsi(),
        sso=FakeSso(raises=sso_mod.OAuthError(503, "server_error", "down")),
        spawn=DirectSpawn())
    controller.refresh_characters()

    ch = controller._state.characters[0]
    assert ch.needs_reauth is False and ch.refresh_token_blob == "blob"


def test_a_cached_token_is_reused_across_both_calls(tmp_path):
    """Two ESI calls per character must not mean two token refreshes. At
    forty characters that is forty wasted SSO round trips per click."""
    sso = FakeSso()
    controller, _, _ = build(tmp_path, characters=[with_snapshot()],
                             client=FakeEsi(), sso=sso, spawn=DirectSpawn())
    controller.refresh_characters()

    assert len(sso.refreshes) == 1


def test_a_401_forces_exactly_one_refresh_and_one_retry(tmp_path):
    """The stampede fix. A forced refresh only actually refreshes when the
    cached token is still the one ESI rejected -- so callers queued behind
    the first find a token that no longer matches and reuse it, and one
    stale token produces one refresh rather than N."""
    sso = FakeSso()
    esi = FakeEsi(skills=[esi_response(401, error="expired"),
                          esi_response(200, SKILLS_BODY, etag='"s1"')])
    controller, _, _ = build(tmp_path, characters=[with_snapshot()],
                             client=esi, sso=sso, spawn=DirectSpawn())
    controller.refresh_characters()

    skills_calls = [c for c in esi.calls if c[0].endswith("/skills/")]
    assert len(skills_calls) == 2                     # One 401, one retry.
    assert skills_calls[0][1] != skills_calls[1][1]   # A different token.
    # Two refreshes total: the initial mint, and the one the 401 forced.
    # The queue call that follows reuses the second and adds none.
    assert len(sso.refreshes) == 2


def test_an_expiring_token_is_refreshed_before_it_is_used(tmp_path):
    """A token that is valid when checked and expired when it lands is a
    401 the user pays a retry for. The margin covers the round trip."""
    sso = FakeSso(expires_in=10)      # Inside TOKEN_EXPIRY_MARGIN_S.
    controller, _, _ = build(tmp_path, characters=[with_snapshot()],
                             client=FakeEsi(), sso=sso, spawn=DirectSpawn())
    controller.refresh_characters()

    assert len(sso.refreshes) == 2, "the second call must not reuse it"


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
            return sso_mod.TokenSet(access_token="access-1",
                                    refresh_token="", expires_in=1200)

    sso = OmittingSso()
    controller, _, _ = build(tmp_path, characters=[with_snapshot()],
                             client=FakeEsi(), sso=sso, spawn=DirectSpawn())
    controller.refresh_characters()

    assert len(sso.refreshes) == 1
    assert controller._state.characters[0].refresh_token_blob == "blob"
