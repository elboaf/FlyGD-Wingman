"""Standalone Fleet Bar window, bridge lifecycle, and payload contract."""

import inspect
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.fakes import FakeWindow
from tests.test_api import make_api
from wingman.telemetry.model import FleetRow, FleetSnapshot, StreamHealth


class FleetWindow(FakeWindow):
    def __init__(self):
        super().__init__()
        self.hidden = False
        self.resized = []
        self.width = 0
        self.height = 0

    def show(self):
        self.hidden = False

    def hide(self):
        self.hidden = True

    def resize(self, width, height):
        self.resized.append((width, height))
        self.width = width
        self.height = height


class FakeTelemetry:
    def __init__(self):
        self.reconciled = 0

    def reconcile(self):
        self.reconciled += 1

    def stop(self):
        pass


@pytest.fixture
def api(tmp_path):
    telemetry = FakeTelemetry()
    built = make_api(tmp_path, telemetry=telemetry)
    built._fleetbar_window = FleetWindow()
    return built


def _fleet_scripts(window):
    scripts = getattr(window, "calls", getattr(window, "evaluated", []))
    return [call for call in scripts if "onFleetSnapshot" in call]


def test_toggle_persists_reconciles_and_creates_the_window(tmp_path, monkeypatch):
    from wingman.ui import fleetbar

    telemetry = FakeTelemetry()
    api = make_api(tmp_path, telemetry=telemetry)
    api._fleetbar_window = None
    created = []

    def fake_create(inner, hidden=True):
        created.append(hidden)
        inner._fleetbar_window = FleetWindow()
        return inner._fleetbar_window

    monkeypatch.setattr(fleetbar, "create", fake_create)

    result = api.toggle_fleet_bar(True)

    assert result["applied"] is True
    assert api._state.settings["fleet_bar"]["enabled"] is True
    assert telemetry.reconciled == 1
    assert created == [False]
    assert _fleet_scripts(api._fleetbar_window)


def test_toggle_pushes_one_authoritative_state_to_main_page(api):
    api.toggle_fleet_bar(True)

    scripts = getattr(api._window, "evaluated", [])
    state_pushes = [script for script in scripts if "onFleetBarState" in script]
    assert len(state_pushes) == 1
    assert api.fleet_bar_settings()["enabled"] is True


def test_failed_first_show_rolls_back_enabled_state(tmp_path, monkeypatch):
    from wingman.ui import fleetbar

    telemetry = FakeTelemetry()
    api = make_api(tmp_path, telemetry=telemetry)

    def fail_create(_api, hidden=True):
        raise RuntimeError("WebView unavailable")

    monkeypatch.setattr(fleetbar, "create", fail_create)

    result = api.toggle_fleet_bar(True)

    assert result["applied"] is False
    assert api._state.settings["fleet_bar"]["enabled"] is False
    assert telemetry.reconciled == 2


def test_reenable_does_not_flash_previous_generation_rows(api):
    api._receive_fleet_snapshot(
        FleetSnapshot(
            rows=(FleetRow("Old Session", 99),),
            stream_health=StreamHealth(state="active"),
        )
    )

    api.toggle_fleet_bar(False)
    api._fleetbar_window.calls.clear()
    api.toggle_fleet_bar(True)

    script = _fleet_scripts(api._fleetbar_window)[-1]
    payload = json.loads(script.split("window.onFleetSnapshot(", 1)[1][:-1])
    assert payload["rows"] == []


def test_toggle_off_hides_existing_window_and_reconciles(api):
    api._state.settings.setdefault("fleet_bar", {})["enabled"] = True

    api.toggle_fleet_bar(False)

    assert api._fleetbar_window.hidden is True
    assert api._state.settings["fleet_bar"]["enabled"] is False
    assert api._telemetry.reconciled == 1


def test_snapshot_payload_preserves_rows_status_and_diagnostics(api):
    snapshot = FleetSnapshot(
        rows=(
            FleetRow("Alice", 43, ("SCRAM/POINT",)),
            FleetRow("Bravo", None, (), "NO LOG"),
        ),
        stream_health=StreamHealth(state="stale", detail="3.2s since poll"),
        metric_error="clock skew",
    )

    api._receive_fleet_snapshot(snapshot)

    script = _fleet_scripts(api._fleetbar_window)[-1]
    payload = json.loads(script.split("window.onFleetSnapshot(", 1)[1][:-1])
    assert payload == {
        "rows": [
            {
                "character": "Alice",
                "dps": 43,
                "ewar": ["SCRAM/POINT"],
                "log_status": None,
            },
            {
                "character": "Bravo",
                "dps": None,
                "ewar": [],
                "log_status": "NO LOG",
            },
        ],
        "stream_health": {"state": "stale", "detail": "3.2s since poll"},
        "metric_error": "clock skew",
    }


def test_snapshot_push_targets_only_the_fleet_window(api):
    snapshot = FleetSnapshot(
        rows=(FleetRow("Alice", 10),),
        stream_health=StreamHealth(state="active"),
    )

    api._receive_fleet_snapshot(snapshot)

    assert _fleet_scripts(api._fleetbar_window)
    assert not _fleet_scripts(api._window)


