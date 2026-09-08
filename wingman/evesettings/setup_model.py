"""Pure portable setup semantics; no codec, transport, profile or UI imports.

These are Wingman v1 support limits, not EVE maxima or proof of persisted-data
behavior. Validation grants no authority to publish a profile. In particular,
physical representations remain the adapter's responsibility; current-client
compatibility evidence is recorded in docs/ui-setup-client-evidence.md.
"""

from dataclasses import dataclass
from itertools import chain
from typing import Literal

from .setup_compat import JOTUNN_FINGERPRINTS

FORMAT = "wingman-preset"
VERSION = 1
TYPE = "ui-setup"

MAX_BYTES = 2 * 1024 * 1024
MAX_DEPTH = 16
MAX_NODES = 100_000
MAX_PRESETS = 256
MAX_TABS = 8
MAX_WINDOW_GROUPS = 8
MAX_SHIP_LABELS = 64
MAX_LAYOUT_WINDOWS = 32
MAX_MEMBERSHIP_IDS = 8192
MAX_ID = 2**31 - 1
MAX_NAME_CODEPOINTS = 512
MAX_LABEL_CODEPOINTS = 4096
MAX_GEOMETRY = 32768
MIN_SIZE = 1
MIN_UNIT = 0
MAX_UNIT = 1

# Product allowlist, not a pattern for arbitrary cached window names. Active
# overview slots are derived only from validated groups, never geometry caches.
FIXED_WINDOWS = {
    "selecteditemview": "Selected item",
    "probeScannerWindow": "Probe scanner",
    "directionalScannerWindow": "Directional scanner",
    "droneview": "Drones",
    "fleetwindow": "Fleet",
    "watchlistpanel": "Watch list",
    "standaloneBookmarkWnd": "Standalone bookmarks",
    "solar_system_map_panel": "Solar-system map",
    "primary_map_panel": "Primary map",
}
WINDOW_STATES = (
    "open",
    "minimized",
    "collapsed",
    "compact",
    "locked",
    "overlay",
    "lightBackground",
)
COLUMNS = (
    "ALLIANCE",
    "ANGULARVELOCITY",
    "CORPORATION",
    "DISTANCE",
    "FACTION",
    "ICON",
    "MILITIA",
    "NAME",
    "RADIALVELOCITY",
    "SIZE",
    "TAG",
    "TRANSVERSALVELOCITY",
    "TYPE",
    "VELOCITY",
)
STATE_CATEGORIES = ("background", "flag")
BRACKET_SHOW_ALL = "_BracketFilterShowAll"
TAB_FLAGS = ("showAll", "showNone", "showSpecials")
TAB_COLUMNS = ("tabColumns", "tabColumnOrder")
LABEL_TYPES = (
    None,
    "pilot name",
    "corporation",
    "alliance",
    "ship type",
    "ship name",
    "linebreak",
)
LABEL_BOOLEAN_FIELDS = ("bold", "italic", "underline")
LABEL_NULL_FIELDS = ("fontsize", "color")
ID_SETTINGS = ("flagOrder", "flagStates", "backgroundOrder", "backgroundStates")
COLUMN_SETTINGS = ("columnOrder", "overviewColumns")
STATE_SETTINGS = ("stateColors", "stateBlinks")
BOOLEAN_SETTINGS = (
    "applyToOtherObjects",
    "applyToStructures",
    "overviewBroadcastsToTop",
    "showBiggestDamageDealers",
    "showInTargetRange",
    "showModuleHairlines",
    "showCategoryInTargetRange_6",
    "showCategoryInTargetRange_11",
    "showCategoryInTargetRange_18",
    "targetCrosshair",
    "useSmallColorTags",
    "viewTactical",
    "viewTactical_camTactical",
    "hideCorpTicker",
    "useSmallText",
)
SETTINGS = ID_SETTINGS + COLUMN_SETTINGS + STATE_SETTINGS + BOOLEAN_SETTINGS
OVERVIEW_FIELDS = ("presets", "tabs", "windowGroups", "shipLabels", "settings")

DISPLAY_NOTICE = (
    "Your resolution and UI scale stay unchanged. This layout is copied as saved; "
    "a different display size or UI scale may need manual adjustment in EVE."
)
STACK_NOTICE = "Only unstacked supported windows can be shared."
NATIVE_NOTICE = "Overview configuration only — no window layout."


