"""Pure selective copy for decoded EVE account and character settings."""

from __future__ import annotations

import copy
from dataclasses import dataclass


@dataclass(frozen=True)
class CopyGroup:
    id: str
    label: str
    default_on: bool


@dataclass(frozen=True)
class _Rule:
    group: CopyGroup
    kind: str
    names: tuple[str, ...]


_ACCOUNT_RULES = (
    _Rule(
        CopyGroup("overview", "Overview profiles", True),
        "sections",
        ("overview", "defaultoverview"),
    ),
    _Rule(
        CopyGroup("probes", "Probe formations", True),
        "ui_prefixes",
        ("probescanning.",),
    ),
    _Rule(CopyGroup("suppress", "Suppressed dialogs", True), "sections", ("suppress",)),
    _Rule(CopyGroup("audio", "Audio settings", True), "sections", ("audio",)),
    _Rule(
        CopyGroup("camera_graphics", "Camera & graphics", True),
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
    _Rule(
        CopyGroup("market", "Market & contracts", True),
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
    _Rule(
        CopyGroup("slots", "Module slot layout", False),
        "ui_prefixes",
        ("slotOrder", "linkedWeapons_"),
    ),
    _Rule(
        CopyGroup("tabgroups", "Window tab groups", True), "sections", ("tabgroups",)
    ),
    _Rule(
        CopyGroup("search_history", "Search history & suggestions", False),
        "ui_prefixes",
        ("editHistory", "contracts_history", "market_searchText", "assetsSearch"),
    ),
)
_CHARACTER_RULES = (
    _Rule(CopyGroup("windows", "Window layout", True), "sections", ("windows",)),
    _Rule(
        CopyGroup("neocom", "Neocom sidebar", True),
        "ui_prefixes",
        ("neocomButtonRawData",),
    ),
    _Rule(CopyGroup("chat", "Chat channels", True), "ui_prefixes", ("chatchannels",)),
    _Rule(
        CopyGroup("infopanels", "Info panels", True),
        "ui_prefixes",
        ("InfoPanelModes_",),
    ),
    _Rule(CopyGroup("dockpanels", "Docked panels", True), "sections", ("dockPanels",)),
    _Rule(
        CopyGroup("search_history", "Search history & suggestions", False),
        "ui_prefixes",
        ("editHistory", "contracts_history", "market_searchText", "assetsSearch"),
    ),
)
_RULES = {"account": _ACCOUNT_RULES, "character": _CHARACTER_RULES}


def _rules(kind: str) -> tuple[_Rule, ...]:
    try:
        return _RULES[kind]
    except (KeyError, TypeError) as error:
        raise ValueError("Settings kind must be 'account' or 'character'.") from error


def groups_for_kind(kind: str) -> tuple[CopyGroup, ...]:
    return tuple(rule.group for rule in _rules(kind))


def groups_payload(kind: str) -> list[dict]:
    return [
        {"id": group.id, "label": group.label, "default_on": group.default_on}
        for group in groups_for_kind(kind)
    ]


def rules_for_kind(kind: str) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    """Return the immutable canonical matching rules for provenance tests."""
    return tuple((rule.group.id, rule.kind, rule.names) for rule in _rules(kind))


def _strip_type_prefix(key: str) -> str:
    _prefix, separator, rest = key.partition(":")
    return rest if separator else key


def _index(mapping: dict, *, context: str) -> dict[str, str]:
    index = {}
    for key in mapping:
        if not isinstance(key, str):
            raise ValueError(f"{context} contains a non-text key.")
        stripped = _strip_type_prefix(key)
        if stripped in index:
            raise ValueError(
                f"{context} contains duplicate typed keys for {stripped!r}."
            )
        index[stripped] = key
    return index


def _validate_document(
    document, *, context: str
) -> tuple[dict[str, str], dict | None, str | None]:
    if not isinstance(document, dict):
        raise ValueError(f"{context} file has an unexpected root structure.")
    sections = _index(document, context=f"{context} file")
    ui_key = sections.get("ui")
    if ui_key is None:
        return sections, None, None
    ui = document[ui_key]
    if not isinstance(ui, dict):
        raise ValueError(f"{context} file has an unexpected ui structure.")
    _index(ui, context=f"{context} ui")
    return sections, ui, ui_key


def _matches(key: str, prefixes: tuple[str, ...]) -> bool:
    stripped = _strip_type_prefix(key)
    return any(stripped.startswith(prefix) for prefix in prefixes)


def copy_selected(
    source: dict,
    target: dict,
    *,
    kind: str,
    selected_groups: list[str],
) -> dict:
    """Clone *source*, restoring every unselected group from *target*."""
    rules = _rules(kind)
    valid_ids = {rule.group.id for rule in rules}
    if (
        not isinstance(selected_groups, list)
        or any(not isinstance(group_id, str) for group_id in selected_groups)
        or len(set(selected_groups)) != len(selected_groups)
        or not set(selected_groups) <= valid_ids
    ):
        raise ValueError(
            "Selected groups must be a unique list offered for this file kind."
        )

    source_sections, _source_ui, source_ui_key = _validate_document(
        source, context="Source"
    )
    target_sections, target_ui, target_ui_key = _validate_document(
        target, context="Target"
    )
    result = copy.deepcopy(source)

    selected = set(selected_groups)
    for rule in rules:
        if rule.group.id in selected:
            continue
        if rule.kind == "sections":
            for name in rule.names:
                source_key = source_sections.get(name)
                if source_key is not None:
                    result.pop(source_key, None)
                target_key = target_sections.get(name)
                if target_key is not None:
                    result[target_key] = copy.deepcopy(target[target_key])
            continue

        target_matches = (
            [
                (key, value)
                for key, value in target_ui.items()
                if _matches(key, rule.names)
            ]
            if target_ui is not None
            else []
        )
        if source_ui_key is None and not target_matches:
            continue

        result_ui_key = source_ui_key or target_ui_key
        result_ui = result.get(result_ui_key)
        if result_ui is None:
            result_ui = {}
            result[result_ui_key] = result_ui
        for key in list(result_ui):
            if _matches(key, rule.names):
                del result_ui[key]
        for key, value in target_matches:
            result_ui[key] = copy.deepcopy(value)

    return result
