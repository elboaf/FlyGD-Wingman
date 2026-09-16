"""Explicit primary snapshots — pure records, not runtime/window ownership."""

import copy
import importlib
from dataclasses import FrozenInstanceError, replace

import pytest

from wingman.preview.geometry import Rect
from wingman.preview.layout import Entry


@pytest.fixture
def model():
    # Keep settings regressions runnable before the new module exists.
    return importlib.import_module("wingman.preview.savedlayouts")


@pytest.fixture
def raw_record():
    return {
        "id": "stable-id",
        "name": "Rolling",
        "characters": {
            "Alice": {
                "visible": True,
                "rect": {"x": -800, "y": -40, "w": 320, "h": 210},
            },
            "Offline": {"visible": False, "rect": None},
        },
    }


def test_record_roundtrip_is_detached_and_excludes_global_fields(model, raw_record):
    raw_record["name"] = "  Rolling  "
    raw_record["characters"]["Alice"]["locked"] = True
    raw_record["characters"]["Alice"]["rect"]["hwnd"] = 123
    record = model.validate_record(raw_record)
    assert record == model.SavedLayout(
        "stable-id",
        "Rolling",
        (
            model.SavedCharacter("Alice", True, Rect(-800, -40, 320, 210)),
            model.SavedCharacter("Offline", False, None),
        ),
    )
    with pytest.raises(FrozenInstanceError):
        record.name = "Changed"
    with pytest.raises(FrozenInstanceError):
        record.characters[0].visible = False
    encoded = model.serialize((record,))
    assert encoded == {
        "version": 1,
        "items": [
            {
                "id": "stable-id",
                "name": "Rolling",
                "characters": {
                    "Alice": {
                        "visible": True,
                        "rect": {"x": -800, "y": -40, "w": 320, "h": 210},
                    },
                    "Offline": {"visible": False, "rect": None},
                },
            }
        ],
    }
    assert model.deserialize(encoded) == (record,)
    encoded["items"][0]["characters"]["Alice"]["rect"]["x"] = 77
    raw_record["characters"].clear()
    assert record.characters[0].rect.x == -800


@pytest.mark.parametrize("raw", [None, [], "bad", 1, True, {}, {"id": "a"}])
def test_non_records_are_refused(model, raw):
    with pytest.raises(ValueError):
        model.validate_record(raw)


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", None),
        ("id", ""),
        ("id", 3),
        ("id", True),
        ("name", None),
        ("name", ""),
        ("name", "  "),
        ("name", 3),
        ("name", "Bad\nname"),
        ("name", "\tRolling"),
        ("name", "Bad\x00name"),
        ("characters", {}),
        ("characters", []),
        ("characters", None),
    ],
)
def test_bad_record_fields_refuse_the_whole_record(model, raw_record, field, value):
    raw_record[field] = value
    with pytest.raises(ValueError):
        model.validate_record(raw_record)


@pytest.mark.parametrize(
    "owner", ["", " Alice", "Alice ", "hwnd:123", "Ali\nce", 7, None]
)
def test_malformed_owner_invalidates_even_a_partly_valid_record(
    model, raw_record, owner
):
    raw_record["characters"][owner] = {"visible": True, "rect": None}
    with pytest.raises(ValueError, match=r"character|owner"):
        model.validate_record(raw_record)


@pytest.mark.parametrize(
    "member",
    [
        None,
        [],
        {},
        {"visible": True},
        {"rect": None},
        {"visible": 1, "rect": None},
        {"visible": "false", "rect": None},
    ],
)
def test_missing_or_non_boolean_member_fields_are_not_guessed(
    model, raw_record, member
):
    raw_record["characters"]["Offline"] = member
    with pytest.raises(ValueError):
        model.validate_record(raw_record)


@pytest.mark.parametrize(
    "rect", [[], {}, [1, 2, 3, 4], "rect", True, {"x": 1, "y": 2, "w": 3}]
)
def test_rect_shape_is_strict(model, raw_record, rect):
    raw_record["characters"]["Alice"]["rect"] = rect
    with pytest.raises(ValueError, match="rectangle"):
        model.validate_record(raw_record)


