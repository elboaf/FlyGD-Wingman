"""Retained process-local timing, owned by the existing serialized signed lane.

Construction establishes no authenticated identity. Only wholly validated,
authenticated, request-bound responses may reach diagnostic candidacy. A feasible
rolling intersection is necessary, not proof against hidden clock faults.
"""

from bisect import bisect_left
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from fractions import Fraction
from math import isfinite
from types import MappingProxyType

from ..combatprofile import LIMITS
from ..telemetry.model import FleetSnapshot, ObservationId
from .model import (
    CombatProjectionRow,
    FleetCatalogue,
    PublicationSource,
    TimedEffect,
    TimedObservation,
    TimedRemoteRow,
    TimedSnapshot,
    TimingFenceReason,
)
from .projection import _resolved_combat_rows, project_combat_snapshot
from .protocol import (
    API_VERSION,
    EFFECT_ORDER,
    JS_SAFE_MAX,
    CombatRow,
    CombatSnapshot,
    parse_combat_put,
)
from .scheduling import Scheduler

_DIAGNOSTIC_WINDOW_MS = (
    LIMITS["anchor_lifetime_ms"] + LIMITS["activity_ms"] + LIMITS["request_elapsed_ms"]
)
_DIAGNOSTIC_CAPACITY = _DIAGNOSTIC_WINDOW_MS // LIMITS["signed_interval_ms"] + 1


@dataclass(frozen=True)
class _TimingLoss:
    reason: TimingFenceReason
    cutoff: float | None


@dataclass(frozen=True)
class _Exchange:
    started_at: Fraction
    received_at: Fraction
    server_time_ms: int


@dataclass(frozen=True)
class _Anchor:
    server_time_ms: int
    received_at: Fraction


@dataclass(frozen=True)
class _ReceiverRecord:
    server_time_ms: int
    offset: Fraction


@dataclass(frozen=True)
class _ReceiverState:
    records: tuple[_ReceiverRecord, ...] = ()
    last_server_time_ms: int | None = None
    payload: TimedSnapshot | None = None
    recovering: bool = False
    recovery_r0: int | None = None


@dataclass(frozen=True)
class _TimingState:
    """One immutable accepted aggregate; baselines survive diagnostic pruning."""

    exchanges: tuple[_Exchange, ...] = ()
    lo: Fraction | None = None
    hi: Fraction | None = None
    last_started_at: Fraction | None = None
    last_received_at: Fraction | None = None
    last_server_time_ms: int | None = None
    anchor: _Anchor | None = None
    receiver: _ReceiverState = _ReceiverState()


@dataclass(frozen=True)
class _TimingCandidate:
    base: _TimingState
    state: _TimingState


@dataclass(frozen=True)
class _ClockContradiction:
    base: _TimingState
    reason: TimingFenceReason = "clock_inconsistent"


@dataclass(frozen=True)
class _Evidence:
    key: tuple
    coordinate: Fraction
    horizon: Fraction
    signature: object


@dataclass(frozen=True)
class _Pin:
    evidence: _Evidence
    origin_ms: int


@dataclass(frozen=True)
class _PublisherState:
    associations: Mapping[tuple, _Pin]


@dataclass(frozen=True)
class _PreparedPublication:
    source: PublicationSource
    snapshot: FleetSnapshot
    sampled_at_mono: float
    sampled_at_ms: int
    rows: tuple[CombatRow, ...]
    pins: tuple[_Pin, ...]
    _staged_at: Fraction
    # Reference identity, not a second mutable payload or a cryptographic seal.
    # Keeping this tiny binding avoids re-projecting or reading the source under
    # its leaf lock. Callers retain this value, never construct/restamp it.
    _seal: tuple


def _event(
    character_id: int,
    slot: str | tuple[str, str | None],
    observation_id: ObservationId,
    deadline: float,
) -> _Evidence:
    horizon = Fraction(deadline)
    return _Evidence(
        (character_id, observation_id[0], slot, observation_id),
        horizon - Fraction(LIMITS["activity_ms"], 1000),
        horizon,
        horizon,
    )


