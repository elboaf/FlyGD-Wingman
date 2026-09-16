"""Fleet-sharing wire DTOs and the process-local publication consumer port.

Catalogue and legacy PublishRow dataclasses are relay values, per
docs/superpowers/specs/2026-09-04-shared-fleet-telemetry-design.md.
PublicationSource instead retains local telemetry's immutable snapshot and
admission authority; CombatProjectionRow and the Timed* receiver values are also
local-only. They are not serialized: local paths, source identities, log details
and monotonic timestamps must not leave the machine.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal, Protocol

from ..telemetry.model import EffectObservation, FleetRow, FleetSnapshot


class PublicationSource(Protocol):
    @property
    def snapshot(self) -> FleetSnapshot: ...

    def is_current(self) -> bool: ...

    def admit_start(self, validate: Callable[[], None]) -> bool: ...


@dataclass(frozen=True)
class CatalogueCharacter:
    """One character authGD's device catalogue links to the paired account.

    `character_name` is authGD's own rendering of the character, used only
    to match a locally observed title-derived name -- Wingman never
    submits a name of its own to the relay.
    """

    character_id: int
    character_name: str


@dataclass(frozen=True)
class FleetCatalogue:
    """The paired device's whole catalogue, as authGD returns it.

    `revision` changes whenever the account's linked characters change;
    a stale revision forces a refresh before Wingman resumes matching.
    """

    revision: int
    characters: tuple[CatalogueCharacter, ...] = ()


@dataclass(frozen=True)
class CombatProjectionRow:
    """Local selection, not a wire DTO: keep original measurement and evidence."""

    character_id: int
    row: FleetRow
    observations: tuple[EffectObservation, ...]


@dataclass(frozen=True)
class TimedObservation:
    name: str | None
    expires_at_mono: Fraction


@dataclass(frozen=True)
class TimedEffect:
    kind: Literal["SCRAM", "POINT", "NEUT"]
    observations: tuple[TimedObservation, ...]


@dataclass(frozen=True)
class TimedRemoteRow:
    """Local-only projection; UUIDs and receipt/paint times are not time authority."""

    character_id: int
    character_name: str
    outgoing_dps: int | None
    incoming_dps: int | None
    sampled_at_mono: Fraction
    activity_expires_at_mono: Fraction
    effects: tuple[TimedEffect, ...]


@dataclass(frozen=True)
class TimedSnapshot:
    server_time_ms: int
    rows: tuple[TimedRemoteRow, ...]


@dataclass(frozen=True)
class PublishRow:
    """One sparse row of the wire publication contract.

    Deliberately narrow: `character_id`, `dps`, and `ewar` are the only
    fields the wire schema (and authGD's `fleet_telemetry_row` CHECK
    constraint) ever accepts. There is no character name, no local path, no
    log status, no source id, and no timestamp -- see
    `wingman.fleetsharing.projection.project_snapshot`, the only place this
    type is constructed from local state.
    """

    character_id: int
    dps: int
    ewar: tuple[str, ...] = ()
