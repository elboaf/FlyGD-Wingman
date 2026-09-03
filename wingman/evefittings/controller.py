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


def _noop_alert(_kind: str, _title: str, _body: str) -> None:
    pass


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
            for character_id in targets:
                if self._stopping.is_set():
                    break
                character_result = self._refresh_one(character_id, batch_id)
                type_ids.update(character_result.pop("_type_ids", ()))
                results.append(character_result)
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
