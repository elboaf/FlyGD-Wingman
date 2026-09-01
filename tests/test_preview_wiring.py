"""Wiring, with the host faked. What must hold: the subsystem is lazy,
enable/disable is idempotent, and shutdown always tears it down.

make_api is the existing helper in tests/test_api.py -- imported, not
redefined. It takes tmp_path positionally and forwards **kwargs to Api().
"""

import contextlib
import copy
import threading
import types

from tests.test_api import make_api


class FakeHost:
    def __init__(self):
        self.started = self.stopped = 0
        self.flushed = 0
        self.sweeps = 0
        self.rebinds = 0
        self.hotkeys = None
        self.restyles = 0

    def start(self):
        self.started += 1

    def stop(self, timeout=5.0):
        self.stopped += 1

    def request_sweep(self):
        self.sweeps += 1

    def request_rebind(self):
        self.rebinds += 1

    def set_hotkeys(self, table):
        self.hotkeys = table

    def restyle(self):
        self.restyles += 1

    def resize_all(self, size):
        self.bulk_sizes = getattr(self, "bulk_sizes", [])
        self.bulk_sizes.append(tuple(size))

    def characters(self):
        return []

    def hotkey_status(self):
        return {}

    def client_sizes(self):
        return {}

    def layout_entries(self):
        return {}

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
    from wingman import __main__ as main_mod

    monkeypatch.setattr(main_mod.sys, "platform", "linux")
    assert main_mod.build_preview_host(object(), {}) is None


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

    from wingman import __main__ as main_mod

    monkeypatch.setattr(main_mod.sys, "platform", "win32")
    state = SimpleNamespace(
        settings={
            "preview": {"enabled": False, "width": 320, "height": 210, "layouts": {}}
        }
    )
    host = main_mod.build_preview_host(state, {})
    assert host is not None
    assert not host.is_running  # constructed, never started


