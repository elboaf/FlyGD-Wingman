"""Pure adapter contracts on synthetic recipients, not real-profile acceptance."""

import copy
import json
from pathlib import Path

import pytest

from tests.setup_fixtures import documents, install_lossless_codec, wire
from tests.test_evesettings_codec import CODEC
from wingman.evesettings import codec
from wingman.evesettings import setup_model as model
from wingman.evesettings.setup_documents import apply_setup
from wingman.evesettings.setup_sharing import parse_text

STAMP = "long:116444736420000000"


def value(document, section, key):
    return document.doc[f"bytes:{section}"][f"bytes:{key}"]["tuple"][1]


def stamp(item):
    return {"tuple": ["long:116444736010000000", item]}


def supported_recipient():
    """Synthetic missing-selector/no-surplus branch; NOT a sender clone.

    Retain the rich recipient's four distinct tabs, identities, definitions,
    defaults and geometry, but group its tabs in ONE active window. Cached
    overview_3 is deliberately stacked and remains outside the active topology.
    """
    account, character = documents("recipient")
    account.doc["bytes:overview"]["bytes:tabsByWindowInstanceID"] = stamp(
        [[0, 1, 2, 3]]
    )
    for key in ("overviewTabs", "overviewTabs_names"):
        del account.doc["bytes:tabgroups"][f"bytes:{key}"]
    value(character, "windows", "stacksWindows")["bytes:overview_3"] = (
        "bytes:CachedStack"
    )
    return account, character


def incoming():
    """Distinct incoming custom name exercises insertion, not replacement."""
    data = wire()
    data["overview"]["presets"][0]["name"] = "Incoming Fleet"
    for tab in data["overview"]["tabs"]:
        if tab["overview"] == "Synthetic Fleet":
            tab["overview"] = "Incoming Fleet"
    return model.validate_wingman(data)


def apply(account, character, parsed=None, *, keep=False):
    return apply_setup(
        account, character, parsed or incoming(), keep_ship_labels=keep, now=42.9
    )


def refuse(account, character, code, context, parsed=None, *, keep=False):
    before = copy.deepcopy((account, character, parsed))
    with pytest.raises(model.SetupError) as error:
        apply(account, character, parsed, keep=keep)
    assert error.value.code == code
    assert context in str(error.value)
    assert (account, character, parsed) == before


def test_full_apply_changes_owned_records_not_recipient_identity_or_metadata():
    account, character = supported_recipient()
    parsed = incoming()
    before = copy.deepcopy((account, character, parsed))
    out_a, out_c = apply(account, character, parsed)
    assert (account, character, parsed) == before
    assert out_a.had_crc is False and out_c.had_crc is False
    for section in ("defaultoverview", "syntheticPrivate", "audio"):
        assert out_a.doc[f"bytes:{section}"] == account.doc[f"bytes:{section}"]
    assert value(out_a, "tabgroups", "overviewTabs") == 0
    assert (
        out_a.doc["bytes:tabgroups"]["bytes:syntheticUnrelatedTab"]
        == account.doc["bytes:tabgroups"]["bytes:syntheticUnrelatedTab"]
    )
    for section in ("ui", "syntheticPrivate"):
        assert out_c.doc[f"bytes:{section}"] == character.doc[f"bytes:{section}"]
    for key in (
        "activeOverviewPreset",
        "presetHistoryKeys",
        "restoreData",
        "alwaysShow",
        "filterOut",
        "unfiltered",
    ):
        assert (
            out_a.doc["bytes:overview"][f"bytes:{key}"]
            == account.doc["bytes:overview"][f"bytes:{key}"]
        )
    for key in ("overviewProfileName", "editHistory"):
        assert (
            out_a.doc["bytes:ui"][f"bytes:{key}"]
            == account.doc["bytes:ui"][f"bytes:{key}"]
        )
    assert value(out_a, "overview", "tabsByWindowInstanceID") == [
        [0, 1, 2],
        [3, 4, 5],
        [6, 7],
    ]
    tabs = value(out_a, "overview", "tabsettings_new")
    assert list(tabs) == [f"int:{i}" for i in range(8)]
    assert tabs["int:0"] == {
        "bytes:name": "utf8:Synthetic near",
        "bytes:overview": "utf8:Incoming Fleet",
        "bytes:bracket": "utf8:Synthetic Brackets",
        "bytes:color": [0.2, 0.5, 1.0],
        "bytes:showAll": False,
        "bytes:showNone": False,
        "bytes:showSpecials": False,
        "bytes:tabColumns": ["bytes:ICON", "bytes:DISTANCE", "bytes:NAME"],
        "bytes:tabColumnOrder": [
            "bytes:ICON",
            "bytes:DISTANCE",
            "bytes:NAME",
            "bytes:TYPE",
            "bytes:TAG",
            "bytes:CORPORATION",
            "bytes:ALLIANCE",
            "bytes:FACTION",
            "bytes:MILITIA",
            "bytes:SIZE",
            "bytes:VELOCITY",
            "bytes:RADIALVELOCITY",
            "bytes:TRANSVERSALVELOCITY",
            "bytes:ANGULARVELOCITY",
        ],
    }
    assert tabs["int:2"]["bytes:overview"] == "utf8:Synthetic Travel"
    presets = value(out_a, "overview", "overviewProfilePresets")
    assert presets["utf8:Incoming Fleet"] == {
        "bytes:groups": [25, 27],
        "bytes:filteredStates": [9],
        "bytes:alwaysShownStates": [12],
    }
    for key, record in value(account, "overview", "overviewProfilePresets").items():
        assert presets[key] == record
    out_a.doc["bytes:defaultoverview"].clear()
    out_c.doc["bytes:ui"].clear()
    presets["utf8:Incoming Fleet"]["bytes:groups"].clear()
    assert (account, character, parsed) == before