class SetupError(ValueError):
    """A stable boundary code plus contextual, human-readable refusal."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ParsedSetup:
    """Owned per validation call, NOT deeply immutable review authority."""

    source_kind: Literal["wingman", "native-yaml"]
    overview: dict
    layout: dict | None
    ambiguous_labels: bool = False
    warnings: tuple[str, ...] = ()


def limits_payload() -> dict:
    """Fresh user-visible budgets, derived from the validators' sole source."""
    return {
        "max_bytes": MAX_BYTES,
        "max_depth": MAX_DEPTH,
        "max_nodes": MAX_NODES,
        "max_presets": MAX_PRESETS,
        "max_tabs": MAX_TABS,
        "max_window_groups": MAX_WINDOW_GROUPS,
        "max_ship_labels": MAX_SHIP_LABELS,
        "max_layout_windows": MAX_LAYOUT_WINDOWS,
        "max_membership_ids": MAX_MEMBERSHIP_IDS,
        "max_id": MAX_ID,
        "max_name_codepoints": MAX_NAME_CODEPOINTS,
        "max_label_codepoints": MAX_LABEL_CODEPOINTS,
        "min_coordinate": -MAX_GEOMETRY,
        "max_coordinate": MAX_GEOMETRY,
        "min_size": MIN_SIZE,
        "max_size": MAX_GEOMETRY,
        "min_target_origin": MIN_UNIT,
        "max_target_origin": MAX_UNIT,
        "min_hud_offset": -MAX_GEOMETRY,
        "max_hud_offset": MAX_GEOMETRY,
        "min_color": MIN_UNIT,
        "max_color": MAX_UNIT,
    }


def _utf8(value: str, label: str) -> bytes:
    if "\x00" in value:
        raise SetupError("invalid_text", f"{label}: NUL text is not supported.")
    try:
        return value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise SetupError(
            "invalid_text",
            f"{label}: expected valid UTF-8 text, without lone surrogates.",
        ) from error


def check_text_budget(text: str) -> None:
    """Check before decoding; a code-point precheck avoids a huge encoded copy."""
    if type(text) is not str:
        raise SetupError("invalid_text", "Shared setup text must be a string.")
    message = f"Shared setup text exceeds {MAX_BYTES} UTF-8 bytes."
    if len(text) > MAX_BYTES:
        raise SetupError("byte_limit", message)
    if len(_utf8(text, "Shared setup text")) > MAX_BYTES:
        raise SetupError("byte_limit", message)


def check_structure_budget(value: object) -> None:
    """Count containers, scalar values and mapping keys, before domain copying.

    Depth counts nested containers (the root container is depth 1). Iterator
    frames use O(depth) memory even for a wide input. Cycles hit the same limits;
    no recursive walk or deep copy runs on unchecked structures. For JSON this
    is necessarily post-decode, not a pre-allocation node guarantee.
    """
    stack = [(iter((value,)), 0)]
    nodes = 0
    while stack:
        iterator, depth = stack[-1]
        try:
            item = next(iterator)
        except StopIteration:
            stack.pop()
            continue
        nodes += 1
        if nodes > MAX_NODES:
            raise SetupError("node_limit", f"Setup exceeds {MAX_NODES} parsed nodes.")
        if type(item) in (dict, list):
            nested = depth + 1
            if nested > MAX_DEPTH:
                raise SetupError(
                    "depth_limit", f"Setup exceeds nesting depth {MAX_DEPTH}."
                )
            children = (
                chain(item.keys(), item.values()) if type(item) is dict else iter(item)
            )
            stack.append((children, nested))


def _fields(value, required, label, *, optional=()):
    if type(value) is not dict:
        raise SetupError("invalid_type", f"{label}: expected an object.")
    missing = set(required) - value.keys()
    if missing:
        raise SetupError(
            "invalid_fields", f"{label}: missing fields: {', '.join(sorted(missing))}."
        )
    if value.keys() - set(required) - set(optional):
        raise SetupError("invalid_fields", f"{label}: unsupported fields.")


def _list(value, label, *, maximum=None, minimum=0):
    if type(value) is not list:
        raise SetupError("invalid_type", f"{label}: expected a list.")
    if len(value) < minimum or (maximum is not None and len(value) > maximum):
        raise SetupError(
            "collection_limit", f"{label}: expected {minimum} to {maximum} entries."
        )
    return value


def _text(value, maximum, label, *, name=False):
    if type(value) is not str or len(value) > maximum:
        raise SetupError(
            "invalid_text",
            f"{label}: expected text of at most {maximum} Unicode code points.",
        )
    if name and not value.strip():
        raise SetupError(
            "invalid_text", f"{label}: name must not be empty or whitespace."
        )
    _utf8(value, label)
    return value


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise SetupError(
            "invalid_number",
            f"{label}: expected an integer between {low} and {high}, not a boolean.",
        )
    return value


