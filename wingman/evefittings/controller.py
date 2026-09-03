"""Single-writer owner for fitting refreshes and the consolidated library.

Remote snapshots are committed only while the shared character lifecycle lease
is held.  The feature lock is always acquired inside that lease, never the
other way around, so refresh, global forget, and later fitting writes share one
lock order.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from ..eveauth import application
from ..eveauth.controller import MutationResult
from ..eveesi import EsiClient
from . import contracts, names, store
from .model import (
    FINGERPRINT_VERSION,
    CharacterSnapshot,
    Collection,
    FittingsState,
    LibraryEntry,
    Presence,
    RemoteFitting,
    SourceAlias,
    canonical_equal,
    canonicalize,
    fingerprint,
    new_library_entry,
    retain_aliases,
    validate_remote_snapshot,
    validate_supersession,
)

logger = logging.getLogger(__name__)

MSG_REAUTH = "Re-authenticate this EVE character to refresh fittings."
MSG_SAVE_FAILED = "The fitting refresh could not be saved."
_MAX_ERROR_CHARS = store.MAX_ERROR_CHARS


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _bounded_error(value: object) -> str:
    text = str(value or "Fitting refresh failed.")
    return text[:_MAX_ERROR_CHARS]


def _noop_changed(_payload: dict) -> None:
    pass


def _noop_progress(_payload: dict) -> None:
    pass


def _noop_alert(_kind: str, _title: str, _body: str) -> None:
    pass


def _iso(value: datetime | None) -> str:
    return "" if value is None else value.astimezone(UTC).isoformat()


# Rail order for the workspace's collection summaries. "all"/"unfiled"/
# "superseded" are derived scopes, never persisted Collection rows -- see
# the design doc's "Unfiled is a derived view ... not a reserved mutable
# collection."
_ALL_SCOPE = "all"
_UNFILED_SCOPE = "unfiled"
_SUPERSEDED_SCOPE = "superseded"


class FittingsController:
    """The only runtime writer of ``eve_fittings.json``."""

    def __init__(
        self,
        *,
        state_path,
        names_path,
        authority,
        client=None,
        changed: Callable[[dict], None] = _noop_changed,
        progress: Callable[[dict], None] = _noop_progress,
        alert: Callable[[str, str, str], None] = _noop_alert,
        now: Callable[[], datetime] = _utcnow,
        save_state=store.save_fittings,
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
        batch_id_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
    ) -> None:
        self._state_path = Path(state_path)
        self._names_path = Path(names_path)
        self._authority = authority
        self._client = client or EsiClient(user_agent=application.USER_AGENT)
        self._changed = changed
        self._progress = progress
        self._alert = alert
        self._now = now
        self._save_state = save_state
        self._id_factory = id_factory
        self._batch_id_factory = batch_id_factory

        self._lock = threading.RLock()
        self._refresh_gate = threading.Lock()
        self._stopping = threading.Event()
        self._state, warnings = store.load_fittings(self._state_path)
        self._names, name_warnings = names.load(self._names_path)
        self._load_warnings = [*warnings, *name_warnings]

    @property
    def state(self) -> FittingsState:
        """Return the current immutable aggregate for local query adapters."""
        with self._lock:
            return self._state

    @property
    def load_warnings(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._load_warnings)

    def character_status(self, character_id: int) -> CharacterSnapshot:
        with self._lock:
            return next(
                (
                    item
                    for item in self._state.snapshots
                    if item.character_id == character_id
                ),
                CharacterSnapshot(character_id=character_id),
            )

    def type_name(self, type_id: int) -> str:
        return self._names.label(type_id)

    def refresh(self, character_ids: Iterable[int] | None = None) -> dict:
        """Refresh selected or all enabled characters, sequentially.

        A concurrent request is refused rather than queued.  This keeps a click
        from silently scheduling a second complete ESI pass behind the first.
        """
        if self._stopping.is_set():
            return {
                "ok": False,
                "busy": False,
                "batch_id": "",
                "characters": [],
                "error": "The fitting subsystem is shutting down.",
            }
        if not self._refresh_gate.acquire(blocking=False):
            return {
                "ok": False,
                "busy": True,
                "batch_id": "",
                "characters": [],
                "error": "A fitting refresh is already in progress.",
            }
        try:
            targets = self._refresh_targets(character_ids)
            batch_id = str(self._batch_id_factory())[: store.MAX_BATCH_ID_CHARS]
            if not batch_id:
                batch_id = uuid.uuid4().hex
            results = []
            type_ids = set()
            total = len(targets)
            for index, character_id in enumerate(targets, start=1):
                if self._stopping.is_set():
                    break
                character_result = self._refresh_one(character_id, batch_id)
                type_ids.update(character_result.pop("_type_ids", ()))
                results.append(character_result)
                self._notify_progress(
                    {
                        "character_id": character_id,
                        "completed": index,
                        "total": total,
                        "error": character_result["error"],
                    }
                )
            # Cosmetic and unauthenticated. This deliberately runs only after
            # every lifecycle-gated snapshot transaction has completed.
            self._enrich_names(type_ids)
            return {
                "ok": len(results) == len(targets)
                and all(item["ok"] for item in results),
                "busy": False,
                "batch_id": batch_id,
                "characters": results,
                "error": next((item["error"] for item in results if item["error"]), ""),
            }
        finally:
            self._refresh_gate.release()

    def _refresh_targets(self, character_ids: Iterable[int] | None) -> tuple[int, ...]:
        if character_ids is None:
            source = (
                character.character_id for character in self._authority.characters
            )
        else:
            source = character_ids
        targets = []
        seen = set()
        for raw in source:
            if isinstance(raw, bool):
                continue
            try:
                character_id = int(raw)
            except (TypeError, ValueError):
                continue
            if character_id <= 0 or character_id in seen:
                continue
            seen.add(character_id)
            if (
                self._authority.capability_status(character_id, application.FITTINGS)
                == "enabled"
            ):
                targets.append(character_id)
        return tuple(targets)

    def _refresh_one(self, character_id: int, batch_id: str) -> dict:
        try:
            # Lock order is lifecycle -> feature.  No state lock is held while
            # asking authority for this gate.
            with self._authority.lifecycle(character_id, application.FITTINGS):
                return self._refresh_one_leased(character_id, batch_id)
        except KeyError:
            return self._result(character_id, False, "Unknown EVE character.")
        except PermissionError:
            self._commit_failure(character_id, MSG_REAUTH)
            return self._result(character_id, False, MSG_REAUTH)
        except Exception as exc:
            # One broken character must not abort the sequential pass for all
            # characters behind it.
            message = _bounded_error(exc)
            logger.warning("Fitting refresh failed for %s", character_id, exc_info=True)
            self._commit_failure(character_id, message)
            return self._result(character_id, False, message)

    def _refresh_one_leased(self, character_id: int, batch_id: str) -> dict:
        with self._lock:
            snapshot = self._snapshot_locked(character_id)
            etag = snapshot.etag if snapshot is not None else ""

        response, error = self._authorised_get(character_id, etag)
        if response is None:
            self._commit_failure(character_id, error)
            return self._result(character_id, False, error)

        timestamp = self._now()
        if response.not_modified:
            with self._lock:
                current = self._snapshot_locked(character_id)
                if current is None or current.fetched_utc is None:
                    error = "ESI returned 304 without a retained fitting snapshot."
                    self._commit_failure_locked(character_id, error)
                    return self._result(character_id, False, error)
                candidate = self._confirmed_not_modified_locked(
                    character_id, timestamp, response.etag or current.etag
                )
                if not self._publish_locked(candidate):
                    return self._result(character_id, False, MSG_SAVE_FAILED)
                type_ids = self._type_ids_for_character_locked(character_id)
            result = self._result(character_id, True, "", not_modified=True)
            result["_type_ids"] = type_ids
            return result

        if response.status != 200:
            error = _bounded_error(
                f"ESI request failed ({response.status}): {response.error}"
            )
            self._commit_failure(character_id, error)
            return self._result(character_id, False, error)

        try:
            fittings = validate_remote_snapshot(response.data)
        except (ValueError, RecursionError) as exc:
            error = _bounded_error(exc)
            self._commit_failure(character_id, error)
            return self._result(character_id, False, error)

        with self._lock:
            candidate = self._import_locked(
                character_id,
                fittings,
                batch_id=batch_id,
                timestamp=timestamp,
                etag=response.etag,
            )
            if not self._publish_locked(candidate):
                return self._result(character_id, False, MSG_SAVE_FAILED)
        result = self._result(character_id, True, "")
        result["_type_ids"] = tuple(
            {fitting.ship_type_id for fitting in fittings}
            | {item.type_id for fitting in fittings for item in fitting.items}
        )
        return result

    def _enrich_names(self, type_ids: Iterable[int]) -> None:
        missing = set(self._names.missing(type_ids))
        if not missing or not self._names.resolve_missing(missing, self._client):
            return
        added = sorted(missing & self._names.type_names().keys())
        try:
            names.save(self._names_path, self._names)
        except (OSError, ValueError):
            # The cache is reconstructable and already updated in memory. A
            # failed cosmetic save cannot downgrade the committed import.
            logger.warning("Could not save fitting type names", exc_info=True)
        try:
            self._changed({"reason": "type_names", "type_ids": added})
        except Exception:
            # Delivery is cosmetic and may race page/window teardown.
            logger.debug(
                "Fitting type-name update could not be delivered", exc_info=True
            )

    def _authorised_get(self, character_id: int, etag: str):
        token_result = self._authority.access_token(character_id, application.FITTINGS)
        token = token_result.token
        if token is None:
            return None, _bounded_error(token_result.error or MSG_REAUTH)

        path = contracts.GET_PATH.format(character_id=character_id)
        try:
            response = self._client.get(path, token=token, etag=etag or None)
        except (OSError, ValueError, RecursionError) as exc:
            return None, _bounded_error(exc)
        if response.status == 401:
            token_result = self._authority.access_token(
                character_id,
                application.FITTINGS,
                rejected_token=token,
            )
            if token_result.token is None:
                return None, _bounded_error(token_result.error or MSG_REAUTH)
            try:
                response = self._client.get(
                    path,
                    token=token_result.token,
                    etag=etag or None,
                )
            except (OSError, ValueError, RecursionError) as exc:
                return None, _bounded_error(exc)
            if response.status == 401:
                return None, MSG_REAUTH
        if response.status == 403:
            # Endpoint status is not an OAuth verdict.  Authority retains the
            # shared grant, which may still be valid for Skills.
            return None, MSG_REAUTH
        if response.status not in {200, 304}:
            return None, _bounded_error(
                f"ESI request failed ({response.status}): {response.error}"
            )
        return response, ""

    def _import_locked(
        self,
        character_id: int,
        fittings: tuple[RemoteFitting, ...],
        *,
        batch_id: str,
        timestamp: datetime,
        etag: str,
    ) -> FittingsState:
        entries = list(self._state.entries)
        positions = {entry.id: index for index, entry in enumerate(entries)}
        versions = {entry.fingerprint_version for entry in entries}
        versions.add(FINGERPRINT_VERSION)
        digest_index: dict[tuple[int, str], list[str]] = {}
        for entry in entries:
            digest_index.setdefault(
                (entry.fingerprint_version, entry.digest), []
            ).append(entry.id)

        previous = {
            item.remote_fitting_id: item
            for item in self._state.presences
            if item.character_id == character_id
        }
        presences = [
            item for item in self._state.presences if item.character_id != character_id
        ]

        for fitting in fittings:
            content = canonicalize(fitting)
            match = self._find_content_match(
                content, entries, positions, digest_index, versions
            )
            if match is None:
                match = new_library_entry(
                    fitting,
                    entry_id=self._id_factory(),
                    now=timestamp,
                )
                positions[match.id] = len(entries)
                entries.append(match)
                versions.add(match.fingerprint_version)
                digest_index.setdefault(
                    (match.fingerprint_version, match.digest), []
                ).append(match.id)
            else:
                alias = SourceAlias(fitting.name, fitting.description, fitting.items)
                aliases = retain_aliases(
                    (*match.aliases, alias),
                    preferred_name=match.preferred_name,
                    preferred_description=match.preferred_description,
                )
                if aliases != match.aliases:
                    match = replace(match, aliases=aliases, updated_utc=timestamp)
                    entries[positions[match.id]] = match

            old = previous.get(fitting.fitting_id)
            same_presence = old is not None and old.library_entry_id == match.id
            presences.append(
                Presence(
                    character_id=character_id,
                    remote_fitting_id=fitting.fitting_id,
                    library_entry_id=match.id,
                    source_name=fitting.name,
                    source_description=fitting.description,
                    source_template=fitting.items,
                    first_seen_utc=(old.first_seen_utc if same_presence else timestamp),
                    discovered_batch_id=(
                        old.discovered_batch_id if same_presence else batch_id
                    ),
                    last_confirmed_utc=timestamp,
                )
            )

        snapshots = (
            *(
                item
                for item in self._state.snapshots
                if item.character_id != character_id
            ),
            CharacterSnapshot(
                character_id=character_id,
                fetched_utc=timestamp,
                etag=etag,
                error="",
            ),
        )
        return replace(
            self._state,
            entries=tuple(entries),
            presences=tuple(presences),
            snapshots=snapshots,
        )

    @staticmethod
    def _find_content_match(
        content,
        entries: list[LibraryEntry],
        positions: dict[str, int],
        digest_index: dict[tuple[int, str], list[str]],
        versions: set[int],
    ) -> LibraryEntry | None:
        for version in sorted(versions):
            digest = fingerprint(content, version=version)
            for entry_id in digest_index.get((version, digest), ()):
                entry = entries[positions[entry_id]]
                # The digest narrows candidates only.  Full canonical equality
                # remains the identity verdict even under a hash collision.
                if canonical_equal(entry.content, content, version=version):
                    return entry
        return None

    def _type_ids_for_character_locked(self, character_id: int) -> tuple[int, ...]:
        entry_ids = {
            item.library_entry_id
            for item in self._state.presences
            if item.character_id == character_id
        }
        entries = (entry for entry in self._state.entries if entry.id in entry_ids)
        return tuple(
            {
                type_id
                for entry in entries
                for type_id in (
                    entry.content.ship_type_id,
                    *(item.type_id for item in entry.content.items),
                )
            }
        )

    def _confirmed_not_modified_locked(
        self, character_id: int, timestamp: datetime, etag: str
    ) -> FittingsState:
        presences = tuple(
            replace(item, last_confirmed_utc=timestamp)
            if item.character_id == character_id
            else item
            for item in self._state.presences
        )
        snapshots = tuple(
            replace(item, fetched_utc=timestamp, etag=etag, error="")
            if item.character_id == character_id
            else item
            for item in self._state.snapshots
        )
        return replace(self._state, presences=presences, snapshots=snapshots)

    def _commit_failure(self, character_id: int, error: str) -> None:
        with self._lock:
            self._commit_failure_locked(character_id, error)

    def _commit_failure_locked(self, character_id: int, error: str) -> None:
        current = self._snapshot_locked(character_id)
        fetched = current.fetched_utc if current is not None else None
        etag = current.etag if current is not None else ""
        if fetched is None:
            confirmations = [
                item.last_confirmed_utc
                for item in self._state.presences
                if item.character_id == character_id
            ]
            fetched = max(confirmations, default=None)
        failed = CharacterSnapshot(
            character_id=character_id,
            fetched_utc=fetched,
            etag=etag,
            error=_bounded_error(error),
        )
        snapshots = (
            *(
                item
                for item in self._state.snapshots
                if item.character_id != character_id
            ),
            failed,
        )
        self._publish_locked(replace(self._state, snapshots=snapshots))

    def _publish_locked(self, candidate: FittingsState) -> bool:
        try:
            self._save_state(self._state_path, candidate)
        except (OSError, ValueError):
            logger.warning("Could not save fitting state", exc_info=True)
            return False
        self._state = candidate
        return True

    def _snapshot_locked(self, character_id: int) -> CharacterSnapshot | None:
        return next(
            (
                item
                for item in self._state.snapshots
                if item.character_id == character_id
            ),
            None,
        )

    @staticmethod
    def _result(
        character_id: int, ok: bool, error: str, *, not_modified: bool = False
    ) -> dict:
        return {
            "character_id": character_id,
            "ok": ok,
            "not_modified": not_modified,
            "error": _bounded_error(error) if error else "",
        }

    def _notify_changed(self, payload: dict) -> None:
        try:
            self._changed(payload)
        except Exception:
            # Delivery is cosmetic and may race page/window teardown; a
            # dropped notification never rolls back the mutation it follows.
            logger.debug(
                "Fitting change notification could not be delivered", exc_info=True
            )

    def _notify_progress(self, payload: dict) -> None:
        try:
            self._progress(payload)
        except Exception:
            logger.debug(
                "Fitting refresh progress could not be delivered", exc_info=True
            )

    # ----- workspace queries ----------------------------------------------
    #
    # Search, collection selection, sorting, and pagination are backend
    # queries -- the design doc is explicit that the catalog may hold
    # thousands of entries and the route must never rebuild or send the
    # full library. Row SELECTION stays page-owned; nothing here reads or
    # remembers which rows a caller has checked, and a summary row never
    # carries the full detail a caller did not ask for.

    def workspace(self, filters: dict | None = None) -> dict:
        """One bounded page plus rail/roster summaries for the route."""
        collection_id, search, ship_type_id, page = self._parsed_filters(filters)
        # Authority is never consulted while self._lock is held -- the same
        # lock-order rule _refresh_one and _authorised_get already follow.
        authority_characters = self._authority.characters
        auth_in_progress = self._authority.auth_in_progress
        with self._lock:
            state = self._state
            refreshing = self._refresh_gate.locked()
            load_warnings = list(self._load_warnings)
            scoped = self._scoped_entries_locked(state, collection_id)
            entries = self._searched_entries_locked(scoped, search, ship_type_id)
            entries = sorted(
                entries, key=lambda entry: (entry.preferred_name.casefold(), entry.id)
            )
            total = len(entries)
            start = (page - 1) * contracts.PAGE_SIZE
            page_entries = entries[start : start + contracts.PAGE_SIZE]
            presence_counts = self._presence_counts_locked(state)
            rows = [
                self._summary_row(entry, presence_counts.get(entry.id, 0))
                for entry in page_entries
            ]
            collections = self._collection_summaries_locked(state)
            # Ship options for the current COLLECTION scope, ahead of search
            # and the ship filter itself -- so narrowing by name or ship does
            # not also shrink the dropdown that offers the other ships to
            # pick from.
            ships = self._ship_options_locked(scoped)
        characters = [
            self._character_summary(character, state)
            for character in authority_characters
        ]
        return {
            "available": True,
            "warnings": load_warnings,
            "collections": collections,
            "characters": characters,
            "ships": ships,
            "rows": rows,
            "total": total,
            "page": page,
            "page_size": contracts.PAGE_SIZE,
            "filters": {
                "collection_id": collection_id,
                "search": search,
                "ship_type_id": ship_type_id,
            },
            "auth_configured": application.is_configured(),
            "auth_in_progress": auth_in_progress,
            "refreshing": refreshing,
        }

    def detail(self, entry_id: object) -> dict | None:
        """One expanded fitting, or None if it does not exist.

        Never a page of anything -- a caller that wants a list asks
        :meth:`workspace` instead.
        """
        if not isinstance(entry_id, str) or not entry_id:
            return None
        with self._lock:
            state = self._state
            entry = next((e for e in state.entries if e.id == entry_id), None)
            if entry is None:
                return None
            presences = [
                item for item in state.presences if item.library_entry_id == entry_id
            ]
        authority_characters = self._authority.characters
        character_names = {
            character.character_id: character.character_name
            for character in authority_characters
        }
        return {
            "id": entry.id,
            "name": entry.preferred_name,
            "description": entry.preferred_description,
            "ship_type_id": entry.content.ship_type_id,
            "ship_name": self._names.label(entry.content.ship_type_id),
            "items": [
                {
                    "location": item.location,
                    "type_id": item.type_id,
                    "type_name": self._names.label(item.type_id),
                    "quantity": item.quantity,
                }
                for item in entry.content.items
            ],
            "deployable": entry.deployment_template is not None,
            "collection_ids": list(entry.collection_ids),
            "superseded_by": entry.superseded_by,
            "aliases": [
                {"name": alias.name, "description": alias.description}
                for alias in entry.aliases
            ],
            "presences": sorted(
                (
                    {
                        "character_id": item.character_id,
                        "character_name": character_names.get(item.character_id, ""),
                        "source_name": item.source_name,
                        "first_seen_utc": _iso(item.first_seen_utc),
                        "last_confirmed_utc": _iso(item.last_confirmed_utc),
                        "discovered_batch_id": item.discovered_batch_id,
                    }
                    for item in presences
                ),
                key=lambda row: (row["character_name"].casefold(), row["character_id"]),
            ),
            "created_utc": _iso(entry.created_utc),
            "updated_utc": _iso(entry.updated_utc),
        }

    @staticmethod
    def _parsed_filters(filters: object) -> tuple[str, str, int | None, int]:
        raw = filters if isinstance(filters, dict) else {}
        collection_id = raw.get("collection_id")
        if not isinstance(collection_id, str) or not collection_id:
            collection_id = _ALL_SCOPE
        search = raw.get("search")
        # Bounded against pathological input; this is a transient query
        # argument, never a persisted value.
        search = search[:200] if isinstance(search, str) else ""
        ship_type_id = raw.get("ship_type_id")
        if (
            isinstance(ship_type_id, bool)
            or not isinstance(ship_type_id, int)
            or ship_type_id <= 0
        ):
            ship_type_id = None
        page = raw.get("page")
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            page = 1
        return collection_id, search, ship_type_id, page

    @staticmethod
    def _scoped_entries_locked(
        state: FittingsState, collection_id: str
    ) -> list[LibraryEntry]:
        if collection_id == _ALL_SCOPE:
            return list(state.entries)
        if collection_id == _UNFILED_SCOPE:
            return [entry for entry in state.entries if entry.is_unfiled]
        if collection_id == _SUPERSEDED_SCOPE:
            return [entry for entry in state.entries if entry.superseded_by is not None]
        return [
            entry for entry in state.entries if collection_id in entry.collection_ids
        ]

    def _searched_entries_locked(
        self, entries: list[LibraryEntry], search: str, ship_type_id: int | None
    ) -> list[LibraryEntry]:
        if ship_type_id is not None:
            entries = [
                entry for entry in entries if entry.content.ship_type_id == ship_type_id
            ]
        needle = search.strip().casefold()
        if not needle:
            return entries
        return [entry for entry in entries if self._matches_search(entry, needle)]

    def _matches_search(self, entry: LibraryEntry, needle: str) -> bool:
        if needle in entry.preferred_name.casefold():
            return True
        if needle in self._names.label(entry.content.ship_type_id).casefold():
            return True
        return any(needle in alias.name.casefold() for alias in entry.aliases)

    @staticmethod
    def _presence_counts_locked(state: FittingsState) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in state.presences:
            counts[item.library_entry_id] = counts.get(item.library_entry_id, 0) + 1
        return counts

    def _ship_options_locked(self, entries: list[LibraryEntry]) -> list[dict]:
        names: dict[int, str] = {}
        for entry in entries:
            names.setdefault(
                entry.content.ship_type_id,
                self._names.label(entry.content.ship_type_id),
            )
        return sorted(
            ({"type_id": type_id, "name": name} for type_id, name in names.items()),
            key=lambda ship: (ship["name"].casefold(), ship["type_id"]),
        )

    def _summary_row(self, entry: LibraryEntry, presence_count: int) -> dict:
        return {
            "id": entry.id,
            "name": entry.preferred_name,
            "ship_type_id": entry.content.ship_type_id,
            "ship_name": self._names.label(entry.content.ship_type_id),
            "collection_ids": list(entry.collection_ids),
            "is_unfiled": entry.is_unfiled,
            "superseded_by": entry.superseded_by,
            "presence_count": presence_count,
            "deployable": entry.deployment_template is not None,
            "updated_utc": _iso(entry.updated_utc),
        }

    @staticmethod
    def _collection_summaries_locked(state: FittingsState) -> list[dict]:
        unfiled = sum(1 for entry in state.entries if entry.is_unfiled)
        superseded = sum(
            1 for entry in state.entries if entry.superseded_by is not None
        )
        counts = dict.fromkeys((collection.id for collection in state.collections), 0)
        for entry in state.entries:
            for collection_id in entry.collection_ids:
                if collection_id in counts:
                    counts[collection_id] += 1
        return [
            {"id": _ALL_SCOPE, "name": "All fittings", "count": len(state.entries)},
            {"id": _UNFILED_SCOPE, "name": "Unfiled", "count": unfiled},
            {"id": _SUPERSEDED_SCOPE, "name": "Superseded", "count": superseded},
            *(
                {
                    "id": collection.id,
                    "name": collection.name,
                    "count": counts.get(collection.id, 0),
                }
                for collection in state.collections
            ),
        ]

    def _character_summary(self, character, state: FittingsState) -> dict:
        status = self._authority.capability_status(
            character.character_id, application.FITTINGS
        )
        snapshot = next(
            (
                item
                for item in state.snapshots
                if item.character_id == character.character_id
            ),
            None,
        )
        return {
            "character_id": character.character_id,
            "character_name": character.character_name,
            "status": status,
            "fetched_utc": _iso(snapshot.fetched_utc) if snapshot else "",
            "error": snapshot.error if snapshot else "",
            "stale": bool(snapshot.stale) if snapshot else False,
        }

    # ----- local curation ---------------------------------------------------
    #
    # Every mutation here validates, builds one candidate FittingsState,
    # publishes it under self._lock, and notifies onFittingsChanged so the
    # page re-queries the current view -- never a whole-library push.

    def create_collection(self, name: object) -> str:
        trimmed = name.strip() if isinstance(name, str) else ""
        if not trimmed or len(trimmed) > contracts.MAX_COLLECTION_NAME_CHARS:
            self._alert(
                "warning",
                "Collection not created",
                f"A collection name must be 1-{contracts.MAX_COLLECTION_NAME_CHARS} "
                "characters.",
            )
            return ""
        with self._lock:
            if len(self._state.collections) >= contracts.MAX_COLLECTIONS:
                self._alert(
                    "warning",
                    "Collection not created",
                    f"Wingman supports at most {contracts.MAX_COLLECTIONS} "
                    "collections.",
                )
                return ""
            collection_id = str(self._id_factory())
            candidate = replace(
                self._state,
                collections=(
                    *self._state.collections,
                    Collection(id=collection_id, name=trimmed),
                ),
            )
            if not self._publish_locked(candidate):
                self._alert(
                    "warning",
                    "Collection not saved",
                    "The new collection could not be saved.",
                )
                return ""
        self._notify_changed({"reason": "collection", "collection_id": collection_id})
        return collection_id

    def rename_collection(self, collection_id: object, name: object) -> bool:
        if not isinstance(collection_id, str) or not collection_id:
            return False
        trimmed = name.strip() if isinstance(name, str) else ""
        if not trimmed or len(trimmed) > contracts.MAX_COLLECTION_NAME_CHARS:
            self._alert(
                "warning",
                "Collection not renamed",
                f"A collection name must be 1-{contracts.MAX_COLLECTION_NAME_CHARS} "
                "characters.",
            )
            return False
        with self._lock:
            collections = list(self._state.collections)
            index = next(
                (i for i, item in enumerate(collections) if item.id == collection_id),
                None,
            )
            if index is None:
                return False
            collections[index] = replace(collections[index], name=trimmed)
            candidate = replace(self._state, collections=tuple(collections))
            if not self._publish_locked(candidate):
                self._alert(
                    "warning", "Collection not saved", "The rename could not be saved."
                )
                return False
        self._notify_changed({"reason": "collection", "collection_id": collection_id})
        return True

    def delete_collection(self, collection_id: object) -> bool:
        if not isinstance(collection_id, str) or not collection_id:
            return False
        with self._lock:
            collections = tuple(
                item for item in self._state.collections if item.id != collection_id
            )
            if len(collections) == len(self._state.collections):
                return False
            entries = tuple(
                replace(
                    entry,
                    collection_ids=tuple(
                        item for item in entry.collection_ids if item != collection_id
                    ),
                )
                if collection_id in entry.collection_ids
                else entry
                for entry in self._state.entries
            )
            candidate = replace(self._state, collections=collections, entries=entries)
            if not self._publish_locked(candidate):
                self._alert(
                    "warning",
                    "Collection not saved",
                    "The collection deletion could not be saved.",
                )
                return False
        self._notify_changed({"reason": "collection", "collection_id": collection_id})
        return True

    def update_metadata(
        self, entry_id: object, name: object, description: object
    ) -> bool:
        if not isinstance(entry_id, str) or not entry_id:
            return False
        if (
            not isinstance(name, str)
            or not name
            or len(name) > contracts.MAX_NAME_CHARS
        ):
            self._alert(
                "warning",
                "Fitting not updated",
                f"A fitting name must be 1-{contracts.MAX_NAME_CHARS} characters.",
            )
            return False
        if not isinstance(description, str) or len(description) > (
            contracts.MAX_DESCRIPTION_CHARS
        ):
            self._alert(
                "warning",
                "Fitting not updated",
                "A fitting description must be at most "
                f"{contracts.MAX_DESCRIPTION_CHARS} characters.",
            )
            return False
        with self._lock:
            entries = list(self._state.entries)
            index = next(
                (i for i, item in enumerate(entries) if item.id == entry_id), None
            )
            if index is None:
                return False
            entries[index] = replace(
                entries[index],
                preferred_name=name,
                preferred_description=description,
                updated_utc=self._now(),
            )
            candidate = replace(self._state, entries=tuple(entries))
            if not self._publish_locked(candidate):
                self._alert(
                    "warning",
                    "Fitting not saved",
                    "The metadata change could not be saved.",
                )
                return False
        self._notify_changed({"reason": "metadata", "entry_id": entry_id})
        return True

    def set_membership(
        self, entry_id: object, collection_id: object, member: object
    ) -> bool:
        if not isinstance(entry_id, str) or not entry_id:
            return False
        if not isinstance(collection_id, str) or not collection_id:
            return False
        with self._lock:
            if not any(item.id == collection_id for item in self._state.collections):
                return False
            entries = list(self._state.entries)
            index = next(
                (i for i, item in enumerate(entries) if item.id == entry_id), None
            )
            if index is None:
                return False
            current = entries[index]
            has = collection_id in current.collection_ids
            wanted = bool(member)
            if wanted == has:
                return True
            ids = (
                (*current.collection_ids, collection_id)
                if wanted
                else tuple(
                    item for item in current.collection_ids if item != collection_id
                )
            )
            entries[index] = replace(
                current, collection_ids=ids, updated_utc=self._now()
            )
            candidate = replace(self._state, entries=tuple(entries))
            if not self._publish_locked(candidate):
                self._alert(
                    "warning",
                    "Fitting not saved",
                    "The collection change could not be saved.",
                )
                return False
        self._notify_changed({"reason": "collection_membership", "entry_id": entry_id})
        return True

    def set_supersession(self, entry_id: object, superseded_by: object) -> bool:
        if not isinstance(entry_id, str) or not entry_id:
            return False
        if superseded_by is not None and (
            not isinstance(superseded_by, str) or not superseded_by
        ):
            return False
        with self._lock:
            try:
                validate_supersession(self._state.entries, entry_id, superseded_by)
            except ValueError as exc:
                self._alert("warning", "Supersession not set", str(exc))
                return False
            entries = tuple(
                replace(entry, superseded_by=superseded_by, updated_utc=self._now())
                if entry.id == entry_id
                else entry
                for entry in self._state.entries
            )
            candidate = replace(self._state, entries=entries)
            if not self._publish_locked(candidate):
                self._alert(
                    "warning",
                    "Fitting not saved",
                    "The supersession change could not be saved.",
                )
                return False
        self._notify_changed({"reason": "supersession", "entry_id": entry_id})
        return True

    def delete_entry(self, entry_id: object) -> bool:
        if not isinstance(entry_id, str) or not entry_id:
            return False
        with self._lock:
            if any(item.library_entry_id == entry_id for item in self._state.presences):
                self._alert(
                    "warning",
                    "Fitting not deleted",
                    "This fitting is still present on a character.",
                )
                return False
            if not any(item.id == entry_id for item in self._state.entries):
                return False
            entries = tuple(
                replace(item, superseded_by=None)
                if item.superseded_by == entry_id
                else item
                for item in self._state.entries
                if item.id != entry_id
            )
            # Completed write-intent HISTORY may reference a deleted entry
            # once the copy engine exists; unresolved intents are never
            # pruned, but a terminal record naming a now-gone entry cannot
            # pass save validation and would otherwise wedge every future
            # save.
            intents = tuple(
                item
                for item in self._state.intents
                if item.unresolved or item.library_entry_id != entry_id
            )
            candidate = replace(self._state, entries=entries, intents=intents)
            if not self._publish_locked(candidate):
                self._alert(
                    "warning", "Fitting not saved", "The deletion could not be saved."
                )
                return False
        self._notify_changed({"reason": "delete", "entry_id": entry_id})
        return True

    # ----- shared-authority participant ---------------------------------

    def prepare_forget(self, character_id: int) -> MutationResult:
        with self._lock:
            unresolved = any(
                item.character_id == character_id and item.unresolved
                for item in self._state.intents
            )
        if unresolved:
            return MutationResult(
                False,
                True,
                "Refresh this character to reconcile an unresolved fitting copy first.",
            )
        return MutationResult(True, True, "")

    def authority_removed(self, character_id: int) -> None:
        self._remove_character_state(character_id)

    def grant_invalidated(self, character_id: int) -> None:
        # A revoked grant makes the last remote snapshot unusable, but an
        # ambiguous create remains safety evidence. It must survive until a
        # later authoritative refresh can prove presence or absence.
        self._remove_character_state(character_id, preserve_intents=True)

    def reconcile_characters(self, characters) -> None:
        wanted = {character.character_id for character in characters}
        with self._lock:
            candidate = replace(
                self._state,
                presences=tuple(
                    item
                    for item in self._state.presences
                    if item.character_id in wanted
                ),
                snapshots=tuple(
                    item
                    for item in self._state.snapshots
                    if item.character_id in wanted
                ),
                intents=tuple(
                    item for item in self._state.intents if item.character_id in wanted
                ),
            )
            if candidate == self._state:
                return
            saved = self._publish_locked(candidate)
        if not saved:
            self._alert(
                "warning",
                "Fitting cleanup is not saved",
                "Character fitting state could not be reconciled and will be retried at startup.",
            )

    def _remove_character_state(
        self, character_id: int, *, preserve_intents: bool = False
    ) -> None:
        with self._lock:
            intents = (
                self._state.intents
                if preserve_intents
                else tuple(
                    item
                    for item in self._state.intents
                    if item.character_id != character_id
                )
            )
            candidate = replace(
                self._state,
                presences=tuple(
                    item
                    for item in self._state.presences
                    if item.character_id != character_id
                ),
                snapshots=tuple(
                    item
                    for item in self._state.snapshots
                    if item.character_id != character_id
                ),
                intents=intents,
            )
            if candidate == self._state:
                return
            saved = self._publish_locked(candidate)
        if not saved:
            self._alert(
                "warning",
                "Character cleanup is incomplete",
                "EVE authorization was removed, but fitting cleanup could not be saved.",
            )

    def shutdown(self) -> None:
        self._stopping.set()
