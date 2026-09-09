"""Pure sparse projection from a local FleetSnapshot to wire-safe rows.

Pins the design's exact publication rules
(docs/superpowers/specs/2026-09-04-shared-fleet-telemetry-design.md,
"Publication"): a row publishes only when it currently matters (positive
DPS or active SCRAM/POINT), only when its name resolves to exactly one
catalogue character, and never carries anything beyond `character_id`,
`dps`, `ewar`.
"""

import dataclasses
from itertools import combinations

import pytest

from wingman.fleetsharing.model import CatalogueCharacter, FleetCatalogue, PublishRow
from wingman.fleetsharing.projection import (
    MAX_PUBLISH_DPS,
    MAX_PUBLISH_ROWS,
    project_snapshot,
    validate_publish_batch,
)
from wingman.telemetry.model import FleetRow, FleetSnapshot, StreamHealth

HEALTH = StreamHealth(state="active")

CATALOGUE = FleetCatalogue(
    revision=1,
    characters=(
        CatalogueCharacter(character_id=42, character_name="Alice"),
        CatalogueCharacter(character_id=7, character_name="Bravo"),
    ),
)


def _snapshot(*rows: FleetRow) -> FleetSnapshot:
    return FleetSnapshot(rows=rows, stream_health=HEALTH)


def _row(character="Alice", dps=0, ewar=(), log_status=None) -> FleetRow:
    return FleetRow(character=character, dps=dps, ewar=ewar, log_status=log_status)


def test_a_quiet_row_with_no_ewar_is_omitted():
    snapshot = _snapshot(_row(dps=0, ewar=()))
    assert (
        project_snapshot(snapshot, CATALOGUE, eligible_character_ids=frozenset({7, 42}))
        == ()
    )


@pytest.mark.parametrize("outgoing,ewar", [(0, ()), (0, ("SCRAM",)), (12, ())])
def test_incoming_damage_never_expands_wire_metrics_or_sparse_publication(
    outgoing, ewar
):
    snapshot = _snapshot(FleetRow("Alice", outgoing, ewar, incoming_dps=900))
    expected = ()
    if outgoing or ewar:
        expected = (PublishRow(42, outgoing, ("SCRAM/POINT",) if ewar else ()),)
    result = project_snapshot(
        snapshot, CATALOGUE, eligible_character_ids=frozenset({42})
    )
    assert result == expected
    assert all(
        set(dataclasses.asdict(row)) == {"character_id", "dps", "ewar"}
        for row in result
    )


def test_zero_dps_with_active_scram_point_is_published_at_zero():
    """The design's own example: "quiet but currently tackling" publishes
    at 0 dps, never omitted."""
    snapshot = _snapshot(_row(dps=0, ewar=("SCRAM/POINT",)))
    assert project_snapshot(
        snapshot, CATALOGUE, eligible_character_ids=frozenset({7, 42})
    ) == (PublishRow(character_id=42, dps=0, ewar=("SCRAM/POINT",)),)


def test_positive_dps_with_no_ewar_is_published():
    snapshot = _snapshot(_row(dps=612, ewar=()))
    assert project_snapshot(
        snapshot, CATALOGUE, eligible_character_ids=frozenset({7, 42})
    ) == (PublishRow(character_id=42, dps=612, ewar=()),)


def test_dps_none_no_log_row_is_omitted_even_with_active_ewar():
    """The local NO_LOG state (dps is None) is never published, regardless
    of any EWAR value that might otherwise accompany it."""
    snapshot = _snapshot(_row(dps=None, ewar=(), log_status="NO LOG"))
    assert (
        project_snapshot(snapshot, CATALOGUE, eligible_character_ids=frozenset({7, 42}))
        == ()
    )


def test_an_unknown_ewar_tag_alone_does_not_publish_a_quiet_row():
    snapshot = _snapshot(_row(dps=0, ewar=("NEUT",)))
    assert (
        project_snapshot(snapshot, CATALOGUE, eligible_character_ids=frozenset({7, 42}))
        == ()
    )


