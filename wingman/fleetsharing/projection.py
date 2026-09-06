"""Pure sparse projection from a local FleetSnapshot to wire-safe rows.

Ports the design's "Publication" rules
(docs/superpowers/specs/2026-09-04-shared-fleet-telemetry-design.md) into
one small, fully pure function: no I/O, no logging, no network. It takes
today's completed local `FleetSnapshot` -- the same value the local Fleet
Bar already renders -- and an authenticated `FleetCatalogue`, and returns
only the rows that are both currently interesting and unambiguously
resolvable to a catalogue character id.

Nothing here is a Fleet Bar or coordinator concern: this module never
touches `wingman.telemetry.coordinator`, never subscribes to anything, and
never performs network I/O. A later task hands it a snapshot and a
catalogue and does something with the result; this module only computes
that result.
"""

from __future__ import annotations

from ..telemetry.model import FleetSnapshot
from .model import FleetCatalogue, PublishRow

# The only EWAR value the wire schema (and authGD's `fleet_telemetry_row`
# CHECK constraint, Task 3) ever accepts. Anything else observed locally is
# silently dropped here rather than rejected outright -- ECM/JAM stays
# unshipped in local telemetry today (wingman/telemetry/metrics.py), so this
# is defence in depth against a future local tag this module was not
# updated for, not a case that can currently occur.
_ALLOWED_EWAR = frozenset({"SCRAM/POINT"})

# authGD's own wire limits on a published batch (Task 3's
# `fleet_telemetry_row` CHECK constraint and Task 6's route-level bounds):
# at most 32 rows per publish, `0 <= dps <= 10_000_000`, and `ewar` exactly
# `()` or `("SCRAM/POINT",)` -- never a longer tuple, even one made only of
# repeated "SCRAM/POINT" entries. `validate_publish_batch` below is the
# client-side belt-and-suspenders check against these limits before a
# batch ever reaches the network.
MAX_PUBLISH_ROWS = 32
MAX_PUBLISH_DPS = 10_000_000
_VALID_PUBLISH_EWAR_SHAPES = frozenset({(), ("SCRAM/POINT",)})


def _normalize(name: str) -> str:
    """The one Unicode-safe normalization this whole module uses.

    strip().casefold(), nothing else -- both the local FleetRow character
    name and every catalogue character name go through exactly this and
    nothing more specific, so "Alice", " alice ", and "ALICE" all resolve
    to the same catalogue entry, and a German "Straße" matches "STRASSE"
    the way casefold() (not .lower()) is designed to.
    """
    return name.strip().casefold()


def project_snapshot(
    snapshot: FleetSnapshot, catalogue: FleetCatalogue
) -> tuple[PublishRow, ...]:
    """The sparse rows *snapshot* would publish against *catalogue*.

    Row inclusion:
      - A row whose local log is unavailable (`FleetRow.dps is None`, the
        local `NO LOG` state) is never published -- there is nothing
        current to say about it.
      - Otherwise a row publishes only when its damage is positive or its
        (filtered) EWAR is non-empty. A quiet, un-tackled character is
        omitted entirely, matching the wire contract's own sparse
        semantics -- silence, not an explicit `0 dps` row, is how "nothing
        to report" is spelled on the wire.
      - A `0 dps` character IS published, but only when EWAR is
        non-empty: "quiet but currently tackling" is exactly the case the
        design calls out by name.

    EWAR filtering: only "SCRAM/POINT" ever survives into a published row;
    any other tag is dropped from the row's own `ewar` tuple before the
    inclusion test above runs, so a row whose only EWAR was an unknown tag
    is treated as EWAR-empty, not published-with-something-unexpected.

    Character resolution: every local row's `character` and every
    catalogue entry's `character_name` are matched through `_normalize`
    only. A name that resolves to zero or to more than one catalogue
    character is omitted outright -- never published under a guessed id,
    and never logged, since an ambiguous or unmatched name is exactly as
    ordinary as any other ineligible row.

    Output is sorted by integer `character_id` ascending, which is also
    what makes ambiguous catalogue names ("two characters share one
    normalized name") a stable, order-independent property to test.
    """
    catalogue_ids_by_name: dict[str, list[int]] = {}
    for character in catalogue.characters:
        key = _normalize(character.character_name)
        catalogue_ids_by_name.setdefault(key, []).append(character.character_id)

    rows: list[PublishRow] = []
    for row in snapshot.rows:
        if row.dps is None:
            # Local log unavailable (NO LOG): nothing current to publish.
            continue
        ewar = tuple(tag for tag in row.ewar if tag in _ALLOWED_EWAR)
        if row.dps <= 0 and not ewar:
            continue
        matches = catalogue_ids_by_name.get(_normalize(row.character))
        if matches is None or len(matches) != 1:
            # No catalogue match, or an ambiguous one: never guess, never log.
            continue
        rows.append(PublishRow(character_id=matches[0], dps=row.dps, ewar=ewar))

    return tuple(sorted(rows, key=lambda published: published.character_id))


def validate_publish_batch(rows: tuple[PublishRow, ...]) -> tuple[PublishRow, ...]:
    """Refuse a batch that cannot possibly satisfy authGD's own wire
    limits before a caller (`wingman.fleetsharing.client.FleetRelayClient.
    publish_snapshot`) ever sends it.

    `project_snapshot` already produces rows shaped this way for any
    single valid input, so this is defence in depth against a corrupted
    or hand-constructed batch -- e.g. a snapshot whose two local rows
    both normalize to the same catalogue character name by construction
    error elsewhere, or a row whose `ewar` accumulated a duplicate
    "SCRAM/POINT" tag -- reaching the network at all. Matches this
    module's own "never guess, never silently coerce" posture: a caller
    gets an immediate `ValueError` naming the row at fault, not a request
    authGD's schema would reject anyway.

    Returns *rows* unchanged when the whole batch is valid, so a caller
    can use this as a pass-through validation step.
    """
    if len(rows) > MAX_PUBLISH_ROWS:
        raise ValueError(
            f"Fleet sharing batch has {len(rows)} rows, more than the "
            f"{MAX_PUBLISH_ROWS}-row limit."
        )
    seen_ids: set[int] = set()
    for row in rows:
        if row.character_id in seen_ids:
            raise ValueError(
                f"Fleet sharing batch has duplicate character_id {row.character_id}."
            )
        seen_ids.add(row.character_id)
        if not (0 <= row.dps <= MAX_PUBLISH_DPS):
            raise ValueError(
                f"Fleet sharing batch row for character_id {row.character_id} "
                f"has dps {row.dps}, outside 0..{MAX_PUBLISH_DPS}."
            )
        if row.ewar not in _VALID_PUBLISH_EWAR_SHAPES:
            raise ValueError(
                f"Fleet sharing batch row for character_id {row.character_id} "
                f"has an invalid ewar shape {row.ewar!r}."
            )
    return rows
