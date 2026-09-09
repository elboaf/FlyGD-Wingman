"""Pure projection/application of the supported V24.01 overview/layout subset.

No I/O, profile identity, publication authority or runtime client dependency.
Physical ownership and source references: docs/ui-setup-client-evidence.md.
"""

import copy
import hashlib
import json
import re

from . import codec, formations
from . import setup_model as model
from .setup_compat import (
    ALL_COLUMNS,
    CLIENT_TAB_SLOTS,
    DEFAULT_COLUMNS,
    JOTUNN_FINGERPRINTS,
)
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
_TAB_COLUMNS = model.TAB_COLUMNS
_UNSAVED_KEYS = ("overviewProfilePresets_notSaved", "overviewProfilePresets_notSaved2")


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


def _same_representation(left, right):
    # JSON comparison distinguishes bool/int and numeric representations while
    # remaining insensitive to dictionary insertion order. In particular, True
    # must not keep a label's integer-one formatting override from being written.
    return json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)


def _put(section, name, value, stamp, *, exact_types=False):
    key = f"bytes:{name}"
    if value is _MISSING:
        section.pop(key, None)
    elif (
        key not in section
        or section[key]["tuple"][1] != value
        or (exact_types and not _same_representation(section[key]["tuple"][1], value))
    ):
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
    fields = _fields(
        record, ("groups", "filteredStates"), label, optional=("alwaysShownStates",)
    )
    # GetAlwaysShownStates defaults only omission, not invalid present values.
    # Keep this DAT-only; evidence: docs/reference/setup-preset-compatibility.md.
    fields.setdefault("alwaysShownStates", [])
    return _validated({"presets": [{"name": name, **fields}]}, label)["presets"][0]


def protected_definition_names(account_doc: dict) -> frozenset[str]:
    """Exact stored-name domain in the supported public Jotunn context.

    overviewID is intentionally not consulted: ordinary edits null it, and it
    is not the active catalogue selector (DefaultOverviews.__init__:11).
    """
    context = _setting(_section(account_doc, "defaultoverview"), "defaultOverviewID")
    if (
        context is _MISSING
        or context is None
        or _text(context, "defaultOverviewID") != "jotunn_default"
    ):
        raise SetupError(
            "default_context",
            "Setup sharing requires the recognized jotunn_default overview context.",
        )
    return frozenset(JOTUNN_FINGERPRINTS)


def _canonical(definition):
    name = definition["name"]
    body = {key: definition[key] for key in _PRESET_FIELDS}
    fingerprint = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if fingerprint != JOTUNN_FINGERPRINTS[name]:
        raise SetupError(
            "protected_definition",
            f"Protected definition {name!r} is not the canonical public Jotunn definition.",
        )


def _effective_unsaved(overview):
    # Present empty _notSaved2 wins; never union the two generations.
    key = (
        _UNSAVED_KEYS[1]
        if _setting(overview, _UNSAVED_KEYS[1]) is not _MISSING
        else _UNSAVED_KEYS[0]
    )
    return _map_setting(overview, key)


def _apply_definitions(overview, incoming, protected, stamp):
    saved = _map_setting(overview, "overviewProfilePresets", required=True)
    names = _names(saved, "overviewProfilePresets")
    definitions = incoming.get("presets", [])
    imported_names = {definition["name"] for definition in definitions}
    external_names = _tab_dependencies(incoming.get("tabs", [])).keys() - imported_names
    # Full validation requires closure; only native exact Jotunn dependencies
    # can reach here without bodies. Hashes verify saved data, never reconstruct it.
    for name in sorted(external_names):
        if name not in names:
            raise SetupError(
                "protected_definition",
                f"Missing saved canonical protected dependency {name!r}.",
            )
        _canonical(
            _definition(saved[names[name]], name, f"overviewProfilePresets {name}")
        )
    imported_names.update(external_names)
    new_saved = dict(saved)
    for definition in definitions:
        name = definition["name"]
        if name in protected:
            _canonical(definition)
        existing = None
        if name in names:
            existing = _definition(
                saved[names[name]], name, f"overviewProfilePresets {name}"
            )
            if name in protected:
                _canonical(existing)
        if existing != definition:
            new_saved[names.get(name, f"utf8:{name}")] = {
                f"bytes:{key}": definition[key] for key in _PRESET_FIELDS
            }
    _put(overview, "overviewProfilePresets", new_saved, stamp)
    for key in _UNSAVED_KEYS:
        unsaved = _map_setting(overview, key)
        unsaved_names = _names(unsaved, key)
        result = dict(unsaved)
        # Native external defaults count as imported too: a retained effective
        # override would silently replace the canonical body the tab requested.
        for name in sorted(imported_names):
            if name in unsaved_names:
                _definition(unsaved[unsaved_names[name]], name, f"{key} {name}")
                del result[unsaved_names[name]]
        if result != unsaved:
            _put(overview, key, result, stamp)


