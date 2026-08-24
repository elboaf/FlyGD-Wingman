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


def test_set_preview_enabled_returns_truthy_on_success(tmp_path, monkeypatch):
    """WM.send resolves to null on a bridge failure and cannot tell that
    apart from a method that returned None, so the page would revert the
    checkbox on every successful toggle (settings.js:181 records the same
    trap for save_settings)."""
    _no_disk(monkeypatch)
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


def test_the_preview_card_lives_in_its_own_route():
    """It was first added to the Bookmarks route, between 'EVE bookmark
    hotkeys' and 'Root' -- under the wrong feature, and splitting the
    bookmarks flow in half. Previews get their own destination: the
    deferred work (labels, opacity, size, hotkeys, cycle groups, alerts)
    is roughly the volume of the Bookmarks tab.
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1]
    lines = (root / "obs_youtube_uploader" / "web"
             / "index.html").read_text(encoding="utf-8").splitlines()

    starts = {}
    for i, line in enumerate(lines):
        m = re.search(r'id="route-(\w+)"', line)
        if m:
            starts[m.group(1)] = i
    card = next(i for i, line in enumerate(lines)
                if "EVE client previews" in line)
    ordered = sorted(starts.items(), key=lambda kv: kv[1])
    owner = [name for name, at in ordered if at < card][-1]
    assert owner == "previews", f"the preview card is in route-{owner}"


def test_the_previews_route_is_registered_and_reachable():
    """A route div with no entry in app.js's routes map never shows, and a
    nav button with no matching div throws on click. Both halves have to
    exist, and nothing else in the suite reads the page."""
    import pathlib

    web = pathlib.Path(__file__).resolve().parents[1] / "obs_youtube_uploader" / "web"
    html = (web / "index.html").read_text(encoding="utf-8")
    app = (web / "app.js").read_text(encoding="utf-8")

    assert 'id="route-previews"' in html
    assert 'data-route="previews"' in html
    assert "previews: 'route-previews'" in app
    # Peer destination, so the gear returns here rather than to Uploader.
    assert "name === 'previews'" in app


def test_an_unchanged_toggle_still_reports_success(tmp_path):
    """The no-op short-circuit is a SUCCESS path. Returning None gave it
    exactly the failure the truthy return exists to prevent: WM.send
    resolves to null on a bridge error, so the page could not tell a
    redundant toggle from a broken one and reverted the checkbox."""
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"enabled": True}
    assert api.set_preview_enabled(True) is True
    assert host.started == 0        # still short-circuited, not restarted


class FakeClientLayouts:
    def __init__(self):
        self.started = self.stopped = 0
        self.saves = self.restores = 0

    def save_now(self):
        self.saves += 1
        return {"saved": 3, "persisted": True}

    def restore_now(self):
        self.restores += 1
        return {"restored": 2, "skipped": 1}

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1


def _no_disk(monkeypatch):
    """set_restore_clients_on_launch persists through settings.update, and
    the real save()/update() write to paths.settings_file() -- the user's
    actual file. Stub both so no test can reach it."""
    from obs_youtube_uploader.ui import api as api_mod
    writes = []
    monkeypatch.setattr(api_mod.settings_mod, "save", writes.append)

    def fake_update(read, mutate, path=None):
        doc = read()
        mutate(doc)
        writes.append(doc)

    monkeypatch.setattr(api_mod.settings_mod, "update", fake_update)
    return writes


def test_save_client_layout_passes_the_count_through(tmp_path):
    manager = FakeClientLayouts()
    api = make_api(tmp_path, client_layouts=manager)
    assert api.save_client_layout() == {"saved": 3, "persisted": True}
    assert manager.saves == 1


def test_restore_client_layout_passes_the_counts_through(tmp_path):
    manager = FakeClientLayouts()
    api = make_api(tmp_path, client_layouts=manager)
    assert api.restore_client_layout() == {"restored": 2, "skipped": 1}


def test_the_client_layout_endpoints_are_no_ops_without_a_manager(
        tmp_path, monkeypatch):
    """None off Windows and in most tests, like preview_host.

    _no_disk is not optional here: set_restore_clients_on_launch persists
    even with no manager, and the real save() writes to
    paths.settings_file() -- the developer's actual settings file.
    """
    _no_disk(monkeypatch)
    api = make_api(tmp_path)
    assert api.save_client_layout() == {"saved": 0, "persisted": True}
    assert api.restore_client_layout() == {"restored": 0, "skipped": 0}
    assert api.set_restore_clients_on_launch(True) is True
    api.shutdown_client_layouts()
    api.start_client_layouts_if_enabled()


def test_enabling_restore_on_launch_starts_the_watcher(tmp_path, monkeypatch):
    writes = _no_disk(monkeypatch)
    manager = FakeClientLayouts()
    api = make_api(tmp_path, client_layouts=manager)
    api._state.settings["preview"] = {}
    assert api.set_restore_clients_on_launch(True) is True
    assert manager.started == 1
    assert api._state.settings["preview"]["restore_clients_on_launch"] is True
    assert len(writes) == 1


def test_disabling_restore_on_launch_stops_the_watcher(tmp_path, monkeypatch):
    _no_disk(monkeypatch)
    manager = FakeClientLayouts()
    api = make_api(tmp_path, client_layouts=manager)
    api._state.settings["preview"] = {"restore_clients_on_launch": True}
    api.set_restore_clients_on_launch(False)
    assert manager.stopped == 1


def test_an_unwritable_settings_file_does_not_block_the_watcher(
        tmp_path, monkeypatch):
    """Same posture as set_preview_enabled: the feature still works."""
    from obs_youtube_uploader.ui import api as api_mod

    def boom(_read, _mutate, path=None):
        raise OSError("read-only")

    monkeypatch.setattr(api_mod.settings_mod, "update", boom)
    manager = FakeClientLayouts()
    api = make_api(tmp_path, client_layouts=manager)
    api._state.settings["preview"] = {}
    assert api.set_restore_clients_on_launch(True) is True
    assert manager.started == 1


def test_the_client_watcher_starts_on_launch_only_when_asked(tmp_path):
    manager = FakeClientLayouts()
    api = make_api(tmp_path, client_layouts=manager)
    api._state.settings["preview"] = {}
    api.start_client_layouts_if_enabled()
    assert manager.started == 0

    manager2 = FakeClientLayouts()
    api2 = make_api(tmp_path, client_layouts=manager2)
    api2._state.settings["preview"] = {"restore_clients_on_launch": True}
    api2.start_client_layouts_if_enabled()
    assert manager2.started == 1


def test_client_layout_shutdown_never_raises(tmp_path):
    """Runs on every exit path, like shutdown_previews."""
    class Exploding:
        def stop(self):
            raise RuntimeError("nope")

    make_api(tmp_path, client_layouts=Exploding()).shutdown_client_layouts()


def test_build_client_layout_manager_returns_none_off_windows(monkeypatch):
    """None elsewhere keeps every call site in api.py a plain no-op
    rather than a platform check."""
    from obs_youtube_uploader import __main__ as main_mod

    monkeypatch.setattr(main_mod.sys, "platform", "linux")
    assert main_mod.build_client_layout_manager(object()) is None


def test_build_client_layout_manager_body_is_exercised(monkeypatch):
    """The sys.platform guard means this body never runs in CI, so a
    NameError or wrong module alias inside it would ship silently and
    fail only on a user's Windows machine.

    Same known limit as build_preview_host's twin above: this catches
    only EAGERLY resolved names. A lambda body is not executed here, so
    collaborators must be bound method references (clientwin32.read_
    placement, settings_mod.update) rather than lambdas wrapping them.
    `screen` is the one deliberate closure, and it is not called here.
    """
    from types import SimpleNamespace

    from obs_youtube_uploader import __main__ as main_mod

    monkeypatch.setattr(main_mod.sys, "platform", "win32")
    state = SimpleNamespace(settings={"preview": {
        "restore_clients_on_launch": False, "client_layouts": {}}})
    manager = main_mod.build_client_layout_manager(state)
    assert manager is not None


def test_build_client_layout_manager_survives_a_broken_subsystem(monkeypatch):
    """Client layouts are secondary to the upload workflow; failing to
    build them must not stop Wingman launching.

    NOT the object() trick the preview twin uses. build_preview_host reads
    state.settings eagerly, so object() raises there; this builder reads it
    only inside a lambda, so object() would sail through and return a live
    manager. Break something the builder DOES touch eagerly instead:
    settings_mod.update is resolved when the kwargs are built.
    """
    from types import SimpleNamespace

    from obs_youtube_uploader import __main__ as main_mod

    monkeypatch.setattr(main_mod.sys, "platform", "win32")
    monkeypatch.setattr(main_mod, "settings_mod", SimpleNamespace())
    state = SimpleNamespace(settings={"preview": {}})
    assert main_mod.build_client_layout_manager(state) is None


def test_main_actually_starts_the_client_layout_watcher():
    """The preview twin of this test exists because the method was
    written, unit-tested, and never called -- so the feature silently did
    nothing at launch. Only reading main() catches that."""
    import inspect

    from obs_youtube_uploader import __main__ as main_mod

    assert "start_client_layouts_if_enabled()" in inspect.getsource(
        main_mod.main)


def test_main_tears_the_client_layout_watcher_down():
    import inspect

    from obs_youtube_uploader import __main__ as main_mod

    assert "shutdown_client_layouts()" in inspect.getsource(main_mod.main)


def test_the_client_window_card_lives_on_the_previews_route():
    """A second card, not more rows on the previews card: these controls
    move the CLIENT windows and are not about previews."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    html = (root / "obs_youtube_uploader" / "web"
            / "index.html").read_text(encoding="utf-8")
    route = html.split('id="route-previews"')[1].split('id="route-')[0]
    assert "EVE client windows" in route
    assert 'id="btn-save-client-layout"' in route
    assert 'id="btn-restore-client-layout"' in route
    assert 'id="client-restore-on-launch"' in route
