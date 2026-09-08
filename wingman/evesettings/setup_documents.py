"""Pure recipient-preserving application of the evidenced setup subset.

No exporter, classifier or publication authority lives here. Unknown selection
repairs, differing definition collisions and surplus retirement are case refusals,
not implemented features. See docs/overview-layout-sharing-reassessment.md.
"""

import copy
import json
import re

from . import codec, formations
from . import setup_model as model
from .setup_model import ParsedSetup, SetupError

_MISSING = object()
_SETTING_KEYS = {
    "flagOrder": "flagOrder2",
    "flagStates": "flagStates2",
    "backgroundOrder": "backgroundOrder2",
    "backgroundStates": "backgroundStates2",
    "columnOrder": "overviewColumnOrder",
}
_STATE_MAPS = {
    "open": "openWindows",
    "minimized": "minimizedWindows",
    "collapsed": "collapsedWindows",
    "compact": "compactWindows",
    "locked": "lockedWindows",
    "overlay": "isOverlayedWindows",
    "lightBackground": "isLightBackgroundWindows",
}
_PRESET_FIELDS = ("groups", "filteredStates", "alwaysShownStates")
_TAB_TEXT = ("name", "overview", "bracket")
_TAB_COLUMNS = ("tabColumns", "tabColumnOrder")


def _shape(label):
    raise SetupError(
        "recipient_shape", f"Unsupported recipient {label} representation."
    )


def _mapping(value, label):
    if type(value) is not dict:
        _shape(label)
    return value


def _list(value, label):
    if type(value) is not list:
        _shape(label)
    return value


def _text(value, label):
    if type(value) is not str or not value.startswith(("bytes:", "utf8:")):
        _shape(label)
    return value.split(":", 1)[1]


def _key(mapping, name, label, *, text_alias=False):
    # Codec transport support does not establish arbitrary EVE section aliases.
    candidates = [
        key for key in (f"bytes:{name}", f"utf8:{name}", name) if key in mapping
    ]
    if len(candidates) > 1 or (
        candidates
        and candidates[0] != f"bytes:{name}"
        and not (text_alias and candidates[0] == f"utf8:{name}")
    ):
        _shape(f"{label}.{name} alias")
    return candidates[0] if candidates else None


def _section(doc, name, *, required=False):
    _mapping(doc, "document")
    key = _key(doc, name, "section")
    if key is None:
        if required:
            _shape(f"missing {name} section")
        return {}
    return _mapping(doc[key], name)


def _tuple(value, size, label):
    if type(value) is not dict or set(value) != {"tuple"}:
        _shape(label)
    items = _list(value["tuple"], label)
    if len(items) != size:
        _shape(label)
    return items


def _setting(section, name):
    key = _key(section, name, "setting")
    if key is None:
        return _MISSING
    stamp, value = _tuple(section[key], 2, name)
    if type(stamp) is not str or re.fullmatch(r"long:[0-9]+", stamp) is None:
        _shape(f"{name} timestamp")
    return value


def _map_setting(section, name, *, required=False):
    value = _setting(section, name)
    if value is _MISSING:
        if required:
            _shape(f"missing {name}")
        return {}
    return _mapping(value, name)


def _put(section, name, value, stamp):
    key = f"bytes:{name}"
    if value is _MISSING:
        section.pop(key, None)
    elif key not in section or section[key]["tuple"][1] != value:
        section[key] = {"tuple": [stamp, value]}


def _fields(record, fields, label, *, optional=(), text_alias=False):
    _mapping(record, label)
    result = {}
    used = set()
    for name in (*fields, *optional):
        key = _key(record, name, label, text_alias=text_alias)
        if key is None:
            if name in fields:
                _shape(f"{label}.{name}")
        else:
            used.add(key)
            result[name] = record[key]
    if used != record.keys():
        _shape(f"{label} fields")
    return result


