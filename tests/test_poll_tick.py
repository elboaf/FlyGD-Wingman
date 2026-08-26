"""The watcher tick, which no longer has a Tk event loop under it.

Under Tk this was a closure over root.after with no harness at all. It is a
module-level function now precisely so the three things that were only ever
verified by hand -- the deferred-refresh flag, the notify_mode branch, and
the one-shot failure notification -- have tests.
"""

from pathlib import Path

from wingman.__main__ import (
    FAILURE_NOTIFY_THRESHOLD,
    PollState,
    poll_tick,
)


class _FakeIcon:
    def __init__(self, exc=None):
        self.notifications = []
        self._exc = exc

    def notify(self, message, title):
        if self._exc is not None:
            raise self._exc
        self.notifications.append((message, title))


class _FakeState:
    def __init__(self, notify_mode):
        self.settings = {"notify_mode": notify_mode}


class _FakeApi:
    def __init__(self, uploading=False, notify_mode="toast"):
        self._state = _FakeState(notify_mode)
        self._uploading = uploading
        self.rows_calls = []
        # Recorded, not a no-op: otherwise nothing in the suite notices if
        # the status push is dropped from poll_tick, and the status bar
        # silently stops updating.
        self.status_pushes = 0

    def _busy(self):
        return self._uploading

    def _push_eve_status(self):
        self.status_pushes += 1

    def list_rows(self, preselect=None):
        self.rows_calls.append(preselect)


class _FakeWindow:
    def __init__(self):
        self.shown = 0

    def show(self):
        self.shown += 1


class _FakeWatcher:
    def __init__(self, ready=(), exc=None):
        self._ready = list(ready)
        self._exc = exc

    def poll_once(self):
        if self._exc is not None:
            raise self._exc
        return self._ready


def test_new_recordings_refresh_the_list_and_toast():
    api, icon, window = _FakeApi(), _FakeIcon(), _FakeWindow()
    state = PollState()

    poll_tick(_FakeWatcher([Path("a.mkv")]), api, icon, window, state)

    # A set of Path, matching RowSnapshot.rebuild's contract -- not strings.
    assert api.rows_calls == [{Path("a.mkv")}]
    assert icon.notifications == [
        ("1 new recording(s) ready to upload", "FlyGD Wingman")
    ]
    assert window.shown == 0


def test_popup_mode_raises_the_window_instead_of_toasting():
    api = _FakeApi(notify_mode="popup")
    icon, window = _FakeIcon(), _FakeWindow()

    poll_tick(_FakeWatcher([Path("a.mkv")]), api, icon, window, PollState())

    assert window.shown == 1
    assert icon.notifications == []


def test_notify_mode_is_read_live_not_snapshotted():
    """Settings is a route in the same window now, so this can change
    mid-run. Reading a startup snapshot would need a restart to take."""
    api, icon, window = _FakeApi(notify_mode="toast"), _FakeIcon(), _FakeWindow()
    state = PollState()

    poll_tick(_FakeWatcher([Path("a.mkv")]), api, icon, window, state)
    api._state.settings["notify_mode"] = "popup"
    poll_tick(_FakeWatcher([Path("b.mkv")]), api, icon, window, state)

    assert window.shown == 1
    assert len(icon.notifications) == 1


def test_a_refresh_during_an_upload_is_deferred_not_dropped():
    """Rebuilding the list mid-upload would wipe the links and progress of
    the upload actually running -- but the user still gets told."""
    api = _FakeApi(uploading=True)
    icon, window = _FakeIcon(), _FakeWindow()
    state = PollState()

    poll_tick(_FakeWatcher([Path("a.mkv")]), api, icon, window, state)

    assert state.refresh_deferred is True
    assert api.rows_calls == []
    assert len(icon.notifications) == 1


def test_the_deferred_refresh_lands_on_a_later_empty_tick():
    api = _FakeApi(uploading=True)
    icon, window = _FakeIcon(), _FakeWindow()
    state = PollState()
    poll_tick(_FakeWatcher([Path("a.mkv")]), api, icon, window, state)

    api._uploading = False
    poll_tick(_FakeWatcher([]), api, icon, window, state)

    assert state.refresh_deferred is False
    assert api.rows_calls == [None]


def test_a_failing_tick_notifies_exactly_once_at_the_threshold():
    """A single failure is indistinguishable from "nothing new", which is
    fine for a blip and not for an unreachable folder. One message, not a
    stream -- and none before the threshold."""
    api = _FakeApi()
    icon, window = _FakeIcon(), _FakeWindow()
    state = PollState()
    watcher = _FakeWatcher(exc=OSError("recording folder is gone"))

    for _ in range(FAILURE_NOTIFY_THRESHOLD + 3):
        poll_tick(watcher, api, icon, window, state)

    assert len(icon.notifications) == 1
    assert "trouble" in icon.notifications[0][0]


def test_the_failure_counter_resets_on_a_clean_tick():
    api, icon, window = _FakeApi(), _FakeIcon(), _FakeWindow()
    state = PollState()
    failing = _FakeWatcher(exc=OSError("blip"))
    for _ in range(FAILURE_NOTIFY_THRESHOLD - 1):
        poll_tick(failing, api, icon, window, state)

    poll_tick(_FakeWatcher([]), api, icon, window, state)

    assert state.consecutive_failures == 0
    assert icon.notifications == []


def test_a_tick_never_raises():
    """Scheduler reschedules regardless, but the counter and the one-shot
    notification live in here and would be lost with the exception."""
    api, window = _FakeApi(), _FakeWindow()
    icon = _FakeIcon(exc=RuntimeError("no toast service"))

    poll_tick(_FakeWatcher([Path("a.mkv")]), api, icon, window, PollState())


def test_each_tick_pushes_engine_status():
    """The status bar updates only because poll_tick pushes on every tick.
    Without this assertion, removing that call would silently freeze the
    readout and no test would fail."""
    api, icon, window = _FakeApi(), _FakeIcon(), _FakeWindow()

    poll_tick(_FakeWatcher([]), api, icon, window, PollState())

    assert api.status_pushes == 1


def test_a_failing_status_push_does_not_skip_the_poll():
    """The status push and the watcher poll are separate failure domains: a
    broken status push must not be miscounted as a failing tick, and must
    not skip poll_once for that tick."""

    class _RaisingApi(_FakeApi):
        def _push_eve_status(self):
            self.status_pushes += 1
            raise RuntimeError("status push exploded")

    api = _RaisingApi()
    icon, window = _FakeIcon(), _FakeWindow()
    state = PollState()

    poll_tick(_FakeWatcher([Path("a.mkv")]), api, icon, window, state)

    assert api.status_pushes == 1
    assert api.rows_calls == [{Path("a.mkv")}]
    assert state.consecutive_failures == 0


def test_a_first_run_with_no_folder_no_longer_asks(monkeypatch):
    """The ask fallback is GONE: create_file_dialog is a method on a window
    and no window exists this early. None means "render the first-run
    route", not "give up"."""
    from wingman import __main__ as main_mod

    monkeypatch.setattr(main_mod.obsconfig, "find_recording_dir", lambda: None)
    assert main_mod.resolve_recording_dir({}) is None
    assert "ask" not in main_mod.resolve_recording_dir.__code__.co_varnames
