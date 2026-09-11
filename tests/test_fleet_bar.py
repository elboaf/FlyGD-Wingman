"""Standalone Fleet Bar window, bridge lifecycle, and payload contract."""

import inspect
import json
import re
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.fakes import FakeWindow
from tests.test_api import decode_payload
from tests.test_api import make_api as _make_api
from wingman import settings
from wingman.telemetry.model import FleetRow, FleetSnapshot, StreamHealth
from wingman.ui import chrome


def make_api(*args, **kwargs):
    """These contract tests drain explicitly; worker races live in their own file."""
    api = _make_api(*args, **kwargs)
    api._start_fleet_presentation = lambda: True
    return api


class FleetWindow(FakeWindow):
    def __init__(self, *, width=0, height=0, x=0, y=0, work_area=None):
        super().__init__()
        self.hidden = False
        self.resized = []
        self.moved = []
        self.width = width
        self.height = height
        self.x = x
        self.y = y
        self.work_area = work_area

    def show(self):
        self.hidden = False

    def hide(self):
        self.hidden = True

    def resize(self, width, height):
        self.resized.append((width, height))
        self.width = width
        self.height = height

    def move(self, x, y):
        self.moved.append((x, y))
        self.x = x
        self.y = y


class _Handle:
    def __init__(self, value):
        self._value = value

    def ToInt64(self):
        return self._value


class _Native:
    def __init__(self, value):
        self.Handle = _Handle(value)


def _attach_hwnd(window, hwnd):
    window.native = _Native(hwnd)
    return window


class _FakeUser32:
    def __init__(
        self,
        *,
        foreground=0,
        foreground_after_set=None,
        styles=None,
        alive=(),
        visible=None,
        titles=None,
    ):
        self._foreground = foreground
        self._foreground_after_set = foreground_after_set
        self.styles = dict(styles or {})
        self.alive = set(alive)
        self.visible = dict(visible or {})
        self.titles = dict(titles or {})
        self.calls = []

    def GetForegroundWindow(self):
        self.calls.append(("GetForegroundWindow",))
        return self._foreground

    def GetWindowLongW(self, hwnd, index):
        self.calls.append(("GetWindowLongW", hwnd, index))
        return self.styles.get(hwnd, 0)

    def SetWindowLongW(self, hwnd, index, style):
        self.calls.append(("SetWindowLongW", hwnd, index, style))
        self.styles[hwnd] = style
        return style

    def SetForegroundWindow(self, hwnd):
        self.calls.append(("SetForegroundWindow", hwnd))
        if callable(self._foreground_after_set):
            self._foreground = self._foreground_after_set(hwnd)
        elif self._foreground_after_set is not None:
            self._foreground = self._foreground_after_set
        else:
            self._foreground = hwnd
        return 1

    def IsWindow(self, hwnd):
        self.calls.append(("IsWindow", hwnd))
        return hwnd in self.alive

    def IsWindowVisible(self, hwnd):
        self.calls.append(("IsWindowVisible", hwnd))
        return bool(self.visible.get(hwnd))

    def GetWindowTextLengthW(self, hwnd):
        self.calls.append(("GetWindowTextLengthW", hwnd))
        return len(self.titles.get(hwnd, ""))

    def GetWindowTextW(self, hwnd, buffer, length):
        self.calls.append(("GetWindowTextW", hwnd, length))
        buffer.value = self.titles.get(hwnd, "")[: max(0, length - 1)]
        return len(buffer.value)


class FakeTelemetry:
    def __init__(self):
        self.reconciled = 0
        self.subscribers = []
        self.generation = 0
        self.latest = FleetSnapshot(
            rows=(),
            stream_health=StreamHealth(state="stopped"),
            activation_generation=0,
        )

    def reconcile(self):
        self.reconciled += 1
        self.generation += 1
        return self.generation

    def subscribe_fleet(self, callback):
        self.subscribers.append(callback)
        return lambda: self.subscribers.remove(callback)

    def requested_fleet_generation(self):
        return self.generation

    def snapshot(self):
        return self.latest

    def stop(self):
        pass


@pytest.fixture(autouse=True)
def _headless_fleet_window_helpers(monkeypatch):
    """Keep fake windows independent of the host running the test suite."""
    from wingman.ui import fleetbar

    monkeypatch.setattr(
        fleetbar,
        "is_alive",
        lambda bar: bar is not None and getattr(bar, "alive", True),
    )

    def reveal(bar):
        if bar is not None:
            bar.show()

    def hide(bar):
        if bar is not None:
            bar.hide()

    monkeypatch.setattr(fleetbar, "reveal_bar", reveal)
    monkeypatch.setattr(fleetbar, "hide_bar", hide)
    monkeypatch.setattr(
        fleetbar,
        "is_visible",
        lambda bar: bool(
            bar is not None
            and getattr(bar, "alive", True)
            and not getattr(bar, "hidden", False)
        ),
        raising=False,
    )


@pytest.fixture
def api(tmp_path):
    telemetry = FakeTelemetry()
    built = make_api(tmp_path, telemetry=telemetry)
    built._state.settings["fleet_bar"] = settings.validated_fleet_bar(
        {"enabled": False}
    )
    built._fleetbar_window = FleetWindow(width=500, height=90, x=0, y=0)
    built._fleetbar_page_id = "a" * 64
    built._fleetbar_ready = True
    built._fleetbar_resize_insets = chrome.ResizeInsets(0, 0, 0, 0)
    built._fleetbar_resize_enabled = False
    built._fleetbar_applied_x = 0
    built._fleetbar_applied_y = 0
    built._fleetbar_applied_outer_width = 500
    built._fleetbar_applied_outer_height = 90
    return built


def _fleet_scripts(window):
    scripts = getattr(window, "calls", getattr(window, "evaluated", []))
    return [call for call in scripts if "onFleetSnapshot" in call]


def _fleet_state_pushes(api):
    scripts = getattr(api._window, "calls", getattr(api._window, "evaluated", []))
    return [call for call in scripts if "onFleetBarState" in call]


def _clear_scripts(window):
    getattr(window, "calls", getattr(window, "evaluated", [])).clear()


def test_snapshot_from_retired_activation_is_rejected(api):
    """A late dispatcher callback must not repopulate a retired generation."""
    api._fleet_expected_generation = 2
    stale = FleetSnapshot(
        rows=(FleetRow("Old Session", 99),),
        stream_health=StreamHealth(state="active"),
        activation_generation=1,
    )

    api._receive_fleet_snapshot(stale)

    assert api._fleet_snapshot is None


def test_callback_during_toggle_handoff_cannot_restore_old_snapshot(api):
    """Closing acceptance precedes the reconcile callback without sleep races."""
    stale = FleetSnapshot(
        rows=(FleetRow("Old Session", 99),),
        stream_health=StreamHealth(state="active"),
        activation_generation=1,
    )
    callback_finished = threading.Event()
    api._state.settings.setdefault("fleet_bar", {})["enabled"] = True
    api._fleet_expected_generation = 1
    api._telemetry.generation = 1

    def reconcile():
        callback = threading.Thread(
            target=lambda: (api._receive_fleet_snapshot(stale), callback_finished.set())
        )
        callback.start()
        assert callback_finished.wait(5)
        callback.join(5)
        api._telemetry.generation = 2
        return 2

    api._telemetry.reconcile = reconcile
    api.toggle_fleet_bar(False)

    assert api._fleet_expected_generation == 2
    assert api._fleet_snapshot is None


