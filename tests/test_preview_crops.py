"""Pure crop geometry and the single-definition persistence boundary."""

from dataclasses import replace

import pytest

from wingman.preview.geometry import Rect


def test_normalized_source_scales_with_client_dimensions():
    from wingman.preview.crops import source_from_pixels, source_to_pixels
    from wingman.preview.geometry import Rect

    source = source_from_pixels(Rect(320, 180, 640, 360), (1280, 720))
    assert source_to_pixels(source, (1920, 1080)) == Rect(480, 270, 960, 540)


@pytest.mark.parametrize(
    "rect,size",
    [
        (Rect(0, 0, 16, 16), (True, 720)),
        (Rect(0, 0, 16, 16), (1280, False)),
        (Rect(0, 0, 16, 16), (1280.0, 720)),
        (Rect(0, 0, 16, 16), (1280, 0)),
        (Rect(0, 0, 16, 16), (-1280, 720)),
        (Rect(0, 0, 16, 16), (float("nan"), 720)),
        (Rect(0, 0, 16, 16), (1280, float("inf"))),
        (Rect(True, 0, 16, 16), (1280, 720)),
        (Rect(0, 0, 16.0, 16), (1280, 720)),
        (Rect(-1, 0, 32, 32), (1280, 720)),
        (Rect(0, -1, 32, 32), (1280, 720)),
        (Rect(1270, 0, 32, 32), (1280, 720)),
        (Rect(0, 710, 32, 32), (1280, 720)),
        (Rect(0, 0, 15, 16), (1280, 720)),
        (Rect(0, 0, 16, 15), (1280, 720)),
        (Rect(0, 0, 0, 32), (1280, 720)),
        (Rect(0, 0, 32, -32), (1280, 720)),
    ],
)
def test_invalid_pixel_selection_is_refused(rect, size):
    from wingman.preview.crops import source_from_pixels

    with pytest.raises(ValueError):
        source_from_pixels(rect, size)


@pytest.mark.parametrize(
    "size", [(30, 32), (32, 30), (0, 100), (True, 100), (100, float("nan"))]
)
def test_current_source_too_small_or_invalid_cannot_render(size):
    from wingman.preview.crops import source_from_pixels, source_to_pixels

    source = source_from_pixels(Rect(0, 0, 16, 16), (32, 32))
    assert source_to_pixels(source, size) is None


def test_current_source_minimum_and_exact_far_edges():
    from wingman.preview.crops import source_from_pixels, source_to_pixels

    source = source_from_pixels(Rect(64, 64, 64, 64), (128, 128))
    assert source_to_pixels(source, (32, 32)) == Rect(16, 16, 16, 16)


def test_fractional_edges_round_outward_without_using_diagnostics():
    from wingman.preview.crops import source_from_pixels, source_to_pixels

    source = source_from_pixels(Rect(1, 1, 20, 20), (100, 100))
    source = replace(source, original_client_w=3000, original_px=Rect(90, 90, 3, 3))
    assert source_to_pixels(source, (128, 128)) == Rect(1, 1, 26, 26)


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), -float("inf"), True, "0.5"]
)
@pytest.mark.parametrize("field", ["x", "y", "w", "h"])
def test_invalid_normalized_numbers_cannot_render(field, value):
    from wingman.preview.crops import source_from_pixels, source_to_pixels

    source = source_from_pixels(Rect(0, 0, 32, 32), (128, 128))
    assert source_to_pixels(replace(source, **{field: value}), (128, 128)) is None


@pytest.mark.parametrize(
    "rect,size",
    [(Rect(13, 17, 213, 109), (1280, 720)), (Rect(3, 7, 67, 53), (997, 541))],
)
def test_fractional_pixel_round_trip_only_adds_subpixel_edge_coverage(rect, size):
    from wingman.preview.crops import source_from_pixels, source_to_pixels

    result = source_to_pixels(source_from_pixels(rect, size), size)
    assert 0 <= rect.x - result.x <= 1
    assert 0 <= rect.y - result.y <= 1
    assert 0 <= result.right - rect.right <= 1
    assert 0 <= result.bottom - rect.bottom <= 1