def test_geometry_seven_maps_and_target_hud_are_exact_and_narrow():
    account, character = supported_recipient()
    out_a, out_c = apply(account, character)
    geometry = value(out_c, "windows", "windowSizesAndPositions_1")
    assert geometry["bytes:overview"] == {"tuple": [100, 120, 340, 500, 1920, 1080]}
    assert geometry["bytes:overview_1"] == {"tuple": [-20, 200, 320, 420, 1600, 900]}
    assert "bytes:primary_map_panel" not in geometry
    for field, expected in [
        ("openWindows", True),
        ("minimizedWindows", False),
        ("collapsedWindows", False),
        ("compactWindows", True),
        ("lockedWindows", False),
        ("isOverlayedWindows", False),
        ("isLightBackgroundWindows", True),
    ]:
        result = value(out_c, "windows", field)
        assert result["bytes:overview"] is expected
        assert "bytes:primary_map_panel" not in result
        if field != "openWindows":
            assert "bytes:overview_2" not in result
        for key in ("bytes:overview_3", "utf8:SyntheticPrivateChat"):
            original = value(character, "windows", field)
            assert (key in result) == (key in original)
            if key in original:
                assert result[key] == original[key]
    for key in ("bytes:overview_3", "utf8:SyntheticPrivateChat"):
        assert (
            geometry[key]
            == value(character, "windows", "windowSizesAndPositions_1")[key]
        )
    for key in ("stacksWindows", "preferredIdxInStack3", "__version__"):
        assert (
            out_c.doc["bytes:windows"][f"bytes:{key}"]
            == character.doc["bytes:windows"][f"bytes:{key}"]
        )
    assert out_a.doc["bytes:ui"]["bytes:targetOrigin"] == {
        "tuple": [STAMP, {"tuple": [0.25, 0.75]}]
    }
    assert out_a.doc["bytes:ui"]["bytes:targetOriginLocked"] == {"tuple": [STAMP, 0]}
    assert out_c.doc["bytes:windows"]["bytes:shipuialignleftoffset"] == {
        "tuple": [STAMP, -160]
    }


def test_ordered_labels_and_optional_formatting_presence():
    out_a, _ = apply(*supported_recipient())
    labels = value(out_a, "overview", "shipLabels")
    assert [row["bytes:pre"] for row in labels] == [
        "utf8:<b>Synthetic flight</b>",
        "utf8:Pilot: ",
        "utf8:[",
        "utf8:",
        "utf8:<br>",
        "utf8:(",
        "utf8: — ",
        "utf8: / ",
        "utf8:'",
    ]
    assert sum(row["bytes:type"] is None for row in labels) == 4
    assert set(labels[0]) == {"bytes:type", "bytes:pre", "bytes:post", "bytes:state"}
    assert labels[8] == {
        "bytes:type": "utf8:ship name",
        "bytes:pre": "utf8:'",
        "bytes:post": "utf8:'",
        "bytes:state": 0,
        "bytes:bold": False,
        "bytes:italic": False,
        "bytes:underline": False,
        "bytes:fontsize": None,
        "bytes:color": None,
    }


def test_full_appearance_state_aggregates_are_known_types():
    out_a, _ = apply(*supported_recipient())
    assert value(out_a, "overview", "flagOrder2") == [12, 9, 10]
    assert value(out_a, "overview", "overviewColumns") == [
        "bytes:ICON",
        "bytes:DISTANCE",
        "bytes:NAME",
    ]
    assert value(out_a, "overview", "stateColors") == {
        'json:{"tuple":["bytes:background",9]}': {"tuple": [0.75, 0.0, 0.0, 1.0]},
        'json:{"tuple":["bytes:flag",12]}': {"tuple": [0.0, 0.15, 0.6, 1.0]},
    }
    assert value(out_a, "overview", "stateBlinks") == {
        'json:{"tuple":["bytes:background",9]}': True,
        'json:{"tuple":["bytes:flag",12]}': False,
    }
    assert value(out_a, "overview", "applyToStructures") is False
    assert value(out_a, "overview", "viewTactical_camTactical") is True


def test_full_absent_and_null_clear_only_owned_overrides():
    account, character = supported_recipient()
    parsed = incoming()
    parsed.overview["settings"].pop("hideCorpTicker")
    parsed.overview["settings"]["stateColors"] = None
    parsed.layout.update(targetOrigin=None, targetOriginLocked=None, hudOffset=None)
    account.doc["bytes:ui"]["bytes:targetOriginLocked"] = stamp(0)
    out_a, out_c = apply(account, character, parsed)
    assert "bytes:hideCorpTicker" not in out_a.doc["bytes:overview"]
    assert "bytes:stateColors" not in out_a.doc["bytes:overview"]
    assert "bytes:targetOrigin" not in out_a.doc["bytes:ui"]
    assert "bytes:targetOriginLocked" not in out_a.doc["bytes:ui"]
    assert "bytes:shipuialignleftoffset" not in out_c.doc["bytes:windows"]
    assert (
        out_a.doc["bytes:ui"]["bytes:editHistory"]
        == account.doc["bytes:ui"]["bytes:editHistory"]
    )