def test_failed_toggle_persistence_restores_prior_acceptance(api, monkeypatch):
    """A failed settings save restores the generation and accepted display state."""
    from wingman.ui import api as api_mod

    prior = FleetSnapshot(
        rows=(FleetRow("Alice", 10),),
        stream_health=StreamHealth(state="active"),
        activation_generation=1,
    )
    api._fleet_expected_generation = 1
    api._fleet_snapshot = prior
    api._fleet_roster_signature = ("Alice",)

    def fail_save(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(api_mod.settings_mod, "_save_locked", fail_save)
    result = api.toggle_fleet_bar(True)

    assert result["applied"] is False
    assert api._fleet_expected_generation == 1
    assert api._fleet_snapshot is prior
    assert api._fleet_roster_signature == ("Alice",)


def test_persisted_enabled_startup_installs_generation_before_latest_snapshot(api):
    """Startup samples the coordinator only after reserving Fleet's generation."""
    latest = FleetSnapshot(
        rows=(FleetRow("Alice", 10),),
        stream_health=StreamHealth(state="active"),
        activation_generation=1,
    )
    api._state.settings.setdefault("fleet_bar", {})["enabled"] = True
    api._telemetry.latest = latest

    api.start_previews_if_enabled()

    assert api._fleet_expected_generation == 1
    assert api._fleet_snapshot is latest


def test_enabled_fleet_keeps_remembered_names_known_before_first_roster(api, tmp_path):
    """The coordinator must not turn an activation's synthetic empty into Offline."""
    from tests.test_telemetry_coordinator import _harness, _roster

    harness = _harness(tmp_path, fleet=True)
    telemetry = harness.coordinator
    api._telemetry = telemetry
    api._state.settings["fleet_bar"].update(enabled=True, seen=["Alice"])
    telemetry.subscribe_fleet(api._receive_fleet_snapshot)

    api.start_previews_if_enabled()
    telemetry.dispatch_once(0)

    assert api._fleet_snapshot is None
    assert api.fleet_bar_settings()["characters"] == [
        {"name": "Alice", "running": None, "visible": True}
    ]

    harness.discovery.publish(_roster())
    harness.pump()

    assert api.fleet_bar_settings()["characters"] == [
        {"name": "Alice", "running": False, "visible": True}
    ]


def test_unexpected_reconcile_error_uses_requested_generation(api):
    """After a persisted enable, infrastructure failure leaves Fleet waiting."""
    api._telemetry.generation = 2

    def fail_reconcile():
        raise RuntimeError("unexpected")

    api._telemetry.reconcile = fail_reconcile
    result = api.toggle_fleet_bar(True)

    assert result["applied"] is True
    assert api._fleet_expected_generation == 2
    assert api._fleet_snapshot is None


def test_toggle_persists_reconciles_and_creates_the_window(tmp_path, monkeypatch):
    from wingman.ui import fleetbar

    telemetry = FakeTelemetry()
    api = make_api(tmp_path, telemetry=telemetry)
    api._fleetbar_window = None
    created = []

    def fake_create(inner, hidden=True):
        created.append(hidden)
        inner._fleetbar_window = FleetWindow()
        inner._fleetbar_page_id = PAGE_A
        inner._fleetbar_window.hidden = hidden
        return inner._fleetbar_window

    monkeypatch.setattr(fleetbar, "create", fake_create)

    result = api.toggle_fleet_bar(True)

    assert result["applied"] is True
    assert api._state.settings["fleet_bar"]["enabled"] is True
    assert telemetry.reconciled == 1
    assert created == [True]
    assert api._fleetbar_window.hidden is True
    api.fleet_bar_ready(api._fleetbar_page_id)
    assert api._fleetbar_window.hidden is False


def test_concurrent_enable_requests_create_only_one_window(tmp_path, monkeypatch):
    from wingman.ui import fleetbar

    api = make_api(tmp_path, telemetry=FakeTelemetry())
    entered = threading.Event()
    release = threading.Event()
    created = []

    def blocking_create(inner, hidden=True):
        created.append(hidden)
        entered.set()
        assert release.wait(5)
        inner._fleetbar_window = FleetWindow()
        inner._fleetbar_page_id = PAGE_A
        return inner._fleetbar_window

    monkeypatch.setattr(fleetbar, "create", blocking_create)
    first = threading.Thread(target=lambda: api.toggle_fleet_bar(True))
    second = threading.Thread(target=lambda: api.toggle_fleet_bar(True))
    first.start()
    assert entered.wait(5)
    second.start()
    assert created == [True]
    release.set()
    first.join(5)
    second.join(5)

    assert not first.is_alive() and not second.is_alive()
    assert created == [True]


def test_toggle_refuses_to_create_after_shutdown_starts(api, monkeypatch):
    from wingman.ui import fleetbar

    api._fleetbar_window = None
    api._fleetbar_quitting = True
    monkeypatch.setattr(
        fleetbar,
        "create",
        lambda *_args, **_kwargs: pytest.fail("must not create while quitting"),
    )

    result = api.toggle_fleet_bar(True)

    assert result["applied"] is False
    assert not api._state.settings.get("fleet_bar", {}).get("enabled", False)


def test_toggle_pushes_one_authoritative_state_to_main_page(api):
    api.toggle_fleet_bar(True)
    api._fleet_worker.iterate_once()

    scripts = getattr(api._window, "evaluated", [])
    state_pushes = [script for script in scripts if "onFleetBarState" in script]
    assert len(state_pushes) == 1
    assert api.fleet_bar_settings()["enabled"] is True


def test_failed_first_show_rolls_back_enabled_state(tmp_path, monkeypatch):
    from wingman.ui import api as api_mod
    from wingman.ui import fleetbar

    telemetry = FakeTelemetry()
    api = make_api(tmp_path, telemetry=telemetry)
    stale = FleetSnapshot(
        rows=(FleetRow("Old Session", 99),),
        stream_health=StreamHealth(state="active"),
        activation_generation=1,
    )
    accepted_during_rollback = []
    original_save = api_mod.settings_mod._save_locked
    saves = 0

    def save_with_late_callback(*args, **kwargs):
        nonlocal saves
        saves += 1
        if saves == 2:
            api._receive_fleet_snapshot(stale)
            accepted_during_rollback.append(api._fleet_snapshot)
        return original_save(*args, **kwargs)

    def fail_create(_api, hidden=True):
        raise RuntimeError("WebView unavailable")

    monkeypatch.setattr(api_mod.settings_mod, "_save_locked", save_with_late_callback)
    monkeypatch.setattr(fleetbar, "create", fail_create)

    result = api.toggle_fleet_bar(True)

    assert result["applied"] is False
    assert api._state.settings["fleet_bar"]["enabled"] is False
    assert telemetry.reconciled == 2
    assert accepted_during_rollback == [None]


def test_creation_failure_with_failed_rollback_reopens_current_generation(
    api, monkeypatch
):
    """A failed rollback cannot strand subscribers behind the rejecting sentinel."""
    from wingman.ui import api as api_mod
    from wingman.ui import fleetbar

    api._fleetbar_window = None
    original_save = api_mod.settings_mod._save_locked
    saves = 0

    def fail_only_rollback(*args, **kwargs):
        nonlocal saves
        saves += 1
        if saves == 2:
            raise OSError("disk full")
        return original_save(*args, **kwargs)

    def reconcile():
        api._telemetry.reconciled += 1
        if api._state.settings["fleet_bar"]["enabled"]:
            api._telemetry.generation = max(api._telemetry.generation, 1)
        return api._telemetry.generation

    monkeypatch.setattr(api_mod.settings_mod, "_save_locked", fail_only_rollback)
    monkeypatch.setattr(
        fleetbar,
        "create",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("broken")),
    )
    api._telemetry.reconcile = reconcile

    result = api.toggle_fleet_bar(True)
    api._fleet_worker.iterate_once()

    assert result == {
        "applied": False,
        "persisted": False,
        "error": "The Fleet Bar could not be opened.",
    }
    assert saves == 2
    assert api._state.settings["fleet_bar"]["enabled"] is True
    assert api._fleet_expected_generation == api._telemetry.requested_fleet_generation()
    assert api._fleet_snapshot is None
    state_push = [
        script for script in api._window.evaluated if "onFleetBarState" in script
    ][-1]
    state = decode_payload(state_push.split("window.onFleetBarState(", 1)[1][:-1])
    assert state["enabled"] is True

    current = FleetSnapshot(
        rows=(FleetRow("Alice", 10),),
        stream_health=StreamHealth(state="active"),
        activation_generation=api._fleet_expected_generation,
    )
    api._receive_fleet_snapshot(current)

    assert api._fleet_snapshot is current


def test_reenable_does_not_flash_previous_generation_rows(api):
    api._fleet_expected_generation = 1
    api._telemetry.generation = 1
    api._receive_fleet_snapshot(
        FleetSnapshot(
            rows=(FleetRow("Old Session", 99),),
            stream_health=StreamHealth(state="active"),
            activation_generation=1,
        )
    )

    api.toggle_fleet_bar(False)
    api._fleetbar_window.calls.clear()
    api.toggle_fleet_bar(True)
    api._fleet_worker.iterate_once()

    script = _fleet_scripts(api._fleetbar_window)[-1]
    payload = json.loads(script.split("window.onFleetSnapshot(", 1)[1][:-1])
    assert payload["rows"] == []


def test_page_readiness_survives_disable_during_boot(api):
    api._state.settings.setdefault("fleet_bar", {})["enabled"] = False
    api._fleetbar_window.hidden = True
    api._fleetbar_ready = False

    api.fleet_bar_ready(api._fleetbar_page_id)
    assert api._fleetbar_ready is True
    assert api._fleetbar_window.hidden is True

    api.toggle_fleet_bar(True)
    assert api._fleetbar_window.hidden is False


def test_toggle_off_hides_existing_window_and_reconciles(api):
    api._state.settings.setdefault("fleet_bar", {})["enabled"] = True

    api.toggle_fleet_bar(False)

    assert api._fleetbar_window.hidden is True
    assert api._state.settings["fleet_bar"]["enabled"] is False
    assert api._telemetry.reconciled == 1


def test_snapshot_payload_preserves_rows_status_and_diagnostics(api):
    api._fleet_expected_generation = 1
    snapshot = FleetSnapshot(
        rows=(
            FleetRow("Alice", 43, ("SCRAM", "NEUT"), incoming_dps=17),
            FleetRow("Bravo", None, (), "NO LOG"),
        ),
        stream_health=StreamHealth(state="stale", detail="3.2s since poll"),
        metric_error="clock skew",
        activation_generation=1,
    )

    api._receive_fleet_snapshot(snapshot)
    api._fleet_worker.iterate_once()

    script = _fleet_scripts(api._fleetbar_window)[-1]
    payload = json.loads(script.split("window.onFleetSnapshot(", 1)[1][:-1])
    assert payload == {
        "rows": [
            {
                "character": "Alice",
                "outgoing_dps": 43,
                "incoming_dps": 17,
                "ewar": ["SCRAM", "NEUT"],
                "log_status": None,
            },
            {
                "character": "Bravo",
                "outgoing_dps": None,
                "incoming_dps": None,
                "ewar": [],
                "log_status": "NO LOG",
            },
        ],
        "running_count": 2,
        "revision": 1,
        "stream_health": {"state": "stale", "detail": "3.2s since poll"},
        "metric_error": "clock skew",
    }


def test_fleet_page_source_rejects_stale_revision_and_all_hidden_copy():
    from wingman.ui import window as window_mod

    html = (window_mod._web_dir() / "fleetbar.html").read_text(encoding="utf-8")
    js = (window_mod._web_dir() / "fleetbar.js").read_text(encoding="utf-8")

    assert "running_count" in js
    assert "lastRevision" in js
    assert "All running characters are hidden." in js
    assert js.index("All running characters are hidden.") < js.index("return fit();")
    assert "Waiting for EVE clients" in html


def test_fleet_page_rejects_invalid_hydration_without_erasing_newer_state():
    """Keep the lexical guard alongside the executable Fleet runtime harness."""
    from wingman.ui import window as window_mod

    js = (window_mod._web_dir() / "fleetbar.js").read_text(encoding="utf-8")
    render = js[
        js.index("function render(payload)") : js.index("window.onFleetSnapshot")
    ]
    invalid_revision = re.search(
        r"if\s*\(\s*typeof revision !== 'number'\s*\|\|\s*"
        r"!isFinite\(revision\)\s*\|\|\s*revision < 0\s*\|\|\s*"
        r"Math\.floor\(revision\) !== revision\s*\)\s*\{\s*"
        r"return Promise\.resolve\(null\);\s*\}",
        render,
    )

    assert invalid_revision is not None
    assert invalid_revision.start() < render.index("var rows")
    hydration = js[js.index("Promise.all([send('fleet_bar_snapshot')") :]
    assert "render(values[0] || {})" not in hydration
    assert "if (!values[0]) return null;" in hydration
    assert "return render(values[0]);" in hydration


def test_fleet_page_changes_empty_live_text_only_for_a_new_message():
    """Repeated cadence renders must not reannounce the same role=status copy."""
    from wingman.ui import window as window_mod

    js = (window_mod._web_dir() / "fleetbar.js").read_text(encoding="utf-8")
    render = js[
        js.index("function render(payload)") : js.index("window.onFleetSnapshot")
    ]

    assert "var emptyText = runningCount > 0" in render
    assert re.search(
        r"if\s*\(empty\.textContent !== emptyText\)\s*\{\s*"
        r"empty\.textContent = emptyText;\s*\}",
        render,
    )
    assert render.count("empty.textContent =") == 1

    assert "var noteText = detail || '';" in render
    assert re.search(
        r"if\s*\(note\.textContent !== noteText\)\s*\{\s*"
        r"note\.textContent = noteText;\s*\}",
        render,
    )
    assert render.count("note.textContent =") == 1


def test_fleet_settings_groups_running_offline_and_hidden(api):
    api._state.settings["fleet_bar"].update(
        seen=["Bravo", "Alice", "Offline"], hidden=["Bravo"]
    )
    api._fleet_expected_generation = 3
    api._receive_fleet_snapshot(
        FleetSnapshot(
            rows=(FleetRow("Bravo", 0), FleetRow("Alice", 10)),
            stream_health=StreamHealth(state="active"),
            activation_generation=3,
        )
    )

    assert api.fleet_bar_settings()["characters"] == [
        {"name": "Alice", "running": True, "visible": True},
        {"name": "Bravo", "running": True, "visible": False},
        {"name": "Offline", "running": False, "visible": True},
    ]


