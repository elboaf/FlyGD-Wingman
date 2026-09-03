"""Bounded durable storage for the consolidated fitting library.

The fitting controller is the single writer.  This module keeps one sibling
backup and atomically publishes a fully validated document.  A malformed local
row may be discarded with an actionable warning; malformed ESI data never
reaches this module because remote snapshots use the strict model validator.
"""

from __future__ import annotations

import contextlib
import json
import os
import stat as stat_module
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from .. import atomicio
from . import contracts
from .model import (
    CANONICAL_LOCATIONS,
    CanonicalContent,
    CanonicalItem,
    CharacterSnapshot,
    Collection,
    FittingsState,
    LibraryEntry,
    Presence,
    RemoteFitting,
    RemoteItem,
    SourceAlias,
    WriteIntent,
    canonicalize,
    retain_aliases,
    validate_supersession_graph,
)

STATE_VERSION = 1
MAX_LOCAL_ID_CHARS = 200
MAX_BATCH_ID_CHARS = 200
MAX_ERROR_CHARS = 4096
MAX_ETAG_CHARS = 4096
INTENT_STATUSES = frozenset({"in_flight", "unknown", "success", "failed"})

T = TypeVar("T")


def _iso(value: datetime | None) -> str:
    return "" if value is None else value.astimezone(UTC).isoformat()


def _parse_utc(raw: object, label: str, *, required: bool = True) -> datetime | None:
    if raw == "" and not required:
        return None
    if not isinstance(raw, str) or not raw:
        raise ValueError(f"{label} must be an ISO 8601 timestamp.")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO 8601 timestamp.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _positive_int(raw: object, label: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        raise ValueError(f"{label} must be a positive integer.")
    return raw


def _optional_positive_int(raw: object, label: str) -> int | None:
    if raw is None:
        return None
    return _positive_int(raw, label)


def _text(
    raw: object,
    label: str,
    maximum: int,
    *,
    required: bool = False,
) -> str:
    if not isinstance(raw, str):
        raise ValueError(f"{label} must be text.")
    if required and not raw:
        raise ValueError(f"{label} must not be empty.")
    if len(raw) > maximum:
        raise ValueError(f"{label} exceeds its {maximum}-character limit.")
    return raw


def _identifier(raw: object, label: str) -> str:
    return _text(raw, label, MAX_LOCAL_ID_CHARS, required=True)


def _content_to_dict(content: CanonicalContent) -> dict:
    return {
        "ship_type_id": content.ship_type_id,
        "items": [
            {
                "location": item.location,
                "type_id": item.type_id,
                "quantity": item.quantity,
            }
            for item in content.items
        ],
    }


def _content_from_dict(raw: object) -> CanonicalContent:
    if not isinstance(raw, dict):
        raise ValueError("Canonical content must be an object.")
    ship_type_id = _positive_int(raw.get("ship_type_id"), "Canonical ship type ID")
    items_raw = raw.get("items")
    if not isinstance(items_raw, list) or not items_raw:
        raise ValueError("Canonical content must contain item rows.")
    items = []
    for row in items_raw:
        if not isinstance(row, dict):
            raise ValueError("Canonical item must be an object.")
        location = row.get("location")
        if not isinstance(location, str) or location not in CANONICAL_LOCATIONS:
            raise ValueError("Canonical item has an invalid location.")
        items.append(
            CanonicalItem(
                location=location,
                type_id=_positive_int(row.get("type_id"), "Canonical item type ID"),
                quantity=_positive_int(row.get("quantity"), "Canonical item quantity"),
            )
        )
    content = CanonicalContent(ship_type_id, tuple(items))
    # Stored canonical rows are identity, not source data to recanonicalize.
    # Refuse an order/aggregation drift instead of silently changing that identity.
    keys = tuple(item.key() for item in content.items)
    identities = tuple((item.location, item.type_id) for item in content.items)
    if keys != tuple(sorted(keys)) or len(identities) != len(set(identities)):
        raise ValueError("Canonical item rows must be aggregated and sorted.")
    return content


def _template_to_dict(template: tuple[RemoteItem, ...] | None) -> list[dict] | None:
    if template is None:
        return None
    return [
        {"flag": item.flag, "type_id": item.type_id, "quantity": item.quantity}
        for item in template
    ]


def _template_from_dict(
    raw: object, label: str, *, allow_none: bool = False
) -> tuple[RemoteItem, ...] | None:
    if raw is None and allow_none:
        return None
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{label} must contain exact item rows.")
    if len(raw) > contracts.MAX_CREATE_ITEMS:
        raise ValueError(f"{label} exceeds {contracts.MAX_CREATE_ITEMS} item rows.")
    result = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"{label} item must be an object.")
        flag = item.get("flag")
        if not isinstance(flag, str) or flag not in contracts.ACCEPTED_FLAGS:
            raise ValueError(f"{label} item has an invalid flag.")
        result.append(
            RemoteItem(
                flag=flag,
                type_id=_positive_int(item.get("type_id"), f"{label} item type ID"),
                quantity=_positive_int(item.get("quantity"), f"{label} item quantity"),
            )
        )
    return tuple(result)