def _repair_active(overview, incoming, stamp):
    active = _setting(overview, "activeOverviewPreset")
    if active is _MISSING:
        return
    try:
        name = _text(active, "activeOverviewPreset")
    except SetupError as error:
        raise SetupError(
            "active_reference", "Unsupported recipient activeOverviewPreset reference."
        ) from error
    names = _names(
        _map_setting(overview, "overviewProfilePresets", required=True),
        "overviewProfilePresets",
    )
    names.update(_names(_effective_unsaved(overview), "unsaved presets"))
    if name in names:
        return
    if "tabs" not in incoming:
        raise SetupError(
            "active_reference",
            "Recipient activeOverviewPreset has a dangling named reference.",
        )
    # The reset selects the primary group's first displayed tab, not an
    # arbitrary definition-list entry. Other groups retain their assignments.
    primary = incoming["windowGroups"][0][0]
    selected = next(tab for tab in incoming["tabs"] if tab["id"] == primary)
    _put(overview, "activeOverviewPreset", f"utf8:{selected['overview']}", stamp)


def _tab_dependencies(tabs):
    return dict.fromkeys(
        tab[field]
        for tab in tabs
        for field in ("overview", "bracket")
        if field != "bracket" or tab[field] not in (None, model.BRACKET_SHOW_ALL)
    )


def _tabs(overview, *, materialize=False):
    records = _map_setting(overview, "tabsettings_new", required=True)
    tabs = []
    for key, record in records.items():
        if (
            type(key) is not str
            or len(key) > len("int:") + len(str(CLIENT_TAB_SLOTS - 1))
            or re.fullmatch(r"int:(0|[1-9][0-9]*)", key) is None
            or int(key[4:]) >= CLIENT_TAB_SLOTS
        ):
            _shape(
                f"tabsettings_new tab ID (supported physical slots 0..{CLIENT_TAB_SLOTS - 1})"
            )
        fields = _fields(
            record,
            ("name", "overview"),
            "tabsettings_new",
            optional=("bracket", "color", *_TAB_COLUMNS, *model.TAB_FLAGS),
        )
        fields.setdefault("bracket", None)
        fields.setdefault("color", None)
        for field in _TAB_TEXT:
            if field != "bracket" or fields[field] is not None:
                fields[field] = _text(fields[field], f"tabsettings_new.{field}")
        for field in _TAB_COLUMNS:
            if field not in fields:
                if not materialize:
                    continue
                columns = (
                    _setting(overview, "overviewColumns")
                    if field == "tabColumns"
                    else _MISSING
                )
                fields[field] = (
                    [
                        f"bytes:{item}"
                        for item in (
                            DEFAULT_COLUMNS if field == "tabColumns" else ALL_COLUMNS
                        )
                    ]
                    if columns is _MISSING
                    else columns
                )
            fields[field] = [
                _text(item, f"tabsettings_new.{field}")
                for item in _list(fields[field], "tabsettings_new")
            ]
        tabs.append({"id": int(key[4:]), **fields})
    tabs.sort(key=lambda tab: tab["id"])
    saved = _map_setting(overview, "overviewProfilePresets", required=True)
    names = _names(saved, "overviewProfilePresets")
    names.update(_names(_effective_unsaved(overview), "unsaved presets"))
    definitions = []
    for name in _tab_dependencies(tabs):
        if name not in names:
            _shape(f"tabsettings_new dangling reference {name}")
        # Old topology needs only reference existence. Never interpret unrelated
        # recipient definition bodies just to replace their former tabs.
        definitions.append({"name": name, **{field: [] for field in _PRESET_FIELDS}})
    groups = _setting(overview, "tabsByWindowInstanceID")
    if groups is _MISSING:
        groups = [[tab["id"] for tab in tabs]]
    else:
        groups = _list(groups, "tabsByWindowInstanceID")
        for group in groups:
            if any(
                type(item) is not int for item in _list(group, "tabsByWindowInstanceID")
            ):
                _shape("tabsByWindowInstanceID IDs")
        groups = [sorted(group) for group in groups]
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