def _validated(fragment, label):
    try:
        return model.validate_overview(fragment, partial=True)
    except SetupError as error:
        raise SetupError(
            "recipient_shape", f"Unsupported recipient {label}: {error}"
        ) from error


def _names(records, label):
    result = {}
    for key in records:
        name = _text(key, label)
        if name in result:
            _shape(f"{label} duplicate name alias {name}")
        result[name] = key
    return result


def _definition(record, name, label):
    fields = _fields(record, _PRESET_FIELDS, label)
    return _validated({"presets": [{"name": name, **fields}]}, label)["presets"][0]


def _apply_definitions(overview, incoming, stamp):
    saved = _map_setting(overview, "overviewProfilePresets", required=True)
    names = _names(saved, "overviewProfilePresets")
    unsaved = _map_setting(overview, "overviewProfilePresets_notSaved")
    unsaved_names = _names(unsaved, "overviewProfilePresets_notSaved")
    new_saved, new_unsaved = dict(saved), dict(unsaved)
    for definition in incoming:
        name = definition["name"]
        if name in names:
            existing = _definition(
                saved[names[name]], name, f"overviewProfilePresets {name}"
            )
            if existing != definition:
                raise SetupError(
                    "definition_collision",
                    f"Definition {name!r} differs; recipient custom status is unproved.",
                )
            # Keep the entire physical record (key encoding, lists and order).
        else:
            # A local refusal for the observed namespace, NOT a classifier of
            # every built-in/custom name, and never authority to replace one.
            if name.startswith("DefaultPreset_"):
                raise SetupError(
                    "unclassified_definition",
                    f"Definition {name!r} is in an unclassified reserved-looking namespace.",
                )
            new_saved[f"utf8:{name}"] = {
                f"bytes:{key}": definition[key] for key in _PRESET_FIELDS
            }
        if name in unsaved_names:
            _definition(
                unsaved[unsaved_names[name]],
                name,
                f"overviewProfilePresets_notSaved {name}",
            )
            del new_unsaved[unsaved_names[name]]
    active = _setting(overview, "activeOverviewPreset")
    if active is not _MISSING:
        try:
            name = _text(active, "activeOverviewPreset")
        except SetupError as error:
            raise SetupError(
                "active_reference",
                "Unsupported recipient activeOverviewPreset reference.",
            ) from error
        if name not in _names(new_saved, "overviewProfilePresets"):
            raise SetupError(
                "active_reference",
                "Recipient activeOverviewPreset has a dangling named reference.",
            )
    _put(overview, "overviewProfilePresets", new_saved, stamp)
    if new_unsaved != unsaved:
        _put(overview, "overviewProfilePresets_notSaved", new_unsaved, stamp)


def _tabs(overview):
    records = _map_setting(overview, "tabsettings_new", required=True)
    tabs = []
    for key, record in records.items():
        if (
            type(key) is not str
            or len(key) > len("int:") + len(str(model.MAX_ID))
            or re.fullmatch(r"int:(0|[1-9][0-9]*)", key) is None
        ):
            _shape("tabsettings_new tab ID")
        fields = _fields(
            record, (*_TAB_TEXT, "color", *_TAB_COLUMNS), "tabsettings_new"
        )
        for field in _TAB_TEXT:
            fields[field] = _text(fields[field], f"tabsettings_new.{field}")
        for field in _TAB_COLUMNS:
            fields[field] = [
                _text(item, f"tabsettings_new.{field}")
                for item in _list(fields[field], "tabsettings_new")
            ]
        tabs.append({"id": int(key[4:]), **fields})
    saved = _map_setting(overview, "overviewProfilePresets", required=True)
    names = _names(saved, "overviewProfilePresets")
    dependencies = dict.fromkeys(
        tab[field] for tab in tabs for field in ("overview", "bracket")
    )
    definitions = []
    for name in dependencies:
        if name not in names:
            _shape(f"tabsettings_new dangling reference {name}")
        definitions.append(
            _definition(saved[names[name]], name, "tabsettings_new definition")
        )
    groups = _setting(overview, "tabsByWindowInstanceID")
    if groups is _MISSING:
        # An absent topology does not authorize deriving activity from geometry.
        _shape("missing tabsByWindowInstanceID")
    result = _validated(
        {"presets": definitions, "tabs": tabs, "windowGroups": groups},
        "tabsettings_new / tabsByWindowInstanceID",
    )
    return result["tabs"], result["windowGroups"]