def _template_content(
    ship_type_id: int, template: tuple[RemoteItem, ...]
) -> CanonicalContent:
    return canonicalize(
        RemoteFitting(
            fitting_id=1,
            ship_type_id=ship_type_id,
            name="Stored template",
            description="",
            items=template,
        )
    )


def _validate_content_value(content: object) -> CanonicalContent:
    if not isinstance(content, CanonicalContent):
        raise ValueError("Canonical content has the wrong type.")
    _positive_int(content.ship_type_id, "Canonical ship type ID")
    if not isinstance(content.items, tuple) or not content.items:
        raise ValueError("Canonical content must contain item rows.")
    keys = []
    identities = set()
    for item in content.items:
        if not isinstance(item, CanonicalItem):
            raise ValueError("Canonical item has the wrong type.")
        if item.location not in CANONICAL_LOCATIONS:
            raise ValueError("Canonical item has an invalid location.")
        _positive_int(item.type_id, "Canonical item type ID")
        _positive_int(item.quantity, "Canonical item quantity")
        identity = item.location, item.type_id
        if identity in identities:
            raise ValueError("Canonical item rows must be aggregated.")
        identities.add(identity)
        keys.append(item.key())
    if keys != sorted(keys):
        raise ValueError("Canonical item rows must be sorted.")
    return content


def _validate_template_value(
    content: CanonicalContent,
    template: object,
    label: str,
    cache: dict[tuple[int, tuple[RemoteItem, ...]], CanonicalContent],
    *,
    deployable: bool = False,
) -> tuple[RemoteItem, ...]:
    if not isinstance(template, tuple) or not template:
        raise ValueError(f"{label} must contain exact item rows.")
    if len(template) > contracts.MAX_CREATE_ITEMS:
        raise ValueError(f"{label} exceeds {contracts.MAX_CREATE_ITEMS} item rows.")
    for item in template:
        if not isinstance(item, RemoteItem):
            raise ValueError(f"{label} item has the wrong type.")
        if item.flag not in contracts.ACCEPTED_FLAGS:
            raise ValueError(f"{label} item has an invalid flag.")
        _positive_int(item.type_id, f"{label} item type ID")
        _positive_int(item.quantity, f"{label} item quantity")
    if deployable and any(item.flag == "Invalid" for item in template):
        raise ValueError(f"{label} may not contain Invalid rows.")
    key = content.ship_type_id, template
    canonical = cache.get(key)
    if canonical is None:
        canonical = _template_content(content.ship_type_id, template)
        cache[key] = canonical
    if canonical != content:
        raise ValueError(f"{label} does not reproduce canonical content.")
    return template


def _validate_template_matches(
    content: CanonicalContent,
    template: tuple[RemoteItem, ...],
    label: str,
    *,
    deployable: bool = False,
) -> None:
    _validate_template_value(content, template, label, {}, deployable=deployable)


def _validate_alias_value(
    alias: object,
    content: CanonicalContent,
    cache: dict[tuple[int, tuple[RemoteItem, ...]], CanonicalContent],
) -> None:
    if not isinstance(alias, SourceAlias):
        raise ValueError("Alias has the wrong type.")
    _text(alias.name, "Alias name", contracts.MAX_NAME_CHARS, required=True)
    _text(alias.description, "Alias description", contracts.MAX_DESCRIPTION_CHARS)
    _validate_template_value(
        content, alias.source_template, "Alias source template", cache
    )


def _alias_to_dict(alias: SourceAlias) -> dict:
    return {
        "name": alias.name,
        "description": alias.description,
        "source_template": _template_to_dict(alias.source_template),
    }


def _alias_from_dict(raw: object, content: CanonicalContent) -> SourceAlias:
    if not isinstance(raw, dict):
        raise ValueError("Alias must be an object.")
    template = _template_from_dict(raw.get("source_template"), "Alias source template")
    assert template is not None
    _validate_template_matches(content, template, "Alias source template")
    return SourceAlias(
        name=_text(
            raw.get("name"),
            "Alias name",
            contracts.MAX_NAME_CHARS,
            required=True,
        ),
        description=_text(
            raw.get("description"),
            "Alias description",
            contracts.MAX_DESCRIPTION_CHARS,
        ),
        source_template=template,
    )


def _entry_to_dict(entry: LibraryEntry) -> dict:
    return {
        "id": entry.id,
        "content": _content_to_dict(entry.content),
        "fingerprint_version": entry.fingerprint_version,
        "digest": entry.digest,
        "source_template": _template_to_dict(entry.source_template),
        "deployment_template": _template_to_dict(entry.deployment_template),
        "preferred_name": entry.preferred_name,
        "preferred_description": entry.preferred_description,
        "aliases": [_alias_to_dict(alias) for alias in entry.aliases],
        "collection_ids": list(entry.collection_ids),
        "superseded_by": entry.superseded_by,
        "created_utc": _iso(entry.created_utc),
        "updated_utc": _iso(entry.updated_utc),
    }