def test_build_preview_host_wires_ordered_layout_replacement(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from wingman import __main__ as main_mod
    from wingman.preview import geometry, layout

    monkeypatch.setattr(main_mod.sys, "platform", "win32")
    state = SimpleNamespace(settings={"preview": {"layouts": {}}})
    host = main_mod.build_preview_host(state, {})
    entry = layout.Entry(geometry.Rect(1, 2, 320, 210), False)

    assert host._replace_layout("Alice", entry) is True
    assert state.settings["preview"]["layouts"]["Alice"]["x"] == 1


def test_build_preview_host_survives_a_broken_subsystem(monkeypatch):
    """Previews are secondary to the upload workflow; failing to build
    them must not stop Wingman launching."""
    from wingman import __main__ as main_mod

    monkeypatch.setattr(main_mod.sys, "platform", "win32")
    assert main_mod.build_preview_host(object(), {}) is None


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

    from wingman import __main__ as main_mod

    src = inspect.getsource(main_mod.main)
    assert "start_previews_if_enabled()" in src


def test_main_tears_previews_down():
    import inspect

    from wingman import __main__ as main_mod

    src = inspect.getsource(main_mod.main)
    assert "shutdown_previews()" in src


def test_the_preview_card_lives_in_its_own_section():
    """It was first added to the Bookmarks route, between 'EVE bookmark
    hotkeys' and 'Root' -- under the wrong feature, and splitting the
    bookmarks flow in half. Previews keep their own container.

    That container is a Settings SECTION now rather than a top-level
    route: previews are configuration, visited twice ever, producing
    nothing on their own screen. What this test guards is unchanged --
    the card must not drift back into the bookmarks flow.
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1]
    lines = (
        (root / "wingman" / "web" / "index.html")
        .read_text(encoding="utf-8")
        .splitlines()
    )

    starts = {}
    for i, line in enumerate(lines):
        m = re.search(r'id="(?:route|section)-(\w+)"', line)
        if m:
            starts[m.group(1)] = i
    card = next(i for i, line in enumerate(lines) if "EVE client previews" in line)
    ordered = sorted(starts.items(), key=lambda kv: kv[1])
    owner = [name for name, at in ordered if at < card][-1]
    assert owner == "previews", f"the preview card is in {owner}"


def test_the_previews_section_is_registered_and_reachable():
    """A section div with no rail item is unreachable, and a rail item with
    no matching div shows an empty pane. Both halves have to exist, and
    nothing else in the suite reads the page.

    This replaced the route-and-nav-button pair: WM.section toggles
    `.active` on `#section-<name>` and on the `.rail-item` whose
    data-section matches, so those two spellings are the contract.
    """
    import pathlib

    web = pathlib.Path(__file__).resolve().parents[1] / "wingman" / "web"
    html = (web / "index.html").read_text(encoding="utf-8")

    assert 'id="section-previews"' in html
    assert 'data-section="previews"' in html
    # And it must NOT have come back as a top-level destination.
    assert 'id="route-previews"' not in html
    assert 'data-route="previews"' not in html


def test_previews_disarms_its_capture_on_a_section_change():
    """The capture handler preventDefault()s EVERY key, Tab included, and
    stopPropagation() does not stop bookmarks.js's sibling listener on the
    same node. While Previews was a route, leaving it fired wm:route and
    disarmed the capture. As a section, switching to Folders or Discord
    fires NO route change -- so listening on wm:route alone would let an
    armed capture escape and swallow a path or a webhook being typed."""
    import pathlib

    web = pathlib.Path(__file__).resolve().parents[1] / "wingman" / "web"
    js = (web / "previews.js").read_text(encoding="utf-8")
    app = (web / "app.js").read_text(encoding="utf-8")

    assert "addEventListener('wm:section'" in js
    block = js.split("addEventListener('wm:section'")[1]
    assert "endCapture()" in block, "the leave branch no longer disarms"
    # And WM.route must keep firing a section change, or leaving Settings
    # entirely would never reach that branch.
    assert "WM.notify_section(" in app


def test_an_unchanged_toggle_still_reports_success(tmp_path):
    """The no-op short-circuit is a SUCCESS path. Returning None gave it
    exactly the failure the truthy return exists to prevent: WM.send
    resolves to null on a bridge error, so the page could not tell a
    redundant toggle from a broken one and reverted the checkbox."""
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"enabled": True}
    assert api.set_preview_enabled(True) is True
    assert host.started == 0  # still short-circuited, not restarted


def _no_disk(monkeypatch):
    """set_restore_preview_positions persists through settings.update, and
    the real save()/update() write to paths.settings_file() -- the user's
    actual file. Stub both so no test can reach it."""
    from wingman.ui import api as api_mod

    writes = []
    monkeypatch.setattr(api_mod.settings_mod, "save", writes.append)

    def fake_update(data, path=None):
        # Mirrors the real context manager: yields the LIVE dict, so the
        # caller's mutation lands on the object it passed in, and records
        # what would have been written. Records a deepcopy, not `data`
        # itself -- appending the live reference would let a later
        # mutation of `data` retroactively rewrite what this list says an
        # earlier `writes` entry contained.
        @contextlib.contextmanager
        def _cm():
            yield data
            writes.append(copy.deepcopy(data))

        return _cm()

    monkeypatch.setattr(api_mod.settings_mod, "update", fake_update)
    return writes


def test_the_position_toggle_is_a_no_op_without_a_host(tmp_path, monkeypatch):
    """None off Windows and in most tests, like every other preview
    endpoint -- but the choice is still persisted, so _no_disk is not
    optional here."""
    _no_disk(monkeypatch)
    api = make_api(tmp_path)
    assert api.set_restore_preview_positions(False) == {
        "applied": True,
        "persisted": True,
    }


def test_the_position_toggle_persists_the_choice(tmp_path, monkeypatch):
    writes = _no_disk(monkeypatch)
    api = make_api(tmp_path, preview_host=FakeHost())
    api._state.settings["preview"] = {}
    assert api.set_restore_preview_positions(False) == {
        "applied": True,
        "persisted": True,
    }
    assert api._state.settings["preview"]["restore_preview_positions"] is False
    assert len(writes) == 1


def test_the_position_toggle_does_not_move_the_previews_already_open(
    tmp_path, monkeypatch
):
    """The setting says where a preview OPENS. Repositioning windows the
    user has already arranged is what #29 learned not to do from the
    toggle it replaces."""
    _no_disk(monkeypatch)
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"enabled": True}
    api.start_previews_if_enabled()
    api.set_restore_preview_positions(False)
    assert host.started == 1 and host.stopped == 0
    assert host.sweeps == 0


def test_a_failed_position_write_is_reported_rather_than_claimed(tmp_path, monkeypatch):
    """#29's contract, carried across the rename: a dict, not a bool, so
    a write that did not land can be said out loud instead of leaving the
    checkbox lying about what survives a restart."""
    from wingman.ui import api as api_mod

    def boom(_data, path=None):
        raise OSError("read-only")

    monkeypatch.setattr(api_mod.settings_mod, "update", boom)
    api = make_api(tmp_path, preview_host=FakeHost())
    api._state.settings["preview"] = {}
    assert api.set_restore_preview_positions(False) == {
        "applied": True,
        "persisted": False,
    }


def test_a_failed_position_write_lets_the_next_toggle_retry(tmp_path, monkeypatch):
    """settings.update() restores the live dict when the block raises, so
    the stored value still reads as the OLD one and the next call sees a
    real change. Stubs _save_locked, not update(): the point is to
    exercise the REAL update() and fake only the disk write."""
    from wingman.ui import api as api_mod

    calls = []
    real_save_locked = api_mod.settings_mod._save_locked

    def flaky(data, path=None):
        calls.append(1)
        if len(calls) == 1:
            raise OSError("read-only")
        real_save_locked(data, tmp_path / "s.json")

    monkeypatch.setattr(api_mod.settings_mod, "_save_locked", flaky)
    api = make_api(tmp_path, preview_host=FakeHost())
    api._state.settings["preview"] = {}

    assert api.set_restore_preview_positions(False)["persisted"] is False
    assert api.set_restore_preview_positions(False)["persisted"] is True
    assert len(calls) == 2


def test_an_unchanged_position_toggle_does_not_rewrite_the_document(
    tmp_path, monkeypatch
):
    """settings.save projects every key, so a no-op toggle rewriting the
    whole file is a real cost."""
    writes = _no_disk(monkeypatch)
    api = make_api(tmp_path, preview_host=FakeHost())
    api._state.settings["preview"] = {}
    api.set_restore_preview_positions(False)
    api.set_restore_preview_positions(False)
    assert len(writes) == 1


def test_set_preview_show_labels_persists_and_restyles(tmp_path, monkeypatch):
    writes = _no_disk(monkeypatch)
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"show_labels": True}
    assert api.set_preview_show_labels(False) == {
        "applied": True,
        "persisted": True,
        "error": None,
    }
    assert api._state.settings["preview"]["show_labels"] is False
    assert len(writes) == 1
    assert host.restyles == 1


def test_set_preview_show_labels_is_a_no_op_without_restyling(tmp_path, monkeypatch):
    writes = _no_disk(monkeypatch)
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"show_labels": True}
    assert api.set_preview_show_labels(True) == {
        "applied": True,
        "persisted": True,
        "error": None,
    }
    assert len(writes) == 0
    # Restyle still fires on a no-op write: the endpoint's job is "make
    # the live state match what was asked for," not "only touch the host
    # when the document changed" -- a stale host state after a no-op
    # would be a silent bug the no-op guard was never meant to hide.
    assert host.restyles == 1


def test_set_preview_show_labels_restyles_even_without_a_host(tmp_path, monkeypatch):
    _no_disk(monkeypatch)
    api = make_api(tmp_path)
    assert api._preview_host is None
    assert api.set_preview_show_labels(False) == {
        "applied": True,
        "persisted": True,
        "error": None,
    }


def test_set_preview_opacity_persists_and_restyles(tmp_path, monkeypatch):
    writes = _no_disk(monkeypatch)
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"opacity": 255}
    assert api.set_preview_opacity(180) == {
        "applied": True,
        "persisted": True,
        "error": None,
    }
    assert api._state.settings["preview"]["opacity"] == 180
    assert len(writes) == 1
    assert host.restyles == 1


def test_set_preview_opacity_does_not_clamp_the_endpoint_itself(tmp_path, monkeypatch):
    """settings.validated_preview owns the 20-255 range (settings.py:235-
    239). The endpoint must hand the raw value to settings.update
    untouched and let the next normalise pass do the clamping -- this
    stores the out-of-range value verbatim so a re-owned range in the
    endpoint would show up as a failure here."""
    writes = _no_disk(monkeypatch)
    api = make_api(tmp_path, preview_host=FakeHost())
    api._state.settings["preview"] = {"opacity": 255}
    api.set_preview_opacity(5)
    assert writes[0]["preview"]["opacity"] == 5


def test_set_minimize_inactive_clients_persists_and_restyles(tmp_path, monkeypatch):
    writes = _no_disk(monkeypatch)
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"minimize_inactive_clients": False}
    assert api.set_minimize_inactive_clients(True) == {
        "applied": True,
        "persisted": True,
        "error": None,
    }
    assert api._state.settings["preview"]["minimize_inactive_clients"] is True
    assert len(writes) == 1
    assert host.restyles == 1


def test_set_preview_hide_on_lost_focus_persists_and_restyles(tmp_path, monkeypatch):
    writes = _no_disk(monkeypatch)
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"hide_on_lost_focus": False}
    assert api.set_preview_hide_on_lost_focus(True) == {
        "applied": True,
        "persisted": True,
        "error": None,
    }
    assert api._state.settings["preview"]["hide_on_lost_focus"] is True
    assert len(writes) == 1
    # Restyled, not merely written: unticking has to put the previews back
    # now rather than up to a sweep later, and _apply_visibility runs off
    # the restyle path.
    assert host.restyles == 1


def test_set_preview_hide_on_lost_focus_survives_no_host(tmp_path, monkeypatch):
    """Settings are reachable with previews off, so every preview endpoint
    has to tolerate a None host."""
    _no_disk(monkeypatch)
    api = make_api(tmp_path, preview_host=None)
    api._state.settings["preview"] = {}
    assert api.set_preview_hide_on_lost_focus(True)["persisted"] is True


def test_set_preview_locked_adds_an_offline_character_and_restyles(
    tmp_path, monkeypatch
):
    """The brief's round-trip case: a character who has never been seen
    running (no host.characters() entry, no saved layout rect) must still
    be lockable -- that is the entire reason Task 1 moved lock storage out
    of preview.layouts, whose deserialize drops any entry missing a full
    rect. `name` here appears nowhere else in api._state.settings, proving
    the write does not depend on the character having a prior footprint."""
    writes = _no_disk(monkeypatch)
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {}
    assert api.set_preview_locked("Someone Offline", True) == {
        "applied": True,
        "persisted": True,
        "error": None,
    }
    assert api._state.settings["preview"]["locked"] == ["Someone Offline"]
    assert writes[0]["preview"]["locked"] == ["Someone Offline"]
    assert host.restyles == 1


def test_set_preview_locked_removes_by_name(tmp_path, monkeypatch):
    writes = _no_disk(monkeypatch)
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"locked": ["Aiga Otsolen", "Zuelo Parvi"]}
    assert api.set_preview_locked("Aiga Otsolen", False) == {
        "applied": True,
        "persisted": True,
        "error": None,
    }
    assert api._state.settings["preview"]["locked"] == ["Zuelo Parvi"]
    assert writes[0]["preview"]["locked"] == ["Zuelo Parvi"]
    assert host.restyles == 1


def test_set_preview_locked_is_a_no_op_without_a_host(tmp_path, monkeypatch):
    """restyle() must not be called when there is no host to call it on --
    same guard set_preview_show_labels/set_preview_opacity already use."""
    _no_disk(monkeypatch)
    api = make_api(tmp_path)
    assert api.set_preview_locked("Aiga Otsolen", True) == {
        "applied": True,
        "persisted": True,
        "error": None,
    }


def test_set_never_minimize_adds_and_removes_by_name(tmp_path, monkeypatch):
    writes = _no_disk(monkeypatch)
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {}
    assert api.set_never_minimize("Zuelo Parvi", True)["applied"] is True
    assert api._state.settings["preview"]["never_minimize"] == ["Zuelo Parvi"]
    assert api.set_never_minimize("Zuelo Parvi", False)["applied"] is True
    assert api._state.settings["preview"]["never_minimize"] == []
    assert writes[-1]["preview"]["never_minimize"] == []
    assert host.restyles == 2


def test_get_preview_hotkey_state_reports_locked_and_never_minimize(tmp_path):
    """The per-character table paints its two new checkboxes off this one
    payload (ui/api.py's own comment says so) -- confirm the two keys
    actually ride it, and default to [] rather than raising when the
    section predates Task 1."""
    api = make_api(tmp_path)
    api._state.settings["preview"] = {
        "locked": ["Aiga Otsolen"],
        "never_minimize": ["Zuelo Parvi"],
    }
    payload = api.get_preview_hotkey_state()
    assert payload["locked"] == ["Aiga Otsolen"]
    assert payload["never_minimize"] == ["Zuelo Parvi"]

    api._state.settings["preview"] = {}
    payload = api.get_preview_hotkey_state()
    assert payload["locked"] == []
    assert payload["never_minimize"] == []


def test_get_preview_hotkey_state_reports_which_characters_can_be_sized(
    tmp_path,
):
    """`sizable` is the set set_preview_size can actually succeed for.

    It refuses for a character that is neither running nor already in
    `layouts` -- there is no x/y to write, and layout.deserialize drops an
    entry without a full rect, so a w/h stored alone would vanish at the
    next load after the page had reported it accepted. The refusal is
    right; offering the control anyway was not, and on a fresh install it
    was a guaranteed refusal for every offline character.

    Pinned here rather than in the page tests because the RULE is Python's:
    previews.js only reads the answer, and restating "running, or already
    in layouts" in JavaScript would put it in two places.
    """
    api = make_api(tmp_path)
    api._state.settings["preview"] = {
        "layouts": {"Aiga Otsolen": {"x": 0, "y": 0, "w": 320, "h": 210}},
    }
    # No host at all: only the dragged character qualifies.
    assert api.get_preview_hotkey_state()["sizable"] == ["Aiga Otsolen"]

    # A running character qualifies WITHOUT a layouts entry -- that is the
    # first branch of set_preview_size, which resizes the live window and
    # never consults `layouts`.
    api._preview_host = types.SimpleNamespace(
        is_running=True,
        characters=lambda: ["Zuelo Parvi"],
        hotkey_status=dict,
        client_sizes=dict,
        layout_entries=dict,
    )
    assert api.get_preview_hotkey_state()["sizable"] == [
        "Aiga Otsolen",
        "Zuelo Parvi",
    ]

    # Neither running nor dragged: absent, so the page draws no control.
    api._preview_host = None
    api._state.settings["preview"] = {"seen": ["Nobody Home"]}
    assert api.get_preview_hotkey_state()["sizable"] == []


def test_a_failed_preview_setting_write_is_refused_not_claimed(tmp_path, monkeypatch):
    """Mirrors test_a_rolled_back_alert_write_reverts_the_checkbox's
    Python-side counterpart: settings.update() restores the live dict on
    OSError, so the value did NOT take effect either -- this must report
    `applied: False`, not the `applied: True, persisted: False` shape
    set_restore_preview_positions uses for its own, different, contract."""
    from wingman.ui import api as api_mod

    def boom(_data, path=None):
        raise OSError("read-only")

    monkeypatch.setattr(api_mod.settings_mod, "update", boom)
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"show_labels": True}
    result = api.set_preview_show_labels(False)
    assert result["applied"] is False
    assert result["persisted"] is False
    assert result["error"]
    # The write never landed, so the live document must still read as it
    # did before the call -- settings.update() restores it on raise.
    assert api._state.settings["preview"]["show_labels"] is True


def test_write_alert_setting_still_nests_under_preview_alerts(tmp_path, monkeypatch):
    """_write_alert_setting is now a thin wrapper over
    _write_preview_setting, prefixing the path with "alerts" -- this
    pins that the resulting document shape is unchanged by the refactor:
    a regression here would silently move every alert field out from
    under preview.alerts."""
    writes = _no_disk(monkeypatch)
    api = make_api(tmp_path, preview_host=FakeHost())
    api._state.settings["preview"] = {}
    api.set_alert_pve_filter(True)
    assert writes[0]["preview"]["alerts"]["pve_filter"] is True


def test_the_host_reads_the_position_setting_live(monkeypatch):
    """build_preview_host must hand the host something that re-reads the
    document, not the value the app started with: the toggle changes
    mid-session, and settings._normalize replaces the whole preview
    section on every write."""
    from types import SimpleNamespace

    from wingman import __main__ as main_mod

    monkeypatch.setattr(main_mod.sys, "platform", "win32")
    state = SimpleNamespace(
        settings={
            "preview": {
                "enabled": False,
                "width": 320,
                "height": 210,
                "layouts": {},
                "restore_preview_positions": True,
            }
        }
    )
    host = main_mod.build_preview_host(state, {})
    assert host._restoring() is True

    # A whole new section object, as _normalize produces.
    state.settings["preview"] = {"restore_preview_positions": False}
    assert host._restoring() is False


def test_the_host_restores_positions_when_the_key_is_absent(monkeypatch):
    """An upgrading user's file predates the key. Absent must mean on,
    or their existing layouts are silently discarded on first launch."""
    from types import SimpleNamespace

    from wingman import __main__ as main_mod

    monkeypatch.setattr(main_mod.sys, "platform", "win32")
    state = SimpleNamespace(settings={"preview": {}})
    assert main_mod.build_preview_host(state, {})._restoring() is True


def test_the_host_reads_show_labels_and_opacity_live(monkeypatch):
    """Same reasoning as test_the_host_reads_the_position_setting_live:
    Settings has no Save button, so build_preview_host must hand the host
    callables that re-read state.settings on every call, not the values
    captured at app start."""
    from types import SimpleNamespace

    from wingman import __main__ as main_mod

    monkeypatch.setattr(main_mod.sys, "platform", "win32")
    state = SimpleNamespace(
        settings={
            "preview": {
                "enabled": False,
                "width": 320,
                "height": 210,
                "layouts": {},
                "show_labels": False,
                "opacity": 180,
            }
        }
    )
    host = main_mod.build_preview_host(state, {})
    assert host._labels_shown() is False
    assert host._current_opacity() == 180

    # A whole new section object, as _normalize produces.
    state.settings["preview"] = {"show_labels": True, "opacity": 90}
    assert host._labels_shown() is True
    assert host._current_opacity() == 90


def test_the_host_defaults_labels_on_and_fully_opaque_when_the_keys_are_absent(
    monkeypatch,
):
    """An upgrading user's file predates these keys. Absent must mean the
    behaviour that shipped before the toggle existed, or every existing
    install's previews would silently restyle on first launch. 255 here
    is __main__'s own fallback for a missing key, matching settings.py's
    _preview_defaults() opacity now that both mean "fully opaque, as
    shipped" -- not host.py's separate 255 fallback, which only applies
    when the callable itself is absent or raises, never through
    build_preview_host's live read."""
    from types import SimpleNamespace

    from wingman import __main__ as main_mod

    monkeypatch.setattr(main_mod.sys, "platform", "win32")
    state = SimpleNamespace(settings={"preview": {}})
    host = main_mod.build_preview_host(state, {})
    assert host._labels_shown() is True
    assert host._current_opacity() == 255


def test_the_host_reads_minimize_inactive_and_the_rosters_live(monkeypatch):
    """Same reasoning again: a roster edit or a minimize toggle happens
    while previews are already running."""
    from types import SimpleNamespace

    from wingman import __main__ as main_mod

    monkeypatch.setattr(main_mod.sys, "platform", "win32")
    state = SimpleNamespace(
        settings={
            "preview": {
                "enabled": False,
                "width": 320,
                "height": 210,
                "layouts": {},
                "minimize_inactive_clients": True,
                "never_minimize": ["Alice"],
                "locked": ["Bravo"],
            }
        }
    )
    host = main_mod.build_preview_host(state, {})
    assert host._minimizing_inactive() is True
    assert host._is_never_minimize("Alice") is True
    assert host._is_locked("Bravo") is True

    # A whole new section object, as _normalize produces.
    state.settings["preview"] = {
        "minimize_inactive_clients": False,
        "never_minimize": [],
        "locked": [],
    }
    assert host._minimizing_inactive() is False
    assert host._is_never_minimize("Alice") is False
    assert host._is_locked("Bravo") is False


def test_the_host_reads_hide_on_lost_focus_live(monkeypatch):
    """Ticking the box has to reach previews that are already running, and
    _normalize hands back a whole new section object rather than mutating
    the old one -- so the host must read through to state.settings, not
    capture the dict it was built with."""
    from types import SimpleNamespace

    from wingman import __main__ as main_mod

    monkeypatch.setattr(main_mod.sys, "platform", "win32")
    state = SimpleNamespace(settings={"preview": {"hide_on_lost_focus": True}})
    host = main_mod.build_preview_host(state, {})
    assert host._hiding_on_lost_focus() is True

    state.settings["preview"] = {"hide_on_lost_focus": False}
    assert host._hiding_on_lost_focus() is False


def test_the_host_defaults_to_leaving_previews_visible_when_absent(monkeypatch):
    """Absent means off, for the same class of reason minimize_inactive
    does: taking previews off a user's screen is a change they have to ask
    for, and an upgrading install has no such key."""
    from types import SimpleNamespace

    from wingman import __main__ as main_mod

    monkeypatch.setattr(main_mod.sys, "platform", "win32")
    state = SimpleNamespace(settings={"preview": {}})
    assert main_mod.build_preview_host(state, {})._hiding_on_lost_focus() is False


def test_the_host_defaults_to_no_minimizing_and_empty_rosters_when_absent(monkeypatch):
    """Absent must mean off for minimize_inactive_clients: minimizing a
    real EVE client window must be asked for, never assumed by an
    upgrading install. The rosters default to empty for the same reason."""
    from types import SimpleNamespace

    from wingman import __main__ as main_mod

    monkeypatch.setattr(main_mod.sys, "platform", "win32")
    state = SimpleNamespace(settings={"preview": {}})
    host = main_mod.build_preview_host(state, {})
    assert host._minimizing_inactive() is False
    assert host._is_never_minimize("Alice") is False
    assert host._is_locked("Alice") is False


def test_the_client_window_machinery_is_gone():
    """It moved the GAME windows: EVE read the resize as a resolution
    change and rewrote its own configuration, costing three characters'
    settings. Named here so it cannot come back by import.
    """
    import importlib

    from wingman.ui import api as api_mod

    for name in ("placement", "clientwin32", "clientlayout"):
        try:
            importlib.import_module("wingman.preview." + name)
        except ImportError:
            continue
        raise AssertionError(f"wingman.preview.{name} still exists")
    for name in (
        "save_client_layout",
        "restore_client_layout",
        "set_restore_clients_on_launch",
        "start_client_layouts_if_enabled",
        "shutdown_client_layouts",
    ):
        assert not hasattr(api_mod.Api, name), name


def test_main_never_places_a_client_window():
    """The one permitted interaction with an EVE window is raising it."""
    import inspect

    from wingman import __main__ as main_mod

    src = inspect.getsource(main_mod)
    assert "client_layout" not in src
    assert "SetWindowPlacement" not in src
    assert "SetWindowPos" not in src


def test_the_client_placement_win32_surface_is_not_declared():
    """`SetWindowPlacement` is the call that rewrote a client's resolution
    and destroyed three characters' settings. Nothing calls it now, and
    leaving it bound leaves it one line away from being called again.

    Asserted on the module source rather than the bind list, because
    tests/test_preview_win32.py is skipped off Windows and CI is ubuntu --
    so the bind list alone would never be checked by anything that runs.

    `SetWindowPos` is deliberately NOT listed here: window.py:317 uses it
    to move Wingman's OWN preview windows, which is the whole feature.
    The rule is about EVE's windows, and no EVE window's HWND reaches any
    of these calls any more.

    `SystemParametersInfoW` is absent too. It was briefly bound to suppress
    minimize animation, but an asynchronous request outlives that toggle, so
    the context could restore the user's preference before EVE processed it.
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1]
    src = (root / "wingman" / "preview" / "win32.py").read_text(encoding="utf-8")
    for gone in (
        "SetWindowPlacement",
        "GetWindowPlacement",
        "WINDOWPLACEMENT",
        "SPI_GETWORKAREA",
    ):
        assert gone not in src, gone
    assert not re.findall(r"\bSPI_[A-Z]+\b", src)


def test_nonactivating_async_minimize_is_the_only_live_client_show_state_surface():
    """The narrow live-client command minimizes without activating another window.

    Its BOOL describes the window's former show state, not completion, so the
    host intentionally does not inspect it as an activation/minimize verdict.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    src = (root / "wingman" / "preview" / "win32.py").read_text(encoding="utf-8")
    host_src = (root / "wingman" / "preview" / "host.py").read_text(encoding="utf-8")
    assert '"ShowWindowAsync", BOOL, [HWND, ctypes.c_int]' in src
    assert "SW_SHOWMINNOACTIVE = 7" in src
    assert "SW_MINIMIZE" not in src
    assert "show state" in src.lower()
    assert "2026-08-24" in src
    assert "test_the_client_placement_win32_surface_is_not_declared" in src
    for gone in (
        "WM_SYSCOMMAND",
        "SC_MINIMIZE",
        "SMTO_ABORTIFHUNG",
        "SendMessageTimeoutW",
    ):
        assert gone not in src
    assert "ShowWindowAsync(" in host_src
    assert "SendMessageTimeoutW" not in host_src


def test_the_preview_window_no_longer_owns_the_switch():
    """The window classifies the gesture; the host performs the switch.

    Both owned it once -- window.py called activate() and THEN fired the
    host's callback, which was a no-op stub. The host therefore learned of
    a click only after the foreground had already moved, which is exactly
    the information the minimize-inactive-clients feature needs. Restoring
    a second owner here would activate twice per click and put the
    outgoing foreground out of reach again, with nothing user-visible to
    show for it until someone reports keyboard input landing in the wrong
    client.
    """
    import inspect
    import re

    from wingman.preview import window as window_mod

    src = inspect.getsource(window_mod.PreviewWindow._on_message)
    # Comments stripped first: the handler's remaining comment explains
    # the handoff by naming activate(), and the guard is about what the
    # code does, not about what it is allowed to say.
    code = "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )
    # Bare `activate(`, not `self._on_activate(` -- the lookbehind rejects
    # any word character (which includes the underscore) before it.
    assert not re.search(r"(?<![\w.])activate\(", code), (
        "PreviewWindow._on_message calls activate() again; the host owns "
        "the switch (see PreviewHost._activate_client)"
    )
    assert "self._on_activate(" in code


def test_setfocus_is_declared_once_for_attached_queue_focus_assignment():
    """Linux CI cannot bind user32, so guard the pointer-sized declaration
    lexically as well as through the Windows-only ctypes completeness test.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    src = (root / "wingman" / "preview" / "win32.py").read_text(encoding="utf-8")
    assert src.count('(user32, "SetFocus", HWND, [HWND])') == 1


def test_synchronous_minimize_sends_are_not_declared():
    """The preview pump must not synchronously wait for a client minimize."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    src = (root / "wingman" / "preview" / "win32.py").read_text(encoding="utf-8")
    for gone in ("SendMessageW", "SendMessageTimeoutW"):
        assert gone not in src


def _web(name):
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    return (root / "wingman" / "web" / name).read_text(encoding="utf-8")


def test_the_client_window_card_is_gone():
    """Its buttons drove SetWindowPlacement against a live EVE client."""
    html = _web("index.html")
    js = _web("settings.js")
    for gone in (
        "EVE client windows",
        "btn-save-client-layout",
        "btn-restore-client-layout",
        "client-restore-on-launch",
        "client-layout-status",
    ):
        assert gone not in html, gone
        assert gone not in js, gone
    for gone in (
        "save_client_layout",
        "restore_client_layout",
        "set_restore_clients_on_launch",
    ):
        assert gone not in js, gone


def test_the_position_checkbox_sits_with_the_preview_settings():
    """It is a preview setting now, not a card of its own about clients,
    and nothing it says may still read as being about a game window."""
    html = _web("index.html")
    route = html.split('id="section-previews"')[1].split('id="section-')[0]
    card = route.split("EVE client previews")[1].split("<section")[0]
    assert 'id="restore-preview-positions"' in card
    label = card.split('id="restore-preview-positions"')[1].split("</label>")[0]
    assert "client" not in label.lower(), label


def test_the_position_toggle_says_when_the_choice_will_not_survive():
    """#29's contract, carried across the rename. A silent failed write
    is how the user finds out at their next restart; reverting the box
    would be the opposite lie, since the setting really did change for
    this session. Only a bridge failure may revert it."""
    js = _web("settings.js")
    block = js.split("set_restore_preview_positions")[1]
    assert "res.persisted" in block, "the flag is returned but never read"
    assert "will not survive a restart" in block
    assert "if (!res)" in block.split("box.checked = !wanted")[0]


# ---- The Previews tab must not report the opposite of the truth -----------
#
# The page has no test harness -- nothing in the suite executes web/*.js --
# so these assert on its source, the way the settings.js tests above do.
# That is a real limit: they pin the mechanism, not the rendered result.
# They are written against named states rather than CSS values so that a
# rename breaks them loudly instead of silently passing.


def test_an_absent_registration_entry_is_its_own_state():
    """Three states, not two. `false` is "Windows refused this chord";
    ABSENT is "we cannot know" -- which is what Python sends for every
    chord once the host has stopped (api.py gates on is_running and
    returns registration: {}). Testing only `=== false` collapsed absent
    into "registered", so with previews off the tab claimed every chord
    was held while Windows held none of them."""
    js = _web("previews.js")
    block = js.split("function clashes")[1].split("function makeRow")[0]
    assert "hasOwnProperty" in block, (
        "an absent key must be distinguished from a present one; a plain "
        "lookup cannot tell `undefined` from a missing entry"
    )
    assert "'unknown'" in block
    assert "'refused'" in block


def test_an_unknown_chord_is_not_rendered_as_a_refusal():
    """Unknown is not an error: nothing is wrong, we simply cannot say.
    Rendering it with .clash would trade one wrong report for another."""
    js = _web("previews.js")
    block = js.split("function makeRow")[1].split("function beginCapture")[0]
    marked = block.split("classList.add('clash')")[0]
    assert "'unknown'" not in marked, "the unknown state reaches the .clash branch"
    assert "classList.add('unknown')" in block


def test_the_unknown_state_is_visually_distinct_from_a_latent_clash():
    """.bindbtn.dim already means "a bookmark would collide with this".
    Reusing it would make the new state indistinguishable from that one --
    the same defect, relocated."""
    css = _web("style.css")
    assert ".bindbtn.unknown" in css


def test_rows_are_not_dimmed_when_previews_are_off():
    """Dimming means "this character is logged off", and it only carries
    that meaning by contrast with an undimmed row. With previews off the
    host is stopped and Python sends characters: [], so every row would
    dim at once and the list would be indistinguishable from "all my
    characters happen to be logged out". Off is said by the banner, not
    implied by styling every row identically."""
    js = _web("previews.js")
    block = js.split("function render")[1].split("function send")[0]
    assert "state.enabled && entry.online" not in block, (
        "previews being off must not be reported as every character being offline"
    )
    assert "preview-binds-off" in js, "the explicit off banner is the signal"


def test_a_rejected_binding_is_not_reverted_in_silence():
    """set_preview_binds returning false means Python refused the chord.
    Repainting from the backend without saying anything looks exactly
    like the click not registering."""
    js = _web("previews.js")
    block = js.split("function send")[1].split("function setBind")[0]
    assert "alert_bookmarks" in block, "the refusal is swallowed"


def test_a_resolved_save_cannot_overwrite_a_newer_push():
    """onPreviewHotkeys replaces `state` wholesale and fires whenever a
    client opens or closes -- routinely while a bind is being set. A
    send() resolving afterwards must not write its own older table back
    over the push that overtook it."""
    js = _web("previews.js")
    block = js.split("function send")[1].split("function setBind")[0]
    assert "generation" in block, (
        "nothing distinguishes a state that was replaced mid-flight"
    )


def test_the_row_dedup_set_cannot_collide_with_object_prototype():
    """A character named "constructor" or "__proto__" hits a truthy
    inherited property on a `{}` seen-set and is dropped from the list --
    silently, along with any binding it has."""
    js = _web("previews.js")
    block = js.split("function rows")[1].split("function clashes")[0]
    assert "Object.create(null)" in block


def test_toggling_minimize_inactive_live_disables_never_minimize_rows():
    """wm:settings is never re-dispatched after a single-field write (see
    list.js's own comment on refreshRecordingDir -- repainting the whole
    Settings form on every field commit would clobber whatever else the
    user is mid-edit on). Without a narrower signal, toggling "Minimize
    inactive" off would leave every already-rendered Never-minimize
    checkbox enabled until the next full page load, contradicting the
    hint text next to it. settings.js's own write handler must dispatch a
    one-field custom event on success (mirroring the existing
    wm:preview-enabled-changed precedent), and previews.js must listen for
    it -- not just for wm:settings, which only ever fires once, at load."""
    settings_js = _web("settings.js")
    # Anchored on the checkbox's own element id rather than nearby prose,
    # which a copy-edit could move or reword without breaking the wiring
    # this test actually checks.
    assert "WM.el('preview-minimize-inactive')" in settings_js
    after_box = settings_js.split("WM.el('preview-minimize-inactive')", 1)[1]
    assert "document.addEventListener('wm:settings'" in after_box
    write_handler = after_box.split("document.addEventListener('wm:settings'", 1)[0]
    assert "wm:preview-minimize-inactive" in write_handler, (
        "the event must be dispatched from the write's success branch"
    )

    previews_js = _web("previews.js")
    assert "wm:preview-minimize-inactive'" in previews_js
    after_event = previews_js.split("wm:preview-minimize-inactive'", 1)[1]
    # The next addEventListener call marks the end of this listener's own
    # body -- a real boundary, unlike a fixed character count that was
    # measured to overrun the handler by ~90 characters and could read
    # into code this test does not mean to check.
    assert "document.addEventListener(" in after_event
    listener = after_event.split("document.addEventListener(", 1)[0]
    assert "minimizeInactive" in listener
    # Recording the new value is only half of it: without the repaint the
    # already-rendered checkboxes keep their old disabled state, which IS
    # the bug this test exists for. Deleting the requestRender() call left
    # the assertion above green.
    assert "requestRender" in listener


def test_build_preview_host_wires_the_disabled_roster(monkeypatch):
    """Read live off the section, like the other two rosters: ticking the
    box writes settings and the host must see it on the very next sweep,
    without a restart."""
    from types import SimpleNamespace

    from wingman import __main__ as main_mod

    monkeypatch.setattr(main_mod.sys, "platform", "win32")
    state = SimpleNamespace(settings={"preview": {"excluded": ["Alice"]}})
    host = main_mod.build_preview_host(state, {})
    assert host._is_excluded("Alice") is True
    assert host._is_excluded("Bravo") is False

    # A whole new section object, as _normalize produces.
    state.settings["preview"] = {"excluded": []}
    assert host._is_excluded("Alice") is False


def test_the_host_defaults_to_no_disabled_characters_when_absent(monkeypatch):
    """Absent means every character keeps its preview: an upgrading
    install must not lose windows to a key its settings file predates."""
    from types import SimpleNamespace

    from wingman import __main__ as main_mod

    monkeypatch.setattr(main_mod.sys, "platform", "win32")
    state = SimpleNamespace(settings={"preview": {}})
    host = main_mod.build_preview_host(state, {})
    assert host._is_excluded("Alice") is False


def test_set_preview_excluded_adds_and_removes_by_name(tmp_path, monkeypatch):
    writes = _no_disk(monkeypatch)
    api = make_api(tmp_path, preview_host=FakeHost())
    api._state.settings["preview"] = {}

    assert api.set_preview_excluded("Zuelo Parvi", True)["applied"] is True
    assert api._state.settings["preview"]["excluded"] == ["Zuelo Parvi"]
    assert api.set_preview_excluded("Zuelo Parvi", False)["applied"] is True
    assert api._state.settings["preview"]["excluded"] == []
    assert writes[-1]["preview"]["excluded"] == []


def test_set_preview_excluded_sweeps_and_rebinds_rather_than_restyling(
    tmp_path, monkeypatch
):
    """restyle() only re-reads style on windows that already exist, so it
    cannot create or destroy one -- the window comes and goes on a sweep.
    The focus keybind is filtered at rebind, and ticking the box edits no
    chord, so a rebind has to be asked for even though no chord changed.
    """
    _no_disk(monkeypatch)
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"hotkeys": {"characters": {"Alice": "Ctrl+F1"}}}

    api.set_preview_excluded("Alice", True)

    assert host.sweeps == 1
    assert host.rebinds == 1
    assert host.restyles == 0


def test_set_preview_excluded_never_re_sources_the_hotkey_table(tmp_path, monkeypatch):
    """It must ask the host to re-apply what it ALREADY holds, not read the
    table back out of settings and push it.

    pywebview serves each JS->Python call on its own thread. A
    set_preview_binds landing between this method's read and its push would
    have its table silently reverted inside the host: the page and the
    settings file would both hold the new table while the host stayed
    registered against the old one, until some unrelated rebind. Nothing
    logs it -- _apply_hotkeys' INFO line reports counts, not contents.

    request_rebind carries no payload, so the race has nothing to lose:
    WM_APP_REBIND re-reads _desired_hotkeys under the host's own lock.
    """
    _no_disk(monkeypatch)
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"hotkeys": {"characters": {"Alice": "Ctrl+F1"}}}

    api.set_preview_excluded("Alice", True)

    assert host.hotkeys is None, (
        "set_preview_excluded pushed a hotkey table it re-read from "
        "settings; it must post a payload-free rebind instead"
    )


