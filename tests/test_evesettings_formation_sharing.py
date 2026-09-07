import copy
import json
import math
import re
from pathlib import Path

import pytest

from wingman.evesettings import formation_sharing as sharing
from wingman.evesettings.formations import (
    MAX_PROBES,
    Formation,
    Probe,
    from_payload,
    to_payload,
)


def item(name="Pinpoint", ident=7, scan_range=149597870700):
    return {
        "id": ident,
        "name": name,
        "probes": [{"x": -1250.5, "y": 0, "z": 2500.25, "range": scan_range}],
    }


def test_share_round_trip_omits_local_identity():
    text = sharing.export_text([item()])
    wire = json.loads(text)
    assert set(wire) == {"format", "version", "type", "formations"}
    assert wire["format"] == "wingman-preset"
    assert wire["version"] == 1
    assert wire["type"] == "probe-formations"
    assert set(wire["formations"][0]) == {"name", "probes"}
    parsed = sharing.parse_text(text)
    assert parsed[0].id is None
    assert to_payload(parsed)[0] == item(ident=None)


def test_target_conflicts_use_python_casefold():
    prepared, conflicts = sharing.prepare_import(
        [item(name="Straße", ident=None)], ["STRASSE"]
    )
    assert prepared[0].name == "Straße"
    assert conflicts == [0]


def artifact(formations=None):
    return {
        "format": "wingman-preset",
        "version": 1,
        "type": "probe-formations",
        "formations": formations
        if formations is not None
        else [{"name": "Pinpoint", "probes": item()["probes"]}],
    }


def consume(operation, items):
    if operation == "export":
        # Do not let the strict parser mask an exporter that forgot validation.
        return from_payload(json.loads(sharing.export_text(items))["formations"])
    if operation == "prepare":
        return sharing.prepare_import(items, [])[0]
    portable = [{key: value for key, value in f.items() if key != "id"} for f in items]
    return sharing.parse_text(json.dumps(artifact(portable), ensure_ascii=False))


OPERATIONS = ("parse", "export", "prepare")


def test_export_projects_only_names_and_geometry_even_with_unserializable_metadata():
    selected = item(name="Pilot Alice's formation")
    selected.update(
        path="C:/private/account.dat",
        account={"alias": "Secret"},
        character_name="Private pilot",
        content_revision="private revision",
        selected=True,
        scratch_entries=[{"id": -4}],
        credentials=object(),
    )
    selected["probes"][0]["source"] = object()
    text = sharing.export_text([selected])
    assert json.loads(text) == artifact(
        [{"name": "Pilot Alice's formation", "probes": item()["probes"]}]
    )
    assert selected["path"] == "C:/private/account.dat"
    assert "source" in selected["probes"][0]


def test_export_only_valid_selected_items_does_not_validate_other_drafts():
    drafts = [item(), item(name="", scan_range=1), item(ident=-4)]
    before = copy.deepcopy(drafts)
    assert to_payload(sharing.parse_text(sharing.export_text([drafts[0]]))) == [
        item(ident=None)
    ]
    assert drafts == before


def test_export_refuses_scratch_instead_of_exporting_its_positions():
    with pytest.raises(ValueError, match=r"(?i)formation 1.*scratch"):
        sharing.export_text([item(ident=-4)])


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("count", [1, 32])
def test_formation_count_inclusive_boundaries(operation, count):
    items = [item(name=f"Formation {i}", ident=None) for i in range(count)]
    assert to_payload(consume(operation, items)) == items


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("count", [0, 33])
def test_formation_count_outside_boundaries_is_rejected(operation, count):
    items = [item(name=f"Formation {i}", ident=None) for i in range(count)]
    with pytest.raises(ValueError, match=r"(?i)formation.*32"):
        consume(operation, items)


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("count", [1, 8])
def test_probe_count_inclusive_boundaries(operation, count):
    source = item(ident=None)
    source["probes"] *= count
    assert to_payload(consume(operation, [source])) == [source]


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("count", [0, 9])
def test_probe_count_outside_boundaries_is_rejected(operation, count):
    source = item(ident=None)
    source["probes"] *= count
    with pytest.raises(ValueError, match=r"(?i)formation 1.*probe.*8"):
        consume(operation, [source])


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("name", ["a" * 128, "𐐀" * 128, "é" * 128, "a\u200db"])
def test_names_use_unicode_codepoints_and_allow_non_control_unicode(operation, name):
    source = item(name="  " + name + "  ", ident=None)
    assert consume(operation, [source])[0].name == name
    assert source["name"] == "  " + name + "  "


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize(
    "name",
    [
        "",
        "   ",
        "a" * 129,
        "𐐀" * 129,
        "é" * 129,
        "bad\x00name",
        "bad\x1fname",
        "bad\x7fname",
        "bad\x85name",
        "\tname",
        "name\n",
        "bad\ud800name",
        "bad\udfffname",
        None,
        12,
        True,
    ],
)
def test_invalid_names_are_rejected(operation, name):
    with pytest.raises(ValueError, match=r"(?i)(name|UTF-8)"):
        consume(operation, [item(name=name, ident=None)])


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("names", [("Straße", "STRASSE"), (" A ", "a"), ("Σ", "ς")])
def test_incoming_duplicates_are_validation_errors_after_trimming(operation, names):
    incoming = [item(name=name, ident=None) for name in names]
    with pytest.raises(ValueError, match=r"(?i)(twice|duplicate)"):
        consume(operation, incoming)


