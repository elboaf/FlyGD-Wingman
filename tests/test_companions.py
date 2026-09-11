"""Persisted authority and source identity boundaries for companion previews."""

from dataclasses import FrozenInstanceError, replace
from uuid import uuid4

import pytest

from wingman.preview import companions as c
from wingman.preview.layout import Rect


def definition(**changes):
    item = c.CompanionDefinition(
        1,
        uuid4().hex,
        "Mapper",
        True,
        "whole",
        c.SourceDescriptor(
            r"c:\apps\mapper.exe", "mapper.exe", "Mapper", "Map", "exact", "Map"
        ),
        Rect(10, 20, 320, 210),
        None,
    )
    return replace(item, **changes)


def test_roundtrip_drops_unknown_native_identity_without_changing_id():
    item = definition()
    raw = c.serialize_definitions((item,))
    raw[0]["hwnd"] = 42
    raw[0]["source"]["pid"] = 7
    assert c.validate_definitions(raw) == (item,)
    assert "hwnd" not in c.serialize_definitions(c.validate_definitions(raw))[0]
    with pytest.raises(FrozenInstanceError):
        item.label = "changed"


def test_duplicate_ids_all_drop_but_other_entries_survive():
    item, other = definition(), definition()
    raw = c.serialize_definitions((item, other, item))
    assert c.validate_definitions(raw) == (other,)


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "not-an-id"),
        ("enabled", 1),
        ("version", True),
        ("mode", "other"),
        ("label", "x" * 81),
        ("window", {"x": 0, "y": 0, "w": False, "h": 20}),
    ],
)
def test_malformed_definition_drops_individually(field, value):
    raw = c.serialize_definitions((definition(),))
    raw[0][field] = value
    assert c.validate_definitions(raw) == ()


def test_source_identity_is_windows_normalized_and_title_literal():
    raw = c.serialize_definitions((definition(),))[0]["source"]
    raw["executable_path"] = "C:/APPS/Mapper.exe"
    raw["executable_name"] = "Mapper.exe"
    source = c.validate_descriptor(raw)
    assert source.executable_path == r"c:\apps\mapper.exe"
    binding = c.SourceBinding(
        5, 2, 3, r"C:\Apps\Mapper.exe", "Mapper", "Map", (800, 600)
    )
    assert c.matching_sources(source, (binding,)) == (binding,)
    assert not c.matching_sources(source, (replace(binding, title="Map 2"),))
    assert (
        len(
            c.matching_sources(
                replace(source, title_mode="contains"),
                (binding, replace(binding, hwnd=9)),
            )
        )
        == 2
    )
    raw["title_hint"] = "Map\n"
    with pytest.raises(ValueError):
        c.validate_descriptor(raw)


def test_regions_reuse_normalized_edge_coverage_and_reject_unusable_sizes():
    region = c.region_from_pixels(Rect(10, 20, 50, 40), (100, 100))
    assert c.region_to_pixels(region, (200, 300)) == Rect(20, 60, 100, 121)
    assert c.region_to_pixels(region, (10, 10)) is None
    item = definition(mode="region", region=region)
    assert c.validate_definitions(c.serialize_definitions((item,))) == (item,)
    raw = c.serialize_definitions((item,))
    raw[0]["region"]["x"] = float("nan")
    assert c.validate_definitions(raw) == ()


def test_settings_defaults_and_unrelated_updates_preserve_companions(tmp_path):
    from wingman import settings

    state = settings.load(tmp_path / "settings.json")
    assert state["companion_previews"] == {"enabled": False, "definitions": []}
    raw = c.serialize_definitions((definition(),))
    with settings.update(state, tmp_path / "settings.json") as data:
        data["companion_previews"] = {"enabled": True, "definitions": raw}
    with settings.update(state, tmp_path / "settings.json") as data:
        data["privacy"] = "private"
    assert settings.load(tmp_path / "settings.json")["companion_previews"] == {
        "enabled": True,
        "definitions": raw,
    }