def _boolean(value, label):
    if type(value) is not bool:
        raise SetupError(
            "invalid_type", f"{label}: expected a boolean, not an integer."
        )
    return value


def _unit(value, label):
    # Comparisons reject NaN/infinity and huge ints without float conversion or
    # rounding. Both RGB and RGBA use this supported normalized-colour domain.
    if type(value) not in (int, float) or not MIN_UNIT <= value <= MAX_UNIT:
        raise SetupError(
            "invalid_number",
            f"{label}: expected a finite number between {MIN_UNIT} and {MAX_UNIT}, not a boolean.",
        )
    return value


def _enum(value, allowed, label):
    if value not in allowed:
        raise SetupError("unsupported_variant", f"{label}: unsupported variant.")
    return value


def _unique(values, label, *, code="duplicate_id"):
    if len(set(values)) != len(values):
        raise SetupError(code, f"{label}: duplicate logical key.")


def _ids(value, label, *, maximum=MAX_MEMBERSHIP_IDS, minimum=0, unique=True):
    result = [
        _integer(item, 0, MAX_ID, label)
        for item in _list(value, label, maximum=maximum, minimum=minimum)
    ]
    if unique:
        _unique(result, label)
    return result


def _columns(value, label):
    result = [_enum(item, COLUMNS, label) for item in _list(value, label)]
    _unique(result, label)
    return result


def _units(value, size, label):
    values = _list(value, label, maximum=size, minimum=size)
    return [_unit(item, label) for item in values]


def _presets(value):
    result = []
    for item in _list(value, "Presets", maximum=MAX_PRESETS):
        _fields(
            item, ("name", "groups", "filteredStates", "alwaysShownStates"), "Preset"
        )
        result.append(
            {
                "name": _text(
                    item["name"], MAX_NAME_CODEPOINTS, "Preset name", name=True
                ),
                # ReorderPresets:279 -> ReorderList:92 sorts all three lists
                # without deduplication; state getters return lists too. Relax
                # uniqueness validation only here, retaining sequence/budgets.
                "groups": _ids(item["groups"], "Preset groups", unique=False),
                "filteredStates": _ids(
                    item["filteredStates"], "Preset filtered states", unique=False
                ),
                "alwaysShownStates": _ids(
                    item["alwaysShownStates"],
                    "Preset always-shown states",
                    unique=False,
                ),
            }
        )
    _unique([item["name"] for item in result], "Preset names", code="duplicate_name")
    return result


def _tabs(value, *, partial):
    result = []
    for item in _list(value, "Tabs", maximum=MAX_TABS, minimum=1):
        _fields(
            item,
            (
                "id",
                "name",
                "overview",
                "bracket",
                "color",
                *(() if partial else TAB_COLUMNS),
            ),
            "Tab",
            optional=TAB_FLAGS + (TAB_COLUMNS if partial else ()),
        )
        result.append(
            {
                "id": _integer(item["id"], 0, MAX_ID, "Tab ID"),
                "name": _text(item["name"], MAX_NAME_CODEPOINTS, "Tab name", name=True),
                "overview": _text(
                    item["overview"],
                    MAX_NAME_CODEPOINTS,
                    "Tab overview reference",
                    name=True,
                ),
                "bracket": None
                if item["bracket"] is None
                else _text(
                    item["bracket"],
                    MAX_NAME_CODEPOINTS,
                    "Tab bracket reference",
                    name=True,
                ),
                "color": None
                if item["color"] is None
                else _units(item["color"], 3, "Tab RGB color"),
                **{key: _columns(item[key], key) for key in TAB_COLUMNS if key in item},
                **{key: _boolean(item.get(key, False), key) for key in TAB_FLAGS},
            }
        )
    _unique([item["id"] for item in result], "Tab IDs")
    return result


