import copy
import json
from pathlib import Path

import pytest

from wingman.evesettings.selective import (
    copy_selected,
    groups_for_kind,
    groups_payload,
    rules_for_kind,
)

FIXTURES = Path(__file__).parent / "fixtures" / "evesettings_selective"
ACCOUNT = [
    ("overview", "Overview profiles", True),
    ("probes", "Probe formations", True),
    ("suppress", "Suppressed dialogs", True),
    ("audio", "Audio settings", True),
    ("camera_graphics", "Camera & graphics", True),
    ("market", "Market & contracts", True),
    ("slots", "Module slot layout", False),
    ("tabgroups", "Window tab groups", True),
    ("search_history", "Search history & suggestions", False),
]
CHARACTER = [
    ("windows", "Window layout", True),
    ("neocom", "Neocom sidebar", True),
    ("chat", "Chat channels", True),
    ("infopanels", "Info panels", True),
    ("dockpanels", "Docked panels", True),
    ("search_history", "Search history & suggestions", False),
]
EXPECTED_RULES = {
    "account": (
        ("overview", "sections", ("overview", "defaultoverview")),
        ("probes", "ui_prefixes", ("probescanning.",)),
        ("suppress", "sections", ("suppress",)),
        ("audio", "sections", ("audio",)),
        (
            "camera_graphics",
            "ui_prefixes",
            (
                "camera",
                "spaceMouse",
                "offsetUIwithCamera",
                "invertCameraZoom",
                "advancedCamera",
                "missilesEnabled",
                "turretsEnabled",
                "trailsEnabled",
                "effectsEnabled",
                "explosionEffectsEnabled",
                "gpuParticlesEnabled",
                "droneModelsEnabled",
                "modelSkinsInSpaceEnabled",
                "UI_ASTEROID_",
            ),
        ),
        (
            "market",
            "ui_prefixes",
            (
                "market_",
                "minEdit_market",
                "maxEdit_market",
                "quickbar",
                "contracts_search_",
                "mycontracts_",
                "pricehistorytype",
            ),
        ),
        ("slots", "ui_prefixes", ("slotOrder", "linkedWeapons_")),
        ("tabgroups", "sections", ("tabgroups",)),
        (
            "search_history",
            "ui_prefixes",
            ("editHistory", "contracts_history", "market_searchText", "assetsSearch"),
        ),
    ),
    "character": (
        ("windows", "sections", ("windows",)),
        ("neocom", "ui_prefixes", ("neocomButtonRawData",)),
        ("chat", "ui_prefixes", ("chatchannels",)),
        ("infopanels", "ui_prefixes", ("InfoPanelModes_",)),
        ("dockpanels", "sections", ("dockPanels",)),
        (
            "search_history",
            "ui_prefixes",
            ("editHistory", "contracts_history", "market_searchText", "assetsSearch"),
        ),
    ),
}


@pytest.fixture
def account_fixture():
    return json.loads((FIXTURES / "account.json").read_text(encoding="utf-8"))


@pytest.fixture
def character_fixture():
    return json.loads((FIXTURES / "character.json").read_text(encoding="utf-8"))


def _selected(kind, *, without=()):
    return [g.id for g in groups_for_kind(kind) if g.id not in without]


def _rule_cases():
    cases = []
    for kind, rules in EXPECTED_RULES.items():
        for group_id, rule_kind, names in rules:
            for name in names:
                cases.append(
                    pytest.param(
                        kind, group_id, rule_kind, name, id=f"{kind}-{group_id}-{name}"
                    )
                )
    return cases


def test_groups_have_exact_order_labels_and_defaults():
    assert [
        (g.id, g.label, g.default_on) for g in groups_for_kind("account")
    ] == ACCOUNT
    assert [
        (g.id, g.label, g.default_on) for g in groups_for_kind("character")
    ] == CHARACTER
    assert groups_payload("account") == [
        {"id": ident, "label": label, "default_on": default_on}
        for ident, label, default_on in ACCOUNT
    ]
    assert groups_payload("character") == [
        {"id": ident, "label": label, "default_on": default_on}
        for ident, label, default_on in CHARACTER
    ]


def test_defaults_copy_everything_except_slots_and_search_history(account_fixture):
    selected = [g.id for g in groups_for_kind("account") if g.default_on]
    result = copy_selected(
        account_fixture["source"],
        account_fixture["target"],
        kind="account",
        selected_groups=selected,
    )

    assert result["bytes:overview"] == account_fixture["source"]["bytes:overview"]
    assert (
        result["bytes:ui"]["bytes:cameraOffset"]
        == account_fixture["source"]["bytes:ui"]["bytes:cameraOffset"]
    )
    assert (
        result["bytes:ui"]["bytes:slotOrder"]
        == account_fixture["target"]["bytes:ui"]["bytes:slotOrder"]
    )
    assert (
        result["bytes:ui"]["bytes:editHistory"]
        == account_fixture["target"]["bytes:ui"]["bytes:editHistory"]
    )


def test_clone_source_then_restore_excluded_keeps_unmapped_source_values(
    account_fixture,
):
    result = copy_selected(
        account_fixture["source"],
        account_fixture["target"],
        kind="account",
        selected_groups=_selected("account", without={"slots"}),
    )

    assert (
        result["bytes:wingmanUnmappedSection"]
        == account_fixture["source"]["bytes:wingmanUnmappedSection"]
    )
    assert (
        result["bytes:ui"]["bytes:wingmanUnmappedUi"]
        == account_fixture["source"]["bytes:ui"]["bytes:wingmanUnmappedUi"]
    )