def test_identical_collision_keeps_physical_record_and_removes_only_imported_unsaved():
    account, character = supported_recipient()
    parsed = parse_text(
        "presets:\n  - [Synthetic Fleet, [[groups, [88]], [filteredStates, [10]], [alwaysShownStates, []]]]"
    )
    saved = copy.deepcopy(account.doc["bytes:overview"]["bytes:overviewProfilePresets"])
    # Unrelated definitions/unsaved data need no interpretation.
    value(account, "overview", "overviewProfilePresets")["bytes:Opaque"] = {
        "future": [1]
    }
    value(account, "overview", "overviewProfilePresets_notSaved")["bytes:Opaque"] = {
        "future": [2]
    }
    out_a, out_c = apply(account, character, parsed)
    assert (
        value(out_a, "overview", "overviewProfilePresets")["utf8:Synthetic Fleet"]
        == saved["tuple"][1]["utf8:Synthetic Fleet"]
    )
    assert (
        out_a.doc["bytes:overview"]["bytes:overviewProfilePresets"]
        == account.doc["bytes:overview"]["bytes:overviewProfilePresets"]
    )
    unsaved = value(out_a, "overview", "overviewProfilePresets_notSaved")
    assert "utf8:Synthetic Fleet" not in unsaved
    assert unsaved["utf8:Synthetic Local"] == {
        "bytes:groups": [86],
        "bytes:filteredStates": [],
        "bytes:alwaysShownStates": [10],
    }
    assert unsaved["bytes:Opaque"] == {"future": [2]}
    assert out_c == character


@pytest.mark.parametrize("native", [False, True], ids=["full", "native"])
def test_tab_replacement_preserves_opaque_nonimported_old_tab_definition(native):
    account, character = selector_recipient() if native else supported_recipient()
    saved = value(account, "overview", "overviewProfilePresets")
    saved["utf8:Synthetic Local"]["bytes:future"] = {"bytes:opaque": [1, 2]}
    # This definition is referenced by old tabs and activeOverviewPreset, but
    # neither replacement imports it or needs to interpret its membership.
    before = copy.deepcopy((account, character))
    parsed = selector_native() if native else incoming()
    out_a, out_c = apply(account, character, parsed)
    assert (account, character) == before
    assert value(out_a, "overview", "overviewProfilePresets")[
        "utf8:Synthetic Local"
    ] == {
        "bytes:groups": [89],
        "bytes:filteredStates": [],
        "bytes:alwaysShownStates": [10],
        "bytes:future": {"bytes:opaque": [1, 2]},
    }
    for key in ("activeOverviewPreset", "overviewProfilePresets_notSaved"):
        assert (
            out_a.doc["bytes:overview"][f"bytes:{key}"]
            == account.doc["bytes:overview"][f"bytes:{key}"]
        )
    if native:
        assert out_a.doc["bytes:tabgroups"] == account.doc["bytes:tabgroups"]
    else:
        assert value(out_a, "tabgroups", "overviewTabs") == 0
    assert value(out_a, "overview", "tabsettings_new")["int:0"]["bytes:overview"] == (
        "utf8:Added" if native else "utf8:Incoming Fleet"
    )
    if native:
        assert out_c == character


@pytest.mark.parametrize("field", ["overview", "bracket"])
def test_old_tab_dangling_reference_still_refuses(field):
    account, character = supported_recipient()
    value(account, "overview", "tabsettings_new")["int:0"][f"bytes:{field}"] = (
        "utf8:Missing"
    )
    refuse(account, character, "recipient_shape", "dangling reference Missing")


def test_opaque_imported_definition_collision_still_requires_full_validation():
    account, character = supported_recipient()
    value(account, "overview", "overviewProfilePresets")["utf8:Added"] = {
        "bytes:groups": [25],
        "bytes:filteredStates": [],
        "bytes:alwaysShownStates": [],
        "bytes:future": [1],
    }
    refuse(
        account,
        character,
        "recipient_shape",
        "overviewProfilePresets Added",
        selector_native(),
    )


@pytest.mark.parametrize(
    "name",
    ["Synthetic Fleet", "DefaultPreset_SyntheticBuiltin"],
    ids=["custom", "prefix-lookalike"],
)
def test_differing_custom_collision_replaces_under_exact_jotunn_classification(name):
    account, character = supported_recipient()
    parsed = model.ParsedSetup(
        "native-yaml",
        {
            "presets": [
                {
                    "name": name,
                    "groups": [1],
                    "filteredStates": [],
                    "alwaysShownStates": [],
                }
            ]
        },
        None,
    )
    out_a, out_c = apply(account, character, parsed)
    key = ("bytes:" if name.startswith("DefaultPreset_") else "utf8:") + name
    assert value(out_a, "overview", "overviewProfilePresets")[key] == {
        "bytes:groups": [1],
        "bytes:filteredStates": [],
        "bytes:alwaysShownStates": [],
    }
    assert out_c == character


def test_prefix_lookalike_new_name_is_custom_and_identical_existing_is_preserved():
    account, character = supported_recipient()
    parsed = model.ParsedSetup(
        "native-yaml",
        {
            "presets": [
                {
                    "name": "DefaultPreset_SyntheticBuiltin",
                    "groups": [90],
                    "filteredStates": [],
                    "alwaysShownStates": [],
                }
            ]
        },
        None,
    )
    out_a, _ = apply(account, character, parsed)
    assert out_a == account
    parsed.overview["presets"][0]["name"] = "DefaultPreset_New"
    out_a, _ = apply(account, character, parsed)
    assert value(out_a, "overview", "overviewProfilePresets")["utf8:DefaultPreset_New"][
        "bytes:groups"
    ] == [90]