def _labels(value):
    result = []
    for item in _list(value, "Ship labels", maximum=MAX_SHIP_LABELS):
        _fields(
            item,
            ("type", "pre", "post", "state"),
            "Ship label",
            optional=LABEL_BOOLEAN_FIELDS + LABEL_NULL_FIELDS,
        )
        label = {
            "type": _enum(item["type"], LABEL_TYPES, "Ship label type"),
            **{
                key: None
                if item["type"] == "linebreak" and item[key] is None
                else _text(item[key], MAX_LABEL_CODEPOINTS, f"Ship label {key}")
                for key in ("pre", "post")
            },
            "state": None
            if item["type"] == "linebreak" and item["state"] is None
            else _integer(item["state"], 0, 1, "Ship label state"),
        }
        # Optional presence is meaningful. In particular, do not fill absent
        # formatting fields or collapse repeated literal/type records.
        for key in LABEL_BOOLEAN_FIELDS:
            if key in item:
                label[key] = (
                    1
                    if key in ("bold", "italic")
                    and type(item[key]) is int
                    and item[key] == 1
                    else _boolean(item[key], f"Ship label {key}")
                )
        if "fontsize" in item:
            size = item["fontsize"]
            if size is not None and (type(size) is not int or size not in (11, 12)):
                raise SetupError(
                    "unsupported_variant",
                    "Ship label fontsize: expected 11, 12 or null.",
                )
            label["fontsize"] = size
        if "color" in item:
            label["color"] = (
                None
                if item["color"] is None
                else _units(item["color"], 3, "Ship label RGB color")
            )
        result.append(label)
    return result


def _state_records(value, field):
    result = []
    payload = "color" if field == "stateColors" else "blink"
    for item in _list(value, field):
        _fields(item, ("category", "state", payload), field)
        result.append(
            {
                "category": _enum(
                    item["category"], STATE_CATEGORIES, f"{field} category"
                ),
                "state": _integer(item["state"], 0, MAX_ID, f"{field} state"),
                payload: _units(item[payload], 4, "State RGBA color")
                if payload == "color"
                else _boolean(item[payload], "State blink"),
            }
        )
    _unique([(item["category"], item["state"]) for item in result], field)
    return result


def _settings(value, *, partial):
    _fields(value, (), "Overview settings", optional=SETTINGS)
    result = {}
    for key in SETTINGS:
        if key not in value and partial:
            continue
        item = value.get(key)
        if item is None and not partial:
            result[key] = None
        elif key in ID_SETTINGS:
            result[key] = _ids(item, key)
        elif key in COLUMN_SETTINGS:
            result[key] = _columns(item, key)
        elif key in STATE_SETTINGS:
            result[key] = _state_records(item, key)
        else:
            result[key] = _boolean(item, key)
    return result


def validate_overview(value: object, *, partial: bool) -> dict:
    """Normalize full clear intent or preserve partial/native omissions.

    Supplied partial tabs must already have groups. Native exports omit exact
    Jotunn built-in bodies; partial validation permits those external references,
    but the recipient adapter must verify saved canonical bodies before use.
    All custom dependencies and full Wingman inputs remain self-contained, apart
    from the exact bracket sentinel/null. The native parser owns grouping policy.
    """
    check_structure_budget(value)
    _fields(
        value, () if partial else OVERVIEW_FIELDS, "Overview", optional=OVERVIEW_FIELDS
    )
    if ("tabs" in value) != ("windowGroups" in value):
        raise SetupError(
            "invalid_groups", "Tabs and window groups must be supplied together."
        )
    result = {}
    if "presets" in value:
        result["presets"] = _presets(value["presets"])
    if "tabs" in value:
        result["tabs"] = _tabs(value["tabs"], partial=partial)
        names = {item["name"] for item in result.get("presets", [])}
        if partial:
            names.update(JOTUNN_FINGERPRINTS)
        for tab in result["tabs"]:
            for field in ("overview", "bracket"):
                if field == "bracket" and tab[field] in (None, BRACKET_SHOW_ALL):
                    continue
                if tab[field] not in names:
                    raise SetupError(
                        "dangling_reference",
                        f"Tab {tab['id']} {field}: missing exact-name preset definition.",
                    )
        groups = [
            _ids(group, "Window group tab IDs", maximum=MAX_TABS, minimum=1)
            for group in _list(
                value["windowGroups"],
                "Window groups",
                maximum=MAX_WINDOW_GROUPS,
                minimum=1,
            )
        ]
        assigned = [tab_id for group in groups for tab_id in group]
        _unique(assigned, "Window group tab assignments")
        if set(assigned) != {item["id"] for item in result["tabs"]}:
            raise SetupError(
                "invalid_groups",
                "Every tab must belong to exactly one nonempty window group, with no dangling tab IDs.",
            )
        sequence = [tab["id"] for tab in result["tabs"]]
        for group in groups:
            if group != [tab_id for tab_id in sequence if tab_id in group]:
                raise SetupError(
                    "invalid_order",
                    "Window group order contradicts the ordered tab sequence.",
                )
        result["windowGroups"] = groups
    if "shipLabels" in value:
        result["shipLabels"] = _labels(value["shipLabels"])
    if "settings" in value:
        result["settings"] = _settings(value["settings"], partial=partial)
    return result


