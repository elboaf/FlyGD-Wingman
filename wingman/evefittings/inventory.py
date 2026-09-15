"""Strict, public-only inventory resolution for fitting clipboard operations.

The caller serializes operations and owns worker lifetime. Caches retain verified
metadata only, never clipboard text or library state. EsiClient owns transport
retries; stop admission is checked around each bounded client call, not inside
that shared transport's retry ladder.
"""

from __future__ import annotations

import http.client
import unicodedata
from collections import OrderedDict
from collections.abc import Callable

from ..eveesi import EsiClient
from . import contracts
from .eft import (
    EftError,
    InventorySnapshot,
    InventoryType,
    ParsedEft,
    _export_template,
    _name_key,
    _text_name,
)
from .model import LibraryEntry

MAX_BATCH = 1000
MAX_CACHED_TYPES = 4096
MAX_CACHED_GROUPS = 4096
# Bounds external arrays retained as immutable effects, not response documents.
MAX_TYPE_EFFECTS = 4096


def _id(value: object, label: str) -> int:
    if type(value) is not int or not 0 < value <= contracts.MAX_EFT_QUANTITY:
        raise EftError("invalid_metadata", f"Invalid {label} in inventory response.")
    return value


def _name(value: object) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise EftError(
            "invalid_metadata", "Inventory response contains an invalid name."
        )
    return _text_name(value)


def _published(raw: dict) -> None:
    if raw.get("published") is not True:
        raise EftError("invalid_metadata", "Inventory type/group must be published.")