@pytest.mark.parametrize(
    "selection,destination,size,expected",
    [
        (
            Rect(120, 80, 200, 100),
            Rect(20, 30, 400, 200),
            (1280, 720),
            Rect(320, 180, 640, 360),
        ),
        (
            Rect(320, 180, -200, -100),
            Rect(20, 30, 400, 200),
            (1280, 720),
            Rect(320, 180, 640, 360),
        ),
        (
            Rect(-20, -10, 1000, 1000),
            Rect(20, 30, 400, 200),
            (1280, 720),
            Rect(0, 0, 1280, 720),
        ),
        (Rect(21, 31, 20, 20), Rect(20, 30, 100, 100), (128, 128), Rect(1, 1, 26, 26)),
        (Rect(0, 0, 10, 10), Rect(20, 30, 400, 200), (1280, 720), None),
        (Rect(20, 30, 0, 50), Rect(20, 30, 400, 200), (1280, 720), None),
        (Rect(20, 30, 15, 16), Rect(20, 30, 100, 100), (100, 100), None),
        (Rect(20, 30, 16, 15), Rect(20, 30, 100, 100), (100, 100), None),
        (Rect(20, 30, 16, 16), Rect(20, 30, 100, 100), (100, 100), Rect(0, 0, 16, 16)),
        (Rect(20, 30, 50, 50), Rect(20, 30, 0, 100), (100, 100), None),
        (Rect(20, 30, 50, 50), Rect(20, 30, 100, -100), (100, 100), None),
        (Rect(20, 30, 50, 50), Rect(20, 30, 100, 100), (True, 100), None),
        (Rect(20, 30, 50, 50), Rect(20, 30, 100, 100), (100, 0), None),
        (Rect(20, 30, 50, 50), Rect(20, 30, 100.0, 100), (100, 100), None),
        (Rect(False, 30, 50, 50), Rect(20, 30, 100, 100), (100, 100), None),
        (Rect(20, float("nan"), 50, 50), Rect(20, 30, 100, 100), (100, 100), None),
        (Rect(20, 30, float("inf"), 50), Rect(20, 30, 100, 100), (100, 100), None),
    ],
)
def test_picker_selection_maps_inset_clamped_and_reversed_drags(
    selection, destination, size, expected
):
    from wingman.preview.crops import map_selection

    assert map_selection(selection, destination, size) == expected


def _raw_crop():
    return {
        "version": 1,
        "enabled": False,
        "source": {
            "x": 0.25,
            "y": 0.125,
            "w": 0.5,
            "h": 0.5,
            "original_client_w": 1280,
            "original_client_h": 720,
            "original_px": [320, 90, 640, 360],
        },
        "window": {"x": -800, "y": -40, "w": 320, "h": 180},
    }


def test_single_definition_round_trips_with_negative_destination_and_disabled_state():
    from wingman.preview.crops import CropDefinition, CropSource, deserialize, serialize

    raw = {"Alice": _raw_crop()}
    definitions = deserialize(raw)
    assert definitions == {
        "Alice": CropDefinition(
            CropSource(0.25, 0.125, 0.5, 0.5, 1280, 720, Rect(320, 90, 640, 360)),
            Rect(-800, -40, 320, 180),
            enabled=False,
        )
    }
    assert serialize(definitions) == raw
    assert deserialize(serialize(definitions)) == definitions
    raw["Alice"]["source"]["original_px"][0] = 999
    assert definitions["Alice"].source.original_px.x == 320


@pytest.mark.parametrize("raw", [None, [], "crop", 7, True])
def test_malformed_crop_section_falls_back_to_empty(raw):
    from wingman.preview.crops import deserialize

    assert deserialize(raw) == {}


@pytest.mark.parametrize("name", ["", "   ", "hwnd:123", " hwnd:123 ", 123, None])
def test_only_named_characters_can_own_saved_crops(name):
    from wingman.preview.crops import deserialize

    assert tuple(deserialize({name: _raw_crop(), "Good": _raw_crop()})) == ("Good",)