def _entry_from_dict(raw: object) -> tuple[LibraryEntry, int]:
    if not isinstance(raw, dict):
        raise ValueError("Library entry must be an object.")
    content = _content_from_dict(raw.get("content"))
    source_template = _template_from_dict(raw.get("source_template"), "Source template")
    assert source_template is not None
    _validate_template_matches(content, source_template, "Source template")
    deployment = _template_from_dict(
        raw.get("deployment_template"), "Deployment template", allow_none=True
    )
    if deployment is not None:
        _validate_template_matches(
            content, deployment, "Deployment template", deployable=True
        )

    preferred_name = _text(
        raw.get("preferred_name"),
        "Preferred name",
        contracts.MAX_NAME_CHARS,
        required=True,
    )
    preferred_description = _text(
        raw.get("preferred_description"),
        "Preferred description",
        contracts.MAX_DESCRIPTION_CHARS,
    )
    aliases_raw = raw.get("aliases")
    if not isinstance(aliases_raw, list) or not aliases_raw:
        raise ValueError("Library entry must retain at least one source alias.")
    aliases = []
    dropped_aliases = 0
    for alias_raw in aliases_raw:
        try:
            aliases.append(_alias_from_dict(alias_raw, content))
        except (ValueError, RecursionError):
            dropped_aliases += 1
    if not aliases:
        raise ValueError("Library entry retained no valid source aliases.")
    retained = retain_aliases(
        aliases,
        preferred_name=preferred_name,
        preferred_description=preferred_description,
    )
    dropped_aliases += len(aliases) - len(retained)

    collection_ids_raw = raw.get("collection_ids")
    if not isinstance(collection_ids_raw, list):
        raise ValueError("Collection membership must be a list of stable IDs.")
    collection_ids = tuple(
        dict.fromkeys(
            _identifier(item, "Collection membership ID") for item in collection_ids_raw
        )
    )
    superseded_by_raw = raw.get("superseded_by")
    superseded_by = (
        None
        if superseded_by_raw is None
        else _identifier(superseded_by_raw, "Superseding entry ID")
    )
    version = _positive_int(raw.get("fingerprint_version"), "Fingerprint version")
    digest = _text(raw.get("digest"), "Fingerprint digest", 256, required=True)
    created = _parse_utc(raw.get("created_utc"), "Entry creation time")
    updated = _parse_utc(raw.get("updated_utc"), "Entry update time")
    assert created is not None and updated is not None
    return (
        LibraryEntry(
            id=_identifier(raw.get("id"), "Library entry ID"),
            content=content,
            fingerprint_version=version,
            digest=digest,
            source_template=source_template,
            deployment_template=deployment,
            preferred_name=preferred_name,
            preferred_description=preferred_description,
            aliases=retained,
            collection_ids=collection_ids,
            superseded_by=superseded_by,
            created_utc=created,
            updated_utc=updated,
        ),
        dropped_aliases,
    )


def _collection_to_dict(collection: Collection) -> dict:
    return {"id": collection.id, "name": collection.name}


def _collection_from_dict(raw: object) -> Collection:
    if not isinstance(raw, dict):
        raise ValueError("Collection must be an object.")
    return Collection(
        id=_identifier(raw.get("id"), "Collection ID"),
        name=_text(
            raw.get("name"),
            "Collection name",
            contracts.MAX_COLLECTION_NAME_CHARS,
            required=True,
        ),
    )


def _presence_to_dict(presence: Presence) -> dict:
    return {
        "character_id": presence.character_id,
        "remote_fitting_id": presence.remote_fitting_id,
        "library_entry_id": presence.library_entry_id,
        "source_name": presence.source_name,
        "source_description": presence.source_description,
        "source_template": _template_to_dict(presence.source_template),
        "first_seen_utc": _iso(presence.first_seen_utc),
        "discovered_batch_id": presence.discovered_batch_id,
        "last_confirmed_utc": _iso(presence.last_confirmed_utc),
    }


