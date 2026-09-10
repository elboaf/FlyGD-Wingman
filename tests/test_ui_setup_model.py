"""Behavioral contracts for the pure, identity-free setup model.

The hand-authored wire fixture, not a document projection or production builder,
is the expected supported shape. Mutations below name independently invalid
boundaries; no test needs EVE, a profile, the codec or the clipboard.
"""

import copy
import math

import pytest

from tests.setup_fixtures import wire, wire_with_tabs
from wingman.evesettings import setup_model as model


def changed(path, value):
    source = wire()
    node = source
    for part in path[:-1]:
        node = node[part]
    node[path[-1]] = value
    return source


def assert_error(code, function, *args, **kwargs):
    with pytest.raises(model.SetupError) as caught:
        function(*args, **kwargs)
    assert caught.value.code == code
    assert str(caught.value)


def test_fixture_preserves_independent_order_geometry_and_text():
    source = wire()
    parsed = model.validate_wingman(source)
    assert parsed.source_kind == "wingman"
    assert parsed.overview == source["overview"]
    assert parsed.layout == source["layout"]
    assert parsed.ambiguous_labels is False
    assert parsed.warnings == ()
    assert parsed.overview["windowGroups"] == [[0, 1, 2], [3, 4, 5], [6, 7]]
    assert [label["type"] for label in parsed.overview["shipLabels"]] == [
        None,
        "pilot name",
        None,
        "corporation",
        None,
        "alliance",
        "ship type",
        None,
        "ship name",
    ]
    assert parsed.overview["shipLabels"][0]["pre"] == "<b>Synthetic flight</b>"
    assert parsed.layout["windows"][1]["geometry"] == [-20, 200, 320, 420, 1600, 900]
    assert parsed.layout["windows"][-1] == {
        "key": "primary_map_panel",
        "geometry": None,
        "state": {},
    }


def test_results_own_all_nested_values_and_validation_never_mutates():
    source = wire()
    before = copy.deepcopy(source)
    first = model.validate_wingman(source)
    second = model.validate_wingman(source)
    first.overview["presets"][0]["groups"].append(99)
    first.overview["tabs"][0]["color"][0] = 0
    first.overview["windowGroups"][0].reverse()
    first.overview["shipLabels"][0]["pre"] = "changed"
    first.overview["settings"]["stateColors"][0]["color"][0] = 0
    first.layout["windows"][0]["geometry"][0] = 0
    first.layout["windows"][0]["state"]["open"] = False
    first.layout["targetOrigin"][0] = 0
    assert source == before
    assert second.overview == before["overview"]
    assert second.layout == before["layout"]
    source["overview"]["presets"][0]["groups"].clear()
    assert second.overview["presets"][0]["groups"] == [25, 27]
    source["layout"]["hudOffset"] = True
    invalid_before = copy.deepcopy(source)
    assert_error("invalid_number", model.validate_wingman, source)
    assert source == invalid_before


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("format", "other", "unsupported_format"),
        ("format", {}, "unsupported_format"),
        ("version", True, "unsupported_version"),
        ("version", 1.0, "unsupported_version"),
        ("version", "1", "unsupported_version"),
        ("version", 2, "unsupported_version"),
        ("type", "probe-formations", "unsupported_type"),
        ("type", None, "unsupported_type"),
    ],
    ids=[
        "format",
        "format-object",
        "bool-version",
        "float-version",
        "text-version",
        "v2",
        "probe",
        "null-type",
    ],
)
def test_exact_envelope_markers(field, value, code):
    assert_error(code, model.validate_wingman, changed((field,), value))


OBJECT_PATHS = [
    (),
    ("overview",),
    ("overview", "presets", 0),
    ("overview", "tabs", 0),
    ("overview", "shipLabels", 0),
    ("overview", "settings"),
    ("overview", "settings", "stateColors", 0),
    ("overview", "settings", "stateBlinks", 0),
    ("layout",),
    ("layout", "windows", 0),
    ("layout", "windows", 0, "state"),
]
OBJECT_IDS = [
    "root",
    "overview",
    "preset",
    "tab",
    "label",
    "settings",
    "color",
    "blink",
    "layout",
    "window",
    "state",
]


@pytest.mark.parametrize("path", OBJECT_PATHS, ids=OBJECT_IDS)
def test_unknown_fields_refuse_instead_of_carrying_private_metadata(path):
    source = wire()
    node = source
    for part in path:
        node = node[part]
    node["sourcePath"] = "C:/synthetic/private.dat"
    assert_error("invalid_fields", model.validate_wingman, source)