def test_native_filter_only_preserves_grouping_selectors_layout_and_absent_options():
    account, character = documents("recipient")
    parsed = parse_text(
        "presets:\n  - [Added, [[groups, [25, 25, 26]], [filteredStates, []], [alwaysShownStates, []]]]\nuserSettings:\n  - [useSmallColorTags, true]"
    )
    out_a, out_c = apply(account, character, parsed)
    assert out_c == character
    assert out_a.doc["bytes:tabgroups"] == account.doc["bytes:tabgroups"]
    assert out_a.doc["bytes:ui"] == account.doc["bytes:ui"]
    for key, record in account.doc["bytes:overview"].items():
        if key not in ("bytes:overviewProfilePresets", "bytes:useSmallColorTags"):
            assert out_a.doc["bytes:overview"][key] == record
    assert value(out_a, "overview", "overviewProfilePresets")["utf8:Added"][
        "bytes:groups"
    ] == [25, 25, 26]
    assert value(out_a, "overview", "useSmallColorTags") is True


def test_native_tabs_one_group_keep_all_character_geometry():
    account, character = supported_recipient()
    parsed = parse_text(
        "presets:\n  - [Added, [[groups, [25]], [filteredStates, []], [alwaysShownStates, []]]]\ntabSetup:\n  - [0, [[name, New], [overview, Added], [bracket, Added], [color, null], [tabColumns, [NAME]], [tabColumnOrder, [NAME, ICON]]]]"
    )
    assert parsed.layout is None
    out_a, out_c = apply(account, character, parsed)
    assert value(out_a, "overview", "tabsByWindowInstanceID") == [[0]]
    assert (
        value(out_a, "overview", "tabsettings_new")["int:0"]["bytes:overview"]
        == "utf8:Added"
    )
    assert out_c == character


def test_native_ambiguous_labels_require_explicit_retention_of_entire_opaque_sequence():
    account, character = supported_recipient()
    labels = [
        {
            "bytes:type": "bytes:linebreak",
            "bytes:pre": None,
            "bytes:post": None,
            "bytes:state": None,
        },
        {"future": "opaque"},
    ]
    account.doc["bytes:overview"]["bytes:shipLabels"] = stamp(labels)
    parsed = model.ParsedSetup(
        "native-yaml",
        {"settings": {"useSmallColorTags": True}},
        None,
        ambiguous_labels=True,
    )
    refuse(account, character, "ambiguous_labels", "Keep my ship labels", parsed)
    out_a, out_c = apply(account, character, parsed, keep=True)
    assert out_a.doc["bytes:overview"]["bytes:shipLabels"] == stamp(labels)
    assert out_c == character


def test_original_rich_recipient_retires_surplus_without_erasing_geometry_or_history():
    account, character = documents("recipient")
    out_a, out_c = apply(account, character)
    assert value(out_c, "windows", "openWindows")["bytes:overview_3"] is False
    assert (
        value(out_c, "windows", "windowSizesAndPositions_1")["bytes:overview_3"]
        == value(character, "windows", "windowSizesAndPositions_1")["bytes:overview_3"]
    )
    assert (
        out_c.doc["bytes:syntheticPrivate"] == character.doc["bytes:syntheticPrivate"]
    )
    assert (
        out_a.doc["bytes:overview"]["bytes:restoreData"]
        == account.doc["bytes:overview"]["bytes:restoreData"]
    )


@pytest.mark.parametrize(
    "window",
    ["overview", "overview_2", "primary_map_panel"],
    ids=["primary", "new-slot", "null-geometry"],
)
def test_every_included_recipient_window_stack_is_checked(window):
    account, character = supported_recipient()
    value(character, "windows", "stacksWindows")[f"bytes:{window}"] = "bytes:MixedStack"
    refuse(account, character, "affected_stack", window)


def test_surplus_stack_is_checked_before_retirement():
    account, character = documents("recipient")
    value(character, "windows", "stacksWindows")["bytes:overview_3"] = (
        "bytes:MixedStack"
    )
    refuse(account, character, "affected_stack", "overview_3")


def test_native_tab_change_checks_primary_stack_even_without_layout():
    account, character = supported_recipient()
    value(character, "windows", "stacksWindows")["bytes:overview"] = "bytes:MixedStack"
    parsed = incoming()
    native = model.ParsedSetup(
        "native-yaml",
        {
            "presets": parsed.overview["presets"],
            "tabs": parsed.overview["tabs"],
            "windowGroups": [[0, 1, 2, 3, 4, 5, 6, 7]],
        },
        None,
    )
    refuse(account, character, "affected_stack", "overview", native)


@pytest.mark.parametrize(
    "active", [None, "utf8:Missing", "int:0"], ids=["null", "dangling", "type"]
)
def test_unsupported_or_dangling_active_reference_refuses(active):
    account, character = supported_recipient()
    account.doc["bytes:overview"]["bytes:activeOverviewPreset"] = stamp(active)
    if active == "utf8:Missing":
        out_a, _ = apply(account, character)
        assert value(out_a, "overview", "activeOverviewPreset") == "utf8:Incoming Fleet"
    else:
        refuse(account, character, "active_reference", "activeOverviewPreset")


def test_active_reference_absence_is_not_replaced_with_first_filter():
    account, character = supported_recipient()
    del account.doc["bytes:overview"]["bytes:activeOverviewPreset"]
    out_a, _ = apply(account, character)
    assert "bytes:activeOverviewPreset" not in out_a.doc["bytes:overview"]


@pytest.mark.parametrize(
    "selector", ["overviewTabs", "overviewTabs_names"], ids=["id", "name"]
)
def test_changed_tab_structure_resets_both_selection_forms(selector):
    account, character = supported_recipient()
    account.doc["bytes:tabgroups"][f"bytes:{selector}"] = stamp(
        0 if selector == "overviewTabs" else "utf8:Synthetic local tab"
    )
    out_a, _ = apply(account, character)
    assert value(out_a, "tabgroups", "overviewTabs") == 0
    assert "bytes:overviewTabs_names" not in out_a.doc["bytes:tabgroups"]


