"""Presentation expires combat without changing the collected/remembered roster."""

from uuid import UUID

from tests.test_fleet_bar import (
    _headless_fleet_window_helpers as _headless_fleet_window_helpers,
)
from tests.test_fleet_bar import api as api
from wingman.telemetry.model import (
    CombatActivity,
    EffectObservation,
    FleetRow,
    FleetSnapshot,
    StreamHealth,
)


def test_inactive_filter_preserves_roster_and_rearms_at_activity_deadline(api):
    now = [100.0]
    api._fleet_clock = lambda: now[0]
    api._fleet_expected_generation = 1
    frame = FleetSnapshot(
        rows=(
            FleetRow(
                "Active",
                0,
                incoming_dps=0,
                combat=CombatActivity(130.0, (UUID(int=1), 1)),
            ),
            FleetRow("Quiet", 0, incoming_dps=0, combat=CombatActivity()),
        ),
        stream_health=StreamHealth(state="active"),
        activation_generation=1,
        sampled_at_mono=100.0,
    )
    api._receive_fleet_snapshot(frame)
    result = api.fleet_bar_set_hide_inactive(True)
    assert result["applied"] and result["persisted"]
    with api._fleet_presentation_lock:
        before = api._fleet_payloads_locked()[1]
    assert [r["character"] for r in before["rows"]] == ["Active"]
    assert before["running_count"] == 2
    assert {r["name"] for r in api.fleet_bar_settings()["characters"]} == {
        "Active",
        "Quiet",
    }
    assert api._present_fleet_snapshot() == 130.0
    now[0] = 130.0
    with api._fleet_presentation_lock:
        after = api._fleet_payloads_locked()[1]
    assert after["rows"] == [] and after["revision"] > before["revision"]
    assert api._fleet_snapshot is frame


def test_local_effect_names_and_kinds_expire_independently_without_new_snapshot(api):
    now = [100.0]
    api._fleet_clock = lambda: now[0]
    api._fleet_expected_generation = 1
    activity = CombatActivity(
        130.0,
        (UUID(int=1), 1),
        (
            EffectObservation("POINT", 105.0, (UUID(int=1), 2), "Tackler"),
            EffectObservation("NEUT", 110.0, (UUID(int=1), 3)),
        ),
    )
    api._receive_fleet_snapshot(
        FleetSnapshot(
            rows=(FleetRow("Active", 0, combat=activity),),
            stream_health=StreamHealth(state="active"),
            activation_generation=1,
        )
    )
    with api._fleet_presentation_lock:
        first = api._fleet_payloads_locked()[1]
    assert first["rows"][0]["ewar_sources"] == ["POINT: Tackler"]
    now[0] = 105.0
    with api._fleet_presentation_lock:
        second = api._fleet_payloads_locked()[1]
    assert second["rows"][0]["ewar"] == ["NEUT"]
    assert not second["rows"][0].get("ewar_sources")
    assert second["revision"] > first["revision"]