def _overview_windows(overview):
    return {
        "overview" if ordinal == 0 else f"overview_{ordinal}": "Overview"
        if ordinal == 0
        else f"Overview {ordinal + 1}"
        for ordinal in range(len(overview.get("windowGroups", [])))
    }


def _geometry(value, label):
    values = _list(value, label, maximum=6, minimum=6)
    return [
        _integer(
            item,
            -MAX_GEOMETRY if i < 2 else MIN_SIZE,
            MAX_GEOMETRY,
            f"{label} entry {i + 1}",
        )
        for i, item in enumerate(values)
    ]


def validate_layout(value: object, overview: dict) -> dict:
    """Validate full slot coverage against an already validated overview.

    Missing per-window state properties clear only those overrides. Null
    geometry is allowed only for fixed slots; it never creates default overview
    geometry. Neither geometry nor HUD/origin fields are transformed.
    """
    check_structure_budget(value)
    _fields(
        value, ("windows", "targetOrigin", "targetOriginLocked", "hudOffset"), "Layout"
    )
    active = _overview_windows(overview)
    required = set(FIXED_WINDOWS) | active.keys()
    windows = []
    seen = set()
    for item in _list(value["windows"], "Layout windows", maximum=MAX_LAYOUT_WINDOWS):
        _fields(item, ("key", "geometry", "state"), "Layout window")
        key = item["key"]
        if type(key) is not str or key not in required:
            raise SetupError(
                "unsupported_window",
                "Layout window: expected a fixed supported slot or an active overview ordinal.",
            )
        if key in seen:
            raise SetupError(
                "duplicate_id", f"Layout window {key}: duplicate logical key."
            )
        seen.add(key)
        _fields(item["state"], (), f"{key} state", optional=WINDOW_STATES)
        windows.append(
            {
                "key": key,
                "geometry": None
                if item["geometry"] is None and key not in active
                else _geometry(item["geometry"], f"{key} geometry"),
                "state": {
                    field: _boolean(item["state"][field], f"{key} {field}")
                    for field in WINDOW_STATES
                    if field in item["state"]
                },
            }
        )
    if seen != required:
        raise SetupError(
            "invalid_windows",
            f"Layout is missing required window slots: {', '.join(sorted(required - seen))}.",
        )
    return {
        "windows": windows,
        "targetOrigin": None
        if value["targetOrigin"] is None
        else _units(value["targetOrigin"], 2, "Target origin"),
        "targetOriginLocked": None
        if value["targetOriginLocked"] is None
        else _boolean(value["targetOriginLocked"], "Target origin lock"),
        "hudOffset": None
        if value["hudOffset"] is None
        else _integer(value["hudOffset"], -MAX_GEOMETRY, MAX_GEOMETRY, "HUD offset"),
    }


def validate_wingman(value: object) -> ParsedSetup:
    """Validate one complete envelope and return fresh semantic dictionaries."""
    check_structure_budget(value)
    _fields(value, ("format", "version", "type", "overview", "layout"), "Setup")
    if value["format"] != FORMAT:
        raise SetupError(
            "unsupported_format", f"Unsupported setup format; expected {FORMAT}."
        )
    if type(value["version"]) is not int or value["version"] != VERSION:
        raise SetupError(
            "unsupported_version",
            f"Unsupported setup version; expected integer {VERSION}.",
        )
    if value["type"] != TYPE:
        raise SetupError(
            "unsupported_type", f"Unsupported setup type; expected {TYPE}."
        )
    overview = validate_overview(value["overview"], partial=False)
    return ParsedSetup("wingman", overview, validate_layout(value["layout"], overview))


def summarize(value: ParsedSetup) -> dict:
    """Counts and allowlisted labels only; never expose decoded documents."""
    windows = value.layout["windows"] if value.layout is not None else []
    labels = {**FIXED_WINDOWS, **_overview_windows(value.overview)}
    limitations = [STACK_NOTICE]
    if value.layout is not None:
        limitations.append(DISPLAY_NOTICE)
    if value.source_kind == "native-yaml":
        limitations.append(NATIVE_NOTICE)
    if value.ambiguous_labels:
        limitations.append(
            "Choose Keep my ship labels explicitly; the input cannot reproduce the ordered label sequence."
        )
    limitations.extend(value.warnings)
    return {
        "counts": {
            **{
                key: len(value.overview.get(key, []))
                for key in ("presets", "tabs", "windowGroups", "shipLabels")
            },
            "layoutWindows": len(windows),
        },
        "windowLabels": [labels[window["key"]] for window in windows],
        "limitations": limitations,
    }