@pytest.mark.parametrize("value", [None, [], [_raw_crop()], "crop", {}, {"version": 1}])
def test_malformed_single_entry_drops_without_losing_other_characters(value):
    from wingman.preview.crops import deserialize

    assert tuple(deserialize({"Bad": value, "Good": _raw_crop()})) == ("Good",)


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", 2),
        ("version", True),
        ("version", 1.0),
        ("version", "1"),
        ("version", None),
        ("enabled", 1),
        ("enabled", "false"),
        ("enabled", None),
    ],
)
def test_version_and_enabled_are_strictly_typed(field, value):
    from wingman.preview.crops import deserialize

    bad = _raw_crop()
    bad[field] = value
    assert tuple(deserialize({"Bad": bad, "Good": _raw_crop()})) == ("Good",)


@pytest.mark.parametrize("field", ["version", "enabled", "source", "window"])
def test_incomplete_definition_drops_alone(field):
    from wingman.preview.crops import deserialize

    bad = _raw_crop()
    del bad[field]
    assert tuple(deserialize({"Bad": bad, "Good": _raw_crop()})) == ("Good",)


@pytest.mark.parametrize("field", ["x", "y", "w", "h"])
@pytest.mark.parametrize(
    "value", [True, "0.5", None, float("nan"), float("inf"), -float("inf")]
)
def test_invalid_saved_fractions_drop_only_their_definition(field, value):
    from wingman.preview.crops import deserialize

    bad = _raw_crop()
    bad["source"][field] = value
    assert tuple(deserialize({"Bad": bad, "Good": _raw_crop()})) == ("Good",)


@pytest.mark.parametrize("field,value", [("x", 1), ("y", 5), ("w", 0), ("h", -1)])
def test_empty_normalized_remainders_are_not_saved(field, value):
    from wingman.preview.crops import deserialize

    bad = _raw_crop()
    bad["source"][field] = value
    assert deserialize({"Bad": bad}) == {}


@pytest.mark.parametrize("field", ["original_client_w", "original_client_h"])
@pytest.mark.parametrize("value", [True, 0, -1, 1280.0, "1280", None])
def test_original_client_dimensions_require_positive_integers(field, value):
    from wingman.preview.crops import deserialize

    bad = _raw_crop()
    bad["source"][field] = value
    assert tuple(deserialize({"Bad": bad, "Good": _raw_crop()})) == ("Good",)


@pytest.mark.parametrize(
    "pixels",
    [
        None,
        {},
        [0, 0, 16],
        [0, 0, 16, 16, 16],
        [True, 0, 16, 16],
        [0, False, 16, 16],
        [-1, 0, 16, 16],
        [0, -1, 16, 16],
        [0, 0, 0, 16],
        [0, 0, 16, -1],
        [0, 0, True, 16],
        [0, 0, 16, 16.0],
        ["0", 0, 16, 16],
    ],
)
def test_original_pixels_require_nonnegative_origins_and_positive_integer_extents(
    pixels,
):
    from wingman.preview.crops import deserialize

    bad = _raw_crop()
    bad["source"]["original_px"] = pixels
    assert tuple(deserialize({"Bad": bad, "Good": _raw_crop()})) == ("Good",)


@pytest.mark.parametrize(
    "field,value",
    [
        ("x", True),
        ("y", 1.0),
        ("x", "0"),
        ("w", 0),
        ("h", -1),
        ("w", False),
        ("h", 180.0),
        ("w", None),
    ],
)
def test_destination_requires_integer_origins_and_positive_integer_sizes(field, value):
    from wingman.preview.crops import deserialize

    bad = _raw_crop()
    bad["window"][field] = value
    assert tuple(deserialize({"Bad": bad, "Good": _raw_crop()})) == ("Good",)


@pytest.mark.parametrize("section", ["source", "window"])
@pytest.mark.parametrize("value", [None, [], "invalid", 1])
def test_malformed_nested_section_drops_only_its_owner(section, value):
    from wingman.preview.crops import deserialize

    bad = _raw_crop()
    bad[section] = value
    assert tuple(deserialize({"Bad": bad, "Good": _raw_crop()})) == ("Good",)


def test_finite_fractions_are_clamped_then_trimmed_to_the_unit_square():
    from wingman.preview.crops import deserialize, serialize, source_to_pixels

    raw = _raw_crop()
    raw["source"].update(x=-0.25, y=0.75, w=2, h=0.5)
    definitions = deserialize({"Alice": raw})
    source = definitions["Alice"].source
    assert (source.x, source.y, source.w, source.h) == (0.0, 0.75, 1.0, 0.25)
    assert source_to_pixels(source, (128, 128)) == Rect(0, 96, 128, 32)
    assert source.original_px == Rect(320, 90, 640, 360)
    assert deserialize(serialize(definitions)) == definitions


