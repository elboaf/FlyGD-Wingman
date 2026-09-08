"""Synthetic native compatibility, not evidence of EVE reset/write behavior."""

import copy
import json
from pathlib import Path

import pytest
import yaml

from tests.setup_fixtures import wire
from wingman.evesettings import setup_model as model
from wingman.evesettings import setup_sharing as sharing

FIXTURE = Path(__file__).parent / "fixtures" / "ui_setup" / "native-complete.yaml"


def native():
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def parse(value, *, style="yaml"):
    text = (
        json.dumps(value)
        if style == "json"
        else yaml.safe_dump(value, allow_unicode=True)
    )
    return sharing.parse_text(text)


def assert_error(code, text):
    with pytest.raises(model.SetupError) as caught:
        sharing.parse_text(text)
    assert caught.value.code == code
    assert str(caught.value)


def test_native_input_does_not_fabricate_layout_or_drop_labels():
    parsed = sharing.parse_text(FIXTURE.read_text(encoding="utf-8"))
    assert parsed.source_kind == "native-yaml"
    assert parsed.layout is None
    assert parsed.ambiguous_labels
    assert len(parsed.overview["presets"]) == 42
    assert parsed.overview["presets"][0] == {
        "name": "Synthetic Filter 00",
        "groups": [25, 27],
        "filteredStates": [9],
        "alwaysShownStates": [12],
    }
    assert parsed.overview["windowGroups"] == [list(range(8))]
    assert len(parsed.overview["shipLabels"]) == 9
    # Ambiguity is disclosed, not resolved by assigning arbitrary null records
    # to order slots. Keep every supplied record in encounter order for review.
    assert [row["pre"] for row in parsed.overview["shipLabels"]] == [
        "<b>Invented patrol</b>",
        "[",
        "<br>",
        " / ",
        "(",
        "",
        "Synthetic pilot: ",
        "!",
        " — ",
    ]
    assert parsed.overview["tabs"][0] == {
        "id": 0,
        "name": "Synthetic Tab 0",
        "overview": "Synthetic Filter 00",
        "bracket": "Synthetic Filter 01",
        "color": None,
        "tabColumns": ["NAME", "ICON"],
        "tabColumnOrder": ["ICON", "DISTANCE", "NAME"],
        "showAll": False,
        "showNone": False,
        "showSpecials": False,
    }
    summary = model.summarize(parsed)
    assert summary["counts"]["layoutWindows"] == 0
    assert any("Keep my ship labels" in item for item in summary["limitations"])
    assert any("one primary overview group" in item for item in summary["limitations"])
    assert any(
        "absent" in item.lower() and "retain" in item.lower()
        for item in summary["limitations"]
    )


@pytest.mark.parametrize("style", ["block", "flow", "json", "document", "bom"])
def test_native_syntax_variants_use_the_strict_native_path(style):
    value = {"presets": native()["presets"][:1]}
    text = yaml.safe_dump(value, default_flow_style=style == "flow")
    if style == "json":
        text = json.dumps(value)
    elif style == "document":
        text = "---\n" + text + "...\n"
    elif style == "bom":
        text = "\ufeff" + text
    parsed = sharing.parse_text(text)
    assert parsed.source_kind == "native-yaml"
    assert parsed.overview == {
        "presets": [
            {
                "name": "Synthetic Filter 00",
                "groups": [25, 27],
                "filteredStates": [9],
                "alwaysShownStates": [12],
            }
        ]
    }
    assert parsed.layout is None
    assert not parsed.ambiguous_labels


def test_absent_aggregates_are_not_filled_and_empty_false_are_supplied():
    parsed = parse(
        {
            "flagStates": [],
            "stateBlinks": [],
            "stateColorsNameList": [],
            "userSettings": [["useSmallColorTags", False]],
        }
    )
    assert parsed.overview == {
        "settings": {
            "flagStates": [],
            "stateColors": [],
            "stateBlinks": [],
            "useSmallColorTags": False,
        }
    }
    assert parse({"presets": []}).overview == {"presets": []}
    assert parse({"userSettings": []}).overview == {"settings": {}}
    assert parse({"shipLabels": [], "shipLabelOrder": []}).overview == {
        "shipLabels": []
    }


