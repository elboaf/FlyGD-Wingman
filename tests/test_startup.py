"""main()'s startup ORDERING -- the property no single module owns.

main() had no test at all, which is how a `_push` on the main thread
before `webview.start()` survived every per-task review. pywebview wraps
`evaluate_js` in `event.wait(20)` on `_pywebviewready`, an event that
cannot be set until start() has run and the page has loaded. So any push
issued before run() blocks the main thread for the full twenty seconds,
raises, gets swallowed, and delivers nothing -- twenty seconds of
invisible window, and the push lost anyway.

These tests assert the sequence, not the timing: nothing may reach the
page before run() is entered, and the work that used to run early must
still run automatically.
"""
import threading
from types import SimpleNamespace

import pytest

from obs_youtube_uploader import __main__ as main_mod
from tests import fakes


class FakeIcon:
    def __init__(self):
        self.stopped = False

    def run(self):
        pass

    def stop(self):
        self.stopped = True

    def notify(self, *a, **kw):
        pass


@pytest.fixture
def startup(monkeypatch, tmp_path):
    """Run main() with every side effect stubbed, recording the sequence.

    Only the ordering is under test, so the tray, the preflight, the log
    file and the single-instance mutex are all replaced. `window_mod.run`
    stands in for `webview.start`: it records that the GUI loop began and
    then calls the `func` it was handed, exactly as pywebview does on its
    own thread once the loop is up.
    """
    order = []
    captured = {}

    monkeypatch.setattr(main_mod, "set_dpi_awareness", lambda: None)
    monkeypatch.setattr(main_mod, "acquire_single_instance", lambda: object())
    monkeypatch.setattr(main_mod.paths, "ensure_dirs", lambda: None)
    monkeypatch.setattr(main_mod, "configure_logging", lambda: None)
    monkeypatch.setattr(main_mod.stitch, "sweep_orphans", lambda d: None)
    monkeypatch.setattr(main_mod.paths, "tmp_dir", lambda: tmp_path)
    monkeypatch.setattr(main_mod.paths, "resolve_binary", lambda name: None)
    monkeypatch.setattr(main_mod.settings_mod, "load", lambda path=None: {})
    monkeypatch.setattr(main_mod.preflight, "require_webview2", lambda: True)
    # None keeps main() off the watcher path: no Scheduler, no polling
    # thread, nothing to tear down. The first-run push is deferred onto a
    # daemon timer that outlives the test harmlessly.
    monkeypatch.setattr(main_mod, "resolve_recording_dir", lambda cfg: None)
    monkeypatch.setattr(main_mod, "build_tray",
                        lambda on_open, on_quit: FakeIcon())

    def fake_create(api):
        # The real create() hands the api its window; the ordering test
        # depends on that wiring existing, because refresh_auth pushes.
        api._window = fakes.FakeWindow()
        captured["api"] = api
        order.append("create_window")
        return SimpleNamespace(show=lambda: None, destroy=lambda: None)

    monkeypatch.setattr(main_mod.window_mod, "create", fake_create)

    def fake_run(func=None):
        order.append("run")
        captured["func"] = func
        if func is not None:
            # pywebview starts `func` on its own thread. Joining it here
            # keeps the assertions deterministic without pretending the
            # call is synchronous.
            thread = threading.Thread(target=func)
            thread.start()
            thread.join(timeout=5)

    monkeypatch.setattr(main_mod.window_mod, "run", fake_run)

    def spy_refresh_auth(self):
        order.append("refresh_auth")

    monkeypatch.setattr(main_mod.api_mod.Api, "refresh_auth", spy_refresh_auth)

    return SimpleNamespace(order=order, captured=captured)


def test_nothing_touches_the_page_before_the_gui_loop_starts(startup):
    """The whole of C2 in one assertion.

    `refresh_auth` pushes "connecting" synchronously before it spawns its
    worker. Called on the main thread ahead of run(), that push waits out
    pywebview's twenty-second readiness timeout, throws, is swallowed by
    _push's bare except -- and the window does not appear until it is
    over. Whatever mechanism is used, run() must come first.
    """
    assert main_mod.main() == 0
    order = startup.order
    assert "refresh_auth" in order, "the auth check must still run at startup"
    assert order.index("run") < order.index("refresh_auth"), (
        f"refresh_auth ran before the GUI loop: {order}")


def test_the_auth_check_is_handed_to_the_gui_loop_to_run(startup):
    """It must be deferred by giving run() the work, not by a fixed sleep:
    a delay long enough to be safe is a delay the user watches."""
    assert main_mod.main() == 0
    func = startup.captured["func"]
    api = startup.captured["api"]
    assert func is not None, "run() was given no startup function"
    assert func == api.refresh_auth
