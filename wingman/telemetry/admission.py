"""Process-local source proof, independent of Fleet sharing's consumer port.

All state lives behind one leaf Lock. Callers acquire producer, dispatcher or
worker locks FIRST. Only a ticket's trusted bounded validator runs under this
lock: no I/O, waiting, subscribers, snapshot computation or acquisition of other
locks, including re-entry into this authority. The guard is non-consuming for
both logical request start and original-source completion installation.

Private methods are for the producer/coordinator integration, not consumers.
Receipts acknowledge successful *complete associated work*, not model cleanliness.
An old ACK can be ignored even when its old payload contaminated the model.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Lock
from typing import Literal

from .model import FleetSnapshot

_Lane = Literal["roster", "stream", "control"]
_LANES: tuple[_Lane, ...] = ("roster", "stream", "control")


@dataclass(frozen=True, slots=True)
class _Receipt:
    authority: object
    lane: _Lane
    lifetime: object
    order: int
    previous: int


@dataclass(frozen=True, slots=True)
class _Operation:
    """Original pre-work delivery coordinate, separate from invalidation ACKs."""

    authority: object
    lane: _Lane
    lifetime: object
    order: int


@dataclass(frozen=True, slots=True)
class _ResetBoundary:
    authority: object
    serial: int
    poison_serial: int


@dataclass(slots=True)
class _LaneState:
    lifetime: object | None = None
    running: bool = False
    requested: _Receipt | None = None
    applied: int = 0
    started: _Operation | None = None
    provenance: _Operation | None = None
    reset_cut: _Operation | None = None


@dataclass(frozen=True, slots=True)
class _Frontier:
    authority: object
    token: object
    receipts: tuple[_Receipt, ...]
    provenance: tuple[_Operation | None, ...]


@dataclass(frozen=True, slots=True, eq=False, init=False)
class SourceAdmissionTicket:
    """Frozen original snapshot/token binding; only the authority seals tickets.

    There is no public constructor/restamping interface. Consumers use exactly
    snapshot, is_current and admit_start.
    """

    _authority: _SourceAuthority = field(repr=False)
    _token: object = field(repr=False)
    _snapshot: FleetSnapshot

    def __init__(self) -> None:
        raise TypeError("source tickets can only be sealed by their authority")

    @property
    def snapshot(self) -> FleetSnapshot:
        return self._snapshot

    def is_current(self) -> bool:
        """Advisory only; atomic work must use admit_start instead."""
        with self._authority._lock:
            return self._authority._current_locked(self._token)

    def admit_start(self, validate: Callable[[], None]) -> bool:
        """Run a bounded leaf validator iff current; preserve its exception."""
        with self._authority._lock:
            if not self._authority._current_locked(self._token):
                return False
            validate()
            return True


class _SourceAuthority:
    """Three fixed lane slots, no receipt registry or retired lifetime history."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._identity = object()
        self._token = object()
        self._lanes = {lane: _LaneState() for lane in _LANES}
        self._next_reservation = 0
        self._closed = False
        self._poison_reason: str | None = None
        self._poison_serial = 0
        self._next_operation = 0
        self._reset_serial = 0
        self._pending_reset: _ResetBoundary | None = None
        self._applied_reset: _ResetBoundary | None = None

    def _begin(self, lane: _Lane) -> _Receipt | None:
        """Admit a lifetime only after its previous owner is proven stopped.

        Initial admission and restart both require fresh associated application.
        A refused/timed-out stop never permits a replacement or clears poison.
        """
        with self._lock:
            if self._closed:
                return None
            state = self._lanes[lane]
            if state.lifetime is not None:
                raise RuntimeError("previous source owner has not stopped")
            state.lifetime = object()
            state.running = True
            state.applied = 0
            state.requested = None
            state.started = None
            state.provenance = None
            return self._reserve_locked(lane, state)

    def _reserve(self, lane: _Lane, lifetime: object) -> _Receipt | None:
        """Revoke BEFORE actual producer mutation, under its mutation lock.

        Do not call for unchanged scans or fact-only operations. Carry the
        returned receipt unchanged with the resulting complete delivery. A
        retired operation must never acquire the replacement owner's receipt.
        """
        with self._lock:
            state = self._lanes[lane]
            if self._closed or not state.running or state.lifetime is not lifetime:
                return None
            return self._reserve_locked(lane, state)

    def _reserve_locked(self, lane: _Lane, state: _LaneState) -> _Receipt:
        self._next_reservation += 1
        previous = 0 if state.requested is None else state.requested.order
        receipt = _Receipt(
            self._identity, lane, state.lifetime, self._next_reservation, previous
        )
        state.requested = receipt
        self._token = object()
        return receipt

    def _stop(self, lane: _Lane, lifetime: object) -> None:
        """Revoke before unsubscribe/stop/join; does NOT authorize replacement."""
        with self._lock:
            state = self._lanes[lane]
            if state.lifetime is lifetime and state.running:
                state.running = False
                self._token = object()

    def _stopped(self, lane: _Lane, lifetime: object) -> None:
        """Owner confirms actual stop, outside join and under its lifecycle lock.

        Must follow _stop; never call on timeout. This is an external ownership
        proof supplied by the producer, not thread supervision by this leaf.
        """
        with self._lock:
            state = self._lanes[lane]
            if state.lifetime is lifetime and not state.running:
                state.lifetime = None
                state.requested = None
                state.applied = 0
                state.started = None
                state.provenance = None

    def _operation(self, lane: _Lane, lifetime: object) -> _Operation | None:
        """Capture BEFORE work, under producer ordering, even for fact-only work.

        Carry this exact coordinate across enumeration/read, enqueue, legacy
        callbacks and reentrant restart. Pair it with that operation's original
        receipt; a reservation during the operation does not change its order.
        Unchanged/failed operations need no application report or reservation.
        """
        with self._lock:
            state = self._lanes[lane]
            if self._closed or not state.running or state.lifetime is not lifetime:
                return None
            self._next_operation += 1
            operation = _Operation(self._identity, lane, lifetime, self._next_operation)
            state.started = operation
            return operation

    def _record_application(self, operation: _Operation) -> None:
        """Dispatcher reports actual successful model application, NOT an ACK.

        Report once the whole associated operation applies, including fact-only
        deliveries. Preserve legacy consumption first; obsolete payloads poison
        publication instead of being silently dropped. Failed application calls
        _poison directly and must not ACK. A demonstrably skipped roster reports
        neither application nor contamination.
        """
        with self._lock:
            state = self._lanes[operation.lane]
            if self._closed:
                return
            cut = state.reset_cut
            prior = state.provenance
            if (
                operation.authority is not self._identity
                or operation.lifetime is not state.lifetime
                or not state.running
                or (
                    cut is not None
                    and cut.lifetime is operation.lifetime
                    and operation.order <= cut.order
                )
                or (
                    prior is not None
                    and prior.lifetime is operation.lifetime
                    and operation.order < prior.order
                )
            ):
                self._poison_locked("obsolete source operation applied")
            state.provenance = operation

    def _reset_started(self) -> _ResetBoundary | None:
        """Dispatcher begins an EXISTING legitimate reset, before metrics work.

        This revokes admission; it neither performs a reset nor clears poison.
        Capture the old poison serial now, not after reset/reseed succeeds.
        """
        with self._lock:
            if self._closed:
                return None
            self._reset_serial += 1
            boundary = _ResetBoundary(
                self._identity, self._reset_serial, self._poison_serial
            )
            self._pending_reset = boundary
            self._token = object()
            return boundary

    def _reset_applied(self, boundary: _ResetBoundary) -> bool:
        """Report successful actual reset, on the serialized dispatcher only.

        Cut off ALL operations started through reset completion, including work
        overlapping reset within the same producer lifetime. Producer operations
        therefore capture order before doing work, not when delivering results.
        Reseeding must begin after this cut and report complete per-lane work.
        """
        with self._lock:
            if self._closed:
                return False
            if boundary is not self._pending_reset or boundary is self._applied_reset:
                self._poison_locked("obsolete reset applied")
                return False
            self._applied_reset = boundary
            for state in self._lanes.values():
                state.reset_cut = state.started
                state.provenance = None
            return True

    def _reseeded(self, boundary: _ResetBoundary) -> bool:
        """Complete that reset after successful full current roster/source reseed.

        Caller must report the whole reseed operation per lane, not its first
        sibling. C3 owns that semantic completion barrier. These bounded checks
        are necessary proof coordinates, never a substitute for actual reset or
        successful restatement. No unrelated reset/unpoison interface exists.
        """
        with self._lock:
            if (
                self._closed
                or boundary is not self._pending_reset
                or boundary is not self._applied_reset
                or boundary.poison_serial != self._poison_serial
                or not self._complete_locked()
            ):
                return False
            for state in self._lanes.values():
                operation = state.provenance
                cut = state.reset_cut
                if (
                    operation is None
                    or operation.authority is not self._identity
                    or operation.lifetime is not state.lifetime
                    or (
                        cut is not None
                        and cut.lifetime is operation.lifetime
                        and operation.order <= cut.order
                    )
                ):
                    return False
            self._pending_reset = None
            self._poison_reason = None
            self._token = object()
            return True

    def _applied(self, receipt: _Receipt) -> None:
        """ACK complete successful work, not payload cleanliness or recovery.

        A roster is a full restatement and may supersede older roster receipts.
        Stream/control work must complete in predecessor order. An out-of-order
        ACK is NOT buffered or upgraded to a maximum; the dispatcher must prove
        all preceding deltas applied, or perform a legitimate reset/reseed.
        """
        with self._lock:
            state = self._lanes[receipt.lane]
            if (
                self._closed
                or receipt.authority is not self._identity
                or not state.running
                or receipt.lifetime is not state.lifetime
                or state.requested is None
                or not state.applied < receipt.order <= state.requested.order
            ):
                return
            if receipt.lane != "roster" and receipt.previous != state.applied:
                return
            state.applied = receipt.order

    def _complete_locked(self) -> bool:
        return all(
            state.running
            and state.requested is not None
            and state.applied == state.requested.order
            for state in self._lanes.values()
        )

    def _current_locked(self, token: object) -> bool:
        return (
            not self._closed
            and self._poison_reason is None
            and self._pending_reset is None
            and token is self._token
            and self._complete_locked()
        )

    def _capture(self) -> _Frontier | None:
        """Capture before snapshot calculation, which must run outside the leaf."""
        with self._lock:
            return self._capture_locked()

    def _capture_locked(self) -> _Frontier | None:
        if not self._current_locked(self._token):
            return None
        return _Frontier(
            self._identity,
            self._token,
            tuple(self._lanes[lane].requested for lane in _LANES),
            tuple(self._lanes[lane].provenance for lane in _LANES),
        )

    def _seal(
        self, frontier: _Frontier, snapshot: FleetSnapshot
    ) -> SourceAdmissionTicket | None:
        """Bind the computed snapshot to its ORIGINAL still-current capture."""
        with self._lock:
            if frontier != self._capture_locked():
                return None
            ticket = object.__new__(SourceAdmissionTicket)
            object.__setattr__(ticket, "_authority", self)
            object.__setattr__(ticket, "_token", frontier.token)
            object.__setattr__(ticket, "_snapshot", snapshot)
            return ticket

    def _poison(self, reason: str) -> None:
        """Dispatcher reports failed work or actual obsolete payload application.

        Repeated poisoning advances the serial even while already blocked: an
        earlier reset/reseed attempt must never clear later contamination.
        """
        with self._lock:
            self._poison_locked(reason)

    def _poison_locked(self, reason: str) -> None:
        self._poison_serial += 1
        self._poison_reason = reason
        self._token = object()

    def _close(self) -> None:
        """Irreversible final admission close, before any external teardown."""
        with self._lock:
            self._closed = True
            self._token = object()
