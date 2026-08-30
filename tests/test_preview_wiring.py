"""Wiring, with the host faked. What must hold: the subsystem is lazy,
enable/disable is idempotent, and shutdown always tears it down.

make_api is the existing helper in tests/test_api.py -- imported, not
redefined. It takes tmp_path positionally and forwards **kwargs to Api().
"""

import contextlib
import copy
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

    `SystemParametersInfoW` used to be on the list too, as the placement
    feature's work-area reader. It is bound again for exactly two actions,
    SPI_GETANIMATION/SPI_SETANIMATION -- the minimize/restore animation the
    switch suspends (host.py, _animation_off). Neither takes a window or
    touches a rect, so it cannot reach the rewrite this guard exists to
    prevent; the closed list of SPI_ constants below is what keeps the
    binding from quietly growing back into the work-area reader.
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
    assert sorted(set(re.findall(r"\bSPI_[A-Z]+\b", src))) == [
        "SPI_GETANIMATION",
        "SPI_SETANIMATION",
    ]


def test_sc_minimize_is_present_and_documented():
    """SC_MINIMIZE is the one Win32 surface allowed to reach a live EVE
    client's window: it changes only show state (the same transition the
    taskbar button and Alt-Tab already send), never position or size, so it
    cannot trigger the resolution rewrite the guard above exists to prevent.

    This asserts the constant is present and explained, so a future purge
    that sweeps up "that Win32 thing near the dangerous ones" fails a test
    instead of silently removing the minimize-inactive-clients feature.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    src = (root / "wingman" / "preview" / "win32.py").read_text(encoding="utf-8")
    assert "SC_MINIMIZE = 0xF020" in src
    assert "show state" in src.lower()


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


def test_sendmessagew_is_not_declared():
    """Bare `SendMessageW` blocks until the target window's queue processes
    the message, so a hung or still-loading EVE client would stall the
    preview thread -- and with it hotkey dispatch, the alert pump, and the
    sweep -- indefinitely. `SendMessageTimeoutW` with `SMTO_ABORTIFHUNG`
    gets the ordering guarantee `PostMessageW` can't provide without that
    unbounded stall, so `SendMessageW` should never appear in the bind list.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    src = (root / "wingman" / "preview" / "win32.py").read_text(encoding="utf-8")
    assert "SendMessageTimeoutW" in src
    assert '"SendMessageW"' not in src
    assert "user32.SendMessageW" not in src


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