# Exhaust _fields at the root; None at every nested site pins its wiring.
@pytest.mark.parametrize(
    "path,value",
    [
        pytest.param(path, value, id=f"{value_id}-{path_id}")
        for value, value_id in [
            (None, "null"),
            ([], "list"),
            ("object", "text"),
            (1, "int"),
            (True, "bool"),
        ]
        for path, path_id in zip(OBJECT_PATHS, OBJECT_IDS, strict=True)
        if not path or value is None
    ],
)
def test_records_require_objects(path, value):
    source = changed(path, value) if path else value
    assert_error("invalid_type", model.validate_wingman, source)


# All sites reach _list — exhaust its types once and reject a dict at each site.
@pytest.mark.parametrize(
    "path,value",
    [
        pytest.param(path, value, id=f"{value_id}-{path_id}")
        for value, value_id in [
            ({}, "object"),
            ("list", "text"),
            (1, "int"),
            (True, "bool"),
            ((), "tuple"),
        ]
        for path, path_id in [
            (("overview", "presets"), "presets"),
            (("overview", "tabs"), "tabs"),
            (("overview", "windowGroups"), "groups"),
            (("overview", "shipLabels"), "labels"),
            (("overview", "presets", 0, "groups"), "members"),
            (("overview", "tabs", 0, "tabColumns"), "columns"),
            (("overview", "settings", "flagOrder"), "states"),
            (("layout", "windows"), "windows"),
        ]
        if path_id == "presets" or value_id == "object"
    ],
)
def test_collections_require_lists(path, value):
    assert_error("invalid_type", model.validate_wingman, changed(path, value))


@pytest.mark.parametrize(
    "path",
    [
        ("format",),
        ("overview",),
        ("layout",),
        ("overview", "presets"),
        ("overview", "tabs"),
        ("overview", "windowGroups"),
        ("overview", "shipLabels"),
        ("overview", "settings"),
        ("overview", "presets", 0, "groups"),
        ("overview", "tabs", 0, "bracket"),
        ("overview", "shipLabels", 0, "state"),
        ("overview", "settings", "stateColors", 0, "color"),
        ("layout", "windows"),
        ("layout", "windows", 0, "state"),
        ("layout", "windows", 0, "geometry"),
        ("layout", "targetOrigin"),
        ("layout", "targetOriginLocked"),
        ("layout", "hudOffset"),
    ],
    ids=[
        "format",
        "overview",
        "layout",
        "presets",
        "tabs",
        "groups",
        "labels",
        "settings",
        "members",
        "bracket",
        "label-state",
        "color",
        "windows",
        "state",
        "geometry",
        "origin",
        "lock",
        "hud",
    ],
)
def test_required_fields_cannot_be_silently_defaulted(path):
    source = wire()
    node = source
    for part in path[:-1]:
        node = node[part]
    del node[path[-1]]
    assert_error("invalid_fields", model.validate_wingman, source)


def test_full_missing_settings_become_clear_not_false_or_empty():
    source = wire()["overview"]
    supported_names = set(source["settings"])
    source["settings"] = {"useSmallText": False, "flagStates": [], "flagOrder": None}
    full = model.validate_overview(source, partial=False)
    assert full["settings"] == {
        name: False if name == "useSmallText" else [] if name == "flagStates" else None
        for name in supported_names
    }
    assert source["settings"] == {
        "useSmallText": False,
        "flagStates": [],
        "flagOrder": None,
    }
    assert model.validate_overview(full, partial=False) == full


def test_partial_absence_stays_absent_and_supplied_values_are_owned():
    source = {"settings": {"useSmallText": False, "flagStates": []}}
    parsed = model.validate_overview(source, partial=True)
    assert parsed == {"settings": {"useSmallText": False, "flagStates": []}}
    parsed["settings"]["flagStates"].append(9)
    assert source == {"settings": {"useSmallText": False, "flagStates": []}}
    assert model.validate_overview({}, partial=True) == {}
    assert model.validate_overview({"presets": []}, partial=True) == {"presets": []}


@pytest.mark.parametrize(
    "field",
    list(wire()["overview"]["settings"]),
    ids=list(wire()["overview"]["settings"]),
)
def test_every_setting_clear_is_full_only(field):
    source = {"settings": {field: None}}
    assert_error("invalid_type", model.validate_overview, source, partial=True)
    full = changed(("overview", "settings", field), None)
    assert model.validate_wingman(full).overview["settings"][field] is None


