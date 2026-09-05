"""Fleet-sharing settings schema: defaults, validation, and isolation.

`fleet_sharing.enabled` is the single predicate that decides whether
Wingman's local combat-log-derived DPS/EWAR display is ever transmitted
to authGD. This tracer ships no UI control for it (see
.superpowers/sdd/2026-09-04-shared-fleet-telemetry-tracer/task-3-report.md's
ruling) -- tests and the isolated tracer harness are its only activation
seams -- so this file pins that an ordinary install can never end up
enabled by accident, and that toggling it never disturbs the unrelated
`fleet_bar` section.
"""

import json

from wingman import settings


def test_fleet_sharing_defaults_off():
    assert settings.load()["fleet_sharing"] == {"enabled": False}


def test_fleet_sharing_validation_rejects_a_non_bool_enabled():
    assert settings.validated_fleet_sharing({"enabled": "yes"}) == {"enabled": False}
    assert settings.validated_fleet_sharing({"enabled": 1}) == {"enabled": False}


def test_fleet_sharing_validation_falls_back_whole_for_a_non_dict_section():
    assert settings.validated_fleet_sharing(None) == {"enabled": False}
    assert settings.validated_fleet_sharing("enabled") == {"enabled": False}
    assert settings.validated_fleet_sharing([True]) == {"enabled": False}


def test_fleet_sharing_validation_accepts_an_explicit_true():
    assert settings.validated_fleet_sharing({"enabled": True}) == {"enabled": True}


def test_fleet_sharing_defaults_are_not_shared():
    first = settings._fresh_defaults()
    second = settings._fresh_defaults()
    first["fleet_sharing"]["enabled"] = True
    assert second["fleet_sharing"]["enabled"] is False


def test_explicit_true_round_trips_through_load_and_save_without_touching_fleet_bar(
    tmp_path,
):
    target = tmp_path / "s.json"
    data = settings._fresh_defaults()
    data["fleet_sharing"]["enabled"] = True

    settings.save(data, target)
    loaded = settings.load(target)

    assert loaded["fleet_sharing"] == {"enabled": True}
    assert loaded["fleet_bar"] == {"enabled": False, "x": None, "y": None}


def test_malformed_input_cannot_enable_sharing_via_direct_save(tmp_path):
    """settings.save() bypasses update()'s _normalize() call, so
    _save_locked must guarantee the persisted fleet_sharing shape itself --
    the same property test_fleet_bar_settings.py pins for fleet_bar."""
    target = tmp_path / "s.json"
    settings.save(
        {**settings._fresh_defaults(), "fleet_sharing": {"enabled": "yes"}},
        target,
    )
    raw = json.loads(target.read_text())
    assert raw["fleet_sharing"] == {"enabled": False}


def test_save_normalises_a_missing_fleet_sharing_section(tmp_path):
    target = tmp_path / "s.json"
    payload = settings._fresh_defaults()
    del payload["fleet_sharing"]
    settings.save(payload, target)
    raw = json.loads(target.read_text())
    assert raw["fleet_sharing"] == {"enabled": False}


def test_enabling_sharing_does_not_affect_fleet_bar_settings(tmp_path):
    target = tmp_path / "s.json"
    data = settings._fresh_defaults()
    with settings.update(data, target) as live:
        live["fleet_sharing"] = {"enabled": True}
        live["fleet_bar"] = {"enabled": True, "x": 5, "y": 9}

    reloaded = settings.load(target)
    assert reloaded["fleet_sharing"] == {"enabled": True}
    assert reloaded["fleet_bar"] == {"enabled": True, "x": 5, "y": 9}


def test_enabling_fleet_bar_does_not_affect_fleet_sharing_settings(tmp_path):
    target = tmp_path / "s.json"
    data = settings._fresh_defaults()
    with settings.update(data, target) as live:
        live["fleet_bar"] = {"enabled": True, "x": 1, "y": 2}

    reloaded = settings.load(target)
    assert reloaded["fleet_bar"] == {"enabled": True, "x": 1, "y": 2}
    assert reloaded["fleet_sharing"] == {"enabled": False}