@pytest.mark.parametrize("field", ["x", "y", "w", "h"])
@pytest.mark.parametrize(
    "value", [True, False, 1.0, "1", None, 2**31, -(2**31) - 1, 10**100]
)
def test_rect_fields_are_signed_win32_integers(model, raw_record, field, value):
    raw_record["characters"]["Alice"]["rect"][field] = value
    with pytest.raises(ValueError, match="rectangle"):
        model.validate_record(raw_record)


@pytest.mark.parametrize(
    "rect",
    [
        Rect(0, 0, 0, 1),
        Rect(0, 0, 1, 0),
        Rect(0, 0, -1, 1),
        Rect(0, 0, 1, -1),
        Rect(2**31 - 1, 0, 1, 1),
        Rect(0, 2**31 - 1, 1, 1),
        Rect(1, 0, 2**31 - 1, 1),
        Rect(0, 1, 1, 2**31 - 1),
    ],
)
def test_extents_and_far_edge_arithmetic_must_be_native_safe(model, raw_record, rect):
    raw_record["characters"]["Alice"]["rect"] = rect._asdict()
    with pytest.raises(ValueError, match="rectangle"):
        model.validate_record(raw_record)


@pytest.mark.parametrize(
    "rect",
    [
        Rect(-(2**31), -(2**31), 1, 1),
        Rect(0, 0, 2**31 - 1, 2**31 - 1),
        Rect(2**31 - 2, 2**31 - 2, 1, 1),
    ],
)
def test_exact_signed_boundaries_and_negative_coordinates_are_valid(
    model, raw_record, rect
):
    raw_record["characters"]["Alice"]["rect"] = rect._asdict()
    assert model.validate_record(raw_record).characters[0].rect == rect


@pytest.mark.parametrize(
    "raw",
    [
        None,
        [],
        {},
        "bad",
        {"items": []},
        {"version": True, "items": []},
        {"version": 1.0, "items": []},
        {"version": 2, "items": []},
        {"version": "1", "items": []},
        {"version": 1, "items": {}},
        {"version": 1, "items": None},
    ],
)
def test_unknown_schema_and_bad_collection_are_not_interpreted(model, raw):
    assert model.deserialize(raw) == ()


def test_load_keeps_first_valid_id_and_casefolded_name_not_partial_members(
    model, raw_record
):
    bad = copy.deepcopy(raw_record)
    bad["characters"]["Offline"]["visible"] = "false"
    duplicate_id = {**raw_record, "name": "Other"}
    duplicate_name = {**raw_record, "id": "another", "name": " rolling "}
    sibling = {**raw_record, "id": "sibling", "name": "Other"}
    loaded = model.deserialize(
        {
            "version": 1,
            "items": [
                bad,
                raw_record,
                duplicate_id,
                duplicate_name,
                sibling,
            ],
        }
    )
    assert [(r.id, r.name) for r in loaded] == [
        ("stable-id", "Rolling"),
        ("sibling", "Other"),
    ]
    assert len(loaded[0].characters) == 2
    assert model.deserialize({"version": 2, "items": [raw_record]}) == ()


def test_exact_case_and_prototype_like_owner_names_are_preserved(model):
    names = ("Alice", "alice", "constructor", "__proto__", "toString")
    record = model.validate_record(
        {
            "id": "opaque",
            "name": "All hidden",
            "characters": {name: {"visible": False, "rect": None} for name in names},
        }
    )
    assert tuple(c.name for c in record.characters) == names
    assert list(model.serialize((record,))["items"][0]["characters"]) == list(names)


def test_no_arbitrary_collection_or_display_name_cap(model, raw_record):
    raw = {
        "version": 1,
        "items": [
            {**raw_record, "id": str(i), "name": str(i) + "x" * 500} for i in range(70)
        ],
    }
    assert len(model.deserialize(raw)) == 70
    assert model.serialize(model.deserialize(raw)) == raw