@pytest.mark.parametrize(
    "path",
    [
        ("overview", "presets", 0, "name"),
        ("overview", "tabs", 0, "name"),
        ("overview", "tabs", 0, "overview"),
        ("overview", "tabs", 0, "bracket"),
    ],
    ids=["preset", "tab", "overview-ref", "bracket-ref"],
)
@pytest.mark.parametrize(
    "value",
    ["", " \t\n", "x" * 513, "bad\x00text", "bad\ud800", "bad\udfff", None, 4],
    ids=["empty", "blank", "long", "nul", "high", "low", "null", "int"],
)
def test_names_and_references_are_valid_text(path, value):
    if path[-1] == "bracket" and value is None:
        assert (
            model.validate_wingman(changed(path, value)).overview["tabs"][0]["bracket"]
            is None
        )
    else:
        assert_error("invalid_text", model.validate_wingman, changed(path, value))


def test_names_are_exact_text_not_trimmed_casefolded_or_unicode_normalized():
    source = wire()
    names = [" Fleet ", "fleet", "FLEET", "é", "e\u0301", "𐐀" * 512]
    source["overview"]["presets"] += [
        {"name": name, "groups": [], "filteredStates": [], "alwaysShownStates": []}
        for name in names
    ]
    source["overview"]["tabs"][0]["overview"] = " Fleet "
    source["overview"]["tabs"][0]["name"] = "𐐀" * 512
    parsed = model.validate_wingman(source)
    assert [p["name"] for p in parsed.overview["presets"]][-6:] == names
    assert parsed.overview["tabs"][0]["overview"] == " Fleet "
    assert parsed.overview["tabs"][0]["name"] == "𐐀" * 512
    source["overview"]["tabs"][0]["overview"] = "Fleet"
    assert_error("dangling_reference", model.validate_wingman, source)


@pytest.mark.parametrize("field", ["overview", "bracket"])
@pytest.mark.parametrize(
    "reference",
    ["synthetic Fleet", "DefaultPreset_missing", "all", "none"],
    ids=["case", "default", "all", "none"],
)
def test_tab_references_need_exact_included_definitions_not_sentinels(field, reference):
    assert_error(
        "dangling_reference",
        model.validate_wingman,
        changed(("overview", "tabs", 0, field), reference),
    )


def test_partial_tabs_require_their_own_definitions_and_grouping():
    source = wire()["overview"]
    partial = {name: source[name] for name in ("presets", "tabs", "windowGroups")}
    assert model.validate_overview(partial, partial=True) == partial
    del partial["presets"]
    assert_error("dangling_reference", model.validate_overview, partial, partial=True)
    assert_error(
        "invalid_groups",
        model.validate_overview,
        {"tabs": source["tabs"]},
        partial=True,
    )
    assert_error(
        "invalid_groups", model.validate_overview, {"windowGroups": [[0]]}, partial=True
    )


@pytest.mark.parametrize(
    "collection,code", [("presets", "duplicate_name"), ("tabs", "duplicate_id")]
)
def test_duplicate_logical_records_refuse(collection, code):
    source = wire()
    source["overview"][collection][1] = copy.deepcopy(source["overview"][collection][0])
    assert_error(code, model.validate_wingman, source)


@pytest.mark.parametrize("field", ["groups", "filteredStates", "alwaysShownStates"])
@pytest.mark.parametrize(
    "value",
    [-1, 2147483648, True, False, 1.0, "1", None],
    ids=["negative", "large", "true", "false", "float", "text", "null"],
)
def test_membership_ids_are_signed_32_bit_nonboolean_integers(field, value):
    assert_error(
        "invalid_number",
        model.validate_wingman,
        changed(("overview", "presets", 0, field), [value]),
    )


@pytest.mark.parametrize("field", ["groups", "filteredStates", "alwaysShownStates"])
def test_membership_bounds_and_duplicates(field):
    source = changed(("overview", "presets", 0, field), [2147483647, 0])
    assert model.validate_wingman(source).overview["presets"][0][field] == [
        2147483647,
        0,
    ]
    source["overview"]["presets"][0][field] = [1, 1]
    assert model.validate_wingman(source).overview["presets"][0][field] == [1, 1]
    source["overview"]["presets"][0][field] = list(range(8192))
    assert len(model.validate_wingman(source).overview["presets"][0][field]) == 8192
    source["overview"]["presets"][0][field].append(8192)
    assert_error("collection_limit", model.validate_wingman, source)


def test_repeated_preset_groups_preserve_order_and_count_toward_membership_limit():
    groups = [73, 11, 73, 0, 11, 2147483647, 73]
    source = changed(("overview", "presets", 0, "groups"), groups)
    before = copy.deepcopy(source)
    for partial in (True, False):
        overview = model.validate_overview(source["overview"], partial=partial)
        assert overview["presets"][0]["groups"] == [73, 11, 73, 0, 11, 2147483647, 73]
        overview["presets"][0]["groups"].clear()
        assert source == before
    source["overview"]["presets"][0]["groups"] = [73] * 8192
    assert (
        model.validate_wingman(source).overview["presets"][0]["groups"] == [73] * 8192
    )
    source["overview"]["presets"][0]["groups"].append(73)
    assert_error("collection_limit", model.validate_wingman, source)