def test_preparation_revalidates_review_names_and_reports_all_conflict_indexes():
    incoming = [
        item(name=" Fresh ", ident=None),
        item(name="Renamed", ident=None),
        item(name="Straße", ident=None),
    ]
    existing = ["STRASSE", "RENAMED", "RENAMED"]
    before = copy.deepcopy((incoming, existing))
    candidates, conflicts = sharing.prepare_import(incoming, existing)
    assert [f.name for f in candidates] == ["Fresh", "Renamed", "Straße"]
    assert all(f.id is None for f in candidates)
    assert conflicts == [1, 2]
    assert (incoming, existing) == before


def test_existing_draft_names_are_compared_as_stored_not_validated_or_trimmed():
    existing = ["", "bad\x00name", "x" * 129, " Padded ", "\ud800"] * 10
    candidates, conflicts = sharing.prepare_import(
        [item(name="Padded", ident=None)], existing
    )
    assert candidates[0].name == "Padded"
    assert conflicts == []


def test_duplicate_review_names_are_errors_even_when_the_target_also_conflicts():
    with pytest.raises(ValueError, match=r"(?i)(twice|duplicate)"):
        sharing.prepare_import(
            [item(name="Straße", ident=None), item(name="STRASSE", ident=None)],
            ["STRASSE"],
        )


@pytest.mark.parametrize("ident", [7, -4, True, "7", 0.0])
def test_prepare_refuses_source_identity(ident):
    with pytest.raises(ValueError, match=r"(?i)formation 1.*id"):
        sharing.prepare_import([item(ident=ident)], [])


def test_prepare_requires_canonical_keys_including_null_id():
    source = item(ident=None)
    del source["id"]
    with pytest.raises(ValueError, match=r"(?i)formation 1.*id"):
        sharing.prepare_import([source], [])
    source["id"] = None
    source["path"] = "private"
    with pytest.raises(ValueError, match=r"(?i)formation 1.*(field|key)"):
        sharing.prepare_import([source], [])


@pytest.mark.parametrize("names", [None, "name", [None], [12], [True]])
def test_prepare_rejects_non_list_or_non_string_existing_names(names):
    with pytest.raises(ValueError, match=r"(?i)existing.*name"):
        sharing.prepare_import([item(ident=None)], names)


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("field", ["x", "y", "z", "range"])
@pytest.mark.parametrize(
    "value",
    [
        True,
        False,
        "149597870700",
        None,
        [],
        {},
        float("nan"),
        float("inf"),
        -float("inf"),
        10**400,
    ],
)
def test_numeric_values_are_strict_finite_and_bounded(operation, field, value):
    source = item(ident=None)
    source["probes"][0][field] = value
    with pytest.raises(
        ValueError, match=rf"(?i)(formation 1.*probe 1.*{field}|JSON number)"
    ):
        consume(operation, [source])


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize(
    "value",
    [
        149597.8707,
        math.nextafter(149597.8707, math.inf),
        9804046054195200,
        math.nextafter(9804046054195200, -math.inf),
        187.25 * 149597870700,
    ],
)
def test_exact_range_bounds_and_adjacent_supported_values_are_preserved(
    operation, value
):
    assert (
        consume(operation, [item(ident=None, scan_range=value)])[0].probes[0].range
        == value
    )


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize(
    "value",
    [
        math.nextafter(149597.8707, -math.inf),
        math.nextafter(9804046054195200, math.inf),
        1,
        1e-320,
        0,
        -1,
    ],
)
def test_range_outside_sharing_bounds_is_rejected_without_clamping(operation, value):
    with pytest.raises(
        ValueError, match=r"(?i)formation 1.*probe 1.*range.*149597.*9804046054195200"
    ):
        consume(operation, [item(ident=None, scan_range=value)])


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("field", ["x", "y", "z"])
@pytest.mark.parametrize("value", [-(10**16), 10**16, -1e-320, 0, 1e-320])
def test_coordinate_bounds_and_tiny_values_are_preserved(operation, field, value):
    source = item(ident=None)
    source["probes"][0][field] = value
    assert getattr(consume(operation, [source])[0].probes[0], field) == value


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("field", ["x", "y", "z"])
@pytest.mark.parametrize(
    "value",
    [
        -(10**16) - 1,
        10**16 + 1,
        math.nextafter(1e16, math.inf),
        math.nextafter(-1e16, -math.inf),
    ],
)
def test_coordinates_outside_bounds_are_rejected_before_float_rounding(
    operation, field, value
):
    source = item(ident=None)
    source["probes"][0][field] = value
    with pytest.raises(
        ValueError, match=rf"(?i)formation 1.*probe 1.*{field}.*10000000000000000"
    ):
        consume(operation, [source])