@pytest.mark.parametrize("key", ["alwaysShow", "filterOut", "unfiltered"])
def test_known_nonnull_legacy_filter_dependencies_refuse(key):
    account, character = supported_recipient()
    account.doc["bytes:overview"][f"bytes:{key}"] = stamp([25])
    refuse(account, character, "legacy_dependency", key)


@pytest.mark.parametrize(
    "where,key,bad",
    [
        ("overview", "applyToStructures", 1),
        ("overview", "flagOrder2", [True]),
        ("overview", "stateColors", {"bad": {"tuple": [0, 0, 0, 1]}}),
        ("overview", "shipLabels", [{"bytes:type": "bytes:linebreak"}]),
        ("overview", "tabsByWindowInstanceID", [[0], [0]]),
        (
            "windows",
            "windowSizesAndPositions_1",
            {"bytes:overview": [1, 2, 3, 4, 5, 6]},
        ),
        ("windows", "openWindows", {"bytes:overview": 0}),
        ("windows", "shipuialignleftoffset", True),
        ("ui", "targetOrigin", [0.2, 0.3]),
    ],
    ids=[
        "bool",
        "ids",
        "color",
        "labels",
        "groups",
        "geometry",
        "state",
        "hud",
        "origin",
    ],
)
def test_malformed_present_owned_values_refuse_even_when_replaced(where, key, bad):
    account, character = supported_recipient()
    document = character if where == "windows" else account
    document.doc[f"bytes:{where}"][f"bytes:{key}"] = stamp(bad)
    refuse(account, character, "recipient_shape", key)


@pytest.mark.parametrize(
    "kind",
    ["section", "setting", "stamp", "window", "name", "field"],
    ids=["section", "setting", "stamp", "window", "name", "field"],
)
def test_unsupported_or_dual_aliases_and_stamp_shapes_refuse(kind):
    account, character = supported_recipient()
    overview = account.doc["bytes:overview"]
    if kind == "section":
        account.doc["utf8:overview"] = {}
    elif kind == "setting":
        overview["utf8:shipLabels"] = overview["bytes:shipLabels"]
    elif kind == "stamp":
        overview["bytes:shipLabels"] = {"tuple": [42, []]}
    elif kind == "window":
        value(character, "windows", "openWindows")["utf8:overview"] = False
    elif kind == "name":
        value(account, "overview", "overviewProfilePresets")[
            "bytes:Synthetic Local"
        ] = {}
    else:
        value(account, "overview", "shipLabels")[0]["utf8:pre"] = "utf8:contradiction"
    refuse(account, character, "recipient_shape", "recipient")


def test_target_lock_true_and_integer_one_are_supported_but_other_integers_refuse():
    account, character = supported_recipient()
    parsed = incoming()
    parsed.layout["targetOriginLocked"] = True
    out_a, _ = apply(account, character, parsed)
    assert type(value(out_a, "ui", "targetOriginLocked")) is int
    assert value(out_a, "ui", "targetOriginLocked") == 1
    account.doc["bytes:ui"]["bytes:targetOriginLocked"] = stamp(1)
    out_a, _ = apply(account, character)
    assert value(out_a, "ui", "targetOriginLocked") == 0
    account.doc["bytes:ui"]["bytes:targetOriginLocked"] = stamp(2)
    refuse(account, character, "recipient_shape", "targetOriginLocked")


def selector_native():
    names = [
        "Synthetic local tab",
        "Synthetic local second",
        "Synthetic local third",
        "Synthetic local fourth",
    ]
    return model.ParsedSetup(
        "native-yaml",
        {
            "presets": [
                {
                    "name": "Added",
                    "groups": [25],
                    "filteredStates": [],
                    "alwaysShownStates": [],
                }
            ],
            "tabs": [
                {
                    "id": i,
                    "name": name,
                    "overview": "Added",
                    "bracket": "Added",
                    "color": [0.7, 0.7, 0.7] if i == 0 else None,
                    "tabColumns": ["NAME"],
                    "tabColumnOrder": ["NAME", "ICON"],
                }
                for i, name in enumerate(names)
            ],
            "windowGroups": [[0, 1, 2, 3]],
        },
        None,
    )


def selector_recipient():
    account, character = supported_recipient()
    account.doc["bytes:tabgroups"].update(
        {
            "bytes:overviewTabs": stamp(0),
            "bytes:overviewTabs_names": stamp("utf8:Synthetic local tab"),
        }
    )
    return account, character


def test_unchanged_tab_identity_order_grouping_preserves_selectors_but_replaces_assignments():
    account, character = selector_recipient()
    out_a, out_c = apply(account, character, selector_native())
    assert out_a.doc["bytes:tabgroups"] == account.doc["bytes:tabgroups"]
    assert value(out_a, "overview", "activeOverviewPreset") == "utf8:Synthetic Local"
    assert (
        value(out_a, "overview", "tabsettings_new")["int:0"]["bytes:overview"]
        == "utf8:Added"
    )
    assert (
        value(out_a, "overview", "tabsettings_new")["int:3"]["bytes:bracket"]
        == "utf8:Added"
    )
    assert out_c == character


