"""Frozen wire-safe data model for the fleet-sharing protocol boundary.

Every dataclass here is exactly what may cross the network to or from
authGD's relay, per
docs/superpowers/specs/2026-09-04-shared-fleet-telemetry-design.md. None of
them may ever hold a local path, a source id, a log detail, or a
timestamp: those are local telemetry's own correctness machinery
(wingman.telemetry.model) and must never leave the machine.
"""

from __future__ import annotations

from dataclasses import dataclass


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
