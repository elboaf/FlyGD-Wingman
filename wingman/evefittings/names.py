"""Bounded, rebuildable inventory type-ID display names.

Type IDs remain authoritative fitting identity.  This cache is unauthenticated
and cosmetic: every read, request, or write failure degrades to ``Type 123`` and
must never roll back a fitting import.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Iterable, Mapping
from pathlib import Path

from .. import atomicio

logger = logging.getLogger(__name__)

CACHE_VERSION = 1
MAX_BATCH = 1000
MAX_ENTRIES = 100_000
MAX_NAME_CHARS = 256
MAX_CACHE_BYTES = 8 * 1024 * 1024
NAMES_PATH = "/universe/names"


def _type_id(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _name(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > MAX_NAME_CHARS:
        return None
    return cleaned


class TypeNameCache:
    """A thread-safe bounded mapping whose complete contents may be rebuilt."""

    def __init__(self, mapping: Mapping[int, str] | None = None) -> None:
        self._lock = threading.RLock()
        self._names: dict[int, str] = {}
        if mapping:
            self.merge(mapping)

    def merge(self, mapping: Mapping[int, str]) -> int:
        added = 0
        with self._lock:
            for raw_id, raw_name in mapping.items():
                if len(self._names) >= MAX_ENTRIES:
                    break
                type_id = _type_id(raw_id)
                name = _name(raw_name)
                if type_id is None or name is None or type_id in self._names:
                    continue
                self._names[type_id] = name
                added += 1
        return added

    def type_names(self) -> dict[int, str]:
        with self._lock:
            return dict(self._names)

    def label(self, type_id: int) -> str:
        with self._lock:
            name = self._names.get(type_id)
        return name if name is not None else f"Type {type_id}"[:MAX_NAME_CHARS]

    def missing(self, type_ids: Iterable[object]) -> tuple[int, ...]:
        with self._lock:
            available = max(0, MAX_ENTRIES - len(self._names))
            known = set(self._names)
        result = []
        seen = set()
        for raw in type_ids:
            type_id = _type_id(raw)
            if (
                type_id is None
                or type_id in known
                or type_id in seen
                or len(result) >= available
            ):
                continue
            seen.add(type_id)
            result.append(type_id)
        return tuple(result)

    def resolve_missing(self, type_ids: Iterable[object], client) -> bool:
        """Resolve uncached IDs through bounded unauthenticated POST batches."""
        pending = self.missing(type_ids)
        added = 0
        for start in range(0, len(pending), MAX_BATCH):
            batch = pending[start : start + MAX_BATCH]
            try:
                response = client.post(NAMES_PATH, list(batch), token=None)
            except Exception:
                # Offline and teardown failures are ordinary for cosmetic data;
                # debug logging keeps caller bugs diagnosable without noise.
                logger.debug("Fitting type-name batch lookup failed", exc_info=True)
                continue
            data = getattr(response, "data", None)
            if getattr(response, "status", None) != 200 or not isinstance(data, list):
                continue
            requested = set(batch)
            found = {}
            for item in data:
                if not isinstance(item, dict):
                    continue
                type_id = _type_id(item.get("id"))
                name = _name(item.get("name"))
                if (
                    item.get("category") != "inventory_type"
                    or type_id not in requested
                    or name is None
                ):
                    continue
                found[type_id] = name
            added += self.merge(found)
        return bool(added)


def save(path: Path, cache: TypeNameCache) -> None:
    """Atomically save the bounded cache; no backup is required to rebuild it."""
    document = {
        "version": CACHE_VERSION,
        "entries": [
            {"type_id": type_id, "name": name}
            for type_id, name in sorted(cache.type_names().items())
        ],
    }
    encoded = json.dumps(document, indent=2)
    if len(encoded.encode("utf-8")) > MAX_CACHE_BYTES:
        raise ValueError("Type-name cache exceeds its file-size limit.")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomicio.write_atomic(path, encoded)


def load(path: Path) -> tuple[TypeNameCache, tuple[str, ...]]:
    """Load a cache, returning an empty rebuildable mapping on every failure."""
    path = Path(path)
    try:
        if path.stat().st_size > MAX_CACHE_BYTES:
            raise ValueError("file exceeds the type-name cache limit")
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("version") != CACHE_VERSION:
            raise ValueError("unrecognised type-name cache version")
        entries = raw.get("entries")
        if not isinstance(entries, list):
            raise ValueError("type-name cache entries must be a list")
        cache = TypeNameCache()
        for item in entries:
            if not isinstance(item, dict):
                continue
            type_id = _type_id(item.get("type_id"))
            name = _name(item.get("name"))
            if type_id is not None and name is not None:
                cache.merge({type_id: name})
        return cache, ()
    except FileNotFoundError:
        return TypeNameCache(), ()
    except (OSError, ValueError, RecursionError) as exc:
        return TypeNameCache(), (
            f"{path.name} could not be read ({exc}); type names will be resolved again.",
        )