def _presence_from_dict(raw: object, entries: dict[str, LibraryEntry]) -> Presence:
    if not isinstance(raw, dict):
        raise ValueError("Presence must be an object.")
    entry_id = _identifier(raw.get("library_entry_id"), "Presence library entry ID")
    entry = entries.get(entry_id)
    if entry is None:
        raise ValueError("Presence references a missing library entry.")
    template = _template_from_dict(
        raw.get("source_template"), "Presence source template"
    )
    assert template is not None
    _validate_template_matches(entry.content, template, "Presence source template")
    first_seen = _parse_utc(raw.get("first_seen_utc"), "Presence first-seen time")
    confirmed = _parse_utc(raw.get("last_confirmed_utc"), "Presence confirmation time")
    assert first_seen is not None and confirmed is not None
    return Presence(
        character_id=_positive_int(raw.get("character_id"), "Presence character ID"),
        remote_fitting_id=_positive_int(
            raw.get("remote_fitting_id"), "Presence remote fitting ID"
        ),
        library_entry_id=entry_id,
        source_name=_text(
            raw.get("source_name"),
            "Presence source name",
            contracts.MAX_NAME_CHARS,
            required=True,
        ),
        source_description=_text(
            raw.get("source_description"),
            "Presence source description",
            contracts.MAX_DESCRIPTION_CHARS,
        ),
        source_template=template,
        first_seen_utc=first_seen,
        discovered_batch_id=_text(
            raw.get("discovered_batch_id"),
            "Presence discovery batch ID",
            MAX_BATCH_ID_CHARS,
            required=True,
        ),
        last_confirmed_utc=confirmed,
    )


def _snapshot_to_dict(snapshot: CharacterSnapshot) -> dict:
    return {
        "character_id": snapshot.character_id,
        "fetched_utc": _iso(snapshot.fetched_utc),
        "etag": snapshot.etag,
        "error": snapshot.error,
    }


def _snapshot_from_dict(raw: object) -> CharacterSnapshot:
    if not isinstance(raw, dict):
        raise ValueError("Character snapshot must be an object.")
    return CharacterSnapshot(
        character_id=_positive_int(raw.get("character_id"), "Snapshot character ID"),
        fetched_utc=_parse_utc(
            raw.get("fetched_utc"), "Snapshot fetch time", required=False
        ),
        etag=_text(raw.get("etag"), "Snapshot ETag", MAX_ETAG_CHARS),
        error=_text(raw.get("error"), "Snapshot error", MAX_ERROR_CHARS),
    )


def _intent_to_dict(intent: WriteIntent) -> dict:
    return {
        "operation_id": intent.operation_id,
        "character_id": intent.character_id,
        "library_entry_id": intent.library_entry_id,
        "content": _content_to_dict(intent.content),
        "status": intent.status,
        "created_utc": _iso(intent.created_utc),
        "sent_utc": _iso(intent.sent_utc),
        "completed_utc": _iso(intent.completed_utc),
        "remote_fitting_id": intent.remote_fitting_id,
        "error": intent.error,
    }


def _intent_from_dict(raw: object) -> WriteIntent:
    if not isinstance(raw, dict):
        raise ValueError("Write intent must be an object.")
    status = raw.get("status")
    if not isinstance(status, str) or status not in INTENT_STATUSES:
        raise ValueError("Write intent has an invalid status.")
    entry_id_raw = raw.get("library_entry_id")
    if entry_id_raw == "" and status in {"in_flight", "unknown"}:
        entry_id = ""
    else:
        entry_id = _identifier(entry_id_raw, "Intent library entry ID")
    created = _parse_utc(raw.get("created_utc"), "Intent creation time")
    assert created is not None
    return WriteIntent(
        operation_id=_identifier(raw.get("operation_id"), "Operation ID"),
        character_id=_positive_int(raw.get("character_id"), "Intent character ID"),
        library_entry_id=entry_id,
        content=_content_from_dict(raw.get("content")),
        status=status,
        created_utc=created,
        sent_utc=_parse_utc(raw.get("sent_utc"), "Intent sent time", required=False),
        completed_utc=_parse_utc(
            raw.get("completed_utc"), "Intent completion time", required=False
        ),
        remote_fitting_id=_optional_positive_int(
            raw.get("remote_fitting_id"), "Intent remote fitting ID"
        ),
        error=_text(raw.get("error"), "Intent error", MAX_ERROR_CHARS),
    )


def _intent_identity(intent: WriteIntent) -> tuple[str, int, CanonicalContent]:
    return intent.operation_id, intent.character_id, intent.content


def _bounded_completed_history(
    intents: tuple[WriteIntent, ...], now: datetime
) -> tuple[WriteIntent, ...]:
    cutoff = now - contracts.COMPLETED_OPERATION_MAX_AGE
    completed = sorted(
        (
            intent
            for intent in intents
            if not intent.unresolved
            and (intent.completed_utc or intent.created_utc) >= cutoff
        ),
        key=lambda intent: (intent.created_utc, intent.operation_id),
    )[-contracts.MAX_OPERATION_RECORDS :]
    keep = {id(intent) for intent in completed}
    return tuple(
        intent for intent in intents if intent.unresolved or id(intent) in keep
    )


def bounded_operation_history(state: FittingsState, now: datetime) -> FittingsState:
    """Apply terminal-history bounds without ever removing safety state."""
    return replace(state, intents=_bounded_completed_history(state.intents, now))