def test_order_arrays_tab_ids_and_optional_label_presence_remain_independent():
    value = native()
    value["tabSetup"].reverse()
    value["tabSetup"][0][0] = 2147483647
    parsed = parse(value)
    assert parsed.overview["windowGroups"] == [[2147483647, 6, 5, 4, 3, 2, 1, 0]]
    assert parsed.overview["settings"]["flagOrder"] == [12, 0, 9]
    assert parsed.overview["settings"]["backgroundStates"] == [9, 12]
    assert parsed.overview["settings"]["overviewColumns"] == [
        "NAME",
        "ICON",
        "DISTANCE",
    ]
    assert parsed.overview["shipLabels"][0] == {
        "type": None,
        "pre": "<b>Invented patrol</b>",
        "post": "",
        "state": 1,
    }
    assert parsed.overview["shipLabels"][-1]["bold"] is False
    assert parsed.overview["shipLabels"][-1]["fontsize"] is None


@pytest.mark.parametrize("kind", [None, "pilot name"], ids=["null", "named"])
def test_repeated_label_types_are_records_not_duplicate_mapping_keys(kind):
    labels = [
        [kind, [["type", kind], ["pre", text], ["post", ""], ["state", 1]]]
        for text in ["First", "Second"]
    ]
    parsed = parse({"shipLabels": labels, "shipLabelOrder": [kind, kind]})
    assert parsed.ambiguous_labels
    assert [row["pre"] for row in parsed.overview["shipLabels"]] == ["First", "Second"]


def test_unique_label_order_is_authoritative_not_pair_encounter_order():
    value = native()
    labels = value["shipLabels"][4:]
    parsed = parse(
        {
            "shipLabels": labels,
            "shipLabelOrder": [
                "ship type",
                "pilot name",
                "alliance",
                "ship name",
                "corporation",
            ],
        }
    )
    assert not parsed.ambiguous_labels
    assert [row["pre"] for row in parsed.overview["shipLabels"]] == [
        " — ",
        "Synthetic pilot: ",
        "(",
        "!",
        "",
    ]


@pytest.mark.parametrize(
    "case",
    [
        "missing-order",
        "order-only",
        "missing-type",
        "extra-type",
        "unknown-type",
        "outer-mismatch",
    ],
)
def test_label_order_and_outer_type_must_describe_exact_supplied_records(case):
    value = native()
    if case == "missing-order":
        del value["shipLabelOrder"]
    elif case == "order-only":
        del value["shipLabels"]
    elif case == "missing-type":
        value["shipLabelOrder"].pop()
    elif case == "extra-type":
        value["shipLabelOrder"].append(None)
    elif case == "unknown-type":
        value["shipLabelOrder"][0] = "linebreak"
    else:
        value["shipLabels"][0][0] = "pilot name"
    with pytest.raises(model.SetupError):
        parse(value)


@pytest.mark.parametrize("field", ["overview", "bracket"])
@pytest.mark.parametrize(
    "reference",
    [
        None,
        "all",
        "none",
        "DefaultPreset_missing",
        "synthetic Filter 00",
        " Synthetic Filter 00 ",
    ],
    ids=["null", "all", "none", "default", "case", "space"],
)
def test_no_unproved_sentinel_or_recipient_name_can_resolve_a_reference(
    field, reference
):
    value = native()
    for pair in value["tabSetup"][0][1]:
        if pair[0] == field:
            pair[1] = reference
    if field == "bracket" and reference is None:
        assert parse(value).overview["tabs"][0]["bracket"] is None
    else:
        with pytest.raises(model.SetupError):
            parse(value)


