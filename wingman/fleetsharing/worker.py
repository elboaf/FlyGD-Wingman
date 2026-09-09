"""One cadence-aware owner of the fleet device, session, journals and transport.

Telemetry's dispatcher only replaces the latest immutable snapshot. Controls
likewise submit immutable values; none load state, unwrap a key, sign or send.
The non-daemon worker (or serialized iterate_once seam) does all I/O. A signed
attempt is durably allocated before dispatch, including refusals and lost replies.

Local Off inhibits immediately. Remote deletion, consent and new sessions are
never inferred from queue acceptance or transport failure. Lifecycle, identity,
session and relevant command fences surround dispatch and completion; abandoned
requests leave journals for reconciliation, not an obsolete acknowledgement.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import random
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from ..telemetry.model import FleetSnapshot
from . import crypto, projection
from . import protocol as p
from . import state as s
from .client import FleetRelayClient, FleetRelayError
from .config import resolve_relay_origin
from .model import FleetCatalogue, PublishRow
from .scheduling import OPERATIONS, Scheduler, Work

logger = logging.getLogger(__name__)
BASE_BACKOFF_S = 1.0
MAX_BACKOFF_S = 30.0
IDLE_POLL_S = 0.5
INERT_POLL_S = 15.0
CATALOGUE_REFRESH_INTERVAL_S = 60.0
SESSION_RENEWAL_INTERVAL_S = 600.0
MAX_SNAPSHOT_AGE_S = 5.0
HEARTBEAT_INTERVAL_S = 2.0
CAPABILITIES = (p.SHARED_CAPABILITY,)
# Only these classifications may reach status. Never render an exception body.
ERROR_CODES = frozenset(
    (
        "unauthorized",
        "forbidden",
        "conflict",
        "revision_replayed",
        "rate_limited",
        "transport_error",
        "server_error",
        "bad_request",
        "bad_headers",
        "not_found",
        "invalid_intent",
        "capability_required",
        "fleet_read_required",
        "update_required",
        "service_unavailable",
        "feature_disabled",
        "malformed_response",
        "protocol_mismatch",
    )
)


@dataclass(frozen=True)
class SharingMetadata:
    """Safe observations only. The binding fingerprints the SAVED key/origin."""

    loaded: bool = False
    binding: str | None = None
    paired_origin: str | None = None
    device_id: str | None = None
    has_session: bool = False
    session_expires_at: str | None = None
    feature_enabled: bool | None = None
    approved_capabilities: tuple[str, ...] | None = None
    session_approved_capabilities: tuple[str, ...] | None = None
    acknowledged_capabilities: tuple[str, ...] | None = None


@dataclass(frozen=True)
class PendingSourceStatus:
    source_id: str
    operation: str
    character_id: int | None
    stage: str


@dataclass(frozen=True)
class SharingStatus:
    state: Literal["stopped", "connecting", "active", "verifying", "refused", "error"]
    detail: str | None = None
    participation: str | None = None
    participation_intent_id: str | None = None
    participation_order: int = 0
    source_control: str | None = None
    pairing: str | None = None
    approval_url: str | None = None
    sources: p.Sources | None = None
    eligibility: p.Eligibility | None = None
    observed_participation: p.Participation | None = None
    local_inhibited: bool = False
    metadata: SharingMetadata = SharingMetadata()
    pending_sources: tuple[PendingSourceStatus, ...] = ()
    # Bounded session-only terminal results for absent IDs (not source history).
    source_results: tuple[PendingSourceStatus, ...] = ()
    order: int = 0
    pairing_action_id: str | None = None


@dataclass(frozen=True)
class RemoteEvent:
    rows: tuple[p.ObservedRemoteRow, ...]
    receipt_monotonic: float
    request_elapsed: float
    lifecycle_epoch: int
    identity_epoch: int
    kind: Literal["replace", "clear"]


@dataclass(frozen=True)
class _Command:
    sequence: int
    kind: str
    payload: object
    identity_epoch: int
    binding: str | None


@dataclass(frozen=True)
class _Fence:
    lifecycle: int
    identity: int
    session: str | None
    participation: int
    source: tuple[tuple[str, int], ...]


class _Obsolete(Exception):
    pass


class _PersistenceFailed(Exception):
    pass


def _noop_thread_factory(*, target, args, name, daemon):
    class _NoopThread:
        def __init__(self):
            self.daemon = daemon

        def start(self):
            pass

        def is_alive(self):
            return False

        def join(self, timeout=None):
            pass

    return _NoopThread()


def _no_op_save_state(_state):
    """Compatibility seam; production must supply the atomic file writer."""


class FleetSharingWorker:
    def __init__(
        self,
        *,
        load_state: Callable[[], s.SharingState],
        client_factory=FleetRelayClient,
        unwrap_private_key=s.unwrap_private_key,
        sharing_enabled=lambda: True,
        save_state=_no_op_save_state,
        wrap_private_key=s.wrap_private_key,
        _generate_private_key=crypto.generate_private_key,
        _thread_factory=threading.Thread,
        _clock=time.monotonic,
        _utc_clock=lambda: datetime.now(UTC),
        _jitter=random.random,
    ):
        self._load_state = load_state
        self._save_state = save_state
        self._client_factory = client_factory
        self._unwrap_private_key = unwrap_private_key
        self._wrap_private_key = wrap_private_key
        self._generate_private_key = _generate_private_key
        self._sharing_enabled = sharing_enabled
        self._thread_factory = _thread_factory
        self._clock = _clock
        self._utc_clock = _utc_clock
        self._jitter = _jitter
        self._lock = threading.Lock()
        self._status_lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._iteration_lock = threading.Lock()
        self._latest: tuple[FleetSnapshot, float] | None = None
        self._pending = threading.Event()
        self._commands: dict[str, _Command] = {}
        self._sequence = 0
        self._participation_generation = 0
        self._source_generations: dict[str, int] = {}
        self._identity_epoch = 0
        # Submission fences completions; only a durably changed key/origin
        # invalidates older queued controls (not a rejected/same-key upgrade).
        self._identity_floor = 0
        self._epoch = 0
        self._inhibit = False
        self._watch = False
        self._probe_queued = False
        self._probe_used = False
        self._restart_requested = False
        self._status = SharingStatus("stopped")
        self._durable_sources: tuple[PendingSourceStatus, ...] = ()
        self._pairing_action_id = None
        self._subscribers: dict[str, dict[object, Callable]] = {
            "status": {},
            "remote": {},
        }
        self._worker = None
        self._running = False
        self._stop_event = threading.Event()

        # Owner-only state, never reconstructed from a stale pass-local copy.
        self._state: s.SharingState | None = None
        self._client = None
        self._client_origin = None
        self._scheduler = Scheduler()
        self._local_retry_at = 0.0
        self._needs_device = True
        self._resume_metadata = False
        self._fresh_on: str | None = None
        self._part_observe = True
        self._needs_fresh_intent = False
        self._source_observe: set[str] = set()
        self._withdraw_needed = False
        self._catalogue: FleetCatalogue | None = None
        self._eligibility: p.Eligibility | None = None
        self._sources: p.Sources | None = None
        self._due = dict.fromkeys(
            ("device", "catalogue", "eligibility", "read", "sources"), 0.0
        )
        self._expiry_binding = None
        self._renew_at = 0.0
        self._expires_at = 0.0
        self._last_published: tuple[PublishRow, ...] = ()
        self._last_publish_at = 0.0
        self._pause_binding = None
        self._pause_until = 0.0

    def submit(self, snapshot: FleetSnapshot) -> None:
        with self._lock:
            self._latest = (snapshot, self._clock())
        self._pending.set()

    def _queue(self, key, kind, payload, *, binding=None):
        with self._lock:
            if binding is not None and binding != self._status.metadata.binding:
                return None
            if (
                kind == "source"
                and key not in self._commands
                and sum(c.kind == "source" for c in self._commands.values())
                >= p.MAX_SOURCE_INTENTS
            ):
                return None
            changes = {}
            if kind == "pairing":
                self._identity_epoch += 1
                self._inhibit = True
                changes = dict(
                    pairing="queued",
                    approval_url=None,
                    local_inhibited=True,
                    pairing_action_id=payload[2],
                )
            elif kind == "participation":
                self._participation_generation += 1
                self._inhibit = True
                changes = dict(
                    participation="queued",
                    local_inhibited=True,
                    eligibility=None,
                    participation_intent_id=payload.intent_id,
                    participation_order=self._sequence + 1,
                )
            elif kind == "source":
                source_id = payload.source_id
                self._source_generations[source_id] = (
                    self._source_generations.get(source_id, 0) + 1
                )
                changes = dict(
                    source_control="queued",
                    source_results=tuple(
                        item
                        for item in self._status.source_results
                        if item.source_id.lower() != source_id.lower()
                    ),
                )
            self._sequence += 1
            command = _Command(
                self._sequence, kind, payload, self._identity_epoch, binding
            )
            self._commands[key] = command
            # Publish queue status before the owner can consume this command.
            # Callbacks are deliberately deferred until BOTH locks are released.
            with self._status_lock:
                self._status = status = replace(
                    self._status,
                    **changes,
                    order=self._status.order + 1,
                    pending_sources=self._pending_sources_locked(),
                )
        self._pending.set()
        self._notify("status", status)
        return command

    def request_pairing(
        self, *, mode="initial", configured_origin=None, action_id=None
    ) -> bool:
        """Queue initial/retry, same-key upgrade, or explicitly authorized fresh setup.

        Fresh is admitted by the owner only after proved terminal auth or an
        explicit origin change. This never opens a browser; status exposes a
        validated URL only after the admission journal is durable.
        """
        if mode not in ("initial", "upgrade", "fresh") or (
            configured_origin is not None and not isinstance(configured_origin, str)
        ):
            return False
        if action_id is not None:
            try:
                p.uuid(action_id)
            except ValueError:
                return False
        accepted = (
            self._queue("pairing", "pairing", (mode, configured_origin, action_id))
            is not None
        )
        if accepted:
            self._clear_remote()
        return accepted

    def request_participation(self, enabled: bool) -> str | None:
        """Return an explicit intent UUID, not a durable or server acknowledgement."""
        if type(enabled) is not bool:
            return None
        intent = s.PendingParticipation(str(uuid4()), enabled)
        # New On remains inhibited until its fresh observation/CAS is known.
        if self._queue("participation", "participation", intent) is None:
            return None
        if not enabled:
            self._clear_remote()
        return intent.intent_id

    def request_source_start(
        self, character_id: int, character_link_epoch: str, *, binding=None
    ) -> str | None:
        """Create identity/time at the explicit action, never at a later retry."""
        try:
            command = p.StartSource(
                str(uuid4()),
                p.integer(character_id, 1, p.JS_SAFE_MAX),
                p.uuid(character_link_epoch),
                self._utc_text(),
            )
        except (ValueError, TypeError):
            return None
        return (
            command.source_id if self._queue_source(command, binding=binding) else None
        )

    def request_source_stop(
        self, source_id: str, *, expected_generation: int = 0, binding=None
    ) -> bool:
        try:
            command = p.StopSource(
                p.uuid(source_id).lower(),
                p.integer(expected_generation, 0, p.INT4_MAX - 1),
            )
        except ValueError:
            return False
        return self._queue_source(command, binding=binding)

    def _queue_source(self, command, *, binding=None):
        return (
            self._queue(
                "source:" + command.source_id, "source", command, binding=binding
            )
            is not None
        )

    @staticmethod
    def _source_summary(command, stage):
        return PendingSourceStatus(
            command.source_id,
            "start" if isinstance(command, p.StartSource) else "stop",
            command.character_id if isinstance(command, p.StartSource) else None,
            stage,
        )

    def _command_binding_current(self, command, metadata):
        # A queued setup reserves a future epoch before its key is saved. Bound
        # controls from the still-visible old identity must not inherit that key.
        return command.identity_epoch >= self._identity_floor and (
            command.binding is None or command.binding == metadata.binding
        )

    def _pending_sources_locked(self, metadata=None):
        metadata = metadata or self._status.metadata
        pending = {item.source_id.lower(): item for item in self._durable_sources}
        for command in self._commands.values():
            if command.kind == "source" and self._command_binding_current(
                command, metadata
            ):
                item = self._source_summary(command.payload, "queued")
                pending[item.source_id.lower()] = item
        return tuple(pending.values())

    def _project_saved(self):
        """Owner-only projection; queue threads merge against this immutable cache."""
        state = self._state
        binding = None
        if state.identity is not None:
            binding = hashlib.sha256(
                (
                    state.relay_origin + "\n" + state.identity.public_key_spki_b64
                ).encode()
            ).hexdigest()
        metadata = SharingMetadata(
            loaded=True,
            binding=binding,
            paired_origin=state.relay_origin,
            device_id=state.device_id,
            has_session=state.session_id is not None,
            session_expires_at=state.session_expires_at,
            feature_enabled=state.feature_enabled,
            approved_capabilities=state.approved_capabilities,
            session_approved_capabilities=state.session_approved_capabilities,
            acknowledged_capabilities=state.acknowledged_capabilities,
        )
        with self._lock:
            self._durable_sources = tuple(
                self._source_summary(command, "persisted")
                for command in state.pending_source_commands
            )
        changes = {}
        if self.status().metadata.binding != binding:
            changes = dict(
                sources=None,
                eligibility=None,
                source_results=(),
                observed_participation=state.observed_participation,
            )
        self._update_status(metadata=metadata, **changes)

    def set_source_watch(self, enabled: bool) -> bool:
        if type(enabled) is not bool:
            return False
        with self._lock:
            self._watch = enabled
        self._pending.set()
        return True

    def resume_pending(self) -> bool:
        """Queue ONE startup metadata probe, even Off. Never unwrap an idle key."""
        with self._lock:
            if self._probe_used:
                return False
            self._probe_used = self._probe_queued = True
        self._pending.set()
        return True

    def status(self) -> SharingStatus:
        with self._status_lock:
            return self._status

    def subscribe_status(self, callback: Callable[[SharingStatus], None]):
        return self._subscribe("status", callback)

    def subscribe_remote(self, callback: Callable[[RemoteEvent], None]):
        return self._subscribe("remote", callback)

    def _subscribe(self, kind, callback):
        token = object()
        with self._status_lock:
            self._subscribers[kind][token] = callback

        def unsubscribe():
            with self._status_lock:
                self._subscribers[kind].pop(token, None)

        return unsubscribe

    def _notify(self, kind, value):
        with self._status_lock:
            callbacks = tuple(self._subscribers[kind].values())
        for callback in callbacks:
            if kind == "status" and self.status() != value:
                break
            if kind == "remote" and value.kind == "replace":
                with self._lock:
                    obsolete = self._inhibit or (self._epoch, self._identity_epoch) != (
                        value.lifecycle_epoch,
                        value.identity_epoch,
                    )
                if obsolete:
                    break
            try:
                callback(value)
            except Exception:  # noqa: BLE001 - a subscriber cannot kill the single I/O owner
                logger.warning("Fleet sharing subscriber failed")

    def _update_status(self, *, fence=None, **changes):
        # Ingestion notifications share the submission lock: an old persisted
        # stage must not overwrite a replacement queued during a save/callback.
        with self._lock:
            if fence is not None and self._fence_locked() != fence:
                raise _Obsolete
            with self._status_lock:
                status = replace(
                    self._status,
                    **changes,
                    pending_sources=self._pending_sources_locked(
                        changes.get("metadata")
                    ),
                )
                changed = self._status != status
                if changed:
                    status = replace(status, order=self._status.order + 1)
                self._status = status
        if changed:
            self._notify("status", status)

    def _clear_remote(self):
        with self._lock:
            epoch, identity = self._epoch, self._identity_epoch
        self._notify(
            "remote", RemoteEvent((), self._clock(), 0, epoch, identity, "clear")
        )

    def start(self) -> bool:
        with self._lifecycle_lock:
            if self._running:
                return True
            if self._worker is not None and self._worker.is_alive():
                return False
            with self._lock:
                self._epoch += 1
                self._restart_requested = True
            self._running = True
            self._stop_event = threading.Event()
            try:
                worker = self._thread_factory(
                    target=self._run,
                    args=(self._stop_event,),
                    name="fleet-sharing-worker",
                    daemon=False,
                )
                self._worker = worker
                worker.start()
            except Exception:  # noqa: BLE001 - failed thread construction must leave a restartable owner
                self._running = False
                self._worker = None
                return False
            return True

    def stop(self, timeout: float = 5.0) -> bool:
        with self._lifecycle_lock:
            worker = self._worker
            self._running = False
            self._stop_event.set()
            with self._lock:
                self._epoch += 1
            self._pending.set()
        if worker is None:
            return True
        worker.join(timeout)
        with self._lifecycle_lock:
            if worker.is_alive():
                return False
            # A concurrent start after this join must keep its new reference.
            if self._worker is worker:
                self._worker = None
        return True

    def _run(self, stop_event):
        while not stop_event.is_set():
            self._pending.clear()
            with self._iteration_lock:
                if stop_event.is_set():
                    break
                wait, _ = self._iterate()
            self._pending.wait(wait)

    def iterate_once(self):
        with self._lifecycle_lock:
            if self._worker is not None and self._worker.is_alive():
                raise RuntimeError("iterate_once cannot run beside the sharing worker")
        with self._iteration_lock:
            with self._lifecycle_lock:
                if self._worker is not None and self._worker.is_alive():
                    raise RuntimeError(
                        "iterate_once cannot run beside the sharing worker"
                    )
            self._iterate()

    def _utc_now(self):
        try:
            now = self._utc_clock()
            if not isinstance(now, datetime) or now.tzinfo is None:
                raise ValueError
            return now.astimezone(UTC)
        except Exception:  # noqa: BLE001 - clock failures cannot extend consent or session authority
            raise ValueError("UTC clock unavailable") from None

    def _utc_text(self):
        return self._utc_now().isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def _remaining(self, text):
        return (
            datetime.fromisoformat(p.utc_date(text)) - self._utc_now()
        ).total_seconds()

    def _enabled(self):
        try:
            return bool(self._sharing_enabled())
        except Exception:  # noqa: BLE001 - preference access fails closed without affecting local telemetry
            return False

    def _fence_locked(self):
        return _Fence(
            self._epoch,
            self._identity_epoch,
            self._state.session_id if self._state else None,
            self._participation_generation,
            tuple(sorted(self._source_generations.items())),
        )

    def _fence(self):
        with self._lock:
            return self._fence_locked()

    def _check(self, fence, *, work=None):
        current = self._fence()
        if work is not None:
            with self._lock:
                queued = tuple(self._commands.values())
            if any(
                command.kind == "pairing"
                or (
                    command.kind == "participation"
                    and work.operation
                    in (
                        "fetch_device",
                        "acknowledge_capabilities",
                        "set_participation",
                        "read_snapshot",
                        "publish_snapshot",
                        "fetch_eligibility",
                    )
                )
                or (
                    command.kind == "source"
                    and (
                        work.operation == "fetch_sources"
                        or (
                            work.operation == "control_source"
                            and command.payload.source_id == work.payload.source_id
                        )
                    )
                )
                for command in queued
            ):
                raise _Obsolete
        if (current.lifecycle, current.identity, current.session) != (
            fence.lifecycle,
            fence.identity,
            fence.session,
        ):
            raise _Obsolete
        if current.participation != fence.participation and (
            work is None
            or work.operation
            in (
                "fetch_device",
                "acknowledge_capabilities",
                "set_participation",
                "read_snapshot",
                "publish_snapshot",
                "fetch_eligibility",
            )
        ):
            raise _Obsolete
        if current.source != fence.source and (
            work is None or work.operation in ("fetch_sources", "control_source")
        ):
            raise _Obsolete

    def _persist(self, candidate, fence, *, work=None):
        self._check(fence, work=work)
        try:
            self._save_state(candidate)
        except Exception:  # noqa: BLE001 - no network may follow a failed atomic journal write
            raise _PersistenceFailed from None
        # This is the only assignment of a successfully saved candidate. Queue
        # submission during a save is processed on the next serialized turn.
        if (candidate.identity, candidate.relay_origin) != (
            self._state.identity,
            self._state.relay_origin,
        ):
            self._identity_floor = fence.identity
        self._state = candidate
        self._project_saved()
        self._check(replace(fence, session=candidate.session_id), work=work)

    def _reset_session(self):
        self._needs_device = True
        self._part_observe = True
        self._source_observe.update(
            c.source_id for c in self._state.pending_source_commands
        )
        self._catalogue = self._eligibility = self._sources = None
        self._expiry_binding = None
        self._last_published = ()
        self._due = dict.fromkeys(self._due, 0.0)
        self._update_status(
            sources=None,
            eligibility=None,
            observed_participation=self._state.observed_participation,
        )

    def _load(self):
        if self._state is not None:
            return
        self._state = self._load_state()
        self._project_saved()
        # The previous process may have just completed an attempt. Its monotonic
        # clock cannot be persisted, so pay one conservative bucket interval on
        # startup rather than causing our own refusal after an immediate restart.
        if self._state.identity is not None:
            self._scheduler.deadlines["bootstrap"] = self._clock() + 1.0
            if self._state.last_revision:
                self._scheduler.deadlines["read"] = self._clock() + 0.5
                self._scheduler.deadlines["publication"] = self._clock() + 0.5
        self._reset_session()
        pending = self._state.pending_participation
        if pending is not None:
            self._withdraw_needed = not pending.enabled
            with self._lock:
                self._inhibit = True
            self._update_status(participation="persisted", local_inhibited=True)
        # An attempted pairing completion may have registered the key even if no
        # session was saved. Reconnect by proof rather than replaying one-use work.
        if (
            self._state.pending_pairing
            and self._state.pending_pairing.completion_attempted
        ):
            self._needs_device = True

    def _ingest(self):
        with self._lock:
            fence = self._fence_locked()
            # Validate the identity transition before deciding which controls
            # belong to it. Sequence order alone drops Stop queued before upgrade.
            commands = tuple(
                sorted(
                    self._commands.items(),
                    key=lambda item: (item[1].kind != "pairing", item[1].sequence),
                )
            )
        for key, command in commands:
            with self._lock:
                if self._commands.get(key) != command:
                    continue
            # Only our own session installation may advance this snapshot's
            # fence. Reentrant On/Off/Stop/setup submissions never may.
            fence = replace(fence, session=self._state.session_id)
            self._check(fence)
            if command.kind == "pairing":
                self._ingest_pairing(command, fence)
            elif self._command_binding_current(command, self.status().metadata):
                self._ingest_control(command, fence)
            self._drop_command(key, command)

    def _drop_command(self, key, command):
        with self._lock:
            if self._commands.get(key) == command:
                self._commands.pop(key)
        self._update_status()

    def _ingest_pairing(self, command, fence):
        mode, configured, action_id = command.payload
        state = self._state
        changed_origin = False
        try:
            if mode == "fresh" and configured is not None:
                origin = resolve_relay_origin(configured_origin=configured)
                changed_origin = origin != state.relay_origin
            else:
                origin = resolve_relay_origin(
                    paired_origin=state.relay_origin, configured_origin=configured
                )
        except ValueError:
            self._update_status(
                fence=fence, state="refused", detail="local_failure", pairing="rejected"
            )
            return
        terminal = state.auth_pause and state.auth_pause.result in (
            "device_revoked",
            "device_key_conflict",
        )
        if mode == "fresh" and not (terminal or changed_origin):
            self._update_status(
                fence=fence,
                state="refused",
                detail="fresh_key_not_authorized",
                pairing="rejected",
            )
            return
        if mode == "upgrade" and (state.identity is None or terminal):
            self._update_status(
                state="refused",
                detail="needs_fresh_key" if terminal else "needs_pairing",
                pairing="rejected",
                fence=fence,
            )
            return
        if (
            mode == "initial"
            and state.identity is not None
            and state.pending_pairing is None
        ):
            self._update_status(
                fence=fence,
                state="refused",
                detail="use_key_recovery",
                pairing="rejected",
            )
            return
        if state.identity is None or mode == "fresh":
            raw = self._generate_private_key()
            identity = s.DeviceIdentity(
                self._wrap_private_key(raw),
                crypto.canonical_device_public_key_b64(crypto.public_key_spki(raw)),
            )
            candidate = s.SharingState(
                identity=identity,
                relay_origin=origin,
                pending_pairing=s.PendingPairing(mode),
            )
        else:
            candidate = replace(
                s.replace_session(state, None),
                pending_pairing=s.PendingPairing(mode),
                pending_recovery=None,
                auth_pause=None,
            )
        self._persist(candidate, fence)
        self._reset_session()
        self._pairing_action_id = action_id
        self._update_status(
            fence=replace(fence, session=self._state.session_id),
            state="connecting",
            detail=None,
            pairing="persisted",
            approval_url=None,
        )

    def _ingest_control(self, command, fence):
        if self._state.identity is None:
            self._update_status(state="refused", detail="needs_pairing")
            return
        if command.kind == "participation":
            intent = command.payload
            self._persist(replace(self._state, pending_participation=intent), fence)
            self._fresh_on = intent.intent_id if intent.enabled else None
            self._needs_fresh_intent = False
            self._part_observe = self._needs_device = True
            self._withdraw_needed = not intent.enabled
            self._eligibility = None
            self._update_status(fence=fence, participation="persisted")
        else:
            incoming = command.payload
            commands = self._state.pending_source_commands
            old = next(
                (
                    c
                    for c in commands
                    if c.source_id.lower() == incoming.source_id.lower()
                ),
                None,
            )
            if isinstance(incoming, p.StopSource) and isinstance(old, p.StartSource):
                incoming = p.StopSource(old.source_id, 0)
            candidate = (
                *(
                    c
                    for c in commands
                    if c.source_id.lower() != incoming.source_id.lower()
                ),
                incoming,
            )
            if len(candidate) > p.MAX_SOURCE_INTENTS:
                self._update_status(state="error", detail="source_queue_full")
                return
            self._persist(
                replace(self._state, pending_source_commands=candidate), fence
            )
            if isinstance(incoming, p.StopSource) and incoming != old:
                self._source_observe.add(incoming.source_id)
            self._update_status(fence=fence, source_control="persisted")

    def _iterate(self):
        try:
            now = self._clock()
            if now < self._local_retry_at:
                return IDLE_POLL_S, False
            enabled = self._enabled()
            with self._lock:
                explicit = bool(self._commands) or self._watch or self._probe_queued
            pending = self._state and (
                self._state.pending_participation
                or self._state.pending_source_commands
                or self._state.pending_pairing
                or self._state.pending_recovery
            )
            if not (
                enabled
                or explicit
                or pending
                or self._withdraw_needed
                or self._resume_metadata
            ):
                return INERT_POLL_S, False
            self._load()
            with self._lock:
                self._probe_queued = False
                restart = self._restart_requested
                self._restart_requested = False
                retained = {c.source_id for c in self._state.pending_source_commands}
                retained.update(
                    c.payload.source_id
                    for c in self._commands.values()
                    if c.kind == "source"
                )
                self._source_generations = {
                    key: value
                    for key, value in self._source_generations.items()
                    if key in retained
                }
            if restart:
                self._reset_session()
            self._ingest()
            self._prune_source_work()
            fence = self._fence()
            work = self._work(enabled)
            chosen = self._scheduler.choose(tuple(work), self._clock())
            if chosen is not None:
                # Planning may durably replace our own expired session, but it
                # must not adopt the generation of a newly queued user control.
                self._execute(chosen, replace(fence, session=self._state.session_id))
            return IDLE_POLL_S, True
        except _Obsolete:
            # Persisted uncertainty is intentionally left for the next owner turn.
            return IDLE_POLL_S, True
        except _PersistenceFailed:
            self._local_retry_at = self._clock() + BASE_BACKOFF_S
            self._update_status(state="error", detail="persistence_failed")
            return BASE_BACKOFF_S, False
        except Exception:  # noqa: BLE001 - fail closed, without leaking key/response/exception context
            self._local_retry_at = self._clock() + BASE_BACKOFF_S
            self._update_status(state="error", detail="local_failure")
            return BASE_BACKOFF_S, False

    def _expiry(self):
        binding = (self._state.session_id, self._state.session_expires_at)
        if binding != self._expiry_binding:
            remaining = self._remaining(binding[1])
            self._expires_at = self._clock() + max(0, remaining)
            self._renew_at = self._clock() + max(
                0, min(SESSION_RENEWAL_INTERVAL_S, remaining - 60)
            )
            self._expiry_binding = binding

    def _work(self, enabled):
        state = self._state
        if state.identity is None or state.relay_origin is None:
            return ()
        with self._lock:
            watching, inhibited = self._watch, self._inhibit
        pending = (
            state.pending_participation
            or state.pending_source_commands
            or state.pending_pairing
            or state.pending_recovery
        )
        if not (
            enabled
            or watching
            or pending
            or self._withdraw_needed
            or self._resume_metadata
        ):
            return ()
        fence = self._fence()
        if state.auth_pause:
            pause = state.auth_pause
            if pause.retry_not_before is None:
                self._update_status(state="refused", detail="needs_fresh_key")
                return ()
            if pause != self._pause_binding:
                self._pause_binding = pause
                self._pause_until = self._clock() + max(
                    0, self._remaining(pause.retry_not_before)
                )
            if self._clock() < self._pause_until:
                self._update_status(state="refused", detail=pause.result)
                return ()
            self._persist(replace(state, auth_pause=None), fence)
            state = self._state
        pairing = state.pending_pairing
        if pairing:
            if pairing.completion_attempted:
                # A lost response may mean either registration or no commit at
                # all. Keep initial provenance for an explicit SAME-key retry;
                # a generic recovery 401 proves neither revocation nor consent.
                return self._recovery_work()
            if pairing.pairing_id is None:
                return (Work("begin_pairing", "pairing", priority=1),)
            if self._remaining(pairing.expires_at) <= 0:
                self._update_status(
                    state="refused",
                    detail="pairing_expired",
                    pairing="needs_retry",
                    approval_url=None,
                )
                return ()
            return (Work("complete_pairing", "pairing", priority=1),)
        if state.pending_recovery or not state.session_id:
            return self._recovery_work()
        if state.session_expires_at is not None:
            self._expiry()
            if self._clock() >= self._expires_at:
                self._persist(s.replace_session(state, None), fence)
                self._reset_session()
                return self._recovery_work()
        if self._needs_device or state.session_expires_at is None:
            return (Work("fetch_device", "device", priority=1),)
        if not state.feature_enabled:
            self._update_status(state="refused", detail="feature_disabled")
            return (
                Work("fetch_device", "device", due=self._due["device"], periodic=True),
            )
        if p.SHARED_CAPABILITY not in (state.approved_capabilities or ()):
            self._update_status(state="refused", detail="needs_upgrade")
            return ()
        if p.SHARED_CAPABILITY not in (state.session_approved_capabilities or ()):
            self._persist(s.replace_session(state, None), fence)
            self._reset_session()
            return self._recovery_work()
        if p.SHARED_CAPABILITY not in (state.acknowledged_capabilities or ()):
            return (Work("acknowledge_capabilities", "ack", priority=1),)
        work = []
        if self._withdraw_needed:
            work.append(Work("publish_snapshot", "withdraw", priority=0, payload=()))
        if self._clock() >= self._renew_at:
            work.append(Work("renew_session", "renew", due=self._renew_at, priority=1))
        intent = state.pending_participation
        if intent and not self._needs_fresh_intent:
            if self._part_observe:
                work.append(
                    Work(
                        "fetch_device",
                        "device",
                        priority=0 if not intent.enabled else 2,
                    )
                )
            elif intent.expected_generation is not None:
                work.append(
                    Work(
                        "set_participation",
                        "participation",
                        priority=0 if not intent.enabled else 2,
                        payload=intent,
                    )
                )
        for command in state.pending_source_commands:
            critical = isinstance(command, p.StopSource)
            if command.source_id in self._source_observe or (
                isinstance(command, p.StartSource)
                and self._remaining(command.intent_created_at) <= -60
            ):
                self._source_observe.add(command.source_id)
                work.append(
                    Work(
                        "fetch_sources",
                        "sources-reconcile",
                        priority=0 if critical else 2,
                    )
                )
            else:
                work.append(
                    Work(
                        "control_source",
                        self._source_work_key(command),
                        priority=0 if critical else 2,
                        payload=command,
                    )
                )
        if watching:
            work.append(
                Work(
                    "fetch_sources", "sources", due=self._due["sources"], periodic=True
                )
            )
        if (
            enabled
            and not inhibited
            and state.observed_participation
            and state.observed_participation.enabled
            and intent is None
        ):
            work.extend(
                (
                    Work(
                        "fetch_device", "device", due=self._due["device"], periodic=True
                    ),
                    Work(
                        "fetch_catalogue",
                        "catalogue",
                        due=self._due["catalogue"],
                        periodic=True,
                    ),
                    Work(
                        "fetch_eligibility",
                        "eligibility",
                        due=self._due["eligibility"],
                        periodic=True,
                    ),
                    Work("read_snapshot", "read", due=self._due["read"], periodic=True),
                )
            )
            rows = self._publication()
            if rows is not None and (
                rows != self._last_published
                or (
                    rows
                    and self._clock() - self._last_publish_at >= HEARTBEAT_INTERVAL_S
                )
            ):
                work.append(
                    Work(
                        "publish_snapshot",
                        "publication",
                        due=self._last_publish_at + HEARTBEAT_INTERVAL_S
                        if rows == self._last_published
                        else 0,
                        periodic=True,
                        payload=rows,
                        priority=0 if not rows else 2,
                    )
                )
        return tuple(work)

    @staticmethod
    def _source_work_key(command):
        # Stop supersedes Start, but repeated Stop/CAS rebasing is still the
        # SAME retry owner. Submission generations would let clicks defeat backoff.
        kind = "stop" if isinstance(command, p.StopSource) else "start"
        return "source:" + kind + ":" + command.source_id.lower()

    def _prune_source_work(self):
        self._scheduler.retain(
            "source:",
            {self._source_work_key(c) for c in self._state.pending_source_commands},
        )

    def _publication(self):
        if self._catalogue is None or self._eligibility is None:
            return None
        with self._lock:
            latest = self._latest
            if latest and self._clock() - latest[1] > MAX_SNAPSHOT_AGE_S:
                self._latest = latest = None
        if latest is None:
            return None
        eligible = {
            c.character_id
            for c in self._eligibility.characters
            if self._remaining(c.expires_at) > 0
        }
        if (
            self._eligibility.state != "ready"
            or self._eligibility.participation_generation
            != self._state.observed_participation.generation
        ):
            eligible = set()
        return tuple(
            row
            for row in projection.project_snapshot(latest[0], self._catalogue)
            if row.character_id in eligible
        )

    def _recovery_work(self):
        pending = self._state.pending_recovery
        fence = self._fence()
        if pending is not None:
            expired = (
                self._remaining(pending.challenge.expires_at) <= 0
                if pending.challenge
                else not -60 < self._remaining(pending.issued_at) <= 60
            )
            if expired:
                pending = None
        if pending is None:
            pending = s.PendingRecovery(secrets.token_urlsafe(32), self._utc_text())
            self._persist(replace(self._state, pending_recovery=pending), fence)
        operation = "complete_recovery" if pending.challenge else "begin_recovery"
        return (Work(operation, "recovery", priority=1),)

    def _execute(self, work, fence):
        self._check(fence, work=work)
        started = self._clock()
        sent = failed = False
        try:
            state = self._state
            origin = resolve_relay_origin(paired_origin=state.relay_origin)
            if self._client is None or self._client_origin != origin:
                self._client = self._client_factory(origin)
                self._client_origin = origin
            private_key = self._unwrap_private_key(
                state.identity.protected_private_key_b64
            )
            if (
                not isinstance(private_key, bytes)
                or len(private_key) != crypto.RAW_PRIVATE_KEY_BYTES
            ):
                raise ValueError("Key unavailable")
            args = {}
            operation = work.operation
            if OPERATIONS[operation] != "bootstrap":
                candidate = replace(
                    self._state, last_revision=self._state.last_revision + 1
                )
                if operation == "set_participation":
                    candidate = replace(
                        candidate,
                        pending_participation=replace(
                            candidate.pending_participation, attempted=True
                        ),
                    )
                self._persist(candidate, fence, work=work)
                args = {
                    "session_id": self._state.session_id,
                    "private_key": private_key,
                    "revision": self._state.last_revision,
                    "now": self._utc_now(),
                }
                if operation == "publish_snapshot":
                    args["rows"] = work.payload
                elif operation == "set_participation":
                    args.update(
                        enabled=work.payload.enabled,
                        expected_generation=work.payload.expected_generation,
                    )
                    self._part_observe = True
                elif operation == "control_source":
                    args["command"] = work.payload
                    self._source_observe.add(work.payload.source_id)
                elif operation == "acknowledge_capabilities":
                    args["capabilities"] = CAPABILITIES
            elif operation == "begin_recovery":
                pending = self._state.pending_recovery
                args = dict(
                    private_key=private_key,
                    request_id=pending.request_id,
                    issued_at=pending.issued_at,
                )
            elif operation == "complete_recovery":
                args = dict(
                    private_key=private_key,
                    challenge=self._state.pending_recovery.challenge,
                )
            elif operation == "begin_pairing":
                args = dict(
                    public_key_spki=base64.b64decode(
                        state.identity.public_key_spki_b64
                    ),
                    requested_capabilities=CAPABILITIES,
                )
            elif operation == "complete_pairing":
                pairing = self._state.pending_pairing
                self._persist(
                    replace(
                        self._state,
                        pending_pairing=replace(pairing, completion_attempted=True),
                    ),
                    fence,
                    work=work,
                )
                args = dict(
                    pairing_id=pairing.pairing_id,
                    challenge=crypto.pairing_challenge_preimage(pairing.pairing_id),
                    private_key=private_key,
                )
            self._check(fence, work=work)
            if (
                operation in ("read_snapshot", "publish_snapshot")
                and work.key != "withdraw"
            ):
                with self._lock:
                    inhibited = self._inhibit
                if inhibited or not self._enabled():
                    raise _Obsolete
            sent = True
            result = getattr(self._client, operation)(**args)
            self._check(fence, work=work)
            self._accept(work, result, fence, started)
        except FleetRelayError as exc:
            failed = True
            self._check(fence, work=work)
            self._relay_error(work, exc, fence)
        finally:
            if sent:
                self._scheduler.completed(
                    work,
                    self._clock(),
                    failed=failed,
                    jitter=self._jitter() if failed else 0,
                )
                # Completion may retire a journal (or be obsolete). Do not keep
                # historical UUID backoff, or resurrect it after reconciliation.
                self._prune_source_work()

    def _accept(self, work, result, fence, started):
        operation = work.operation
        if operation in ("fetch_device", "acknowledge_capabilities"):
            self._accept_device(result, fence, work)
        elif operation == "renew_session":
            self._persist(
                replace(self._state, session_expires_at=result), fence, work=work
            )
            self._expiry_binding = None
        elif operation == "fetch_catalogue":
            self._catalogue = result
            self._due["catalogue"] = self._clock() + CATALOGUE_REFRESH_INTERVAL_S
        elif operation == "fetch_eligibility":
            self._eligibility = result
            self._due["eligibility"] = self._clock() + 2.0
            self._update_status(eligibility=result)
        elif operation == "publish_snapshot":
            self._last_published = work.payload
            self._last_publish_at = self._clock()
            if work.key == "withdraw":
                self._withdraw_needed = False
        elif operation == "read_snapshot":
            self._due["read"] = self._clock() + 1.0
            self._notify(
                "remote",
                RemoteEvent(
                    result,
                    self._clock(),
                    max(0, self._clock() - started),
                    fence.lifecycle,
                    fence.identity,
                    "replace",
                ),
            )
        elif operation == "set_participation":
            self._persist(
                replace(
                    self._state,
                    observed_participation=result,
                    pending_participation=None,
                ),
                fence,
                work=work,
            )
            self._participation_ack(result.enabled)
        elif operation == "fetch_sources":
            self._accept_sources(result, fence, work)
        elif operation == "control_source":
            self._finish_source(work.payload, result, fence, work)
        elif operation == "begin_recovery":
            self._persist(
                replace(
                    self._state,
                    pending_recovery=replace(
                        self._state.pending_recovery, challenge=result
                    ),
                ),
                fence,
                work=work,
            )
        elif operation == "complete_recovery":
            self._accept_recovery(result, fence, work)
        elif operation == "begin_pairing":
            pairing = replace(
                self._state.pending_pairing,
                pairing_id=result.pairing_id,
                approval_url=result.approval_url,
                expires_at=result.expires_at,
            )
            self._persist(
                replace(self._state, pending_pairing=pairing), fence, work=work
            )
            self._update_status(
                fence=fence,
                pairing="awaiting_approval",
                approval_url=pairing.approval_url,
                pairing_action_id=self._pairing_action_id,
            )
        elif operation == "complete_pairing":
            candidate = replace(
                s.replace_session(self._state, result.session_id),
                pending_pairing=None,
                pending_recovery=None,
            )
            self._persist(candidate, fence, work=work)
            self._reset_session()
            self._resume_metadata = True
            self._update_status(pairing="acknowledged", approval_url=None)
        self._check(replace(fence, session=self._state.session_id), work=work)
        if not self._needs_fresh_intent and self._state.auth_pause is None:
            self._update_status(state="active", detail=None)

    def _accept_device(self, device, fence, work):
        candidate = replace(
            self._state,
            device_id=device.device_id,
            session_expires_at=device.session_expires_at,
            feature_enabled=device.feature_enabled,
            approved_capabilities=device.approved_capabilities,
            session_approved_capabilities=device.session_approved_capabilities,
            acknowledged_capabilities=device.acknowledged_capabilities,
            observed_participation=device.participation,
        )
        intent = candidate.pending_participation
        acknowledged = False
        if intent is not None:
            if (
                intent.enabled
                and intent.expected_generation is None
                and intent.intent_id != self._fresh_on
            ) or (
                intent.enabled
                and intent.expected_generation is not None
                and device.participation.generation > intent.expected_generation
                and not device.participation.enabled
            ):
                self._needs_fresh_intent = True
            elif device.participation.enabled == intent.enabled:
                candidate = replace(candidate, pending_participation=None)
                acknowledged = True
            elif not intent.enabled or intent.expected_generation is None:
                candidate = replace(
                    candidate,
                    pending_participation=replace(
                        intent,
                        expected_generation=device.participation.generation,
                        attempted=False,
                    ),
                )
        self._persist(candidate, fence, work=work)
        self._needs_device = self._part_observe = False
        self._resume_metadata = False
        self._due["device"] = self._clock() + 60.0
        self._expiry()
        if self._needs_fresh_intent:
            self._update_status(
                state="refused",
                detail="needs_fresh_intent",
                participation="needs_confirmation",
            )
        elif acknowledged:
            self._participation_ack(device.participation.enabled)
        elif intent is None and device.participation.enabled:
            with self._lock:
                self._inhibit = False
            self._update_status(local_inhibited=False)
        if not device.participation.enabled:
            self._eligibility = None
            self._clear_remote()
        self._update_status(observed_participation=device.participation)

    def _participation_ack(self, enabled):
        with self._lock:
            self._inhibit = not enabled
        self._fresh_on = None
        self._needs_fresh_intent = self._part_observe = False
        self._eligibility = None
        self._due["eligibility"] = 0
        self._update_status(
            participation="acknowledged",
            local_inhibited=not enabled,
            eligibility=None,
            observed_participation=self._state.observed_participation,
        )
        if not enabled:
            self._clear_remote()

    def _accept_sources(self, result, fence, work):
        commands = self._state.pending_source_commands
        updated = []
        clear = expired = False
        expired_results = []
        for command in commands:
            if command.source_id not in self._source_observe:
                updated.append(command)
                continue
            view = next(
                (
                    v
                    for v in result.sources
                    if v.source_id.lower() == command.source_id.lower()
                ),
                None,
            )
            if isinstance(command, p.StopSource):
                if view and view.state == "ended":
                    clear = True
                    continue
                updated.append(
                    p.StopSource(command.source_id, view.generation if view else 0)
                )
            elif view is None:
                if self._remaining(command.intent_created_at) > -60:
                    updated.append(command)
                else:
                    expired = True
                    expired_results.append(self._source_summary(command, "expired"))
            # An already admitted ID is acknowledged, even ended. An absent
            # expired Start is finished without ever minting another consent.
        self._persist(
            replace(self._state, pending_source_commands=tuple(updated)),
            fence,
            work=work,
        )
        self._source_observe.clear()
        if self._sources:
            live = {v.source_id for v in self._sources.sources if v.state != "ended"}
            current = {v.source_id for v in result.sources if v.state != "ended"}
            clear |= bool(live - current)
        self._sources = result
        self._due["sources"] = self._clock() + 2.0
        self._update_status(
            fence=fence,
            sources=result,
            source_results=(*self.status().source_results, *expired_results)[
                -p.MAX_SOURCE_INTENTS :
            ],
            source_control="persisted"
            if updated
            else "expired"
            if expired
            else "acknowledged",
        )
        if clear:
            self._clear_remote()

    def _finish_source(self, command, view, fence, work):
        commands = tuple(
            c
            for c in self._state.pending_source_commands
            if c.source_id.lower() != command.source_id.lower()
        )
        self._persist(
            replace(self._state, pending_source_commands=commands), fence, work=work
        )
        self._source_observe.discard(command.source_id)
        self._due["sources"] = 0
        # The individual response is an observation of THIS UUID, not every
        # queued row. Retain it until the next complete owned-source read.
        if self._sources is not None:
            self._sources = replace(
                self._sources,
                sources=(
                    *(
                        v
                        for v in self._sources.sources
                        if v.source_id.lower() != view.source_id.lower()
                    ),
                    view,
                ),
            )
        self._update_status(source_control="acknowledged", sources=self._sources)
        if view.state == "ended":
            self._clear_remote()

    def _accept_recovery(self, result, fence, work):
        if result.result == "reconnected":
            pairing = self._state.pending_pairing
            candidate = replace(
                s.replace_session(
                    self._state, result.session_id, expires_at=result.session_expires_at
                ),
                device_id=result.device_id,
                approved_capabilities=result.approved_capabilities,
                observed_participation=result.participation,
                pending_recovery=None,
                auth_pause=None,
                pending_pairing=None,
            )
            self._persist(candidate, fence, work=work)
            self._reset_session()
            if pairing is not None:
                self._resume_metadata = True
                self._update_status(
                    fence=replace(fence, session=self._state.session_id),
                    pairing="acknowledged",
                    approval_url=None,
                )
        else:
            deadline = None
            if result.retry_after_ms is not None:
                floor = 60 if result.result == "account_ineligible" else 1
                deadline = (
                    (
                        self._utc_now()
                        + timedelta(seconds=max(floor, result.retry_after_ms / 1000))
                    )
                    .isoformat(timespec="milliseconds")
                    .replace("+00:00", "Z")
                )
            self._persist(
                replace(
                    self._state,
                    pending_recovery=None,
                    auth_pause=s.AuthPause(result.result, deadline),
                ),
                fence,
                work=work,
            )
            self._update_status(
                state="refused",
                detail="needs_fresh_key"
                if result.requires_fresh_key_setup
                else result.result,
            )

    def _relay_error(self, work, exc, fence):
        code = exc.code if exc.code in ERROR_CODES else "server_error"
        self._update_status(state="error", detail=code)
        operation = work.operation
        if operation == "complete_pairing":
            if exc.status == 409:
                # Unapproved/expired/consumed is coarse conflict, NOT proof of
                # revocation. Polling remains bounded by the bootstrap scheduler.
                pairing = replace(
                    self._state.pending_pairing, completion_attempted=False
                )
                self._persist(
                    replace(self._state, pending_pairing=pairing), fence, work=work
                )
            return
        if (
            operation == "begin_recovery"
            and exc.status == 401
            and self._state.pending_pairing is not None
            and self._state.pending_pairing.mode == "initial"
        ):
            self._update_status(pairing="needs_retry", approval_url=None)
        if operation == "complete_recovery":
            # One-use completion might already have committed. A fresh challenge
            # with this registered key is the only safe way to learn a new session.
            self._persist(replace(self._state, pending_recovery=None), fence, work=work)
            return
        if exc.status == 401 and OPERATIONS[operation] != "bootstrap":
            self._persist(s.replace_session(self._state, None), fence, work=work)
            self._reset_session()
        elif operation == "set_participation":
            self._part_observe = self._needs_device = True
        elif operation == "control_source":
            self._source_observe.add(work.payload.source_id)
        elif exc.code in ("forbidden", "capability_required", "feature_disabled"):
            self._needs_device = True
            self._catalogue = self._eligibility = None
            self._due["catalogue"] = self._due["eligibility"] = 0


__all__ = [
    "FleetSharingWorker",
    "PendingSourceStatus",
    "RemoteEvent",
    "SharingMetadata",
    "SharingStatus",
]