def _normalized_intents_for_save(state: FittingsState) -> tuple[WriteIntent, ...]:
    entries = {entry.id: entry for entry in state.entries}
    return tuple(
        replace(intent, library_entry_id="")
        if intent.unresolved
        and (
            (entry := entries.get(intent.library_entry_id)) is None
            or entry.content != intent.content
        )
        else intent
        for intent in state.intents
    )


def _to_dict(state: FittingsState, now: datetime) -> dict:
    intents = _bounded_completed_history(_normalized_intents_for_save(state), now)
    return {
        "version": STATE_VERSION,
        "entries": [_entry_to_dict(entry) for entry in state.entries],
        "collections": [
            _collection_to_dict(collection) for collection in state.collections
        ],
        "presences": [_presence_to_dict(item) for item in state.presences],
        "snapshots": [_snapshot_to_dict(item) for item in state.snapshots],
        "intents": [_intent_to_dict(item) for item in intents],
    }


def _parse_rows(
    raw: object,
    parser: Callable[[object], T],
    label: str,
    warnings: list[str],
) -> list[T]:
    if not isinstance(raw, list):
        raise ValueError(f"Fitting state {label} must be a list.")
    rows = []
    dropped = 0
    for item in raw:
        try:
            rows.append(parser(item))
        except (ValueError, RecursionError):
            dropped += 1
    if dropped:
        warnings.append(f"Fitting state dropped {dropped} invalid {label} rows.")
    return rows


def _deduplicate_by(
    rows: list[T], key: Callable[[T], object], label: str, warnings: list[str]
) -> list[T]:
    kept = []
    seen = set()
    dropped = 0
    for row in rows:
        value = key(row)
        if value in seen:
            dropped += 1
            continue
        seen.add(value)
        kept.append(row)
    if dropped:
        warnings.append(f"Fitting state dropped {dropped} duplicate {label} rows.")
    return kept


def _recover_relationships(
    entries: list[LibraryEntry], collections: list[Collection], warnings: list[str]
) -> list[LibraryEntry]:
    collection_ids = {collection.id for collection in collections}
    recovered = []
    removed_memberships = 0
    for entry in entries:
        valid_ids = tuple(
            collection_id
            for collection_id in entry.collection_ids
            if collection_id in collection_ids
        )
        removed_memberships += len(entry.collection_ids) - len(valid_ids)
        recovered.append(replace(entry, collection_ids=valid_ids))
    if removed_memberships:
        warnings.append(
            f"Fitting state removed {removed_memberships} dangling collection memberships."
        )

    by_id = {entry.id: entry for entry in recovered}
    invalid_edges = set()
    for entry in recovered:
        target = by_id.get(entry.superseded_by) if entry.superseded_by else None
        if entry.superseded_by and (
            target is None
            or target.id == entry.id
            or target.content.ship_type_id != entry.content.ship_type_id
        ):
            invalid_edges.add(entry.id)

    edges = {
        entry.id: entry.superseded_by
        for entry in recovered
        if entry.superseded_by and entry.id not in invalid_edges
    }
    visited: set[str] = set()
    for start in edges:
        if start in visited:
            continue
        path: list[str] = []
        positions: dict[str, int] = {}
        current: str | None = start
        while current is not None and current in edges:
            if current in positions:
                invalid_edges.update(path[positions[current] :])
                break
            if current in visited:
                break
            positions[current] = len(path)
            path.append(current)
            current = edges.get(current)
        visited.update(path)
    if invalid_edges:
        warnings.append(
            f"Fitting state removed {len(invalid_edges)} invalid supersession edges."
        )
        recovered = [
            replace(entry, superseded_by=None) if entry.id in invalid_edges else entry
            for entry in recovered
        ]
    return recovered


