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

import logging
import sys
import threading
from types import SimpleNamespace

import pytest

from tests import fakes
from wingman import __main__ as main_mod


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
    # state_dir too, not just tmp_dir: main() now builds a real HotkeyEngine
    # and apply() writes an INI through it. Unpatched, running the suite
    # overwrites the developer's own eve_bookmark_helper.ini with blank
    # keybinds -- write_atomic creates the directory if absent, so it
    # succeeds silently rather than failing safe.
    monkeypatch.setattr(main_mod.paths, "state_dir", lambda: tmp_path)
    monkeypatch.setattr(main_mod.paths, "resolve_binary", lambda name: None)
    # Must include eve_bookmarks: settings.load() guarantees the section on
    # every path, and main() now relies on that when priming the hotkey
    # engine. A bare {} here would only ever have worked while nothing
    # depended on the invariant.
    monkeypatch.setattr(
        main_mod.settings_mod,
        "load",
        lambda path=None: {
            "eve_bookmarks": {"enabled": False, "keybinds": {}, "windows": {}}
        },
    )
    monkeypatch.setattr(main_mod.preflight, "require_webview2", lambda: True)
    # None keeps main() off the watcher path: no Scheduler, no polling
    # thread, nothing to tear down. The first-run push is deferred onto a
    # daemon timer that outlives the test harmlessly.
    monkeypatch.setattr(main_mod, "resolve_recording_dir", lambda cfg: None)

    def fake_build_tray(on_open, on_quit):
        captured["on_open"] = on_open
        captured["on_quit"] = on_quit
        return FakeIcon()

    monkeypatch.setattr(main_mod, "build_tray", fake_build_tray)

    class FakeMainWindow:
        def __init__(self):
            self.destroyed = 0

        def show(self):
            order.append("show_window")

        def destroy(self):
            self.destroyed += 1
            order.append("destroy_window")

    def fake_create(api, hidden=False):
        # The real create() hands the api its window; the ordering test
        # depends on that wiring existing, because refresh_auth pushes.
        api._window = fakes.FakeWindow()
        captured["api"] = api
        captured["hidden"] = hidden
        captured["window"] = FakeMainWindow()
        order.append("create_window")
        return captured["window"]

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
            assert not thread.is_alive(), "page-ready callback did not finish"
        during_run = captured.get("during_run")
        if during_run is not None:
            during_run()

    monkeypatch.setattr(main_mod.window_mod, "run", fake_run)

    def spy_refresh_auth(self):
        order.append("refresh_auth")

    def spy_update_cleanup(self):
        order.append("update_cleanup")

    def spy_update_check(self, automatic):
        order.append("update_check")
        captured.setdefault("automatic_checks", []).append(automatic)
        return {}

    def spy_shutdown_updates(self):
        order.append("shutdown_updates")

    def spy_shutdown_previews(self):
        order.append("shutdown_previews")

    def spy_shutdown_skills(self):
        order.append("shutdown_skills")

    monkeypatch.setattr(main_mod.api_mod.Api, "refresh_auth", spy_refresh_auth)
    monkeypatch.setattr(
        main_mod.api_mod.Api,
        "_cleanup_update_staging_once",
        spy_update_cleanup,
        raising=False,
    )
    monkeypatch.setattr(main_mod.api_mod.Api, "_start_update_check", spy_update_check)
    monkeypatch.setattr(
        main_mod.api_mod.Api,
        "shutdown_updates",
        spy_shutdown_updates,
        raising=False,
    )
    monkeypatch.setattr(
        main_mod.api_mod.Api, "shutdown_previews", spy_shutdown_previews
    )
    monkeypatch.setattr(main_mod.api_mod.Api, "shutdown_skills", spy_shutdown_skills)

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
    assert "update_cleanup" in order, "stale updater staging must be cleaned at startup"
    assert "update_check" in order, "the update check must run at startup"
    assert order.index("run") < order.index("refresh_auth")
    assert order.index("run") < order.index("update_cleanup")
    assert order.index("update_cleanup") < order.index("update_check"), (
        f"startup updater work ran out of order: {order}"
    )


def test_page_ready_work_is_handed_to_the_gui_loop_to_run(startup):
    """It must be deferred by giving run() the work, not by a fixed sleep:
    a delay long enough to be safe is a delay the user watches."""
    assert main_mod.main() == 0
    func = startup.captured["func"]
    api = startup.captured["api"]
    assert func is not None, "run() was given no startup function"
    assert func == api._page_ready
    assert startup.captured["automatic_checks"] == [True]