def test_supplied_tabs_need_included_dependencies_even_when_presets_are_absent():
    value = native()
    del value["presets"]
    with pytest.raises(model.SetupError) as caught:
        parse(value)
    assert caught.value.code == "dangling_reference"


@pytest.mark.parametrize("style", ["yaml", "json"])
@pytest.mark.parametrize(
    "name", ["all", "none", " Fleet ", "𐐀é"], ids=["all", "none", "space", "unicode"]
)
def test_reference_names_are_exact_text_not_magic_sentinels(style, name):
    value = native()
    value["presets"][0][0] = name
    for pair in value["tabSetup"][0][1]:
        if pair[0] in ("name", "overview", "bracket"):
            pair[1] = name
    overview = parse(value, style=style).overview
    assert overview["presets"][0]["name"] == name
    assert overview["tabs"][0]["name"] == name
    assert overview["tabs"][0]["overview"] == name
    assert overview["tabs"][0]["bracket"] == name


@pytest.mark.parametrize("style", ["yaml", "json"])
def test_native_exponent_tab_colors_preserve_numeric_values(style):
    value = native()
    next(pair for pair in value["tabSetup"][0][1] if pair[0] == "color")[1] = [
        1e-6,
        1e-20,
        1,
    ]
    parsed = parse(value, style=style)
    assert parsed.overview["tabs"][0]["color"] == [0.000001, 0.00000000000000000001, 1]
    assert list(map(type, parsed.overview["tabs"][0]["color"])) == [float, float, int]
    assert parsed.source_kind == "native-yaml"
    assert parsed.layout is None


@pytest.mark.parametrize(
    "name,want",
    [
        ("black", [0.0, 0.0, 0.0, 1.0]),
        ("blue", [0.2, 0.5, 1.0, 1.0]),
        ("darkBlue", [0.0, 0.15, 0.6, 1.0]),
        ("green", [0.1, 0.6, 0.1, 1.0]),
        ("orange", [1.0, 0.35, 0.0, 1.0]),
        ("red", [0.75, 0.0, 0.0, 1.0]),
        ("turquoise", [0.0, 0.63, 0.57, 1.0]),
        ("white", [0.7, 0.7, 0.7, 1.0]),
        ("yellow", [1.0, 0.7, 0.0, 1.0]),
    ],
    ids=[
        "black",
        "blue",
        "dark-blue",
        "green",
        "orange",
        "red",
        "turquoise",
        "white",
        "yellow",
    ],
)
def test_eve_palette_is_not_css_and_state_categories_remain_distinct(name, want):
    result = parse(
        {
            "stateColorsNameList": [["background_9", name], ["flag_9", name]],
            "stateBlinks": [["flag_9", False]],
        }
    ).overview["settings"]
    assert result["stateColors"] == [
        {"category": "background", "state": 9, "color": want},
        {"category": "flag", "state": 9, "color": want},
    ]
    assert result["stateBlinks"] == [{"category": "flag", "state": 9, "blink": False}]


@pytest.mark.parametrize(
    "color",
    ["purple", "DarkBlue", "#ff0000", None, [1, 0, 0, 1], True],
    ids=["name", "case", "css", "null", "rgba", "bool"],
)
def test_unknown_native_color_names_and_variants_refuse(color):
    with pytest.raises(model.SetupError) as caught:
        parse({"stateColorsNameList": [["flag_9", color]]})
    assert caught.value.code == "unsupported_variant"


@pytest.mark.parametrize(
    "key",
    [
        "other_1",
        "flag_-1",
        "flag_2147483648",
        "flag_01",
        "flag_+1",
        "flag_1.0",
        "flag_\u0661",
        "flag_1_extra",
        True,
        None,
    ],
    ids=[
        "category",
        "negative",
        "large",
        "zero-pad",
        "plus",
        "float",
        "unicode",
        "suffix",
        "bool",
        "null",
    ],
)
def test_state_key_syntax_is_explicit_and_bounded(key):
    with pytest.raises(model.SetupError):
        parse({"stateBlinks": [[key, True]]})