def _from_dict(raw: object, now: datetime) -> tuple[FittingsState, tuple[str, ...]]:
    if not isinstance(raw, dict):
        raise ValueError("Fitting state must be an object.")
    warnings: list[str] = []

    entry_rows = _parse_rows(raw.get("entries"), _entry_from_dict, "entry", warnings)
    entries = []
    alias_drops = 0
    for entry, dropped_aliases in entry_rows:
        entries.append(entry)
        alias_drops += dropped_aliases
    if alias_drops:
        warnings.append(
            f"Fitting state aliases exceeded or failed validation; retained the deterministic bounded set and dropped {alias_drops}."
        )
    entries = _deduplicate_by(entries, lambda entry: entry.id, "entry ID", warnings)
    if len(entries) > contracts.MAX_LIBRARY_ENTRIES:
        raise ValueError("Fitting state exceeds the library entry limit.")

    collections = _parse_rows(
        raw.get("collections"), _collection_from_dict, "collection", warnings
    )
    collections = _deduplicate_by(
        collections, lambda collection: collection.id, "collection ID", warnings
    )
    if len(collections) > contracts.MAX_COLLECTIONS:
        raise ValueError("Fitting state exceeds the collection limit.")
    entries = _recover_relationships(entries, collections, warnings)
    by_entry_id = {entry.id: entry for entry in entries}

    presences = _parse_rows(
        raw.get("presences"),
        lambda item: _presence_from_dict(item, by_entry_id),
        "presence",
        warnings,
    )
    presences = _deduplicate_by(
        presences,
        lambda item: (item.character_id, item.remote_fitting_id),
        "presence identity",
        warnings,
    )
    snapshots = _parse_rows(
        raw.get("snapshots"), _snapshot_from_dict, "snapshot", warnings
    )
    snapshots = _deduplicate_by(
        snapshots, lambda item: item.character_id, "snapshot character", warnings
    )
    intents = _parse_rows(raw.get("intents"), _intent_from_dict, "intent", warnings)
    intents = _deduplicate_by(
        intents,
        _intent_identity,
        "intent identity",
        warnings,
    )
    intents = [
        replace(item, status="unknown", completed_utc=None)
        if item.status == "in_flight"
        else item
        for item in intents
    ]
    retained_intents = []
    unresolved_missing = 0
    unresolved_mismatched = 0
    terminal_missing = 0
    terminal_mismatched = 0
    for item in intents:
        if item.unresolved and not item.library_entry_id:
            retained_intents.append(item)
            continue
        entry = by_entry_id.get(item.library_entry_id)
        relationship = (
            "missing"
            if entry is None
            else "mismatched"
            if entry.content != item.content
            else ""
        )
        if not relationship:
            retained_intents.append(item)
        elif item.unresolved:
            retained_intents.append(replace(item, library_entry_id=""))
            if relationship == "missing":
                unresolved_missing += 1
            else:
                unresolved_mismatched += 1
        elif relationship == "missing":
            terminal_missing += 1
        else:
            terminal_mismatched += 1
    for qualifier, count in (
        ("unresolved missing", unresolved_missing),
        ("unresolved mismatched", unresolved_mismatched),
        ("terminal missing", terminal_missing),
        ("terminal mismatched", terminal_mismatched),
    ):
        if not count:
            continue
        if qualifier.startswith("unresolved"):
            warnings.append(
                f"Fitting state preserved {count} {qualifier} intent references. "
                "Duplicate-copy safety remains blocked by character and canonical "
                "content until reconciliation."
            )
        else:
            warnings.append(
                f"Fitting state dropped {count} {qualifier} intent references."
            )
    intents = list(_bounded_completed_history(tuple(retained_intents), now))
    return (
        FittingsState(
            entries=tuple(entries),
            collections=tuple(collections),
            presences=tuple(presences),
            snapshots=tuple(snapshots),
            intents=tuple(intents),
        ),
        tuple(warnings),
    )


def _validate_datetime_value(
    value: object, label: str, *, required: bool = True
) -> None:
    if value is None and not required:
        return
    if not isinstance(value, datetime):
        raise ValueError(f"{label} must be a datetime.")


def _validate_presence_value(
    presence: object,
    entries: dict[str, LibraryEntry],
    cache: dict[tuple[int, tuple[RemoteItem, ...]], CanonicalContent],
) -> None:
    if not isinstance(presence, Presence):
        raise ValueError("Presence has the wrong type.")
    entry = entries.get(presence.library_entry_id)
    if entry is None:
        raise ValueError("Presence references a missing library entry.")
    _positive_int(presence.character_id, "Presence character ID")
    _positive_int(presence.remote_fitting_id, "Presence remote fitting ID")
    _text(
        presence.source_name,
        "Presence source name",
        contracts.MAX_NAME_CHARS,
        required=True,
    )
    _text(
        presence.source_description,
        "Presence source description",
        contracts.MAX_DESCRIPTION_CHARS,
    )
    _validate_template_value(
        entry.content, presence.source_template, "Presence source template", cache
    )
    _validate_datetime_value(presence.first_seen_utc, "Presence first-seen time")
    _text(
        presence.discovered_batch_id,
        "Presence discovery batch ID",
        MAX_BATCH_ID_CHARS,
        required=True,
    )
    _validate_datetime_value(presence.last_confirmed_utc, "Presence confirmation time")


def _validate_snapshot_value(snapshot: object) -> None:
    if not isinstance(snapshot, CharacterSnapshot):
        raise ValueError("Character snapshot has the wrong type.")
    _positive_int(snapshot.character_id, "Snapshot character ID")
    _validate_datetime_value(
        snapshot.fetched_utc, "Snapshot fetch time", required=False
    )
    _text(snapshot.etag, "Snapshot ETag", MAX_ETAG_CHARS)
    _text(snapshot.error, "Snapshot error", MAX_ERROR_CHARS)