def test_an_unknown_ewar_tag_is_dropped_but_positive_dps_still_publishes():
    snapshot = _snapshot(_row(dps=50, ewar=("NEUT",)))
    assert project_snapshot(
        snapshot, CATALOGUE, eligible_character_ids=frozenset({7, 42})
    ) == (PublishRow(character_id=42, dps=50, ewar=()),)


def test_scram_point_survives_alongside_a_dropped_unknown_tag():
    snapshot = _snapshot(_row(dps=0, ewar=("NEUT", "SCRAM/POINT")))
    assert project_snapshot(
        snapshot, CATALOGUE, eligible_character_ids=frozenset({7, 42})
    ) == (PublishRow(character_id=42, dps=0, ewar=("SCRAM/POINT",)),)


def test_case_insensitive_and_whitespace_tolerant_catalogue_match():
    snapshot = _snapshot(_row(character="  ALICE ", dps=10))
    assert project_snapshot(
        snapshot, CATALOGUE, eligible_character_ids=frozenset({7, 42})
    ) == (PublishRow(character_id=42, dps=10, ewar=()),)


def test_unicode_casefold_match_beyond_simple_lowercasing():
    """casefold(), not lower(): the German eszett only matches under full
    Unicode case folding."""
    catalogue = FleetCatalogue(
        revision=1,
        characters=(CatalogueCharacter(character_id=99, character_name="Straße"),),
    )
    snapshot = _snapshot(_row(character="STRASSE", dps=5))
    assert project_snapshot(
        snapshot, catalogue, eligible_character_ids=frozenset({99})
    ) == (PublishRow(character_id=99, dps=5, ewar=()),)


def test_no_catalogue_match_is_omitted():
    snapshot = _snapshot(_row(character="Charlie", dps=10))
    assert (
        project_snapshot(snapshot, CATALOGUE, eligible_character_ids=frozenset({7, 42}))
        == ()
    )


def test_ambiguous_normalized_catalogue_names_are_omitted_and_never_logged(caplog):
    ambiguous = FleetCatalogue(
        revision=1,
        characters=(
            CatalogueCharacter(character_id=42, character_name="Alice"),
            CatalogueCharacter(character_id=43, character_name="alice"),
        ),
    )
    snapshot = _snapshot(_row(character="Alice", dps=10))
    with caplog.at_level("DEBUG"):
        result = project_snapshot(
            snapshot, ambiguous, eligible_character_ids=frozenset({42})
        )
    assert result == ()
    assert caplog.records == []


def test_output_is_sorted_by_integer_character_id():
    snapshot = _snapshot(
        _row(character="Bravo", dps=5),
        _row(character="Alice", dps=9),
    )
    assert project_snapshot(
        snapshot, CATALOGUE, eligible_character_ids=frozenset({7, 42})
    ) == (
        PublishRow(character_id=7, dps=5, ewar=()),
        PublishRow(character_id=42, dps=9, ewar=()),
    )


def test_multiple_rows_mix_published_and_omitted_independently():
    snapshot = _snapshot(
        _row(character="Alice", dps=612, ewar=()),
        _row(character="Bravo", dps=0, ewar=()),
        _row(character="Charlie", dps=99, ewar=()),  # no catalogue match
    )
    assert project_snapshot(
        snapshot, CATALOGUE, eligible_character_ids=frozenset({7, 42})
    ) == (PublishRow(character_id=42, dps=612, ewar=()),)


def test_publish_row_carries_only_character_id_dps_and_ewar():
    """No name, path, log detail, source id, or timestamp may ever reach a
    PublishRow -- pinned structurally, not just by this module's own
    behaviour."""
    fields = {f.name for f in dataclasses.fields(PublishRow)}
    assert fields == {"character_id", "dps", "ewar"}


