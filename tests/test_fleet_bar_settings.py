"""Fleet-bar settings schema: defaults, validation, and isolation.

The fleet bar is a second independent floating window (its own WebView2
host), so it shares the same off-by-default/explicit-opt-in posture as
sig_bar and preview.  The tests here match that posture and mirror the
style of tests/test_settings.py's sig_bar coverage.
"""

from wingman import settings


def test_fleet_bar_defaults_off_with_no_position():
    assert settings.load()["fleet_bar"] == {
        "enabled": False,
        "x": None,
        "y": None,
    }


def test_fleet_bar_validation_rejects_bool_coordinates():
    value = settings.validated_fleet_bar({"enabled": True, "x": True, "y": "12"})
    assert value == {"enabled": True, "x": None, "y": None}


def test_fleet_bar_defaults_are_not_shared():
    first = settings._fresh_defaults()
    second = settings._fresh_defaults()
    first["fleet_bar"]["enabled"] = True
    assert second["fleet_bar"]["enabled"] is False


def test_save_normalises_malformed_fleet_bar_in_the_file(tmp_path):
    """settings.save() bypasses update()'s _normalize() call, so
    _save_locked must guarantee the persisted fleet_bar shape itself.
    A caller passing booleans as coordinates or missing keys must not
    corrupt the stored document."""
    import json

    p = tmp_path / "s.json"
    settings.save(
        {
            **settings._fresh_defaults(),
            "fleet_bar": {"enabled": True, "x": True, "y": "bad"},
        },
        p,
    )
    raw = json.loads(p.read_text())
    assert raw["fleet_bar"] == {"enabled": True, "x": None, "y": None}


def test_save_normalises_partial_fleet_bar_in_the_file(tmp_path):
    """A partial section (missing x/y) written via save() must be stored
    with the full normalized shape, not the partial dict."""
    import json

    p = tmp_path / "s.json"
    settings.save(
        {**settings._fresh_defaults(), "fleet_bar": {"enabled": True}},
        p,
    )
    raw = json.loads(p.read_text())
    assert raw["fleet_bar"] == {"enabled": True, "x": None, "y": None}