def _validate_intent_value(intent: object) -> None:
    if not isinstance(intent, WriteIntent):
        raise ValueError("Write intent has the wrong type.")
    if intent.status not in INTENT_STATUSES:
        raise ValueError("Write intent has an invalid status.")
    _identifier(intent.operation_id, "Operation ID")
    _positive_int(intent.character_id, "Intent character ID")
    if intent.library_entry_id or not intent.unresolved:
        _identifier(intent.library_entry_id, "Intent library entry ID")
    _validate_content_value(intent.content)
    _validate_datetime_value(intent.created_utc, "Intent creation time")
    _validate_datetime_value(intent.sent_utc, "Intent sent time", required=False)
    _validate_datetime_value(
        intent.completed_utc, "Intent completion time", required=False
    )
    _optional_positive_int(intent.remote_fitting_id, "Intent remote fitting ID")
    _text(intent.error, "Intent error", MAX_ERROR_CHARS)


def _validate_state(state: FittingsState) -> None:
    if not isinstance(state, FittingsState):
        raise ValueError("Fitting state has the wrong type.")
    if len(state.entries) > contracts.MAX_LIBRARY_ENTRIES:
        raise ValueError(
            f"Fitting state supports at most {contracts.MAX_LIBRARY_ENTRIES} library entries."
        )
    if len(state.collections) > contracts.MAX_COLLECTIONS:
        raise ValueError(
            f"Fitting state supports at most {contracts.MAX_COLLECTIONS} collections."
        )

    entry_ids = set()
    template_cache: dict[tuple[int, tuple[RemoteItem, ...]], CanonicalContent] = {}
    for entry in state.entries:
        if not isinstance(entry, LibraryEntry):
            raise ValueError("Library entry has the wrong type.")
        _identifier(entry.id, "Library entry ID")
        if entry.id in entry_ids:
            raise ValueError("Library entry IDs must be unique.")
        entry_ids.add(entry.id)
        _validate_content_value(entry.content)
        _positive_int(entry.fingerprint_version, "Fingerprint version")
        _text(entry.digest, "Fingerprint digest", 256, required=True)
        _validate_template_value(
            entry.content, entry.source_template, "Source template", template_cache
        )
        if entry.deployment_template is not None:
            _validate_template_value(
                entry.content,
                entry.deployment_template,
                "Deployment template",
                template_cache,
                deployable=True,
            )
        _text(
            entry.preferred_name,
            "Preferred name",
            contracts.MAX_NAME_CHARS,
            required=True,
        )
        _text(
            entry.preferred_description,
            "Preferred description",
            contracts.MAX_DESCRIPTION_CHARS,
        )
        if len(entry.aliases) > contracts.MAX_ALIASES_PER_ENTRY:
            raise ValueError(
                f"A library entry supports at most {contracts.MAX_ALIASES_PER_ENTRY} aliases."
            )
        if not entry.aliases:
            raise ValueError("A library entry must retain at least one alias.")
        for alias in entry.aliases:
            _validate_alias_value(alias, entry.content, template_cache)
        _validate_datetime_value(entry.created_utc, "Entry creation time")
        _validate_datetime_value(entry.updated_utc, "Entry update time")

    collection_ids = set()
    for collection in state.collections:
        _identifier(collection.id, "Collection ID")
        if collection.id in collection_ids:
            raise ValueError("Collection IDs must be unique.")
        collection_ids.add(collection.id)
        _text(
            collection.name,
            "Collection name",
            contracts.MAX_COLLECTION_NAME_CHARS,
            required=True,
        )
    for entry in state.entries:
        if len(set(entry.collection_ids)) != len(entry.collection_ids):
            raise ValueError("Collection membership IDs must be unique per entry.")
        if not set(entry.collection_ids) <= collection_ids:
            raise ValueError("Library entry references a missing collection.")
    validate_supersession_graph(state.entries)

    presence_keys = set()
    entries = {entry.id: entry for entry in state.entries}
    for item in state.presences:
        _validate_presence_value(item, entries, template_cache)
        key = item.character_id, item.remote_fitting_id
        if key in presence_keys:
            raise ValueError("Presence identities must be unique.")
        presence_keys.add(key)

    snapshot_ids = set()
    for item in state.snapshots:
        _validate_snapshot_value(item)
        if item.character_id in snapshot_ids:
            raise ValueError("Snapshot character IDs must be unique.")
        snapshot_ids.add(item.character_id)

    intent_keys = set()
    for item in state.intents:
        key = _intent_identity(item)
        if key in intent_keys:
            raise ValueError("Write intent identities must be unique.")
        intent_keys.add(key)
        _validate_intent_value(item)
        entry = entries.get(item.library_entry_id)
        if item.unresolved and (entry is None or item.content != entry.content):
            continue
        if entry is None:
            raise ValueError("Write intent references a missing library entry.")
        if item.content != entry.content:
            raise ValueError("Write intent content does not match its library entry.")