# --- shared orderly shutdown -----------------------------------------------


def test_tray_quit_claims_then_runs_window_destruction_once(startup, monkeypatch):
    claims = []

    def claim(self):
        claims.append(True)
        return True

    monkeypatch.setattr(main_mod.api_mod.Api, "_claim_quit", claim)

    def during_run():
        startup.captured["on_quit"]()
        startup.captured["on_quit"]()

    startup.captured["during_run"] = during_run

    assert main_mod.main() == 0
    assert claims == [True, True]
    assert startup.captured["window"].destroyed == 1


def test_update_shutdown_callback_is_idempotent_and_destroys_sigbar_first(startup):
    events = startup.order

    class FakeSigBar:
        def destroy(self):
            events.append("destroy_sigbar")

    def during_run():
        api = startup.captured["api"]
        api._sigbar_window = FakeSigBar()
        assert callable(api._request_shutdown)
        api._request_shutdown()
        api._request_shutdown()

    startup.captured["during_run"] = during_run

    assert main_mod.main() == 0
    assert startup.captured["window"].destroyed == 1
    assert events.index("destroy_sigbar") < events.index("destroy_window")


def test_create_finishing_after_shutdown_starts_is_seen_and_destroyed(
    startup, monkeypatch
):
    from wingman.ui import sigbar

    create_entered = threading.Event()
    shutdown_waiting = threading.Event()
    release_create = threading.Event()

    class ObservedLock:
        """Signal when shutdown reaches the lock held by create()."""

        def __init__(self):
            self._lock = threading.RLock()

        def __enter__(self):
            if not self._lock.acquire(blocking=False):
                shutdown_waiting.set()
                self._lock.acquire()
            return self

        def __exit__(self, *args):
            self._lock.release()

    class FakeSigBar:
        def __init__(self):
            self.destroyed = 0

        def destroy(self):
            self.destroyed += 1

    bar = FakeSigBar()

    def create_window(*args, **kwargs):
        create_entered.set()
        assert release_create.wait(timeout=2)
        return bar

    monkeypatch.setitem(
        sys.modules, "webview", SimpleNamespace(create_window=create_window)
    )

    def during_run():
        api = startup.captured["api"]
        api._state.settings["sig_bar"] = {"enabled": True, "x": 1, "y": 2}
        api._sigbar_lifecycle_lock = ObservedLock()
        creator = threading.Thread(target=lambda: sigbar.create(api, hidden=True))
        creator.start()
        assert create_entered.wait(timeout=2)

        shutdown = threading.Thread(target=api._request_shutdown)
        shutdown.start()
        assert shutdown_waiting.wait(timeout=2)
        release_create.set()
        creator.join(timeout=2)
        shutdown.join(timeout=2)
        assert not creator.is_alive()
        assert not shutdown.is_alive()

    startup.captured["during_run"] = during_run

    assert main_mod.main() == 0
    assert bar.destroyed == 1
    assert startup.captured["api"]._sigbar_window is None


def test_shutdown_before_toggle_refuses_late_sigbar_creation(startup, monkeypatch):
    from wingman.ui import sigbar

    create_calls = []

    def create_after_shutdown(*args, **kwargs):
        create_calls.append(True)
        return SimpleNamespace(show=lambda: None)

    monkeypatch.setattr(sigbar, "create", create_after_shutdown)

    def during_run():
        api = startup.captured["api"]
        api._request_shutdown()
        api.toggle_sig_bar(True)

    startup.captured["during_run"] = during_run

    assert main_mod.main() == 0
    assert create_calls == []
    assert startup.captured["api"]._sigbar_window is None


def test_delayed_reveal_does_not_show_a_bar_destroyed_by_shutdown(startup, monkeypatch):
    from wingman.ui import sigbar

    reveals = []

    class FakeTimer:
        def __init__(self, delay, callback):
            reveals.append(callback)

        def start(self):
            pass

    class FakeSigBar:
        def __init__(self):
            self.destroyed = 0
            self.shown = 0

        def destroy(self):
            self.destroyed += 1

        def show(self):
            self.shown += 1

    bar = FakeSigBar()

    def create(inner, hidden=True):
        inner._sigbar_window = bar
        return bar

    monkeypatch.setattr(sigbar.threading, "Timer", FakeTimer)
    monkeypatch.setattr(sigbar, "create", create)

    def during_run():
        api = startup.captured["api"]
        api._state.settings["sig_bar"] = {"enabled": True, "x": 1, "y": 2}
        sigbar.restore(api)
        assert len(reveals) == 1
        api._request_shutdown()
        reveals[0]()

    startup.captured["during_run"] = during_run

    assert main_mod.main() == 0
    assert bar.destroyed == 1
    assert bar.shown == 0


