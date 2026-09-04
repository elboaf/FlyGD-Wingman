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
from tests.test_api import make_api
from wingman.telemetry.model import FleetRow, FleetSnapshot, StreamHealth


class FleetWindow(FakeWindow):
    def __init__(self):
        super().__init__()
        self.hidden = False
        self.resized = []
        self.moved = []
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

    def move(self, x, y):
        self.moved.append((x, y))


class FakeTelemetry:
    def __init__(self):
        self.reconciled = 0
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


@pytest.fixture
def api(tmp_path):
    telemetry = FakeTelemetry()
    built = make_api(tmp_path, telemetry=telemetry)
    built._state.settings["fleet_bar"] = {
        "enabled": False,
        "x": None,
        "y": None,
        "seen": [],
        "hidden": [],
    }
    built._fleetbar_window = FleetWindow()
    built._fleetbar_ready = True
    return built


def _fleet_scripts(window):
    scripts = getattr(window, "calls", getattr(window, "evaluated", []))
    return [call for call in scripts if "onFleetSnapshot" in call]


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
        inner._fleetbar_window.hidden = hidden
        return inner._fleetbar_window

    monkeypatch.setattr(fleetbar, "create", fake_create)

    result = api.toggle_fleet_bar(True)

    assert result["applied"] is True
    assert api._state.settings["fleet_bar"]["enabled"] is True
    assert telemetry.reconciled == 1
    assert created == [True]
    assert api._fleetbar_window.hidden is True
    api.fleet_bar_ready()
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
    state = json.loads(state_push.split("window.onFleetBarState(", 1)[1][:-1])
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

    script = _fleet_scripts(api._fleetbar_window)[-1]
    payload = json.loads(script.split("window.onFleetSnapshot(", 1)[1][:-1])
    assert payload["rows"] == []


def test_page_readiness_survives_disable_during_boot(api):
    api._state.settings.setdefault("fleet_bar", {})["enabled"] = False
    api._fleetbar_window.hidden = True
    api._fleetbar_ready = False

    api.fleet_bar_ready()
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
            FleetRow("Alice", 43, ("SCRAM/POINT",)),
            FleetRow("Bravo", None, (), "NO LOG"),
        ),
        stream_health=StreamHealth(state="stale", detail="3.2s since poll"),
        metric_error="clock skew",
        activation_generation=1,
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
    """No DOM harness exists, so pin the guard before any DOM mutation."""
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
    api._fleet_pending_seen = ["Pending", "Current"]
    api._fleet_expected_generation = 1

    api._receive_fleet_snapshot(
        FleetSnapshot(
            rows=(FleetRow("Current", 1),),
            stream_health=StreamHealth(state="active"),
            activation_generation=1,
        )
    )

    assert api._state.settings["fleet_bar"]["seen"] == [
        "Current",
        "Pending",
        "Persisted",
    ]
    assert api._fleet_pending_seen == []


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

    assert api._state.settings["fleet_bar"]["seen"] == ["Persisted"]
    assert api._fleet_pending_seen == ["Alice"]
    api._receive_fleet_snapshot(
        FleetSnapshot(
            rows=(FleetRow("Alice", 99),),
            stream_health=StreamHealth(state="active"),
            activation_generation=1,
        )
    )
    assert calls == 1

    monkeypatch.setattr(api_mod.settings_mod, "_save_locked", original_save)
    api._receive_fleet_snapshot(
        FleetSnapshot(
            rows=(FleetRow("Alice", 99), FleetRow("Bravo", 1)),
            stream_health=StreamHealth(state="active"),
            activation_generation=1,
        )
    )

    assert api._state.settings["fleet_bar"]["seen"] == [
        "Alice",
        "Bravo",
        "Persisted",
    ]
    assert api._fleet_pending_seen == []


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
    assert api._fleet_pending_seen == ["Alice"]

    monkeypatch.setattr(api_mod.settings_mod, "_save_locked", original_save)
    api.toggle_fleet_bar(False)
    api.toggle_fleet_bar(True)

    assert api._fleet_snapshot is None
    assert api._fleet_pending_seen == ["Alice"]
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
    api._window.evaluated.clear()

    api._receive_fleet_snapshot(
        FleetSnapshot(
            rows=(FleetRow("Alice", 99),),
            stream_health=StreamHealth(state="active", detail="fresh"),
            metric_error="late sample",
            activation_generation=1,
        )
    )

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
    assert "Alice" not in [row["character"] for row in api.fleet_bar_snapshot()["rows"]]
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
            rows=(FleetRow("Alice", 43, ("SCRAM",)),),
            stream_health=StreamHealth(state="active"),
            activation_generation=1,
        )
    )

    api.set_fleet_bar_character_visible("Alice", False)
    hidden = api.fleet_bar_snapshot()
    api.set_fleet_bar_character_visible("Alice", True)
    restored = api.fleet_bar_snapshot()

    assert hidden["rows"] == []
    assert hidden["running_count"] == 1
    assert hidden["revision"] < restored["revision"]
    assert restored["rows"] == [
        {"character": "Alice", "dps": 43, "ewar": ["SCRAM"], "log_status": None}
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
    older = api.fleet_bar_snapshot()
    older_settings = api.fleet_bar_settings()

    api._install_fleet_generation(2)
    newer = api.fleet_bar_snapshot()
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
        inner._fleetbar_window.hidden = hidden
        return inner._fleetbar_window

    monkeypatch.setattr(fleetbar, "create", fake_create)

    fleetbar.restore(api)
    fleetbar.restore(api)
    api.fleet_bar_ready()

    assert created == [True]
    assert api._fleetbar_window.hidden is False


def test_fit_does_not_resurrect_a_disabled_window(api):
    api._state.settings.setdefault("fleet_bar", {})["enabled"] = False

    api.fit_fleet_bar(380, 112)

    assert api._fleetbar_window.resized == []


def test_save_position_and_fit_ignore_invalid_values(api):
    api.save_fleet_bar_pos(25, -40)
    assert api._state.settings["fleet_bar"]["x"] == 25
    assert api._state.settings["fleet_bar"]["y"] == -40

    api._state.settings["fleet_bar"]["enabled"] = True
    api.fit_fleet_bar(380, 112)
    api.fit_fleet_bar(0, "bad")
    api.move_fleet_bar(30, 45)
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
        return SimpleNamespace()

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
    assert calls["url"].endswith("fleetbar.html")
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
    assert "telemetry.subscribe_fleet" in source
    assert "fleetbar.restore" in source
    assert "api._fleetbar_quitting = True" in source
    assert "fleet.destroy()" in source
    assert "api.shutdown_previews()" in source


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
    assert "fleet_bar_ready" in js  # hidden until initial render and fit complete
    assert "screen.availLeft" in js and "move_fleet_bar" in js
    assert "unavailable ? row.log_status" in js  # NO LOG belongs under EWAR
    assert "SCRAM/POINT" not in js  # rendered from telemetry, never guessed here