def order_only_case():
    """Keep recipient identities and grouping; match only its tab payloads."""
    account, character = supported_recipient()
    tabs = value(account, "overview", "tabsettings_new")
    for record in tabs.values():
        record["bytes:overview"] = "utf8:Added"
        record["bytes:bracket"] = "utf8:Added"
        record.update(
            {
                "bytes:showAll": False,
                "bytes:showNone": False,
                "bytes:showSpecials": False,
            }
        )
    tabs["int:0"].update(
        {
            "bytes:color": [0.7, 0.7, 0.7],
            "bytes:tabColumns": ["bytes:NAME"],
            "bytes:tabColumnOrder": ["bytes:NAME", "bytes:ICON"],
        }
    )
    value(account, "overview", "overviewProfilePresets")["utf8:Added"] = {
        "bytes:groups": [25],
        "bytes:filteredStates": [],
        "bytes:alwaysShownStates": [],
    }
    data = wire()
    data["overview"].update(selector_native().overview)
    # The artifact sequence and its group subsequence must agree. Dense output
    # makes this the client's sorted physical-ID order, not map encounter order.
    data["overview"]["tabs"].reverse()
    data["overview"]["windowGroups"][0].reverse()
    data["layout"]["windows"] = [
        row
        for row in data["layout"]["windows"]
        if row["key"] not in ("overview_1", "overview_2")
    ]
    return account, character, model.validate_wingman(data)


def test_no_selector_order_only_tab_replacement_updates_order_and_stamp():
    account, character, parsed = order_only_case()
    before = copy.deepcopy((account, character, parsed))
    out_a, _ = apply(account, character, parsed)
    tabs = value(out_a, "overview", "tabsettings_new")
    assert list(tabs) == ["int:0", "int:1", "int:2", "int:3"]
    assert tabs["int:0"]["bytes:name"] == "utf8:Synthetic local fourth"
    assert tabs["int:3"]["bytes:name"] == "utf8:Synthetic local tab"
    assert out_a.doc["bytes:overview"]["bytes:tabsettings_new"]["tuple"][0] == STAMP
    for key in ("tabsByWindowInstanceID", "overviewProfilePresets"):
        assert (
            out_a.doc["bytes:overview"][f"bytes:{key}"]
            == account.doc["bytes:overview"][f"bytes:{key}"]
        )
    assert value(out_a, "tabgroups", "overviewTabs") == 0
    assert (account, character, parsed) == before
    assert list(value(account, "overview", "tabsettings_new")) == [
        "int:0",
        "int:1",
        "int:2",
        "int:3",
    ]


def test_unchanged_tab_sequence_does_not_rewrite_nested_map_order_or_stamp():
    account, character, parsed = order_only_case()
    parsed.overview["tabs"].reverse()
    parsed.overview["windowGroups"][0].reverse()
    tabs = value(account, "overview", "tabsettings_new")
    tabs["int:0"] = dict(reversed(list(tabs["int:0"].items())))
    saved = value(account, "overview", "overviewProfilePresets")
    saved["utf8:Added"] = dict(reversed(list(saved["utf8:Added"].items())))
    out_a, _ = apply(account, character, parsed)
    for key in ("tabsettings_new", "overviewProfilePresets"):
        # Compare serialized insertion order as well as the original stamp.
        assert json.dumps(out_a.doc["bytes:overview"][f"bytes:{key}"]) == json.dumps(
            account.doc["bytes:overview"][f"bytes:{key}"]
        )


@pytest.mark.skipif(not CODEC.is_file(), reason="settings codec not built")
@pytest.mark.parametrize("crc", [False, True], ids=["plain", "crc"])
def test_order_only_replacement_survives_native_codec_in_sorted_physical_order(
    tmp_path, crc
):
    account, character, parsed = order_only_case()
    out_a, _ = apply(codec.Document(account.doc, crc), character, parsed)
    target = tmp_path / "order.dat"
    codec.write_document(
        target, out_a, backup=lambda path: None, exe=lambda: str(CODEC)
    )
    readback = codec.read_document(target, exe=lambda: str(CODEC))
    tabs = value(readback, "overview", "tabsettings_new")
    assert set(tabs) == {"int:0", "int:1", "int:2", "int:3"}
    # GetTabIDs:1193 sorts physical IDs; insertion order is not rendering proof.
    assert [
        tabs[key]["bytes:name"] for key in sorted(tabs, key=lambda key: int(key[4:]))
    ] == [
        "utf8:Synthetic local fourth",
        "utf8:Synthetic local third",
        "utf8:Synthetic local second",
        "utf8:Synthetic local tab",
    ]
    assert value(readback, "overview", "tabsByWindowInstanceID") == [[0, 1, 2, 3]]
    assert readback.had_crc is crc
    assert readback == out_a


@pytest.mark.parametrize("change", ["id", "order", "name", "groups", "color"])
def test_selector_invalidation_guards_each_structural_dimension(change):
    account, character = selector_recipient()
    parsed = selector_native()
    if change == "id":
        parsed.overview["tabs"][0]["id"] = 9
        parsed.overview["windowGroups"][0][0] = 9
    elif change == "order":
        parsed.overview["tabs"].reverse()
        parsed.overview["windowGroups"][0].reverse()
    elif change == "name":
        parsed.overview["tabs"][0]["name"] = "Renamed"
    elif change == "color":
        parsed.overview["tabs"][0]["color"] = None
    else:
        # Full input adds a group without changing the ordered tab identities.
        data = wire()
        data["overview"].update(parsed.overview)
        data["overview"]["windowGroups"] = [[0, 1], [2, 3]]
        data["layout"]["windows"] = [
            row for row in data["layout"]["windows"] if row["key"] != "overview_2"
        ]
        parsed = model.validate_wingman(data)
    out_a, _ = apply(account, character, parsed)
    if change == "id":
        # Artifact-local IDs are normalized back to the same physical identity.
        assert out_a.doc["bytes:tabgroups"] == account.doc["bytes:tabgroups"]
    else:
        assert value(out_a, "tabgroups", "overviewTabs") == 0
        assert "bytes:overviewTabs_names" not in out_a.doc["bytes:tabgroups"]