def test_filter_count_boundary():
    source = wire()
    source["overview"]["presets"] += [
        {
            "name": f"Filter {i}",
            "groups": [],
            "filteredStates": [],
            "alwaysShownStates": [],
        }
        for i in range(253)
    ]
    assert len(model.validate_wingman(source).overview["presets"]) == 256
    source["overview"]["presets"].append(
        {"name": "Excess", "groups": [], "filteredStates": [], "alwaysShownStates": []}
    )
    assert_error("collection_limit", model.validate_wingman, source)


@pytest.mark.parametrize("count,group_count", [(9, 1), (20, 1), (20, 8)])
def test_full_twenty_tab_budget_preserves_complete_groups_and_geometry(
    count, group_count
):
    source = wire_with_tabs(count, group_count=group_count)
    # Logical IDs are not physical slots, even at the full collection budget.
    source["overview"]["tabs"][-1]["id"] = 2147483647
    group = source["overview"]["windowGroups"][(count - 1) % group_count]
    group[-1] = 2147483647
    parsed = model.validate_wingman(source)
    assert parsed.overview == source["overview"]
    assert parsed.layout == source["layout"]
    assert len(parsed.overview["tabs"]) == count
    assert len(parsed.layout["windows"]) == group_count + 9
    assert model.summarize(parsed)["counts"]["tabs"] == count


@pytest.mark.parametrize("count,group_count", [(0, 1), (21, 1), (20, 9)])
def test_tab_and_group_budgets_refuse_without_truncation(count, group_count):
    source = wire_with_tabs(count, group_count=group_count)
    before = copy.deepcopy(source)
    assert_error("collection_limit", model.validate_wingman, source)
    assert source == before


@pytest.mark.parametrize(
    "fault,code",
    [
        ("missing", "invalid_groups"),
        ("duplicate", "duplicate_id"),
        ("order", "invalid_order"),
        ("geometry", "invalid_type"),
    ],
)
def test_twenty_tabs_do_not_relax_assignment_order_or_geometry(fault, code):
    source = wire_with_tabs(20, group_count=8)
    groups = source["overview"]["windowGroups"]
    if fault == "missing":
        groups[-1].pop()
    elif fault == "duplicate":
        groups[-1].append(groups[0][0])
    elif fault == "order":
        groups[0].reverse()
    else:
        source["layout"]["windows"][7]["geometry"] = None
    assert_error(code, model.validate_wingman, source)


def test_one_tab_group_is_supported_with_closed_dependencies():
    source = wire()
    source["overview"]["tabs"] = source["overview"]["tabs"][:1]
    source["overview"]["windowGroups"] = [[0]]
    source["layout"]["windows"] = [
        w
        for w in source["layout"]["windows"]
        if w["key"] not in ("overview_1", "overview_2")
    ]
    assert model.validate_wingman(source).overview["windowGroups"] == [[0]]


@pytest.mark.parametrize(
    "groups",
    [
        [],
        [[]],
        [[0, 1], [1, 2, 3, 4, 5, 6, 7]],
        [[0, 1, 2, 3, 4, 5, 6]],
        [[0, 1, 2, 3, 4, 5, 6, 99]],
        [[True, 1, 2, 3, 4, 5, 6, 7]],
    ],
    ids=["none", "empty", "twice", "missing", "dangling", "bool"],
)
def test_every_tab_is_assigned_exactly_once_to_nonempty_groups(groups):
    with pytest.raises(model.SetupError):
        model.validate_wingman(changed(("overview", "windowGroups"), groups))


def test_tab_ids_are_not_list_positions_and_names_need_not_be_unique():
    source = wire()
    source["overview"]["tabs"][0]["id"] = 2147483647
    source["overview"]["windowGroups"][0][0] = 2147483647
    source["overview"]["tabs"][1]["name"] = source["overview"]["tabs"][0]["name"]
    assert model.validate_wingman(source).overview["windowGroups"][0] == [
        2147483647,
        1,
        2,
    ]
    source["overview"]["tabs"][0]["id"] = True
    assert_error("invalid_number", model.validate_wingman, source)


