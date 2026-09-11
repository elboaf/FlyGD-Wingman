"""Fleet-bar settings schema: defaults, validation, and isolation.

The fleet bar is a second independent floating window (its own WebView2
host), so it shares the same off-by-default/explicit-opt-in posture as
sig_bar and preview. The preferred content width is part of that
persisted contract: later resize work needs one authoritative settings
source rather than ad-hoc literals.
"""

import json

import pytest

from wingman import settings


def _fleet_bar(**overrides):
    value = {
        "enabled": False,
        "x": None,
        "y": None,
        "preferred_content_width": 500,
        "seen": [],
        "hidden": [],
    }
    value.update(overrides)
    return value


def test_fleet_bar_width_contract_constants_match_the_spec():
    """Later Fleet Bar tasks reuse one settings-owned width contract."""
    assert getattr(settings, "FLEET_BAR_MIN_PREFERRED_CONTENT_WIDTH", None) == 420
    assert getattr(settings, "FLEET_BAR_DEFAULT_PREFERRED_CONTENT_WIDTH", None) == 500
    assert getattr(settings, "FLEET_BAR_MAX_PREFERRED_CONTENT_WIDTH", None) == 720


def test_fleet_bar_defaults_off_with_default_preferred_content_width(tmp_path):
    assert settings.load(tmp_path / "missing.json")["fleet_bar"] == _fleet_bar()


def test_fleet_bar_load_migrates_a_document_missing_preferred_content_width(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(
        json.dumps(
            {
                "fleet_bar": {
                    "enabled": True,
                    "x": 12,
                    "y": 34,
                    "seen": ["Alice"],
                    "hidden": ["Bravo"],
                }
            }
        )
    )
    assert settings.load(p)["fleet_bar"] == _fleet_bar(
        enabled=True,
        x=12,
        y=34,
        seen=["Alice"],
        hidden=["Bravo"],
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (420, 420),
        (500, 500),
        (720, 720),
        (419, 420),
        (721, 720),
        (True, 500),
        (False, 500),
        ("500", 500),
        (None, 500),
    ],
)
def test_fleet_bar_validates_preferred_content_width(raw, expected):
    value = settings.validated_fleet_bar({"preferred_content_width": raw})
    assert value["preferred_content_width"] == expected


def test_fleet_bar_validation_rejects_bool_coordinates():
    value = settings.validated_fleet_bar(
        {"enabled": True, "x": True, "y": "12", "preferred_content_width": 720}
    )
    assert value == _fleet_bar(enabled=True, preferred_content_width=720)


def test_fleet_bar_defaults_are_not_shared():
    first = settings._fresh_defaults()
    second = settings._fresh_defaults()
    first["fleet_bar"]["enabled"] = True
    assert second["fleet_bar"] == _fleet_bar()


def test_fleet_bar_validates_character_rosters():
    value = settings.validated_fleet_bar(
        {
            "enabled": True,
            "seen": ["Alice", "", 4, "hwnd:0x1", "Alice", "Bravo"],
            "hidden": ["Bravo", None, "Bravo", "Carol"],
        }
    )
    assert value == _fleet_bar(
        enabled=True, seen=["Alice", "Bravo"], hidden=["Bravo", "Carol"]
    )


def test_fleet_bar_character_rosters_are_capped():
    names = [f"Character {index}" for index in range(70)]
    value = settings.validated_fleet_bar({"seen": names, "hidden": names})
    assert value["seen"] == names[:64]
    assert value["hidden"] == names[:64]


def test_save_normalises_invalid_fleet_bar_width_and_unknown_keys_in_the_file(tmp_path):
    """settings.save() bypasses update()'s _normalize() call, so
    _save_locked must guarantee the persisted fleet_bar shape itself.
    Unknown keys and invalid widths must not survive a direct save."""
    p = tmp_path / "s.json"
    settings.save(
        {
            **settings._fresh_defaults(),
            "fleet_bar": {
                "enabled": True,
                "x": True,
                "y": "bad",
                "preferred_content_width": "wide",
                "seen": ["Alice"],
                "hidden": ["Bravo"],
                "bogus": 1,
            },
        },
        p,
    )
    raw = json.loads(p.read_text())
    assert raw["fleet_bar"] == _fleet_bar(
        enabled=True,
        seen=["Alice"],
        hidden=["Bravo"],
    )


def test_save_normalises_partial_fleet_bar_in_the_file(tmp_path):
    """A partial section written via save() must be stored with the full
    normalized shape, including the default preferred width."""
    p = tmp_path / "s.json"
    settings.save(
        {**settings._fresh_defaults(), "fleet_bar": {"enabled": True}},
        p,
    )
    raw = json.loads(p.read_text())
    assert raw["fleet_bar"] == _fleet_bar(enabled=True)


def test_load_then_save_materialises_preferred_content_width_for_old_documents(
    tmp_path,
):
    p = tmp_path / "s.json"
    p.write_text(
        json.dumps(
            {
                "fleet_bar": {
                    "enabled": True,
                    "x": 5,
                    "y": 9,
                    "seen": ["Alice"],
                    "hidden": ["Bravo"],
                }
            }
        )
    )

    loaded = settings.load(p)
    assert loaded["fleet_bar"] == _fleet_bar(
        enabled=True,
        x=5,
        y=9,
        seen=["Alice"],
        hidden=["Bravo"],
    )

    settings.save(loaded, p)
    assert json.loads(p.read_text())["fleet_bar"] == _fleet_bar(
        enabled=True,
        x=5,
        y=9,
        seen=["Alice"],
        hidden=["Bravo"],
    )