def _combat_rows(
    sample_ms: int,
    row_evidence: list[tuple[CombatProjectionRow, _Evidence, tuple[_Evidence, ...]]],
    associations: Mapping[tuple, _Pin],
) -> tuple[CombatRow, ...]:
    """Reuse the closed codec for all wire dimensions before committing pins."""
    rows = []
    for selected, row_event, effects in row_evidence:
        observations = selected.observations
        kinds = sorted({o.kind for o in observations}, key=EFFECT_ORDER.index)
        rows.append(
            {
                "character_id": selected.character_id,
                "outgoing_dps": selected.row.dps,
                "incoming_dps": selected.row.incoming_dps,
                "activity_age_ms": sample_ms - associations[row_event.key].origin_ms,
                "effects": [
                    {
                        "kind": kind,
                        "observations": [
                            {
                                "name": o.name,
                                "age_ms": sample_ms - associations[event.key].origin_ms,
                            }
                            for o, event in zip(observations, effects, strict=True)
                            if o.kind == kind
                        ],
                    }
                    for kind in kinds
                ],
            }
        )
    return parse_combat_put(
        {"protocol": API_VERSION, "sampled_at_ms": sample_ms, "rows": rows}
    ).rows


class TimingContext:
    """Retain across same-domain consumers; all mutation is signed-lane-owned.

    No internal lock, thread, timer or operational recovery is provided here.
    The retained bounded loss latch/generation is signalled under the worker's
    state lock. Histories/pins and loss application remain signed-lane-owned;
    a thread restart cannot turn a closed context into a new timing lifetime.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float],
        db_continuity_token: object,
        elapsed_lifetime_token: object,
    ):
        self._clock = clock
        self._db_continuity_token = db_continuity_token
        self._elapsed_lifetime_token = elapsed_lifetime_token
        self._state = _TimingState()
        self._inconsistent = False
        # Bound once by a current authenticated DeviceState/recovery, never by
        # construction or persisted expected identity. Session is NOT this scope.
        self._authenticated_scope: tuple[str, str, object, object] | None = None
        self._timing_loss: _TimingLoss | None = None
        self._timing_generation = 0
        self._loss_applied = False
        # Later workers borrow this existing scheduler, never a second read
        # bucket. All actual completions, even failed/obsolete ones, consume it.
        self._scheduler = Scheduler()
        self._publisher = _PublisherState(MappingProxyType({}))
        self._next_stage_at: Fraction | None = None
        self._publication_epoch = object()
        self._publisher_cutoff: Fraction | None = None
        self._next_get_at: Fraction | None = None
        self._snapshot_started_at: Fraction | None = None

    def _start_snapshot_get(self, *, started_at: float) -> bool:
        """Record actual before_send admission, including attempts that later fail.

        This exact GET-start floor complements, never replaces, the retained
        scheduler's completion bucket. The caller still charges every completion.
        No telemetry source ticket is involved in remote receiving.
        """
        if not isfinite(started_at):
            return False
        a = Fraction(started_at)
        if self._next_get_at is not None and a < self._next_get_at:
            return False
        self._next_get_at = a + Fraction(LIMITS["signed_interval_ms"], 1000)
        self._snapshot_started_at = a
        return True

    def _snapshot_candidate(
        self, snapshot: CombatSnapshot, *, started_at: float, received_at: float
    ) -> _TimingCandidate | None:
        """Prepare ONE already codec-validated, authenticated, bound GET return.

        All diagnostic/receiver/anchor/payload work is detached. Final outer
        authority checks and the existing pointer commit remain caller-owned.
        A recovery candidate may commit evidence without producing a payload.
        """
        if not self._finish_snapshot_get(started_at=started_at):
            return None
        return self._primitive_candidate(
            self._evaluate_snapshot(
                snapshot, started_at=started_at, received_at=received_at
            )
        )

    def _finish_snapshot_get(self, *, started_at: float) -> bool:
        """Consume only this lane attempt's marker, even for failed/obsolete HTTP."""
        if (
            not isfinite(started_at)
            or Fraction(started_at) != self._snapshot_started_at
        ):
            return False
        self._snapshot_started_at = None
        return True

    def _evaluate_snapshot(
        self, snapshot: CombatSnapshot, *, started_at: float, received_at: float
    ) -> _TimingCandidate | _ClockContradiction | None:
        """Pure evaluation AFTER the lane consumed its actual-start marker.

        No authority, history, start marker or contradiction latch is mutated.
        The runtime commits only under its final original-auth/generation fence.
        """
        diagnostic = self._evaluate_diagnostic(
            started_at=started_at,
            received_at=received_at,
            server_time_ms=snapshot.server_time_ms,
        )
        if not isinstance(diagnostic, _TimingCandidate):
            return diagnostic
        # The diagnostic's separate last-DB baseline includes every accepted
        # snapshot (and device anchor), so it also enforces R >= last receiver R.
        offset = (
            Fraction(started_at)
            - Fraction(snapshot.server_time_ms, 1000)
            - Fraction(LIMITS["clock_margin_ms"], 1000)
        )

        records = [
            record
            for record in diagnostic.base.receiver.records
            if snapshot.server_time_ms - record.server_time_ms < LIMITS["activity_ms"]
        ]
        records.append(_ReceiverRecord(snapshot.server_time_ms, offset))
        if len(records) > LIMITS["receiver_capacity"]:
            return None
        previous = diagnostic.base.receiver
        r0 = previous.recovery_r0
        if previous.recovering and r0 is None:
            r0 = snapshot.server_time_ms
        recovering = (
            previous.recovering and snapshot.server_time_ms < r0 + LIMITS["activity_ms"]
        )
        receiver = replace(
            previous,
            records=tuple(records),
            last_server_time_ms=snapshot.server_time_ms,
            payload=None,
            recovering=recovering,
            recovery_r0=r0,
        )
        if recovering:
            return replace(
                diagnostic, state=replace(diagnostic.state, receiver=receiver)
            )
        endpoints = tuple(record.server_time_ms for record in records)
        minima = [record.offset for record in records]
        for i in range(len(minima) - 2, -1, -1):
            minima[i] = min(minima[i], minima[i + 1])

        def origin(age_ms: int) -> Fraction:
            # For every currently legal x, covering intervals are exactly the
            # suffix R_i >= x, for BOTH horizons. The just-appended GET covers x.
            # O(n) preprocessing once; O(log n) per origin, never a history scan.
            x = snapshot.server_time_ms - age_ms
            return Fraction(x, 1000) + minima[bisect_left(endpoints, x)]

        lifetime = Fraction(LIMITS["activity_ms"], 1000)
        payload = TimedSnapshot(
            snapshot.server_time_ms,
            tuple(
                TimedRemoteRow(
                    row.character_id,
                    row.character_name,
                    row.outgoing_dps,
                    row.incoming_dps,
                    origin(row.age_ms),
                    origin(row.activity_age_ms) + lifetime,
                    tuple(
                        TimedEffect(
                            effect.kind,
                            tuple(
                                TimedObservation(o.name, origin(o.age_ms) + lifetime)
                                for o in effect.observations
                            ),
                        )
                        for effect in row.effects
                    ),
                )
                for row in snapshot.rows
            ),
        )
        receiver = replace(receiver, payload=payload)
        return replace(diagnostic, state=replace(diagnostic.state, receiver=receiver))

    def _receiver_lost_history(self) -> None:
        """Explicit signed-lane loss, never ordinary clear or session recovery.

        S4 must fence use/late completions and withdraw the presentation payload
        before ordering this hook. Keep diagnostic/order/cadence protection and
        any contradiction latch. No clock/DB/identity domain is reset here, and
        passing the fixed barrier cannot open the outer operational fence.
        """
        if self._state.receiver.recovering:
            return
        self._snapshot_started_at = None
        self._state = replace(
            self._state,
            anchor=None,
            receiver=replace(
                self._state.receiver,
                records=(),
                payload=None,
                recovering=True,
                recovery_r0=None,
            ),
        )

    def _stage_publication(
        self,
        source: PublicationSource,
        catalogue: FleetCatalogue,
        *,
        eligible_character_ids: frozenset[int],
    ) -> _PreparedPublication | None:
        """Prepare selected work on the signed lane, never on submit or scans.

        Nonempty prepared result or None only; empty projection is NOT an
        intentional withdrawal. Pins and original payload associations commit
        together before signing. S4 owns all authority fences and the final gate.
        """
        stamp = self._clock()
        if not isfinite(stamp):
            return None
        now = Fraction(stamp)
        if self._next_stage_at is not None and now < self._next_stage_at:
            return None
        # Admission consumes the slot even when preparation subsequently refuses.
        self._next_stage_at = now + Fraction(LIMITS["signed_interval_ms"], 1000)
        if self._inconsistent or source.is_current() is not True:
            return None
        snapshot = source.snapshot
        if snapshot.sampled_at_mono is None or not isfinite(snapshot.sampled_at_mono):
            return None
        m = Fraction(snapshot.sampled_at_mono)
        anchor = self._state.anchor
        if (
            anchor is None
            or not 0 <= 1000 * (now - m) < LIMITS["input_age_ms"]
            or not 0
            <= 1000 * (now - anchor.received_at)
            <= LIMITS["anchor_lifetime_ms"]
        ):
            return None
        selected = project_combat_snapshot(
            snapshot,
            catalogue,
            eligible_character_ids=eligible_character_ids,
            now_mono=now,
        )
        if not selected or len(selected) > LIMITS["put_rows"]:
            return None
        # A changed deadline cannot disguise an immutable conflict as expiry.
        # Projection has validated times; check original members, including those
        # genuinely pruned from this attempt, against every still-protected key.
        for character_id, row in _resolved_combat_rows(
            snapshot, catalogue, eligible_character_ids
        ):
            activity = row.combat
            if activity is None or activity.observation_id is None:
                continue
            original = [
                _event(
                    character_id,
                    "row",
                    activity.observation_id,
                    activity.expires_at_mono,
                )
            ]
            original.extend(
                _event(
                    character_id, (o.kind, o.name), o.observation_id, o.expires_at_mono
                )
                for o in activity.observations
            )
            for event in original:
                previous = self._publisher.associations.get(event.key)
                if (
                    previous is not None
                    and previous.evidence.horizon > now
                    and previous.evidence != event
                ):
                    return None
        signature = tuple(
            (r.character, r.dps, r.incoming_dps, r.combat) for r in snapshot.rows
        )
        sample = _Evidence(
            (snapshot.activation_generation, m),
            m,
            m + Fraction(LIMITS["transport_ms"], 1000),
            signature,
        )
        evidence = [sample]
        row_evidence = []
        for selected_row in selected:
            row = selected_row.row
            activity = row.combat
            row_event = _event(
                selected_row.character_id,
                "row",
                activity.observation_id,
                activity.expires_at_mono,
            )
            effects = tuple(
                _event(
                    selected_row.character_id,
                    (o.kind, o.name),
                    o.observation_id,
                    o.expires_at_mono,
                )
                for o in selected_row.observations
            )
            evidence.extend((row_event, *effects))
            row_evidence.append((selected_row, row_event, effects))
        if self._publisher_cutoff is not None and any(
            event.coordinate <= self._publisher_cutoff for event in evidence
        ):
            return None
        # All work is detached; abandonment after the single swap keeps every pin.
        associations = {
            key: pin
            for key, pin in self._publisher.associations.items()
            if pin.evidence.horizon > now
        }
        incoming_keys = {event.key for event in evidence}
        if (
            len(evidence) > LIMITS["associations_per_attempt"]
            or len(associations) + len(incoming_keys - associations.keys())
            > LIMITS["association_capacity"]
        ):
            return None
        points = {
            pin.evidence.coordinate: pin.origin_ms for pin in associations.values()
        }
        coordinates = sorted(points)
        for event in sorted(evidence, key=lambda event: event.coordinate):
            if event.key in associations:
                if associations[event.key].evidence != event:
                    return None
                continue
            x = event.coordinate
            if x not in points:
                index = bisect_left(coordinates, x)
                lower = points[coordinates[index - 1]] if index else 0
                upper = (
                    points[coordinates[index]]
                    if index < len(coordinates)
                    else JS_SAFE_MAX
                )
                delta = 1000 * (x - anchor.received_at)
                candidate = (
                    anchor.server_time_ms
                    + delta.numerator // delta.denominator
                    - LIMITS["clock_margin_ms"]
                )
                if candidate < 0 or lower > upper:
                    return None
                points[x] = min(upper, max(lower, candidate))
                coordinates.insert(index, x)
            associations[event.key] = _Pin(event, points[x])
        s = associations[sample.key].origin_ms
        try:
            rows = _combat_rows(s, row_evidence, associations)
        except ValueError:
            # A dimensional/origin failure is one refusal, never a repaired subset.
            return None
        pins = tuple(associations[e.key] for e in evidence)
        values = (source, snapshot, snapshot.sampled_at_mono, s, rows, pins, now)
        prepared = _PreparedPublication(*values, (self._publication_epoch, *values))
        self._publisher = _PublisherState(MappingProxyType(associations))
        return prepared

    def _validate_publication(self, prepared: _PreparedPublication) -> None:
        """Bounded final timing gate, safe UNDER PublicationSource's leaf lock.

        The caller owns worker/session/identity/consent checks and invokes this
        through the ORIGINAL source.admit_start. Do not read source.snapshot,
        call is_current/admit_start, sign, serialize, or acquire any lock here.
        The private seal retains exact immutable values validated at staging;
        validation performs at most one bounded association lookup per pin.
        """
        stamp = self._clock()
        values = (
            prepared.source,
            prepared.snapshot,
            prepared.sampled_at_mono,
            prepared.sampled_at_ms,
            prepared.rows,
            prepared.pins,
            prepared._staged_at,
        )
        if (
            self._inconsistent
            or not isfinite(stamp)
            or len(prepared._seal) != len(values) + 1
            or prepared._seal[0] is not self._publication_epoch
            or any(
                actual is not original
                for actual, original in zip(values, prepared._seal[1:], strict=True)
            )
        ):
            raise ValueError("Obsolete publication association.")
        now = Fraction(stamp)
        m = Fraction(prepared.sampled_at_mono)
        anchor = self._state.anchor
        if (
            now < prepared._staged_at
            or not 0 <= 1000 * (now - m) < LIMITS["input_age_ms"]
            or anchor is None
            or not 0
            <= 1000 * (now - anchor.received_at)
            <= LIMITS["anchor_lifetime_ms"]
            or any(
                pin.evidence.horizon <= now
                or self._publisher.associations.get(pin.evidence.key) is not pin
                or (
                    self._publisher_cutoff is not None
                    and pin.evidence.coordinate <= self._publisher_cutoff
                )
                for pin in prepared.pins
            )
        ):
            raise ValueError("Publication timing is no longer admissible.")

    def _publisher_lost_continuity(self, *, cutoff: float) -> None:
        """Signed-lane loss handling ONLY with trustworthy elapsed continuity.

        S4 must synchronously fence its worker before ordering this operation.
        Reset/paused/untrustworthy elapsed requires fresh model/context, not this
        cutoff. Keep pins, pacing and a latched contradiction; never auto-unlatch
        or infer permission to recover. The outer owner orders receiver history
        loss separately, only when that protection was actually lost.
        """
        if not isfinite(cutoff):
            raise ValueError("Continuity cutoff must be finite.")
        cutoff_ratio = Fraction(cutoff)
        self._publisher_cutoff = (
            cutoff_ratio
            if self._publisher_cutoff is None
            else max(self._publisher_cutoff, cutoff_ratio)
        )
        self._publication_epoch = object()
        self._state = replace(self._state, anchor=None)

    def _diagnostic_candidate(
        self, *, started_at: float, received_at: float, server_time_ms: int
    ) -> _TimingCandidate | None:
        """Prepare timing for an already validated, bound response without install.

        Start is the logical before_send stamp; receipt is after the complete
        client return. The caller validates the integer DB timestamp with the
        closed codec first. Only proven order/intersection contradictions latch;
        ineligible nonfinite/slow responses and overflow leave state untouched.
        """
        return self._primitive_candidate(
            self._evaluate_diagnostic(
                started_at=started_at,
                received_at=received_at,
                server_time_ms=server_time_ms,
            )
        )

    def _primitive_candidate(self, result):
        # Preserve S1/S3 primitive wrappers; runtime uses detached evaluation and
        # owns the final authority check before applying a contradiction.
        if isinstance(result, _ClockContradiction):
            self._inconsistent = True
            return None
        return result

    def _evaluate_diagnostic(
        self, *, started_at: float, received_at: float, server_time_ms: int
    ) -> _TimingCandidate | _ClockContradiction | None:
        if self._inconsistent or not (isfinite(started_at) and isfinite(received_at)):
            return None
        # Convert each supplied binary ratio before subtraction, without flooring.
        a = Fraction(started_at)
        r = Fraction(received_at)
        if 1000 * (r - a) > LIMITS["request_elapsed_ms"]:
            # A slow response provides no timing evidence, not a new domain or
            # an automatic contradiction. Its actual-attempt slot stays spent.
            return None
        state = self._state
        if r < a or (state.last_received_at is not None and a < state.last_received_at):
            # A regressed local clock cannot supply a comparable cutoff F.
            # Keep that evidence in the detached result until the worker's final
            # authority check; an obsolete reply must not diagnose this lifetime.
            return _ClockContradiction(state, "elapsed_reset")
        if (
            state.last_server_time_ms is not None
            and server_time_ms < state.last_server_time_ms
        ):
            return _ClockContradiction(state)
        exchange = _Exchange(a, r, server_time_ms)
        # Prune only in the detached candidate, using old request STARTS. Idle
        # records stay bounded without a timer; refusal cannot remove protection.
        exchanges = [
            e
            for e in state.exchanges
            if 1000 * (r - e.started_at) <= _DIAGNOSTIC_WINDOW_MS
        ]
        exchanges.append(exchange)
        if len(exchanges) > _DIAGNOSTIC_CAPACITY:
            return None
        lo = max(
            e.server_time_ms - 1000 * e.received_at - LIMITS["clock_error_ms"]
            for e in exchanges
        )
        hi = min(
            e.server_time_ms - 1000 * e.started_at + LIMITS["clock_error_ms"]
            for e in exchanges
        )
        if lo > hi:
            return _ClockContradiction(state)
        return _TimingCandidate(
            state,
            replace(
                state,
                exchanges=tuple(exchanges),
                lo=lo,
                hi=hi,
                last_started_at=a,
                last_received_at=r,
                last_server_time_ms=server_time_ms,
                anchor=_Anchor(server_time_ms, r),
            ),
        )

    def _commit_diagnostic(self, candidate: _TimingCandidate) -> bool:
        """Install once, only after ALL applicable response admission succeeds.

        Identity comparison rejects stale/foreign bases without equality aliases.
        The state pointer swap is the commit boundary, not a callback transaction:
        receiver admission must extend this aggregate, not commit beside it.
        This method assumes the same serialized owner as candidate construction.
        """
        if self._inconsistent or candidate.base is not self._state:
            return False
        self._state = candidate.state
        return True