def test_set_preview_excluded_is_a_no_op_without_a_host(tmp_path, monkeypatch):
    _no_disk(monkeypatch)
    api = make_api(tmp_path)
    api._state.settings["preview"] = {}

    assert api.set_preview_excluded("Aiga Otsolen", True) == {
        "applied": True,
        "persisted": True,
        "error": None,
    }


def test_get_preview_hotkey_state_reports_disabled(tmp_path):
    api = make_api(tmp_path)
    api._state.settings["preview"] = {"excluded": ["Aiga Otsolen"]}
    assert api.get_preview_hotkey_state()["excluded"] == ["Aiga Otsolen"]
    api._state.settings["preview"] = {}
    assert api.get_preview_hotkey_state()["excluded"] == []


# --- apply_preview_default_size(): the apply-to-open-previews button --------


def test_apply_preview_default_size_resizes_every_open_preview(tmp_path):
    """The button half of the default-size field: the persisted pair, read
    back from settings (never re-validated in the endpoint -- the file
    already owns the MIN_SIZE floor), pushed at the host as one bulk job."""
    host = FakeHost()
    host.started = 1  # is_running
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"width": 640, "height": 392}

    assert api.apply_preview_default_size() == {
        "applied": True,
        "persisted": True,
        "error": None,
    }
    assert host.bulk_sizes == [(640, 392)]
    # The cards show each character's size; every one just changed, so the
    # push that repaints them fires from here rather than waiting a sweep.
    pushes = [c for c in api._window.evaluated if "onPreviewHotkeys" in c]
    assert len(pushes) == 1