@pytest.mark.parametrize("duplicate", ["id", "name"])
def test_write_serialization_refuses_duplicate_records(model, raw_record, duplicate):
    first = model.validate_record(raw_record)
    second = replace(first, id="second", name="Second")
    second = replace(
        second, **{duplicate: first.id if duplicate == "id" else " rolling "}
    )
    with pytest.raises(ValueError, match="Duplicate"):
        model.serialize((first, second))


def test_revision_ignores_character_insertion_order_but_tracks_snapshot_changes(
    model, raw_record
):
    record = model.validate_record(raw_record)
    revision = model.record_revision(record)
    assert len(revision) == 64
    assert (
        model.record_revision(replace(record, characters=record.characters[::-1]))
        == revision
    )
    for changed in (
        replace(record, id="other"),
        replace(record, name="Other"),
        replace(record, characters=record.characters[:1]),
        replace(
            record,
            characters=(
                replace(record.characters[0], visible=False),
                record.characters[1],
            ),
        ),
        replace(
            record,
            characters=(replace(record.characters[0], rect=None), record.characters[1]),
        ),
    ):
        assert model.record_revision(changed) != revision


def test_known_owners_unions_every_explicit_source_without_casefold_or_cap(model):
    section = {
        "layouts": {"Geometry": {}},
        "seen": ["Recent", "Same"],
        "excluded": ["Hidden"],
        "hotkeys": {
            "characters": {"Direct": "Ctrl+F1"},
            # The group's NAME is never an owner; its members are.
            "groups": [{"id": "g", "name": "Not an owner", "members": ["Grouped"]}],
        },
        "locked": ["Locked"],
        "never_minimize": ["Minimize"],
        "crops": {"Crop": {}},
        "label_markers": {"Marker": "blue"},
        "saved_layouts": {
            "version": 1,
            "items": [
                {
                    "id": "one",
                    "name": "Not an owner either",
                    "characters": {
                        "Saved only": {"visible": False, "rect": None},
                    },
                }
            ],
        },
    }
    # Legacy rosters allow these names; the new snapshot boundary must not.
    section["seen"] += ["", " Wrong ", "hwnd:1", "Line\nBreak", None, 3]
    owners = model.known_owners(
        section, ("Live", "Same", "same", "__proto__", "constructor")
    )
    assert owners == (
        "Live",
        "Same",
        "same",
        "__proto__",
        "constructor",
        "Geometry",
        "Recent",
        "Hidden",
        "Direct",
        "Grouped",
        "Locked",
        "Minimize",
        "Crop",
        "Marker",
        "Saved only",
    )
    assert model.known_owners({}, ()) == ()
    many = tuple(f"Pilot{i}" for i in range(70))
    assert model.known_owners({"excluded": list(many)}, ()) == many


def test_capture_uses_actual_then_retained_then_current_geometry_not_saved_geometry(
    model,
):
    section = {
        "layouts": {
            "Live": {"x": 1, "y": 2, "w": 3, "h": 4, "locked": True},
            "Retained": {"x": 1, "y": 2, "w": 3, "h": 4, "locked": False},
            "Current": {"x": 10, "y": 20, "w": 30, "h": 40, "locked": True},
        },
        "excluded": ["Hidden"],
        "seen": ["Offline", "hwnd:1"],
        "saved_layouts": {
            "version": 1,
            "items": [
                {
                    "id": "s",
                    "name": "Saved",
                    "characters": {
                        "Saved only": {
                            "visible": False,
                            "rect": {"x": 1, "y": 2, "w": 3, "h": 4},
                        },
                    },
                }
            ],
        },
        "hide_active_preview": True,
        "hide_on_lost_focus": True,
        "lock_default": True,
    }
    retained = {
        "Live": Entry(Rect(20, 30, 40, 50)),
        "Retained": Entry(Rect(-2, -3, 40, 50), True),
        "Retained only": Entry(Rect(1, 2, 3, 4)),
    }
    live = {"Live": Rect(90, 80, 70, 60), "Untouched live": Rect(4, 5, 6, 7)}
    before = copy.deepcopy((section, retained, live))
    chars = {c.name: c for c in model.capture_characters(section, retained, live)}
    assert {name: c.rect for name, c in chars.items()} == {
        "Live": Rect(90, 80, 70, 60),
        "Retained": Rect(-2, -3, 40, 50),
        "Current": Rect(10, 20, 30, 40),
        "Hidden": None,
        "Offline": None,
        "Saved only": None,
        "Retained only": Rect(1, 2, 3, 4),
        "Untouched live": Rect(4, 5, 6, 7),
    }
    assert {name for name, c in chars.items() if not c.visible} == {"Hidden"}
    assert (section, retained, live) == before


