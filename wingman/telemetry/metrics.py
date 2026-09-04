"""Thread-free Fleet Metrics: pure, clock-injected combat/EWAR state.

Consumes ``TelemetryEnvelope[RosterSnapshot | SourceLifecycle | CombatFact]``
in whatever order a coordinator's single serialized dispatcher delivers them,
and produces complete, immutable ``FleetSnapshot`` values on demand. Nothing
in this module owns a thread, a lock, a window, or a setting -- callers are
expected to serialize ``consume()``/``snapshot()`` themselves, exactly as the
brief for this module requires.

Per-character join
-------------------
State is keyed by character name and lives only for characters currently
named in the latest accepted roster snapshot. A row enters *observed* state
(a real, decaying DPS number; a live tackle tag) only once its current
client session has an ACTIVE, sequence-verified log source bound to it.
Until then the row reports ``NO LOG`` and a ``dps`` of ``None`` -- a
missing measurement, never a suppressed zero.

Three independent staleness/identity guards keep an out-of-order or
cross-session envelope from rolling this join backward:

* A ``RosterSnapshot`` envelope is rejected outright if its telemetry
  sequence is not strictly greater than the last one accepted. Roster
  processing is otherwise all-or-nothing per envelope: every named client
  present is (re)joined, and every character previously tracked but no
  longer named is dropped -- "removing a client immediately ... clears
  that session's accumulated metrics" per the design.
* A changed ``ClientSessionId`` for the same character key -- a relog, a
  HWND/PID change, a generic-title round trip -- replaces the character's
  state outright (fresh deque, fresh tackle deadline, unbound). The
  replacement's ``session_first_roster_seq`` is the sequence of the roster
  envelope that introduced it, and no ``SourceLifecycle`` at or before that
  sequence may bind: the coordinator's fresh ``request_source`` publication
  for a newly identified session is defined to land strictly after it, so
  anything at or before it is necessarily a stale echo from the OLD
  session.
* A ``SourceLifecycle`` envelope for a character with no known session is
  dropped (nothing to bind against). One whose sequence does not exceed the
  session's first-roster sequence, or does not exceed the last
  ``SourceLifecycle`` sequence already applied to that character, is
  dropped as stale. A newly active lifecycle whose generation or source
  identity differs from what is currently bound clears the damage deque and
  the tackle deadline before adopting the new source -- old combat cannot
  leak across a truncation/relog/rotation boundary. A retiring
  (``active=False``) lifecycle fully clears the row: bound source
  generation/identity, the damage deque, the tackle deadline, and the
  per-source fact-ordering floor described below. This is deliberate and
  not merely cosmetic -- without it, a later active lifecycle that happens
  to reuse the SAME retired ``SourceId``/generation (a legitimate
  ``request_source`` republish, not a bug) would see an unchanged
  ``source_generation``/``source_id`` on rebind, skip the "changed source"
  clear, and silently resurrect the old deque/deadline as if they were
  fresh. Clearing on retirement, not only on a detected change, closes that
  gap. Any fact for a retired (now-unbound) source is separately rejected
  by the bound-source check below, matching "delayed facts from retired
  sources are ignored".

A ``CombatFact`` is accepted only when the row is currently bound AND the
fact's ``(source_generation, source_id)`` equals the row's bound source AND
the fact's telemetry sequence exceeds the sequence of the lifecycle
envelope that bound it AND the fact's sequence exceeds the last fact
sequence already accepted for that same bind (``last_fact_sequence``,
reset to ``None`` on every lifecycle bind). This last guard is what a
lifecycle-sequence check alone cannot provide: two facts belonging to the
SAME still-current source can themselves arrive out of order or
duplicated, and only a per-source fact-ordering floor stops a duplicate
from double-counting damage or a stale-but-still-"newer-than-the-bind"
fact from rolling a tackle deadline backward. Only a fact that is actually
accepted under the timestamp/horizon rules below advances
``last_fact_sequence`` -- a fact rejected for being too far in the future
does NOT consume its sequence number, so a differently-timestamped
correction sharing that same sequence can still be accepted. (Real
coordinator sequences are unique and monotonic; this only matters for this
module's own defensive ordering guarantee, not for a real duplicate
sequence ever being reused in practice.)

Outgoing DPS
------------
``sum(damage with timestamp in (now - 10s, now]) / 10``, rounded half-up to
a whole number via ``Decimal`` -- never Python's banker's ``round()``. The
denominator is fixed; quiet time inside the window is not skipped. Two
independent horizon checks run at ingestion, using the injected UTC clock
sampled once per fact:

* older than ten seconds (``occurred_at <= now - 10s``) is dropped silently
  -- an ordinary, expected outcome of catching up on a batch of lines, not
  a diagnostic.
* more than two seconds in the future is dropped AND recorded as
  ``FleetSnapshot.metric_error`` -- one-second log-timestamp precision and
  polling boundaries do not explain a two-second-plus skew. Up to two
  seconds is instead clamped to ``now``. The next accepted metric fact of
  EITHER kind -- outgoing damage or incoming tackle, any character --
  clears the transient diagnostic, matching "a later accepted timestamp
  clears that transient metric diagnostic".

The deque is re-pruned to the window on every ``consume()`` damage
ingestion AND on every ``snapshot()`` call, which is what produces one-second
idle decay to zero without any new lines arriving.

Incoming tackle
---------------
``remaining = occurred_at + 8s - utc_now`` at ingestion. A non-positive
remainder is ignored outright (a genuinely stale event, not a fresh grant).
A positive remainder is capped at eight seconds -- covers a future-skewed
``occurred_at`` producing an inflated remainder -- and converted to
``monotonic_now + remaining``, so expiry is checked purely against the
injected monotonic clock at ``snapshot()`` time with no further fact
required. A later accepted tackle fact for the same bound source simply
overwrites the deadline (a refresh).

JAM is deliberately absent: it is release-gated on a verified fixture this
task does not add (see task brief; do not add dormant JAM constants,
branches, or tests here).
"""