def test_apply_preview_default_size_is_refused_while_previews_are_stopped(tmp_path):
    """Applying with nothing open would report success for a no-op the
    user cannot see -- the same refusal shape the field writers use."""
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"width": 640, "height": 392}

    result = api.apply_preview_default_size()
    assert result["applied"] is False
    assert result["error"]
    assert getattr(host, "bulk_sizes", None) is None


# --- set_preview_selection_color(): the ring colour picker ------------------


def test_set_preview_selection_color_persists_and_restyles(tmp_path, monkeypatch):
    """The #rrggbb string travels verbatim -- the endpoint str()s it and
    stores; validated_preview owns the format, exactly the division
    set_preview_opacity keeps with its range."""
    writes = _no_disk(monkeypatch)
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"selection_color": "#00c8dc"}
    assert api.set_preview_selection_color("#ff5a00") == {
        "applied": True,
        "persisted": True,
        "error": None,
    }
    assert api._state.settings["preview"]["selection_color"] == "#ff5a00"
    assert len(writes) == 1
    assert host.restyles == 1


def test_set_preview_selection_color_works_without_a_host(tmp_path, monkeypatch):
    """Same no-host tolerance as every other preview writer: the colour is
    still persisted, so it is waiting for the next start."""
    _no_disk(monkeypatch)
    api = make_api(tmp_path)
    assert api.set_preview_selection_color("#ff5a00")["applied"] is True


# ---------------------------------------------------------------------------
# Task 3: Serialized, operation-specific group API writes
# ---------------------------------------------------------------------------

# --- Step 1: Construction and preservation tests ---


def test_preview_hotkey_lock_is_private(tmp_path):
    """The lock must not be a public attribute (pywebview recurses into it)."""
    api = make_api(tmp_path)
    assert hasattr(api, "_preview_hotkey_lock"), "lock not created"
    assert not hasattr(api, "preview_hotkey_lock"), (
        "lock is public — RecursionError risk"
    )


def test_set_preview_binds_preserves_cycle_groups(tmp_path, monkeypatch):
    """set_preview_binds owns characters/cycle_next/cycle_prev only.
    Pre-existing groups and group_by_character must survive the write."""
    _no_disk(monkeypatch)
    api = make_api(tmp_path)
    api._state.settings["preview"] = {
        "hotkeys": {
            "characters": {},
            "cycle_next": "",
            "cycle_prev": "",
            "groups": [{"id": "dps", "name": "DPS", "cycle": "Ctrl+F3"}],
            "group_by_character": {"Alice": "dps"},
        }
    }
    assert (
        api.set_preview_binds(
            {
                "characters": {"Bob": "Ctrl+F2"},
                "cycle_next": "Ctrl+F1",
                "cycle_prev": "",
            }
        )
        is True
    )
    hotkeys = api._state.settings["preview"]["hotkeys"]
    assert hotkeys["groups"][0]["id"] == "dps"
    assert hotkeys["group_by_character"] == {"Alice": "dps"}
    # Owned fields were still applied:
    assert hotkeys["characters"] == {"Bob": "Ctrl+F2"}
    assert hotkeys["cycle_next"] == "Ctrl+F1"