def _overview_windows(groups):
    return ["overview" if i == 0 else f"overview_{i}" for i in range(len(groups))]


def _check_stacks(windows, affected):
    stacks = _map_setting(windows, "stacksWindows")
    blocked = []
    for window in sorted(affected):
        key = _key(stacks, window, "stacksWindows", text_alias=True)
        if key is not None and stacks[key] is not None:
            blocked.append(window)
    if blocked:
        raise SetupError(
            "affected_stack",
            f"Affected recipient windows have unsupported stack associations: {', '.join(blocked)}.",
        )
    # This second index must not hide a mixed stack absent from stacksWindows.
    index = _map_setting(windows, "preferredIdxInStack3")
    for stack, members in index.items():
        _mapping(members, "preferredIdxInStack3")
        for window in sorted(affected):
            if (
                _key(members, window, "preferredIdxInStack3", text_alias=True)
                is not None
            ):
                raise SetupError(
                    "affected_stack",
                    f"Affected recipient window {window} is indexed in stack {stack}.",
                )


def _check_tab_selection(tabgroups, old_tabs, old_groups, incoming):
    # Without ordinal-vs-ID authority, preserving the entire identity/order/
    # grouping signature is the only supported selector-bearing transformation.
    def signature(tabs):
        return [(tab["id"], tab["name"]) for tab in tabs]

    unchanged = (
        signature(old_tabs) == signature(incoming["tabs"])
        and old_groups == incoming["windowGroups"]
    )
    for key in ("overviewTabs", "overviewTabs_names"):
        current = _setting(tabgroups, key)
        if current is _MISSING:
            continue
        valid = type(current) is int and current in {tab["id"] for tab in old_tabs}
        if key == "overviewTabs_names":
            try:
                name = _text(current, key)
                valid = sum(tab["name"] == name for tab in old_tabs) == 1
            except SetupError:
                valid = False
        if not unchanged or not valid:
            raise SetupError(
                "tab_selection",
                f"Recipient {key} cannot be safely preserved across the requested tab IDs, names, order or grouping.",
            )


def _tab_records(tabs):
    return {
        f"int:{tab['id']}": {
            **{f"bytes:{key}": f"utf8:{tab[key]}" for key in _TAB_TEXT},
            "bytes:color": tab["color"],
            **{
                f"bytes:{key}": [f"bytes:{item}" for item in tab[key]]
                for key in _TAB_COLUMNS
            },
        }
        for tab in tabs
    }


def _labels(value):
    labels = []
    for record in _list(value, "shipLabels"):
        fields = _fields(
            record,
            ("type", "pre", "post", "state"),
            "shipLabels",
            optional=model.LABEL_BOOLEAN_FIELDS + model.LABEL_NULL_FIELDS,
            text_alias=True,
        )
        for field in ("type", "pre", "post"):
            if field != "type" or fields[field] is not None:
                fields[field] = _text(fields[field], f"shipLabels.{field}")
        labels.append(fields)
    return _validated({"shipLabels": labels}, "shipLabels")["shipLabels"]


def _label_records(labels):
    return [
        {
            f"bytes:{key}": f"utf8:{item}"
            if key in ("type", "pre", "post") and item is not None
            else item
            for key, item in record.items()
        }
        for record in labels
    ]


def _composite_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate composite-key field")
        result[key] = value
    return result