def test_shutdown_retries_only_the_sigbar_after_its_destroy_fails(startup, caplog):
    attempts = []

    class FlakySigBar:
        def destroy(self):
            attempts.append("sigbar")
            if len(attempts) == 1:
                raise RuntimeError("sigbar destroy failed")

    def during_run():
        api = startup.captured["api"]
        api._sigbar_window = FlakySigBar()
        api._request_shutdown()
        api._request_shutdown()

    startup.captured["during_run"] = during_run

    with caplog.at_level(logging.ERROR, logger=main_mod.__name__):
        assert main_mod.main() == 0

    assert attempts == ["sigbar", "sigbar"]
    assert startup.captured["window"].destroyed == 1
    assert startup.captured["api"]._sigbar_window is None
    assert "Sig bar window did not destroy cleanly" in caplog.text
    assert "sigbar destroy failed" in caplog.text


def test_shutdown_retries_only_main_after_its_destroy_fails(startup, caplog):
    main_attempts = []
    sigbar_attempts = []

    class FakeSigBar:
        def destroy(self):
            sigbar_attempts.append(True)

    def during_run():
        api = startup.captured["api"]
        window = startup.captured["window"]
        real_destroy = window.destroy

        def flaky_destroy():
            main_attempts.append(True)
            if len(main_attempts) == 1:
                raise RuntimeError("main destroy failed")
            real_destroy()

        window.destroy = flaky_destroy
        api._sigbar_window = FakeSigBar()
        api._request_shutdown()
        api._request_shutdown()

    startup.captured["during_run"] = during_run

    with caplog.at_level(logging.ERROR, logger=main_mod.__name__):
        assert main_mod.main() == 0

    assert sigbar_attempts == [True]
    assert main_attempts == [True, True]
    assert startup.captured["window"].destroyed == 1
    assert "Main window did not destroy cleanly" in caplog.text
    assert "main destroy failed" in caplog.text


def test_concurrent_quit_retries_a_failure_without_repeating_success(startup):
    first_main_attempt = threading.Event()
    release_failure = threading.Event()
    main_attempts = []
    sigbar_attempts = []

    class FakeSigBar:
        def destroy(self):
            sigbar_attempts.append(True)

    def during_run():
        api = startup.captured["api"]
        window = startup.captured["window"]
        real_destroy = window.destroy

        def flaky_destroy():
            main_attempts.append(True)
            if len(main_attempts) == 1:
                first_main_attempt.set()
                assert release_failure.wait(timeout=2)
                raise RuntimeError("first concurrent destroy failed")
            real_destroy()

        window.destroy = flaky_destroy
        api._sigbar_window = FakeSigBar()
        first = threading.Thread(target=startup.captured["on_quit"])
        second = threading.Thread(target=startup.captured["on_quit"])
        first.start()
        assert first_main_attempt.wait(timeout=2)
        second.start()
        release_failure.set()
        first.join(timeout=2)
        second.join(timeout=2)
        assert not first.is_alive()
        assert not second.is_alive()

    startup.captured["during_run"] = during_run

    assert main_mod.main() == 0
    assert sigbar_attempts == [True]
    assert main_attempts == [True, True]
    assert startup.captured["window"].destroyed == 1


def test_updater_cleanup_precedes_preview_and_skills_shutdown(startup):
    assert main_mod.main() == 0

    order = startup.order
    assert order.index("shutdown_updates") < order.index("shutdown_previews")
    assert order.index("shutdown_updates") < order.index("shutdown_skills")


# --- the login launch (M3) --------------------------------------------------


def test_a_normal_launch_shows_its_window_and_checks_once(startup, monkeypatch):
    """Everything except the login entry raises a window. A Start menu
    shortcut that silently did nothing visible would read as a crash."""
    monkeypatch.setattr(sys, "argv", ["wingman"])
    assert main_mod.main() == 0
    assert startup.captured["hidden"] is False
    assert startup.captured["automatic_checks"] == [True]


