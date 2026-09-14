"""Explicit primary-preview snapshots. Pure records; no file or native ownership.

Working geometry and Preview choices remain independent of named snapshots.
The settings normalizer forgives malformed records, never malformed members of
an otherwise accepted record; live writes refuse rather than silently dropping.
"""

import hashlib
import json
from dataclasses import dataclass

from .crops import valid_owner
from .geometry import Rect

_INT_MIN = -(2**31)
_INT_MAX = 2**31 - 1


@dataclass(frozen=True)
class PrimaryLayoutLiveResult:
    live: str
    warning: str | None


@dataclass(frozen=True)
class SavedCharacter:
    name: str
    visible: bool
    rect: Rect | None


@dataclass(frozen=True)
class SavedLayout:
    id: str
    name: str
    characters: tuple[SavedCharacter, ...]


def _rectangle(raw: object) -> Rect:
    if not isinstance(raw, dict):
        raise ValueError("Saved layout rectangle must be an object")
    values = tuple(raw.get(key) for key in ("x", "y", "w", "h"))
    if any(type(v) is not int or not _INT_MIN <= v <= _INT_MAX for v in values):
        raise ValueError("Saved layout rectangle must contain signed 32-bit integers")
    rect = Rect(*values)
    # Win32 RECT stores far edges, while SetWindowPos takes extents. Checking
    # each component alone still permits overflow when computing right/bottom.
    if rect.w <= 0 or rect.h <= 0 or rect.right > _INT_MAX or rect.bottom > _INT_MAX:
        raise ValueError("Saved layout rectangle needs positive, native-safe extents")
    return rect


def validate_record(raw: object) -> SavedLayout:
    """Refuse the whole proposal before any working configuration is changed."""
    if not isinstance(raw, dict):
        raise ValueError("Saved layout must be an object")
    record_id, name = raw.get("id"), raw.get("name")
    # IDs are opaque, as with named cycle groups; the creator owns generation.
    if not isinstance(record_id, str) or not record_id:
        raise ValueError("Saved layout ID must be a nonempty string")
    if not isinstance(name, str) or not name.strip() or not name.isprintable():
        raise ValueError("Saved layout name must be nonblank and printable")
    members = raw.get("characters")
    if not isinstance(members, dict) or not members:
        raise ValueError("Saved layout must contain at least one character")
    characters = []
    for owner, member in members.items():
        if not valid_owner(owner):
            raise ValueError(f"Invalid saved layout character owner: {owner!r}")
        if not isinstance(member, dict) or type(member.get("visible")) is not bool:
            raise ValueError(f"Preview visibility for {owner!r} must be a boolean")
        if "rect" not in member:
            raise ValueError(
                f"Saved layout character {owner!r} needs a rectangle or null"
            )
        rect = None if member["rect"] is None else _rectangle(member["rect"])
        characters.append(SavedCharacter(owner, member["visible"], rect))
    return SavedLayout(record_id, name.strip(), tuple(characters))


def deserialize(raw: object) -> tuple[SavedLayout, ...]:
    """Load v1 records in order; only a valid record claims its ID/name."""
    if (
        not isinstance(raw, dict)
        or type(raw.get("version")) is not int
        or raw["version"] != 1
        or not isinstance(raw.get("items"), list)
    ):
        return ()
    records, ids, names = [], set(), set()
    for item in raw["items"]:
        try:
            record = validate_record(item)
        except ValueError:
            continue
        folded = record.name.casefold()
        if record.id in ids or folded in names:
            continue
        records.append(record)
        ids.add(record.id)
        names.add(folded)
    return tuple(records)


