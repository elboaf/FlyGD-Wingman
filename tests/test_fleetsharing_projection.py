"""Pure sparse projection from a local FleetSnapshot to wire-safe rows.

Pins the design's exact publication rules
(docs/superpowers/specs/2026-09-04-shared-fleet-telemetry-design.md,
"Publication"): a row publishes only when it currently matters (positive
DPS or active SCRAM/POINT), only when its name resolves to exactly one
catalogue character, and never carries anything beyond `character_id`,
`dps`, `ewar`.
"""

import dataclasses

from wingman.fleetsharing.model import CatalogueCharacter, FleetCatalogue, PublishRow
from wingman.fleetsharing.projection import project_snapshot
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
    assert project_snapshot(snapshot, CATALOGUE) == ()


def test_zero_dps_with_active_scram_point_is_published_at_zero():
    """The design's own example: "quiet but currently tackling" publishes
    at 0 dps, never omitted."""
    snapshot = _snapshot(_row(dps=0, ewar=("SCRAM/POINT",)))
    assert project_snapshot(snapshot, CATALOGUE) == (
        PublishRow(character_id=42, dps=0, ewar=("SCRAM/POINT",)),
    )


def test_positive_dps_with_no_ewar_is_published():
    snapshot = _snapshot(_row(dps=612, ewar=()))
    assert project_snapshot(snapshot, CATALOGUE) == (
        PublishRow(character_id=42, dps=612, ewar=()),
    )


def test_dps_none_no_log_row_is_omitted_even_with_active_ewar():
    """The local NO_LOG state (dps is None) is never published, regardless
    of any EWAR value that might otherwise accompany it."""
    snapshot = _snapshot(_row(dps=None, ewar=(), log_status="NO LOG"))
    assert project_snapshot(snapshot, CATALOGUE) == ()


def test_an_unknown_ewar_tag_alone_does_not_publish_a_quiet_row():
    snapshot = _snapshot(_row(dps=0, ewar=("NEUT",)))
    assert project_snapshot(snapshot, CATALOGUE) == ()


def test_an_unknown_ewar_tag_is_dropped_but_positive_dps_still_publishes():
    snapshot = _snapshot(_row(dps=50, ewar=("NEUT",)))
    assert project_snapshot(snapshot, CATALOGUE) == (
        PublishRow(character_id=42, dps=50, ewar=()),
    )


def test_scram_point_survives_alongside_a_dropped_unknown_tag():
    snapshot = _snapshot(_row(dps=0, ewar=("NEUT", "SCRAM/POINT")))
    assert project_snapshot(snapshot, CATALOGUE) == (
        PublishRow(character_id=42, dps=0, ewar=("SCRAM/POINT",)),
    )


def test_case_insensitive_and_whitespace_tolerant_catalogue_match():
    snapshot = _snapshot(_row(character="  ALICE ", dps=10))
    assert project_snapshot(snapshot, CATALOGUE) == (
        PublishRow(character_id=42, dps=10, ewar=()),
    )


def test_unicode_casefold_match_beyond_simple_lowercasing():
    """casefold(), not lower(): the German eszett only matches under full
    Unicode case folding."""
    catalogue = FleetCatalogue(
        revision=1,
        characters=(CatalogueCharacter(character_id=99, character_name="Straße"),),
    )
    snapshot = _snapshot(_row(character="STRASSE", dps=5))
    assert project_snapshot(snapshot, catalogue) == (
        PublishRow(character_id=99, dps=5, ewar=()),
    )


def test_no_catalogue_match_is_omitted():
    snapshot = _snapshot(_row(character="Charlie", dps=10))
    assert project_snapshot(snapshot, CATALOGUE) == ()


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
        result = project_snapshot(snapshot, ambiguous)
    assert result == ()
    assert caplog.records == []


def test_output_is_sorted_by_integer_character_id():
    snapshot = _snapshot(
        _row(character="Bravo", dps=5),
        _row(character="Alice", dps=9),
    )
    assert project_snapshot(snapshot, CATALOGUE) == (
        PublishRow(character_id=7, dps=5, ewar=()),
        PublishRow(character_id=42, dps=9, ewar=()),
    )


def test_multiple_rows_mix_published_and_omitted_independently():
    snapshot = _snapshot(
        _row(character="Alice", dps=612, ewar=()),
        _row(character="Bravo", dps=0, ewar=()),
        _row(character="Charlie", dps=99, ewar=()),  # no catalogue match
    )
    assert project_snapshot(snapshot, CATALOGUE) == (
        PublishRow(character_id=42, dps=612, ewar=()),
    )


def test_publish_row_carries_only_character_id_dps_and_ewar():
    """No name, path, log detail, source id, or timestamp may ever reach a
    PublishRow -- pinned structurally, not just by this module's own
    behaviour."""
    fields = {f.name for f in dataclasses.fields(PublishRow)}
    assert fields == {"character_id", "dps", "ewar"}