def _read_option(value, field, label):
    if field in model.COLUMN_SETTINGS:
        value = [_text(item, label) for item in _list(value, label)]
    elif field in model.STATE_SETTINGS:
        records = []
        for key, item in _mapping(value, label).items():
            if type(key) is not str or not key.startswith("json:"):
                _shape(label)
            try:
                pair = json.loads(key[5:], object_pairs_hook=_composite_object)
            except (ValueError, RecursionError) as error:
                raise SetupError(
                    "recipient_shape", f"Unsupported recipient {label} composite key."
                ) from error
            category, state = _tuple(pair, 2, label)
            # Only this inner bytes: enum shape is evidenced for composite keys.
            if category not in ("bytes:background", "bytes:flag"):
                _shape(label)
            payload = "color" if field == "stateColors" else "blink"
            records.append(
                {
                    "category": category[6:],
                    "state": state,
                    payload: _tuple(item, 4, label) if payload == "color" else item,
                }
            )
        value = records
    elif (
        field in ("hideCorpTicker", "useSmallText")
        and type(value) is int
        and value == 0
    ):
        value = False
    return _validated({"settings": {field: value}}, label)["settings"][field]


def _option_record(value, field):
    if field in model.COLUMN_SETTINGS:
        return [f"bytes:{item}" for item in value]
    if field in model.STATE_SETTINGS:
        return {
            "json:"
            + json.dumps(
                {"tuple": [f"bytes:{record['category']}", record["state"]]},
                separators=(",", ":"),
            ): {"tuple": record["color"]} if field == "stateColors" else record["blink"]
            for record in value
        }
    return value


def _apply_options(overview, settings, stamp):
    for field, incoming in settings.items():
        key = _SETTING_KEYS.get(field, field)
        current = _setting(overview, key)
        if current is not _MISSING:
            _read_option(current, field, key)
        _put(
            overview,
            key,
            _MISSING if incoming is None else _option_record(incoming, field),
            stamp,
        )


def _geometry(value, label):
    coordinates = _tuple(value, 6, label)
    for i, item in enumerate(coordinates):
        low = -model.MAX_GEOMETRY if i < 2 else model.MIN_SIZE
        if type(item) is not int or not low <= item <= model.MAX_GEOMETRY:
            _shape(label)


def _apply_window_map(windows, name, incoming, stamp, *, geometry=False):
    current = _map_setting(windows, name)
    result = dict(current)
    for window, item in incoming.items():
        key = _key(current, window, name, text_alias=True)
        if key is not None:
            if geometry:
                _geometry(current[key], name)
            elif type(current[key]) is not bool:
                _shape(f"{name}.{window}")
        if item is _MISSING:
            if key is not None:
                del result[key]
        else:
            result[key or f"bytes:{window}"] = {"tuple": item} if geometry else item
    if result != current:
        _put(windows, name, result, stamp)


def _apply_layout(ui, windows, layout, stamp):
    _apply_window_map(
        windows,
        "windowSizesAndPositions_1",
        {
            row["key"]: _MISSING if row["geometry"] is None else row["geometry"]
            for row in layout["windows"]
        },
        stamp,
        geometry=True,
    )
    for field, name in _STATE_MAPS.items():
        _apply_window_map(
            windows,
            name,
            {
                row["key"]: row["state"].get(field, _MISSING)
                for row in layout["windows"]
            },
            stamp,
        )
    origin = _setting(ui, "targetOrigin")
    if origin is not _MISSING:
        for coordinate in _tuple(origin, 2, "targetOrigin"):
            if type(coordinate) not in (int, float) or not 0 <= coordinate <= 1:
                _shape("targetOrigin")
    lock = _setting(ui, "targetOriginLocked")
    if (lock is not _MISSING and (type(lock) is not int or lock != 0)) or layout[
        "targetOriginLocked"
    ] is True:
        raise SetupError(
            "target_lock",
            "targetOriginLocked supports only the evidenced integer-zero override or absence; locked physical variants are unproved.",
        )
    offset = _setting(windows, "shipuialignleftoffset")
    if offset is not _MISSING and (
        type(offset) is not int
        or not -model.MAX_GEOMETRY <= offset <= model.MAX_GEOMETRY
    ):
        _shape("shipuialignleftoffset")
    _put(
        ui,
        "targetOrigin",
        _MISSING
        if layout["targetOrigin"] is None
        else {"tuple": layout["targetOrigin"]},
        stamp,
    )
    _put(
        ui,
        "targetOriginLocked",
        _MISSING if layout["targetOriginLocked"] is None else 0,
        stamp,
    )
    _put(
        windows,
        "shipuialignleftoffset",
        _MISSING if layout["hudOffset"] is None else layout["hudOffset"],
        stamp,
    )


