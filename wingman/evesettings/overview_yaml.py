"""Bounded native overview compatibility, never a DAT or layout importer.

The shapes and palette are inventoried in docs/ui-setup-field-map.md. Missing
aggregates retain recipient values; supplied aggregates replace them. These are
Wingman policies, not experimentally proved EVE resets. Publication is separate
and remains gated on physical default/cache/retirement evidence.
"""

import re
from collections import Counter

import yaml
from yaml.events import (
    AliasEvent,
    CollectionEndEvent,
    CollectionStartEvent,
    DocumentStartEvent,
    ScalarEvent,
)

from . import setup_model as model
from .setup_model import ParsedSetup, SetupError

# Only these DAT-independent native fields were evidenced. In particular the
# model's other scalar settings are NOT proof of native userSettings support.
NATIVE_FIELDS = frozenset(
    model.ID_SETTINGS
    + model.COLUMN_SETTINGS
    + (
        "presets",
        "tabSetup",
        "shipLabels",
        "shipLabelOrder",
        "stateBlinks",
        "stateColorsNameList",
        "userSettings",
    )
)
_USER_SETTINGS = ("useSmallColorTags",)
_PALETTE = {
    "black": (0.0, 0.0, 0.0, 1.0),
    "blue": (0.2, 0.5, 1.0, 1.0),
    "darkBlue": (0.0, 0.15, 0.6, 1.0),
    "green": (0.1, 0.6, 0.1, 1.0),
    "orange": (1.0, 0.35, 0.0, 1.0),
    "red": (0.75, 0.0, 0.0, 1.0),
    "turquoise": (0.0, 0.63, 0.57, 1.0),
    "white": (0.7, 0.7, 0.7, 1.0),
    "yellow": (1.0, 0.7, 0.0, 1.0),
}
_BASIC_TAGS = frozenset(
    "tag:yaml.org,2002:" + name
    for name in ("map", "seq", "str", "int", "float", "bool", "null")
)


class _NativeLoader(yaml.SafeLoader):
    def construct_object(self, node, deep=False):
        # Implicit timestamp/merge types also fall outside the native contract;
        # never invoke even SafeLoader's additional constructors for those.
        if node.tag not in _BASIC_TAGS:
            raise SetupError("unsupported_yaml", "Unsupported native YAML type.")
        return super().construct_object(node, deep=deep)

    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if type(key) is not str:
                raise SetupError("invalid_type", "YAML mapping keys must be text.")
            if key in result:
                raise SetupError("duplicate_field", "Duplicate YAML mapping key.")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def _preflight(text):
    """Streaming events: reject before composing nodes or constructing values.

    Match the model's counting: containers, scalar values and mapping keys are
    nodes; only containers add depth. Aliases are refused, not expanded/count-
    estimated. No event list or document tree is retained during this pass.
    """
    nodes = depth = documents = 0
    events = yaml.parse(text, Loader=yaml.SafeLoader)
    try:
        for event in events:
            if (
                isinstance(event, AliasEvent)
                or getattr(event, "anchor", None) is not None
                or getattr(event, "tag", None) is not None
            ):
                raise SetupError(
                    "unsupported_yaml",
                    "Native YAML tags, anchors and aliases are not supported.",
                )
            if isinstance(event, DocumentStartEvent):
                documents += 1
                if documents > 1:
                    raise SetupError(
                        "unsupported_yaml", "Expected one native YAML document."
                    )
            if isinstance(event, (CollectionStartEvent, ScalarEvent)):
                nodes += 1
                if nodes > model.MAX_NODES:
                    raise SetupError(
                        "node_limit", f"Setup exceeds {model.MAX_NODES} parsed nodes."
                    )
            if isinstance(event, CollectionStartEvent):
                depth += 1
                if depth > model.MAX_DEPTH:
                    raise SetupError(
                        "depth_limit", f"Setup exceeds nesting depth {model.MAX_DEPTH}."
                    )
            elif isinstance(event, CollectionEndEvent):
                depth -= 1
    finally:
        events.close()


def _list(value, label):
    if type(value) is not list:
        raise SetupError("invalid_type", f"{label}: expected a native list.")
    return value


def _pair(value, label):
    if len(_list(value, label)) != 2:
        raise SetupError("invalid_type", f"{label}: expected a two-entry native pair.")
    return value


def _keyed_pairs(value, label, *, key_type=str):
    result = {}
    for item in _list(value, label):
        key, content = _pair(item, label)
        if type(key) is not key_type:
            raise SetupError("invalid_type", f"{label}: unsupported native key type.")
        if key in result:
            raise SetupError("duplicate_field", f"{label}: duplicate native pair key.")
        result[key] = content
    return result


def _record(value, label, allowed):
    result = _keyed_pairs(value, label)
    if result.keys() - set(allowed):
        raise SetupError("invalid_fields", f"{label}: unsupported native fields.")
    return result


