"""The floating sig bar: settings section, bridge methods, push fan-out.

Headless throughout, like the rest of the Api tests: the window is a fake
and sigbar's native helpers are monkeypatched, so nothing here needs
pywebview's event loop (which does not exist off the GUI thread anyway)
or a real HWND.
"""

import json

import pytest

from tests.fakes import FakeWindow
from wingman import settings


class SigBarWindow(FakeWindow):
    """A FakeWindow plus the state the bar's bridge drives: visible /
    hidden (the toggle), alive (external destruction), and the resize
    plus width/height readbacks the page's fit round-trip uses."""

    def __init__(self):
        super().__init__()
        self.hidden = True
        self.alive = True
        self.resized = []
        self.width = 0
        self.height = 0

    def resize(self, width, height):
        self.resized.append((width, height))
        self.width = width
        self.height = height


@pytest.fixture
def api(tmp_path, monkeypatch):
    from wingman.ui import api as api_mod
    from wingman.ui import sigbar

    monkeypatch.setattr(api_mod.paths, "settings_file", lambda: tmp_path / "s.json")
    state = api_mod.AppState(
        recording_dir=tmp_path, settings=settings.load(tmp_path / "s.json")
    )
    built = api_mod.Api(state)
    built._window = FakeWindow()
    built._sigbar_window = SigBarWindow()

    # The native helpers are what the bridge calls; fakes stand in so the
    # tests run anywhere and the fake window's state is the only truth.
    monkeypatch.setattr(sigbar, "is_alive", lambda bar: bar is not None and bar.alive)
    monkeypatch.setattr(
        sigbar, "is_visible", lambda bar: bar is not None and not bar.hidden
    )

    def reveal(bar):
        if bar is not None:
            bar.hidden = False

    def hide(bar):
        if bar is not None:
            bar.hidden = True

    monkeypatch.setattr(sigbar, "reveal_bar", reveal)
    monkeypatch.setattr(sigbar, "hide_bar", hide)
    yield built
    # The focus-gate timer chain is self-re-arming and daemon; a test that
    # ends with the bar enabled would leave it ticking into LATER tests,
    # where it can construct whatever threading.Timer they have patched
    # (the startup suite counts Timer constructions -- see the ubuntu-only
    # failure this teardown exists to prevent). Close the lifecycle and
    # cancel: a tick racing this teardown sees quitting under the lock and
    # never re-arms.
    with built._sigbar_lifecycle_lock:
        built._sigbar_quitting = True
        if built._sigbar_focus_timer is not None:
            built._sigbar_focus_timer.cancel()
            built._sigbar_focus_timer = None


def state_pushes(window):
    return [c for c in window.calls if "onSigBarState" in c]


# ---- settings section ---------------------------------------------------


def test_defaults_carry_the_sig_bar_section(tmp_path):
    data = settings.load(tmp_path / "s.json")  # absent file -> fresh defaults
    assert data["sig_bar"] == {
        "enabled": False,
        "x": None,
        "y": None,
    }


def test_sig_bar_survives_the_save_projection(tmp_path):
    """save() projects onto DEFAULTS keys; an undeclared key is dropped on
    every write. This is the test that keeps the declaration honest."""
    data = settings.load(tmp_path / "s.json")
    data["sig_bar"]["enabled"] = True
    data["sig_bar"]["x"] = 120
    data["sig_bar"]["y"] = 340
    settings.save(data, tmp_path / "s.json")
    reloaded = settings.load(tmp_path / "s.json")
    assert reloaded["sig_bar"]["enabled"] is True
    assert reloaded["sig_bar"]["x"] == 120
    assert reloaded["sig_bar"]["y"] == 340


def test_validated_sig_bar_falls_back_whole_on_a_malformed_section():
    for raw in (None, 7, "on", [True]):
        assert settings.validated_sig_bar(raw) == settings._sig_bar_defaults()


def test_validated_sig_bar_falls_back_alone_per_value():
    raw = {
        "enabled": "yes",  # not a bool -> default
        "x": "120",  # a string coordinate -> None (default placement)
        "y": True,  # bool is an int; must not become a coordinate
    }
    got = settings.validated_sig_bar(raw)
    assert got["enabled"] is False
    assert got["x"] is None
    assert got["y"] is None


def test_validated_sig_bar_accepts_a_good_document():
    raw = {
        "enabled": True,
        "x": -8,  # a negative position is legal on Windows
        "y": 40,
    }
    got = settings.validated_sig_bar(raw)
    assert got == raw


def test_a_section_absent_from_an_old_file_is_added_on_load(tmp_path):
    (tmp_path / "s.json").write_text(json.dumps({"privacy": "public"}))
    data = settings.load(tmp_path / "s.json")
    assert data["sig_bar"] == settings._sig_bar_defaults()