@pytest.mark.parametrize("field", ["pre", "post"])
def test_label_text_limit_preserves_markup_and_unicode(field):
    source = changed(("overview", "shipLabels", 0, field), "𐐀" * 4096)
    assert model.validate_wingman(source).overview["shipLabels"][0][field] == "𐐀" * 4096
    source["overview"]["shipLabels"][0][field] += "a"
    assert_error("invalid_text", model.validate_wingman, source)


@pytest.mark.parametrize(
    "field,value",
    [
        ("type", "LINEBREAK"),
        ("type", "unknown"),
        ("type", False),
        ("pre", None),
        ("post", None),
        ("pre", "\x00"),
        ("post", "\ud800"),
        ("state", None),
        ("state", True),
        ("state", 2),
        ("state", 0.0),
        ("fontsize", 10),
        ("fontsize", 13),
        ("fontsize", False),
        ("color", [1.0, 1.0, 1.0, 1.0]),
        ("bold", 2),
        ("italic", 0),
        ("underline", None),
    ],
    ids=[
        "linebreak",
        "type",
        "bool-type",
        "null-pre",
        "null-post",
        "nul",
        "surrogate",
        "null-state",
        "bool-state",
        "state2",
        "float-state",
        "font10",
        "font13",
        "font-bool",
        "rgba",
        "bold2",
        "italic-int",
        "underline-null",
    ],
)
def test_unmodeled_label_variants_are_not_coerced_or_dropped(field, value):
    with pytest.raises(model.SetupError):
        model.validate_wingman(changed(("overview", "shipLabels", 0, field), value))


@pytest.mark.parametrize("field", ["bold", "italic", "underline"])
@pytest.mark.parametrize("value", [True, False])
def test_optional_label_booleans_are_independent_and_remain_optional(field, value):
    source = changed(("overview", "shipLabels", 0, field), value)
    label = model.validate_wingman(source).overview["shipLabels"][0]
    assert label == {
        "type": None,
        "pre": "<b>Synthetic flight</b>",
        "post": "",
        "state": 1,
        field: value,
    }


@pytest.mark.parametrize("field", ["fontsize", "color"])
def test_optional_nullable_formatting_presence_is_preserved(field):
    source = changed(("overview", "shipLabels", 0, field), None)
    assert model.validate_wingman(source).overview["shipLabels"][0] == {
        "type": None,
        "pre": "<b>Synthetic flight</b>",
        "post": "",
        "state": 1,
        field: None,
    }


def test_labels_preserve_duplicate_types_and_count_boundaries():
    source = wire()
    label = {"type": None, "pre": "literal", "post": "", "state": 1}
    source["overview"]["shipLabels"] = [copy.deepcopy(label) for _ in range(64)]
    assert model.validate_wingman(source).overview["shipLabels"] == [label] * 64
    source["overview"]["shipLabels"].append(label)
    assert_error("collection_limit", model.validate_wingman, source)
    source["overview"]["shipLabels"] = []
    assert model.validate_wingman(source).overview["shipLabels"] == []
    label["type"] = "pilot name"
    source["overview"]["shipLabels"] = [label, label]
    assert model.validate_wingman(source).overview["shipLabels"] == [label, label]


COLOR_PATHS = [
    ("overview", "tabs", 0, "color"),
    ("overview", "settings", "stateColors", 0, "color"),
]


@pytest.mark.parametrize(
    "path,size", list(zip(COLOR_PATHS, [3, 4], strict=True)), ids=["rgb", "rgba"]
)
@pytest.mark.parametrize(
    "value",
    [-0.001, 1.001, True, "0", float("nan"), float("inf"), -float("inf"), 10**400],
    ids=["low", "high", "bool", "text", "nan", "inf", "negative-inf", "huge"],
)
def test_color_components_use_finite_nonboolean_unit_domain(path, size, value):
    assert_error(
        "invalid_number",
        model.validate_wingman,
        changed(path, [value] + [0] * (size - 1)),
    )


@pytest.mark.parametrize(
    "path,size", list(zip(COLOR_PATHS, [3, 4], strict=True)), ids=["rgb", "rgba"]
)
def test_color_lengths_bounds_and_number_representation_are_preserved(path, size):
    color = [0, 1, 0.5, 1.0][:size]
    source = changed(path, color)
    parsed = model.validate_wingman(source).overview
    actual = (
        parsed["tabs"][0]["color"]
        if size == 3
        else parsed["settings"]["stateColors"][0]["color"]
    )
    assert actual == color
    assert list(map(type, actual)) == list(map(type, color))
    for bad in ([0] * (size - 1), [0] * (size + 1), tuple(color), {}):
        with pytest.raises(model.SetupError):
            model.validate_wingman(changed(path, bad))