def test_shutdown_detaches_fleet_subscription(api):
    detached = []
    api._fleet_unsubscribe = lambda: detached.append(True)

    api.shutdown_previews()

    assert detached == [True]
    assert api._fleet_unsubscribe is None


def test_failed_restore_rolls_back_enabled_state(api, monkeypatch):
    from wingman.ui import fleetbar

    api._state.settings.setdefault("fleet_bar", {})["enabled"] = True
    api._fleetbar_window = None
    monkeypatch.setattr(
        fleetbar,
        "create",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("broken")),
    )

    fleetbar.restore(api)

    assert api._state.settings["fleet_bar"]["enabled"] is False


def test_restore_creates_hidden_then_reveals_with_current_snapshot(api, monkeypatch):
    from wingman.ui import fleetbar

    api._state.settings.setdefault("fleet_bar", {})["enabled"] = True
    api._fleetbar_window = None
    created = []

    def fake_create(inner, hidden=True):
        created.append(hidden)
        inner._fleetbar_window = FleetWindow()
        inner._fleetbar_window.hidden = hidden
        return inner._fleetbar_window

    class ImmediateTimer:
        def __init__(self, _delay, callback):
            self._callback = callback

        def start(self):
            self._callback()

    monkeypatch.setattr(fleetbar, "create", fake_create)
    monkeypatch.setattr(fleetbar.threading, "Timer", ImmediateTimer)

    fleetbar.restore(api)
    fleetbar.restore(api)

    assert created == [True]
    assert api._fleetbar_window.hidden is False
    assert _fleet_scripts(api._fleetbar_window)


def test_save_position_and_fit_ignore_invalid_values(api):
    api.save_fleet_bar_pos(25, -40)
    assert api._state.settings["fleet_bar"]["x"] == 25
    assert api._state.settings["fleet_bar"]["y"] == -40

    api.fit_fleet_bar(380, 112)
    api.fit_fleet_bar(0, "bad")
    assert api._fleetbar_window.resized == [(380, 112)]


def test_create_is_frameless_pinned_hidden_and_full_surface_drag(tmp_path, monkeypatch):
    from wingman.ui import fleetbar

    calls = {}

    def create_window(title, url, **kwargs):
        calls.update(title=title, url=url, kwargs=kwargs)
        return SimpleNamespace()

    monkeypatch.setitem(
        sys.modules, "webview", SimpleNamespace(create_window=create_window)
    )
    api = make_api(tmp_path)

    fleetbar.create(api)

    kwargs = calls["kwargs"]
    assert kwargs["frameless"] is True
    assert kwargs["easy_drag"] is False
    assert kwargs["on_top"] is True
    assert kwargs["hidden"] is True
    assert kwargs["min_size"] == (1, 1)
    assert calls["url"].endswith("fleetbar.html")


def test_settings_and_status_strip_expose_the_same_fleet_toggle():
    from wingman.ui import window as window_mod

    html = (window_mod._web_dir() / "index.html").read_text(encoding="utf-8")
    js = (window_mod._web_dir() / "previews.js").read_text(encoding="utf-8")
    app = (window_mod._web_dir() / "app.js").read_text(encoding="utf-8")

    assert 'id="fleetbar-enabled"' in html
    assert 'id="btn-fleetbar"' in html
    assert "WM.handle('onFleetBarState'" in js
    assert "'onFleetBarState'" in app
    assert js.count("toggle_fleet_bar") == 2
    assert js.index("WM.handle('onFleetBarState'") < js.index("var host =")


def test_superseded_alert_poller_and_preview_timer_are_gone():
    from wingman.alerts import service as alert_module
    from wingman.preview import host as preview_host
    from wingman.preview import win32 as preview_win32

    alert_source = inspect.getsource(alert_module)
    host_source = inspect.getsource(preview_host)
    assert "class AlertService" not in alert_source
    assert not (Path(__file__).parents[1] / "wingman/alerts/tailer.py").exists()
    assert "SWEEP_TIMER_ID" not in host_source
    assert "WM_APP_SWEEP_NOW" not in vars(preview_win32)
    assert "self._sweep(" not in host_source


def test_main_wires_subscription_restore_and_shutdown_destruction():
    from wingman import __main__ as main_mod

    source = inspect.getsource(main_mod.main)
    assert "telemetry.subscribe_fleet" in source
    assert "fleetbar.restore(api)" in source
    assert '("_fleetbar_window", "Fleet Bar")' in source


def test_fleet_page_is_display_only_and_carries_stable_columns():
    from wingman.ui import window as window_mod

    html = (window_mod._web_dir() / "fleetbar.html").read_text(encoding="utf-8")
    js = (window_mod._web_dir() / "fleetbar.js").read_text(encoding="utf-8")

    assert "pywebview-drag-region" in html
    assert "CHARACTER" in html and "DPS" in html and "INCOMING" in html
    assert "<button" not in html and "<input" not in html
    assert "window.onFleetSnapshot" in js
    assert "Waiting for EVE clients" in html
    assert "flex: none" in html  # overrides title-bar drag-region geometry
    assert "shell.offsetHeight" in js  # content can shrink with the roster
    assert "SCRAM/POINT" not in js  # rendered from telemetry, never guessed here