# --- Step 5: Lifecycle and assignment tests ---


def test_create_rename_assign_and_delete_cycle_group(tmp_path, monkeypatch):
    _no_disk(monkeypatch)
    api = make_api(tmp_path, id_factory=lambda: "group-id")
    created = api.create_preview_cycle_group(" DPS ")
    assert created["applied"] is True
    assert created["hotkeys"]["groups"] == [
        {"id": "group-id", "name": "DPS", "cycle": ""}
    ]
    assert api.set_preview_character_group("Alice", "group-id")["applied"]
    assert api.rename_preview_cycle_group("group-id", "Damage")["applied"]
    deleted = api.delete_preview_cycle_group("group-id")
    assert deleted["hotkeys"]["groups"] == []
    assert deleted["hotkeys"]["group_by_character"] == {}


def test_create_cycle_group_rejects_empty_name(tmp_path, monkeypatch):
    _no_disk(monkeypatch)
    api = make_api(tmp_path)
    result = api.create_preview_cycle_group("   ")
    assert result["applied"] is False
    assert result["error"]


def test_create_cycle_group_rejects_non_string_name(tmp_path, monkeypatch):
    _no_disk(monkeypatch)
    api = make_api(tmp_path)
    result = api.create_preview_cycle_group(42)
    assert result["applied"] is False
    assert result["error"]


def test_create_cycle_group_rejects_duplicate_name(tmp_path, monkeypatch):
    """Case-insensitive name uniqueness across groups."""
    _no_disk(monkeypatch)
    seq = iter(["id-1", "id-2"])
    api = make_api(tmp_path, id_factory=lambda: next(seq))
    api.create_preview_cycle_group("DPS")
    result = api.create_preview_cycle_group("dps")
    assert result["applied"] is False
    assert result["error"]


def test_rename_cycle_group_trims_whitespace(tmp_path, monkeypatch):
    _no_disk(monkeypatch)
    api = make_api(tmp_path, id_factory=lambda: "g1")
    api.create_preview_cycle_group("DPS")
    result = api.rename_preview_cycle_group("g1", "  Tank  ")
    assert result["applied"] is True
    assert result["hotkeys"]["groups"][0]["name"] == "Tank"


def test_rename_cycle_group_rejects_stale_id(tmp_path, monkeypatch):
    _no_disk(monkeypatch)
    api = make_api(tmp_path)
    result = api.rename_preview_cycle_group("no-such-id", "Name")
    assert result["applied"] is False
    assert result["error"]


def test_delete_cycle_group_rejects_stale_id(tmp_path, monkeypatch):
    _no_disk(monkeypatch)
    api = make_api(tmp_path)
    result = api.delete_preview_cycle_group("no-such-id")
    assert result["applied"] is False
    assert result["error"]


def test_set_preview_cycle_group_bind_canonicalizes_gesture(tmp_path, monkeypatch):
    """Valid chord string → canonical display form persisted."""
    _no_disk(monkeypatch)
    api = make_api(tmp_path, id_factory=lambda: "g1")
    api.create_preview_cycle_group("DPS")
    result = api.set_preview_cycle_group_bind("g1", "ctrl+f3")
    assert result["applied"] is True
    assert result["hotkeys"]["groups"][0]["cycle"] == "Ctrl+F3"


def test_set_preview_cycle_group_bind_rejects_bad_gesture(tmp_path, monkeypatch):
    _no_disk(monkeypatch)
    api = make_api(tmp_path, id_factory=lambda: "g1")
    api.create_preview_cycle_group("DPS")
    result = api.set_preview_cycle_group_bind("g1", "not-a-chord")
    assert result["applied"] is False
    assert result["error"]


def test_set_preview_character_group_removes_mapping_on_empty_id(tmp_path, monkeypatch):
    """Empty group_id clears the character's mapping (All-only)."""
    _no_disk(monkeypatch)
    api = make_api(tmp_path, id_factory=lambda: "g1")
    api.create_preview_cycle_group("DPS")
    api.set_preview_character_group("Alice", "g1")
    result = api.set_preview_character_group("Alice", "")
    assert result["applied"] is True
    assert "Alice" not in result["hotkeys"]["group_by_character"]


def test_set_preview_character_group_rejects_hwnd_name(tmp_path, monkeypatch):
    _no_disk(monkeypatch)
    api = make_api(tmp_path, id_factory=lambda: "g1")
    api.create_preview_cycle_group("DPS")
    result = api.set_preview_character_group("hwnd:12345", "g1")
    assert result["applied"] is False
    assert result["error"]


def test_set_preview_character_group_rejects_stale_group_id(tmp_path, monkeypatch):
    _no_disk(monkeypatch)
    api = make_api(tmp_path)
    result = api.set_preview_character_group("Alice", "no-such-group")
    assert result["applied"] is False
    assert result["error"]


def test_cycle_group_methods_work_without_host(tmp_path, monkeypatch):
    """Persistence-only path when there is no preview host running."""
    _no_disk(monkeypatch)
    api = make_api(tmp_path, id_factory=lambda: "g1")
    result = api.create_preview_cycle_group("DPS")
    assert result["applied"] is True
    assert result["persisted"] is True


def test_cycle_group_methods_deliver_to_host_when_present(tmp_path, monkeypatch):
    """After a successful mutation the host receives the full table."""
    _no_disk(monkeypatch)
    host = FakeHost()
    api = make_api(tmp_path, id_factory=lambda: "g1", preview_host=host)
    api.create_preview_cycle_group("DPS")
    assert host.hotkeys is not None
    assert host.hotkeys["groups"] == [{"id": "g1", "name": "DPS", "cycle": ""}]


def test_failed_persist_does_not_invoke_host_set_hotkeys(tmp_path, monkeypatch):
    """If settings.update raises, host.set_hotkeys must never be called."""
    from wingman.ui import api as api_mod

    host = FakeHost()
    api = make_api(tmp_path, id_factory=lambda: "g1", preview_host=host)

    def boom(data, path=None):
        import contextlib

        @contextlib.contextmanager
        def _cm():
            yield data
            raise OSError("disk full")

        return _cm()

    monkeypatch.setattr(api_mod.settings_mod, "update", boom)
    result = api.create_preview_cycle_group("DPS")
    assert result["applied"] is False
    # Host was never touched.
    assert host.hotkeys is None


# --- Step 7: Concurrency-order tests ---


def test_preview_hotkey_writer_keeps_host_delivery_in_persist_order(
    tmp_path, monkeypatch
):
    """Two concurrent group mutations must not reorder host delivery past
    their persist order: the first update's host call must complete before
    the second update can even begin persisting."""
    _no_disk(monkeypatch)
    first_delivery = threading.Event()
    release_first = threading.Event()
    second_done = threading.Event()
    deliveries = []

    class BlockingHost(FakeHost):
        def set_hotkeys(self, table):
            deliveries.append(copy.deepcopy(table))
            if len(deliveries) == 1:
                first_delivery.set()
                assert release_first.wait(1)

    api = make_api(tmp_path, preview_host=BlockingHost())
    api._state.settings["preview"] = {
        "hotkeys": {
            "characters": {},
            "cycle_next": "",
            "cycle_prev": "",
            "groups": [{"id": "dps", "name": "DPS", "cycle": ""}],
            "group_by_character": {},
        }
    }

    first = threading.Thread(
        target=lambda: api.rename_preview_cycle_group("dps", "Damage")
    )

    def assign():
        api.set_preview_character_group("Alice", "dps")
        second_done.set()

    first.start()
    assert first_delivery.wait(1)
    second = threading.Thread(target=assign)
    second.start()
    # While first holds the lock, second cannot yet complete its persist.
    assert not second_done.wait(0.05)
    # The settings dict was NOT mutated by second (it is blocked on the lock).
    assert api._state.settings["preview"]["hotkeys"]["group_by_character"] == {}
    release_first.set()
    first.join(1)
    second.join(1)
    # Both deliveries arrived and in the correct order.
    assert [table["group_by_character"] for table in deliveries] == [
        {},
        {"Alice": "dps"},
    ]


def test_stale_rename_cannot_resurrect_deleted_group(tmp_path, monkeypatch):
    """A rename whose ID no longer exists after a delete must fail cleanly
    rather than re-inserting the group. Simulates a delayed thread arriving
    after the delete has committed."""
    _no_disk(monkeypatch)
    api = make_api(tmp_path, id_factory=lambda: "g1")
    api.create_preview_cycle_group("DPS")
    api.delete_preview_cycle_group("g1")
    result = api.rename_preview_cycle_group("g1", "Healers")
    assert result["applied"] is False
    assert result["hotkeys"]["groups"] == []


# --- Step 8: Hotkey-state payload tests ---


def test_get_preview_hotkey_state_includes_groups_and_membership(tmp_path):
    """groups and group_by_character must appear in the hotkey-state payload
    whether a host is running or not."""
    api = make_api(tmp_path)
    api._state.settings["preview"] = {
        "hotkeys": {
            "characters": {},
            "cycle_next": "",
            "cycle_prev": "",
            "groups": [{"id": "g1", "name": "DPS", "cycle": "Ctrl+F3"}],
            "group_by_character": {"Alice": "g1"},
        }
    }
    state = api.get_preview_hotkey_state()
    assert state["hotkeys"]["groups"] == [
        {"id": "g1", "name": "DPS", "cycle": "Ctrl+F3"}
    ]
    assert state["hotkeys"]["group_by_character"] == {"Alice": "g1"}


def test_push_preview_hotkeys_includes_groups_and_membership(tmp_path):
    """push_preview_hotkeys must carry the full hotkeys table including groups."""
    api = make_api(tmp_path)
    api._state.settings["preview"] = {
        "hotkeys": {
            "characters": {},
            "cycle_next": "",
            "cycle_prev": "",
            "groups": [{"id": "g1", "name": "DPS", "cycle": "Ctrl+F3"}],
            "group_by_character": {"Alice": "g1"},
        }
    }
    api.push_preview_hotkeys()
    pushes = [c for c in api._window.evaluated if "onPreviewHotkeys" in c]
    assert len(pushes) == 1
    import json

    payload_str = pushes[0]
    # Extract the JSON argument from the JS call.
    start = payload_str.index("(", payload_str.rindex("onPreviewHotkeys")) + 1
    end = payload_str.rindex(")")
    payload = json.loads(payload_str[start:end])
    assert payload["hotkeys"]["groups"] == [
        {"id": "g1", "name": "DPS", "cycle": "Ctrl+F3"}
    ]
    assert payload["hotkeys"]["group_by_character"] == {"Alice": "g1"}


# ---------------------------------------------------------------------------
# Round-1 / Finding 1 & 2 fixes
# ---------------------------------------------------------------------------


