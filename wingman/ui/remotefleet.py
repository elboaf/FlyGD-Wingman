"""Payload-only remote presentation, owned by Api's presentation lock.

TimingContext projects once on the signed lane. Clears and redraws cannot write
receiver history; the existing presentation worker remains the sole expiry owner.
"""

from dataclasses import dataclass
from fractions import Fraction
from itertools import chain
from math import inf, nextafter
from typing import Literal

from ..combatprofile import LIMITS
from ..fleetsharing.model import TimedRemoteRow, TimedSnapshot

STALE_AFTER_S = Fraction(LIMITS["stale_ms"], 1000)
EXPIRE_AFTER_S = Fraction(LIMITS["transport_ms"], 1000)


@dataclass(frozen=True)
class RemoteDisplayEffect:
    kind: Literal["SCRAM", "POINT", "NEUT"]
    observations: tuple[str | None, ...]


@dataclass(frozen=True)
class RemoteDisplayRow:
    character_id: int
    character_name: str
    outgoing_dps: int | None
    incoming_dps: int | None
    effects: tuple[RemoteDisplayEffect, ...]
    state: Literal["live", "stale"]


class RemoteFleetStore:
    def __init__(self) -> None:
        self._rows: tuple[TimedRemoteRow, ...] = ()

    def replace(self, snapshot: TimedSnapshot) -> None:
        self._rows = tuple(sorted(snapshot.rows, key=lambda row: row.character_id))

    def clear(self) -> None:
        """Withdraw payload only; there is no timing authority here to clear."""
        self._rows = ()

    def current(self, now: float | Fraction) -> tuple[RemoteDisplayRow, ...]:
        now = Fraction(now)
        return tuple(
            RemoteDisplayRow(
                row.character_id,
                row.character_name,
                row.outgoing_dps,
                row.incoming_dps,
                tuple(
                    RemoteDisplayEffect(effect.kind, observations)
                    for effect in row.effects
                    if (
                        observations := tuple(
                            o.name
                            for o in effect.observations
                            if now < o.expires_at_mono
                        )
                    )
                ),
                "stale" if now >= row.sampled_at_mono + STALE_AFTER_S else "live",
            )
            for row in self._rows
            if now
            < min(row.activity_expires_at_mono, row.sampled_at_mono + EXPIRE_AFTER_S)
        )

    def next_transition(self, now: float | Fraction) -> float | None:
        now = Fraction(now)
        deadline = min(
            (
                transition
                for row in self._rows
                if now
                < (
                    end := min(
                        row.activity_expires_at_mono,
                        row.sampled_at_mono + EXPIRE_AFTER_S,
                    )
                )
                for transition in chain(
                    (end, row.sampled_at_mono + STALE_AFTER_S),
                    (
                        o.expires_at_mono
                        for effect in row.effects
                        for o in effect.observations
                    ),
                )
                if transition > now
            ),
            default=None,
        )
        if deadline is None:
            return None
        # Event.wait's advisory wakeup is a float, not timing evidence. Round UP
        # if nearest rounded below the exact boundary; otherwise a waking owner
        # could classify too early and miss (or spin before) this transition.
        wake = float(deadline)
        return nextafter(wake, inf) if Fraction(wake) < deadline else wake