@pytest.mark.parametrize("level", ["root", "formation", "probe"])
@pytest.mark.parametrize("change", ["unknown", "missing"])
def test_parse_requires_exact_keys_at_every_level(level, change):
    wire = artifact()
    node = {
        "root": wire,
        "formation": wire["formations"][0],
        "probe": wire["formations"][0]["probes"][0],
    }[level]
    if change == "unknown":
        node["id"] = 7
    else:
        del node[next(iter(node))]
    with pytest.raises(ValueError, match=r"(?i)(field|key)"):
        sharing.parse_text(json.dumps(wire))


@pytest.mark.parametrize(
    "field,value",
    [
        ("format", "other"),
        ("format", None),
        ("version", 2),
        ("version", True),
        ("version", 1.0),
        ("version", "1"),
        ("version", None),
        ("type", "overview"),
        ("type", []),
        ("format", {}),
    ],
)
def test_parse_refuses_unsupported_markers_and_version_coercions(field, value):
    wire = artifact()
    wire[field] = value
    with pytest.raises(ValueError, match=rf"(?i){field}"):
        sharing.parse_text(json.dumps(wire))


@pytest.mark.parametrize("level", ["root", "formation", "probe"])
def test_parse_rejects_duplicate_json_keys_instead_of_keeping_last(level):
    text = json.dumps(artifact())
    original, repeated, field = {
        "root": ('"version": 1', '"version": 2, "version": 1', "version"),
        "formation": (
            '"name": "Pinpoint"',
            '"name": "Other", "name": "Pinpoint"',
            "name",
        ),
        "probe": ('"x": -1250.5', '"x": 1, "x": -1250.5', "x"),
    }[level]
    with pytest.raises(ValueError, match=rf"(?i)repeated JSON field.*{field}"):
        sharing.parse_text(text.replace(original, repeated))


@pytest.mark.parametrize(
    "text",
    [
        "",
        " \t\r\n ",
        "{",
        '{"format":',
        "null trailing",
        "```json\n{}\n```",
        "https://example.com/preset",
        "{} {}",
    ],
)
def test_parse_refuses_malformed_or_wrapped_input_with_json_context(text):
    with pytest.raises(ValueError, match=r"(?i)JSON"):
        sharing.parse_text(text)


@pytest.mark.parametrize("text", [None, 1, True, b"{}", [], {}])
def test_parse_requires_text_not_implicit_decoding(text):
    with pytest.raises(ValueError, match=r"(?i)text"):
        sharing.parse_text(text)


@pytest.mark.parametrize("level", ["root", "formation", "probe"])
@pytest.mark.parametrize("value", [None, True, 1, "object", []])
def test_parse_requires_objects_not_coercible_shapes(level, value):
    wire = artifact()
    if level == "root":
        wire = value
    elif level == "formation":
        wire["formations"] = [value]
    else:
        wire["formations"][0]["probes"] = [value]
    with pytest.raises(ValueError, match=r"(?i)object"):
        sharing.parse_text(json.dumps(wire))


@pytest.mark.parametrize("level", ["formations", "probes"])
@pytest.mark.parametrize("value", [None, True, 1, "list", {}])
def test_parse_requires_lists(level, value):
    wire = artifact()
    if level == "formations":
        wire["formations"] = value
    else:
        wire["formations"][0]["probes"] = value
    with pytest.raises(ValueError, match=r"(?i)list"):
        sharing.parse_text(json.dumps(wire))


@pytest.mark.parametrize("operation", ["export", "prepare"])
@pytest.mark.parametrize(
    "source",
    [
        None,
        {},
        (),
        "list",
        [None],
        [7],
        [[]],
        [{}],
        [{"name": "A", "id": None, "probes": None}],
        [{"name": "A", "id": None, "probes": ()}],
        [{"name": "A", "id": None, "probes": [None]}],
        [{"name": "A", "id": None, "probes": [{}]}],
    ],
)
def test_internal_payload_shape_errors_are_contextual_value_errors(operation, source):
    with pytest.raises(ValueError, match=r"(?i)(formation|probe)"):
        consume(operation, source)