from __future__ import annotations

import datetime
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from .model import (
    ClientSessionId,
    CombatFact,
    FleetRow,
    FleetSnapshot,
    RosterSnapshot,
    SourceId,
    SourceLifecycle,
    StreamHealth,
    TelemetryEnvelope,
)

UTC = datetime.UTC

# The DPS window's fixed denominator and inclusion bound: (now - 10s, now].
DPS_WINDOW = datetime.timedelta(seconds=10)
# Tolerates one-second log-timestamp precision and polling boundaries.
FUTURE_CLAMP = datetime.timedelta(seconds=2)
# Warp scramble/disruption's event-time lifetime.
TACKLE_LIFETIME = datetime.timedelta(seconds=8)

NO_LOG = "NO LOG"
TACKLE_TAG = "SCRAM/POINT"

_ROUND_UNIT = Decimal(1)
_DPS_DIVISOR = Decimal(10)


def _prune_damage(state: _CharacterState, now: datetime.datetime) -> None:
    """Drop damage entries that have aged out of the fixed 10-second window.

    Called on every damage ingestion (bounds the deque proactively during a
    long quiet stretch, per the brief) and again at every ``snapshot()``
    (produces the one-second idle decay to zero).
    """
    window_start = now - DPS_WINDOW
    state.damage = deque(
        (occurred_at, amount)
        for occurred_at, amount in state.damage
        if occurred_at > window_start
    )


def _round_half_up(total: int) -> int:
    """``total / 10`` rounded half-up to a whole number.

    Deliberately ``Decimal`` rather than Python's ``round()``: the latter
    is banker's rounding and would round 10.5 to 10, not the 11 the design
    requires.
    """
    return int(
        (Decimal(total) / _DPS_DIVISOR).quantize(_ROUND_UNIT, rounding=ROUND_HALF_UP)
    )


@dataclass
class _CharacterState:
    """Mutable per-character join state. Never exposed outside this module."""

    session: ClientSessionId
    session_first_roster_seq: int
    source_generation: int | None = None
    source_id: SourceId | None = None
    source_lifecycle_seq: int | None = None
    bound: bool = False
    # Per-bind fact-ordering floor: reset to None on every lifecycle bind
    # (see _consume_source) so a duplicate or out-of-order fact for the
    # SAME still-current source cannot double-count damage or roll a
    # tackle deadline backward.
    last_fact_sequence: int | None = None
    damage: deque[tuple[datetime.datetime, int]] = field(default_factory=deque)
    tackle_deadline: float | None = None