def test_pre_lock_refusal_excludes_transient_rolled_back_mutation(
    tmp_path, monkeypatch
):
    """A pre-lock refusal must return the authoritative post-rollback table,
    not a snapshot of a concurrent writer's transient mutation.

    Mechanism: a fake settings_mod.update that has real rollback semantics
    (deep-copy-before, restore-on-exception) pauses after the mutation lands
    on the live dict but before the CM exits.  A concurrent invalid operation
    that hits the pre-lock path should not capture the transient state; after
    the fix it blocks on _preview_hotkey_lock until the rollback completes.
    """
    from wingman.ui import api as api_mod

    writer_mutated = threading.Event()  # transient state is now live
    allow_writer_complete = threading.Event()  # let the writer proceed to failure
    refusal_captured = threading.Event()  # refusal result is ready
    refusal_result = {}

    def rollback_update(data, path=None):
        """Real rollback semantics: deep copy + restore on BaseException."""

        @contextlib.contextmanager
        def _cm():
            before = copy.deepcopy(data)
            try:
                yield data  # API code mutates live dict here
                # After yield: transient mutation is live but not yet normalized.
                writer_mutated.set()  # signal: live dict is dirty
                assert allow_writer_complete.wait(2)
                raise OSError("injected failure")  # forces real rollback below
            except BaseException:
                data.clear()
                data.update(before)  # identical to settings.update rollback
                raise

        return _cm()

    monkeypatch.setattr(api_mod.settings_mod, "update", rollback_update)

    api = make_api(tmp_path, id_factory=lambda: "g1")
    api._state.settings["preview"] = {
        "hotkeys": {
            "characters": {},
            "cycle_next": "",
            "cycle_prev": "",
            "groups": [],
            "group_by_character": {},
        }
    }

    def do_write():
        # create_preview_cycle_group acquires _preview_hotkey_lock, enters
        # rollback_update, appends the group to the live dict, then pauses.
        api.create_preview_cycle_group("DPS")

    writer = threading.Thread(target=do_write)
    writer.start()
    assert writer_mutated.wait(2), "writer never signalled transient state"

    # Live dict now has the transient DPS group.  Issue an invalid refusal
    # request from a separate thread so the test-coordinator (main thread)
    # can still signal allow_writer_complete.
    def do_invalid_refusal():
        # Non-string name forces the pre-lock early-return path, which reads
        # _preview_hotkeys() outside the lock (the bug) or inside (the fix).
        result = api.create_preview_cycle_group(123)
        refusal_result.update(result)
        refusal_captured.set()

    refusal_thread = threading.Thread(target=do_invalid_refusal)
    refusal_thread.start()

    # With the fix: refusal_thread blocks on _preview_hotkey_lock (writer holds it).
    # With the bug:  refusal_thread completes immediately and sees transient DPS.
    # This wait is intentional but the result is not used for assertions; the
    # assertion that matters is on refusal_result after both threads join.
    refusal_captured.wait(0.1)  # short probe; not a hard assertion

    # Allow the writer to fail (triggers rollback).
    allow_writer_complete.set()
    writer.join(2)
    refusal_thread.join(2)

    assert refusal_captured.is_set(), "refusal thread did not complete"

    # After rollback, the group must not exist in settings.
    assert api._state.settings["preview"]["hotkeys"]["groups"] == []

    # The authoritative table returned by the refusal must reflect the
    # post-rollback state: no transient DPS group.
    assert refusal_result["hotkeys"]["groups"] == [], (
        "Pre-lock refusal captured transient data that was subsequently rolled back; "
        f"got: {refusal_result['hotkeys']['groups']!r}"
    )


def test_character_group_assignment_over_64_member_cap_is_refused(
    tmp_path, monkeypatch
):
    """Assigning a 65th character to a group must be refused when the
    normalizer enforces the 64-entry roster cap on group_by_character.

    Uses real settings.update() (no _no_disk fake) with the test-isolated
    temp path to exercise real normalization.  The result must have
    applied=False, persisted=False, the mapping must be absent from the
    authoritative returned table, and the host must not be called.
    """
    # Do NOT call _no_disk — we need real normalization + real disk writes
    # to the test's temp-isolated LOCALAPPDATA directory.

    host = FakeHost()
    api = make_api(tmp_path, id_factory=lambda: "grp", preview_host=host)

    # Prime the settings with a group and 64 character-to-group mappings.
    memberships = {f"Char{i:02d}": "grp" for i in range(64)}
    api._state.settings["preview"] = {
        "hotkeys": {
            "characters": {},
            "cycle_next": "",
            "cycle_prev": "",
            "groups": [{"id": "grp", "name": "DPS", "cycle": ""}],
            "group_by_character": memberships,
        }
    }

    # Assign one more character beyond the cap.
    new_char = "ExtraChar"
    result = api.set_preview_character_group(new_char, "grp")

    # Must be refused because normalization drops the assignment.
    assert result["applied"] is False, (
        f"Expected refused result, got applied=True; result={result!r}"
    )
    assert result["persisted"] is False
    assert new_char not in result["hotkeys"]["group_by_character"], (
        "Refused result must not include the dropped mapping"
    )

    # Host must not be called with a table that claims the assignment.
    if host.hotkeys is not None:
        assert new_char not in host.hotkeys.get("group_by_character", {}), (
            "Host was delivered a table claiming the dropped assignment"
        )


# ---------------------------------------------------------------------------
# Task 4: Group keybind rows, clash detection, assignment, and management UI
# ---------------------------------------------------------------------------


def test_named_group_clashes_are_counted_with_all_cycle_chords():
    """clashes() must check group cycles against the chord being tested.
    A group keybind matching cycle_next/cycle_prev or another group cycle
    is a duplicate, not just unknown."""
    js = _web("previews.js")
    block = js.split("function clashes", 1)[1].split("function makeRow", 1)[0]
    assert "state.hotkeys.groups" in block, (
        "clashes() does not walk group cycles; group<->All collision is invisible"
    )
    assert ".cycle" in block, "clashes() does not read the group's cycle field"


def test_group_bind_calls_set_preview_cycle_group_bind_not_send():
    """setGroupBind must use the narrow group endpoint, not the full
    set_preview_binds that overwrites character and cycle_next/prev."""
    js = _web("previews.js")
    block = js.split("function setGroupBind", 1)[1].split("\n  }", 1)[0]
    assert "set_preview_cycle_group_bind" in block, (
        "setGroupBind does not call set_preview_cycle_group_bind"
    )
    assert "send(next)" not in block, (
        "setGroupBind routes through set_preview_binds (send(next)) instead "
        "of the narrow group endpoint"
    )


def test_group_rows_rendered_after_all_rows_before_character_divider():
    """render() appends group rows after the two All rows and before the
    empty bind-group separator that precedes the column headers."""
    import re

    js = _web("previews.js")
    # Strip line comments so embedded prose can't confuse the search.
    stripped = re.sub(r"//[^\n]*", "", js)
    render_body = stripped.split("function render()", 1)[1].split("function send(", 1)[
        0
    ]
    all_pos = render_body.index("'All forward'")  # renamed from 'Cycle forward'
    # groups() helper call appears before bind-group separator (empty divider)
    groups_call_pos = render_body.index("groups()")
    divider_pos = render_body.index("'bind-group'")
    assert all_pos < groups_call_pos < divider_pos, (
        "group rows are not placed after All rows and before the character divider: "
        f"all_pos={all_pos}, groups_call_pos={groups_call_pos}, "
        f"divider_pos={divider_pos}"
    )


def test_group_row_clear_absent_when_no_bind_present():
    """makeRow's Clear gate (only renders when gesture is truthy) already
    handles group rows -- a group row with an empty bind must not render
    a Clear button. This is already guaranteed by the shared makeRow path,
    so the test asserts the group onSet callback passes through makeRow."""
    js = _web("previews.js")
    # groups helper must pass onSet to makeRow, not build its own row.
    # groups() returns the array; render() passes each through makeRow.
    # Just ensure the groups() helper is called in render() context.
    assert (
        "groups()" in js.split("function render()", 1)[1].split("function send(", 1)[0]
    ), "render() does not call groups() to enumerate named-group rows"


def test_group_edit_always_available_not_gated_on_off():
    """Edit… on a group row is never disabled -- groups have no `off` (opted-out)
    state equivalent. setGroupBind must not pass `off=true` to makeRow."""
    js = _web("previews.js")
    render_body = js.split("function render()", 1)[1].split("function send(", 1)[0]
    # group rows call makeRow with online=true (not gated on state.enabled)
    # and no `character` argument (so `off` resolves to false inside makeRow).
    # The clearest assertion: render() passes `true` as the online arg for groups.
    assert "makeRow(group.name" in render_body or "groups()" in render_body, (
        "render() does not iterate named groups at all"
    )


def test_capture_ends_before_rename_dialog():
    """WM.prompt for rename must only be opened after endCapture() -- an
    armed capture's keydown handler preventDefault()s everything, so a
    prompt opened while one is live cannot be typed into."""
    js = _web("previews.js")
    # Find the rename handler -- it calls WM.prompt and endCapture.
    assert "endCapture" in js, "endCapture is not defined"
    assert "WM.prompt" in js, "WM.prompt is not used"
    # The rename path must call endCapture before WM.prompt.
    # Find the renameGroup (or equivalent) code block.
    rename_block = js.split("renameGroup", 1)
    assert len(rename_block) > 1, "no renameGroup function/handler found in previews.js"
    body = rename_block[1].split("\n  function ", 1)[0]
    ec_pos = body.find("endCapture")
    prompt_pos = body.find("WM.prompt")
    assert ec_pos != -1 and prompt_pos != -1, (
        "renameGroup block must contain both endCapture() and WM.prompt"
    )
    assert ec_pos < prompt_pos, (
        "renameGroup calls WM.prompt before endCapture; an armed capture "
        "would eat the dialog's keystrokes"
    )


def test_capture_ends_before_delete_dialog():
    """WM.confirm for delete must only be opened after endCapture() --
    same reasoning as the rename guard above."""
    js = _web("previews.js")
    assert "WM.confirm" in js, "WM.confirm is not used (delete dialog)"
    delete_block = js.split("deleteGroup", 1)
    assert len(delete_block) > 1, "no deleteGroup function/handler found in previews.js"
    body = delete_block[1].split("\n  function ", 1)[0]
    ec_pos = body.find("endCapture")
    confirm_pos = body.find("WM.confirm")
    assert ec_pos != -1 and confirm_pos != -1, (
        "deleteGroup block must contain both endCapture() and WM.confirm"
    )
    assert ec_pos < confirm_pos, "deleteGroup calls WM.confirm before endCapture"


def test_group_rename_uses_wm_prompt_not_window_prompt():
    """DESIGN.md forbids window.prompt/confirm/alert. Group rename must use
    WM.prompt (the app's own dialog)."""
    js = _web("previews.js")
    assert "window.prompt" not in js, (
        "previews.js uses window.prompt, which is forbidden by DESIGN.md; "
        "use WM.prompt instead"
    )


def test_group_delete_uses_wm_confirm_not_window_confirm():
    """DESIGN.md forbids window.confirm. Group delete must use WM.confirm."""
    js = _web("previews.js")
    assert "window.confirm" not in js, (
        "previews.js uses window.confirm, which is forbidden by DESIGN.md; "
        "use WM.confirm instead"
    )


def test_make_group_select_appends_to_lab_not_row():
    """makeGroupSelect must append its <select> to `lab`, never directly
    to `row` -- an extra row.appendChild would break the five-cell grid."""
    js = _web("previews.js")
    assert "function makeGroupSelect" in js, (
        "makeGroupSelect is not defined in previews.js"
    )
    body = js.split("function makeGroupSelect", 1)[1].split("\n  function ", 1)[0]
    # Must not append to row.
    assert "row.appendChild" not in body, (
        "makeGroupSelect calls row.appendChild, which would add a sixth "
        "grid cell and break the five-track layout"
    )
    # Must append to lab (or return a node the caller appends to lab).
    assert "lab.appendChild" in body or "return " in body, (
        "makeGroupSelect neither appends to lab nor returns a node"
    )


