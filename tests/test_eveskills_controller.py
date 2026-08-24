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