# ---- bridge methods -----------------------------------------------------


def test_toggle_persists_and_reveals_the_built_window(api, monkeypatch):
    from wingman.ui import sigbar

    created = []

    def fake_create(inner):
        created.append(True)
        win = SigBarWindow()
        inner._sigbar_window = win
        return win

    monkeypatch.setattr(sigbar, "create", fake_create)
    api._sigbar_window = None
    assert api.toggle_sig_bar(True)["applied"] is True
    assert api._state.settings["sig_bar"]["enabled"] is True
    assert created == [True]
    # Built hidden by create, revealed by the toggle: the taskbar button
    # is created at first SHOW, so this order is what keeps the bar out
    # of the taskbar and the aero preview.
    assert api._sigbar_window.hidden is False


def test_toggle_off_hides_the_existing_window_without_destroying_it(api):
    api.toggle_sig_bar(True)
    assert api._sigbar_window.hidden is False
    api.toggle_sig_bar(False)
    assert api._sigbar_window.hidden is True
    assert api._sigbar_window.alive is True
    assert api._state.settings["sig_bar"]["enabled"] is False


def test_toggle_pushes_state_to_both_pages(api):
    api.toggle_sig_bar(True)
    assert len(state_pushes(api._window)) == 1
    assert len(state_pushes(api._sigbar_window)) == 1


def test_save_sig_bar_persists_ints_and_ignores_junk(api):
    api.save_sig_bar_pos(12, -34)
    assert api._state.settings["sig_bar"]["x"] == 12
    assert api._state.settings["sig_bar"]["y"] == -34
    api.save_sig_bar_pos("12", None)
    assert api._state.settings["sig_bar"]["x"] == 12


def test_fit_sig_bar_resizes_and_tolerates_junk(api):
    api._sigbar_window.hidden = False  # visible: fits apply
    api.fit_sig_bar(240, 40)
    assert api._sigbar_window.resized == [(240, 40)]
    api.fit_sig_bar(0, 40)
    api.fit_sig_bar("wide", 40)
    assert api._sigbar_window.resized == [(240, 40)]
    api._sigbar_window = None
    api.fit_sig_bar(240, 40)  # must not raise


def test_fit_never_resizes_a_hidden_bar(api):
    """THE resurrection bug: pywebview's resize is a raw SetWindowPos
    carrying SWP_SHOWWINDOW, so a fit against a hidden bar SHOWS it. The
    page renders on every 3s poll -- including the pushes aimed at a bar
    the user toggled off -- and every render re-fits, which is how a
    toggled-off bar kept coming back with the GUI still reporting off."""
    api.toggle_sig_bar(True)
    api.toggle_sig_bar(False)
    api._sigbar_window.resized.clear()

    api.fit_sig_bar(240, 40)  # the poll's render, arriving while hidden

    assert api._sigbar_window.resized == []
    assert api._sigbar_window.hidden is True


def test_status_push_fans_out_to_both_pages(api):
    from wingman import hotkeys

    class RunningEngine:
        def status(self, enabled, now=None):
            return hotkeys.EngineStatus(
                state="running",
                sig="MYR",
                root="J1234",
                next_num="21",
                next_alpha="A",
            )

    api._state.engine = RunningEngine()
    api._state.settings["eve_bookmarks"]["enabled"] = True
    api._push_eve_status()
    assert any("onEveStatus" in c for c in api._window.calls)
    assert any("onEveStatus" in c for c in api._sigbar_window.calls)


def test_push_survives_a_closed_bar_window(api):
    class Dead:
        def evaluate_js(self, script):
            raise RuntimeError("window gone")

    api._sigbar_window = Dead()
    api._push("onSigBarState", {"enabled": False})  # must not raise


def test_restore_is_a_noop_while_disabled(api, monkeypatch):
    from wingman.ui import sigbar

    def boom(inner):
        raise AssertionError("restore must not build the window while off")

    monkeypatch.setattr(sigbar, "create", boom)
    sigbar.restore(api)  # settings default to enabled=False


# ---- a window destroyed out from under the GUI ----------------------------
#
# A destroyed pywebview window leaves the Python object behind with all
# its attributes, so calls at it report success at a corpse. The liveness
# check is IsWindow on the HWND (faked here as .alive); the aero-preview
# close that could trigger this is gone with the aero preview itself,
# but any teardown route gets the same recovery.


class _ClosedSigBarWindow(SigBarWindow):
    """A SigBarWindow whose window has been destroyed."""

    def __init__(self):
        super().__init__()
        self.alive = False


