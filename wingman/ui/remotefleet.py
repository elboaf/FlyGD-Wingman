"""Bounded, process-local remote presentation. Api's presentation lock owns this.

Only the current response carries payloads. Timing survives clears until the
honest relay's retention horizon: display expiry can be earlier after a long
request and is NOT permission to forget a conservative age estimate.
"""

from dataclasses import dataclass
from math import ceil
from typing import Literal

from ..fleetsharing.protocol import MAX_REMOTE_ROWS, ObservedRemoteRow
from ..fleetsharing.scheduling import SIGNED_INTERVAL_S

STALE_AFTER_S = 3.0
EXPIRE_AFTER_S = 10.0
MAX_TIMING_ENTRIES = (ceil(EXPIRE_AFTER_S / SIGNED_INTERVAL_S) + 1) * MAX_REMOTE_ROWS


@dataclass(frozen=True)
class _Timing:
    origin: float
    first_receipt: float


@dataclass(frozen=True)
class RemoteDisplayRow:
    character_id: int
    character_name: str
    dps: int
    ewar: tuple[str, ...]
    state: Literal["live", "stale"]


class RemoteFleetStore:
    def __init__(self) -> None:
        self._timing: dict[str, _Timing] = {}
        self._rows: tuple[ObservedRemoteRow, ...] = ()

    def _prune(self, now: float) -> None:
        self._timing = {
            key: timing
            for key, timing in self._timing.items()
            if now < timing.first_receipt + EXPIRE_AFTER_S
        }
        self._rows = tuple(
            row
            for row in self._rows
            if row.publication_id in self._timing
            and now - self._timing[row.publication_id].origin < EXPIRE_AFTER_S
        )

    def replace(
        self, rows: tuple[ObservedRemoteRow, ...], receipt: float, elapsed: float
    ) -> bool:
        self._prune(receipt)
        new_ids = {row.publication_id for row in rows} - self._timing.keys()
        if len(self._timing) + len(new_ids) > MAX_TIMING_ENTRIES:
            # A broken internal cadence/cap invariant cannot evict protected IDs
            # or authorize a partly accepted response. Leave the old set intact.
            return False
        for row in rows:
            candidate = receipt - (row.age_ms / 1000 + elapsed)
            previous = self._timing.get(row.publication_id)
            self._timing[row.publication_id] = _Timing(
                min(previous.origin, candidate) if previous else candidate,
                previous.first_receipt if previous else receipt,
            )
        self._rows = rows
        self._prune(receipt)
        return True

    def clear(self) -> None:
        """Withdraw visible payloads, never their freshness protection."""
        self._rows = ()

    def current(self, now: float) -> tuple[RemoteDisplayRow, ...]:
        self._prune(now)
        return tuple(
            RemoteDisplayRow(
                row.character_id,
                row.character_name,
                row.dps,
                row.ewar,
                "stale"
                if now - self._timing[row.publication_id].origin >= STALE_AFTER_S
                else "live",
            )
            for row in sorted(self._rows, key=lambda row: row.character_id)
        )

    def next_transition(self, now: float) -> float | None:
        self._prune(now)
        return min(
            (
                timing.origin
                + (
                    STALE_AFTER_S
                    if now - timing.origin < STALE_AFTER_S
                    else EXPIRE_AFTER_S
                )
                for row in self._rows
                for timing in (self._timing[row.publication_id],)
            ),
            default=None,
        )