def test_diagnostics_never_determine_source_or_minimum_validity():
    from wingman.preview.crops import deserialize, source_to_pixels

    raw = _raw_crop()
    raw["source"].update(
        original_client_w=1, original_client_h=1, original_px=[0, 0, 1, 1]
    )
    source = deserialize({"Alice": raw})["Alice"].source
    assert source_to_pixels(source, (128, 128)) == Rect(32, 16, 64, 64)


def test_unknown_fields_and_runtime_identity_do_not_serialize():
    from wingman.preview.crops import deserialize, serialize

    raw = _raw_crop()
    raw.update(epoch=7, generation=3, session={"hwnd": 123, "pid": 456}, operation_id=9)
    raw["source"]["label"] = "ignored"
    raw["window"]["hwnd"] = 123
    assert serialize(deserialize({"Alice": raw})) == {"Alice": _raw_crop()}


def test_pixel_created_source_already_has_canonical_far_edge_fractions():
    from wingman.preview.crops import (
        CropDefinition,
        deserialize,
        serialize,
        source_from_pixels,
        source_to_pixels,
    )

    # 18/22 is one ULP wider than 1 - 4/22. A committed definition must
    # not drift the first time an unrelated settings write normalizes it.
    source = source_from_pixels(Rect(4, 4, 18, 18), (22, 22))
    definitions = {"Alice": CropDefinition(source, Rect(0, 0, 320, 320))}
    assert deserialize(serialize(definitions)) == definitions
    assert source_to_pixels(source, (44, 44)) == Rect(8, 8, 36, 36)


def test_large_finite_integer_fractions_clamp_without_float_overflow():
    from wingman.preview.crops import deserialize, source_to_pixels

    raw = _raw_crop()
    raw["source"].update(x=-(10**400), w=10**400)
    source = deserialize({"Alice": raw})["Alice"].source
    assert source_to_pixels(source, (128, 128)) == Rect(0, 16, 128, 64)


def test_default_cap_filters_disabled_and_offline_then_orders_available_names():
    from wingman.preview.crops import deserialize, eligible_names
    from wingman.telemetry.model import ClientSessionId

    names = (
        "zulu",
        "H",
        "g",
        "F",
        "e",
        "D",
        "c",
        "bravo",
        "alpha",
        "Alpha",
        "Offline",
        "Disabled",
    )
    raw = {name: {**_raw_crop(), "enabled": name != "Disabled"} for name in names}
    definitions = deserialize(raw)
    sessions = {
        name: ClientSessionId(i, i, name, 1)
        for i, name in enumerate(names)
        if name != "Offline"
    }
    assert eligible_names(definitions, sessions) == (
        "Alpha",
        "alpha",
        "bravo",
        "c",
        "D",
        "e",
        "F",
        "g",
    )
    # Enumeration order cannot change which saved crops lose the cap lottery.
    assert eligible_names(dict(reversed(tuple(definitions.items()))), sessions) == (
        "Alpha",
        "alpha",
        "bravo",
        "c",
        "D",
        "e",
        "F",
        "g",
    )
    assert eligible_names(definitions, sessions, limit=2) == ("Alpha", "alpha")
    assert eligible_names(definitions, sessions, limit=0) == ()
    assert set(definitions) == set(names)


def test_crop_records_cannot_mutate_snapshots_or_runtime_write_identity():
    from dataclasses import FrozenInstanceError

    from wingman.preview.crops import CropToken, CropWriteResult, deserialize
    from wingman.telemetry.model import ClientSessionId

    definition = deserialize({"Alice": _raw_crop()})["Alice"]
    token = CropToken(9, "Alice", 2, 3, ClientSessionId(100, 200, "Alice", 5))
    result = CropWriteResult(token, True, True, None, 4)
    for record, field, value in (
        (definition.source, "x", 0.0),
        (definition, "enabled", True),
        (token, "generation", 4),
        (result, "persisted", False),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(record, field, value)
