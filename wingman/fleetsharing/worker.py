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
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from math import inf, isfinite, nextafter
from typing import Literal, get_args
from uuid import uuid4

from ..telemetry.model import FleetSnapshot
from . import crypto, projection
from . import protocol as p
from . import state as s
from .client import FleetRelayClient, FleetRelayError
from .config import resolve_relay_origin
from .model import FleetCatalogue, PublicationSource, TimedSnapshot, TimingFenceReason
from .scheduling import OPERATIONS, SIGNED_INTERVAL_S, Work
from .timing import TimingContext, _ClockContradiction, _TimingLoss

logger = logging.getLogger(__name__)
BASE_BACKOFF_S = 1.0
MAX_BACKOFF_S = 30.0
IDLE_POLL_S = 0.5
INERT_POLL_S = 15.0
CATALOGUE_REFRESH_INTERVAL_S = 60.0
ELIGIBILITY_REFRESH_INTERVAL_S = 2.0
ELIGIBILITY_URGENCY_WINDOW_S = ELIGIBILITY_REFRESH_INTERVAL_S + 2 * SIGNED_INTERVAL_S
SESSION_RENEWAL_INTERVAL_S = 600.0
MAX_SNAPSHOT_AGE_S = 5.0
# A 2s heartbeat plus a read that just misses it exhausts the 3s live budget,
# even on healthy low-latency links. Leave room for read service and full RTT.
HEARTBEAT_INTERVAL_S = 1.0
CAPABILITIES = (p.SHARED_CAPABILITY,)
COMBAT_CAPABILITIES = (*CAPABILITIES, p.COMBAT_CAPABILITY)
# Only these classifications may reach status. Never render an exception body.
ERROR_CODES = frozenset(
    (
        "unauthorized",
        "forbidden",
        "conflict",
        "revision_replayed",
        "receipt_not_found",
        "receipt_capacity",
        "request_id_conflict",
        "rate_limited",
        "transport_error",
        "server_error",
        "bad_request",
        "bad_headers",
        "not_found",
        "not_completable",
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
    command: p.SourceCommand | None = None


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
    automatic: s.AutomaticState = field(default_factory=s.AutomaticState)
    automatic_status: p.AutomaticStatus | None = None
    automatic_stage: str | None = None
    automatic_request_id: str | None = None
    automatic_choice: bool | None = None
    cutover_outcomes: tuple[s.CutoverOutcome, ...] = ()
    cutover_present: bool = False
    command_sequence: int = 0
    pending_participation: s.PendingParticipation | None = None
    pending_pairing: s.PendingPairing | None = None
    pending_recovery: s.PendingRecovery | None = None


@dataclass(frozen=True)
class RemoteEvent:
    payload: TimedSnapshot | None
    lifecycle_epoch: int
    identity_epoch: int
    kind: Literal["replace", "clear"]
    order: int
    binding: str | None


@dataclass(frozen=True)
class CatalogueEvent:
    catalogue: FleetCatalogue | None
    binding: str | None
    lifecycle_epoch: int
    identity_epoch: int
    order: int


@dataclass(frozen=True)
class _Command:
    sequence: int
    kind: str
    payload: object
    identity_epoch: int
    binding: str | None
    supersedes: object = None
    automatic_history: s.AutomaticState | None = None


@dataclass(frozen=True)
class _Fence:
    lifecycle: int
    identity: int
    session: str | None
    participation: int
    source: tuple[tuple[str, int], ...]
    automatic: int
    # Independent from control admission: a timing loss must not obsolete an
    # otherwise authorized Off/Stop/receipt or identity/control observation.
    timing: int = field(compare=False)


@dataclass(frozen=True)
class _EligibilityProof:
    response: p.Eligibility
    fence: _Fence
    deadlines: tuple[tuple[int, Fraction], ...]


@dataclass(frozen=True)
class _PublicationSelection:
    source: PublicationSource | None
    snapshot: FleetSnapshot | None
    catalogue: FleetCatalogue
    eligibility: p.Eligibility
    proof: _EligibilityProof
    eligible_character_ids: frozenset[int]
    member_deadlines: tuple[Fraction, ...]
    session_deadline: Fraction
    semantic: tuple
    withdrawal_reason: Literal["inactive", "source_eligibility_lost"] | None = None


@dataclass(frozen=True)
class _OffWithdrawal:
    session_deadline: Fraction
    auth: tuple | None
    reason: Literal["explicit_off"] = "explicit_off"


class _Obsolete(Exception):
    pass


class _PersistenceFailed(Exception):
    pass


class _LoadFailed(Exception):
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


class FleetSharingWorker:
    def __init__(
        self,
        *,
        load_state: Callable[[], s.SharingState],
        timing_context: TimingContext,
        client_factory=FleetRelayClient,
        unwrap_private_key=s.unwrap_private_key,
        sharing_enabled=lambda: True,
        save_state: Callable[[s.SharingState], None],
        wrap_private_key=s.wrap_private_key,
        _generate_private_key=crypto.generate_private_key,
        _thread_factory=threading.Thread,
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
        self._timing_context = timing_context
        self._clock = timing_context._clock
        self._utc_clock = _utc_clock
        self._jitter = _jitter
        self._lock = threading.Lock()
        self._status_lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._iteration_lock = threading.Lock()
        self._latest: PublicationSource | None = None
        self._pending = threading.Event()
        self._commands: dict[str, _Command] = {}
        self._deferred_commands: dict[str, _Command] = {}
        self._sequence = 0
        self._presentation_order = 0
        self._remote_order = 0
        self._catalogue_order = 0
        self._participation_generation = 0
        self._automatic_generation = 0
        self._automatic_observation = None
        self._automatic_probe = False
        self._automatic_receipt_first = True
        self._automatic_fenced_command = None
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
        self._pairing_pollable = None
        self._parked_pairing = None
        self._subscribers: dict[str, dict[object, Callable]] = {
            "status": {},
            "remote": {},
            "catalogue": {},
        }
        self._worker = None
        self._running = False
        self._stop_event = threading.Event()

        # Owner-only state, never reconstructed from a stale pass-local copy.
        self._state: s.SharingState | None = None
        self._quarantined = False
        self._identity_mismatch = False
        self._authenticated_device = None
        self._control_auth = None
        self._control_db_fact = None
        # Public loss closes this under the submission lock, independently of
        # terminal auth. The DB fact never anchors or reopens retained timing.
        self._control_time_fenced = timing_context._timing_loss is not None
        self._client = None
        self._client_origin = None
        self._scheduler = timing_context._scheduler
        self._local_retry_at = 0.0
        self._needs_device = True
        self._resume_metadata = False
        self._part_observe = True
        self._needs_fresh_intent = False
        self._source_observe: set[str] = set()
        self._withdraw_needed = False
        self._catalogue: FleetCatalogue | None = None
        self._eligibility: p.Eligibility | None = None
        self._eligibility_proof: _EligibilityProof | None = None
        self._sources: p.Sources | None = None
        self._due = dict.fromkeys(
            ("device", "catalogue", "eligibility", "read", "sources", "automatic"), 0.0
        )
        self._expiry_binding = None
        self._renew_at = 0.0
        self._expires_at = Fraction(0)
        self._last_published: tuple = ()
        self._last_publish_at = 0.0
        self._pause_binding = None
        self._pause_until = 0.0

    def fence_timing(self, reason: TimingFenceReason) -> None:
        """Permanently close this retained lifetime; never a reset/recovery API."""
        if reason not in get_args(TimingFenceReason):
            raise ValueError("Unknown timing loss reason.")
        with self._lock:
            clear = self._fence_timing_locked(reason)
        self._pending.set()
        if clear is not None:
            self._notify("remote", clear)

    def _fence_timing_locked(self, reason):
        context = self._timing_context
        self._control_time_fenced = True
        if context._timing_loss is not None:
            return None
        cutoff = None
        if reason in ("clock_inconsistent", "db_continuity_lost"):
            try:
                stamp = self._clock()
                if isfinite(stamp):
                    cutoff = stamp
            except Exception:  # noqa: BLE001 — optional context-clock failure cannot block permanent closure.
                # No comparable F; never log or expose private exception details.
                cutoff = None
        context._timing_loss = _TimingLoss(reason, cutoff)
        context._timing_generation += 1
        return self._remote_event_locked(None, "clear")

    def _apply_timing_loss(self):
        """Only the signed lane mutates histories; use the signal's fixed F."""
        context = self._timing_context
        with self._lock:
            notice = context._timing_loss
            if notice is None or context._loss_applied:
                return
            context._loss_applied = True
        if notice.reason == "clock_inconsistent":
            context._inconsistent = True
        if notice.cutoff is not None:
            context._publisher_lost_continuity(cutoff=notice.cutoff)
        # Untrustworthy elapsed has no comparable F. Keep old pins behind the
        # permanent fence; a full client/model restart is the only fresh lifetime.
        context._receiver_lost_history()
        self._update_status(state="refused", detail=notice.reason)

    def _timing_open_locked(self, fence):
        context = self._timing_context
        return (
            context._timing_loss is None
            and not context._inconsistent
            and fence.timing == context._timing_generation
            and self._control_auth_current_locked()
            and self._timing_scope_current_locked()
        )

    def _timing_scope_current_locked(self):
        context = self._timing_context
        scope = context._authenticated_scope
        return bool(
            scope is not None
            and self._control_auth is not None
            and scope[:2] == self._control_auth[3:]
            and scope[2] is context._db_continuity_token
            and scope[3] is context._elapsed_lifetime_token
        )

    def _accept_timing_candidate(self, candidate, fence, work, *, remote=False):
        clear = event = None
        with self._lock:
            self._check_locked(fence, work=work)
            if not self._timing_open_locked(fence):
                return
            if isinstance(candidate, _ClockContradiction):
                if candidate.base is self._timing_context._state:
                    clear = self._fence_timing_locked(candidate.reason)
                    self._timing_context._inconsistent = True
            elif (
                candidate is not None
                and self._timing_context._commit_diagnostic(candidate)
                and remote
            ):
                event = self._remote_event_locked(
                    candidate.state.receiver.payload, "replace"
                )
        if clear is not None:
            self._notify("remote", clear)
        elif event is not None:
            self._notify("remote", event)

    def submit(self, source: PublicationSource) -> None:
        with self._lock:
            self._latest = source
        self._pending.set()

    def _queue(
        self,
        key,
        kind,
        payload,
        *,
        binding=None,
        supersedes=None,
        automatic_history=None,
        expected_sequence=None,
    ):
        with self._lock:
            # Compare before reserving an identity epoch. The displayed setup
            # cannot erase an intervening Off, even if it has already been saved
            # and disappeared from the queue since the bridge's status read.
            if expected_sequence is not None and expected_sequence != self._sequence:
                return None
            if binding is not None and binding != self._status.metadata.binding:
                return None
            if kind == "cancel_automatic":
                queued = self._commands.get(key)
                if (
                    queued is not None
                    and queued.payload[0] == payload[0]
                    and self._command_binding_current(queued, self._status.metadata)
                ):
                    return queued
                pending = self._state.automatic.pending if self._state else None
                if (
                    pending is not None
                    and pending.command.request_id == payload[0]
                    and pending.cancel_after_on is not None
                ):
                    payload = payload[0], pending.cancel_after_on
                    if "remove_cancel" not in self._commands:
                        return _Command(
                            self._sequence, kind, payload, self._identity_epoch, binding
                        )
                queued_on = self._commands.get("automatic")
                if (
                    queued_on is not None
                    and queued_on.kind == "automatic"
                    and queued_on.payload.request_id == payload[0]
                ):
                    # Cancel this displayed, not-yet-durable proposal before
                    # ingestion can replace an older journal. The generation
                    # below also fences a save already admitted by the owner;
                    # its committed On is then cancelled through the usual path.
                    self._commands.pop("automatic")
                    self._deferred_commands.pop("automatic", None)
            if kind == "dismiss_source" and (
                self._state is None
                or payload not in self._state.pending_source_commands
            ):
                return None
            if (
                kind == "source"
                and isinstance(payload, p.StopSource)
                and supersedes is None
            ):
                queued = self._commands.get(key)
                previous = (
                    queued.payload
                    if queued is not None
                    else next(
                        (
                            c
                            for c in (
                                self._state.pending_source_commands
                                if self._state
                                else ()
                            )
                            if c.source_id.lower() == payload.source_id.lower()
                        ),
                        None,
                    )
                )
                if (
                    isinstance(previous, p.StopSource)
                    and previous.expected_generation == payload.expected_generation
                    and previous.expected_automatic == payload.expected_automatic
                    and (
                        queued is None
                        or self._command_binding_current(queued, self._status.metadata)
                    )
                ):
                    return queued or previous
            if (
                kind == "source"
                and key not in self._commands
                and sum(c.kind == "source" for c in self._commands.values())
                >= p.MAX_SOURCE_INTENTS
                # Durable sources retain a Stop slot even behind a full batch
                # of new admissions. Both sets are independently count-bounded.
                and not (
                    isinstance(payload, p.StopSource)
                    and any(
                        item.source_id.lower() == payload.source_id.lower()
                        for item in self._durable_sources
                    )
                )
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
            elif kind in (
                "automatic",
                "cancel_automatic",
                "dismiss_automatic",
                "remove_cancel",
            ):
                self._automatic_generation += 1
                changes = dict(
                    automatic_stage="queued",
                    automatic_choice=payload.enabled
                    if kind == "automatic"
                    else False
                    if kind == "cancel_automatic"
                    else None,
                    automatic_request_id=(
                        payload.request_id
                        if kind == "automatic"
                        else payload[1].request_id
                        if kind == "cancel_automatic"
                        else payload.command.request_id
                    ),
                )
            elif kind in ("source", "dismiss_source"):
                source_id = payload.source_id.lower()
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
                self._sequence,
                kind,
                payload,
                self._identity_epoch,
                binding,
                supersedes,
                automatic_history,
            )
            self._commands[key] = command
            clear = (
                self._remote_event_locked(None, "clear")
                if kind == "pairing"
                or (kind == "participation" and not payload.enabled)
                else None
            )
            # Publish queue status before the owner can consume this command.
            # Callbacks are deliberately deferred until BOTH locks are released.
            with self._status_lock:
                self._status = status = replace(
                    self._status,
                    **changes,
                    order=self._status.order + 1,
                    command_sequence=self._sequence,
                    pending_sources=self._pending_sources_locked(),
                )
        self._pending.set()
        if clear is not None:
            self._notify("remote", clear)
        self._notify("status", status)
        return command

    def request_pairing(
        self,
        *,
        mode="initial",
        configured_origin=None,
        action_id=None,
        requested_capabilities=CAPABILITIES,
        binding=None,
        supersedes=None,
        automatic_history=None,
        expected_sequence=None,
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
        try:
            if expected_sequence is not None:
                p.integer(expected_sequence)
            capabilities = p.capabilities(list(requested_capabilities))
            if action_id is not None:
                p.uuid(action_id)
            if supersedes is not None:
                if (
                    binding is None
                    or mode == "fresh"
                    or type(supersedes) is not tuple
                    or len(supersedes) != 2
                ):
                    return False
                pairing, recovery = supersedes
                if pairing is not None:
                    pairing = s._pending_pairing(
                        {
                            **asdict(pairing),
                            "requested_capabilities": list(
                                pairing.requested_capabilities
                            ),
                        },
                        self.status().metadata.paired_origin,
                    )
                if recovery is not None:
                    recovery = s._pending_recovery(asdict(recovery))
                supersedes = pairing, recovery
            if automatic_history is not None:
                if (
                    binding is None
                    or mode != "fresh"
                    or not isinstance(automatic_history, s.AutomaticState)
                ):
                    return False
                automatic_history = s._automatic(
                    s._to_dict(replace(s.EMPTY, automatic=automatic_history))[
                        "automatic"
                    ]
                )
                if automatic_history.pending is not None:
                    return False
        except (ValueError, TypeError, AttributeError):
            return False
        return (
            self._queue(
                "pairing",
                "pairing",
                (mode, configured_origin, action_id, capabilities),
                binding=binding,
                supersedes=supersedes,
                automatic_history=automatic_history,
                expected_sequence=expected_sequence,
            )
            is not None
        )

    def request_participation(
        self, enabled: bool, *, expected_generation=None, binding=None, supersedes=None
    ) -> str | None:
        """Return an explicit intent UUID, not a durable or server acknowledgement."""
        if type(enabled) is not bool:
            return None
        if supersedes is not None:
            try:
                supersedes = s._pending_participation(asdict(supersedes))
            except (ValueError, TypeError):
                return None
        if expected_generation is not None:
            try:
                p.integer(expected_generation, 0, p.INT4_MAX - 1)
            except (ValueError, TypeError):
                return None
            with self._lock:
                observed = self._state.observed_participation if self._state else None
                if (
                    binding is None
                    or binding != self._status.metadata.binding
                    or not self._terminal_authenticated_locked()
                    or observed is None
                    or observed.generation != expected_generation
                ):
                    return None
        intent = s.PendingParticipation(str(uuid4()), enabled, expected_generation)
        # Unbound choices require a subsequent explicit displayed-CAS confirmation.
        if (
            self._queue(
                "participation",
                "participation",
                intent,
                binding=binding,
                supersedes=supersedes,
            )
            is None
        ):
            return None
        return intent.intent_id

    def confirm_participation(
        self, intent_id, *, expected_generation, binding
    ) -> str | None:
        with self._lock:
            pending = self._state.pending_participation if self._state else None
            if pending is None or pending.intent_id != intent_id:
                return None
        return self.request_participation(
            pending.enabled,
            expected_generation=expected_generation,
            binding=binding,
            supersedes=pending,
        )

    def request_automatic_status(self, *, binding) -> bool:
        return (
            self._queue("automatic_status", "automatic_status", None, binding=binding)
            is not None
        )

    def request_automatic(
        self,
        enabled,
        *,
        expected_generation,
        expected_revision,
        binding,
        supersedes=None,
    ) -> str | None:
        try:
            intent = p.AutomaticCommand(
                str(uuid4()),
                self._utc_text(),
                enabled,
                expected_generation,
                expected_revision,
            )
            p.automatic_command_body(intent)
            if supersedes is not None:
                supersedes = s._pending_automatic(s._pending_automatic_dict(supersedes))
        except (ValueError, TypeError, AttributeError):
            return None
        with self._lock:
            observed = self._automatic_observation
            if (
                binding is None
                or binding != self._status.metadata.binding
                or not self._terminal_authenticated_locked()
                or observed is None
                or (observed.consent.generation, observed.consent.revision)
                != (expected_generation, expected_revision)
                or (
                    enabled
                    and (
                        expected_generation >= p.JS_SAFE_MAX
                        or expected_revision > p.JS_SAFE_MAX - 2
                    )
                )
            ):
                return None
        action = self._queue(
            "automatic", "automatic", intent, binding=binding, supersedes=supersedes
        )
        return intent.request_id if action else None

    def request_cancel_automatic_on(self, request_id, *, binding) -> str | None:
        try:
            p.uuid4_lower(request_id)
            cancel = s.CancelAfterOn(str(uuid4()), self._utc_text())
        except (ValueError, TypeError):
            return None
        with self._lock:
            pending = self._state.automatic.pending if self._state else None
            queued_on = self._commands.get("automatic")
            original = (
                queued_on.payload
                if queued_on is not None
                and queued_on.kind == "automatic"
                and queued_on.payload.request_id == request_id
                else pending.command
                if pending is not None
                else None
            )
            if (
                binding is None
                or binding != self._status.metadata.binding
                or original is None
                or not original.enabled
                or original.request_id != request_id
            ):
                return None
            if (
                pending is not None
                and pending.command.request_id == request_id
                and pending.cancel_after_on is not None
            ):
                if "remove_cancel" not in self._commands:
                    return pending.cancel_after_on.request_id
                cancel = pending.cancel_after_on
            queued = self._commands.get("cancel_automatic")
            if queued is not None and queued.payload[0] == request_id:
                return queued.payload[1].request_id
        action = self._queue(
            "cancel_automatic",
            "cancel_automatic",
            (request_id, cancel),
            binding=binding,
        )
        return action.payload[1].request_id if action else None

    def request_dismiss_source(self, command, *, binding) -> bool:
        try:
            p.source_command_body(command)
        except (ValueError, TypeError, AttributeError):
            return False
        if binding is None:
            return False
        return (
            self._queue(
                "source:" + command.source_id.lower(),
                "dismiss_source",
                command,
                binding=binding,
            )
            is not None
        )

    def request_dismiss_automatic(self, pending, *, binding) -> bool:
        try:
            pending = s._pending_automatic(s._pending_automatic_dict(pending))
        except (ValueError, TypeError, AttributeError):
            return False
        if binding is None:
            return False
        return (
            self._queue("automatic", "dismiss_automatic", pending, binding=binding)
            is not None
        )

    def request_remove_automatic_cancel(self, pending, *, binding) -> bool:
        try:
            pending = s._pending_automatic(s._pending_automatic_dict(pending))
        except (ValueError, TypeError, AttributeError):
            return False
        if pending.cancel_after_on is None or binding is None:
            return False
        return (
            self._queue("remove_cancel", "remove_cancel", pending, binding=binding)
            is not None
        )

    def request_dismiss_cutover(self, selector, *, binding) -> bool:
        if not isinstance(selector, str):
            return False
        with self._lock:
            if binding is None or selector not in {
                v.selector for v in self._status.cutover_outcomes
            }:
                return False
        return (
            self._queue(
                "archive:" + selector, "dismiss_cutover", selector, binding=binding
            )
            is not None
        )

    def request_remove_cutover(self, outcomes, *, binding) -> bool:
        if (
            binding is None
            or type(outcomes) is not tuple
            or len(outcomes) > 260
            or any(
                type(item) is not s.CutoverOutcome
                or type(item.selector) is not str
                or type(item.status) is not str
                for item in outcomes
            )
        ):
            return False
        with self._lock:
            if outcomes != self._status.cutover_outcomes:
                return False
            outcomes = self._status.cutover_outcomes
        return (
            self._queue("remove_cutover", "remove_cutover", outcomes, binding=binding)
            is not None
        )

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
        self,
        source_id: str,
        *,
        expected_generation: int,
        expected_automatic: p.AutomaticBinding | None,
        binding=None,
        supersedes: p.SourceCommand | None = None,
    ) -> bool:
        try:
            command = p.StopSource(
                source_id,
                expected_generation,
                str(uuid4()),
                self._utc_text(),
                expected_automatic,
            )
            p.source_command_body(command)
            if supersedes is not None:
                p.source_command_body(supersedes)
        except (ValueError, TypeError, AttributeError):
            return False
        return self._queue_source(command, binding=binding, supersedes=supersedes)

    def _queue_source(self, command, *, binding=None, supersedes=None):
        return (
            self._queue(
                "source:" + command.source_id.lower(),
                "source",
                command,
                binding=binding,
                supersedes=supersedes,
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
            command,
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
                automatic_status=None,
                automatic_stage=None,
                automatic_request_id=None,
                automatic_choice=None,
            )
        self._update_status(
            metadata=metadata,
            automatic=state.automatic,
            cutover_outcomes=state.cutover.outcomes if state.cutover else (),
            cutover_present=state.cutover is not None,
            pending_participation=state.pending_participation,
            pending_pairing=state.pending_pairing,
            pending_recovery=state.pending_recovery,
            **changes,
        )

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

    def subscribe_catalogue(self, callback: Callable[[CatalogueEvent], None]):
        return self._subscribe("catalogue", callback)

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
            if kind in ("remote", "catalogue"):
                with self._lock:
                    obsolete = (
                        (
                            self._epoch,
                            self._identity_epoch,
                            self._status.metadata.binding,
                        )
                        != (value.lifecycle_epoch, value.identity_epoch, value.binding)
                        or value.order
                        != (
                            self._remote_order
                            if kind == "remote"
                            else self._catalogue_order
                        )
                        or (
                            kind == "remote"
                            and value.kind == "replace"
                            and (
                                self._inhibit
                                or self._timing_context._timing_loss is not None
                            )
                        )
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
            status = self._update_status_locked(**changes)
        if status is not None:
            self._notify("status", status)

    def _update_status_locked(self, **changes):
        with self._status_lock:
            status = self._status_candidate_locked(**changes)
            if status is not None:
                self._status = status
            return status

    def _status_candidate_locked(self, **changes):
        # Caller holds worker AND status locks. Publication completion prepares
        # the detached value before entering the producer's non-reentrant leaf.
        status = replace(
            self._status,
            **changes,
            pending_sources=self._pending_sources_locked(changes.get("metadata")),
        )
        if self._status == status:
            return None
        return replace(status, order=self._status.order + 1)

    def _remote_event_locked(self, payload, kind):
        self._presentation_order += 1
        self._remote_order = self._presentation_order
        return RemoteEvent(
            payload,
            self._epoch,
            self._identity_epoch,
            kind,
            self._remote_order,
            self._status.metadata.binding,
        )

    def _clear_remote(self):
        with self._lock:
            event = self._remote_event_locked(None, "clear")
        self._notify("remote", event)

    def _set_catalogue(self, catalogue, *, fence=None):
        with self._lock:
            if fence is not None:
                current = self._fence_locked()
                if (current.lifecycle, current.identity, current.session) != (
                    fence.lifecycle,
                    fence.identity,
                    fence.session,
                ):
                    raise _Obsolete
            event = self._set_catalogue_locked(catalogue)
        self._notify("catalogue", event)

    def _set_catalogue_locked(self, catalogue):
        self._catalogue = catalogue
        self._presentation_order += 1
        self._catalogue_order = self._presentation_order
        return CatalogueEvent(
            catalogue,
            self._status.metadata.binding,
            self._epoch,
            self._identity_epoch,
            self._catalogue_order,
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
                clear = self._remote_event_locked(None, "clear")
            self._pending.set()
        self._notify("remote", clear)
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
            self._automatic_generation,
            self._timing_context._timing_generation,
        )

    def _fence(self):
        with self._lock:
            return self._fence_locked()

    def _check(self, fence, *, work=None):
        with self._lock:
            self._check_locked(fence, work=work)

    def _check_locked(self, fence, *, work=None):
        if self._identity_mismatch:
            raise _Obsolete
        current = self._fence_locked()
        if current.automatic != fence.automatic and (
            work is None or work.operation in ("control_automatic", "publish_snapshot")
        ):
            raise _Obsolete
        if work is not None:
            queued = tuple(self._commands.values())
            deferred = tuple(self._deferred_commands.values())
            if any(
                command.kind == "pairing"
                or (
                    command.kind == "participation"
                    # Only known deferred choices permit prerequisite reads or
                    # empty withdrawal. They NEVER authorize an older CAS or
                    # publication; a replacement still changes the fence.
                    and not (
                        command in deferred
                        and (
                            work.operation
                            in ("fetch_device", "acknowledge_capabilities")
                            or work.key == "withdraw"
                        )
                    )
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
                        (
                            work.operation == "fetch_sources"
                            # A known full-count Stop must let the owner observe
                            # and drain older work. A replacement/new submission
                            # is still fenced here AND by the source generation.
                            and command not in deferred
                        )
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
            work is None
            or work.operation in ("fetch_sources", "control_source", "publish_snapshot")
        ):
            raise _Obsolete

    def _persist(self, candidate, fence, *, work=None):
        self._check(fence, work=work)
        try:
            self._save_state(candidate)
        except s.CapacityError:
            raise
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
        # Only a typed negative from this live attempt permits another poll.
        self._pairing_pollable = None
        with self._lock:
            notifications = self._reset_session_locked()
        for kind, event in notifications:
            if event is not None:
                self._notify(kind, event)

    def _reset_session_locked(self):
        notifications = self._reset_session_caches_locked()
        status = self._update_status_locked(
            sources=None,
            eligibility=None,
            observed_participation=self._state.observed_participation,
        )
        return (*notifications, ("status", status))

    def _reset_session_caches_locked(self):
        self._control_auth = None
        self._control_db_fact = None
        self._automatic_observation = None
        self._automatic_receipt_first = True
        self._needs_device = True
        self._part_observe = True
        self._source_observe.update(
            c.source_id for c in self._state.pending_source_commands
        )
        self._eligibility = self._sources = None
        remote = self._remote_event_locked(None, "clear")
        catalogue = self._set_catalogue_locked(None)
        self._expiry_binding = None
        self._last_published = ()
        self._due = dict.fromkeys(self._due, 0.0)
        return (("remote", remote), ("catalogue", catalogue))

    def _archived_choice(self, state=None):
        archive = (state or self._state).cutover
        if archive is None:
            return None
        if any(
            item.selector == "participation" and item.status == "fenced"
            for item in archive.outcomes
        ):
            return archive.original["pending_participation"]
        return None

    @staticmethod
    def _settle_archive(state, *, participation=None, recovered=False):
        archive = state.cutover
        if archive is None:
            return state
        choice = archive.original.get("pending_participation")
        outcomes = []
        for item in archive.outcomes:
            status = item.status
            if recovered and status in ("fenced", "expired_unproven"):
                if item.selector == "session":
                    status = "superseded_session"
                elif item.selector in ("pairing", "recovery"):
                    status = "recovered_identity"
            if (
                item.selector == "participation"
                and status == "fenced"
                and participation is not None
                and choice is not None
                and participation.enabled == choice["enabled"]
            ):
                status = "observed_choice"
            outcomes.append(s.CutoverOutcome(item.selector, status))
        return replace(state, cutover=replace(archive, outcomes=tuple(outcomes)))

    def _load(self):
        if self._state is not None:
            return
        if self._quarantined:
            raise s.QuarantineError
        try:
            self._state = self._load_state()
        except s.QuarantineError:
            self._quarantined = True
            raise
        except OSError:
            raise _LoadFailed from None
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
        if self._state.cutover is not None:
            self._resume_metadata = any(
                item.status == "fenced" for item in self._state.cutover.outcomes
            )
        if self._archived_choice() is not None:
            with self._lock:
                self._inhibit = True
            self._update_status(
                local_inhibited=True, participation="needs_confirmation"
            )
        pending = self._state.pending_participation
        if pending is not None:
            self._withdraw_needed = not pending.enabled and bool(self._last_published)
            with self._lock:
                self._inhibit = True
                queued_participation = "participation" in self._commands
            if not queued_participation:
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
            elif (
                self._command_binding_current(command, self.status().metadata)
                and self._ingest_control(command, fence) is False
            ):
                with self._lock:
                    self._deferred_commands[key] = command
                continue
            self._drop_command(key, command)

    def _drop_command(self, key, command):
        with self._lock:
            if self._commands.get(key) == command:
                self._commands.pop(key)
            self._deferred_commands.pop(key, None)
        self._update_status()

    def _ingest_pairing(self, command, fence):
        mode, configured, action_id, capabilities = command.payload
        state = self._state
        changed_origin = False
        auth_ack = command.supersedes
        history_ack = command.automatic_history
        if (
            not self._command_binding_current(command, self.status().metadata)
            or (
                auth_ack is not None
                and auth_ack != (state.pending_pairing, state.pending_recovery)
            )
            or (
                history_ack is not None
                and (
                    history_ack != state.automatic
                    or state.automatic.pending is not None
                )
            )
        ):
            self._update_status(
                fence=fence,
                state="refused",
                detail="unresolved_history",
                pairing="rejected",
            )
            return
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
        if mode == "fresh" and (
            state.cutover is not None
            or state.pending_participation is not None
            or state.pending_source_commands
            or state.pending_pairing is not None
            or state.pending_recovery is not None
            or (
                state.automatic != s.AutomaticState() and history_ack != state.automatic
            )
        ):
            self._update_status(
                fence=fence,
                state="refused",
                detail="unresolved_history",
                pairing="rejected",
            )
            return
        if mode == "fresh" and not (terminal or changed_origin):
            self._update_status(
                fence=fence,
                state="refused",
                detail="fresh_key_not_authorized",
                pairing="rejected",
            )
            return
        if (
            mode != "fresh"
            and auth_ack is None
            and (
                state.pending_recovery is not None
                or (
                    state.pending_pairing is not None
                    and state.pending_pairing.completion_attempted
                )
            )
        ):
            self._update_status(
                fence=fence,
                state="refused",
                detail="unresolved_history",
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
            and auth_ack is None
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
                pending_pairing=s.PendingPairing(
                    mode, requested_capabilities=capabilities
                ),
            )
        else:
            candidate = replace(
                state,
                pending_pairing=s.PendingPairing(
                    mode, requested_capabilities=capabilities
                ),
                pending_recovery=None,
                auth_pause=None,
            )
        try:
            s.check_admission_capacity(candidate)
        except s.CapacityError:
            self._update_status(
                fence=fence,
                state="refused",
                detail="source_queue_full",
                pairing="rejected",
            )
            return
        try:
            self._persist(candidate, fence)
        finally:
            if self._state is candidate:
                # The write may commit before a new submission fences projection.
                # Finish this admission, not a second attempt against its own journal.
                self._pairing_action_id = action_id
                self._parked_pairing = None
                self._drop_command("pairing", command)
                self._reset_session()
        self._update_status(
            fence=replace(fence, session=self._state.session_id),
            state="connecting",
            detail=None,
            pairing="persisted",
            approval_url=None,
        )

    def _ingest_control(self, command, fence) -> bool:
        """False retains a capacity-blocked control; I/O failure aborts the turn."""
        if self._state.identity is None:
            self._update_status(state="refused", detail="needs_pairing")
            return True
        if command.kind in (
            "dismiss_source",
            "dismiss_automatic",
            "remove_cancel",
            "dismiss_cutover",
            "remove_cutover",
        ):
            return self._ingest_history(command, fence)
        if command.kind == "automatic_status":
            self._automatic_probe = True
            return True
        if command.kind == "cancel_automatic":
            self._save_automatic_cancel(command, fence)
            return True
        if command.kind == "automatic":
            if self._state.automatic.pending != command.supersedes:
                pending = self._state.automatic.pending
                if pending is not None:
                    # A stale unsent acknowledgement cannot erase an attempt
                    # which won the save race, nor resume its contrary mutation.
                    self._automatic_fenced_command = pending.command
                self._update_status(fence=fence, automatic_stage="needs_confirmation")
                return True
            old = self._state.automatic.pending
            if old is not None and old.attempted and old.command.enabled:
                with self._lock:
                    proven = self._on_expired_proven_locked(old.command)
                if not proven:
                    self._needs_device = True
                    self._update_status(
                        fence=fence, automatic_stage="awaiting_expiry_proof"
                    )
                    return False
            automatic = replace(
                self._state.automatic,
                pending=s.PendingAutomatic(command.payload),
                last_result=s.AutomaticCompletion(
                    old, "superseded_unknown" if old.attempted else "cancelled_unsent"
                )
                if old is not None
                else self._state.automatic.last_result,
            )
            candidate = replace(self._state, automatic=automatic)
            try:
                self._persist(candidate, fence)
            finally:
                if candidate is self._state:
                    # A committed admission is not a stale acknowledgement of
                    # itself when a newer action fences the post-write callback.
                    self._automatic_receipt_first = False
                    self._automatic_fenced_command = None
                    self._drop_command("automatic", command)
            self._update_status(fence=fence, automatic_stage="persisted")
            return True
        if command.kind == "participation":
            intent = command.payload
            old = self._state.pending_participation
            archive = self._archived_choice()
            if (old is not None and old != command.supersedes) or (
                archive is not None and archive["enabled"] != intent.enabled
            ):
                self._update_status(
                    fence=fence,
                    participation="needs_confirmation",
                    detail="unresolved_history",
                )
                return True
            try:
                candidate = replace(self._state, pending_participation=intent)
                s.check_control_capacity(candidate)
                try:
                    self._persist(candidate, fence)
                finally:
                    if candidate is self._state:
                        self._needs_fresh_intent = False
                        self._part_observe = self._needs_device = True
                        self._withdraw_needed = not intent.enabled and bool(
                            self._last_published
                        )
                        self._eligibility = None
                        self._drop_command("participation", command)
            except s.CapacityError:
                # Keep the exact choice queued and inhibited; a Stop later in
                # this ingest may release space. No false saved/acknowledged.
                self._update_status(
                    fence=fence, state="error", detail="source_queue_full"
                )
                return False
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
            # Same-source replacement is an explicit retirement of unknown work.
            # Ingestion runs only after the previous serialized HTTP has drained.
            if old is not None and command.supersedes != old:
                self._update_status(
                    fence=fence,
                    source_control="needs_confirmation",
                    detail="unresolved_history",
                )
                return True
            candidate = (
                *(
                    c
                    for c in commands
                    if c.source_id.lower() != incoming.source_id.lower()
                ),
                incoming,
            )
            candidate = replace(self._state, pending_source_commands=candidate)
            try:
                if len(candidate.pending_source_commands) > p.MAX_SOURCE_INTENTS:
                    raise s.CapacityError("Too many pending fleet source intents.")
                if isinstance(incoming, p.StartSource) and old is None:
                    s.check_admission_capacity(candidate)
                elif old is None or isinstance(incoming, p.StartSource):
                    # The accepted state4 reserve covers future responses and
                    # terminal growth without borrowing the archive partition.
                    s.check_control_capacity(candidate)
                try:
                    self._persist(candidate, fence)
                finally:
                    if candidate is self._state:
                        if isinstance(incoming, p.StopSource) and incoming != old:
                            self._source_observe.add(incoming.source_id)
                        self._drop_command(
                            "source:" + incoming.source_id.lower(), command
                        )
            except s.CapacityError:
                self._check(fence)
                if old is None:
                    # Only this unsaved admission is refused. Existing requests
                    # and uncertainty remain intact; disk I/O failures never
                    # take this path. Keep the UUID visible as an honest result.
                    self._update_status(
                        fence=fence,
                        state="refused",
                        detail="source_queue_full",
                        source_control="rejected",
                        source_results=(
                            *self.status().source_results,
                            self._source_summary(incoming, "rejected"),
                        )[-p.MAX_SOURCE_INTENTS :],
                    )
                    return True
                self._update_status(
                    fence=fence, state="error", detail="source_queue_full"
                )
                return False
            self._update_status(fence=fence, source_control="persisted")
        return True

    def _ingest_history(self, action, fence):
        state = self._state
        kind, value = action.kind, action.payload
        if kind == "dismiss_source":
            if value not in state.pending_source_commands:
                return True
            candidate = replace(
                state,
                pending_source_commands=tuple(
                    c for c in state.pending_source_commands if c != value
                ),
            )
        elif kind in ("dismiss_automatic", "remove_cancel"):
            pending = state.automatic.pending
            if pending != value:
                completed = state.automatic.last_result
                if (
                    pending is not None
                    and not pending.attempted
                    and value.cancel_after_on is not None
                    and completed is not None
                    and completed.pending == value
                    and completed.receipt is not None
                    and s.settle_automatic_receipt(
                        replace(
                            state, automatic=replace(state.automatic, pending=value)
                        ),
                        completed.receipt,
                    ).automatic.pending
                    == pending
                ):
                    # The acknowledgement crossed our own On-receipt write.
                    # It retires only that receipt's still-unsent cancellation,
                    # never a newer action or an attempted Off.
                    if kind == "dismiss_automatic":
                        with self._lock:
                            proven = self._on_expired_proven_locked(value.command)
                        if not proven:
                            self._update_status(
                                fence=fence, automatic_stage="needs_confirmation"
                            )
                            return True
                    self._persist(
                        replace(
                            state, automatic=replace(state.automatic, pending=None)
                        ),
                        fence,
                    )
                    return True
                self._update_status(fence=fence, automatic_stage="needs_confirmation")
                return True
            if kind == "remove_cancel":
                automatic = replace(
                    state.automatic, pending=replace(pending, cancel_after_on=None)
                )
            else:
                if pending.attempted and pending.command.enabled:
                    with self._lock:
                        proven = self._on_expired_proven_locked(pending.command)
                    if not proven:
                        self._needs_device = True
                        return False
                automatic = replace(
                    state.automatic,
                    pending=None,
                    last_result=s.AutomaticCompletion(
                        pending,
                        "superseded_unknown"
                        if pending.attempted
                        else "cancelled_unsent",
                    ),
                )
            candidate = replace(state, automatic=automatic)
        elif kind == "dismiss_cutover":
            if state.cutover is None or value not in {
                v.selector for v in state.cutover.outcomes
            }:
                return True
            candidate = replace(
                state,
                cutover=replace(
                    state.cutover,
                    outcomes=tuple(
                        replace(v, status="dismissed") if v.selector == value else v
                        for v in state.cutover.outcomes
                    ),
                ),
            )
        else:
            if (
                state.cutover is None
                or state.cutover.outcomes != value
                or any(v.status == "fenced" for v in state.cutover.outcomes)
            ):
                return True
            candidate = replace(state, cutover=None)
        self._persist(candidate, fence)
        return True

    def _iterate(self):
        try:
            self._apply_timing_loss()
            now = self._clock()
            if now < self._local_retry_at:
                return IDLE_POLL_S, False
            enabled = self._enabled()
            with self._lock:
                explicit = bool(self._commands) or self._watch or self._probe_queued
            pending = self._state and (
                self._state.pending_participation
                or self._automatic_active()
                or self._automatic_probe
                or self._state.pending_source_commands
                or (
                    self._state.pending_pairing is not None
                    and self._state.pending_pairing != self._parked_pairing
                )
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
                retained = {
                    c.source_id.lower() for c in self._state.pending_source_commands
                }
                retained.update(
                    c.payload.source_id.lower()
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
                # Re-plan in a new owner turn: another bucket may already be due.
                # _work has durable side effects and the completed request may
                # have replaced authority, so never re-use this turn's Work.
                return 0.0, True
            return min(IDLE_POLL_S, self._scheduler.delay(work, self._clock())), True
        except _Obsolete:
            # Persisted uncertainty is intentionally left for the next owner turn.
            return IDLE_POLL_S, True
        except s.QuarantineError:
            self._update_status(state="refused", detail="state_quarantined")
            return INERT_POLL_S, False
        except s.CapacityError:
            self._update_status(state="error", detail="source_queue_full")
            return IDLE_POLL_S, False
        except _LoadFailed:
            self._local_retry_at = self._clock() + BASE_BACKOFF_S
            self._update_status(state="error", detail="state_load_failed")
            return BASE_BACKOFF_S, False
        except _PersistenceFailed:
            self._local_retry_at = self._clock() + BASE_BACKOFF_S
            self._update_status(state="error", detail="persistence_failed")
            return BASE_BACKOFF_S, False
        except Exception:  # noqa: BLE001 - fail closed, without leaking key/response/exception context
            self._local_retry_at = self._clock() + BASE_BACKOFF_S
            self._update_status(state="error", detail="local_failure")
            return BASE_BACKOFF_S, False

    @staticmethod
    def _elapsed_expiry(text, elapsed, utc):
        delta = datetime.fromisoformat(text) - utc
        return Fraction(elapsed) + Fraction(
            (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds,
            1000000,
        )

    def _expiry(self):
        binding = (self._state.session_id, self._state.session_expires_at)
        if binding != self._expiry_binding:
            elapsed = self._clock()
            self._expires_at = self._elapsed_expiry(
                binding[1], elapsed, self._utc_now()
            )
            remaining = self._expires_at - Fraction(elapsed)
            self._renew_at = elapsed + max(
                0, min(SESSION_RENEWAL_INTERVAL_S, remaining - 60)
            )
            self._expiry_binding = binding

    def _work(self, enabled):
        if self._identity_mismatch:
            return ()
        state = self._state
        if state.identity is None or state.relay_origin is None:
            return ()
        with self._lock:
            watching, inhibited = self._watch, self._inhibit
            timing_allowed = self._timing_open_locked(self._fence_locked())
            queued_participation = "participation" in self._commands
        pending = (
            state.pending_participation
            or self._automatic_active()
            or self._automatic_probe
            or state.pending_source_commands
            or (
                state.pending_pairing is not None
                and state.pending_pairing != self._parked_pairing
            )
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
                if self.status().pairing != "rejected":
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
        terminal_during_pairing = ()
        if (
            pairing
            and state.session_id
            and state.last_revision < p.INT4_MAX
            and (
                self._automatic_active()
                or self._automatic_probe
                or any(
                    isinstance(c, p.StopSource) for c in state.pending_source_commands
                )
            )
        ):
            if state.session_expires_at is not None:
                self._expiry()
            if state.session_expires_at is None or self._clock() < self._expires_at:
                with self._lock:
                    authenticated = self._control_auth_current_locked()
                if not authenticated:
                    return (Work("fetch_device", "device", priority=0),)
                terminal_during_pairing = tuple(
                    w
                    for w in self._terminal_source_work()
                    if w.operation != "control_automatic" or not w.payload.enabled
                )
        if pairing and pairing != self._parked_pairing:
            if pairing.completion_attempted and pairing != self._pairing_pollable:
                # A lost response may mean either registration or no commit at
                # all. Keep initial provenance for an explicit SAME-key retry;
                # a generic recovery 401 proves neither revocation nor consent.
                if (
                    self._scheduler.choose(terminal_during_pairing, self._clock())
                    is not None
                ):
                    return terminal_during_pairing
                return (*terminal_during_pairing, *self._recovery_work())
            if pairing.pairing_id is None:
                return (
                    *terminal_during_pairing,
                    Work("begin_pairing", "pairing", priority=1),
                )
            if self._remaining(pairing.expires_at) <= 0:
                self._update_status(
                    state="refused",
                    detail="pairing_expired",
                    pairing="needs_retry",
                    approval_url=None,
                )
                return terminal_during_pairing
            return (
                *terminal_during_pairing,
                Work("complete_pairing", "pairing", priority=1),
            )
        if (
            state.pending_recovery
            or not state.session_id
            or state.last_revision >= p.INT4_MAX
        ):
            return self._recovery_work()
        if state.session_expires_at is not None:
            self._expiry()
            if self._clock() >= self._expires_at:
                self._persist(s.replace_session(state, None), fence)
                self._reset_session()
                return self._recovery_work()
        terminal = self._terminal_source_work()
        if self._needs_device or state.session_expires_at is None:
            return (*terminal, Work("fetch_device", "device", priority=1))
        if not state.feature_enabled:
            self._update_status(state="refused", detail="feature_disabled")
            return (
                *terminal,
                Work("fetch_device", "device", due=self._due["device"], periodic=True),
            )
        if p.SHARED_CAPABILITY not in (state.approved_capabilities or ()):
            self._update_status(state="refused", detail="needs_upgrade")
            return ()
        if p.SHARED_CAPABILITY not in (state.session_approved_capabilities or ()):
            if terminal:
                return terminal
            self._persist(s.replace_session(state, None), fence)
            self._reset_session()
            return self._recovery_work()
        if p.SHARED_CAPABILITY not in (state.acknowledged_capabilities or ()):
            return (*terminal, Work("acknowledge_capabilities", "ack", priority=1))
        work = list(terminal)
        if any(
            capability not in (state.acknowledged_capabilities or ())
            for capability in self._acknowledge_rights()
        ):
            # Combat acknowledgement is publication disclosure, not permission
            # to receive. Its retry must not strand already-authorized shared GETs.
            work.append(Work("acknowledge_capabilities", "ack", priority=1))
        if self._withdraw_needed:
            work.append(
                Work(
                    "publish_snapshot",
                    "withdraw",
                    priority=0,
                    payload=_OffWithdrawal(self._expires_at, self._control_auth),
                )
            )
        if self._clock() >= self._renew_at:
            work.append(Work("renew_session", "renew", due=self._renew_at, priority=1))
        intent = state.pending_participation
        # A capacity-deferred choice supersedes the old CAS without becoming
        # durable itself. Do not repeatedly select fenced CAS work and starve
        # source reconciliation that can release its needed space.
        if intent and not self._needs_fresh_intent and not queued_participation:
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
            if isinstance(command, p.StopSource):
                continue  # Terminal lane above does not require work permission.
            if not -60 < self._remaining(command.intent_created_at) <= 0:
                # Expiry is a replay refusal, never proof of noncommit/deletion.
                continue
            if command.source_id in self._source_observe:
                self._source_observe.add(command.source_id)
                work.append(
                    Work(
                        "fetch_sources",
                        "sources-reconcile",
                        priority=2,
                    )
                )
            else:
                work.append(
                    Work(
                        "control_source",
                        self._source_work_key(command),
                        priority=2,
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
            and timing_allowed
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
                    self._eligibility_work(),
                    Work("read_snapshot", "read", due=self._due["read"], periodic=True),
                )
            )
            publication = self._publication()
            if publication is not None:
                stage_floor = self._timing_context._next_stage_at or 0
                stage_due = float(stage_floor)
                if stage_due < stage_floor:
                    # Scheduler uses float deadlines. Round UP, never convert an
                    # exact retained floor into a sub-ULP zero-delay busy loop.
                    stage_due = nextafter(stage_due, inf)
                work.append(
                    Work(
                        "publish_snapshot",
                        "publication",
                        due=max(
                            stage_due,
                            self._last_publish_at + HEARTBEAT_INTERVAL_S
                            if publication.semantic == self._last_published
                            else 0,
                        ),
                        periodic=True,
                        payload=publication,
                        priority=0 if publication.withdrawal_reason else 2,
                    )
                )
        return tuple(work)

    def _bind_control_auth(self, device_id, fence, work):
        with self._lock:
            self._check_locked(fence, work=work)
            # Retain the response's association, not a newly sampled epoch which
            # could bless an older response after a queued identity transition.
            self._control_auth = (
                fence.lifecycle,
                fence.identity,
                fence.session,
                self._status.metadata.binding,
                device_id.lower(),
            )
            context = self._timing_context
            if context._authenticated_scope is None:
                context._authenticated_scope = (
                    self._control_auth[3],
                    device_id.lower(),
                    context._db_continuity_token,
                    context._elapsed_lifetime_token,
                )
            # A different authenticated binding never reidentifies old timing.
            # Terminal auth still belongs to B; no new model/domain is invented.

    def _control_auth_current_locked(self):
        state = self._state
        return bool(
            state
            and state.session_id
            and state.device_id
            and not self._identity_mismatch
            and self._control_auth
            == (
                self._epoch,
                self._identity_epoch,
                state.session_id,
                self._status.metadata.binding,
                state.device_id.lower(),
            )
        )

    def _terminal_authenticated_locked(self):
        return self._control_auth_current_locked() and p.SHARED_CAPABILITY in (
            self._state.approved_capabilities or ()
        )

    def _terminal_source_work(self):
        with self._lock:
            if not self._terminal_authenticated_locked():
                return ()
        work = list(self._automatic_work())
        for command in self._state.pending_source_commands:
            if not isinstance(command, p.StopSource):
                continue
            if command.source_id in self._source_observe:
                work.append(
                    Work(
                        "fetch_receipt",
                        self._source_work_key(command),
                        priority=0,
                        payload=command,
                    )
                )
            elif -60 < self._remaining(command.intent_created_at) <= 0:
                work.append(
                    Work(
                        "control_source",
                        self._source_work_key(command),
                        priority=0,
                        payload=command,
                    )
                )
        return tuple(work)

    @staticmethod
    def _intent_ms(text):
        delta = datetime.fromisoformat(p.utc_date(text)) - datetime(
            1970, 1, 1, tzinfo=UTC
        )
        return (delta.days * 86400 + delta.seconds) * 1000 + delta.microseconds // 1000

    def _on_expired_proven_locked(self, command):
        fact = self._control_db_fact
        return bool(
            not self._control_time_fenced
            and not self._timing_context._inconsistent
            and self._terminal_authenticated_locked()
            and fact is not None
            and fact[:2]
            == (self._control_auth, self._timing_context._db_continuity_token)
            and fact[2] >= self._intent_ms(command.intent_created_at) + 60000
        )

    def _save_automatic_cancel(self, action, fence, *, work=None):
        pending = self._state.automatic.pending
        request_id, cancel = action.payload
        if pending is None:
            completed = self._state.automatic.last_result
            if (
                completed is None
                or completed.receipt is None
                or not completed.pending.command.enabled
                or completed.pending.command.request_id != request_id
            ):
                return
            # A callback may queue cancellation while the On completion's atomic
            # write is returning. Its exact saved receipt still authorizes only
            # that On's successor — never the current observed generation.
            pending = replace(completed.pending, cancel_after_on=cancel)
            candidate = replace(
                self._state, automatic=replace(self._state.automatic, pending=pending)
            )
            candidate = s.settle_automatic_receipt(candidate, completed.receipt)
            self._persist(candidate, fence, work=work)
            self._automatic_receipt_first = False
            return
        if not pending.command.enabled or pending.command.request_id != request_id:
            return
        if pending.cancel_after_on is not None:
            return
        if pending.attempted:
            automatic = replace(
                self._state.automatic, pending=replace(pending, cancel_after_on=cancel)
            )
        else:
            automatic = replace(
                self._state.automatic,
                pending=None,
                last_result=s.AutomaticCompletion(pending, "cancelled_unsent"),
            )
        self._persist(replace(self._state, automatic=automatic), fence, work=work)
        self._automatic_receipt_first = True

    def _automatic_active(self):
        automatic = self._state.automatic
        return bool(
            automatic.pending
            or (automatic.observed_consent and automatic.observed_consent.enabled)
        )

    def _automatic_work(self):
        automatic = self._state.automatic
        pending = automatic.pending
        work = []
        if (
            pending is not None
            and pending.attempted
            and (self._automatic_receipt_first or pending.cancel_after_on is not None)
        ):
            work.append(
                Work(
                    "fetch_receipt",
                    "automatic-receipt",
                    priority=0,
                    payload=pending.command,
                )
            )
        if self._automatic_probe or (
            self._automatic_active() and self._automatic_observation is None
        ):
            work.append(Work("fetch_automatic", "automatic-status", priority=1))
        elif self._automatic_active() or self._watch:
            work.append(
                Work(
                    "fetch_automatic",
                    "automatic-status",
                    due=self._due["automatic"],
                    periodic=True,
                )
            )
        with self._lock:
            replacing = any(
                k in self._commands
                for k in ("automatic", "cancel_automatic", "remove_cancel")
            )
        if (
            pending is None
            or pending.cancel_after_on is not None
            or replacing
            or pending.command == self._automatic_fenced_command
            or self._automatic_observation is None
            or (pending.attempted and self._automatic_receipt_first)
        ):
            return tuple(work)
        command = pending.command
        consent = automatic.observed_consent
        if consent is None or (consent.generation, consent.revision) != (
            command.expected_generation,
            command.expected_revision,
        ):
            return tuple(
                work
            )  # No implicit CAS rebase, including derived cancellation Off.
        if command.enabled:
            state = self._state
            if not (
                state.feature_enabled
                and all(
                    p.SHARED_CAPABILITY in (caps or ())
                    for caps in (
                        state.approved_capabilities,
                        state.session_approved_capabilities,
                        state.acknowledged_capabilities,
                    )
                )
                and -60 < self._remaining(command.intent_created_at) <= 0
            ):
                return tuple(work)
        elif self._remaining(command.intent_created_at) > 0:
            return tuple(work)
        return (
            *work,
            Work(
                "control_automatic",
                "automatic-control",
                priority=2 if command.enabled else 0,
                payload=command,
            ),
        )

    def _accept_automatic(self, work, result, fence):
        historical = replace(work, operation="fetch_receipt")
        with self._lock:
            self._check_locked(fence, work=historical)
            if not self._terminal_authenticated_locked():
                raise _Obsolete
            actions = tuple(
                sorted(
                    (
                        c
                        for c in self._commands.values()
                        if c.kind in ("cancel_automatic", "remove_cancel")
                    ),
                    key=lambda c: c.sequence,
                )
            )
        # Validate against the pre-response state before any queued local action
        # is saved or consumed. A malformed whole response has no partial effects.
        self._merge_consent(self._state, result.status.consent)
        if work.operation != "fetch_automatic":
            selected = self._state.automatic.pending
            if (
                selected is None
                or selected.command != work.payload
                or not selected.attempted
            ):
                raise _Obsolete
            if result.receipt is not None and (
                not isinstance(result.receipt, p.AutomaticReceipt)
                or result.receipt.command != selected.command
            ):
                raise FleetRelayError(
                    None, "malformed_response", "Receipt command mismatch"
                )
        # Cancellation changes fence positive dispatch, not the old On receipt.
        # Apply the captured explicit actions in order after HTTP drains. Later
        # callbacks stay queued and can still use the bounded saved On receipt.
        for action in actions:
            if not self._command_binding_current(action, self.status().metadata):
                continue
            if action.kind == "cancel_automatic":
                self._save_automatic_cancel(action, fence, work=historical)
            elif action.payload == self._state.automatic.pending:
                self._persist(
                    replace(
                        self._state,
                        automatic=replace(
                            self._state.automatic,
                            pending=replace(action.payload, cancel_after_on=None),
                        ),
                    ),
                    fence,
                    work=historical,
                )
            self._drop_command(action.kind, action)
        dismissed = None
        previous_consent = self._state.automatic.observed_consent
        candidate = self._merge_consent(self._state, result.status.consent)
        pending = candidate.automatic.pending
        if work.operation != "fetch_automatic":
            receipt = result.receipt
            if (
                pending is None
                or pending.command != work.payload
                or not pending.attempted
            ):
                raise _Obsolete
            if receipt is not None:
                with self._lock:
                    action = self._commands.get("automatic")
                    if (
                        action is not None
                        and action.kind == "dismiss_automatic"
                        and self._command_binding_current(action, self._status.metadata)
                        and action.payload == pending
                        and (
                            not pending.command.enabled
                            or self._on_expired_proven_locked(pending.command)
                        )
                    ):
                        dismissed = action
                if dismissed is not None:
                    # The exact receipt remains evidence of On, but an admitted
                    # whole-journal dismissal also retires its unsent cancellation.
                    candidate = replace(
                        candidate,
                        automatic=replace(
                            candidate.automatic,
                            pending=replace(pending, cancel_after_on=None),
                        ),
                    )
                candidate = s.settle_automatic_receipt(candidate, receipt)
            else:
                candidate = replace(
                    candidate,
                    automatic=replace(
                        candidate.automatic,
                        pending=None,
                        last_result=s.AutomaticCompletion(pending, "already_off"),
                    ),
                )
        pending = candidate.automatic.pending
        if (
            pending is not None
            and not pending.command.enabled
            and not result.status.consent.enabled
            and result.status.consent.revision
            == candidate.automatic.observed_consent.revision
        ):
            candidate = replace(
                candidate,
                automatic=replace(
                    candidate.automatic,
                    pending=None,
                    last_result=s.AutomaticCompletion(pending, "observed_off"),
                ),
            )
        self._persist(candidate, fence, work=historical)
        if dismissed is not None:
            self._drop_command("automatic", dismissed)
        observed = candidate.automatic.observed_consent
        if observed != previous_consent:
            self._invalidate_source_evidence()
        if observed.revision == result.status.consent.revision:
            self._automatic_observation = result.status
        self._automatic_probe = False
        self._due["automatic"] = self._clock() + 2.0
        with self._lock:
            queued = any(
                c.kind in ("automatic", "cancel_automatic")
                for c in self._commands.values()
            )
        self._update_status(
            automatic_status=self._automatic_observation,
            automatic_stage="queued"
            if queued
            else "persisted"
            if candidate.automatic.pending
            else "settled",
        )

    def _invalidate_source_evidence(self):
        self._eligibility = self._sources = None
        # Invalidated evidence is immediately due, but must not jump ahead of
        # every older periodic class after each successful source mutation.
        now = self._clock()
        for key in ("eligibility", "sources"):
            self._due[key] = min(self._due[key], now)
        with self._lock:
            self._automatic_generation += 1
        self._update_status(eligibility=None, sources=None)

    def _merge_consent(self, state, incoming):
        old = state.automatic.observed_consent
        if old is not None:
            if incoming.revision < old.revision:
                return state
            if incoming.revision == old.revision and not p._same_consent(old, incoming):
                raise FleetRelayError(
                    None, "malformed_response", "Contradictory consent"
                )
        return replace(
            state, automatic=replace(state.automatic, observed_consent=incoming)
        )

    def _eligibility_work(self) -> Work:
        eligibility = self._eligibility
        urgent = (
            eligibility is not None
            and eligibility.state == "ready"
            and any(
                self._remaining(entry.expires_at) <= ELIGIBILITY_URGENCY_WINDOW_S
                for entry in eligibility.characters
            )
        )
        return Work(
            "fetch_eligibility",
            "eligibility",
            due=self._due["eligibility"],
            priority=1 if urgent else 2,
            periodic=True,
        )

    @staticmethod
    def _source_work_key(command):
        # Explicit same-source Stop replacement retains its retry floor;
        # submission generations would let repeated clicks defeat backoff.
        kind = "stop" if isinstance(command, p.StopSource) else "start"
        return "source:" + kind + ":" + command.source_id.lower()

    def _prune_source_work(self):
        self._source_observe.intersection_update(
            command.source_id for command in self._state.pending_source_commands
        )
        self._scheduler.retain(
            "source:",
            {self._source_work_key(c) for c in self._state.pending_source_commands},
        )

    def _acknowledge_rights(self):
        return tuple(
            capability
            for capability in COMBAT_CAPABILITIES
            if capability in (self._state.approved_capabilities or ())
            and capability in (self._state.session_approved_capabilities or ())
        )

    def _combat_disclosure(self, required=COMBAT_CAPABILITIES):
        state = self._state
        return all(
            capability in (rights or ())
            for rights in (
                state.approved_capabilities,
                state.session_approved_capabilities,
                state.acknowledged_capabilities,
            )
            for capability in required
        )

    def _publication(self):
        proof = self._eligibility_proof
        if (
            proof is None
            or proof.response is not self._eligibility
            or not self._combat_disclosure(CAPABILITIES)
            or self._catalogue is None
            or self._eligibility is None
        ):
            return None
        try:
            with self._lock:
                self._check_locked(
                    proof.fence, work=Work("publish_snapshot", "publication")
                )
                source = self._latest
        except _Obsolete:
            return None
        if self._eligibility.participation_generation != getattr(
            self._state.observed_participation, "generation", None
        ):
            return None
        if self._eligibility.state == "not_verified":
            if not self._last_published:
                return None
            return _PublicationSelection(
                None,
                None,
                self._catalogue,
                self._eligibility,
                proof,
                frozenset(),
                (),
                self._expires_at,
                (),
                "source_eligibility_lost",
            )
        try:
            current = getattr(source, "is_current", None)
            if not callable(current) or current() is not True:
                return None
            snapshot = source.snapshot
        except Exception:  # noqa: BLE001 — unavailable producer advice must not suppress independent receiving or control; final leaf exceptions are not handled here.
            return None
        now = self._clock()
        m = snapshot.sampled_at_mono
        if (
            m is None
            or not isfinite(m)
            or not isfinite(now)
            or not 0 <= Fraction(now) - Fraction(m) < MAX_SNAPSHOT_AGE_S
            or snapshot.metric_error is not None
            or self._eligibility.state != "ready"
        ):
            return None
        entries = {c.character_id: c for c in self._eligibility.characters}
        eligible = frozenset(entries)
        owned = frozenset(c.character_id for c in self._catalogue.characters)
        resolved = tuple(
            projection._resolved_combat_rows(snapshot, self._catalogue, owned)
        )
        # Missing ownership or unavailable/legacy metrics cannot silently erase a
        # member of the previous atomic publication, even beside healthy rows.
        if len(resolved) != len(snapshot.rows) or any(
            row.combat is None or (row.dps is None and row.incoming_dps is None)
            for _, row in resolved
        ):
            return None
        try:
            for _, row in resolved:
                p._dps(row.dps)
                p._dps(row.incoming_dps)
        except ValueError:
            return None
        projected = projection.project_combat_snapshot(
            snapshot,
            self._catalogue,
            eligible_character_ids=owned,
            now_mono=now,
        )
        # Validate the complete local temporal handoff BEFORE permission filtering;
        # an invalid ineligible member is not evidence of whole-source inactivity.
        if projected is None:
            return None
        rows = tuple(row for row in projected if row.character_id in eligible)
        reason = None
        if not rows:
            if not self._last_published:
                return None
            reason = (
                "inactive"
                if not resolved or any(cid in eligible for cid, _ in resolved)
                else "source_eligibility_lost"
            )
        elif not self._combat_disclosure():
            return None
        deadlines = dict(proof.deadlines)
        members = tuple(deadlines[cid] for cid, _ in resolved if cid in eligible)
        if any(deadline <= now for deadline in members):
            return None
        return _PublicationSelection(
            source,
            snapshot,
            self._catalogue,
            self._eligibility,
            proof,
            eligible,
            # The minimum proves every selected member while keeping final leaf
            # work constant even for a large inactive local roster.
            (min(members),) if members else (),
            self._expires_at,
            tuple(
                (r.character_id, r.row.dps, r.row.incoming_dps, r.row.combat)
                for r in rows
            ),
            reason,
        )

    def _validate_publication_permission_locked(self, selected, fence, work, now):
        self._check_locked(fence, work=work)
        self._check_locked(selected.proof.fence, work=work)
        part = self._state.observed_participation
        if (
            self._inhibit
            or not self._state.feature_enabled
            or not self._combat_disclosure(
                CAPABILITIES if selected.withdrawal_reason else COMBAT_CAPABILITIES
            )
            or not self._timing_open_locked(fence)
            or self._state.pending_participation is not None
            or part is None
            or not part.enabled
            or part.generation != selected.eligibility.participation_generation
            or selected.catalogue is not self._catalogue
            or selected.eligibility is not self._eligibility
            or selected.proof is not self._eligibility_proof
            or now >= selected.session_deadline
            or now >= self._expires_at
            or any(now >= deadline for deadline in selected.member_deadlines)
        ):
            raise _Obsolete

    def _validate_off_withdrawal_locked(self, fence, work, now):
        # The original Off intent/session fences and deadline survive the HTTP
        # wait. No local sample, membership proof or timing prerequisite applies.
        self._check_locked(fence, work=work)
        if (
            not isinstance(work.payload, _OffWithdrawal)
            or not self._withdraw_needed
            or not self._control_auth_current_locked()
            or self._control_auth != work.payload.auth
            or not self._combat_disclosure(CAPABILITIES)
            or not isfinite(now)
            or now >= work.payload.session_deadline
            or now >= self._expires_at
        ):
            raise _Obsolete

    def _check_publication_completion(self, selected, fence, work, receipt):
        if selected is None:
            with self._lock:
                self._validate_off_withdrawal_locked(fence, work, receipt)
            return
        if selected.source is not None and selected.source.is_current() is not True:
            raise _Obsolete
        with self._lock:
            self._validate_publication_permission_locked(selected, fence, work, receipt)

    @staticmethod
    def _with_publication_source_locked(work, install):
        # This is the ORIGINAL non-consuming leaf, not another HTTP admission.
        # Every needed worker/status lock is already held; install is bounded,
        # with no lock acquisition, I/O, source reentry or notification inside.
        source = None if work.key == "withdraw" else work.payload.source
        if source is None:
            install()
        elif source.admit_start(install) is not True:
            raise _Obsolete

    def _validate_publication_completion_locked(self, work, fence, receipt):
        if work.key == "withdraw":
            self._validate_off_withdrawal_locked(fence, work, receipt)
        else:
            self._validate_publication_permission_locked(
                work.payload, fence, work, receipt
            )

    def _publication_success_status_locked(self):
        # Same presentation precedence as the common success tail, but its
        # candidate and ACK must install together under publication authority.
        changes = {}
        if (
            self._state.cutover is not None
            and self._state.pending_participation is None
            and self._status.participation == "needs_confirmation"
            and any(
                item.selector == "participation" and item.status == "observed_choice"
                for item in self._state.cutover.outcomes
            )
        ):
            changes["participation"] = "observed_choice"
        if self._archived_choice() is not None:
            changes.update(
                state="refused",
                detail="unresolved_previous_choice",
                local_inhibited=True,
            )
        elif (
            self._state.pending_pairing is not None
            and self._state.pending_pairing == self._parked_pairing
        ):
            changes.update(
                state="refused",
                detail="unresolved_approval",
                pairing="unresolved_approval",
                approval_url=None,
            )
        elif self._timing_context._timing_loss is not None:
            changes.update(
                state="refused", detail=self._timing_context._timing_loss.reason
            )
        elif (
            self._control_auth_current_locked()
            and not self._timing_scope_current_locked()
        ):
            changes.update(state="refused", detail="timing_scope_mismatch")
        elif not self._needs_fresh_intent and self._state.auth_pause is None:
            changes.update(state="active", detail=None)
        return self._status_candidate_locked(**changes) if changes else None

    def _accept_publication(self, work, fence, receipt):
        with self._lock, self._status_lock:
            status = self._publication_success_status_locked()

            def install():
                self._validate_publication_completion_locked(work, fence, receipt)
                self._last_published = (
                    () if work.key == "withdraw" else work.payload.semantic
                )
                self._last_publish_at = receipt
                if work.key == "withdraw":
                    self._withdraw_needed = False
                if status is not None:
                    self._status = status

            self._with_publication_source_locked(work, install)
        if status is not None:
            self._notify("status", status)

    def _reset_publication_session(
        self, work, fence, reset_fence, receipt, candidate, auth
    ):
        with self._lock, self._status_lock:
            status = self._status_candidate_locked(
                sources=None,
                eligibility=None,
                observed_participation=self._state.observed_participation,
            )
            notifications = ()

            def install():
                nonlocal notifications
                # The admitted save is irreversible. Only its exact result state
                # and original generations/auth may authorize this later reset.
                # Session rights were deliberately cleared by that saved value;
                # never treat an arbitrary session=None as completion authority.
                self._check_locked(reset_fence, work=work)
                if (
                    self._state is not candidate
                    or self._control_auth != auth
                    or not isfinite(receipt)
                    or receipt >= work.payload.session_deadline
                    or receipt >= self._expires_at
                ):
                    raise _Obsolete
                if work.key == "withdraw":
                    if not self._withdraw_needed or auth != work.payload.auth:
                        raise _Obsolete
                else:
                    selected = work.payload
                    context = self._timing_context
                    if (
                        self._inhibit
                        or context._timing_loss is not None
                        or context._inconsistent
                        or context._timing_generation != fence.timing
                        or not self._timing_scope_current_locked()
                        or selected.catalogue is not self._catalogue
                        or selected.eligibility is not self._eligibility
                        or selected.proof is not self._eligibility_proof
                        or any(
                            receipt >= deadline
                            for deadline in selected.member_deadlines
                        )
                    ):
                        raise _Obsolete
                self._pairing_pollable = None
                notifications = self._reset_session_caches_locked()
                if status is not None:
                    self._status = status

            self._with_publication_source_locked(work, install)
        for kind, event in (*notifications, ("status", status)):
            if event is not None:
                self._notify(kind, event)

    def _recovery_work(self):
        pending = self._state.pending_recovery
        fence = self._fence()
        if pending is not None:
            expired = (
                self._remaining(pending.challenge.expires_at) <= 0
                if pending.challenge
                else not -60 < self._remaining(pending.issued_at) <= 60
            )
            if expired or pending.completion_attempted:
                # Completion is one-use even when acceptance/save failed. Replace
                # the bounded journal, never clear its attempt flag on this binding.
                pending = None
        if pending is None:
            pending = s.PendingRecovery(secrets.token_urlsafe(32), self._utc_text())
            self._persist(replace(self._state, pending_recovery=pending), fence)
        operation = "complete_recovery" if pending.challenge else "begin_recovery"
        return (Work(operation, "recovery", priority=1),)

    def _execute(self, work, fence):
        self._check(fence, work=work)
        prepared = None
        selected = (
            work.payload
            if (work.operation == "publish_snapshot" and work.key != "withdraw")
            else None
        )
        if selected is not None and selected.withdrawal_reason is None:
            prepared = self._timing_context._stage_publication(
                selected.source,
                selected.catalogue,
                eligible_character_ids=selected.eligible_character_ids,
            )
            if prepared is None or prepared.snapshot is not selected.snapshot:
                raise _Obsolete
        elif selected is not None and selected.source is not None:
            # One selected-lane check, not a planning scan or a second pin owner.
            # An empty projection alone does not prove immutable source evidence.
            if (
                self._timing_context._checked_publication_sample(
                    selected.snapshot,
                    selected.catalogue,
                    frozenset(c.character_id for c in selected.catalogue.characters),
                    Fraction(self._clock()),
                )
                is None
            ):
                raise _Obsolete
        started = receipt = None
        failed = False
        first_automatic_attempt = False
        timing_refusal = None

        def validate_publication():
            nonlocal started, timing_refusal
            self._check_locked(fence, work=work)
            if prepared is not None:
                try:
                    start = self._timing_context._validate_publication(prepared)
                except ValueError as exc:
                    timing_refusal = exc
                    raise
            else:
                start = self._clock()
                if not isfinite(start) or (
                    selected.source is not None
                    and not 0
                    <= Fraction(start) - Fraction(selected.snapshot.sampled_at_mono)
                    < MAX_SNAPSHOT_AGE_S
                ):
                    raise _Obsolete
            self._validate_publication_permission_locked(selected, fence, work, start)
            started = start

        def before_send():
            nonlocal started
            with self._lock:
                if selected is not None:
                    if selected.source is None:
                        validate_publication()
                    elif selected.source.admit_start(validate_publication) is not True:
                        raise _Obsolete
                    return
                if work.key == "withdraw":
                    start = self._clock()
                    self._validate_off_withdrawal_locked(fence, work, start)
                    started = start
                    return
                self._check_locked(fence, work=work)
                if (
                    work.operation in ("read_snapshot", "publish_snapshot")
                    and work.key != "withdraw"
                    and (self._inhibit or not self._timing_open_locked(fence))
                ):
                    raise _Obsolete
                if work.operation in (
                    "control_source",
                    "control_automatic",
                    "fetch_receipt",
                    "fetch_automatic",
                    "set_participation",
                ) and (
                    not self._control_auth_current_locked()
                    or self._clock() >= self._expires_at
                ):
                    raise _Obsolete
                if work.operation in ("control_source", "control_automatic"):
                    command = work.payload
                    remaining = self._remaining(command.intent_created_at)
                    if remaining > 0 or (
                        (
                            isinstance(command, (p.SourceStart, p.SourceStop))
                            or command.enabled
                        )
                        and remaining <= -60
                    ):
                        raise _Obsolete
                started = self._clock()
                if (
                    work.operation == "read_snapshot"
                    and not self._timing_context._start_snapshot_get(started_at=started)
                ):
                    started = None
                    raise _Obsolete

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
                if operation == "control_automatic":
                    pending = candidate.automatic.pending
                    if pending is None or pending.command != work.payload:
                        raise _Obsolete
                    first_automatic_attempt = not pending.attempted
                    # Even a post-write fence refusal leaves durable attempted
                    # evidence. Its next turn seeks a receipt before any retry.
                    self._automatic_receipt_first = True
                    candidate = replace(
                        candidate,
                        automatic=replace(
                            candidate.automatic,
                            pending=replace(pending, attempted=True),
                        ),
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
                    args["sampled_at_ms"] = prepared.sampled_at_ms if prepared else 0
                    args["rows"] = prepared.rows if prepared else ()
                elif operation == "set_participation":
                    args.update(
                        enabled=work.payload.enabled,
                        expected_generation=work.payload.expected_generation,
                    )
                    self._part_observe = True
                elif operation == "control_automatic":
                    args["command"] = work.payload
                elif operation == "control_source":
                    args["command"] = work.payload
                    self._source_observe.add(work.payload.source_id)
                elif operation == "fetch_receipt":
                    args["request_id"] = work.payload.request_id
                elif operation == "acknowledge_capabilities":
                    args["capabilities"] = self._acknowledge_rights()
            elif operation == "begin_recovery":
                pending = self._state.pending_recovery
                args = dict(
                    private_key=private_key,
                    request_id=pending.request_id,
                    issued_at=pending.issued_at,
                )
            elif operation == "complete_recovery":
                self._persist(
                    replace(
                        self._state,
                        pending_recovery=replace(
                            self._state.pending_recovery,
                            completion_attempted=True,
                        ),
                    ),
                    fence,
                    work=work,
                )
                args = dict(
                    private_key=private_key,
                    challenge=self._state.pending_recovery.challenge,
                )
            elif operation == "begin_pairing":
                args = dict(
                    public_key_spki=base64.b64decode(
                        state.identity.public_key_spki_b64
                    ),
                    requested_capabilities=state.pending_pairing.requested_capabilities,
                )
            elif operation == "complete_pairing":
                pairing = self._state.pending_pairing
                self._pairing_pollable = None
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
            result = getattr(self._client, operation)(**args, before_send=before_send)
            receipt = self._clock()
            if started is None:
                # A client that never admitted transport cannot acknowledge work.
                raise _Obsolete
            self._check(
                fence,
                work=replace(work, operation="fetch_receipt")
                if operation == "control_automatic"
                else work,
            )
            if operation == "publish_snapshot":
                self._check_publication_completion(selected, fence, work, receipt)
            self._accept(work, result, fence, started, receipt)
        except ValueError as exc:
            if exc is timing_refusal:
                raise _Obsolete from None
            raise
        except FleetRelayError as exc:
            receipt = self._clock()
            failed = True
            if started is None:
                raise _Obsolete from None
            self._check(fence, work=work)
            if work.operation == "publish_snapshot":
                self._check_publication_completion(selected, fence, work, receipt)
            if first_automatic_attempt and exc.code in (
                "bad_request",
                "invalid_intent",
                "forbidden",
                "capability_required",
                "feature_disabled",
                "conflict",
                "request_id_conflict",
            ):
                pending = self._state.automatic.pending
                self._persist(
                    replace(
                        self._state,
                        automatic=replace(
                            self._state.automatic,
                            pending=None,
                            last_result=s.AutomaticCompletion(pending, "rejected"),
                        ),
                    ),
                    fence,
                    work=work,
                )
                self._automatic_probe = True
                self._update_status(automatic_stage="rejected")
            elif work.operation == "publish_snapshot":
                self._relay_error(work, exc, fence, receipt=receipt)
            else:
                self._relay_error(work, exc, fence)
        finally:
            if started is not None:
                if work.operation == "read_snapshot":
                    self._timing_context._finish_snapshot_get(started_at=started)
                self._scheduler.completed(
                    work,
                    receipt if receipt is not None else self._clock(),
                    failed=failed,
                    jitter=self._jitter() if failed else 0,
                )
                # Completion may retire a journal (or be obsolete). Do not keep
                # historical UUID backoff, or resurrect it after reconciliation.
                self._prune_source_work()
            self._apply_timing_loss()

    def _accept(self, work, result, fence, started, receipt):
        operation = work.operation
        if operation in ("fetch_device", "acknowledge_capabilities"):
            self._accept_device(result, fence, work)
            candidate = self._timing_context._evaluate_diagnostic(
                started_at=started,
                received_at=receipt,
                server_time_ms=result.server_time_ms,
            )
            self._accept_timing_candidate(candidate, fence, work)
        elif operation == "renew_session":
            self._persist(
                replace(self._state, session_expires_at=result), fence, work=work
            )
            self._expiry_binding = None
        elif operation == "fetch_catalogue":
            self._set_catalogue(result, fence=fence)
            self._due["catalogue"] = self._clock() + CATALOGUE_REFRESH_INTERVAL_S
        elif operation == "fetch_eligibility":
            # Capture elapsed BEFORE UTC. Time spent in the external clock cannot
            # extend the proof. Convert once, never on planning or under a leaf.
            elapsed = Fraction(self._clock())
            utc = self._utc_now()
            deadlines = []
            for entry in result.characters:
                deadlines.append(
                    (
                        entry.character_id,
                        self._elapsed_expiry(entry.expires_at, elapsed, utc),
                    )
                )
            with self._lock:
                self._check_locked(fence, work=work)
                self._eligibility = result
                self._eligibility_proof = _EligibilityProof(
                    result, fence, tuple(deadlines)
                )
            self._due["eligibility"] = self._clock() + ELIGIBILITY_REFRESH_INTERVAL_S
            self._update_status(eligibility=result)
        elif operation == "publish_snapshot":
            self._accept_publication(work, fence, receipt)
            return  # Publication status must not escape into the unfenced tail.
        elif operation == "read_snapshot":
            self._due["read"] = self._clock() + 1.0
            if not self._timing_context._finish_snapshot_get(started_at=started):
                return
            candidate = self._timing_context._evaluate_snapshot(
                result, started_at=started, received_at=receipt
            )
            self._accept_timing_candidate(candidate, fence, work, remote=True)
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
        elif operation in ("fetch_automatic", "control_automatic") or (
            operation == "fetch_receipt"
            and isinstance(work.payload, p.AutomaticCommand)
        ):
            self._accept_automatic(work, result, fence)
        elif operation == "fetch_receipt":
            if not isinstance(
                result.receipt, p.SourceStopReceipt
            ) or not p._same_stop_command(work.payload, result.receipt.command):
                raise FleetRelayError(
                    None, "malformed_response", "Receipt command mismatch"
                )
            self._finish_source(
                work.payload,
                replace(result.receipt, command=work.payload),
                fence,
                work,
                status=result.status,
            )
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
        fence = replace(fence, session=self._state.session_id)
        self._check(fence, work=work)
        with self._lock:
            timing_scope_mismatch = (
                self._control_auth_current_locked()
                and not self._timing_scope_current_locked()
            )
        if (
            self._state.cutover is not None
            and self._state.pending_participation is None
            and self.status().participation == "needs_confirmation"
            and any(
                item.selector == "participation" and item.status == "observed_choice"
                for item in self._state.cutover.outcomes
            )
        ):
            self._update_status(fence=fence, participation="observed_choice")
        if self._archived_choice() is not None:
            self._update_status(
                state="refused",
                detail="unresolved_previous_choice",
                local_inhibited=True,
            )
        elif (
            self._state.pending_pairing is not None
            and self._state.pending_pairing == self._parked_pairing
        ):
            self._update_status(
                fence=fence,
                state="refused",
                detail="unresolved_approval",
                pairing="unresolved_approval",
                approval_url=None,
            )
        elif self._timing_context._timing_loss is not None:
            self._update_status(
                state="refused", detail=self._timing_context._timing_loss.reason
            )
        elif timing_scope_mismatch:
            self._update_status(state="refused", detail="timing_scope_mismatch")
        elif not self._needs_fresh_intent and self._state.auth_pause is None:
            self._update_status(state="active", detail=None)

    def _check_device_identity(self, device_id, fence, work):
        with self._lock:
            self._check_locked(fence, work=work)
            expected = self._state.device_id
            if expected is not None and expected.lower() != device_id.lower():
                self._identity_mismatch = True
                self._inhibit = True
                self._authenticated_device = None
            else:
                return
        self._clear_remote()
        self._update_status(
            state="refused", detail="identity_mismatch", local_inhibited=True
        )
        raise _Obsolete

    def _accept_device(self, device, fence, work):
        self._check_device_identity(device.device_id, fence, work)
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
        candidate = self._settle_archive(candidate, participation=device.participation)
        with self._lock:
            queued_participation = "participation" in self._commands
        intent = candidate.pending_participation
        acknowledged = False
        # Deferred controls allow this observation, not effects belonging to a
        # superseded intent. Keep its uncertainty on disk and local inhibit on.
        if intent is not None and not queued_participation:
            if intent.expected_generation is None:
                self._needs_fresh_intent = True
            elif device.participation.enabled == intent.enabled:
                candidate = replace(candidate, pending_participation=None)
                acknowledged = True
            elif device.participation.generation != intent.expected_generation:
                self._needs_fresh_intent = True
        self._persist(candidate, fence, work=work)
        self._authenticated_device = device.device_id
        self._bind_control_auth(device.device_id, fence, work)
        with self._lock:
            self._check_locked(fence, work=work)
            self._control_db_fact = (
                self._control_auth,
                self._timing_context._db_continuity_token,
                device.server_time_ms,
            )
        self._needs_device = False
        self._part_observe = queued_participation
        self._resume_metadata = False
        self._due["device"] = self._clock() + 60.0
        self._expiry()
        if queued_participation:
            pass  # Metadata only; queued/durable/CAS are distinct stages.
        elif self._needs_fresh_intent:
            self._update_status(
                state="refused",
                detail="needs_fresh_intent",
                participation="needs_confirmation",
            )
        elif acknowledged:
            self._participation_ack(device.participation.enabled)
            self._update_status(participation="observed_choice")
        elif (
            intent is None
            and device.participation.enabled
            and self._archived_choice() is None
            and self._state.pending_pairing is None
        ):
            with self._lock:
                self._inhibit = False
            self._update_status(local_inhibited=False)
        if not device.participation.enabled:
            self._eligibility = None
            self._clear_remote()
        self._update_status(observed_participation=device.participation)

    def _participation_ack(self, enabled):
        inhibited = not enabled or self._archived_choice() is not None
        with self._lock:
            self._inhibit = inhibited
        self._needs_fresh_intent = self._part_observe = False
        self._eligibility = None
        self._due["eligibility"] = 0
        if not enabled:
            self._clear_remote()
        self._update_status(
            participation="acknowledged",
            local_inhibited=inhibited,
            eligibility=None,
            observed_participation=self._state.observed_participation,
        )

    def _accept_sources(self, result, fence, work):
        self._check(fence, work=work)
        # A catalogue lacks original intent provenance. Even an ended manual
        # UUID is only an observation, not settlement of this immutable command.
        clear = False
        self._source_observe.intersection_update(
            c.source_id
            for c in self._state.pending_source_commands
            if isinstance(c, p.StopSource)
        )
        if self._sources:
            live = {v.source_id for v in self._sources.sources if v.state != "ended"}
            current = {v.source_id for v in result.sources if v.state != "ended"}
            clear |= bool(live - current)
        self._sources = result
        self._due["sources"] = self._clock() + 2.0
        if clear:
            self._clear_remote()
        self._update_status(
            fence=fence,
            sources=result,
            source_control="persisted"
            if self._state.pending_source_commands
            else self.status().source_control,
        )

    def _finish_source(self, command, result, fence, work, *, status=None):
        if command not in self._state.pending_source_commands:
            raise _Obsolete
        view = result.source
        commands = tuple(
            c
            for c in self._state.pending_source_commands
            if c.source_id.lower() != command.source_id.lower()
        )
        candidate = replace(self._state, pending_source_commands=commands)
        if isinstance(command, p.StopSource):
            with self._lock:
                if not self._terminal_authenticated_locked():
                    raise _Obsolete
            candidate = self._merge_consent(
                candidate, (status or result.status).consent
            )
        self._persist(candidate, fence, work=work)
        if isinstance(command, p.StopSource):
            current = status or result.status
            if (
                candidate.automatic.observed_consent.revision
                == current.consent.revision
            ):
                self._automatic_observation = current
                self._due["automatic"] = self._clock() + 2.0
                self._update_status(automatic_status=current)
        self._source_observe.discard(command.source_id)
        self._invalidate_source_evidence()
        if view.state == "ended":
            self._clear_remote()
        self._update_status(source_control="acknowledged", sources=self._sources)

    def _accept_recovery(self, result, fence, work):
        if result.result == "reconnected":
            self._check_device_identity(result.device_id, fence, work)
            pairing = self._state.pending_pairing
            unfulfilled = (
                pairing
                if pairing
                and not set(pairing.requested_capabilities).issubset(
                    result.approved_capabilities
                )
                else None
            )
            candidate = replace(
                s.replace_session(
                    self._state, result.session_id, expires_at=result.session_expires_at
                ),
                device_id=result.device_id,
                approved_capabilities=result.approved_capabilities,
                observed_participation=result.participation,
                pending_recovery=None,
                auth_pause=None,
                pending_pairing=unfulfilled,
            )
            candidate = self._settle_archive(
                candidate, participation=result.participation, recovered=True
            )
            self._persist(candidate, fence, work=work)
            self._reset_session()
            self._authenticated_device = result.device_id
            self._bind_control_auth(
                result.device_id, replace(fence, session=result.session_id), work
            )
            # Recovery proves actual D, not completion of the requested upgrade.
            # Park only that immutable pairing; other work keeps its own admission.
            self._parked_pairing = unfulfilled
            if pairing is not None:
                self._resume_metadata = True
                self._update_status(
                    fence=replace(fence, session=self._state.session_id),
                    pairing="unresolved_approval" if unfulfilled else "acknowledged",
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

    def _relay_error(self, work, exc, fence, *, receipt=None):
        code = exc.code if exc.code in ERROR_CODES else "server_error"
        operation = work.operation
        if operation == "publish_snapshot":
            catalogue = None
            with self._lock, self._status_lock:
                status = self._status_candidate_locked(state="error", detail=code)
                auth = self._control_auth

                def install():
                    nonlocal catalogue
                    self._validate_publication_completion_locked(work, fence, receipt)
                    if status is not None:
                        self._status = status
                    if exc.status != 401 and exc.code in (
                        "forbidden",
                        "capability_required",
                        "feature_disabled",
                    ):
                        self._needs_device = True
                        self._eligibility = None
                        catalogue = self._set_catalogue_locked(None)
                        self._due["catalogue"] = self._due["eligibility"] = 0

                self._with_publication_source_locked(work, install)
            if status is not None:
                self._notify("status", status)
            if catalogue is not None:
                self._notify("catalogue", catalogue)
            if exc.status != 401:
                return
        else:
            self._update_status(state="error", detail=code)
        if operation == "complete_pairing":
            if exc.status == 409 and exc.code == "not_completable":
                # This live typed negative proves only this poll did not mint a
                # session. Keep durable uncertainty; never carry knowledge across
                # restart, response loss, or a replacement pairing binding.
                self._pairing_pollable = self._state.pending_pairing
            return
        if (
            operation == "begin_recovery"
            and exc.status == 401
            and self._state.pending_pairing is not None
            and self._state.pending_pairing.mode == "initial"
        ):
            self._update_status(pairing="needs_retry", approval_url=None)
        if operation == "complete_recovery":
            # Retain attempted evidence until a fresh initiation is durably saved.
            return
        if exc.status == 401 and OPERATIONS[operation] != "bootstrap":
            # The final attempted revision is evidence even when it got a 401.
            # The exhaustion gate recovers without another signed use or reset.
            reset_fence = fence
            candidate = self._state
            if self._state.last_revision < p.INT4_MAX:
                candidate = s.replace_session(self._state, None)
                self._persist(candidate, fence, work=work)
                reset_fence = replace(fence, session=candidate.session_id)
            if operation == "publish_snapshot":
                self._reset_publication_session(
                    work, fence, reset_fence, receipt, candidate, auth
                )
            else:
                self._reset_session()
        elif operation == "set_participation":
            self._part_observe = self._needs_device = True
        elif operation == "control_source":
            self._source_observe.add(work.payload.source_id)
        elif operation == "fetch_receipt" and exc.code == "receipt_not_found":
            if isinstance(work.payload, p.AutomaticCommand):
                self._automatic_receipt_first = False
                self._automatic_probe = True
            else:
                self._source_observe.discard(work.payload.source_id)
        elif operation == "control_automatic":
            self._automatic_receipt_first = True
        elif exc.code in ("forbidden", "capability_required", "feature_disabled"):
            self._needs_device = True
            self._eligibility = None
            self._set_catalogue(None)
            self._due["catalogue"] = self._due["eligibility"] = 0


__all__ = [
    "CatalogueEvent",
    "FleetSharingWorker",
    "PendingSourceStatus",
    "RemoteEvent",
    "SharingMetadata",
    "SharingStatus",
]