def test_fleet_settings_reports_unknown_when_consumer_is_inactive(api):
    api._state.settings["fleet_bar"]["seen"] = ["Alice"]
    api._fleet_snapshot = None

    assert api.fleet_bar_settings()["characters"] == [
        {"name": "Alice", "running": None, "visible": True}
    ]


def test_fleet_roster_persists_current_pending_then_prior_without_duplicates(api):
    api._state.settings["fleet_bar"]["seen"] = ["Persisted", "Current"]
    api._fleet_roster.pending = dict.fromkeys(["Pending", "Current"], 0)
    api._fleet_expected_generation = 1

    api._receive_fleet_snapshot(
        FleetSnapshot(
            rows=(FleetRow("Current", 1),),
            stream_health=StreamHealth(state="active"),
            activation_generation=1,
        )
    )

    api._fleet_worker.iterate_once()
    assert api._state.settings["fleet_bar"]["seen"] == [
        "Current",
        "Pending",
        "Persisted",
    ]
    assert list(api._fleet_roster.pending) == []


def test_fleet_roster_sorts_current_tier_before_pending_and_persisted_names(api):
    """Current characters have a deterministic case-insensitive recency tier."""
    api._state.settings["fleet_bar"]["seen"] = ["Persisted"]
    api._fleet_expected_generation = 1

    api._receive_fleet_snapshot(
        FleetSnapshot(
            rows=(
                FleetRow("bravo", 1),
                FleetRow("alice", 1),
                FleetRow("Alice", 1),
            ),
            stream_health=StreamHealth(state="active"),
            activation_generation=1,
        )
    )

    api._fleet_worker.iterate_once()
    assert api._state.settings["fleet_bar"]["seen"] == [
        "Alice",
        "alice",
        "bravo",
        "Persisted",
    ]