def test_excluding_ui_group_preserves_source_when_neither_document_has_ui():
    source = {"bytes:wingmanUnmappedSection": {"tuple": ["source"]}}
    target = {"bytes:wingmanUnmappedSection": {"tuple": ["target"]}}

    result = copy_selected(
        source,
        target,
        kind="account",
        selected_groups=_selected("account", without={"market"}),
    )

    assert result == source


def test_type_prefix_is_split_once_when_setting_name_contains_colon():
    key = "bytes:market_:nested"
    source = {"bytes:ui": {key: {"tuple": ["source"]}}}
    target = {"bytes:ui": {key: {"tuple": ["target"]}}}

    result = copy_selected(
        source,
        target,
        kind="account",
        selected_groups=_selected("account", without={"market"}),
    )

    assert result["bytes:ui"][key] == {"tuple": ["target"]}


def test_excluded_group_restores_target_keys_missing_from_source(account_fixture):
    result = copy_selected(
        account_fixture["source"],
        account_fixture["target"],
        kind="account",
        selected_groups=_selected("account", without={"slots"}),
    )

    assert (
        result["bytes:ui"]["bytes:linkedWeapons_targetOnly"]
        == account_fixture["target"]["bytes:ui"]["bytes:linkedWeapons_targetOnly"]
    )


def test_every_ported_section_and_prefix_rule_is_exact():
    assert rules_for_kind("account") == EXPECTED_RULES["account"]
    assert rules_for_kind("character") == EXPECTED_RULES["character"]


@pytest.mark.parametrize("kind,group_id,rule_kind,name", _rule_cases())
def test_every_ported_rule_restores_matching_target_values_when_excluded(
    kind, group_id, rule_kind, name
):
    value_key = f"bytes:{name}same"
    if rule_kind == "sections":
        value_key = f"bytes:{name}"
        source = {value_key: {"tuple": ["source"]}, "bytes:ui": {}}
        target = {value_key: {"tuple": ["target"]}, "bytes:ui": {}}
        result_key = value_key
    else:
        source = {"bytes:ui": {value_key: {"tuple": ["source"]}}}
        target = {"bytes:ui": {value_key: {"tuple": ["target"]}}}
        result_key = value_key

    result = copy_selected(
        source, target, kind=kind, selected_groups=_selected(kind, without={group_id})
    )
    container = result if rule_kind == "sections" else result["bytes:ui"]
    assert container[result_key] == {"tuple": ["target"]}


@pytest.mark.parametrize("kind,group_id,rule_kind,name", _rule_cases())
def test_every_ported_rule_restores_target_only_matching_keys(
    kind, group_id, rule_kind, name
):
    value_key = f"utf8:{name}targetOnly"
    if rule_kind == "sections":
        value_key = f"utf8:{name}"
        source = {"bytes:ui": {}}
        target = {value_key: {"tuple": ["target-only"]}, "bytes:ui": {}}
    else:
        source = {"bytes:ui": {}}
        target = {"bytes:ui": {value_key: {"tuple": ["target-only"]}}}

    result = copy_selected(
        source, target, kind=kind, selected_groups=_selected(kind, without={group_id})
    )
    container = result if rule_kind == "sections" else result["bytes:ui"]
    assert container[value_key] == {"tuple": ["target-only"]}


def test_account_rules_do_not_offer_character_groups(account_fixture):
    with pytest.raises(ValueError):
        copy_selected(
            account_fixture["source"],
            account_fixture["target"],
            kind="account",
            selected_groups=["windows"],
        )


def test_character_rules_do_not_offer_account_groups(character_fixture):
    with pytest.raises(ValueError):
        copy_selected(
            character_fixture["source"],
            character_fixture["target"],
            kind="character",
            selected_groups=["overview"],
        )


def test_an_overlapping_key_copies_only_when_every_matching_group_is_selected(
    account_fixture,
):
    source_value = account_fixture["source"]["bytes:ui"]["bytes:market_searchText"]
    target_value = account_fixture["target"]["bytes:ui"]["bytes:market_searchText"]
    for omitted, expected in [
        (set(), source_value),
        ({"market"}, target_value),
        ({"search_history"}, target_value),
        ({"market", "search_history"}, target_value),
    ]:
        result = copy_selected(
            account_fixture["source"],
            account_fixture["target"],
            kind="account",
            selected_groups=_selected("account", without=omitted),
        )
        assert result["bytes:ui"]["bytes:market_searchText"] == expected


def test_transform_does_not_mutate_either_input(account_fixture):
    source_before = copy.deepcopy(account_fixture["source"])
    target_before = copy.deepcopy(account_fixture["target"])
    copy_selected(
        account_fixture["source"],
        account_fixture["target"],
        kind="account",
        selected_groups=[],
    )
    assert account_fixture["source"] == source_before
    assert account_fixture["target"] == target_before


@pytest.mark.parametrize("bad", [None, ["slots", "slots"], ["windows"], [3]])
def test_group_selection_is_strict(bad, account_fixture):
    with pytest.raises(ValueError):
        copy_selected(
            account_fixture["source"],
            account_fixture["target"],
            kind="account",
            selected_groups=bad,
        )


@pytest.mark.parametrize(
    "source,target",
    [
        ([], {}),
        ({}, []),
        ({"bytes:ui": []}, {"bytes:ui": {}}),
        ({"bytes:ui": {}}, {"bytes:ui": []}),
        ({"bytes:ui": {}, "utf8:ui": {}}, {"bytes:ui": {}}),
        (
            {"bytes:ui": {"bytes:market_x": 1, "utf8:market_x": 2}},
            {"bytes:ui": {}},
        ),
    ],
)
def test_malformed_root_or_ui_is_refused_not_trimmed(source, target):
    with pytest.raises(ValueError):
        copy_selected(source, target, kind="account", selected_groups=[])