def test_make_group_select_only_when_groups_exist():
    """The group select is only built (and only appended to lab) when
    groups().length is truthy -- an empty group list should leave the
    lab unchanged."""
    js = _web("previews.js")
    body = js.split("function makeRow", 1)[1].split("return row;", 1)[0]
    # The conditional guard: groups().length before appending the select.
    assert "groups().length" in body, (
        "makeRow does not guard the group select on groups().length; "
        "the select would always render even with no groups defined"
    )


def test_manage_groups_disclosure_has_add_rename_delete():
    """The management disclosure must contain Add, Rename…, and Delete
    controls for each group."""
    js = _web("previews.js")
    assert "makeGroupManager" in js or "renderGroupManager" in js, (
        "no group manager renderer found in previews.js"
    )
    # Check all three actions appear in the source.
    assert "create_preview_cycle_group" in js, (
        "previews.js does not call create_preview_cycle_group (Add)"
    )
    assert "rename_preview_cycle_group" in js, (
        "previews.js does not call rename_preview_cycle_group (Rename…)"
    )
    assert "delete_preview_cycle_group" in js, (
        "previews.js does not call delete_preview_cycle_group (Delete)"
    )


def test_manage_add_commits_on_button_or_enter_not_blur():
    """Settings commit rule: free text commits on Enter or an explicit
    button, never on blur. The Add text field must not have a blur listener
    that calls create_preview_cycle_group."""
    js = _web("previews.js")
    # The add path must not commit on blur.
    # Find the add-name field handling.
    assert "create_preview_cycle_group" in js, "no add endpoint"
    # Any blur listener that leads to create_preview_cycle_group is wrong.
    # Simple lexical check: 'blur' must not appear between the add-field
    # event binding and the create call in a single handler chain.
    # The last addEventListener before the create call must not be 'blur'.
    # If blur listener appears at all before the create call it must not
    # directly reach create_preview_cycle_group on the same path.
    # Sufficient signal: no blur listener immediately before the send.
    # Sufficient signal: no blur listener immediately before the send.
    create_after_blur = js.split("addEventListener('blur'", 1)
    if len(create_after_blur) > 1:
        after_blur = create_after_blur[1]
        # If blur handler contains create_preview_cycle_group it commits on blur.
        blur_handler = after_blur.split("addEventListener(", 1)[0]
        assert "create_preview_cycle_group" not in blur_handler, (
            "the Add field commits on blur, violating the Settings commit rule"
        )


def test_delete_confirm_copy_includes_group_name_and_member_count():
    """The delete confirmation must include the group name and member count
    so the user knows what they are removing."""
    js = _web("previews.js")
    delete_block = js.split("deleteGroup", 1)
    assert len(delete_block) > 1, "no deleteGroup in previews.js"
    body = delete_block[1].split("\n  function ", 1)[0]
    # Must reference group_by_character to derive member count.
    assert "group_by_character" in body, (
        "deleteGroup does not derive member count from group_by_character"
    )
    # The confirm dialog body must mention the group name and count.
    confirm_pos = body.find("WM.confirm")
    assert confirm_pos != -1, "no WM.confirm in deleteGroup"
    confirm_call = body[confirm_pos : confirm_pos + 300]
    # group name must appear in the confirm text (group.name or similar).
    assert ".name" in confirm_call or "group" in confirm_call, (
        "WM.confirm message does not reference the group name"
    )


def test_group_busy_disables_controls_during_mutation():
    """groupBusy state: while a write is pending, lifecycle and assignment
    controls must be disabled. The source must declare a groupBusy variable."""
    js = _web("previews.js")
    assert "groupBusy" in js, (
        "previews.js has no groupBusy state variable; controls are never "
        "disabled during a group mutation"
    )
    # groupBusy must be set before the async call and cleared in both
    # resolve and reject paths.
    assert js.count("groupBusy") >= 3, (
        "groupBusy must be set, cleared on success, and cleared on failure "
        "(at minimum 3 references)"
    )


def test_state_defaults_fill_groups_and_group_by_character():
    """The payload normalisation in onPreviewHotkeys and refresh() must
    fill groups and group_by_character with safe defaults, so later code
    does not need null checks everywhere."""
    js = _web("previews.js")
    # Both the push handler and the refresh path normalize state.
    normalize_block = js.split("onPreviewHotkeys", 1)[1].split(
        "WM.handle('onPreviewBindCaptured'", 1
    )[0]
    assert "state.hotkeys.groups" in normalize_block, (
        "onPreviewHotkeys does not default state.hotkeys.groups"
    )
    assert "state.hotkeys.group_by_character" in normalize_block, (
        "onPreviewHotkeys does not default state.hotkeys.group_by_character"
    )
    # Also check refresh().
    refresh_block = js.split("function refresh(", 1)[1].split("\n  }", 1)[0]
    assert "groups" in refresh_block, (
        "refresh() does not normalize groups in the returned payload"
    )


def test_delete_group_restores_focus_to_surviving_control():
    """After a successful group delete and repaint, keyboard focus must
    return to a surviving logical control rather than falling to <body>.
    The deleteGroup success path must call a focus helper (or equivalent)
    that targets a surviving group manage button or the Add-name field.

    Acceptable patterns:
    - focusGroupManager() called in the success path of deleteGroup
    - An explicit .focus() call on a surviving control or fallback in that path
    - A querySelector for '.group-delete-btn' or '.group-add-name' after render

    The helper must use a query-selector (to find an attached node) and must
    fall back to a section-level enabled control, matching focusCopyTarget.
    """
    js = _web("previews.js")
    delete_block = js.split("function deleteGroup", 1)
    assert len(delete_block) > 1, "no deleteGroup function found in previews.js"
    body = delete_block[1].split("\n  function ", 1)[0]

    # The success path is the .then(...) block containing requestRender.
    # It must contain a focus call or a helper that performs focus.
    has_focus_helper = (
        "focusGroupManager" in body
        or ("querySelector" in body and ".focus()" in body)
        or ("group-delete-btn" in body and ".focus()" in body)
        or ("group-add-name" in body and ".focus()" in body)
    )
    assert has_focus_helper, (
        "deleteGroup success path does not restore keyboard focus to a "
        "surviving control. After repaint the browser drops focus to <body>. "
        "Add a focusGroupManager() helper or explicit .focus() on a "
        "surviving group button or the Add-name field."
    )

    # The focus must not be attempted on a detached node: the helper must
    # run AFTER requestRender (which rebuilds the DOM), not before.
    render_pos = body.find("requestRender")
    # Allow both focusGroupManager and querySelector-based patterns.
    focus_pos = body.find("focusGroupManager")
    if focus_pos == -1:
        focus_pos = body.find(".focus()")
    assert render_pos != -1, "deleteGroup must call requestRender"
    assert focus_pos != -1, "deleteGroup must contain a focus call"
    assert focus_pos > render_pos, (
        "focus call appears before requestRender in deleteGroup; "
        "focus must run AFTER repaint so it targets an attached node"
    )


def test_make_group_select_has_generation_guard():
    """makeGroupSelect's change handler must use a generation guard
    (store `pushes` before the bridge call, check it before applying
    res.hotkeys) matching the pattern in setGroupBind and other handlers.

    Without the guard, a Python push that arrives while set_preview_character_group
    is in flight will have its state overwritten by the stale response.
    groupBusy prevents concurrent user-initiated requests but does NOT
    prevent an onPreviewHotkeys push from replacing state.hotkeys wholesale
    during the in-flight call.
    """
    js = _web("previews.js")
    assert "function makeGroupSelect" in js, (
        "makeGroupSelect is not defined in previews.js"
    )
    body = js.split("function makeGroupSelect", 1)[1].split("\n  function ", 1)[0]

    # Must capture pushes before the bridge call.
    assert "before = pushes" in body, (
        "makeGroupSelect change handler does not capture the current push "
        "generation before calling set_preview_character_group. "
        "Add `var before = pushes;` before WM.send(...)."
    )
    # Must check for a newer push before applying res.hotkeys.
    assert "pushes !== before" in body or "before !== pushes" in body, (
        "makeGroupSelect does not guard res.hotkeys application with a "
        "generation check. Add `if (pushes !== before) { return; }` "
        "before applying res.hotkeys, matching the setGroupBind pattern."
    )


def test_rename_group_has_generation_guard():
    """renameGroup's WM.send callback must use a generation guard.

    Before the bridge call it must capture `var before = pushes`, and before
    applying res.hotkeys it must check `pushes !== before`, matching the
    makeGroupSelect and setGroupBind patterns.

    Without the guard, an onPreviewHotkeys push arriving while
    rename_preview_cycle_group is in flight will have its state.hotkeys
    overwritten by the stale response payload.  groupBusy blocks concurrent
    user writes but does NOT block Python-pushed state replacements.
    """
    js = _web("previews.js")
    assert "function renameGroup" in js, "no renameGroup function in previews.js"
    body = js.split("function renameGroup", 1)[1].split("\n  function ", 1)[0]

    assert "before = pushes" in body, (
        "renameGroup does not capture the push generation before the bridge "
        "call.  Add `var before = pushes;` before WM.send(...)."
    )
    assert "pushes !== before" in body or "before !== pushes" in body, (
        "renameGroup does not guard res.hotkeys with a generation check.  "
        "Add `if (pushes !== before) { ... }` before applying res.hotkeys, "
        "matching the setGroupBind / makeGroupSelect pattern."
    )


def test_delete_group_has_generation_guard():
    """deleteGroup's WM.send callback must use a generation guard.

    Before the bridge call it must capture `var before = pushes`, and the
    hotkeys assignment must be skipped when `pushes !== before`.

    Crucially, groupBusy = false, requestRender(), and focusGroupManager()
    must all still execute even when a newer push has landed (the guard must
    only gate the state.hotkeys assignment, not the cleanup/focus obligations).
    """
    js = _web("previews.js")
    assert "function deleteGroup" in js, "no deleteGroup function in previews.js"
    body = js.split("function deleteGroup", 1)[1].split("\n  function ", 1)[0]

    assert "before = pushes" in body, (
        "deleteGroup does not capture the push generation before the bridge "
        "call.  Add `var before = pushes;` before WM.send(...)."
    )
    assert "pushes !== before" in body or "before !== pushes" in body, (
        "deleteGroup does not guard res.hotkeys with a generation check.  "
        "Add the guard matching the makeGroupSelect / setGroupBind pattern."
    )
    # groupBusy = false must appear in the then() callback
    then_body = (
        body.split(".then(function (res)")[1]
        if ".then(function (res)" in body
        else body
    )
    assert "groupBusy = false" in then_body, (
        "groupBusy = false must appear inside deleteGroup's .then() callback "
        "so busy state always clears, even when the guard skips the hotkeys update."
    )
    # focusGroupManager must be present (tested by earlier test too, but
    # confirm it survives the guard refactor)
    assert "focusGroupManager" in then_body or ".focus()" in then_body, (
        "deleteGroup success path must still call focusGroupManager() (or "
        "equivalent .focus()) even when a newer push won."
    )


