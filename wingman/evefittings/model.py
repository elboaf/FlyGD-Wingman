"""Pure fitting validation, identity, provenance, and curation rules.

Remote ESI snapshots are untrusted authority input and are therefore strict:
one malformed fitting rejects the whole snapshot.  Local persistence is parsed by
:mod:`wingman.evefittings.store`, which may instead discard an isolated damaged
record while retaining the rest of the user's library.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from . import contracts

FINGERPRINT_VERSION = 1
CANONICAL_LOCATIONS = frozenset(contracts.RACK_BY_FLAG.values()) | (
    contracts.NON_RACK_FLAGS
)


@dataclass(frozen=True, order=True)
class RemoteItem:
    flag: str
    type_id: int
    quantity: int

    def key(self) -> tuple[str, int, int]:
        return self.flag, self.type_id, self.quantity


@dataclass(frozen=True)
class RemoteFitting:
    fitting_id: int
    ship_type_id: int
    name: str
    description: str
    items: tuple[RemoteItem, ...]


@dataclass(frozen=True, order=True)
class CanonicalItem:
    location: str
    type_id: int
    quantity: int

    def key(self) -> tuple[str, int, int]:
        return self.location, self.type_id, self.quantity


@dataclass(frozen=True)
class CanonicalContent:
    ship_type_id: int
    items: tuple[CanonicalItem, ...]

    def key(self) -> tuple[int, tuple[tuple[str, int, int], ...]]:
        return self.ship_type_id, tuple(item.key() for item in self.items)


@dataclass(frozen=True, order=True)
class SourceAlias:
    name: str
    description: str
    source_template: tuple[RemoteItem, ...]

    def key(self) -> tuple[str, str, tuple[tuple[str, int, int], ...]]:
        return (
            self.name,
            self.description,
            tuple(item.key() for item in self.source_template),
        )


@dataclass(frozen=True)
class Collection:
    id: str
    name: str


@dataclass(frozen=True)
class LibraryEntry:
    id: str
    content: CanonicalContent
    fingerprint_version: int
    digest: str
    source_template: tuple[RemoteItem, ...]
    deployment_template: tuple[RemoteItem, ...] | None
    preferred_name: str
    preferred_description: str
    aliases: tuple[SourceAlias, ...]
    collection_ids: tuple[str, ...]
    superseded_by: str | None
    created_utc: datetime
    updated_utc: datetime

    @property
    def is_unfiled(self) -> bool:
        return not self.collection_ids


@dataclass(frozen=True)
class Presence:
    character_id: int
    remote_fitting_id: int
    library_entry_id: str
    source_name: str
    source_description: str
    source_template: tuple[RemoteItem, ...]
    first_seen_utc: datetime
    discovered_batch_id: str
    last_confirmed_utc: datetime


@dataclass(frozen=True)
class CharacterSnapshot:
    character_id: int
    fetched_utc: datetime | None = None
    etag: str = ""
    error: str = ""

    @property
    def stale(self) -> bool:
        return self.fetched_utc is not None and bool(self.error)


@dataclass(frozen=True)
class WriteIntent:
    operation_id: str
    character_id: int
    # Empty only after tolerant recovery detaches a missing or mismatched
    # entry. The canonical content remains the safety key that blocks a copy.
    library_entry_id: str
    content: CanonicalContent
    status: str
    created_utc: datetime
    sent_utc: datetime | None = None
    completed_utc: datetime | None = None
    remote_fitting_id: int | None = None
    error: str = ""

    @property
    def unresolved(self) -> bool:
        return self.status in {"in_flight", "unknown"}


@dataclass(frozen=True)
class FittingsState:
    entries: tuple[LibraryEntry, ...] = ()
    collections: tuple[Collection, ...] = ()
    presences: tuple[Presence, ...] = ()
    snapshots: tuple[CharacterSnapshot, ...] = ()
    intents: tuple[WriteIntent, ...] = ()


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer.")
    return value


def _bounded_text(
    value: object, label: str, maximum: int, *, required: bool = False
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be text.")
    if required and not value:
        raise ValueError(f"{label} must not be empty.")
    if len(value) > maximum:
        raise ValueError(f"{label} exceeds its {maximum}-character limit.")
    return value


def _validate_remote_item(
    raw: object, fitting_index: int, item_index: int
) -> RemoteItem:
    if not isinstance(raw, dict):
        raise ValueError(
            f"Remote fitting {fitting_index} item {item_index} must be an object."
        )
    flag = raw.get("flag")
    if not isinstance(flag, str):
        raise ValueError(
            f"Remote fitting {fitting_index} item {item_index} flag must be text."
        )
    if flag not in contracts.ACCEPTED_FLAGS:
        raise ValueError(
            f"Remote fitting {fitting_index} item {item_index} has unknown fitting flag {flag!r}."
        )
    return RemoteItem(
        flag=flag,
        type_id=_positive_int(raw.get("type_id"), "Remote item type ID"),
        quantity=_positive_int(raw.get("quantity"), "Remote item quantity"),
    )


def validate_remote_snapshot(raw: object) -> tuple[RemoteFitting, ...]:
    """Validate one complete ESI GET payload or raise without returning rows."""
    if not isinstance(raw, list):
        raise ValueError("Remote fitting snapshot must be a list.")
    if len(raw) > contracts.MAX_REMOTE_FITTINGS:
        raise ValueError(
            f"Remote fitting snapshot exceeds {contracts.MAX_REMOTE_FITTINGS} fittings."
        )

    fittings: list[RemoteFitting] = []
    seen_ids: set[int] = set()
    for fitting_index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"Remote fitting {fitting_index} must be an object.")
        fitting_id = _positive_int(item.get("fitting_id"), "Remote fitting ID")
        if fitting_id in seen_ids:
            raise ValueError(f"Remote fitting ID {fitting_id} appears more than once.")
        seen_ids.add(fitting_id)
        items = item.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError(f"Remote fitting {fitting_index} must contain item rows.")
        if len(items) > contracts.MAX_CREATE_ITEMS:
            raise ValueError(
                f"Remote fitting {fitting_index} exceeds {contracts.MAX_CREATE_ITEMS} item rows."
            )
        fittings.append(
            RemoteFitting(
                fitting_id=fitting_id,
                ship_type_id=_positive_int(
                    item.get("ship_type_id"), "Remote ship type ID"
                ),
                name=_bounded_text(
                    item.get("name"),
                    "Remote fitting name",
                    contracts.MAX_NAME_CHARS,
                    required=True,
                ),
                description=_bounded_text(
                    item.get("description"),
                    "Remote fitting description",
                    contracts.MAX_DESCRIPTION_CHARS,
                ),
                items=tuple(
                    _validate_remote_item(raw_item, fitting_index, item_index)
                    for item_index, raw_item in enumerate(items)
                ),
            )
        )
    return tuple(fittings)


def canonicalize(fitting: RemoteFitting) -> CanonicalContent:
    """Collapse numbered positions and aggregate exact canonical rows."""
    quantities: dict[tuple[str, int], int] = defaultdict(int)
    for item in fitting.items:
        location = contracts.RACK_BY_FLAG.get(item.flag, item.flag)
        quantities[(location, item.type_id)] += item.quantity
    items = tuple(
        CanonicalItem(location, type_id, quantity)
        for (location, type_id), quantity in sorted(quantities.items())
    )
    return CanonicalContent(fitting.ship_type_id, items)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def fingerprint(
    content: CanonicalContent, *, version: int = FINGERPRINT_VERSION
) -> str:
    if isinstance(version, bool) or not isinstance(version, int) or version <= 0:
        raise ValueError("Fingerprint version must be a positive integer.")
    encoded = json.dumps(content.key(), separators=(",", ":"), ensure_ascii=True)
    return _digest(f"{version}:{encoded}")


def canonical_equal(
    left: CanonicalContent,
    right: CanonicalContent,
    *,
    version: int = FINGERPRINT_VERSION,
) -> bool:
    """Use the digest as an index hint, never as proof of identity."""
    return (
        fingerprint(left, version=version) == fingerprint(right, version=version)
        and left == right
    )


def deployment_template(fitting: RemoteFitting) -> tuple[RemoteItem, ...] | None:
    """Return an exact create template, or None for schema-defined Invalid rows."""
    if any(item.flag == "Invalid" for item in fitting.items):
        return None
    return fitting.items


def normalized_name_key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def retain_aliases(
    aliases: Iterable[SourceAlias], *, preferred_name: str, preferred_description: str
) -> tuple[SourceAlias, ...]:
    """Deduplicate and deterministically retain bounded source metadata.

    Aliases are observed provenance rather than curated identity.  The preferred
    name/description's source alias is retained when present; all other aliases
    are ordered by normalized name and complete source data before applying the
    cap, so input order cannot decide which provenance survives.
    """
    unique = {alias.key(): alias for alias in aliases}
    ordered = sorted(
        unique.values(),
        key=lambda alias: (
            normalized_name_key(alias.name),
            alias.name,
            alias.description,
            tuple(item.key() for item in alias.source_template),
        ),
    )
    preferred = next(
        (
            alias
            for alias in ordered
            if alias.name == preferred_name
            and alias.description == preferred_description
        ),
        None,
    )
    if preferred is not None:
        ordered.remove(preferred)
        ordered.insert(0, preferred)
    return tuple(ordered[: contracts.MAX_ALIASES_PER_ENTRY])


def new_library_entry(
    fitting: RemoteFitting,
    *,
    entry_id: str | None = None,
    now: datetime | None = None,
    fingerprint_version: int = FINGERPRINT_VERSION,
) -> LibraryEntry:
    content = canonicalize(fitting)
    timestamp = now or datetime.now(UTC)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    else:
        timestamp = timestamp.astimezone(UTC)
    alias = SourceAlias(fitting.name, fitting.description, fitting.items)
    return LibraryEntry(
        id=entry_id or str(uuid.uuid4()),
        content=content,
        fingerprint_version=fingerprint_version,
        digest=fingerprint(content, version=fingerprint_version),
        source_template=fitting.items,
        deployment_template=deployment_template(fitting),
        preferred_name=fitting.name,
        preferred_description=fitting.description,
        aliases=(alias,),
        collection_ids=(),
        superseded_by=None,
        created_utc=timestamp,
        updated_utc=timestamp,
    )


def _index_entries(entries: Iterable[LibraryEntry]) -> dict[str, LibraryEntry]:
    by_id: dict[str, LibraryEntry] = {}
    for entry in entries:
        if entry.id in by_id:
            raise ValueError("Library entry IDs must be unique.")
        by_id[entry.id] = entry
    return by_id


def _validate_supersession_edges(
    by_id: dict[str, LibraryEntry], edges: dict[str, str]
) -> None:
    for entry_id, target_id in edges.items():
        if target_id == entry_id:
            raise ValueError("A fitting cannot supersede itself.")
        target = by_id.get(target_id)
        if target is None:
            raise ValueError(f"Superseding entry {target_id!r} does not exist.")
        if by_id[entry_id].content.ship_type_id != target.content.ship_type_id:
            raise ValueError("Supersession requires the same ship type.")

    complete: set[str] = set()
    for start in edges:
        if start in complete:
            continue
        path: list[str] = []
        positions: dict[str, int] = {}
        current = start
        while current in edges and current not in complete:
            if current in positions:
                raise ValueError("Supersession would create a cycle.")
            positions[current] = len(path)
            path.append(current)
            current = edges[current]
        complete.update(path)


def validate_supersession_graph(entries: Iterable[LibraryEntry]) -> None:
    """Validate every persisted supersession edge with one stable-ID index."""
    by_id = _index_entries(entries)
    edges = {
        entry.id: entry.superseded_by
        for entry in by_id.values()
        if entry.superseded_by is not None
    }
    _validate_supersession_edges(by_id, edges)


def validate_supersession(
    entries: Iterable[LibraryEntry], entry_id: str, superseded_by: str | None
) -> None:
    """Validate a proposed edge against stable IDs, hulls, and the whole graph."""
    by_id = _index_entries(entries)
    if entry_id not in by_id:
        raise ValueError(f"Library entry {entry_id!r} does not exist.")
    if superseded_by is None:
        return
    edges = {
        entry.id: entry.superseded_by
        for entry in by_id.values()
        if entry.superseded_by is not None
    }
    edges[entry_id] = superseded_by
    _validate_supersession_edges(by_id, edges)