def apply_setup(
    account: codec.Document,
    character: codec.Document,
    parsed: ParsedSetup,
    *,
    keep_ship_labels: bool,
    now: float,
) -> tuple[codec.Document, codec.Document]:
    """Return independent documents, or refuse without changing either input.

    Full inputs clear absent owned overrides; native omissions retain recipient
    data. Acceptance here proves only pure construction, not EVE interpretation.
    """
    if parsed.ambiguous_labels and not keep_ship_labels:
        raise SetupError(
            "ambiguous_labels",
            "Choose Keep my ship labels explicitly for ambiguous native labels.",
        )
    partial = parsed.source_kind == "native-yaml"
    if parsed.source_kind not in ("wingman", "native-yaml") or (
        partial and parsed.layout is not None
    ):
        raise SetupError(
            "unsupported_input",
            "Expected a Wingman setup or native configuration without layout.",
        )
    incoming = model.validate_overview(parsed.overview, partial=partial)
    layout = None if partial else model.validate_layout(parsed.layout, incoming)
    if (
        partial
        and "tabs" in incoming
        and incoming["windowGroups"] != [[tab["id"] for tab in incoming["tabs"]]]
    ):
        raise SetupError(
            "invalid_groups",
            "Native tabs must normalize to one primary overview group.",
        )
    out_a, out_c = copy.deepcopy((account, character))
    overview = _section(out_a.doc, "overview", required=True)
    stamp = f"long:{formations.filetime(now)}"
    for key in ("alwaysShow", "filterOut", "unfiltered"):
        current = _setting(overview, key)
        if current is not _MISSING and current is not None:
            raise SetupError(
                "legacy_dependency",
                f"Recipient {key} has an unsupported non-null filter dependency.",
            )
    if "tabs" in incoming:
        old_tabs, old_groups = _tabs(overview)
        windows = _section(out_c.doc, "windows", required=True)
        active = _overview_windows(incoming["windowGroups"])
        surplus = _overview_windows(old_groups)[len(active) :]
        affected = set(active + surplus)
        if layout is not None:
            affected.update(row["key"] for row in layout["windows"])
        _check_stacks(windows, affected)
        if surplus:
            raise SetupError(
                "surplus_overview",
                f"Surplus active recipient windows require unproved retirement: {', '.join(surplus)}.",
            )
        _check_tab_selection(
            _section(out_a.doc, "tabgroups"), old_tabs, old_groups, incoming
        )
    _apply_definitions(overview, incoming.get("presets", []), stamp)
    if "tabs" in incoming:
        _put(overview, "tabsettings_new", _tab_records(incoming["tabs"]), stamp)
        _put(overview, "tabsByWindowInstanceID", incoming["windowGroups"], stamp)
    if "shipLabels" in incoming and not keep_ship_labels:
        current = _setting(overview, "shipLabels")
        if current is not _MISSING:
            _labels(current)
        _put(overview, "shipLabels", _label_records(incoming["shipLabels"]), stamp)
    _apply_options(overview, incoming.get("settings", {}), stamp)
    if layout is not None:
        ui = _section(out_a.doc, "ui")
        _apply_layout(ui, windows, layout, stamp)
        if ui:
            out_a.doc["bytes:ui"] = ui
    return out_a, out_c