@pytest.mark.parametrize(
    "case",
    [
        "root",
        "preset",
        "preset-field",
        "tab",
        "tab-field",
        "label-field",
        "setting",
        "color",
        "blink",
    ],
)
@pytest.mark.parametrize("style", ["yaml", "json"])
def test_duplicate_mapping_and_keyed_pairs_refuse_before_last_wins(style, case):
    value = native()
    if case == "root":
        text = (
            '{"presets": [], "presets": []}'
            if style == "json"
            else "presets: []\npresets: []\n"
        )
        assert_error("duplicate_field", text)
        return
    field, nested = {
        "preset": ("presets", False),
        "preset-field": ("presets", True),
        "tab": ("tabSetup", False),
        "tab-field": ("tabSetup", True),
        "label-field": ("shipLabels", True),
        "setting": ("userSettings", False),
        "color": ("stateColorsNameList", False),
        "blink": ("stateBlinks", False),
    }[case]
    pairs = value[field][0][1] if nested else value[field]
    pairs.append(copy.deepcopy(pairs[0]))
    with pytest.raises(model.SetupError) as caught:
        parse(value, style=style)
    assert caught.value.code == "duplicate_field"


@pytest.mark.parametrize(
    "text",
    [
        "presets: []\nextra: {a: 1, a: 2}\n",
        "presets: []\n? [a, b]\n: 1\n",
    ],
    ids=["nested-map", "complex-key"],
)
def test_mapping_keys_are_never_silently_collapsed_or_unhashable_errors(text):
    with pytest.raises(model.SetupError):
        sharing.parse_text(text)


@pytest.mark.parametrize(
    "case",
    [
        "root",
        "preset-map",
        "preset-fields-map",
        "tab-map",
        "label-map",
        "setting-map",
        "short-pair",
        "long-pair",
        "bool-id",
        "unknown-preset",
        "unknown-tab",
        "unknown-label",
        "unknown-setting",
        "layout",
    ],
)
@pytest.mark.parametrize("style", ["yaml", "json"])
def test_native_shape_and_field_allowlists_are_not_generic_dat_passthrough(style, case):
    value = native()
    if case == "root":
        value["extra"] = []
    elif case in ("preset-map", "tab-map", "label-map", "setting-map"):
        key = {
            "preset-map": "presets",
            "tab-map": "tabSetup",
            "label-map": "shipLabels",
            "setting-map": "userSettings",
        }[case]
        value[key] = {}
    elif case == "preset-fields-map":
        value["presets"][0][1] = dict(value["presets"][0][1])
    elif case == "short-pair":
        value["presets"][0].pop()
    elif case == "long-pair":
        value["presets"][0].append([])
    elif case == "bool-id":
        value["tabSetup"][0][0] = True
    elif case in ("unknown-preset", "unknown-tab", "unknown-label"):
        key = {
            "unknown-preset": "presets",
            "unknown-tab": "tabSetup",
            "unknown-label": "shipLabels",
        }[case]
        value[key][0][1].append(["extra", False])
    elif case == "unknown-setting":
        value["userSettings"].append(["useSmallText", False])
    else:
        value["layout"] = {}
    with pytest.raises(model.SetupError):
        parse(value, style=style)


@pytest.mark.parametrize(
    "key",
    [
        "presets",
        "tabSetup",
        "shipLabels",
        "shipLabelOrder",
        "backgroundOrder",
        "backgroundStates",
        "flagOrder",
        "flagStates",
        "columnOrder",
        "overviewColumns",
        "stateBlinks",
        "stateColorsNameList",
        "userSettings",
    ],
)
def test_supplied_native_null_is_not_absence_or_full_reset(key):
    value = native()
    value[key] = None
    with pytest.raises(model.SetupError):
        parse(value)