class FleetMetrics:
    """Pure, clock-injected fleet combat/EWAR state.

    Public interface:
        consume(envelope) -> None
        snapshot(sequence, health) -> FleetSnapshot

    Inject ``_clock`` (monotonic) and ``_utc_now`` (aware UTC) for
    deterministic tests. No thread, lock, or window belongs here; a
    coordinator is expected to call both methods from one serialized
    context.
    """

    def __init__(
        self,
        *,
        _clock: Callable[[], float] = time.monotonic,
        _utc_now: Callable[[], datetime.datetime] | None = None,
    ) -> None:
        self._clock = _clock
        self._utc_now = _utc_now or (lambda: datetime.datetime.now(tz=UTC))
        self._states: dict[str, _CharacterState] = {}
        self._last_roster_sequence: int | None = None
        self._metric_error: str | None = None

    def reset(self) -> None:
        """Forget every client/source metric and transient diagnostic.

        Called only by the coordinator's serialized dispatcher when Fleet
        turns off or starts a fresh enabled generation. Keeping this here,
        rather than replacing the metrics object, preserves injected clocks
        while preventing disabled-time facts from appearing on re-enable.
        """
        self._states.clear()
        self._last_roster_sequence = None
        self._metric_error = None

    # ------------------------------------------------------------------
    # Consumption
    # ------------------------------------------------------------------

    def consume(self, envelope: TelemetryEnvelope) -> None:
        payload = envelope.payload
        if isinstance(payload, RosterSnapshot):
            self._consume_roster(envelope.sequence, payload)
        elif isinstance(payload, SourceLifecycle):
            self._consume_source(envelope.sequence, payload)
        elif isinstance(payload, CombatFact):
            self._consume_fact(envelope.sequence, payload)

    def _consume_roster(self, sequence: int, snapshot: RosterSnapshot) -> None:
        if (
            self._last_roster_sequence is not None
            and sequence <= self._last_roster_sequence
        ):
            return  # stale: a newer roster envelope already applied.
        self._last_roster_sequence = sequence

        named = {c.character: c for c in snapshot.clients if c.character is not None}

        for character, client in named.items():
            existing = self._states.get(character)
            if existing is None or existing.session != client.session:
                # New or changed session (relog, HWND/PID change, a generic
                # title round trip): start clean and record this envelope
                # as the session's first roster sequence -- the horizon a
                # bound source lifecycle must land after.
                self._states[character] = _CharacterState(
                    session=client.session, session_first_roster_seq=sequence
                )

        for character in list(self._states):
            if character not in named:
                # Removed from the roster: drop its row and every
                # accumulated metric immediately.
                del self._states[character]

    def _consume_source(self, sequence: int, lifecycle: SourceLifecycle) -> None:
        state = self._states.get(lifecycle.character)
        if state is None:
            return  # No known roster session to bind against.
        if sequence <= state.session_first_roster_seq:
            return  # Must strictly follow the session's first roster envelope.
        if (
            state.source_lifecycle_seq is not None
            and sequence <= state.source_lifecycle_seq
        ):
            return  # Stale relative to a lifecycle envelope already applied.

        state.source_lifecycle_seq = sequence
        if not lifecycle.active:
            # Full clear, not just an unbind: a later active lifecycle that
            # reuses the SAME retired generation/SourceId (a legitimate
            # request_source republish) must not see an unchanged
            # source_generation/source_id and skip the "changed source"
            # clear below -- that would resurrect this retired source's old
            # damage/tackle as if they belonged to the fresh bind.
            state.bound = False
            state.source_generation = None
            state.source_id = None
            state.last_fact_sequence = None
            state.damage.clear()
            state.tackle_deadline = None
            return

        changed = (
            state.source_generation != lifecycle.generation
            or state.source_id != lifecycle.source_id
        )
        if changed:
            state.damage.clear()
            state.tackle_deadline = None
        state.source_generation = lifecycle.generation
        state.source_id = lifecycle.source_id
        state.bound = True
        # Every accepted active lifecycle is a fresh bind event, whether or
        # not the source identity itself changed: the fact-ordering floor
        # starts over so a fact legitimately delivered before this bind
        # cannot be confused with one delivered after it.
        state.last_fact_sequence = None

    def _consume_fact(self, sequence: int, fact: CombatFact) -> None:
        state = self._states.get(fact.character)
        if state is None or not state.bound:
            return
        if (
            fact.source_generation != state.source_generation
            or fact.source_id != state.source_id
        ):
            return  # Delayed fact from a superseded or retired source.
        if (
            state.source_lifecycle_seq is not None
            and sequence <= state.source_lifecycle_seq
        ):
            return  # Stale relative to the binding lifecycle envelope.
        if (
            state.last_fact_sequence is not None
            and sequence <= state.last_fact_sequence
        ):
            return  # Stale or duplicate relative to a fact already accepted.

        accepted = False
        if fact.kind == "outgoing_damage":
            accepted = self._ingest_damage(state, fact)
        elif fact.kind == "incoming_tackle":
            accepted = self._ingest_tackle(state, fact)

        if accepted:
            # Only an actually-accepted fact advances the floor: a fact
            # rejected for being too far in the future must not consume its
            # sequence number, so a differently-timestamped correction
            # sharing that same sequence can still be accepted afterward.
            state.last_fact_sequence = sequence

    def _ingest_damage(self, state: _CharacterState, fact: CombatFact) -> bool:
        if fact.amount is None or fact.occurred_at is None:
            return False  # A malformed/missing timestamp suppresses only this fact.

        now = self._utc_now()
        _prune_damage(state, now)
        if fact.occurred_at <= now - DPS_WINDOW:
            return False  # Ordinary catch-up on old lines: not a diagnostic.

        occurred_at = fact.occurred_at
        if occurred_at > now:
            skew = occurred_at - now
            if skew > FUTURE_CLAMP:
                self._metric_error = (
                    f"future outgoing damage timestamp for {fact.character}"
                )
                return False
            occurred_at = now  # Tolerate log/poll precision.

        state.damage.append((occurred_at, fact.amount))
        self._metric_error = None  # A later accepted timestamp clears it.
        return True

    def _ingest_tackle(self, state: _CharacterState, fact: CombatFact) -> bool:
        if fact.occurred_at is None:
            return False
        remaining = fact.occurred_at + TACKLE_LIFETIME - self._utc_now()
        if remaining <= datetime.timedelta(0):
            return False  # A genuinely stale event grants no fresh lifetime.
        remaining = min(remaining, TACKLE_LIFETIME)
        state.tackle_deadline = self._clock() + remaining.total_seconds()
        self._metric_error = None  # A later accepted metric fact clears it too.
        return True

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self, sequence: int, health: StreamHealth) -> FleetSnapshot:
        """The complete current fleet snapshot.

        ``sequence`` is the telemetry sequence the coordinator has assigned
        to this snapshot publication; it plays no role in this module's own
        state (``FleetSnapshot`` carries no sequence field), but is part of
        the required interface so a coordinator's uniform envelope-stamping
        need not special-case snapshot calls.
        """
        del sequence  # Not part of FleetSnapshot; see docstring above.
        now = self._utc_now()
        mono = self._clock()

        rows = []
        for character, state in self._states.items():
            if not state.bound:
                rows.append(
                    FleetRow(character=character, dps=None, ewar=(), log_status=NO_LOG)
                )
                continue

            _prune_damage(state, now)
            total = sum(amount for _, amount in state.damage)
            dps = _round_half_up(total)

            ewar: tuple[str, ...] = ()
            if state.tackle_deadline is not None and mono < state.tackle_deadline:
                ewar = (TACKLE_TAG,)

            rows.append(
                FleetRow(character=character, dps=dps, ewar=ewar, log_status=None)
            )

        rows.sort(key=lambda row: row.character.casefold())
        return FleetSnapshot(
            rows=tuple(rows), stream_health=health, metric_error=self._metric_error
        )
