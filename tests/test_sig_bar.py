"""The floating sig bar: settings section, bridge methods, push fan-out.

Headless throughout, like the rest of the Api tests: the window is a fake
and sigbar.create is monkeypatched, so nothing here needs pywebview's
event loop (which does not exist off the GUI thread anyway).
"""

import json

import pytest

from tests.fakes import FakeWindow
from wingman import settings


class SigBarWindow(FakeWindow):
    """A FakeWindow plus the window-level calls the bar's bridge makes:
    show/hide (toggle) and resize (the page's fit round-trip)."""

    def __init__(self):
        super().__init__()
        self.hidden = False
        self.resized = []

    def show(self):
        self.hidden = False

    def hide(self):
        self.hidden = True

    def resize(self, width, height):
        self.resized.append((width, height))


@pytest.fixture
def api(tmp_path, monkeypatch):
    from wingman.ui import api as api_mod

    monkeypatch.setattr(api_mod.paths, "settings_file", lambda: tmp_path / "s.json")
    state = api_mod.AppState(
        recording_dir=tmp_path, settings=settings.load(tmp_path / "s.json")
    )
    built = api_mod.Api(state)
    built._window = FakeWindow()
    built._sigbar_window = SigBarWindow()
    return built


def state_pushes(window):
    return [c for c in window.calls if "onSigBarState" in c]


# ---- settings section ---------------------------------------------------


def test_defaults_carry_the_sig_bar_section(tmp_path):
    data = settings.load(tmp_path / "s.json")  # absent file -> fresh defaults
    assert data["sig_bar"] == {
        "enabled": False,
        "bg_color": "#14101c",
        "opacity": 90,
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
        "bg_color": "purple",  # not #rrggbb -> default
        "opacity": 500,  # clamped, not rejected
        "x": "120",  # a string coordinate -> None (default placement)
        "y": True,  # bool is an int; must not become a coordinate
    }
    got = settings.validated_sig_bar(raw)
    assert got["enabled"] is False
    assert got["bg_color"] == "#14101c"
    assert got["opacity"] == 100
    assert got["x"] is None
    assert got["y"] is None


def test_validated_sig_bar_accepts_a_good_document():
    raw = {
        "enabled": True,
        "bg_color": "#1D1030",
        "opacity": 0,
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


def test_toggle_persists_and_creates_the_window_shown(api, monkeypatch):
    from wingman.ui import sigbar

    created = []

    def fake_create(inner, hidden=True):
        created.append(hidden)
        win = SigBarWindow()
        inner._sigbar_window = win
        return win

    monkeypatch.setattr(sigbar, "create", fake_create)
    api._sigbar_window = None
    assert api.toggle_sig_bar(True)["applied"] is True
    assert api._state.settings["sig_bar"]["enabled"] is True
    assert created == [False]


def test_toggle_off_hides_the_existing_window_without_destroying_it(api):
    api.toggle_sig_bar(True)  # the window already exists in the fixture
    assert api._sigbar_window.hidden is True
    assert api._state.settings["sig_bar"]["enabled"] is False


def test_toggle_pushes_state_to_both_pages(api):
    api.toggle_sig_bar(True)
    assert len(state_pushes(api._window)) == 1
    assert len(state_pushes(api._sigbar_window)) == 1


def test_set_sig_bar_style_rejects_a_non_colour(api):
    before = dict(api._state.settings["sig_bar"])
    res = api.set_sig_bar_style("purple", 50)
    assert res["applied"] is False
    assert api._state.settings["sig_bar"] == before
    assert state_pushes(api._window) == []


def test_set_sig_bar_style_clamps_and_persists(api):
    res = api.set_sig_bar_style("#1d1030", 140)
    assert res["applied"] is True
    section = api._state.settings["sig_bar"]
    assert section["bg_color"] == "#1d1030"
    assert section["opacity"] == 100
    payload = json.loads(state_pushes(api._window)[-1].split("(", 1)[1].rstrip(")"))
    assert payload["bg_color"] == "#1d1030"
    assert payload["opacity"] == 100


def test_save_sig_bar_persists_ints_and_ignores_junk(api):
    api.save_sig_bar_pos(12, -34)
    assert api._state.settings["sig_bar"]["x"] == 12
    assert api._state.settings["sig_bar"]["y"] == -34
    api.save_sig_bar_pos("12", None)
    assert api._state.settings["sig_bar"]["x"] == 12


def test_fit_sig_bar_resizes_and_tolerates_junk(api):
    api.fit_sig_bar(240, 40)
    assert api._sigbar_window.resized == [(240, 40)]
    api.fit_sig_bar(0, 40)
    api.fit_sig_bar("wide", 40)
    assert api._sigbar_window.resized == [(240, 40)]
    api._sigbar_window = None
    api.fit_sig_bar(240, 40)  # must not raise


def test_status_push_fans_out_to_both_pages(api):
    from wingman import hotkeys

    class RunningEngine:
        def status(self, enabled, now=None):
            return hotkeys.EngineStatus(
                state="running", sig="MYR", root="J1234",
                next_num="21", next_alpha="A",
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

    def boom(inner, hidden=True):
        raise AssertionError("restore must not build the window while off")

    monkeypatch.setattr(sigbar, "create", boom)
    sigbar.restore(api)  # settings default to enabled=False