def _record_dict(record: SavedLayout) -> dict:
    """Project only snapshot fields, checking directly constructed records too."""
    if not isinstance(record, SavedLayout) or not isinstance(record.characters, tuple):
        raise ValueError("Expected an immutable saved layout record")
    members = {}
    for character in record.characters:
        if not isinstance(character, SavedCharacter) or not valid_owner(character.name):
            raise ValueError("Invalid saved layout character owner")
        if character.name in members:
            raise ValueError(f"Duplicate saved layout character: {character.name!r}")
        if character.rect is not None and not isinstance(character.rect, Rect):
            raise ValueError("Saved layout rectangle must be a Rect or null")
        members[character.name] = {
            "visible": character.visible,
            "rect": character.rect._asdict() if character.rect is not None else None,
        }
    raw = {"id": record.id, "name": record.name, "characters": members}
    validated = validate_record(raw)
    raw["name"] = validated.name
    return raw


def serialize(records: tuple[SavedLayout, ...]) -> dict:
    """Produce detached v1 JSON data; invalid/duplicate live proposals refuse."""
    items, ids, names = [], set(), set()
    for record in records:
        item = _record_dict(record)
        folded = item["name"].casefold()
        if item["id"] in ids:
            raise ValueError(f"Duplicate saved layout ID: {item['id']!r}")
        if folded in names:
            raise ValueError(f"Duplicate saved layout name: {item['name']!r}")
        items.append(item)
        ids.add(item["id"])
        names.add(folded)
    return {"version": 1, "items": items}


def record_revision(record: SavedLayout) -> str:
    """Content identity, independent of character-map insertion order."""
    canonical = json.dumps(_record_dict(record), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def known_owners(section: dict, live_names: tuple[str, ...]) -> tuple[str, ...]:
    """Union exact owners from a normalized Preview section, live names first.

    Legacy rosters have looser identity rules; recheck names at the snapshot
    boundary without rewriting those existing settings or applying their caps.
    """
    hotkeys = section.get("hotkeys") or {}
    sources = (
        live_names,
        section.get("layouts") or {},
        section.get("seen") or [],
        section.get("excluded") or [],
        hotkeys.get("characters") or {},
        hotkeys.get("group_by_character") or {},
        section.get("locked") or [],
        section.get("never_minimize") or [],
        section.get("crops") or {},
        section.get("label_markers") or {},
        (
            character.name
            for record in deserialize(section.get("saved_layouts"))
            for character in record.characters
        ),
    )
    owners = {}
    for source in sources:
        for name in source:
            if valid_owner(name):
                owners[name] = None
    return tuple(owners)


def capture_characters(
    section: dict, retained: dict, live_rectangles: dict
) -> tuple[SavedCharacter, ...]:
    """Prefer actual live geometry, then undebounced retained/current geometry.

    The caller supplies a coherent capture. Saved-only owners contribute their
    identity, never an older snapshot's geometry or visibility. Temporary native
    hiding and global placement/lock preferences do not decide Preview choices.
    """
    owners = known_owners(section, (*live_rectangles, *retained))
    if not owners:
        raise ValueError("No known characters to save")
    current = section.get("layouts") or {}
    excluded = set(section.get("excluded") or [])
    characters = []
    for name in owners:
        rect = None
        if name in live_rectangles:
            rect = _rectangle(live_rectangles[name]._asdict())
        elif name in retained:
            rect = _rectangle(retained[name].rect._asdict())
        elif name in current:
            rect = _rectangle(current[name])
        characters.append(SavedCharacter(name, name not in excluded, rect))
    return tuple(characters)


def apply_snapshot(section: dict, snapshot: SavedLayout) -> None:
    """Merge into a transaction's Preview section, validating before mutation."""
    record = _record_dict(snapshot)
    layouts = dict(section.get("layouts") or {})
    excluded = list(section.get("excluded") or [])
    visible = {
        name for name, member in record["characters"].items() if member["visible"]
    }
    excluded = [name for name in excluded if name not in visible]
    hidden = set(excluded)
    for name, member in record["characters"].items():
        if member["rect"] is not None:
            # Legacy lock bits still round-trip, but are not snapshot authority.
            locked = (layouts.get(name) or {}).get("locked", False)
            layouts[name] = {**member["rect"], "locked": locked}
        if not member["visible"] and name not in hidden:
            excluded.append(name)
            hidden.add(name)
    section["layouts"] = layouts
    section["excluded"] = excluded