@pytest.mark.parametrize("field", ["stateColors", "stateBlinks"])
def test_appearance_records_use_unique_category_state_keys(field):
    source = wire()
    records = source["overview"]["settings"][field]
    records.append(copy.deepcopy(records[0]))
    assert_error("duplicate_id", model.validate_wingman, source)
    records.pop()
    records[1]["state"] = records[0]["state"]
    assert model.validate_wingman(source).overview["settings"][field][1]["state"] == 9
    records[1]["category"] = "other"
    assert_error("unsupported_variant", model.validate_wingman, source)
    records[1]["category"] = "flag"
    records[1]["state"] = True
    assert_error("invalid_number", model.validate_wingman, source)


@pytest.mark.parametrize(
    "field", ["flagOrder", "flagStates", "backgroundOrder", "backgroundStates"]
)
def test_state_membership_limits_and_uniqueness(field):
    source = {"settings": {field: [2147483647, 0]}}
    assert model.validate_overview(source, partial=True) == source
    source["settings"][field] = list(range(8192))
    assert len(model.validate_overview(source, partial=True)["settings"][field]) == 8192
    source["settings"][field].append(8192)
    assert_error("collection_limit", model.validate_overview, source, partial=True)
    source["settings"][field] = [9, 9]
    assert_error("duplicate_id", model.validate_overview, source, partial=True)


@pytest.mark.parametrize("field", ["columnOrder", "overviewColumns"])
@pytest.mark.parametrize(
    "columns",
    [["NAME", "NAME"], ["name"], ["UNKNOWN"], [False]],
    ids=["duplicate", "case", "enum", "bool"],
)
def test_columns_are_explicit_unique_enums(field, columns):
    with pytest.raises(model.SetupError):
        model.validate_overview({"settings": {field: columns}}, partial=True)


def test_tab_column_selection_and_order_are_independent_ordered_lists():
    source = wire()
    tab = source["overview"]["tabs"][0]
    tab["tabColumns"] = ["NAME", "ICON"]
    tab["tabColumnOrder"] = ["ICON", "DISTANCE", "NAME"]
    parsed = model.validate_wingman(source)
    assert parsed.overview["tabs"][0]["tabColumns"] == ["NAME", "ICON"]
    assert parsed.overview["tabs"][0]["tabColumnOrder"] == ["ICON", "DISTANCE", "NAME"]
    tab["tabColumns"] = ["unknown"]
    assert_error("unsupported_variant", model.validate_wingman, source)


SCALARS = [
    key for key, value in wire()["overview"]["settings"].items() if type(value) is bool
]


# _boolean owns the value domain; False and integer 0 pin each field's routing.
@pytest.mark.parametrize(
    "field,value",
    [
        pytest.param(field, value, id=f"{value_id}-{field}")
        for value, value_id in [
            (True, "true"),
            (False, "false"),
            (0, "zero"),
            (1, "one"),
            ("true", "text"),
        ]
        for field in SCALARS
        if field == "useSmallText" or value_id in ("false", "zero")
    ],
)
def test_scalar_settings_are_booleans_without_persisted_integer_coercions(field, value):
    source = {"settings": {field: value}}
    if type(value) is bool:
        assert model.validate_overview(source, partial=True) == source
    else:
        assert_error("invalid_type", model.validate_overview, source, partial=True)


@pytest.mark.parametrize("slot", range(6), ids=["x", "y", "w", "h", "rw", "rh"])
def test_each_geometry_integer_boundary_is_enforced_without_clamping(slot):
    for value in (-32768, 32768) if slot < 2 else (1, 32768):
        geometry = [0, 0, 1, 1, 1, 1]
        geometry[slot] = value
        source = changed(("layout", "windows", 0, "geometry"), geometry)
        assert (
            model.validate_wingman(source).layout["windows"][0]["geometry"] == geometry
        )
    for value in (-32769, 32769) if slot < 2 else (0, -1, 32769):
        geometry = [0, 0, 1, 1, 1, 1]
        geometry[slot] = value
        assert_error(
            "invalid_number",
            model.validate_wingman,
            changed(("layout", "windows", 0, "geometry"), geometry),
        )


@pytest.mark.parametrize(
    "value",
    [
        None,
        [0, 0, 1, 1, 1],
        [0, 0, 1, 1, 1, 1, 1],
        [True, 0, 1, 1, 1, 1],
        [0.0, 0, 1, 1, 1, 1],
        (0, 0, 1, 1, 1, 1),
    ],
    ids=["null", "short", "long", "bool", "float", "tuple"],
)
def test_active_overview_requires_exact_six_integer_geometry(value):
    with pytest.raises(model.SetupError):
        model.validate_wingman(changed(("layout", "windows", 0, "geometry"), value))