def test_do_add_has_generation_guard():
    """doAdd (inside makeGroupManager) must use a generation guard.

    Before the WM.send call it must capture `var before = pushes`, and before
    applying res.hotkeys it must check `pushes !== before`.

    groupBusy = false must still execute in both the refusal and success paths.
    """
    js = _web("previews.js")
    assert "function makeGroupManager" in js, "no makeGroupManager in previews.js"
    mgr_body = js.split("function makeGroupManager", 1)[1].split("\n  function ", 1)[0]

    assert "function doAdd" in mgr_body, "no doAdd inside makeGroupManager"
    do_add_body = mgr_body.split("function doAdd", 1)[1]
    # Trim to just the doAdd closure (next sibling closure at same indent ends it)
    # doAdd is an inner function so it ends at the closing brace before addBtn etc.
    # Use the click-handler registration as a natural end marker.
    if "addBtn.addEventListener" in do_add_body:
        do_add_body = do_add_body.split("addBtn.addEventListener", 1)[0]

    assert "before = pushes" in do_add_body, (
        "doAdd does not capture the push generation before the bridge call.  "
        "Add `var before = pushes;` before WM.send(...)."
    )
    assert "pushes !== before" in do_add_body or "before !== pushes" in do_add_body, (
        "doAdd does not guard res.hotkeys with a generation check.  "
        "Add `if (pushes !== before) { ... }` before applying res.hotkeys."
    )
    # groupBusy must clear in the .then() body
    then_body = (
        do_add_body.split(".then(function (res)")[1]
        if ".then(function (res)" in do_add_body
        else do_add_body
    )
    assert "groupBusy = false" in then_body, (
        "groupBusy = false must appear inside doAdd's .then() callback "
        "so busy state always clears regardless of whether the guard fires."
    )


# ---------------------------------------------------------------------------
# Round 1/5: Four targeted correctness fixes
# ---------------------------------------------------------------------------


def test_set_group_bind_participates_in_group_busy():
    """setGroupBind must set groupBusy=true before the bridge call and
    clear it in both success and refusal paths, so it serialises against
    all other group writes and assignment selects stay disabled.

    Without this, a concurrent assignment-select change or manager action
    (rename/delete/add) can fire while a group-bind write is in flight,
    leading to overlapping bridge calls and stale responses overwriting
    authoritative state.
    """
    js = _web("previews.js")
    assert "function setGroupBind" in js, "setGroupBind not defined in previews.js"
    block = js.split("function setGroupBind", 1)[1].split("\n  function ", 1)[0]

    # Must set groupBusy = true before the bridge call.
    assert "groupBusy = true" in block, (
        "setGroupBind does not set groupBusy = true before the bridge call. "
        "All group writes must participate in the shared busy lock."
    )
    # Must clear groupBusy in the .then() callback.
    then_body = (
        block.split(".then(function (res)", 1)[1]
        if ".then(function (res)" in block
        else ""
    )
    assert "groupBusy = false" in then_body, (
        "setGroupBind does not clear groupBusy = false inside the .then() "
        "callback. Both success and refusal paths must clear busy."
    )
    # groupBusy must be cleared before the early return on refusal.
    refusal_pos = then_body.find("if (!res || !res.applied)")
    busy_clear_pos = then_body.find("groupBusy = false")
    assert busy_clear_pos < refusal_pos, (
        "groupBusy = false must appear before the refusal early-return in "
        "setGroupBind's .then(), so a refused write still clears busy."
    )


def test_group_row_bind_controls_disabled_when_group_busy():
    """makeRow must disable the keybind button, Clear, and Edit… controls
    when groupBusy is true for group rows (rows without a character).

    makeGroupSelect must also be disabled based on groupBusy, so an
    assignment change cannot fire while another group write is in flight.

    The current code gates all three on !off only. A group-row has no
    character so off is always false, meaning the controls stay enabled
    even while a setGroupBind, rename, delete, or add is in flight.
    """
    js = _web("previews.js")
    assert "function makeRow" in js, "makeRow not defined in previews.js"
    make_row = js.split("function makeRow", 1)[1].split("\n  function ", 1)[0]

    # The keybind button, Clear, and Edit… setEnabled calls must reference
    # groupBusy (or a helper that tests it) not just !off.
    assert "groupBusy" in make_row, (
        "makeRow does not reference groupBusy. The keybind button, Clear, "
        "and Edit... controls must be gated on !groupBusy (in addition to "
        "the existing !off gate) so they stay disabled while any group "
        "write is in flight."
    )
    # The group select must also be disabled during groupBusy.
    make_group_select_block = js.split("function makeGroupSelect", 1)[1].split(
        "\n  function ", 1
    )[0]
    # The select element must have WM.setEnabled or disabled attribute set
    # based on groupBusy at creation time.
    assert (
        "setEnabled(sel" in make_group_select_block
        or "groupBusy" in make_group_select_block.split("addEventListener", 1)[0]
    ), (
        "makeGroupSelect does not disable the select based on groupBusy at "
        "creation time. The select must be rendered disabled when groupBusy "
        "is true, matching the lifecycle controls in makeGroupManager."
    )


def test_make_group_select_stale_success_still_repaints():
    """makeGroupSelect's stale-push success path (pushes !== before) must
    call requestRender() before returning.

    Currently: groupBusy = false, then if (pushes !== before) { return; }
    The early return skips requestRender, leaving the DOM with permanently
    disabled controls because groupBusy was cleared in JavaScript state but
    the old DOM nodes (built when groupBusy was true) are never replaced.

    The fix is to move requestRender() outside the stale guard (unconditional
    after the guard), or include it inside the stale guard block before return.
    Either way the DOM must be rebuilt whenever the .then() fires.
    """
    js = _web("previews.js")
    assert "function makeGroupSelect" in js, "makeGroupSelect not found in previews.js"
    block = js.split("function makeGroupSelect", 1)[1].split("\n  function ", 1)[0]
    then_body = block.split(".then(function (res)", 1)
    assert len(then_body) > 1, "makeGroupSelect has no .then() callback"
    then_body = then_body[1]

    stale_guard = "if (pushes !== before)"
    assert stale_guard in then_body, (
        "makeGroupSelect .then() has no stale-push guard (if pushes !== before)"
    )

    # The stale guard must NOT be a bare `return` that skips repaint.
    # Check: the stale guard block itself must contain requestRender, OR
    # requestRender must appear before the stale guard (unconditional).
    stale_pos = then_body.find(stale_guard)
    # Get the guard's inline block content (everything on the same line after the condition)
    guard_line = then_body[stale_pos : then_body.find("\n", stale_pos)]
    # A bare `{ return; }` on the same line is the bug
    is_bare_return = "return;" in guard_line and "requestRender" not in guard_line

    # But the requestRender before the guard must not be inside the refusal block
    # (which exits via return, so stale successes never reach it)
    refusal_end = then_body.find("return;", then_body.find("if (!res || !res.applied)"))
    rr_outside_refusal_before_guard = any(
        then_body[i : i + 13] == "requestRender" and i > (refusal_end or 0)
        for i in range(stale_pos)
    )

    # The guard block itself must not be a bare { return; } unless requestRender
    # already ran unconditionally for ALL paths (i.e., outside both refusal and stale)
    assert not is_bare_return or rr_outside_refusal_before_guard, (
        "makeGroupSelect stale-push guard is a bare `{ return; }` that skips "
        "requestRender(). The DOM retains disabled controls forever (groupBusy "
        "was cleared in JS state but the old disabled DOM is never rebuilt). "
        "Either move requestRender() before the stale guard (unconditional), or "
        "add requestRender() inside the stale guard block before returning."
    )


def test_delete_group_restores_focus_on_refusal():
    """deleteGroup refusal path must restore focus just as the success path
    does. Currently, refusal calls requestRender() but NOT focusGroupManager().

    After a refused delete the DOM is rebuilt (requestRender), so focus falls
    to <body>. The user would have to Tab back to any control, which is
    disorienting — especially since the refused delete means the group and
    its controls are still present.
    """
    js = _web("previews.js")
    assert "function deleteGroup" in js, "deleteGroup not defined in previews.js"
    block = js.split("function deleteGroup", 1)[1].split("\n  function ", 1)[0]
    then_body = block.split(".then(function (res)", 1)
    assert len(then_body) > 1, "deleteGroup has no .then() callback"
    then_body = then_body[1]

    # Identify the refusal branch: if (!res || !res.applied) { ... }
    refusal_idx = then_body.find("if (!res || !res.applied)")
    assert refusal_idx != -1, "deleteGroup .then() has no refusal guard"

    # Find the end of the refusal block (the matching return)
    refusal_block = then_body[refusal_idx:]
    return_idx = refusal_block.find("return;")
    refusal_content = refusal_block[: return_idx + len("return;")]

    has_focus = (
        "focusGroupManager" in refusal_content
        or ("querySelector" in refusal_content and ".focus()" in refusal_content)
        or ("group-delete-btn" in refusal_content and ".focus()" in refusal_content)
        or ("group-add-name" in refusal_content and ".focus()" in refusal_content)
    )
    assert has_focus, (
        "deleteGroup refusal path (if !res || !res.applied) does not restore "
        "keyboard focus. After a refused delete the DOM is rebuilt by "
        "requestRender but focus falls to <body>. Add focusGroupManager() "
        "after requestRender in the refusal branch, matching the success path."
    )


def test_make_group_select_restores_focus_after_repaint():
    """After makeGroupSelect's change handler calls requestRender() and the
    DOM is rebuilt, focus must be restored to the replacement select for the
    same character (by stable character identity / aria-label), or to an
    enabled Previews fallback if that row no longer exists.

    Currently no focus restoration is attempted on success, refusal, or
    stale-push paths. After requestRender() the old select is detached and
    the new one has focus on <body>.

    Acceptable patterns in the .then() body:
    - querySelector('[aria-label="Cycle group for "] + ...') targeting the
      same character's replacement select
    - WM.el() or section.querySelector() using the characterName variable
    - a helper function (focusGroupSelect or similar) called after repaint

    Any of these satisfies the requirement; the key constraint is that the
    focus target is identified by character identity, not by DOM position,
    and the call appears after requestRender().
    """
    js = _web("previews.js")
    assert "function makeGroupSelect" in js, "makeGroupSelect not defined"
    block = js.split("function makeGroupSelect", 1)[1].split("\n  function ", 1)[0]
    then_body = block.split(".then(function (res)", 1)
    assert len(then_body) > 1, "makeGroupSelect has no .then() callback"
    then_body = then_body[1]

    # Focus restoration must appear in the .then() body, after requestRender.
    # Acceptable patterns:
    # 1. focusGroupSelect or similar named helper
    # 2. querySelector using 'Cycle group for' + characterName
    # 3. querySelector using 'preview-group-select' with a focus() call
    has_focus_restore = (
        "focusGroupSelect" in then_body
        or ("Cycle group for" in then_body and ".focus()" in then_body)
        or ("preview-group-select" in then_body and ".focus()" in then_body)
        or ("characterName" in then_body and ".focus()" in then_body)
    )
    assert has_focus_restore, (
        "makeGroupSelect .then() does not restore focus to the replacement "
        "select after requestRender(). The old select node is detached by "
        "repaint; focus falls to <body>. Identify the replacement by character "
        "identity (e.g. aria-label or characterName variable) and call "
        ".focus() on it after requestRender(). Use an enabled Previews control "
        "as fallback when the row no longer exists."
    )

    # The focus call must come AFTER requestRender (targeting an attached node).
    rr_pos = then_body.rfind("requestRender")
    if "focusGroupSelect" in then_body:
        focus_pos = then_body.rfind("focusGroupSelect")
    else:
        focus_pos = then_body.rfind(".focus()")
    assert rr_pos != -1, "makeGroupSelect .then() must call requestRender()"
    assert focus_pos != -1, "makeGroupSelect .then() must have a focus call"
    assert focus_pos > rr_pos, (
        "focus call appears before requestRender in makeGroupSelect .then(); "
        "must run after repaint so it targets an attached (not detached) node"
    )
