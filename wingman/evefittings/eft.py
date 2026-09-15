"""Pure conventional EFT import and lossless-or-refused export.

No network, display-name fallback or fitting simulation belongs here. Import
normalizations are disclosed per line; export proves full canonical equality
using the same verified inventory snapshot before returning actionable text.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from . import contracts
from .model import LibraryEntry, RemoteItem, canonicalize_items, normalized_name_key


@dataclass(frozen=True)
class ParsedLine:
    line_number: int
    kind: Literal["module", "quantity", "empty"]
    type_name: str | None
    quantity: int | None
    charge_name: str | None
    offline: bool
    empty_rack: str | None


@dataclass(frozen=True)
class ParsedEft:
    ship_name: str
    name: str
    header_line_number: int
    lines: tuple[ParsedLine, ...]


@dataclass(frozen=True)
class InventoryType:
    type_id: int
    name: str
    group_id: int
    category_id: int
    published: bool
    dogma_effect_ids: frozenset[int]


@dataclass(frozen=True)
class InventorySnapshot:
    types: tuple[InventoryType, ...]
    name_bindings: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class EftWarning:
    code: Literal["bay_convention", "loaded_charge_omitted", "offline_omitted"]
    line_number: int
    message: str


@dataclass(frozen=True)
class EftCandidate:
    ship_type_id: int
    name: str
    items: tuple[RemoteItem, ...]
    warnings: tuple[EftWarning, ...]
    verified_names: tuple[tuple[int, str], ...]


class EftError(ValueError):
    def __init__(self, code: str, message: str, *, line_number: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.line_number = line_number


_RACK_EFFECTS = {
    11: contracts.LOW,
    13: contracts.MEDIUM,
    12: contracts.HIGH,
    2663: contracts.RIG,
    3772: contracts.SUBSYSTEM,
    6306: contracts.SERVICE,
}
_EMPTY_BY_RACK = {
    contracts.LOW: "[Empty Low slot]",
    contracts.MEDIUM: "[Empty Med slot]",
    contracts.HIGH: "[Empty High slot]",
    contracts.RIG: "[Empty Rig slot]",
    contracts.SUBSYSTEM: "[Empty Subsystem slot]",
    contracts.SERVICE: "[Empty Service slot]",
}
_RACK_BY_EMPTY = {marker: rack for rack, marker in _EMPTY_BY_RACK.items()}
_FLAGS_BY_RACK = {
    rack: tuple(flag for flag, value in contracts.RACK_BY_FLAG.items() if value == rack)
    for rack in _EMPTY_BY_RACK
}
_BAY_BY_CATEGORY = {18: "DroneBay", 87: "FighterBay"}
_QUANTITY = re.compile(r"^(.*?)\s+x(.*)$")


def _name_key(name: str) -> str:
    return normalized_name_key(name.strip())


def _has_control(text: str) -> bool:
    return any(
        unicodedata.category(ch) in {"Cc", "Cf", "Cs", "Zl", "Zp"} for ch in text
    )


def _text_name(value: str, *, fit: bool = False, line: int | None = None) -> str:
    maximum = contracts.MAX_NAME_CHARS if fit else contracts.MAX_EFT_TYPE_NAME_CHARS
    forbidden = "[]" if fit else "[],/"
    if (
        not value.strip()
        or len(value) > maximum
        or _has_control(value)
        or any(ch in value for ch in forbidden)
    ):
        raise EftError(
            "invalid_name", "Invalid or over-limit fitting/type name.", line_number=line
        )
    return value


def _bounded_quantity(value: int, line: int | None = None) -> int:
    if type(value) is not int or not 0 < value <= contracts.MAX_EFT_QUANTITY:
        raise EftError(
            "invalid_quantity",
            "Quantity must be an integer from 1 to 2147483647.",
            line_number=line,
        )
    return value


def parse_eft(text: str) -> ParsedEft:
    """Parse and bound one fit before any inventory lookup can be admitted."""
    if not isinstance(text, str):
        raise EftError("invalid_text", "Fitting text is required.")
    if len(text) > contracts.MAX_EFT_BYTES:
        raise EftError("input_limit", "Fitting text exceeds 64 KiB.")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise EftError("invalid_text", "Fitting text is not valid Unicode.") from exc
    if size > contracts.MAX_EFT_BYTES:
        raise EftError("input_limit", "Fitting text exceeds 64 KiB.")
    text = text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    physical = text.removesuffix("\n").split("\n")
    if len(physical) > contracts.MAX_EFT_LINES:
        raise EftError("input_limit", "Fitting text exceeds 2048 physical lines.")
    header = None
    lines = []
    item_count = 0
    quantities: dict[str, int] = defaultdict(int)
    for number, raw in enumerate(physical, 1):
        # Check before trimming: str.strip also removes some forbidden controls.
        # Tabs may surround fields; _text_name still rejects them inside names.
        if _has_control(raw.replace("\t", "")):
            raise EftError(
                "invalid_text",
                "Control characters are not supported.",
                line_number=number,
            )
        line = raw.strip()
        if not line:
            continue
        if header is None:
            if not line.startswith("[") or not line.endswith("]") or "," not in line:
                raise EftError(
                    "invalid_header",
                    "Expected one [Hull Name, Fit Name] header.",
                    line_number=number,
                )
            ship, name = (part.strip() for part in line[1:-1].split(",", 1))
            header = (
                _text_name(ship, line=number),
                _text_name(name, fit=True, line=number),
                number,
            )
            continue
        if line in _RACK_BY_EMPTY:
            lines.append(
                ParsedLine(
                    number, "empty", None, None, None, False, _RACK_BY_EMPTY[line]
                )
            )
            continue
        if line.startswith("["):
            raise EftError(
                "invalid_syntax",
                "Multiple fits or bracket directives are not supported.",
                line_number=number,
            )
        if any(ch in line for ch in "[]{}"):
            raise EftError(
                "unsupported_mutation",
                "Mutation references and per-instance alterations are not supported.",
                line_number=number,
            )
        item_count += 1
        if item_count > contracts.MAX_CREATE_ITEMS:
            raise EftError(
                "input_limit", "Fitting exceeds 512 item lines.", line_number=number
            )
        match = _QUANTITY.fullmatch(line)
        if match:
            name, digits = match.groups()
            if not re.fullmatch(r"[0-9]+", digits) or len(digits.lstrip("0")) > 10:
                raise EftError(
                    "invalid_quantity",
                    "Expected a positive decimal quantity without state or charge suffixes.",
                    line_number=number,
                )
            # Avoid Python's decimal conversion limit even for many leading zeros.
            quantity = _bounded_quantity(int(digits.lstrip("0") or "0"), number)
            name = _text_name(name.strip(), line=number)
            key = _name_key(name)
            quantities[key] += quantity
            _bounded_quantity(quantities[key], number)
            lines.append(
                ParsedLine(number, "quantity", name, quantity, None, False, None)
            )
            continue
        offline = line.lower().endswith("/offline")
        if offline:
            line = line[: -len("/offline")].rstrip()
        if "/" in line:
            raise EftError(
                "invalid_state", "Only /offline state is supported.", line_number=number
            )
        fields = line.split(",")
        if len(fields) > 2:
            raise EftError(
                "invalid_syntax",
                "Expected one module and at most one inline charge.",
                line_number=number,
            )
        names = [_text_name(field.strip(), line=number) for field in fields]
        lines.append(
            ParsedLine(
                number,
                "module",
                names[0],
                1,
                names[1] if len(names) == 2 else None,
                offline,
                None,
            )
        )
    if header is None or not item_count:
        raise EftError(
            "empty_fitting", "A fitting must contain a hull, name and item rows."
        )
    return ParsedEft(*header, tuple(lines))


def _published(item: InventoryType, line: int | None = None) -> None:
    if not item.published:
        raise EftError(
            "unpublished_type",
            f"{item.name} is not published inventory.",
            line_number=line,
        )


def _module_rack(item: InventoryType, line: int | None = None) -> str:
    _published(item, line)
    racks = [
        _RACK_EFFECTS[effect]
        for effect in item.dogma_effect_ids
        if effect in _RACK_EFFECTS
    ]
    if item.category_id not in {7, 32, 66} or len(racks) != 1:
        raise EftError(
            "unsupported_module",
            f"{item.name} must be a supported module with exactly one rack effect.",
            line_number=line,
        )
    return racks[0]


def _quantity_location(item: InventoryType, line: int | None = None) -> str:
    _published(item, line)
    if item.category_id == 20:
        raise EftError(
            "unsupported_type",
            "Implants and boosters are not supported.",
            line_number=line,
        )
    return _BAY_BY_CATEGORY.get(item.category_id, "Cargo")


def resolve_eft(parsed: ParsedEft, inventory: InventorySnapshot) -> EftCandidate:
    """Resolve every name, disclosing conventional bay/charge/state handling."""
    types = {item.type_id: item for item in inventory.types}
    bindings = dict(inventory.name_bindings)

    def lookup(name, number):
        item = types.get(bindings.get(_name_key(name)))
        if item is None or _name_key(item.name) != _name_key(name):
            raise EftError(
                "unresolved_name",
                f"Inventory name {name!r} could not be verified.",
                line_number=number,
            )
        _published(item, number)
        return item

    ship = lookup(parsed.ship_name, parsed.header_line_number)
    if ship.category_id not in {6, 65}:
        raise EftError(
            "unsupported_hull",
            "Hull must be a ship or structure.",
            line_number=parsed.header_line_number,
        )
    counters = dict.fromkeys(_FLAGS_BY_RACK, 0)
    rows = []
    warnings = []
    totals: dict[tuple[str, int], int] = defaultdict(int)
    for line in parsed.lines:
        number = line.line_number
        if line.kind == "empty":
            rack = line.empty_rack
        else:
            item = lookup(line.type_name, number)
            rack = _module_rack(item, number) if line.kind == "module" else None
        if rack is not None:
            flags = _FLAGS_BY_RACK[rack]
            index = counters[rack]
            if index >= len(flags):
                raise EftError(
                    "rack_overflow",
                    f"Too many {rack} slot positions.",
                    line_number=number,
                )
            counters[rack] += 1
            if line.kind == "empty":
                continue
            flag = flags[index]
        else:
            flag = _quantity_location(item, number)
            if flag != "Cargo":
                warnings.append(
                    EftWarning(
                        "bay_convention",
                        number,
                        f"Line {number}: {item.name} x{line.quantity} is interpreted as {flag} content; EFT does not preserve Cargo/bay intent.",
                    )
                )
        if line.charge_name:
            charge = lookup(line.charge_name, number)
            if charge.category_id != 8:
                raise EftError(
                    "unsupported_charge",
                    f"{charge.name} is not a charge.",
                    line_number=number,
                )
            warnings.append(
                EftWarning(
                    "loaded_charge_omitted",
                    number,
                    f"Line {number}: Loaded charge selection {charge.name} is not retained; EFT specifies no quantity. Explicit cargo quantities are unchanged.",
                )
            )
        if line.offline:
            warnings.append(
                EftWarning(
                    "offline_omitted",
                    number,
                    f"Line {number}: Offline state is not retained; the module remains in the fitting.",
                )
            )
        quantity = _bounded_quantity(line.quantity, number)
        key = (contracts.RACK_BY_FLAG.get(flag, flag), item.type_id)
        totals[key] += quantity
        _bounded_quantity(totals[key], number)
        rows.append(RemoteItem(flag, item.type_id, quantity))
    if not rows or len(rows) > contracts.MAX_CREATE_ITEMS:
        raise EftError("input_limit", "A fitting must contain 1 to 512 item rows.")
    persisted_ids = {ship.type_id} | {row.type_id for row in rows}
    return EftCandidate(
        ship.type_id,
        parsed.name,
        tuple(rows),
        tuple(warnings),
        tuple((type_id, types[type_id].name) for type_id in sorted(persisted_ids)),
    )


def _export_template(entry: LibraryEntry) -> tuple[RemoteItem, ...]:
    """Pre-network refusal checks shared with the inventory boundary."""
    _text_name(entry.preferred_name, fit=True)
    template = entry.deployment_template
    if not template or len(template) > contracts.MAX_CREATE_ITEMS:
        raise EftError(
            "unrepresentable_export",
            "Export needs a nonempty deployment template of at most 512 rows.",
        )
    _bounded_quantity(entry.content.ship_type_id)
    for row in template:
        _bounded_quantity(row.type_id)
        _bounded_quantity(row.quantity)
        if row.flag not in contracts.ACCEPTED_FLAGS or row.flag == "Invalid":
            raise EftError(
                "unrepresentable_export",
                "Invalid deployment location cannot be exported.",
            )
    content = canonicalize_items(entry.content.ship_type_id, template)
    for row in content.items:
        _bounded_quantity(row.quantity)
    if content != entry.content:
        raise EftError(
            "unrepresentable_export",
            "Deployment template does not reproduce saved canonical content.",
        )
    return template


def render_eft(entry: LibraryEntry, inventory: InventorySnapshot) -> str:
    """Return deterministic EFT only after proving the full internal round trip."""
    template = _export_template(entry)
    types = {item.type_id: item for item in inventory.types}

    def lookup(type_id):
        if type_id not in types:
            raise EftError(
                "unresolved_name", f"Inventory type {type_id} could not be verified."
            )
        item = types[type_id]
        _published(item)
        _text_name(item.name)
        return item

    ship = lookup(entry.content.ship_type_id)
    if ship.category_id not in {6, 65}:
        raise EftError("unsupported_hull", "Hull must be a ship or structure.")
    occupied = {}
    stacks: dict[tuple[str, int], int] = defaultdict(int)
    for row in template:
        item = lookup(row.type_id)
        rack = contracts.RACK_BY_FLAG.get(row.flag)
        if rack is not None:
            if row.quantity != 1 or row.flag in occupied or _module_rack(item) != rack:
                raise EftError(
                    "unrepresentable_export",
                    "Fitted rows need one matching module per numbered position; charges cannot be exported.",
                )
            occupied[row.flag] = item.name
        else:
            if _quantity_location(item) != row.flag:
                raise EftError(
                    "unrepresentable_export",
                    "Stored Cargo/bay location would change on re-import.",
                )
            stacks[(row.flag, row.type_id)] += row.quantity
            _bounded_quantity(stacks[(row.flag, row.type_id)])
    racks = []
    for rack, flags in _FLAGS_BY_RACK.items():
        positions = [index for index, flag in enumerate(flags) if flag in occupied]
        if positions:
            racks.append(
                "\n".join(
                    occupied.get(flag, _EMPTY_BY_RACK[rack])
                    for flag in flags[: max(positions) + 1]
                )
            )
    sections = []
    if racks:
        sections.append("\n\n".join(racks))
    bays = []
    for location in ("DroneBay", "FighterBay", "Cargo"):
        lines = [
            f"{types[type_id].name} x{quantity}"
            for (flag, type_id), quantity in sorted(stacks.items())
            if flag == location
        ]
        if not lines:
            continue
        if location == "Cargo":
            if bays:
                sections.append("\n\n".join(bays))
                bays = []
            sections.append("\n".join(lines))
        else:
            bays.append("\n".join(lines))
    if bays:
        sections.append("\n\n".join(bays))
    text = f"[{ship.name}, {entry.preferred_name}]\n\n" + "\n\n\n".join(sections) + "\n"
    candidate = resolve_eft(parse_eft(text), inventory)
    if canonicalize_items(candidate.ship_type_id, candidate.items) != entry.content:
        raise EftError(
            "unrepresentable_export", "Export would change saved canonical content."
        )
    return text