@pytest.mark.parametrize(
    "record",
    [stamp(True), stamp(999), stamp("utf8:0")],
    ids=["bool", "out-of-range-ordinal", "text"],
)
def test_malformed_selector_refuses_even_with_unchanged_structure(record):
    account, character = selector_recipient()
    account.doc["bytes:tabgroups"]["bytes:overviewTabs"] = record
    if type(record["tuple"][1]) is int:
        out_a, _ = apply(account, character, selector_native())
        assert value(out_a, "tabgroups", "overviewTabs") == 999
    else:
        refuse(account, character, "tab_selection", "overviewTabs", selector_native())


def test_stack_secondary_index_cannot_hide_affected_membership():
    account, character = supported_recipient()
    value(character, "windows", "preferredIdxInStack3")["bytes:HiddenStack"] = {
        "utf8:primary_map_panel": 1
    }
    refuse(account, character, "affected_stack", "primary_map_panel")


def test_imported_unsaved_malformed_value_refuses_instead_of_erasing_it():
    account, character = supported_recipient()
    value(account, "overview", "overviewProfilePresets_notSaved")[
        "utf8:Incoming Fleet"
    ] = {"future": [1]}
    refuse(account, character, "recipient_shape", "overviewProfilePresets_notSaved")


def test_known_text_aliases_and_colons_are_preserved_without_arbitrary_aliasing():
    account, character = supported_recipient()
    maps = value(character, "windows", "openWindows")
    maps["utf8:overview"] = maps.pop("bytes:overview")
    labels = value(account, "overview", "shipLabels")
    labels[0] = {
        "utf8:type": None,
        "utf8:pre": "bytes:local:prefix",
        "utf8:post": "utf8:",
        "utf8:state": 1,
    }
    parsed = incoming()
    parsed.overview["presets"][0]["name"] = "bytes:new:Ω"
    for tab in parsed.overview["tabs"]:
        if tab["overview"] == "Incoming Fleet":
            tab["overview"] = "bytes:new:Ω"
    parsed.overview["shipLabels"][0]["pre"] = "utf8:literal:Ω"
    out_a, out_c = apply(account, character, parsed)
    assert value(out_a, "overview", "overviewProfilePresets")["utf8:bytes:new:Ω"][
        "bytes:groups"
    ] == [25, 27]
    assert (
        value(out_a, "overview", "shipLabels")[0]["bytes:pre"] == "utf8:utf8:literal:Ω"
    )
    assert value(out_c, "windows", "openWindows")["utf8:overview"] is True
    assert "bytes:overview" not in value(out_c, "windows", "openWindows")


def test_native_supplied_aggregate_replaces_not_merges_and_keeps_absent_ones():
    account, character = documents("recipient")
    parsed = parse_text(
        "flagOrder: []\nstateColorsNameList: [[flag_12, darkBlue]]\nstateBlinks: [[flag_12, false]]"
    )
    out_a, out_c = apply(account, character, parsed)
    assert value(out_a, "overview", "flagOrder2") == []
    assert value(out_a, "overview", "stateColors") == {
        'json:{"tuple":["bytes:flag",12]}': {"tuple": [0.0, 0.15, 0.6, 1.0]}
    }
    assert value(out_a, "overview", "stateBlinks") == {
        'json:{"tuple":["bytes:flag",12]}': False
    }
    assert (
        out_a.doc["bytes:overview"]["bytes:backgroundOrder2"]
        == account.doc["bytes:overview"]["bytes:backgroundOrder2"]
    )
    assert out_c == character


def test_integer_zero_only_scalar_variants_can_be_replaced_with_booleans():
    account, character = supported_recipient()
    account.doc["bytes:overview"]["bytes:hideCorpTicker"] = stamp(0)
    account.doc["bytes:overview"]["bytes:useSmallText"] = stamp(0)
    out_a, _ = apply(account, character)
    assert value(out_a, "overview", "hideCorpTicker") == 0
    assert value(out_a, "overview", "useSmallText") == 0
    account.doc["bytes:overview"]["bytes:hideCorpTicker"] = stamp(1)
    refuse(account, character, "recipient_shape", "hideCorpTicker")


def test_absent_supported_window_maps_are_constructed_without_unrelated_defaults():
    account, character = supported_recipient()
    del character.doc["bytes:windows"]["bytes:openWindows"]
    del character.doc["bytes:windows"]["bytes:compactWindows"]
    out_a, out_c = apply(account, character)
    assert value(out_c, "windows", "openWindows")["bytes:droneview"] is False
    assert value(out_c, "windows", "compactWindows") == {
        "bytes:overview": True,
        "bytes:directionalScannerWindow": True,
    }
    assert "bytes:primary_map_panel" not in value(out_c, "windows", "openWindows")
    assert out_a.had_crc is False


@pytest.mark.parametrize(
    "section", ["overview", "ui", "windows"], ids=["overview", "ui", "windows"]
)
def test_malformed_section_refuses(section):
    account, character = supported_recipient()
    document = character if section == "windows" else account
    document.doc[f"bytes:{section}"] = []
    refuse(account, character, "recipient_shape", section)


def test_missing_account_topology_defaults_without_activating_cached_windows():
    account, character = supported_recipient()
    del account.doc["bytes:overview"]["bytes:tabsByWindowInstanceID"]
    out_a, out_c = apply(account, character)
    assert value(out_a, "overview", "tabsByWindowInstanceID") == [
        [0, 1, 2],
        [3, 4, 5],
        [6, 7],
    ]
    assert (
        value(out_c, "windows", "openWindows")["bytes:overview_3"]
        == value(character, "windows", "openWindows")["bytes:overview_3"]
    )