def test_layout_requires_every_fixed_slot_and_only_active_overview_ordinals():
    source = wire()
    source["layout"]["windows"].pop()
    assert_error("invalid_windows", model.validate_wingman, source)
    source = wire()
    source["layout"]["windows"].append(
        {"key": "overview_3", "geometry": [0, 0, 1, 1, 1, 1], "state": {}}
    )
    assert_error("unsupported_window", model.validate_wingman, source)
    for key in (
        "overview_0",
        "overview_01",
        "Overview",
        "chat",
        "inventory",
        "../file",
    ):
        assert_error(
            "unsupported_window",
            model.validate_wingman,
            changed(("layout", "windows", 0, "key"), key),
        )


def test_layout_record_budget_is_enforced_before_duplicate_topology():
    source = wire()
    source["layout"]["windows"] = [source["layout"]["windows"][0]] * 32
    # The v1 allowlist plus eight active overviews permits only 17 distinct slots;
    # 32 passes the resource cap but cannot satisfy the independent topology.
    assert_error("duplicate_id", model.validate_wingman, source)
    source["layout"]["windows"].append(source["layout"]["windows"][0])
    assert_error("collection_limit", model.validate_wingman, source)


# Keep the window dispatcher separate from scalar settings, sharing _boolean.
@pytest.mark.parametrize(
    "field,value",
    [
        pytest.param(field, value, id=f"{value_id}-{field}")
        for value, value_id in [
            (True, "true"),
            (False, "false"),
            (0, "zero"),
            (1, "one"),
            (None, "null"),
        ]
        for field in [
            "open",
            "minimized",
            "collapsed",
            "compact",
            "locked",
            "overlay",
            "lightBackground",
        ]
        if field == "open" or value_id in ("false", "zero")
    ],
)
def test_all_window_state_fields_are_optional_strict_booleans(field, value):
    source = changed(("layout", "windows", 0, "state"), {field: value})
    if type(value) is bool:
        assert model.validate_wingman(source).layout["windows"][0]["state"] == {
            field: value
        }
    else:
        assert_error("invalid_type", model.validate_wingman, source)


@pytest.mark.parametrize(
    "value",
    [None, False, True, 0, 1, 0.0, "false"],
    ids=["clear", "false", "true", "zero", "one", "float", "text"],
)
def test_target_lock_is_semantic_nullable_boolean(value):
    source = changed(("layout", "targetOriginLocked"), value)
    if value is None or type(value) is bool:
        assert model.validate_wingman(source).layout["targetOriginLocked"] is value
    else:
        assert_error("invalid_type", model.validate_wingman, source)


@pytest.mark.parametrize("slot", [0, 1], ids=["x", "y"])
def test_target_origin_bounds_are_finite_and_not_transformed(slot):
    for value in (0, 1, 0.25):
        pair = [0.5, 0.5]
        pair[slot] = value
        assert (
            model.validate_wingman(changed(("layout", "targetOrigin"), pair)).layout[
                "targetOrigin"
            ]
            == pair
        )
    for value in (
        -0.001,
        math.nextafter(1, math.inf),
        True,
        float("nan"),
        float("inf"),
        10**400,
    ):
        pair = [0.5, 0.5]
        pair[slot] = value
        assert_error(
            "invalid_number",
            model.validate_wingman,
            changed(("layout", "targetOrigin"), pair),
        )


@pytest.mark.parametrize(
    "value", [[0], [0, 0, 0], (0, 0), {}], ids=["short", "long", "tuple", "object"]
)
def test_target_origin_requires_exact_pair(value):
    with pytest.raises(model.SetupError):
        model.validate_wingman(changed(("layout", "targetOrigin"), value))


@pytest.mark.parametrize(
    "value",
    [-32768, 32768, 0, None, -32769, 32769, True, 0.0, "0"],
    ids=["min", "max", "zero", "clear", "low", "high", "bool", "float", "text"],
)
def test_hud_offset_is_nullable_bounded_integer(value):
    source = changed(("layout", "hudOffset"), value)
    if value is None or (type(value) is int and -32768 <= value <= 32768):
        assert model.validate_wingman(source).layout["hudOffset"] == value
    else:
        assert_error("invalid_number", model.validate_wingman, source)


def test_layout_standalone_returns_owned_values_and_null_clear_intent():
    source = wire()
    layout = source["layout"]
    layout.update(targetOrigin=None, targetOriginLocked=None, hudOffset=None)
    layout["windows"][3]["geometry"] = None
    parsed = model.validate_layout(layout, source["overview"])
    assert parsed == layout
    parsed["windows"][0]["geometry"][0] = 42
    assert layout["windows"][0]["geometry"][0] == 100