def test_capture_refuses_empty_or_unsafe_geometry_instead_of_partial_snapshot(model):
    with pytest.raises(ValueError, match="character"):
        model.capture_characters({"seen": ["hwnd:1"]}, {}, {})
    with pytest.raises(ValueError, match="rectangle"):
        model.capture_characters(
            {"seen": ["Safe"]}, {}, {"Unsafe": Rect(2**31 - 1, 0, 2, 1)}
        )


def test_apply_changes_only_recorded_geometry_and_visibility_and_keeps_legacy_locks(
    model,
):
    section = {
        "layouts": {
            "Changed": {"x": 1, "y": 2, "w": 3, "h": 4, "locked": True},
            "Null": {"x": 5, "y": 6, "w": 7, "h": 8, "locked": True},
            "Absent": {"x": 9, "y": 10, "w": 11, "h": 12, "locked": False},
        },
        "excluded": ["Absent", "Changed"],
        "locked": ["Null"],
        "lock_default": False,
        "restore_preview_positions": False,
        "crops": {"Changed": {"enabled": True}},
        "hotkeys": {"characters": {"Changed": "Ctrl+F1"}},
        "label_markers": {"Changed": "cyan"},
        "width": 640,
        "opacity": 100,
        "never_minimize": ["Changed"],
        "saved_layouts": {"version": 1, "items": []},
    }
    snapshot = model.SavedLayout(
        "s",
        "Apply",
        (
            model.SavedCharacter("Changed", True, Rect(-100, -200, 320, 210)),
            model.SavedCharacter("Null", False, None),
            model.SavedCharacter("New", False, Rect(1, 2, 30, 40)),
        ),
    )
    expected = copy.deepcopy(section)
    expected["layouts"]["Changed"] = {
        "x": -100,
        "y": -200,
        "w": 320,
        "h": 210,
        "locked": True,
    }
    expected["layouts"]["New"] = {"x": 1, "y": 2, "w": 30, "h": 40, "locked": False}
    expected["excluded"] = ["Absent", "Null", "New"]
    model.apply_snapshot(section, snapshot)
    assert section == expected
    model.apply_snapshot(section, snapshot)
    assert section == expected


@pytest.mark.parametrize(
    "bad", ["visibility", "rectangle", "owner", "duplicate", "empty"]
)
def test_invalid_constructed_records_refuse_serialization_and_apply_before_any_mutation(
    model, bad
):
    good = model.SavedCharacter("First", False, Rect(1, 2, 3, 4))
    other = model.SavedCharacter("Other", True, None)
    if bad == "visibility":
        other = replace(other, visible=1)
    elif bad == "rectangle":
        other = replace(other, rect=Rect(0, 0, True, 2))
    elif bad == "owner":
        other = replace(other, name="hwnd:1")
    elif bad == "duplicate":
        other = replace(other, name="First")
    snapshot = model.SavedLayout("id", "Name", () if bad == "empty" else (good, other))
    section = {"layouts": {}, "excluded": []}
    with pytest.raises(ValueError):
        model.serialize((snapshot,))
    with pytest.raises(ValueError):
        model.apply_snapshot(section, snapshot)
    assert section == {"layouts": {}, "excluded": []}