def _read_bounded(path: Path) -> str:
    limit = contracts.MAX_STATE_BYTES
    if path.stat().st_size > limit:
        raise ValueError(f"{path.name} exceeds the fitting state limit.")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"{path.name} exceeds the fitting state limit.")
    return data.decode("utf-8")


def _read_document(path: Path) -> tuple[FittingsState, tuple[str, ...]]:
    return _from_dict(json.loads(_read_bounded(path)), datetime.now(UTC))


def _preserve_corrupt(path: Path) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S") + f"{int(time.time() * 1000) % 1000:03d}"
    target = path.with_name(f"{path.name}.corrupt-{stamp}")
    suffix = 0
    while target.exists():
        suffix += 1
        target = path.with_name(f"{path.name}.corrupt-{stamp}-{suffix}")
    try:
        os.replace(path, target)
    except OSError:
        return ""
    return target.name


def _read_backup_with_retry(
    backup: Path,
) -> tuple[FittingsState, tuple[str, ...]]:
    try:
        return _read_document(backup)
    except OSError:
        # A scanner or backup tool can briefly hold a good file without
        # sharing read access on Windows. One short retry matches Skills'
        # recovery behavior without turning a persistent error into a stall.
        time.sleep(0.05)
        return _read_document(backup)


def _recover_missing_primary(
    path: Path, backup: Path
) -> tuple[FittingsState, tuple[str, ...]]:
    try:
        recovered, row_warnings = _read_backup_with_retry(backup)
    except (OSError, ValueError, RecursionError) as exc:
        return FittingsState(), (
            f"{path.name} was missing and {backup.name} could not be read ({exc}); starting with an empty fitting library.",
        )
    try:
        save_fittings(path, recovered)
    except (OSError, ValueError) as exc:
        return recovered, (
            *row_warnings,
            f"{path.name} was missing and was read from {backup.name}, but the recovery could not be saved ({exc}).",
        )
    return recovered, (
        *row_warnings,
        f"{path.name} was missing and was recovered from {backup.name}.",
    )


def _recover_corrupt_primary(path: Path) -> tuple[FittingsState, tuple[str, ...]]:
    preserved = _preserve_corrupt(path)
    backup = path.with_name(path.name + ".bak")
    try:
        recovered, row_warnings = _read_backup_with_retry(backup)
    except (OSError, ValueError, RecursionError) as exc:
        return FittingsState(), (
            f"{path.name} could not be read and was preserved as {preserved or 'a copy'}; its backup could not be recovered ({exc}). Starting with an empty fitting library.",
        )
    if not preserved:
        return recovered, (
            *row_warnings,
            f"Recovered {path.name} from {backup.name}, but the corrupt primary could not be moved aside and remains in place.",
        )
    try:
        save_fittings(path, recovered)
    except (OSError, ValueError) as exc:
        return recovered, (
            *row_warnings,
            f"Recovered {path.name} from {backup.name}, but the recovery could not be saved ({exc}); the corrupt file was preserved as {preserved}.",
        )
    return recovered, (
        *row_warnings,
        f"Recovered {path.name} from {backup.name}; the corrupt file was preserved as {preserved}.",
    )


def load_fittings(path: Path) -> tuple[FittingsState, tuple[str, ...]]:
    """Load local fitting state, recovering one backup and never raising."""
    path = Path(path)
    try:
        return _read_document(path)
    except FileNotFoundError:
        backup = path.with_name(path.name + ".bak")
        try:
            backup.stat()
        except FileNotFoundError:
            return FittingsState(), ()
        except OSError as exc:
            return FittingsState(), (
                f"{path.name} could not be read ({exc}); starting with an empty fitting library.",
            )
        return _recover_missing_primary(path, backup)
    except OSError as exc:
        return FittingsState(), (
            f"{path.name} could not be read ({exc}); starting with an empty fitting library.",
        )
    except (ValueError, RecursionError):
        return _recover_corrupt_primary(path)


def save_fittings(
    path: Path,
    state: FittingsState,
    *,
    now: Callable[[], datetime] | None = None,
) -> None:
    """Validate and atomically publish fitting state with one sibling backup."""
    _validate_state(state)
    timestamp = (now or (lambda: datetime.now(UTC)))()
    document = json.dumps(_to_dict(state, timestamp), indent=2)
    if len(document.encode("utf-8")) > contracts.MAX_STATE_BYTES:
        raise ValueError("Fitting document exceeds the fitting state limit.")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_name(path.name + ".bak")
    staging = path.with_name(path.name + ".new")
    atomicio.write_atomic(staging, document)
    if path.exists():
        with contextlib.suppress(OSError):
            os.replace(path, backup)
    try:
        atomicio.replace_with_retry(str(staging), path)
    except BaseException:
        with contextlib.suppress(OSError):
            staging.unlink()
        raise
    if backup.exists():
        with contextlib.suppress(OSError):
            os.chmod(backup, stat_module.S_IMODE(path.stat().st_mode))