def test_summary_contains_only_counts_labels_and_limitations_not_document_data():
    parsed = model.validate_wingman(wire())
    summary = model.summarize(parsed)
    assert set(summary) == {"counts", "windowLabels", "limitations"}
    assert summary["counts"] == {
        "presets": 3,
        "tabs": 8,
        "windowGroups": 3,
        "shipLabels": 9,
        "layoutWindows": 12,
    }
    assert summary["windowLabels"] == [
        "Overview",
        "Overview 2",
        "Overview 3",
        "Selected item",
        "Probe scanner",
        "Directional scanner",
        "Drones",
        "Fleet",
        "Watch list",
        "Standalone bookmarks",
        "Solar-system map",
        "Primary map",
    ]
    assert (
        "Your resolution and UI scale stay unchanged. This layout is copied as saved; a different display size or UI scale may need manual adjustment in EVE."
        in summary["limitations"]
    )
    assert any("unstacked" in text for text in summary["limitations"])
    summary["windowLabels"].clear()
    summary["counts"]["presets"] = 100
    assert model.summarize(parsed)["counts"]["presets"] == 3
    assert len(model.summarize(parsed)["windowLabels"]) == 12


def test_partial_summary_cannot_invent_a_layout_and_reports_label_ambiguity():
    parsed = model.ParsedSetup(
        "native-yaml", {"presets": []}, None, True, ("Synthetic warning",)
    )
    summary = model.summarize(parsed)
    assert summary["counts"] == {
        "presets": 0,
        "tabs": 0,
        "windowGroups": 0,
        "shipLabels": 0,
        "layoutWindows": 0,
    }
    assert summary["windowLabels"] == []
    assert "Overview configuration only — no window layout." in summary["limitations"]
    assert any("Keep my ship labels" in text for text in summary["limitations"])
    assert "Synthetic warning" in summary["limitations"]


def test_limits_payload_reports_fresh_complete_supported_budgets():
    limits = model.limits_payload()
    assert limits == {
        "max_bytes": 2097152,
        "max_depth": 16,
        "max_nodes": 100000,
        "max_presets": 256,
        "max_tabs": 20,
        "max_window_groups": 8,
        "max_ship_labels": 64,
        "max_layout_windows": 32,
        "max_membership_ids": 8192,
        "max_id": 2147483647,
        "max_name_codepoints": 512,
        "max_label_codepoints": 4096,
        "min_coordinate": -32768,
        "max_coordinate": 32768,
        "min_size": 1,
        "max_size": 32768,
        "min_target_origin": 0,
        "max_target_origin": 1,
        "min_hud_offset": -32768,
        "max_hud_offset": 32768,
        "min_color": 0,
        "max_color": 1,
    }
    limits["max_bytes"] = 0
    assert model.limits_payload()["max_bytes"] == 2097152


def test_text_budget_counts_utf8_bytes_before_parsing_and_rejects_bad_text():
    text = "𐐀" * 524288
    assert model.check_text_budget(text) is None
    assert_error("byte_limit", model.check_text_budget, text + "a")
    assert_error("byte_limit", model.check_text_budget, "x" * 2097153)
    assert_error("invalid_text", model.check_text_budget, "\ud800")
    assert_error("invalid_text", model.check_text_budget, "\x00")
    assert_error("invalid_text", model.check_text_budget, b"{}")


def test_structure_depth_counts_container_nesting_and_contains_cycles():
    source = 0
    for _ in range(16):
        source = [source]
    assert model.check_structure_budget(source) is None
    assert_error("depth_limit", model.check_structure_budget, [source])
    cycle = []
    cycle.append(cycle)
    assert_error("depth_limit", model.check_structure_budget, cycle)


def test_structure_budget_counts_containers_values_and_object_keys():
    assert model.check_structure_budget([None] * 99999) is None
    assert_error("node_limit", model.check_structure_budget, [None] * 100000)
    # Root, inner list and 49,999 key/value pairs: exactly 100,000 nodes.
    source = [{str(i): None for i in range(49999)}]
    assert model.check_structure_budget(source) is None
    assert_error("node_limit", model.check_structure_budget, [*source, None])


def test_direct_domain_boundaries_check_structure_before_conversion():
    oversized = [None] * 100000
    assert_error("node_limit", model.validate_wingman, {"unknown": oversized})
    assert_error(
        "node_limit", model.validate_overview, {"unknown": oversized}, partial=True
    )
    assert_error(
        "node_limit", model.validate_layout, {"unknown": oversized}, wire()["overview"]
    )