@pytest.mark.parametrize("escaped", [False, True])
def test_parse_rejects_unpaired_surrogates_in_raw_and_escaped_names(escaped):
    wire = artifact([{"name": "bad\ud800", "probes": item()["probes"]}])
    with pytest.raises(ValueError, match=r"(?i)(UTF-8|surrogate)"):
        sharing.parse_text(json.dumps(wire, ensure_ascii=escaped))


@pytest.mark.parametrize(
    "token", ["NaN", "Infinity", "-Infinity", "1e10000", "9" * 400, "9" * 5000]
)
def test_parse_contains_nonfinite_and_huge_json_number_errors(token):
    text = json.dumps(artifact()).replace("-1250.5", token)
    with pytest.raises(ValueError, match=r"(?i)(JSON|formation 1.*probe 1.*x)"):
        sharing.parse_text(text)


@pytest.mark.parametrize(
    "text", ["[" * 2000 + "0" + "]" * 2000, '{"nested":' * 2000 + "0" + "}" * 2000]
)
def test_deep_json_errors_are_contained(text):
    with pytest.raises(ValueError, match=r"(?i)JSON.*(deep|recurs|nest)"):
        sharing.parse_text(text)


def test_utf8_byte_limit_counts_multibyte_characters_and_accepts_exact_boundary():
    text = json.dumps(
        artifact([{"name": "𐐀é", "probes": item()["probes"]}]), ensure_ascii=False
    )
    padded = text + " " * (65536 - len(text.encode("utf-8")))
    assert len(padded) < 65536
    assert sharing.parse_text(padded)[0].name == "𐐀é"
    with pytest.raises(ValueError, match=r"(?i)(bytes|KiB)"):
        sharing.parse_text(padded + " ")


# Pytest puts parameter IDs in PYTEST_CURRENT_TEST; Windows caps its length.
@pytest.mark.parametrize(
    "text",
    ["{" + " " * 65536, "𐐀" * 20000, "\ud800" * 65537],
    ids=["oversized-ascii", "oversized-utf8", "oversized-surrogates"],
)
def test_input_size_is_checked_before_decoding_or_parsing(text):
    with pytest.raises(ValueError, match=r"(?i)(bytes|KiB)"):
        sharing.parse_text(text)


def test_export_enforces_utf8_output_size_without_truncation(monkeypatch):
    # Valid v1 geometry/names fit under 64 KiB even at their individual maxima.
    # Lower only the byte cap to exercise its independent output safeguard.
    sources = [item(name="𐐀é")]
    before = copy.deepcopy(sources)
    text = sharing.export_text(sources)
    byte_count = len(text.encode("utf-8"))
    assert len(text) < byte_count
    monkeypatch.setattr(sharing, "MAX_BYTES", byte_count)
    assert sharing.export_text(sources) == text
    monkeypatch.setattr(sharing, "MAX_BYTES", byte_count - 1)
    with pytest.raises(ValueError, match=r"(?i)copy fewer formations"):
        sharing.export_text(sources)
    assert sources == before


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("invalid", [False, True])
def test_success_and_failure_never_mutate_input_lists_or_nested_dicts(
    operation, invalid
):
    sources = [item(name="  First  ", ident=None), item(name="Second", ident=None)]
    if invalid:
        sources[1]["probes"][0]["range"] = 1
    before = copy.deepcopy(sources)
    if invalid:
        with pytest.raises(ValueError, match=r"(?i)formation 2.*probe 1.*range"):
            consume(operation, sources)
    else:
        candidates = consume(operation, sources)
        assert candidates[0] == Formation(
            None, "First", (Probe(-1250.5, 0, 2500.25, 149597870700),)
        )
        sources[0]["probes"][0]["x"] = 15
        assert candidates[0].probes[0].x == -1250.5
        sources[0]["probes"][0]["x"] = -1250.5
    assert sources == before


def test_limits_payload_is_fresh_and_matches_the_shared_meter_contract():
    limits = sharing.limits_payload()
    assert limits == {
        "max_bytes": 65536,
        "max_formations": 32,
        "max_name_codepoints": 128,
        "max_probes": MAX_PROBES,
        "au_meters": 149597870700,
        "min_range_meters": 149597.8707,
        "max_range_meters": 9804046054195200,
        "max_coordinate_meters": 10**16,
    }
    page = (Path(__file__).parents[1] / "wingman/web/formations.js").read_text(
        encoding="utf-8"
    )
    match = re.search(r"var AU = (\d+);", page)
    assert match is not None
    assert limits["au_meters"] == int(match[1])
    limits["max_bytes"] = 0
    assert sharing.limits_payload()["max_bytes"] == 65536