@pytest.mark.parametrize(
    "tags",
    [
        combo
        for count in range(5)
        for combo in combinations(("SCRAM", "POINT", "SCRAM/POINT", "NEUT"), count)
    ],
)
@pytest.mark.parametrize("dps", [None, 0, 1000])
@pytest.mark.parametrize("eligible", [False, True])
def test_all_local_tackle_combinations_are_sparse_and_permission_scoped(
    tags, dps, eligible
):
    expected = ()
    tackle = any(tag in ("SCRAM", "POINT", "SCRAM/POINT") for tag in tags)
    if eligible and dps is not None and (dps > 0 or tackle):
        expected = (PublishRow(42, dps, ("SCRAM/POINT",) if tackle else ()),)
    assert (
        project_snapshot(
            _snapshot(_row(dps=dps, ewar=tags)),
            CATALOGUE,
            eligible_character_ids=frozenset({42}) if eligible else frozenset(),
        )
        == expected
    )


@pytest.mark.parametrize("count", [32, 33])
def test_full_eligible_projection_is_never_truncated_to_wire_limit(count):
    catalogue = FleetCatalogue(
        1, tuple(CatalogueCharacter(i, str(i)) for i in range(1, count + 1))
    )
    rows = project_snapshot(
        _snapshot(*(_row(character=str(i), dps=1) for i in range(1, count + 1))),
        catalogue,
        eligible_character_ids=frozenset(range(1, count + 1)),
    )
    assert len(rows) == count
    if count == 33:
        with pytest.raises(ValueError, match="33 rows"):
            validate_publish_batch(rows)
    else:
        assert len(validate_publish_batch(rows)) == 32


class TestValidatePublishBatch:
    """authGD's own wire limits on a batch about to be published
    (Task 3's `fleet_telemetry_row` CHECK constraint and Task 6's
    route-level bounds): at most 32 rows, unique `character_id`s,
    `0 <= dps <= 10_000_000`, and `ewar` exactly `()` or
    `("SCRAM/POINT",)`.
    """

    def test_accepts_a_batch_within_every_limit(self):
        rows = (
            PublishRow(character_id=1, dps=0, ewar=()),
            PublishRow(character_id=2, dps=MAX_PUBLISH_DPS, ewar=("SCRAM/POINT",)),
        )
        assert validate_publish_batch(rows) == rows

    def test_accepts_exactly_the_row_limit(self):
        rows = tuple(
            PublishRow(character_id=i, dps=1, ewar=()) for i in range(MAX_PUBLISH_ROWS)
        )
        assert validate_publish_batch(rows) == rows

    def test_rejects_more_rows_than_the_limit(self):
        rows = tuple(
            PublishRow(character_id=i, dps=1, ewar=())
            for i in range(MAX_PUBLISH_ROWS + 1)
        )
        with pytest.raises(ValueError, match="33 rows"):
            validate_publish_batch(rows)

    def test_rejects_dps_above_the_max(self):
        rows = (PublishRow(character_id=1, dps=MAX_PUBLISH_DPS + 1, ewar=()),)
        with pytest.raises(ValueError, match="dps"):
            validate_publish_batch(rows)

    def test_rejects_a_negative_dps(self):
        rows = (PublishRow(character_id=1, dps=-1, ewar=()),)
        with pytest.raises(ValueError, match="dps"):
            validate_publish_batch(rows)

    def test_rejects_a_duplicate_character_id(self):
        rows = (
            PublishRow(character_id=1, dps=10, ewar=()),
            PublishRow(character_id=1, dps=20, ewar=()),
        )
        with pytest.raises(ValueError, match="duplicate character_id 1"):
            validate_publish_batch(rows)

    def test_rejects_an_ewar_tuple_with_a_repeated_scram_point_entry(self):
        """Defence in depth for hand-constructed rows: the projection collapses
        local tackle, but the transport still refuses a duplicate wire tag."""
        rows = (PublishRow(character_id=1, dps=0, ewar=("SCRAM/POINT", "SCRAM/POINT")),)
        with pytest.raises(ValueError, match="ewar shape"):
            validate_publish_batch(rows)

    def test_rejects_an_ewar_tuple_carrying_an_unrecognised_tag(self):
        rows = (PublishRow(character_id=1, dps=0, ewar=("NEUT",)),)
        with pytest.raises(ValueError, match="ewar shape"):
            validate_publish_batch(rows)

    def test_returns_the_same_rows_unchanged_on_success(self):
        rows = (PublishRow(character_id=1, dps=5, ewar=()),)
        assert validate_publish_batch(rows) is rows