def test_failed_roster_memory_write_keeps_pending_until_next_roster_transition(
    api, monkeypatch
):
    from wingman.ui import api as api_mod

    api._state.settings["fleet_bar"]["seen"] = ["Persisted"]
    api._fleet_expected_generation = 1
    original_save = api_mod.settings_mod._save_locked
    calls = 0

    def fail_save(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise OSError("disk full")

    monkeypatch.setattr(api_mod.settings_mod, "_save_locked", fail_save)
    first = FleetSnapshot(
        rows=(FleetRow("Alice", 1),),
        stream_health=StreamHealth(state="active"),
        activation_generation=1,
    )
    api._receive_fleet_snapshot(first)
    api._fleet_worker.iterate_once()

    assert api._state.settings["fleet_bar"]["seen"] == ["Persisted"]
    assert list(api._fleet_roster.pending) == ["Alice"]
    api._receive_fleet_snapshot(
        FleetSnapshot(
            rows=(FleetRow("Alice", 99),),
            stream_health=StreamHealth(state="active"),
            activation_generation=1,
        )
    )
    api._fleet_worker.iterate_once()
    assert calls == 1

    monkeypatch.setattr(api_mod.settings_mod, "_save_locked", original_save)
    api._receive_fleet_snapshot(
        FleetSnapshot(
            rows=(FleetRow("Alice", 99), FleetRow("Bravo", 1)),
            stream_health=StreamHealth(state="active"),
            activation_generation=1,
        )
    )

    api._fleet_worker.iterate_once()
    assert api._state.settings["fleet_bar"]["seen"] == [
        "Alice",
        "Bravo",
        "Persisted",
    ]
    assert list(api._fleet_roster.pending) == []


def test_failed_roster_memory_stays_known_through_off_on_before_next_roster(
    api, monkeypatch
):
    """A failed seen write remains configurable if Fleet goes quiet before retry."""
    from wingman.ui import api as api_mod

    api._state.settings["fleet_bar"].update(enabled=True, seen=["Persisted"])
    api._fleet_expected_generation = 1
    original_save = api_mod.settings_mod._save_locked

    monkeypatch.setattr(
        api_mod.settings_mod,
        "_save_locked",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )
    api._receive_fleet_snapshot(
        FleetSnapshot(
            rows=(FleetRow("Alice", 1),),
            stream_health=StreamHealth(state="active"),
            activation_generation=1,
        )
    )
    api._fleet_worker.iterate_once()
    assert list(api._fleet_roster.pending) == ["Alice"]

    monkeypatch.setattr(api_mod.settings_mod, "_save_locked", original_save)
    api.toggle_fleet_bar(False)
    api.toggle_fleet_bar(True)

    assert api._fleet_snapshot is None
    assert list(api._fleet_roster.pending) == ["Alice"]
    assert api.fleet_bar_settings()["characters"] == [
        {"name": "Alice", "running": None, "visible": True},
        {"name": "Persisted", "running": None, "visible": True},
    ]


def test_metric_only_snapshot_does_not_push_main_fleet_state(api):
    api._fleet_expected_generation = 1
    first = FleetSnapshot(
        rows=(FleetRow("Alice", 1),),
        stream_health=StreamHealth(state="active"),
        activation_generation=1,
    )
    api._receive_fleet_snapshot(first)
    api._fleet_worker.iterate_once()
    api._window.evaluated.clear()

    api._receive_fleet_snapshot(
        FleetSnapshot(
            rows=(FleetRow("Alice", 99),),
            stream_health=StreamHealth(state="active", detail="fresh"),
            metric_error="late sample",
            activation_generation=1,
        )
    )

    api._fleet_worker.iterate_once()
    assert not [
        script for script in api._window.evaluated if "onFleetBarState" in script
    ]


def test_hide_filters_only_fleet_payload(api):
    api._fleet_expected_generation = 1
    api._receive_fleet_snapshot(
        FleetSnapshot(
            rows=(FleetRow("Alice", 10),),
            stream_health=StreamHealth(state="active"),
            activation_generation=1,
        )
    )

    result = api.set_fleet_bar_character_visible("Alice", False)

    assert result["applied"] is True
    assert "Alice" not in [
        row["character"]
        for row in api.fleet_bar_snapshot(api._fleetbar_page_id)["rows"]
    ]
    assert api._state.settings["preview"].get("excluded", []) == []


def test_visibility_write_failure_refuses_and_rolls_back(api, monkeypatch):
    from wingman.ui import api as api_mod

    api._fleet_expected_generation = 1
    api._receive_fleet_snapshot(
        FleetSnapshot(
            rows=(FleetRow("Alice", 10),),
            stream_health=StreamHealth(state="active"),
            activation_generation=1,
        )
    )

    api._fleet_worker.iterate_once()

    def fail_save(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(api_mod.settings_mod, "_save_locked", fail_save)
    result = api.set_fleet_bar_character_visible("Alice", False)

    assert result["applied"] is False
    assert "Alice" not in api._state.settings["fleet_bar"]["hidden"]
    assert result["state"]["characters"][0]["visible"] is True


def test_concurrent_hides_at_limit_do_not_lose_or_silently_truncate(api):
    original = [f"Hidden {index}" for index in range(63)]
    api._state.settings["fleet_bar"].update(seen=["Alice", "Bravo"], hidden=original)
    api._fleet_expected_generation = 1
    api._receive_fleet_snapshot(
        FleetSnapshot(
            rows=(FleetRow("Alice", 1), FleetRow("Bravo", 1)),
            stream_health=StreamHealth(state="active"),
            activation_generation=1,
        )
    )
    start = threading.Barrier(3)
    results = {}

    def hide(name):
        start.wait()
        results[name] = api.set_fleet_bar_character_visible(name, False)

    threads = [
        threading.Thread(target=hide, args=("Alice",)),
        threading.Thread(target=hide, args=("Bravo",)),
    ]
    for thread in threads:
        thread.start()
    start.wait()
    for thread in threads:
        thread.join(5)

    hidden = api._state.settings["fleet_bar"]["hidden"]
    assert all(not thread.is_alive() for thread in threads)
    assert len(hidden) == 64
    assert set(original) <= set(hidden)
    assert sorted(result["applied"] for result in results.values()) == [False, True]


def test_visibility_noop_does_not_write_and_restore_is_allowed_at_the_cap(
    api, monkeypatch
):
    from wingman.ui import api as api_mod

    api._fleet_expected_generation = 1
    api._receive_fleet_snapshot(
        FleetSnapshot(
            rows=(FleetRow("Alice", 10),),
            stream_health=StreamHealth(state="active"),
            activation_generation=1,
        )
    )
    api._fleet_worker.iterate_once()
    api._state.settings["fleet_bar"]["hidden"] = ["Alice"] + [
        f"Hidden {index}" for index in range(63)
    ]
    original_save = api_mod.settings_mod._save_locked
    saves = 0

    def count_save(*args, **kwargs):
        nonlocal saves
        saves += 1
        return original_save(*args, **kwargs)

    monkeypatch.setattr(api_mod.settings_mod, "_save_locked", count_save)
    unchanged = api.set_fleet_bar_character_visible("Alice", False)
    restored = api.set_fleet_bar_character_visible("Alice", True)

    assert unchanged["applied"] is True
    assert saves == 1
    assert restored["applied"] is True
    assert "Alice" not in api._state.settings["fleet_bar"]["hidden"]


def test_visibility_refuses_unknown_or_invalid_names(api):
    api._fleet_expected_generation = 1
    api._receive_fleet_snapshot(
        FleetSnapshot(
            rows=(FleetRow("Alice", 10),),
            stream_health=StreamHealth(state="active"),
            activation_generation=1,
        )
    )

    assert api.set_fleet_bar_character_visible("Unknown", False)["applied"] is False
    assert api.set_fleet_bar_character_visible(None, False)["applied"] is False


def test_all_hidden_payload_keeps_running_count_and_restore_keeps_metrics(api):
    api._fleet_expected_generation = 1
    api._receive_fleet_snapshot(
        FleetSnapshot(
            rows=(FleetRow("Alice", 43, ("SCRAM",), incoming_dps=0),),
            stream_health=StreamHealth(state="active"),
            activation_generation=1,
        )
    )

    api.set_fleet_bar_character_visible("Alice", False)
    hidden = api.fleet_bar_snapshot(api._fleetbar_page_id)
    api.set_fleet_bar_character_visible("Alice", True)
    restored = api.fleet_bar_snapshot(api._fleetbar_page_id)

    assert hidden["rows"] == []
    assert hidden["running_count"] == 1
    assert hidden["revision"] < restored["revision"]
    assert restored["rows"] == [
        {
            "character": "Alice",
            "outgoing_dps": 43,
            "incoming_dps": 0,
            "ewar": ["SCRAM"],
            "log_status": None,
        }
    ]


def test_fleet_payload_revision_increases_after_lifecycle_transition(api):
    api._fleet_expected_generation = 1
    api._receive_fleet_snapshot(
        FleetSnapshot(
            rows=(FleetRow("Alice", 10),),
            stream_health=StreamHealth(state="active"),
            activation_generation=1,
        )
    )
    older = api.fleet_bar_snapshot(api._fleetbar_page_id)
    older_settings = api.fleet_bar_settings()

    api._install_fleet_generation(2)
    newer = api.fleet_bar_snapshot(api._fleetbar_page_id)
    newer_settings = api.fleet_bar_settings()

    assert older["revision"] < newer["revision"]
    assert older_settings["revision"] < newer_settings["revision"]


def test_snapshot_push_targets_only_the_fleet_window(api):
    api._fleet_expected_generation = 1
    snapshot = FleetSnapshot(
        rows=(FleetRow("Alice", 10),),
        stream_health=StreamHealth(state="active"),
        activation_generation=1,
    )

    api._receive_fleet_snapshot(snapshot)
    api._fleet_worker.iterate_once()

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


def test_restore_creates_once_and_page_ready_reveals(api, monkeypatch):
    from wingman.ui import fleetbar

    api._state.settings.setdefault("fleet_bar", {})["enabled"] = True
    api._fleetbar_window = None
    created = []

    def fake_create(inner, hidden=True):
        created.append(hidden)
        inner._fleetbar_window = FleetWindow()
        inner._fleetbar_page_id = PAGE_A
        inner._fleetbar_window.hidden = hidden
        return inner._fleetbar_window

    monkeypatch.setattr(fleetbar, "create", fake_create)

    fleetbar.restore(api)
    fleetbar.restore(api)
    api.fleet_bar_ready(api._fleetbar_page_id)

    assert created == [True]
    assert api._fleetbar_window.hidden is False


def test_fit_does_not_resurrect_a_disabled_window(api):
    api._state.settings.setdefault("fleet_bar", {})["enabled"] = False

    api.fit_fleet_bar(api._fleetbar_page_id, 380, 112)

    assert api._fleetbar_window.resized == []


def test_save_position_and_fit_ignore_invalid_values(api):
    api.save_fleet_bar_pos(api._fleetbar_page_id, 25, -40)
    assert api._state.settings["fleet_bar"]["x"] == 25
    assert api._state.settings["fleet_bar"]["y"] == -40

    api._state.settings["fleet_bar"]["enabled"] = True
    api.fit_fleet_bar(api._fleetbar_page_id, 380, 112)
    api.fit_fleet_bar(api._fleetbar_page_id, 0, "bad")
    api.move_fleet_bar(api._fleetbar_page_id, 30, 45)
    assert api._fleetbar_window.resized == [(380, 112)]
    assert api._fleetbar_window.moved == [(30, 45)]
    assert api._state.settings["fleet_bar"]["x"] == 30
    assert api._state.settings["fleet_bar"]["y"] == 45


def test_create_is_frameless_pinned_hidden_and_full_surface_drag(tmp_path, monkeypatch):
    from wingman.ui import fleetbar

    calls = {}
    styled = []

    def create_window(title, url, **kwargs):
        calls.update(title=title, url=url, kwargs=kwargs)
        return FleetWindow(
            width=kwargs["width"],
            height=kwargs["height"],
            x=kwargs["x"],
            y=kwargs["y"],
        )

    monkeypatch.setitem(
        sys.modules, "webview", SimpleNamespace(create_window=create_window)
    )
    monkeypatch.setattr(fleetbar.sys, "platform", "win32")
    monkeypatch.setattr(
        fleetbar.sigbar_mod, "_apply_tool_style", lambda bar: styled.append(bar)
    )
    api = make_api(tmp_path)

    fleetbar.create(api)

    kwargs = calls["kwargs"]
    assert kwargs["frameless"] is True
    assert kwargs["easy_drag"] is False
    assert kwargs["on_top"] is True
    assert kwargs["focus"] is False
    assert kwargs["hidden"] is True
    assert kwargs["min_size"] == (1, 1)
    page, fragment = calls["url"].split("#")
    assert page.endswith("fleetbar.html")
    assert fragment == "fleet-page=" + api._fleetbar_page_id
    assert re.fullmatch(r"[0-9a-f]{64}", api._fleetbar_page_id)
    assert styled == [api._fleetbar_window]


def test_settings_and_status_strip_expose_the_same_fleet_toggle():
    from wingman.ui import window as window_mod

    html = (window_mod._web_dir() / "index.html").read_text(encoding="utf-8")
    js = (window_mod._web_dir() / "previews.js").read_text(encoding="utf-8")
    app = (window_mod._web_dir() / "app.js").read_text(encoding="utf-8")

    assert 'id="fleetbar-enabled"' in html
    assert 'id="btn-fleetbar"' in html
    assert "WM.handle('onFleetBarState'" in js
    assert "check.checked = lastGood" in js
    assert "'onFleetBarState'" in app
    assert js.count("toggle_fleet_bar") == 2
    assert js.index("WM.handle('onFleetBarState'") < js.index("var host =")


def test_fleet_character_controls_use_the_dedicated_revisioned_state():
    """A generic settings payload must not redraw Fleet's independent roster."""
    from wingman.ui import window as window_mod

    html = (window_mod._web_dir() / "index.html").read_text(encoding="utf-8")
    js = (window_mod._web_dir() / "previews.js").read_text(encoding="utf-8")
    fleet_iife_source = js[js.index("(function () {") : js.index("}());") + 5]

    assert 'id="fleetbar-character-list"' in html
    assert "set_fleet_bar_character_visible" in js
    assert "data-fleet-character" in js
    assert "Show " in js and " in Fleet Bar" in js
    assert "lastRevision" in js
    assert "document.activeElement" in js
    assert "document.body" in js
    assert "document.addEventListener('wm:settings'" not in fleet_iife_source


def test_fleet_character_disclosure_has_explicit_closed_body_rule():
    """The static details element keeps its native open state across renders."""
    from wingman.ui import window as window_mod

    html = (window_mod._web_dir() / "index.html").read_text(encoding="utf-8")
    css = (window_mod._web_dir() / "style.css").read_text(encoding="utf-8")

    assert 'id="fleetbar-characters"' in html
    assert "fleet-characters:not([open])" in css


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
    from wingman.ui.api import Api

    runtime = inspect.getsource(Api._reconcile_eve_runtime)
    presentation = inspect.getsource(Api._start_fleet_presentation)
    assert "telemetry.subscribe_fleet" in runtime
    assert "self._fleet_sharing.submit" in runtime
    assert "self._telemetry.subscribe_fleet" in presentation
    assert "self._receive_fleet_snapshot" in presentation
    assert "api._start_fleet_presentation()" in source
    assert "fleetbar.restore" in source
    assert "api._fleetbar_quitting = True" in source
    assert "fleet.destroy()" in source
    assert "api.shutdown_previews()" in source


def test_fleet_page_is_display_only_and_carries_stable_columns():
    from wingman.ui import window as window_mod

    html = (window_mod._web_dir() / "fleetbar.html").read_text(encoding="utf-8")
    js = (window_mod._web_dir() / "fleetbar.js").read_text(encoding="utf-8")

    assert "pywebview-drag-region" in html
    assert "CHARACTER" in html
    assert ">DAMAGE<" in html and ">OUT<" in html and ">IN<" in html
    assert ">EWAR<" in html
    assert ">DPS<" not in html  # split into the Damage column's OUT/IN halves
    assert ">INCOMING<" not in html  # renamed EWAR; incoming DPS moved into Damage
    assert "<button" not in html and "<input" not in html
    assert "window.onFleetSnapshot" in js
    assert "Waiting for EVE clients" in html
    assert "flex: none" in html  # overrides title-bar drag-region geometry
    assert "shell.offsetHeight" in js  # content can shrink with the roster
    assert "fleet_bar_ready" in js  # best-effort render/fit precedes explicit reveal
    assert "screen.availLeft" in js and "move_fleet_bar" in js
    assert "function damageCell(row, maxOutgoing, maxIncoming)" in js
    assert "function readDps(row, key)" in js
    assert "function maxDps(rows, key)" in js
    assert "function fillRatio(value, maximum)" in js
    assert "function displayDps(value)" in js
    assert "row.log_status" in js  # NO LOG now lives in the Damage cell, not EWAR
    assert "SCRAM" not in js  # rendered from telemetry, never guessed here


PAGE_A = "a" * 64
PAGE_B = "b" * 64
PAGE_CALLBACKS = [
    ("fleet_bar_snapshot", ()),
    ("fit_fleet_bar", (380, 112)),
    ("move_fleet_bar", (30, 45)),
    ("save_fleet_bar_pos", (25, -40)),
    ("fleet_bar_ready", ()),
]
PAGE_SESSION_CALLBACKS = [
    ("activate_fleet_bar", ()),
    ("deactivate_fleet_bar", ()),
    ("hide_fleet_bar", ()),
]


def _page_call(api, method, page_id, *args):
    """Replay the same behavior on the pre-protocol base, not an arity failure.

    The separate bridge signature guard requires the new interface. Only this
    test adapter may omit identity when replaying against the old implementation.
    """
    call = getattr(api, method)
    if "page_id" in inspect.signature(call).parameters:
        return call(page_id, *args)
    return call(*args)


@pytest.mark.parametrize("method,args", PAGE_CALLBACKS)
@pytest.mark.parametrize(
    "identity",
    [
        None,
        True,
        12,
        [],
        {},
        "",
        "a" * 63,
        "a" * 65,
        "A" * 64,
        "g" * 64,
        PAGE_A + "\n",
        " " + PAGE_A,
        PAGE_B,
    ],
)
def test_page_identity_rejects_invalid_or_stale_callbacks(
    api, monkeypatch, method, args, identity
):
    """Removing admission lets predecessor reads/geometry/ready/save reach B."""
    from wingman.ui import api as api_mod

    api._state.settings["fleet_bar"]["enabled"] = True
    api._fleetbar_ready = False
    bar = api._fleetbar_window
    bar.hidden = True
    saves, queued = [], []
    monkeypatch.setattr(
        api_mod.settings_mod, "update_section", lambda *a: saves.append(a)
    )
    monkeypatch.setattr(
        api, "_queue_fleet_presentation", lambda **kw: queued.append(kw)
    )

    result = _page_call(api, method, identity, *args)

    assert result is None
    assert bar.resized == [] and bar.moved == [] and bar.hidden
    assert not api._fleetbar_ready
    assert saves == [] and queued == []


@pytest.mark.parametrize("method,args", PAGE_CALLBACKS)
def test_page_identity_rejects_omitted_token(api, method, args):
    """Old no-token calls remain callable only to refuse, never as a fallback."""
    before = dict(api._state.settings["fleet_bar"])
    api._fleetbar_ready = False
    result = getattr(api, method)(*args)
    assert result is None
    assert api._state.settings["fleet_bar"] == before
    assert not api._fleetbar_ready
    assert api._fleetbar_window.resized == api._fleetbar_window.moved == []


@pytest.mark.parametrize("method,args", PAGE_CALLBACKS)
@pytest.mark.parametrize("retired", ["dead", "absent", "quitting", "tokenless"])
def test_page_identity_rejects_retired_window(api, method, args, retired):
    before = dict(api._state.settings["fleet_bar"])
    api._fleetbar_ready = False
    bar = api._fleetbar_window
    bar.hidden = True
    if retired == "dead":
        bar.alive = False
    elif retired == "absent":
        api._fleetbar_window = None
    elif retired == "quitting":
        api._fleetbar_quitting = True
    else:
        api._fleetbar_page_id = None
    assert _page_call(api, method, PAGE_A, *args) is None
    assert api._state.settings["fleet_bar"] == before
    assert not api._fleetbar_ready
    assert bar.resized == bar.moved == [] and bar.hidden


@pytest.mark.parametrize("interruption", ["replacement", "disable", "shutdown"])
def test_page_identity_fit_never_retargets_after_retry(api, monkeypatch, interruption):
    from wingman.ui import api as api_mod

    api._state.settings["fleet_bar"]["enabled"] = True
    bar = api._fleetbar_window
    bar.resize = lambda w, h: bar.resized.append((w, h))  # size never sticks
    replacement = FleetWindow()
    sleeps = []

    def pause(seconds):
        # Another thread must be able to own lifecycle during the retry gap.
        def interrupt():
            with api._fleetbar_lifecycle_lock, api._fleet_presentation_lock:
                if interruption == "replacement":
                    api._fleetbar_window = replacement
                    api._fleetbar_page_id = PAGE_B
                elif interruption == "disable":
                    api._state.settings["fleet_bar"]["enabled"] = False
                else:
                    api._fleetbar_quitting = True

        thread = threading.Thread(target=interrupt)
        thread.start()
        thread.join(5)
        assert not thread.is_alive(), "fit slept while holding lifecycle"
        sleeps.append(seconds)

    monkeypatch.setattr(api_mod.time, "sleep", pause)
    assert _page_call(api, "fit_fleet_bar", PAGE_A, 380, 112) is None
    assert bar.resized == [(380, 112)]
    assert replacement.resized == []
    assert sleeps == [0.25]


def test_page_identity_disabled_ready_and_reenable_reuse(api, monkeypatch):
    from wingman.ui import fleetbar

    bar = api._fleetbar_window
    bar.hidden = True
    api._fleetbar_ready = False
    monkeypatch.setattr(fleetbar, "create", lambda *a, **kw: pytest.fail("must reuse"))
    assert isinstance(_page_call(api, "fleet_bar_snapshot", PAGE_A), dict)
    _page_call(api, "save_fleet_bar_pos", PAGE_A, 25, -40)
    assert (
        api._state.settings["fleet_bar"]["x"],
        api._state.settings["fleet_bar"]["y"],
    ) == (25, -40)
    _page_call(api, "fit_fleet_bar", PAGE_A, 380, 112)
    _page_call(api, "move_fleet_bar", PAGE_A, 30, 45)
    assert bar.resized == bar.moved == []
    _page_call(api, "fleet_bar_ready", PAGE_A)
    assert api._fleetbar_ready and bar.hidden
    assert api.toggle_fleet_bar(True)["applied"]
    assert api._fleetbar_window is bar and api._fleetbar_page_id == PAGE_A
    assert not bar.hidden and api._fleetbar_ready
    assert api.toggle_fleet_bar(False)["applied"]
    assert api._fleetbar_page_id == PAGE_A and api._fleetbar_ready


@pytest.mark.parametrize("route", ["toggle", "restore"])
def test_page_identity_creation_publishes_only_after_style(api, monkeypatch, route):
    from wingman.ui import fleetbar

    old = api._fleetbar_window
    old.alive = False
    api._state.settings["fleet_bar"]["enabled"] = route == "restore"
    candidate = FleetWindow()
    candidate.hidden = True
    candidate.destroy = lambda: None
    observations, early = [], []
    token = []
    callbacks = []
    started = threading.Event()

    def create_window(title, url, **kwargs):
        token.append(url.partition("#fleet-page=")[2] or PAGE_B)
        observations.append(
            (api._fleetbar_window, api._fleetbar_page_id, api._fleetbar_ready)
        )
        candidate.width = kwargs["width"]
        candidate.height = kwargs["height"]
        candidate.x = kwargs["x"]
        candidate.y = kwargs["y"]
        return candidate

    def style(bar):
        assert bar is candidate
        # The telemetry worker can still take its short lock during native work.
        free = threading.Event()

        def probe():
            with api._fleet_presentation_lock:
                free.set()

        probe_thread = threading.Thread(target=probe)
        probe_thread.start()
        assert free.wait(5)
        probe_thread.join(5)
        observations.append(
            (api._fleetbar_window, api._fleetbar_page_id, api._fleetbar_ready)
        )
        for method, args in PAGE_CALLBACKS:
            early.append(_page_call(api, method, token[0], *args))

        def callback():
            started.set()
            callbacks.append(_page_call(api, "fleet_bar_snapshot", token[0]))

        thread = threading.Thread(target=callback)
        thread.start()
        assert started.wait(5)
        threads.append(thread)

    threads = []
    monkeypatch.setitem(
        sys.modules, "webview", SimpleNamespace(create_window=create_window)
    )
    monkeypatch.setattr(fleetbar.sys, "platform", "win32")
    monkeypatch.setattr(fleetbar.sigbar_mod, "_apply_tool_style", style)
    if route == "toggle":
        assert api.toggle_fleet_bar(True)["applied"]
    else:
        fleetbar.restore(api)
    for thread in threads:
        thread.join(5)
        assert not thread.is_alive()
    assert observations == [(None, None, False), (None, None, False)]
    assert early == [None] * 5
    assert len(callbacks) == 1 and isinstance(callbacks[0], dict)
    assert api._fleetbar_window is candidate
    assert re.fullmatch(r"[0-9a-f]{64}", api._fleetbar_page_id)
    assert api._fleetbar_page_id == token[0] != PAGE_A
    assert not api._fleetbar_ready and candidate.hidden
    assert candidate.resized == candidate.moved == []


@pytest.mark.parametrize("route", ["toggle", "restore"])
@pytest.mark.parametrize("failure", ["none", "style", "publication"])
@pytest.mark.parametrize("cleanup_fails,rollback_fails", [(False, False), (True, True)])
def test_page_identity_creation_failure_retires_before_cleanup(
    api, monkeypatch, route, failure, cleanup_fails, rollback_fails
):
    from wingman.ui import api as api_mod
    from wingman.ui import fleetbar

    api._fleetbar_window.alive = False
    api._state.settings["fleet_bar"]["enabled"] = route == "restore"
    candidate = FleetWindow()
    cleaned, created, early = [], [], []
    queued, threads = [], []
    attempt_failed = False
    original_update = api_mod.settings_mod.update_section

    def update(doc, section, values):
        if rollback_fails and attempt_failed and values == {"enabled": False}:
            raise OSError("rollback failed")
        return original_update(doc, section, values)

    def destroy():
        cleaned.append(
            (api._fleetbar_window, api._fleetbar_page_id, api._fleetbar_ready)
        )
        if cleanup_fails:
            raise RuntimeError("cleanup failed")
        candidate.alive = False

    candidate.destroy = destroy

    def create_window(title, url, **kwargs):
        nonlocal attempt_failed
        created.append(url.partition("#fleet-page=")[2] or PAGE_B)
        candidate.width = kwargs["width"]
        candidate.height = kwargs["height"]
        candidate.x = kwargs["x"]
        candidate.y = kwargs["y"]
        started = threading.Event()

        def callback():
            started.set()
            queued.append(_page_call(api, "fleet_bar_snapshot", created[0]))

        thread = threading.Thread(target=callback)
        threads.append(thread)
        thread.start()
        assert started.wait(5)
        if failure == "none":
            attempt_failed = True
            return None
        return candidate

    def style(bar):
        nonlocal attempt_failed
        if failure == "style":
            attempt_failed = True
            raise RuntimeError("style failed")

    def fail_publish(bar, page_id, **_kwargs):
        nonlocal attempt_failed
        # Simulate a publication fault after an assignment; cleanup must revoke it.
        api._fleetbar_window = bar
        api._fleetbar_page_id = page_id
        attempt_failed = True
        raise RuntimeError("publication failed")

    monkeypatch.setattr(api_mod.settings_mod, "update_section", update)
    monkeypatch.setitem(
        sys.modules, "webview", SimpleNamespace(create_window=create_window)
    )
    monkeypatch.setattr(fleetbar.sys, "platform", "win32")
    monkeypatch.setattr(fleetbar.sigbar_mod, "_apply_tool_style", style)
    if failure == "publication":
        monkeypatch.setattr(
            api, "_publish_fleet_page_locked", fail_publish, raising=False
        )
    if route == "toggle":
        result = api.toggle_fleet_bar(True)
        assert not result["applied"]
    else:
        fleetbar.restore(api)
    for thread in threads:
        thread.join(5)
        assert not thread.is_alive()
    assert queued == [None]
    for method, args in PAGE_CALLBACKS:
        early.append(_page_call(api, method, created[0], *args))
    assert api._fleetbar_window is None and api._fleetbar_page_id is None
    assert not api._fleetbar_ready and early == [None] * 5
    assert cleaned == ([] if failure == "none" else [(None, None, False)])
    assert api._state.settings["fleet_bar"]["enabled"] is rollback_fails


@pytest.mark.parametrize("method,args", PAGE_CALLBACKS)
def test_page_identity_real_replacement_rejects_predecessor(
    api, monkeypatch, method, args
):
    from wingman.ui import fleetbar

    api._fleetbar_window.alive = False
    first, second = FleetWindow(), FleetWindow()
    first.hidden = second.hidden = True
    windows = iter([first, second])
    urls = []

    def create_window(title, url, **kwargs):
        urls.append(url)
        bar = next(windows)
        bar.width = kwargs["width"]
        bar.height = kwargs["height"]
        bar.x = kwargs["x"]
        bar.y = kwargs["y"]
        return bar

    monkeypatch.setitem(
        sys.modules, "webview", SimpleNamespace(create_window=create_window)
    )
    monkeypatch.setattr(fleetbar.sigbar_mod, "_apply_tool_style", lambda bar: None)
    assert api.toggle_fleet_bar(True)["applied"]
    first_token = urls[0].partition("#fleet-page=")[2] or PAGE_A
    first.alive = False
    assert api.toggle_fleet_bar(True)["applied"]
    second_token = urls[1].partition("#fleet-page=")[2] or PAGE_B
    before = dict(api._state.settings["fleet_bar"])

    assert _page_call(api, method, first_token, *args) is None
    assert api._state.settings["fleet_bar"] == before
    assert first.resized == first.moved == second.resized == second.moved == []
    assert second.hidden and not api._fleetbar_ready
    assert first_token != second_token == api._fleetbar_page_id
    # The successor still owns the same endpoint; rejection did not strand boot.
    result = _page_call(api, method, second_token, *args)
    if method == "fleet_bar_snapshot":
        assert isinstance(result, dict)
    elif method == "fit_fleet_bar":
        assert second.resized == [(380, 112)]
    elif method == "move_fleet_bar":
        assert second.moved == [(30, 45)]
    elif method == "save_fleet_bar_pos":
        assert api._state.settings["fleet_bar"]["x"] == 25
    else:
        assert not second.hidden and api._fleetbar_ready


def test_page_identity_entered_move_and_save_finish_before_retirement(api, monkeypatch):
    from wingman.ui import api as api_mod

    api._state.settings["fleet_bar"]["enabled"] = True
    entered, release, stopping, stopped = (threading.Event() for _ in range(4))
    order, errors = [], []
    original_update = api_mod.settings_mod.update_section

    def move(x, y):
        entered.set()
        assert release.wait(5)
        order.append("move")

    api._fleetbar_window.move = move

    def update(*args, **kwargs):
        result = original_update(*args, **kwargs)
        assert api._fleetbar_page_id == PAGE_A
        order.append("save")
        return result

    def detach():
        assert api._fleetbar_page_id is None
        assert (
            api._state.settings["fleet_bar"]["x"],
            api._state.settings["fleet_bar"]["y"],
        ) == (30, 45)
        order.append("detach")

    api._fleet_unsubscribe = detach
    monkeypatch.setattr(api_mod.settings_mod, "update_section", update)

    def moving():
        try:
            _page_call(api, "move_fleet_bar", PAGE_A, 30, 45)
        except Exception as exc:  # noqa: BLE001 -- assert worker failures on the parent thread instead of losing them in a thread warning.
            errors.append(exc)

    def stop():
        stopping.set()
        api._stop_fleet_presentation()
        stopped.set()

    mover, stopper = threading.Thread(target=moving), threading.Thread(target=stop)
    mover.start()
    assert entered.wait(5)
    stopper.start()
    assert stopping.wait(5)
    try:
        assert api._fleetbar_page_id == PAGE_A and not stopped.is_set()
    finally:
        release.set()
        mover.join(5)
        stopper.join(5)
    assert not mover.is_alive() and not stopper.is_alive() and not errors
    assert order == ["move", "save", "detach"]
    assert api._fleetbar_page_id is None


def _set_resizable_bar(
    api,
    *,
    x=40,
    y=60,
    outer_width=512,
    height=90,
    work_area=(0, 0, 1000, 900),
    insets=chrome.ResizeInsets(6, 0, 6, 0),
):
    api._state.settings["fleet_bar"]["enabled"] = True
    api._state.settings["fleet_bar"]["x"] = x
    api._state.settings["fleet_bar"]["y"] = y
    api._fleetbar_resize_insets = insets
    api._fleetbar_resize_enabled = True
    api._fleetbar_applied_x = x
    api._fleetbar_applied_y = y
    api._fleetbar_applied_outer_width = outer_width
    api._fleetbar_applied_outer_height = height
    api._fleetbar_window.x = x
    api._fleetbar_window.y = y
    api._fleetbar_window.width = outer_width
    api._fleetbar_window.height = height
    api._fleetbar_window.work_area = work_area


def test_geometry_helpers_convert_content_width_and_clamp_logical_work_areas():
    from wingman.ui import fleetbar

    insets = chrome.ResizeInsets(6, 0, 6, 0)

    assert fleetbar.outer_width_for_content(500, insets) == 512
    assert fleetbar.content_width_for_outer(512, insets) == 500
    assert fleetbar.clamp_rect_to_work_area(
        -780, 60, 512, 90, (-1600, 0, -800, 900)
    ) == (
        -1312,
        60,
        512,
        90,
    )
    assert fleetbar.clamp_rect_to_work_area(140, 60, 512, 90, (100, 0, 520, 900)) == (
        100,
        60,
        420,
        90,
    )


def test_create_attaches_horizontal_resize_before_publication(tmp_path, monkeypatch):
    from wingman.ui import fleetbar

    api = make_api(tmp_path)
    api._state.settings["fleet_bar"] = settings.validated_fleet_bar(
        {"enabled": True, "x": 25, "y": -40}
    )
    calls = {}
    token = []
    styled = []
    attached = []

    def create_window(title, url, **kwargs):
        calls.update(title=title, url=url, kwargs=kwargs)
        token.append(url.partition("#fleet-page=")[2])
        return FleetWindow(
            width=kwargs["width"],
            height=kwargs["height"],
            x=kwargs["x"],
            y=kwargs["y"],
            work_area=(0, -100, 900, 900),
        )

    def enable_horizontal_resize(bar, **kwargs):
        attached.append(
            (api._fleetbar_window, api._fleetbar_page_id, api._fleetbar_ready)
        )
        assert api.fleet_bar_snapshot(token[0]) is None
        assert kwargs == {
            "min_content_width": settings.FLEET_BAR_MIN_PREFERRED_CONTENT_WIDTH,
            "max_content_width": settings.FLEET_BAR_MAX_PREFERRED_CONTENT_WIDTH,
        }
        return chrome.ResizeInsets(6, 0, 6, 0)

    monkeypatch.setitem(
        sys.modules, "webview", SimpleNamespace(create_window=create_window)
    )
    monkeypatch.setattr(fleetbar.sys, "platform", "win32")
    monkeypatch.setattr(
        fleetbar.sigbar_mod, "_apply_tool_style", lambda bar: styled.append(bar)
    )
    monkeypatch.setattr(
        fleetbar.chrome, "enable_horizontal_resize", enable_horizontal_resize
    )

    created = fleetbar.create(api)

    assert calls["title"] == "Fleet Bar"
    assert calls["kwargs"]["width"] == 500
    assert styled == [created]
    assert attached == [(None, None, False)]
    assert created.resized == [(512, 90)]
    assert api._fleetbar_window is created
    assert api._fleetbar_page_id == token[0]
    assert api._fleetbar_resize_enabled is True
    assert api._fleetbar_resize_insets == chrome.ResizeInsets(6, 0, 6, 0)
    assert api._fleetbar_applied_outer_width == 512


def test_create_without_resize_chrome_falls_back_to_fixed_width_without_stale_inset(
    tmp_path, monkeypatch
):
    from wingman.ui import fleetbar

    api = make_api(tmp_path)
    api._state.settings["fleet_bar"] = settings.validated_fleet_bar({"enabled": True})
    api._fleetbar_resize_insets = chrome.ResizeInsets(6, 0, 6, 0)
    api._fleetbar_resize_enabled = True
    api._fleetbar_applied_outer_width = 512

    def create_window(_title, _url, **kwargs):
        return FleetWindow(
            width=kwargs["width"],
            height=kwargs["height"],
            x=kwargs["x"],
            y=kwargs["y"],
            work_area=(0, 0, 900, 900),
        )

    monkeypatch.setitem(
        sys.modules, "webview", SimpleNamespace(create_window=create_window)
    )
    monkeypatch.setattr(fleetbar.sys, "platform", "win32")
    monkeypatch.setattr(fleetbar.sigbar_mod, "_apply_tool_style", lambda bar: None)
    monkeypatch.setattr(
        fleetbar.chrome, "enable_horizontal_resize", lambda *args, **kwargs: None
    )

    fleetbar.create(api)

    assert api._fleetbar_resize_enabled is False
    assert api._fleetbar_resize_insets == chrome.ResizeInsets(0, 0, 0, 0)
    assert api._fleetbar_applied_outer_width == 500
    assert api.fleet_bar_ready(api._fleetbar_page_id) is False


@pytest.mark.parametrize(
    "method,args",
    [
        ("fit_fleet_bar_height", (112,)),
        ("settle_fleet_bar_resize", (500, 40)),
        ("reset_fleet_bar_page_width", ()),
    ],
)
def test_new_page_geometry_callbacks_reject_omitted_and_stale_tokens(api, method, args):
    _set_resizable_bar(api)
    before = dict(api._state.settings["fleet_bar"])

    assert getattr(api, method)(*args) is None
    assert _page_call(api, method, PAGE_B, *args) is None
    assert api._state.settings["fleet_bar"] == before
    assert api._fleetbar_window.resized == []
    assert api._fleetbar_window.moved == []


def test_legacy_fit_endpoint_converts_content_width_through_current_resize_insets(api):
    _set_resizable_bar(api)

    api.fit_fleet_bar(PAGE_A, 500, 112)

    assert api._fleetbar_window.resized == [(512, 112)]


def test_fit_fleet_bar_height_preserves_current_outer_width_on_every_retry(
    api, monkeypatch
):
    from wingman.ui import api as api_mod

    _set_resizable_bar(api)
    bar = api._fleetbar_window
    bar.width = 400
    bar.height = 80
    sleeps = []

    def resize(width, height):
        bar.resized.append((width, height))

    bar.resize = resize
    monkeypatch.setattr(api_mod.time, "sleep", sleeps.append)

    api.fit_fleet_bar_height(PAGE_A, 112)

    assert bar.resized == [(512, 112)] * 12
    assert sleeps == [0.25] * 12


@pytest.mark.parametrize("interruption", ["replacement", "disable", "shutdown"])
def test_fit_fleet_bar_height_never_retargets_after_retry(
    api, monkeypatch, interruption
):
    from wingman.ui import api as api_mod

    _set_resizable_bar(api)
    bar = api._fleetbar_window
    bar.width = 400
    replacement = FleetWindow(width=600, height=90)
    sleeps = []

    def resize(width, height):
        bar.resized.append((width, height))

    def pause(seconds):
        def interrupt():
            with api._fleetbar_lifecycle_lock, api._fleet_presentation_lock:
                if interruption == "replacement":
                    api._fleetbar_window = replacement
                    api._fleetbar_page_id = PAGE_B
                elif interruption == "disable":
                    api._state.settings["fleet_bar"]["enabled"] = False
                else:
                    api._fleetbar_quitting = True

        thread = threading.Thread(target=interrupt)
        thread.start()
        thread.join(5)
        assert not thread.is_alive(), "fit slept while holding lifecycle"
        sleeps.append(seconds)

    bar.resize = resize
    monkeypatch.setattr(api_mod.time, "sleep", pause)

    assert api.fit_fleet_bar_height(PAGE_A, 112) is None
    assert bar.resized == [(512, 112)]
    assert replacement.resized == []
    assert sleeps == [0.25]


def test_settle_fleet_bar_resize_persists_right_edge_width_only_with_tolerance(api):
    _set_resizable_bar(api)

    result = api.settle_fleet_bar_resize(PAGE_A, 721, 41)

    assert result == {"applied": True, "persisted": True, "error": None}
    assert api._fleetbar_window.resized == [(732, 90)]
    assert api._fleetbar_window.moved == []
    assert api._fleetbar_applied_x == 40
    assert api._fleetbar_applied_outer_width == 732
    assert api._state.settings["fleet_bar"]["preferred_content_width"] == 720
    assert api._state.settings["fleet_bar"]["x"] == 40


def test_settle_fleet_bar_resize_persists_left_edge_width_and_x(api):
    _set_resizable_bar(api, x=200)

    result = api.settle_fleet_bar_resize(PAGE_A, 450, 150)

    assert result == {"applied": True, "persisted": True, "error": None}
    assert api._fleetbar_window.resized == [(462, 90)]
    assert api._fleetbar_window.moved == [(150, 60)]
    assert api._fleetbar_applied_x == 150
    assert api._state.settings["fleet_bar"]["preferred_content_width"] == 450
    assert api._state.settings["fleet_bar"]["x"] == 150


def test_settle_fleet_bar_resize_clamps_to_the_work_area_without_overwriting_preferred_width(
    api,
):
    _set_resizable_bar(api, x=140, work_area=(100, 0, 520, 900))

    result = api.settle_fleet_bar_resize(PAGE_A, 720, 140)

    assert result == {"applied": True, "persisted": True, "error": None}
    assert api._fleetbar_window.resized == [(420, 90)]
    assert api._fleetbar_window.moved == [(100, 60)]
    assert api._fleetbar_applied_x == 100
    assert api._fleetbar_applied_outer_width == 420
    assert api._state.settings["fleet_bar"]["preferred_content_width"] == 720
    assert api._state.settings["fleet_bar"]["x"] == 140


def test_settle_fleet_bar_resize_keeps_session_width_when_persistence_fails(
    api, monkeypatch
):
    from wingman.ui import api as api_mod

    _set_resizable_bar(api, x=200)
    before = dict(api._state.settings["fleet_bar"])

    monkeypatch.setattr(
        api_mod.settings_mod,
        "update_section",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )

    result = api.settle_fleet_bar_resize(PAGE_A, 450, 150)

    assert result["applied"] is True
    assert result["persisted"] is False
    assert "survive restart" in result["error"]
    assert api._fleetbar_window.resized == [(462, 90)]
    assert api._fleetbar_window.moved == [(150, 60)]
    assert api._fleetbar_applied_x == 150
    assert api._fleetbar_applied_outer_width == 462
    assert api._state.settings["fleet_bar"] == before


def test_reset_fleet_bar_page_width_reclamps_visible_bar(api):
    _set_resizable_bar(api, x=150, outer_width=420, work_area=(0, 0, 600, 900))
    api._state.settings["fleet_bar"]["preferred_content_width"] = 720
    api._fleetbar_applied_outer_width = 420
    api._fleetbar_window.width = 420

    result = api.reset_fleet_bar_page_width(PAGE_A)

    assert result == {"applied": True, "persisted": True, "error": None}
    assert api._fleetbar_window.resized == [(512, 90)]
    assert api._fleetbar_window.moved == [(88, 60)]
    assert api._fleetbar_applied_x == 88
    assert api._fleetbar_applied_outer_width == 512
    assert api._state.settings["fleet_bar"]["preferred_content_width"] == 500
    assert api._state.settings["fleet_bar"]["x"] == 88


def test_reset_fleet_bar_width_persists_default_without_a_live_bar(api):
    api._state.settings["fleet_bar"]["preferred_content_width"] = 720
    api._fleetbar_window = None

    result = api.reset_fleet_bar_width()

    assert result == {"applied": True, "persisted": True, "error": None}
    assert api._state.settings["fleet_bar"]["preferred_content_width"] == 500


def test_reset_fleet_bar_width_defers_hidden_live_bar_geometry_until_reenable(
    api, monkeypatch
):
    from wingman.ui import fleetbar

    _set_resizable_bar(api, outer_width=462)
    api._state.settings["fleet_bar"]["preferred_content_width"] = 450
    bar = api._fleetbar_window
    resize_calls = []
    show_calls = []

    assert api.toggle_fleet_bar(False)["applied"] is True
    monkeypatch.setattr(
        fleetbar, "create", lambda *args, **kwargs: pytest.fail("must reuse hidden bar")
    )

    def resize(width, height):
        resize_calls.append((width, height))
        bar.width = width
        bar.height = height
        bar.hidden = False

    def show():
        show_calls.append(True)
        bar.hidden = False

    bar.resize = resize
    bar.show = show

    result = api.reset_fleet_bar_width()

    assert result == {"applied": True, "persisted": True, "error": None}
    assert bar.hidden is True
    assert resize_calls == []
    assert show_calls == []
    assert bar.width == 462
    assert api._fleetbar_applied_outer_width == 512
    assert (
        fleetbar.content_width_for_outer(
            api._fleetbar_applied_outer_width, api._fleetbar_resize_insets
        )
        == 500
    )
    assert api._state.settings["fleet_bar"]["preferred_content_width"] == 500

    assert api.toggle_fleet_bar(True)["applied"] is True
    assert api._fleetbar_window is bar
    assert resize_calls == [(512, 90)]
    assert show_calls == [True]
    assert bar.hidden is False
    assert bar.width == 512
    assert (
        fleetbar.content_width_for_outer(bar.width, api._fleetbar_resize_insets) == 500
    )


def test_reset_fleet_bar_width_applies_pending_default_when_ready_arrives_after_reenable(
    api, monkeypatch
):
    from wingman.ui import fleetbar

    _set_resizable_bar(api, outer_width=462)
    api._state.settings["fleet_bar"]["preferred_content_width"] = 450
    api._fleetbar_ready = False
    bar = api._fleetbar_window
    events = []

    assert api.toggle_fleet_bar(False)["applied"] is True
    monkeypatch.setattr(
        fleetbar, "create", lambda *args, **kwargs: pytest.fail("must reuse hidden bar")
    )

    def resize(width, height):
        events.append(("resize", width, height))
        bar.width = width
        bar.height = height
        bar.hidden = False

    def show():
        events.append(("show",))
        bar.hidden = False

    bar.resize = resize
    bar.show = show

    result = api.reset_fleet_bar_width()

    assert result == {"applied": True, "persisted": True, "error": None}
    assert bar.hidden is True
    assert events == []
    assert bar.width == 462
    assert api._fleetbar_applied_outer_width == 512

    assert api.toggle_fleet_bar(True)["applied"] is True
    assert api._fleetbar_window is bar
    assert bar.hidden is True
    assert events == []

    assert api.fleet_bar_ready(PAGE_A) is True
    assert api._fleetbar_window is bar
    assert events == [("resize", 512, 90), ("show",)]
    assert bar.hidden is False
    assert bar.width == 512
    assert (
        fleetbar.content_width_for_outer(bar.width, api._fleetbar_resize_insets) == 500
    )


def test_reset_fleet_bar_page_width_refuses_native_resize_failure(api):
    _set_resizable_bar(api, outer_width=420)
    api._state.settings["fleet_bar"]["preferred_content_width"] = 720
    api._fleetbar_window.resize = lambda *_args: (_ for _ in ()).throw(
        RuntimeError("broken")
    )

    result = api.reset_fleet_bar_page_width(PAGE_A)

    assert result["applied"] is False
    assert result["persisted"] is False
    assert api._state.settings["fleet_bar"]["preferred_content_width"] == 720


def test_reset_fleet_bar_page_width_keeps_session_geometry_when_persistence_fails(
    api, monkeypatch
):
    from wingman.ui import api as api_mod

    _set_resizable_bar(api, x=150, outer_width=420, work_area=(0, 0, 600, 900))
    api._state.settings["fleet_bar"]["preferred_content_width"] = 720
    before = dict(api._state.settings["fleet_bar"])

    monkeypatch.setattr(
        api_mod.settings_mod,
        "update_section",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )

    result = api.reset_fleet_bar_page_width(PAGE_A)

    assert result["applied"] is True
    assert result["persisted"] is False
    assert "survive restart" in result["error"]
    assert api._fleetbar_window.resized == [(512, 90)]
    assert api._fleetbar_window.moved == [(88, 60)]
    assert api._fleetbar_applied_x == 88
    assert api._fleetbar_applied_outer_width == 512
    assert api._state.settings["fleet_bar"] == before


def test_fleet_bar_ready_returns_resize_capability(api):
    _set_resizable_bar(api)
    api._fleetbar_window.hidden = True
    api._fleetbar_resize_enabled = True

    assert api.fleet_bar_ready(PAGE_A) is True
    api._fleetbar_window.hidden = True
    api._fleetbar_resize_enabled = False
    assert api.fleet_bar_ready(PAGE_A) is False


def test_activate_bar_records_foreground_and_clears_only_noactivate():
    from wingman.ui import fleetbar

    bar = _attach_hwnd(FleetWindow(), 0x202)
    bar.hidden = False
    style = 0x08000000 | 0x80 | 0x04000000
    user32 = _FakeUser32(
        foreground=0x101,
        styles={0x202: style},
        alive={0x202},
    )

    assert fleetbar.activate_bar(bar, user32=user32) == (True, 0x101)
    assert user32.styles[0x202] == style & ~0x08000000
    assert user32.calls == [
        ("GetForegroundWindow",),
        ("GetWindowLongW", 0x202, -20),
        ("SetWindowLongW", 0x202, -20, style & ~0x08000000),
        ("SetForegroundWindow", 0x202),
        ("GetForegroundWindow",),
    ]


def test_activate_bar_restores_noactivate_immediately_on_foreground_refusal():
    from wingman.ui import fleetbar

    bar = _attach_hwnd(FleetWindow(), 0x202)
    bar.hidden = False
    style = 0x08000000 | 0x80 | 0x04000000
    user32 = _FakeUser32(
        foreground=0x101,
        foreground_after_set=0x404,
        styles={0x202: style},
        alive={0x202},
    )

    assert fleetbar.activate_bar(bar, user32=user32) == (False, 0x101)
    assert user32.styles[0x202] == style
    assert user32.calls[-1] == ("SetWindowLongW", 0x202, -20, style)


@pytest.mark.parametrize(
    "return_hwnd,main_hwnd,title,alive,want_focus",
    [
        pytest.param(0x303, 0x303, "", {0x202, 0x303}, True, id="main-window"),
        pytest.param(
            0x404, 0x303, "EVE - Alice", {0x202, 0x404}, True, id="eve-window"
        ),
        pytest.param(0x505, 0x303, "Notepad", {0x202, 0x505}, False, id="unrelated"),
        pytest.param(0x606, 0x303, "", {0x202}, False, id="destroyed"),
    ],
)
def test_deactivate_bar_restores_noactivate_before_guarded_focus_return(
    return_hwnd, main_hwnd, title, alive, want_focus
):
    from wingman.ui import fleetbar

    bar = _attach_hwnd(FleetWindow(), 0x202)
    bar.hidden = False
    main = _attach_hwnd(SimpleNamespace(), main_hwnd)
    style = 0x80 | 0x04000000
    user32 = _FakeUser32(
        styles={0x202: style},
        alive=alive,
        titles={return_hwnd: title},
    )

    assert (
        fleetbar.deactivate_bar(bar, return_hwnd, main_window=main, user32=user32)
        is want_focus
    )
    restore = user32.calls.index(("SetWindowLongW", 0x202, -20, style | 0x08000000))
    focus = [call for call in user32.calls if call[0] == "SetForegroundWindow"]
    assert user32.styles[0x202] == style | 0x08000000
    if want_focus:
        assert focus == [("SetForegroundWindow", return_hwnd)]
        assert restore < user32.calls.index(("SetForegroundWindow", return_hwnd))
    else:
        assert focus == []


@pytest.mark.parametrize("method,args", PAGE_SESSION_CALLBACKS)
@pytest.mark.parametrize(
    "identity",
    [None, True, 12, [], {}, "", "a" * 63, "A" * 64, PAGE_B],
)
def test_page_session_callbacks_reject_invalid_or_stale_ids(
    api, method, args, identity
):
    before = dict(api._state.settings["fleet_bar"])
    api._fleetbar_return_hwnd = 0x123

    assert _page_call(api, method, identity, *args) is None
    assert api._state.settings["fleet_bar"] == before
    assert api._fleetbar_return_hwnd == 0x123
    assert api._fleetbar_window.hidden is False


@pytest.mark.parametrize("method,args", PAGE_SESSION_CALLBACKS)
def test_page_session_callbacks_reject_omitted_token(api, method, args):
    before = dict(api._state.settings["fleet_bar"])
    api._fleetbar_return_hwnd = 0x123

    assert getattr(api, method)(*args) is None
    assert api._state.settings["fleet_bar"] == before
    assert api._fleetbar_return_hwnd == 0x123


@pytest.mark.parametrize("method,args", PAGE_SESSION_CALLBACKS)
def test_page_session_callbacks_reject_retired_window(api, method, args):
    before = dict(api._state.settings["fleet_bar"])
    api._fleetbar_return_hwnd = 0x123
    api._fleetbar_window.alive = False

    assert _page_call(api, method, PAGE_A, *args) is None
    assert api._state.settings["fleet_bar"] == before
    assert api._fleetbar_return_hwnd == 0x123


def test_activation_session_keeps_original_return_hwnd_until_deactivated(
    api, monkeypatch
):
    from wingman.ui import fleetbar

    _set_resizable_bar(api)
    activations = iter([(True, 0x101), (True, 0x202)])
    deactivated = []
    monkeypatch.setattr(
        fleetbar,
        "activate_bar",
        lambda *_args, **_kwargs: next(activations),
        raising=False,
    )
    monkeypatch.setattr(
        fleetbar,
        "deactivate_bar",
        lambda _bar, return_hwnd, **_kwargs: deactivated.append(return_hwnd) or True,
        raising=False,
    )

    assert api.activate_fleet_bar(PAGE_A) is True
    assert api._fleetbar_return_hwnd == 0x101
    assert api.activate_fleet_bar(PAGE_A) is True
    assert api._fleetbar_return_hwnd == 0x101
    assert api.reset_fleet_bar_page_width(PAGE_A)["applied"] is True
    assert api._fleetbar_return_hwnd == 0x101
    assert api.deactivate_fleet_bar(PAGE_A) is True
    assert deactivated == [0x101]
    assert api._fleetbar_return_hwnd is None
    assert api.deactivate_fleet_bar(PAGE_A) is False
    assert deactivated == [0x101]


def test_hide_fleet_bar_ends_activation_and_publishes_one_runtime_state(
    api, monkeypatch
):
    from wingman.ui import fleetbar

    _set_resizable_bar(api)
    api._state.settings["fleet_sharing"] = settings.validated_fleet_sharing({})
    _clear_scripts(api._window)
    api._fleetbar_return_hwnd = 0x101
    deactivated = []
    sharing_before = dict(api._state.settings.get("fleet_sharing") or {})
    monkeypatch.setattr(
        fleetbar,
        "deactivate_bar",
        lambda _bar, return_hwnd, **_kwargs: deactivated.append(return_hwnd) or True,
        raising=False,
    )

    result = api.hide_fleet_bar(PAGE_A)
    api._fleet_worker.iterate_once()

    assert result == {"applied": True, "persisted": True, "error": None}
    assert deactivated == [0x101]
    assert api._fleetbar_return_hwnd is None
    assert api._state.settings["fleet_bar"]["enabled"] is False
    assert api._fleetbar_window.hidden is True
    assert len(_fleet_state_pushes(api)) == 1
    assert dict(api._state.settings.get("fleet_sharing") or {}) == sharing_before


def test_hide_fleet_bar_refuses_when_persistence_fails(api, monkeypatch):
    from wingman.ui import api as api_mod
    from wingman.ui import fleetbar

    _set_resizable_bar(api)
    api._state.settings["fleet_sharing"] = settings.validated_fleet_sharing({})
    _clear_scripts(api._window)
    api._fleetbar_return_hwnd = 0x101
    deactivated = []
    sharing_before = dict(api._state.settings.get("fleet_sharing") or {})
    monkeypatch.setattr(
        fleetbar,
        "deactivate_bar",
        lambda _bar, return_hwnd, **_kwargs: deactivated.append(return_hwnd) or True,
        raising=False,
    )
    monkeypatch.setattr(
        api_mod.settings_mod,
        "update_section",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )

    result = api.hide_fleet_bar(PAGE_A)
    api._fleet_worker.iterate_once()

    assert result == {
        "applied": False,
        "persisted": False,
        "error": "Could not save the Fleet Bar setting.",
    }
    assert deactivated == [0x101]
    assert api._fleetbar_return_hwnd is None
    assert api._state.settings["fleet_bar"]["enabled"] is True
    assert api._fleetbar_window.hidden is False
    assert len(_fleet_state_pushes(api)) == 1
    assert dict(api._state.settings.get("fleet_sharing") or {}) == sharing_before


def test_hide_fleet_bar_rolls_back_enabled_state_when_native_hide_fails(
    api, monkeypatch
):
    from wingman.ui import fleetbar

    _set_resizable_bar(api)
    api._state.settings["fleet_sharing"] = settings.validated_fleet_sharing({})
    _clear_scripts(api._window)
    api._fleetbar_return_hwnd = 0x101
    deactivated = []
    sharing_before = dict(api._state.settings.get("fleet_sharing") or {})
    monkeypatch.setattr(
        fleetbar,
        "deactivate_bar",
        lambda _bar, return_hwnd, **_kwargs: deactivated.append(return_hwnd) or True,
        raising=False,
    )
    monkeypatch.setattr(fleetbar, "hide_bar", lambda bar: None)

    result = api.hide_fleet_bar(PAGE_A)
    api._fleet_worker.iterate_once()

    assert result == {
        "applied": False,
        "persisted": False,
        "error": "The Fleet Bar could not be hidden.",
    }
    assert deactivated == [0x101]
    assert api._fleetbar_return_hwnd is None
    assert api._state.settings["fleet_bar"]["enabled"] is True
    assert api._fleetbar_window.hidden is False
    assert len(_fleet_state_pushes(api)) == 1
    assert dict(api._state.settings.get("fleet_sharing") or {}) == sharing_before


def test_hide_fleet_bar_keeps_session_enabled_when_hide_rollback_wont_persist(
    api, monkeypatch
):
    from wingman import paths
    from wingman.ui import api as api_mod
    from wingman.ui import fleetbar

    _set_resizable_bar(api)
    api._state.settings["fleet_sharing"] = settings.validated_fleet_sharing({})
    _clear_scripts(api._window)
    api._fleetbar_return_hwnd = 0x101
    deactivated = []
    sharing_before = dict(api._state.settings.get("fleet_sharing") or {})
    original_update = api_mod.settings_mod.update_section
    calls = 0

    def fail_rollback(doc, section, values, path=None):
        nonlocal calls
        calls += 1
        if calls == 2 and values == {"enabled": True}:
            raise OSError("disk full")
        return original_update(doc, section, values, path)

    monkeypatch.setattr(
        fleetbar,
        "deactivate_bar",
        lambda _bar, return_hwnd, **_kwargs: deactivated.append(return_hwnd) or True,
        raising=False,
    )
    monkeypatch.setattr(fleetbar, "hide_bar", lambda bar: None)
    monkeypatch.setattr(api_mod.settings_mod, "update_section", fail_rollback)

    result = api.hide_fleet_bar(PAGE_A)
    api._fleet_worker.iterate_once()

    assert result["applied"] is False
    assert result["persisted"] is False
    assert "survive restart" in result["error"]
    assert deactivated == [0x101]
    assert api._fleetbar_return_hwnd is None
    assert api._state.settings["fleet_bar"]["enabled"] is True
    assert settings.load(paths.settings_file())["fleet_bar"]["enabled"] is False
    assert api._fleetbar_window.hidden is False
    assert len(_fleet_state_pushes(api)) == 1
    assert dict(api._state.settings.get("fleet_sharing") or {}) == sharing_before


def test_toggle_off_rolls_back_when_verified_native_hide_fails(api, monkeypatch):
    from wingman.ui import fleetbar

    _set_resizable_bar(api)
    _clear_scripts(api._window)
    api._fleetbar_return_hwnd = 0x101
    deactivated = []
    monkeypatch.setattr(
        fleetbar,
        "deactivate_bar",
        lambda _bar, return_hwnd, **_kwargs: deactivated.append(return_hwnd) or True,
        raising=False,
    )
    monkeypatch.setattr(fleetbar, "hide_bar", lambda bar: None)

    result = api.toggle_fleet_bar(False)
    api._fleet_worker.iterate_once()

    assert result == {
        "applied": False,
        "persisted": False,
        "error": "The Fleet Bar could not be hidden.",
    }
    assert deactivated == [0x101]
    assert api._state.settings["fleet_bar"]["enabled"] is True
    assert api._fleetbar_window.hidden is False
    assert len(_fleet_state_pushes(api)) == 1


def test_replacement_retires_activation_session_once(api, monkeypatch):
    from wingman.ui import fleetbar

    api._state.settings["fleet_bar"]["enabled"] = True
    api._fleetbar_window.alive = False
    api._fleetbar_return_hwnd = 0x101
    deactivated = []

    def create_window(_title, _url, **kwargs):
        return FleetWindow(
            width=kwargs["width"],
            height=kwargs["height"],
            x=kwargs["x"],
            y=kwargs["y"],
        )

    monkeypatch.setitem(
        sys.modules, "webview", SimpleNamespace(create_window=create_window)
    )
    monkeypatch.setattr(
        fleetbar,
        "deactivate_bar",
        lambda _bar, return_hwnd, **_kwargs: deactivated.append(return_hwnd) or True,
        raising=False,
    )

    assert api.toggle_fleet_bar(True)["applied"] is True
    assert deactivated == [0x101]
    assert api._fleetbar_return_hwnd is None
    assert api._fleetbar_page_id != PAGE_A