def test_the_hidden_flag_reaches_the_window_and_still_checks_once(startup, monkeypatch):
    """M3: autostart.command() registers `--hidden`, and this is the wiring
    that makes it mean anything. Read from argv rather than a setting --
    the flag describes how THIS process was started, which no stored value
    can know: the same binary opened from the Start menu a minute later
    must show its window."""
    monkeypatch.setattr(sys, "argv", ["wingman", "--hidden"])
    assert main_mod.main() == 0
    assert startup.captured["hidden"] is True
    assert startup.captured["automatic_checks"] == [True]


def test_an_unrecognised_argument_does_not_kill_a_windowed_launch(startup, monkeypatch):
    """Deliberately not argparse. It exits(2) with a usage message on any
    unknown argument, and in a windowed build with no console that is a
    launch which dies with nothing on screen and nothing in the log."""
    monkeypatch.setattr(sys, "argv", ["wingman", "--what-is-this"])
    assert main_mod.main() == 0
    assert startup.captured["hidden"] is False


def test_the_two_mutex_names_differ():
    """Collapsing these makes the app refuse to start, always.

    acquire_single_instance() creates both names in ONE process. If they
    are equal, the second CreateMutexW reports ERROR_ALREADY_EXISTS
    against our own handle, every launch returns None, and the app never
    opens -- on every machine, not just upgrades.
    """
    assert main_mod.MUTEX_NAME != main_mod.LEGACY_MUTEX_NAME


def test_a_running_3x_instance_blocks_startup(monkeypatch):
    """An upgrade can leave 3.x resident in the tray; Inno cannot close it.

    Two builds running at once both write settings.json, and save()
    projects the whole document from DEFAULTS -- so interleaved writers
    silently revert each other's keys (settings.py:543-548).
    """
    monkeypatch.setattr(main_mod.sys, "platform", "win32")
    tried = []

    def fake_create(name):
        tried.append(name)
        return 1, name == main_mod.LEGACY_MUTEX_NAME

    monkeypatch.setattr(main_mod, "_create_mutex", fake_create)

    assert main_mod.acquire_single_instance() is None
    assert tried == [main_mod.LEGACY_MUTEX_NAME], (
        "the legacy name must be tested FIRST and short-circuit"
    )


def test_both_names_are_held_when_nothing_else_is_running(monkeypatch):
    """Holding the legacy name is what stops a 3.x launched LATER."""
    monkeypatch.setattr(main_mod.sys, "platform", "win32")
    tried = []

    def fake_create(name):
        tried.append(name)
        return 7, False

    monkeypatch.setattr(main_mod, "_create_mutex", fake_create)

    assert main_mod.acquire_single_instance() == 7
    assert tried == [main_mod.LEGACY_MUTEX_NAME, main_mod.MUTEX_NAME]


def test_a_second_4x_instance_blocks_startup(monkeypatch):
    monkeypatch.setattr(main_mod.sys, "platform", "win32")

    def fake_create(name):
        return 1, name == main_mod.MUTEX_NAME

    monkeypatch.setattr(main_mod, "_create_mutex", fake_create)

    assert main_mod.acquire_single_instance() is None


def test_state_migration_runs_before_ensure_dirs(monkeypatch, tmp_path):
    """Ordering is the whole feature, and it is invisible to unit tests
    of migrate_state_dir() itself.

    ensure_dirs() creates state_dir(). If it runs first, migration finds an
    empty new directory, decides there is nothing to do, and strands the
    user's real state permanently. A green test_paths.py proves nothing
    about this.
    """
    order = []

    monkeypatch.setattr(main_mod, "set_dpi_awareness", lambda: None)
    monkeypatch.setattr(main_mod, "acquire_single_instance", lambda: object())
    monkeypatch.setattr(
        main_mod.paths, "migrate_state_dir", lambda: order.append("migrate") or "ok"
    )
    monkeypatch.setattr(
        main_mod.paths, "ensure_dirs", lambda: order.append("ensure_dirs")
    )
    monkeypatch.setattr(
        main_mod, "configure_logging", lambda: order.append("configure_logging")
    )
    monkeypatch.setattr(
        main_mod.stitch, "sweep_orphans", lambda d: (_ for _ in ()).throw(SystemExit)
    )
    monkeypatch.setattr(main_mod.paths, "tmp_dir", lambda: tmp_path)

    with pytest.raises(SystemExit):
        main_mod.main()

    assert order == ["migrate", "ensure_dirs", "configure_logging"]