@pytest.mark.parametrize(
    "text",
    [
        "presets: !custom []",
        "presets: !!python/object/apply:os.system [echo]",
        "presets: !!seq []",
        "presets: &a []",
        "presets: *missing",
        "presets: &a [*a]",
        "presets: &a [1]\nx: &b [*a, *a]\ny: [*b, *b]",
    ],
    ids=["tag", "python", "core-tag", "anchor", "alias", "cycle", "expansion"],
)
def test_forbidden_yaml_events_refuse_before_any_document_construction(
    monkeypatch, text
):
    def must_not_construct(*args, **kwargs):
        pytest.fail("Forbidden YAML reached document construction")

    monkeypatch.setattr(yaml.SafeLoader, "construct_document", must_not_construct)
    assert_error("unsupported_yaml", text)


@pytest.mark.parametrize(
    "text",
    [
        "presets: [",
        "presets: []\n---\npresets: []",
        "presets: []\n---\n",
        "userSettings: [[useSmallColorTags, 2026-01-01]]",
        "presets: []\n<<: {}",
        "flagOrder: [" + "9" * 5000 + "]",
    ],
    ids=["syntax", "documents", "empty-document", "timestamp", "merge", "huge-int"],
)
def test_yaml_parser_and_unsupported_constructor_errors_are_contained(text):
    with pytest.raises(model.SetupError):
        sharing.parse_text(text)


@pytest.mark.parametrize("marker", ["format", "version", "type", "overview", "layout"])
def test_a_claimed_envelope_cannot_hide_among_native_fields(marker):
    value = {"presets": [], marker: "wingman-preset"}
    for text in (
        json.dumps(value),
        yaml.safe_dump(value),
        yaml.safe_dump(value, default_flow_style=True),
    ):
        with pytest.raises(model.SetupError):
            sharing.parse_text(text)


@pytest.mark.parametrize(
    "case",
    [
        "valid-yaml",
        "unsupported-version",
        "malformed-json",
        "trailing",
        "duplicate",
        "missing",
    ],
)
def test_claimed_wingman_input_is_never_rescued_by_yaml(case):
    value = wire()
    if case == "unsupported-version":
        value["version"] = 99
    elif case == "missing":
        del value["layout"]
    text = yaml.safe_dump(value)
    if case == "malformed-json":
        text = json.dumps(value)[:-1] + ",}"
    elif case == "trailing":
        text = json.dumps(value) + "\npresets: []"
    elif case == "duplicate":
        text = json.dumps(value).replace('"version": 1', '"version": 99, "version": 1')
    with pytest.raises(model.SetupError):
        sharing.parse_text(text)


def test_exact_native_utf8_byte_budget_and_one_byte_over():
    text = "presets: []\n# 𐐀é"
    text += " " * (2097152 - len(text.encode("utf-8")))
    assert sharing.parse_text(text).overview == {"presets": []}
    assert_error("byte_limit", text + " ")


def test_native_depth_boundary_and_preconstruction_refusal(monkeypatch):
    from wingman.evesettings import overview_yaml

    # Root container is depth one; scalar leaves do not add depth.
    with pytest.raises(model.SetupError) as caught:
        overview_yaml.parse_text("[" * 16 + "0" + "]" * 16)
    assert caught.value.code == "invalid_type"

    def must_not_construct(*args, **kwargs):
        pytest.fail("Depth overflow reached document construction")

    monkeypatch.setattr(yaml.SafeLoader, "construct_document", must_not_construct)
    with pytest.raises(model.SetupError) as caught:
        overview_yaml.parse_text("[" * 17 + "0" + "]" * 17)
    assert caught.value.code == "depth_limit"