def test_full_keep_labels_retains_the_complete_existing_stamped_sequence():
    account, character = supported_recipient()
    value(account, "overview", "shipLabels").append({"future": "unknown formatting"})
    out_a, _ = apply(account, character, keep=True)
    assert (
        out_a.doc["bytes:overview"]["bytes:shipLabels"]
        == account.doc["bytes:overview"]["bytes:shipLabels"]
    )


def test_identical_repeated_groups_collision_preserves_original_encoding_and_stamp():
    account, character = supported_recipient()
    record = {
        "bytes:groups": [25, 25, 26],
        "bytes:filteredStates": [],
        "bytes:alwaysShownStates": [],
    }
    value(account, "overview", "overviewProfilePresets")["bytes:Repeated"] = record
    parsed = parse_text(
        "presets: [[Repeated, [[groups, [25, 25, 26]], [filteredStates, []], [alwaysShownStates, []]]]]"
    )
    out_a, _ = apply(account, character, parsed)
    assert out_a == account
    assert "utf8:Repeated" not in value(out_a, "overview", "overviewProfilePresets")


def test_complete_native_fixture_applies_configuration_only_with_explicit_label_retention():
    account, character = supported_recipient()
    parsed = parse_text(
        (
            Path(__file__).parent / "fixtures" / "ui_setup" / "native-complete.yaml"
        ).read_text(encoding="utf-8")
    )
    refuse(account, character, "ambiguous_labels", "Keep my ship labels", parsed)
    out_a, out_c = apply(account, character, parsed, keep=True)
    saved = value(out_a, "overview", "overviewProfilePresets")
    assert len(saved) == 45  # 42 imported plus the three different local definitions.
    assert saved["utf8:Synthetic Filter 00"] == {
        "bytes:groups": [25, 27],
        "bytes:filteredStates": [9],
        "bytes:alwaysShownStates": [12],
    }
    assert value(out_a, "overview", "tabsByWindowInstanceID") == [
        [0, 1, 2, 3, 4, 5, 6, 7]
    ]
    assert (
        out_a.doc["bytes:overview"]["bytes:shipLabels"]
        == account.doc["bytes:overview"]["bytes:shipLabels"]
    )
    assert (
        value(out_a, "overview", "tabsettings_new")["int:7"]["bytes:overview"]
        == "utf8:Synthetic Filter 08"
    )
    assert out_c == character
    rich_a, rich_c = documents("recipient")
    rich_out_a, rich_out_c = apply(rich_a, rich_c, parsed, keep=True)
    assert (
        rich_out_a.doc["bytes:overview"]["bytes:shipLabels"]
        == rich_a.doc["bytes:overview"]["bytes:shipLabels"]
    )
    for key in ("bytes:overview_1", "bytes:overview_2", "bytes:overview_3"):
        assert value(rich_out_c, "windows", "openWindows")[key] is False
    assert value(rich_out_c, "windows", "windowSizesAndPositions_1") == value(
        rich_c, "windows", "windowSizesAndPositions_1"
    )


@pytest.mark.parametrize("native", [False, True], ids=["full", "native"])
@pytest.mark.parametrize("crc", [False, True], ids=["plain", "crc"])
def test_modified_documents_round_trip_through_existing_codec_seam(
    tmp_path, monkeypatch, native, crc
):
    install_lossless_codec(monkeypatch)
    account, character = supported_recipient()
    account, character = (
        codec.Document(account.doc, crc),
        codec.Document(character.doc, crc),
    )
    parsed = selector_native() if native else incoming()
    out = apply(account, character, parsed)
    assert [document.had_crc for document in out] == [crc, crc]
    before = copy.deepcopy((account, character, parsed, out))
    for i, document in enumerate(out):
        target = tmp_path / f"out{i}.dat"
        codec.write_document(target, document, backup=lambda path: None)
        readback = codec.read_document(target)
        assert readback.had_crc is crc
        assert json.dumps(readback.doc, sort_keys=True) == json.dumps(
            document.doc, sort_keys=True
        )
    assert (account, character, parsed, out) == before


@pytest.mark.skipif(not CODEC.is_file(), reason="settings codec not built")
@pytest.mark.parametrize("crc", [False, True], ids=["plain", "crc"])
def test_modified_documents_round_trip_native_transport_when_available(tmp_path, crc):
    account, character = supported_recipient()
    account, character = (
        codec.Document(account.doc, crc),
        codec.Document(character.doc, crc),
    )
    out = apply(account, character)
    before = copy.deepcopy((account, character, out))
    for i, document in enumerate(out):
        target = tmp_path / f"native{i}.dat"
        codec.write_document(
            target, document, backup=lambda path: None, exe=lambda: str(CODEC)
        )
        readback = codec.read_document(target, exe=lambda: str(CODEC))
        assert readback.had_crc is crc
        assert json.dumps(readback.doc, sort_keys=True) == json.dumps(
            document.doc, sort_keys=True
        )
    assert (account, character, out) == before


def test_oversized_typed_tab_id_refuses_as_setup_error_without_integer_conversion_escape():
    account, character = supported_recipient()
    tabs = value(account, "overview", "tabsettings_new")
    tabs["int:" + "9" * 5000] = tabs.pop("int:0")
    refuse(account, character, "recipient_shape", "tabsettings_new")


def test_duplicate_composite_fields_refuse_instead_of_silently_last_wins():
    account, character = supported_recipient()
    account.doc["bytes:overview"]["bytes:stateColors"] = stamp(
        {
            'json:{"tuple":["bytes:flag",9],"tuple":["bytes:flag",12]}': {
                "tuple": [0.0, 0.0, 0.0, 1.0]
            }
        }
    )
    refuse(account, character, "recipient_shape", "stateColors")