def _state_records(value, *, colors):
    field = "stateColorsNameList" if colors else "stateBlinks"
    result = []
    for key, content in _keyed_pairs(value, field).items():
        match = re.fullmatch(r"(background|flag)_(0|[1-9][0-9]{0,9})", key)
        if match is None:
            raise SetupError(
                "unsupported_variant",
                f"{field}: expected background_<id> or flag_<id> with a canonical decimal ID.",
            )
        if colors:
            if type(content) is not str or content not in _PALETTE:
                raise SetupError(
                    "unsupported_variant", "Unsupported native EVE palette colour name."
                )
            content = list(_PALETTE[content])
        result.append(
            {
                "category": match[1],
                "state": int(match[2]),
                "color" if colors else "blink": content,
            }
        )
    return result


def _labels(value, order):
    labels = []
    for item in _list(value, "Ship labels"):
        kind, content = _pair(item, "Ship label")
        label = _record(
            content,
            "Ship label",
            (
                "type",
                "pre",
                "post",
                "state",
                *model.LABEL_BOOLEAN_FIELDS,
                *model.LABEL_NULL_FIELDS,
            ),
        )
        if (
            "type" not in label
            or kind not in model.LABEL_TYPES
            or kind != label["type"]
        ):
            raise SetupError(
                "unsupported_variant", "Ship label outer and record types must agree."
            )
        labels.append(label)
    order = _list(order, "Ship label order")
    if any(kind not in model.LABEL_TYPES for kind in order):
        raise SetupError("unsupported_variant", "Unsupported ship label order type.")
    counts = Counter(label["type"] for label in labels)
    if Counter(order) != counts:
        raise SetupError(
            "invalid_order", "Ship label order must cover exactly the supplied records."
        )
    ambiguous = any(count > 1 for count in counts.values())
    # For duplicates, even a stable sort invents a decorator-slot assignment.
    # Preserve the supplied records verbatim for review and require retention.
    if not ambiguous:
        by_type = {label["type"]: label for label in labels}
        labels = [by_type[kind] for kind in order]
    return labels, ambiguous


def normalize(value: object) -> ParsedSetup:
    """Normalize decoded native data; callers check text and structure budgets."""
    if type(value) is not dict:
        raise SetupError("invalid_type", "Native overview YAML must be an object.")
    if not value or value.keys() - NATIVE_FIELDS:
        raise SetupError(
            "unsupported_input",
            "Unsupported native overview fields. Wingman envelopes require strict setup JSON.",
        )
    overview = {}
    if "presets" in value:
        overview["presets"] = [
            {
                "name": name,
                **_record(
                    content, "Preset", ("groups", "filteredStates", "alwaysShownStates")
                ),
            }
            for name, content in _keyed_pairs(value["presets"], "Presets").items()
        ]
    if "tabSetup" in value:
        tabs = _keyed_pairs(value["tabSetup"], "Tabs", key_type=int)
        overview["tabs"] = [
            {
                "id": tab_id,
                **_record(
                    content,
                    "Tab",
                    (
                        "name",
                        "overview",
                        "bracket",
                        "color",
                        "tabColumns",
                        "tabColumnOrder",
                    ),
                ),
            }
            for tab_id, content in tabs.items()
        ]
        overview["windowGroups"] = [list(tabs)]
    if ("shipLabels" in value) != ("shipLabelOrder" in value):
        raise SetupError(
            "invalid_order",
            "Native ship labels and their order must be supplied together.",
        )
    ambiguous = False
    if "shipLabels" in value:
        overview["shipLabels"], ambiguous = _labels(
            value["shipLabels"], value["shipLabelOrder"]
        )
    settings = {
        key: value[key]
        for key in model.ID_SETTINGS + model.COLUMN_SETTINGS
        if key in value
    }
    if "stateColorsNameList" in value:
        settings["stateColors"] = _state_records(
            value["stateColorsNameList"], colors=True
        )
    if "stateBlinks" in value:
        settings["stateBlinks"] = _state_records(value["stateBlinks"], colors=False)
    if "userSettings" in value:
        settings.update(_record(value["userSettings"], "User settings", _USER_SETTINGS))
    if settings or "userSettings" in value:
        overview["settings"] = settings
    # The model owns semantic/null/optional rules and reference closure. No
    # external sentinel has been proved; never borrow a recipient definition.
    overview = model.validate_overview(overview, partial=True)
    warnings = (
        "Absent native options retain recipient values; supplied aggregates replace them.",
    )
    if "tabs" in overview:
        warnings += (
            "Supplied native tabs become one primary overview group, without imported geometry.",
        )
    return ParsedSetup("native-yaml", overview, None, ambiguous, warnings)


def parse_text(text: str) -> ParsedSetup:
    """Admit only the bounded native schema; never accept a Wingman envelope."""
    model.check_text_budget(text)
    try:
        _preflight(text)
        loader = _NativeLoader(text)
        try:
            value = loader.get_single_data()
        finally:
            loader.dispose()
    except SetupError:
        raise
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        location = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        # Parser snippets may contain user-authored names/markup. Keep useful
        # position context without echoing an arbitrary excerpt into the UI.
        raise SetupError("invalid_yaml", f"Invalid native YAML{location}.") from error
    except (ValueError, OverflowError) as error:
        raise SetupError(
            "invalid_yaml", "Unsupported native YAML scalar value."
        ) from error
    model.check_structure_budget(value)
    return normalize(value)