def _reset_tab_selection(tabgroups, old_tabs, old_groups, incoming, stamp):
    def signature(tabs):
        return [(tab["id"], tab["name"], tab["color"]) for tab in tabs]

    for key in ("overviewTabs", "overviewTabs_names"):
        current = _setting(tabgroups, key)
        if current is _MISSING:
            continue
        valid = type(current) is int and current >= 0
        if key == "overviewTabs_names":
            valid = type(current) is str and current.startswith(("bytes:", "utf8:"))
        if not valid:
            raise SetupError(
                "tab_selection", f"Unsupported recipient {key} representation."
            )
    if (
        signature(old_tabs) != signature(incoming["tabs"])
        or old_groups != incoming["windowGroups"]
    ):
        # _names has precedence and may contain markup. The numeric value is
        # an ordinal, NOT a physical tab ID. Zero selects first enabled tab.
        _put(tabgroups, "overviewTabs_names", _MISSING, stamp)
        _put(tabgroups, "overviewTabs", 0, stamp)


def _physical_tabs(incoming, old_tabs):
    """Dense client IDs; native omitted columns retain the destination slot."""
    mapping = {tab["id"]: i for i, tab in enumerate(incoming["tabs"])}
    old = {tab["id"]: tab for tab in old_tabs}
    result = []
    for tab in incoming["tabs"]:
        tab_id = mapping[tab["id"]]
        columns = {
            key: old[tab_id][key]
            for key in _TAB_COLUMNS
            if tab_id in old and key in old[tab_id] and key not in tab
        }
        result.append({**columns, **tab, "id": tab_id})
    incoming["tabs"] = result
    incoming["windowGroups"] = [
        [mapping[tab_id] for tab_id in group] for group in incoming["windowGroups"]
    ]


def _invalidate_headers(ui, tab_ids, stamp):
    for name in ("SortHeadersSettings2", "SortHeadersSizes"):
        current = _map_setting(ui, name)
        result = dict(current)
        for key in current:
            if type(key) is not str or not key.startswith("json:"):
                continue
            try:
                record = json.loads(key[5:], object_pairs_hook=_composite_object)
            except (ValueError, RecursionError) as error:
                raise SetupError(
                    "recipient_shape", f"Unsupported recipient {name} composite key."
                ) from error
            if (
                type(record) is not dict
                or set(record) != {"tuple"}
                or type(record["tuple"]) is not list
            ):
                continue
            pair = record["tuple"]
            if (
                len(pair) == 2
                and pair[0] in ("bytes:overviewScroll2", "utf8:overviewScroll2")
                and type(pair[1]) is int
                and pair[1] in tab_ids
            ):
                del result[key]
        if result != current:
            _put(ui, name, result, stamp)


