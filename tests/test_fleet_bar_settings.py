"""Fleet-bar settings schema: defaults, validation, and isolation.

The fleet bar is a second independent floating window (its own WebView2
host), so it shares the same off-by-default/explicit-opt-in posture as
sig_bar and preview.  The tests here match that posture and mirror the
style of tests/test_settings.py's sig_bar coverage.
"""

import json

from wingman import settings


def test_fleet_bar_defaults_off_with_no_position():
    assert settings.load()["fleet_bar"] == {
        "enabled": False,
        "x": None,
        "y": None,
        "seen": [],
        "hidden": [],
    }


def test_fleet_bar_validation_rejects_bool_coordinates():
    value = settings.validated_fleet_bar({"enabled": True, "x": True, "y": "12"})
    assert value == {
        "enabled": True,
        "x": None,
        "y": None,
        "seen": [],
        "hidden": [],
    }


def test_fleet_bar_defaults_are_not_shared():
    first = settings._fresh_defaults()
    second = settings._fresh_defaults()
    first["fleet_bar"]["enabled"] = True
    assert second["fleet_bar"]["enabled"] is False
    assert second["fleet_bar"]["seen"] == []
    assert second["fleet_bar"]["hidden"] == []


def test_fleet_bar_validates_character_rosters():
    value = settings.validated_fleet_bar(
        {
            "enabled": True,
            "seen": ["Alice", "", 4, "hwnd:0x1", "Alice", "Bravo"],
            "hidden": ["Bravo", None, "Bravo", "Carol"],
        }
    )
    assert value["seen"] == ["Alice", "Bravo"]
    assert value["hidden"] == ["Bravo", "Carol"]


def test_fleet_bar_character_rosters_are_capped():
    names = [f"Character {index}" for index in range(70)]
    value = settings.validated_fleet_bar({"seen": names, "hidden": names})
    assert value["seen"] == names[:64]
    assert value["hidden"] == names[:64]


def test_save_normalises_malformed_fleet_bar_in_the_file(tmp_path):
    """settings.save() bypasses update()'s _normalize() call, so
    _save_locked must guarantee the persisted fleet_bar shape itself.
    A caller passing booleans as coordinates or missing keys must not
    corrupt the stored document."""
    p = tmp_path / "s.json"
    settings.save(
        {
            **settings._fresh_defaults(),
            "fleet_bar": {"enabled": True, "x": True, "y": "bad"},
        },
        p,
    )
    raw = json.loads(p.read_text())
    assert raw["fleet_bar"] == {
        "enabled": True,
        "x": None,
        "y": None,
        "seen": [],
        "hidden": [],
    }


def test_save_normalises_partial_fleet_bar_in_the_file(tmp_path):
    """A partial section (missing x/y) written via save() must be stored
    with the full normalized shape, not the partial dict."""
    p = tmp_path / "s.json"
    settings.save(
        {**settings._fresh_defaults(), "fleet_bar": {"enabled": True}},
        p,
    )
    raw = json.loads(p.read_text())
    assert raw["fleet_bar"] == {
        "enabled": True,
        "x": None,
        "y": None,
        "seen": [],
        "hidden": [],
    }
