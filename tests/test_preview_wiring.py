"""Wiring, with the host faked. What must hold: the subsystem is lazy,
enable/disable is idempotent, and shutdown always tears it down.

make_api is the existing helper in tests/test_api.py -- imported, not
redefined. It takes tmp_path positionally and forwards **kwargs to Api().
"""
from tests.test_api import make_api


class FakeHost:
    def __init__(self):
        self.started = self.stopped = 0
        self.flushed = 0

    def start(self):
        self.started += 1

    def stop(self, timeout=5.0):
        self.stopped += 1

    @property
    def is_running(self):
        return self.started > self.stopped


def test_disabled_at_startup_never_starts_the_thread(tmp_path):
    """A user who never touches EVE previews must not pay a thread, a
    700ms sweep and a foreground hook for a feature they have off."""
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"enabled": False}
    api.start_previews_if_enabled()
    assert host.started == 0


def test_enabled_at_startup_starts_it(tmp_path):
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"enabled": True}
    api.start_previews_if_enabled()
    assert host.started == 1


def test_enabling_starts_it_and_disabling_stops_it(tmp_path):
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"enabled": False}
    api.set_preview_enabled(True)
    assert host.started == 1
    api.set_preview_enabled(False)
    assert host.stopped == 1


def test_enabling_twice_does_not_start_two_threads(tmp_path):
    """Enable clicked twice must not leave an orphan pump owning HWNDs
    that nothing will ever tear down."""
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"enabled": False}
    api.set_preview_enabled(True)
    api.set_preview_enabled(True)
    assert host.started == 1


def test_the_choice_is_persisted(tmp_path):
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"enabled": False}
    api.set_preview_enabled(True)
    assert api._state.settings["preview"]["enabled"] is True


def test_shutdown_stops_the_host_even_when_enabled(tmp_path):
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"enabled": True}
    api.start_previews_if_enabled()
    api.shutdown_previews()
    assert host.stopped == 1


def test_shutdown_without_a_host_is_a_no_op(tmp_path):
    """Off-Windows and in tests there is no host at all; shutdown runs on
    every exit path and must never be the thing that raises."""
    api = make_api(tmp_path)
    api.shutdown_previews()


def test_build_preview_host_returns_none_off_windows(monkeypatch):
    from obs_youtube_uploader import __main__ as main_mod
    monkeypatch.setattr(main_mod.sys, "platform", "linux")
    assert main_mod.build_preview_host(object()) is None


def test_build_preview_host_body_is_exercised(monkeypatch, tmp_path):
    """The sys.platform guard means this function's body never runs in CI,
    so a NameError or a wrong import inside it would ship silently and
    only fail on a user's Windows machine. Force the body to run.

    Known limit, established by deliberately reintroducing the bug: this
    only catches names resolved EAGERLY. An earlier version passed
    `save_settings=lambda data: settings.save(data)` -- wrong module alias,
    but a lambda body is not executed here, so this test went green and the
    failure would have surfaced on a user's machine the first time a
    preview moved. Callbacks built here should therefore be bound method
    references, not lambdas wrapping them.
    """
    from types import SimpleNamespace

    from obs_youtube_uploader import __main__ as main_mod

    monkeypatch.setattr(main_mod.sys, "platform", "win32")
    state = SimpleNamespace(settings={"preview": {
        "enabled": False, "width": 320, "height": 210, "layouts": {}}})
    host = main_mod.build_preview_host(state)
    assert host is not None
    assert not host.is_running     # constructed, never started


def test_build_preview_host_survives_a_broken_subsystem(monkeypatch):
    """Previews are secondary to the upload workflow; failing to build
    them must not stop Wingman launching."""
    from obs_youtube_uploader import __main__ as main_mod

    monkeypatch.setattr(main_mod.sys, "platform", "win32")
    assert main_mod.build_preview_host(object()) is None


def test_set_preview_enabled_returns_truthy_on_success(tmp_path):
    """WM.send resolves to null on a bridge failure and cannot tell that
    apart from a method that returned None, so the page would revert the
    checkbox on every successful toggle (settings.js:181 records the same
    trap for save_settings)."""
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"enabled": False}
    assert api.set_preview_enabled(True) is True


def test_main_actually_calls_start_previews_if_enabled():
    """The method existed, was tested directly, and nothing called it --
    so previews never started at launch however the setting was set. A
    unit test on the method cannot catch that; only reading main() can.
    """
    import inspect

    from obs_youtube_uploader import __main__ as main_mod

    src = inspect.getsource(main_mod.main)
    assert "start_previews_if_enabled()" in src


def test_main_tears_previews_down():
    import inspect

    from obs_youtube_uploader import __main__ as main_mod

    src = inspect.getsource(main_mod.main)
    assert "shutdown_previews()" in src
