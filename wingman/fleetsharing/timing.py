"""Retained process-local timing, owned by the existing serialized signed lane.

Construction establishes no authenticated identity. Only wholly validated,
authenticated, request-bound responses may reach diagnostic candidacy. A feasible
rolling intersection is necessary, not proof against hidden clock faults.
"""

from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from math import isfinite

from ..combatprofile import LIMITS
from .scheduling import Scheduler

_DIAGNOSTIC_WINDOW_MS = (
    LIMITS["anchor_lifetime_ms"] + LIMITS["activity_ms"] + LIMITS["request_elapsed_ms"]
)
_DIAGNOSTIC_CAPACITY = _DIAGNOSTIC_WINDOW_MS // LIMITS["signed_interval_ms"] + 1


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
class _TimingState:
    """One immutable accepted aggregate; baselines survive diagnostic pruning."""

    exchanges: tuple[_Exchange, ...] = ()
    lo: Fraction | None = None
    hi: Fraction | None = None
    last_started_at: Fraction | None = None
    last_received_at: Fraction | None = None
    last_server_time_ms: int | None = None
    anchor: _Anchor | None = None


@dataclass(frozen=True)
class _TimingCandidate:
    base: _TimingState
    state: _TimingState


class TimingContext:
    """Retain across same-domain consumers; all mutation is signed-lane-owned.

    No internal lock, thread, timer, authentication or continuity recovery is
    provided here. The owner fences identity/generations before calling these
    private methods and must serialize candidate/commit with those checks.
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
        # Later workers borrow this existing scheduler, never a second read
        # bucket. All actual completions, even failed/obsolete ones, consume it.
        self._scheduler = Scheduler()

    def _diagnostic_candidate(
        self, *, started_at: float, received_at: float, server_time_ms: int
    ) -> _TimingCandidate | None:
        """Prepare timing for an already validated, bound response without install.

        Start is the logical before_send stamp; receipt is after the complete
        client return. The caller validates the integer DB timestamp with the
        closed codec first. Only proven order/intersection contradictions latch;
        ineligible nonfinite/slow responses and overflow leave state untouched.
        """
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
        if (
            r < a
            or (state.last_received_at is not None and a < state.last_received_at)
            or (
                state.last_server_time_ms is not None
                and server_time_ms < state.last_server_time_ms
            )
        ):
            self._inconsistent = True
            return None
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
            self._inconsistent = True
            return None
        return _TimingCandidate(
            state,
            _TimingState(
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