def _tab_records(tabs):
    return {
        f"int:{tab['id']}": {
            **{
                f"bytes:{key}": None if tab[key] is None else f"utf8:{tab[key]}"
                for key in _TAB_TEXT
            },
            **{f"bytes:{key}": tab[key] for key in model.TAB_FLAGS},
            "bytes:color": tab["color"],
            **{
                f"bytes:{key}": [f"bytes:{item}" for item in tab[key]]
                for key in _TAB_COLUMNS
                if key in tab
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
            if fields[field] is not None:
                fields[field] = _text(fields[field], f"shipLabels.{field}")
        # Client formatting proves these exact integer flags, not arbitrary
        # truthiness. Preserve existing bold/italic 1 and optional absence.
        # Evidence: docs/reference/setup-preset-compatibility.md.
        for field in model.LABEL_BOOLEAN_FIELDS:
            item = fields.get(field)
            if type(item) is int:
                if item == 0:
                    fields[field] = False
                elif field == "underline" and item == 1:
                    fields[field] = True
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
    if lock is not _MISSING and (type(lock) is not int or lock not in (0, 1)):
        _shape("targetOriginLocked")
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
        _MISSING
        if layout["targetOriginLocked"] is None
        else int(layout["targetOriginLocked"]),
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
    protected = protected_definition_names(account.doc)
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
        _physical_tabs(incoming, old_tabs)
        windows = _section(out_c.doc, "windows", required=True)
        active = _overview_windows(incoming["windowGroups"])
        surplus = _overview_windows(old_groups)[len(active) :]
        affected = set(active + surplus)
        if layout is not None:
            affected.update(row["key"] for row in layout["windows"])
        _check_stacks(windows, affected)
        tabgroups = _section(out_a.doc, "tabgroups")
        _reset_tab_selection(tabgroups, old_tabs, old_groups, incoming, stamp)
        if tabgroups:
            out_a.doc["bytes:tabgroups"] = tabgroups
        _invalidate_headers(
            _section(out_c.doc, "ui"), {tab["id"] for tab in incoming["tabs"]}, stamp
        )
        _apply_window_map(
            windows, "openWindows", {window: False for window in surplus}, stamp
        )
    _apply_definitions(overview, incoming, protected, stamp)
    _repair_active(overview, incoming, stamp)
    if "tabs" in incoming:
        _put(overview, "tabsettings_new", _tab_records(incoming["tabs"]), stamp)
        _put(overview, "tabsByWindowInstanceID", incoming["windowGroups"], stamp)
    if "shipLabels" in incoming and not keep_ship_labels:
        current = _setting(overview, "shipLabels")
        labels = _labels(current) if current is not _MISSING else _MISSING
        if labels is _MISSING or not _same_representation(
            labels, incoming["shipLabels"]
        ):
            _put(
                overview,
                "shipLabels",
                _label_records(incoming["shipLabels"]),
                stamp,
                exact_types=True,
            )
    _apply_options(overview, incoming.get("settings", {}), stamp)
    if layout is not None:
        ui = _section(out_a.doc, "ui")
        _apply_layout(ui, windows, layout, stamp)
        if ui:
            out_a.doc["bytes:ui"] = ui
    return out_a, out_c


def _export_definitions(overview, tabs, protected):
    saved = _map_setting(overview, "overviewProfilePresets", required=True)
    names = _names(saved, "overviewProfilePresets")
    unsaved = _effective_unsaved(overview)
    unsaved_names = _names(unsaved, "unsaved presets")
    selected = dict.fromkeys(name for name in names if name not in protected)
    selected.update(_tab_dependencies(tabs))
    definitions = []
    overrides = 0
    for name in selected:
        if name in protected:
            if name not in names:
                raise SetupError(
                    "protected_definition",
                    f"Missing saved canonical protected dependency {name!r}.",
                )
            _canonical(
                _definition(saved[names[name]], name, f"overviewProfilePresets {name}")
            )
        if name in unsaved_names:
            record = unsaved[unsaved_names[name]]
            overrides += 1
        elif name in names:
            record = saved[names[name]]
        else:
            _shape(f"missing definition {name}")
        definition = _definition(record, name, f"effective definition {name}")
        if name in protected:
            _canonical(definition)
        definitions.append(definition)
    return definitions, overrides


def _export_layout(account, character, groups):
    windows = _section(character, "windows", required=True)
    keys = [*_overview_windows(groups), *model.FIXED_WINDOWS]
    _check_stacks(windows, set(keys))
    geometry = _map_setting(windows, "windowSizesAndPositions_1")
    states = {field: _map_setting(windows, name) for field, name in _STATE_MAPS.items()}
    rows = []
    for window in keys:
        key = _key(geometry, window, "windowSizesAndPositions_1", text_alias=True)
        position = None
        if key is not None:
            _geometry(geometry[key], window)
            position = _tuple(geometry[key], 6, window)
        state = {}
        for field, records in states.items():
            key = _key(records, window, _STATE_MAPS[field], text_alias=True)
            if key is not None:
                state[field] = records[key]
        rows.append({"key": window, "geometry": position, "state": state})
    ui = _section(account, "ui")
    origin = _setting(ui, "targetOrigin")
    lock = _setting(ui, "targetOriginLocked")
    if lock is not _MISSING and (type(lock) is not int or lock not in (0, 1)):
        _shape("targetOriginLocked")
    offset = _setting(windows, "shipuialignleftoffset")
    return {
        "windows": rows,
        "targetOrigin": None
        if origin is _MISSING
        else _tuple(origin, 2, "targetOrigin"),
        "targetOriginLocked": None if lock is _MISSING else bool(lock),
        "hudOffset": None if offset is _MISSING else offset,
    }


def export_setup(
    account: codec.Document, character: codec.Document
) -> tuple[dict, tuple[str, ...]]:
    """Project only the allowlisted effective snapshot, without touching inputs.

    All custom definitions and named tab dependencies are exported; orphan
    unsaved/history/default metadata and codec/source identity never travel.
    EVE-closed and confirmed-pair checks belong to the calling controller.
    """
    try:
        protected = protected_definition_names(account.doc)
        overview = _section(account.doc, "overview", required=True)
        for key in ("alwaysShow", "filterOut", "unfiltered"):
            current = _setting(overview, key)
            if current is not _MISSING and current is not None:
                raise SetupError(
                    "legacy_dependency",
                    f"Source {key} has an unsupported non-null filter dependency.",
                )
        tabs, groups = _tabs(overview, materialize=True)
        definitions, overrides = _export_definitions(overview, tabs, protected)
        labels = _setting(overview, "shipLabels")
        if labels is _MISSING:
            _shape("missing shipLabels; default records are not synthesized")
        settings = {}
        for field in model.SETTINGS:
            key = _SETTING_KEYS.get(field, field)
            current = _setting(overview, key)
            settings[field] = (
                None if current is _MISSING else _read_option(current, field, key)
            )
        parsed = model.validate_wingman(
            {
                "format": model.FORMAT,
                "version": model.VERSION,
                "type": model.TYPE,
                "overview": {
                    "presets": definitions,
                    "tabs": tabs,
                    "windowGroups": groups,
                    "shipLabels": _labels(labels),
                    "settings": settings,
                },
                "layout": _export_layout(account.doc, character.doc, groups),
            }
        )
        envelope = {
            "format": model.FORMAT,
            "version": model.VERSION,
            "type": model.TYPE,
            "overview": parsed.overview,
            "layout": parsed.layout,
        }
        model.check_structure_budget(envelope)
        model.check_text_budget(
            json.dumps(
                envelope, ensure_ascii=False, allow_nan=False, separators=(",", ":")
            )
        )
    except SetupError as error:
        # Shared physical readers identify malformed recipient shapes on apply;
        # exporting must instead identify the source (without echoing its path).
        code = "source_shape" if error.code == "recipient_shape" else error.code
        message = str(error)
        for prefix in ("Unsupported recipient ", "Affected recipient "):
            if message.startswith(prefix):
                message = message.replace(
                    prefix, prefix.replace("recipient", "source"), 1
                )
                break
        raise SetupError(code, message) from error
    warnings = (
        (
            f"Exported {overrides} effective unsaved definition override(s); the source was not changed.",
        )
        if overrides
        else ()
    )
    return envelope, warnings