def test_toggle_recreates_the_window_after_an_external_close(api, monkeypatch):
    """Toggle ON after the window was destroyed externally must rebuild
    it, not report success at the corpse."""
    from wingman.ui import sigbar

    created = []

    def fake_create(inner):
        created.append(True)
        win = SigBarWindow()
        inner._sigbar_window = win
        return win

    monkeypatch.setattr(sigbar, "create", fake_create)
    api._sigbar_window = _ClosedSigBarWindow()

    assert api.toggle_sig_bar(True)["applied"] is True
    assert created == [True]  # rebuilt
    assert api._sigbar_window.hidden is False  # and revealed


def test_toggle_off_ignores_a_dead_window_without_error(api):
    """Hiding a corpse is skipped rather than performed: the persisted
    state still goes False, and the next ON rebuilds."""
    api._sigbar_window = _ClosedSigBarWindow()
    api.toggle_sig_bar(False)
    assert api._state.settings["sig_bar"]["enabled"] is False
    assert api._sigbar_window.alive is False  # never revived by a hide


def test_a_live_window_still_counts_as_alive(api):
    api.toggle_sig_bar(True)
    assert api._sig_bar_alive(api._sigbar_window) is True


# ---- focus gate --------------------------------------------------------


def _scoped(api, monkeypatch, focused):
    """Point eve_bookmarks at two checked characters and fake the focus.

    Alice is checked, Bob is not; `focused` is the full window title the
    gate should believe is foreground (None = a non-EVE foreground).
    """
    from wingman import settings as settings_mod

    settings_mod.update_section(
        api._state.settings,
        "eve_bookmarks",
        {"windows": {"EVE - Alice": True, "EVE - Bob": False}},
    )
    from wingman import evewindows

    monkeypatch.setattr(evewindows, "focused_eve_title", lambda: focused)
    return api


def test_gate_hides_the_bar_when_an_unchecked_client_holds_focus(api, monkeypatch):
    api.toggle_sig_bar(True)  # arms the timer; revealed by the toggle
    try:
        _scoped(api, monkeypatch, "EVE - Bob")
        api._apply_sig_bar_focus_gate()
        assert api._sigbar_window.hidden is True
    finally:
        api.toggle_sig_bar(False)  # disarm so no timer outlives the test


def test_gate_hides_the_bar_when_no_eve_client_holds_focus(api, monkeypatch):
    api.toggle_sig_bar(True)
    try:
        _scoped(api, monkeypatch, None)
        api._apply_sig_bar_focus_gate()
        assert api._sigbar_window.hidden is True
    finally:
        api.toggle_sig_bar(False)


def test_gate_reveals_the_bar_when_a_checked_client_holds_focus(api, monkeypatch):
    api._sigbar_window.hidden = True
    api.toggle_sig_bar(True)
    try:
        _scoped(api, monkeypatch, "EVE - Alice")
        api._sigbar_window.hidden = True  # as if the gate hid it earlier
        api._apply_sig_bar_focus_gate()
        assert api._sigbar_window.hidden is False
    finally:
        api.toggle_sig_bar(False)


def test_gate_is_inert_with_an_empty_window_map(api, monkeypatch):
    """No checkboxes ever touched: the bar keeps its long-shipping
    always-show behaviour, even with nothing EVE in the foreground."""
    api.toggle_sig_bar(True)
    try:
        from wingman import evewindows

        monkeypatch.setattr(evewindows, "focused_eve_title", lambda: None)
        api._apply_sig_bar_focus_gate()
        assert api._sigbar_window.hidden is False
    finally:
        api.toggle_sig_bar(False)


def test_gate_leaves_a_disabled_bar_hidden(api, monkeypatch):
    """The gate never shows a bar the user toggled off -- enabled is the
    master switch, focus only scopes an enabled bar."""
    _scoped(api, monkeypatch, "EVE - Alice")
    api._sigbar_window.hidden = True
    api._apply_sig_bar_focus_gate()
    assert api._sigbar_window.hidden is True


def test_toggle_on_applies_the_gate_immediately(api, monkeypatch):
    """Enabling while a non-allowed client holds the foreground must not
    flash the bar for one cadence before hiding it."""
    _scoped(api, monkeypatch, "EVE - Bob")
    api.toggle_sig_bar(True)
    try:
        assert api._sigbar_window.hidden is True
    finally:
        api.toggle_sig_bar(False)


def test_toggle_arms_and_disarms_the_focus_timer(api):
    api.toggle_sig_bar(True)
    armed = api._sigbar_focus_timer
    assert armed is not None and armed.is_alive()
    api.toggle_sig_bar(False)
    assert api._sigbar_focus_timer is None
