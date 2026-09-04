from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class ClientSessionId:
    hwnd: int
    pid: int
    character: str
    first_seen_generation: int


@dataclass(frozen=True)
class RosterClient:
    hwnd: int
    pid: int
    title: str
    character: str | None
    # None for a client whose title is not currently character-derived (a
    # generic character-selection title). Such clients still appear in the
    # roster -- Preview identity and reconciliation need every window -- but
    # carry no Fleet Metrics session.
    session: ClientSessionId | None


@dataclass(frozen=True)
class RosterSnapshot:
    generation: int
    clients: tuple[RosterClient, ...] = ()


@dataclass(frozen=True)
class SourceId:
    normalized_path: str
    session_start_utc: datetime.datetime


@dataclass(frozen=True)
class SourceLifecycle:
    character: str
    generation: int
    source_id: SourceId | None
    available: bool
    active: bool


@dataclass(frozen=True)
class ParsedFact:
    kind: str
    amount: int | None = None
    source: str = ""
    target: str = ""


@dataclass(frozen=True)
class ParsedLine:
    line: str
    character: str
    occurred_at: datetime.datetime | None
    facts: tuple[ParsedFact, ...] = ()
    timestamp_error: str | None = None


@dataclass(frozen=True)
class CombatFact:
    character: str
    source_generation: int
    source_id: SourceId
    occurred_at: datetime.datetime | None
    kind: str
    amount: int | None = None
    source: str = ""


@dataclass(frozen=True)
class TelemetryEnvelope(Generic[T]):
    sequence: int
    payload: T


@dataclass(frozen=True)
class StreamHealth:
    state: str
    detail: str | None = None


@dataclass(frozen=True)
class FleetRow:
    character: str
    dps: int | None
    ewar: tuple[str, ...] = ()
    log_status: str | None = None


@dataclass(frozen=True)
class FleetSnapshot:
    rows: tuple[FleetRow, ...]
    stream_health: StreamHealth
    metric_error: str | None = None