@pytest.mark.parametrize("style", ["yaml", "json"])
def test_native_node_boundary_counts_pair_containers_and_mapping_keys(
    monkeypatch, style
):
    value = {"presets": []}
    remaining = 99937  # Root/key/list = 3; five native presets = 5 * 12 nodes.
    for i in range(5):
        fields = []
        for field in ("groups", "filteredStates", "alwaysShownStates"):
            count = min(8192, remaining)
            # Repeated preset groups still consume one node per supplied ID.
            fields.append(
                [field, [73] * count if field == "groups" else list(range(count))]
            )
            remaining -= count
        value["presets"].append([f"Filter {i}", fields])
    assert remaining == 0
    assert len(parse(value, style=style).overview["presets"]) == 5
    value["presets"][-1][1][-1][1].append(42)
    text = (
        json.dumps(value)
        if style == "json"
        else yaml.safe_dump(value, default_flow_style=True)
    )

    def must_not_construct(*args, **kwargs):
        pytest.fail("Node overflow reached document construction")

    monkeypatch.setattr(yaml.SafeLoader, "construct_document", must_not_construct)
    assert_error("node_limit", text)


def test_native_model_collection_limits_remain_effective():
    value = native()
    value["tabSetup"].append([8, copy.deepcopy(value["tabSetup"][0][1])])
    assert_error("collection_limit", yaml.safe_dump(value))
    value = {
        "presets": [
            [
                f"Filter {i}",
                [["groups", []], ["filteredStates", []], ["alwaysShownStates", []]],
            ]
            for i in range(256)
        ]
    }
    assert len(parse(value).overview["presets"]) == 256
    value["presets"].append(
        ["Extra", [["groups", []], ["filteredStates", []], ["alwaysShownStates", []]]]
    )
    assert_error("collection_limit", yaml.safe_dump(value))


def test_native_repeated_preset_groups_preserve_the_supplied_sequence():
    value = native()
    # Invented IDs reproduce the aggregate pattern, not personal memberships:
    # four definitions with repetitions, 37 extra entries across those lists.
    groups = [
        [73, 11] * 6,
        [88, 19] * 5 + [88],
        [92, 23] * 5 + [92],
        [104, 31] * 5 + [104],
    ]
    for preset, membership in zip(value["presets"], groups):
        next(pair for pair in preset[1] if pair[0] == "groups")[1] = membership
    before = copy.deepcopy(value)
    for text in (yaml.safe_dump(value), json.dumps(value)):
        parsed = sharing.parse_text(text)
        assert [preset["groups"] for preset in parsed.overview["presets"][:4]] == groups
        memberships = [preset["groups"] for preset in parsed.overview["presets"]]
        assert sum(len(ids) != len(set(ids)) for ids in memberships) == 4
        assert sum(len(ids) - len(set(ids)) for ids in memberships) == 37
        assert len(parsed.overview["presets"]) == 42
        parsed.overview["presets"][0]["groups"].clear()
        assert value == before


def test_each_native_parse_owns_its_nested_values():
    text = FIXTURE.read_text(encoding="utf-8")
    first = sharing.parse_text(text)
    first.overview["shipLabels"].clear()
    first.overview["settings"]["stateColors"][0]["color"][0] = 0
    second = sharing.parse_text(text)
    assert len(second.overview["shipLabels"]) == 9
    assert second.overview["settings"]["stateColors"][0]["color"] == [0.75, 0, 0, 1]


def test_pyyaml_notice_includes_installed_license_and_locked_version():
    from importlib.metadata import distribution

    root = Path(__file__).resolve().parents[1]
    package = distribution("PyYAML")
    license_file = next(
        file for file in package.files if str(file).endswith("/licenses/LICENSE")
    )
    license_text = package.locate_file(license_file).read_text(encoding="utf-8").strip()
    notices = (root / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8")
    section = notices.split("## PyYAML\n", 1)[1].split("\n## ", 1)[0]
    assert "Licence: MIT" in section
    assert f"Version: {package.version}" in section
    assert license_text in section