class InventoryResolver:
    def __init__(self, client: EsiClient, *, stopping: Callable[[], bool]):
        self._client = client
        self._stopping = stopping
        self._types: OrderedDict[int, InventoryType] = OrderedDict()
        # Only category IDs survive group validation; large group member lists
        # and response descriptions never become a cache memory multiplier.
        self._groups: OrderedDict[int, int] = OrderedDict()

    def _check_stopping(self) -> None:
        if self._stopping():
            raise EftError("stopping", "Inventory lookup is stopping.")

    def _request(self, path: str, body: list | None = None):
        self._check_stopping()
        try:
            response = (
                self._client.get(path, token=None)
                if body is None
                else self._client.post(path, body, token=None)
            )
        except (OSError, ValueError, RecursionError, http.client.HTTPException) as exc:
            raise EftError(
                "inventory_request",
                f"Inventory lookup failed for {path}: {str(exc)[:512]}",
            ) from exc
        self._check_stopping()
        if response.status != 200:
            raise EftError(
                "inventory_request",
                f"Inventory lookup failed for {path} ({response.status}): {response.error}",
            )
        return response.data

    def _type(self, type_id: int, expected_name: str) -> InventoryType:
        self._check_stopping()
        cached = self._types.get(type_id)
        if cached is not None:
            if _name_key(cached.name) != _name_key(expected_name):
                raise EftError(
                    "invalid_metadata", "Conflicting cached inventory name binding."
                )
            self._types.move_to_end(type_id)
            return cached
        raw = self._request(f"/universe/types/{type_id}")
        if not isinstance(raw, dict) or _id(raw.get("type_id"), "type ID") != type_id:
            raise EftError(
                "invalid_metadata",
                "Inventory response does not match the requested type ID.",
            )
        name = _name(raw.get("name"))
        if _name_key(name) != _name_key(expected_name):
            raise EftError(
                "invalid_metadata",
                "Verified type name does not match the requested inventory name.",
            )
        _published(raw)
        group_id = _id(raw.get("group_id"), "group ID")
        effects = raw.get("dogma_effects")
        if not isinstance(effects, list) or len(effects) > MAX_TYPE_EFFECTS:
            raise EftError(
                "invalid_metadata", "Missing or oversized dogma effects metadata."
            )
        effect_ids = set()
        for effect in effects:
            if (
                not isinstance(effect, dict)
                or type(effect.get("is_default")) is not bool
            ):
                raise EftError("invalid_metadata", "Malformed dogma effect metadata.")
            effect_id = _id(effect.get("effect_id"), "effect ID")
            if effect_id in effect_ids:
                raise EftError("invalid_metadata", "Duplicate dogma effect metadata.")
            effect_ids.add(effect_id)
        category = self._groups.get(group_id)
        if category is None:
            group = self._request(f"/universe/groups/{group_id}")
            if (
                not isinstance(group, dict)
                or _id(group.get("group_id"), "group ID") != group_id
            ):
                raise EftError(
                    "invalid_metadata",
                    "Inventory group response does not match the requested group.",
                )
            _published(group)
            category = _id(group.get("category_id"), "category ID")
            self._groups[group_id] = category
            while len(self._groups) > MAX_CACHED_GROUPS:
                self._groups.popitem(last=False)
        else:
            self._groups.move_to_end(group_id)
        result = InventoryType(
            type_id, name, group_id, category, True, frozenset(effect_ids)
        )
        # Same normalized name cannot silently change ID across requests.
        if any(
            _name_key(t.name) == _name_key(name) and t.type_id != type_id
            for t in self._types.values()
        ):
            raise EftError(
                "invalid_metadata", "Conflicting verified inventory name binding."
            )
        self._types[type_id] = result
        while len(self._types) > MAX_CACHED_TYPES:
            self._types.popitem(last=False)
        return result

    def for_import(self, parsed: ParsedEft) -> InventorySnapshot:
        self._check_stopping()
        requested = {}
        for name, number in [
            (parsed.ship_name, parsed.header_line_number),
            *(
                (name, line.line_number)
                for line in parsed.lines
                for name in (line.type_name, line.charge_name)
                if name is not None
            ),
        ]:
            requested.setdefault(
                _name_key(name), (unicodedata.normalize("NFC", name.strip()), number)
            )
        cached = {_name_key(t.name): t for t in self._types.values()}
        found = {key: cached[key] for key in requested if key in cached}
        missing = [key for key in requested if key not in found]
        for start in range(0, len(missing), MAX_BATCH):
            batch = missing[start : start + MAX_BATCH]
            data = self._request("/universe/ids", [requested[key][0] for key in batch])
            if not isinstance(data, dict):
                raise EftError(
                    "invalid_metadata", "Inventory IDs response must be an object."
                )
            rows = data.get("inventory_types", [])
            if not isinstance(rows, list) or len(rows) > len(batch):
                raise EftError(
                    "invalid_metadata",
                    "Inventory IDs response has malformed or extra results.",
                )
            bindings = {}
            ids = set()
            for row in rows:
                if not isinstance(row, dict):
                    raise EftError(
                        "invalid_metadata", "Inventory ID result must be an object."
                    )
                type_id = _id(row.get("id"), "type ID")
                name = _name(row.get("name"))
                key = _name_key(name)
                if key not in batch or key in bindings or type_id in ids:
                    raise EftError(
                        "invalid_metadata",
                        "Conflicting or unrequested inventory name result.",
                    )
                bindings[key] = (type_id, name)
                ids.add(type_id)
            for key in batch:
                name, number = requested[key]
                if key not in bindings:
                    raise EftError(
                        "unresolved_name",
                        f"Inventory name {name!r} could not be resolved.",
                        line_number=number,
                    )
            for key, (type_id, name) in bindings.items():
                try:
                    found[key] = self._type(type_id, name)
                except EftError as exc:
                    raise EftError(
                        exc.code, exc.message, line_number=requested[key][1]
                    ) from exc
        return self._snapshot(found.values())

    def for_export(self, entry: LibraryEntry) -> InventorySnapshot:
        self._check_stopping()
        template = _export_template(entry)
        requested = sorted(
            {entry.content.ship_type_id} | {row.type_id for row in template}
        )
        found = {
            type_id: self._types[type_id]
            for type_id in requested
            if type_id in self._types
        }
        missing = [type_id for type_id in requested if type_id not in found]
        for start in range(0, len(missing), MAX_BATCH):
            batch = missing[start : start + MAX_BATCH]
            rows = self._request("/universe/names", batch)
            if not isinstance(rows, list) or len(rows) != len(batch):
                raise EftError(
                    "invalid_metadata",
                    "Inventory names response must match the requested IDs.",
                )
            names = {}
            for row in rows:
                if not isinstance(row, dict) or row.get("category") != "inventory_type":
                    raise EftError(
                        "invalid_metadata", "Expected inventory-type names only."
                    )
                type_id = _id(row.get("id"), "type ID")
                if type_id not in batch or type_id in names:
                    raise EftError(
                        "invalid_metadata",
                        "Duplicate or unrequested inventory type ID.",
                    )
                names[type_id] = _name(row.get("name"))
            for type_id, name in names.items():
                found[type_id] = self._type(type_id, name)
        return self._snapshot(found.values())

    def _snapshot(self, records) -> InventorySnapshot:
        self._check_stopping()
        types = tuple(sorted(records, key=lambda item: item.type_id))
        bindings = {}
        seen_ids = set()
        for item in types:
            key = _name_key(item.name)
            if key in bindings or item.type_id in seen_ids:
                raise EftError(
                    "invalid_metadata", "Conflicting inventory snapshot bindings."
                )
            bindings[key] = item.type_id
            seen_ids.add(item.type_id)
            if item.type_id in self._types:
                self._types.move_to_end(item.type_id)
        return InventorySnapshot(types, tuple(sorted(bindings.items())))
