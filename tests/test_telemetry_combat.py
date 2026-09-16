"""Immutable local combat evidence and caller-clock readers."""

import datetime
from dataclasses import FrozenInstanceError
from uuid import UUID

import pytest

from wingman.telemetry import combat, model

TOKEN = UUID("00000000-0000-0000-0000-000000000001")


def test_parsed_fact_appends_observed_name_after_legacy_positional_prefix():
    fact = model.ParsedFact("incoming_scram", 7, "Source [CORP] Hull", "Victim")
    assert (fact.kind, fact.amount, fact.source, fact.target) == (
        "incoming_scram",
        7,
        "Source [CORP] Hull",
        "Victim",
    )
    assert fact.observed_name is None
    assert model.ParsedFact("incoming_scram") == model.ParsedFact(
        "incoming_scram", None, "", "", None
    )
    named = model.ParsedFact("incoming_scram", 7, fact.source, fact.target, "Source")
    assert named.observed_name == "Source"
    assert (named.kind, named.amount, named.source, named.target) == (
        fact.kind,
        fact.amount,
        fact.source,
        fact.target,
    )
    with pytest.raises(FrozenInstanceError):
        named.observed_name = "Other"


def test_combat_fact_appends_observed_name_after_legacy_positional_prefix():
    occurred_at = datetime.datetime(2025, 11, 14, tzinfo=datetime.UTC)
    source_id = model.SourceId("gamelog.txt", occurred_at)
    prefix = ("Victim", 3, source_id, occurred_at, "incoming_scram")
    fact = model.CombatFact(*prefix, 7, "Source [CORP] Hull")
    assert (
        fact.character,
        fact.source_generation,
        fact.source_id,
        fact.occurred_at,
        fact.kind,
        fact.amount,
        fact.source,
    ) == (*prefix, 7, "Source [CORP] Hull")
    assert fact.observed_name is None
    assert model.CombatFact(*prefix) == model.CombatFact(*prefix, None, "", None)
    named = model.CombatFact(*prefix, 7, fact.source, "Source")
    assert named.observed_name == "Source"
    assert named.source == fact.source
    assert named.source_id is source_id
    assert named.occurred_at is occurred_at
    with pytest.raises(FrozenInstanceError):
        named.observed_name = "Other"


def test_legacy_row_positional_prefix_and_defaults_remain_compatible():
    row = model.FleetRow("Alice", 10, ("POINT",), "bound", 20)
    assert (row.character, row.dps, row.ewar, row.log_status, row.incoming_dps) == (
        "Alice",
        10,
        ("POINT",),
        "bound",
        20,
    )
    assert row.combat is None
    assert model.FleetRow("Alice", None) == model.FleetRow(
        "Alice", None, (), None, None, None
    )


def test_legacy_snapshot_positional_prefix_and_defaults_remain_compatible():
    rows = (model.FleetRow("Alice", 10),)
    health = model.StreamHealth("active")
    snapshot = model.FleetSnapshot(rows, health, "diagnostic", 7)
    assert snapshot.rows is rows
    assert snapshot.stream_health is health
    assert snapshot.metric_error == "diagnostic"
    assert snapshot.activation_generation == 7
    assert snapshot.sampled_at_mono is None
    assert model.FleetSnapshot(rows, health) == model.FleetSnapshot(
        rows, health, None, 0, None
    )


def test_combat_values_preserve_supplied_identity_and_optional_defaults():
    observation_id = (TOKEN, 3)
    effect = model.EffectObservation("POINT", 30.0, observation_id)
    activity = model.CombatActivity()
    assert effect.kind == "POINT"
    assert effect.expires_at_mono == 30.0
    assert effect.observation_id is observation_id
    assert effect.name is None
    assert activity.expires_at_mono is None
    assert activity.observation_id is None
    assert activity.observations == ()


def test_supplied_combat_and_sample_time_are_appended_positional_fields():
    activity = model.CombatActivity(50.0, (TOKEN, 4))
    row = model.FleetRow("Alice", 10, (), None, 20, activity)
    snapshot = model.FleetSnapshot((row,), model.StreamHealth("active"), None, 7, 12.5)
    assert row.combat is activity
    assert snapshot.rows[0] is row
    assert snapshot.sampled_at_mono == 12.5


def test_combat_values_and_snapshot_fields_are_frozen():
    effect = model.EffectObservation("SCRAM", 30.0, (TOKEN, 1), "Pilot")
    activity = model.CombatActivity(50.0, (TOKEN, 2), (effect,))
    row = model.FleetRow("Alice", 0, combat=activity)
    snapshot = model.FleetSnapshot(
        (row,), model.StreamHealth("active"), sampled_at_mono=10.0
    )
    for value, field, replacement in (
        (effect, "kind", "NEUT"),
        (effect, "expires_at_mono", 60.0),
        (effect, "observation_id", (TOKEN, 99)),
        (effect, "name", "Other"),
        (activity, "expires_at_mono", 60.0),
        (activity, "observation_id", (TOKEN, 99)),
        (activity, "observations", ()),
        (row, "combat", None),
        (snapshot, "sampled_at_mono", 20.0),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(value, field, replacement)


@pytest.mark.parametrize("activity", [None, model.CombatActivity()])
def test_read_combat_distinguishes_absent_evidence_from_supported_inactive(activity):
    row = model.FleetRow("Alice", 0, combat=activity)
    assert combat.read_combat(row, now_mono=10.0) == activity


def _evidence_row():
    effects = (
        model.EffectObservation("SCRAM", 30.0, (TOKEN, 1), "Pilot A"),
        model.EffectObservation("POINT", 40.0, (TOKEN, 2)),
    )
    activity = model.CombatActivity(50.0, (TOKEN, 3), effects)
    return model.FleetRow("Alice", 0, incoming_dps=0, combat=activity)


@pytest.mark.parametrize(
    "now, indices",
    [(20.0, (0, 1)), (29.999, (0, 1)), (30.0, (1,)), (40.0, ()), (50.0, ())],
)
def test_read_filters_effects_at_deadlines_without_erasing_row_evidence(now, indices):
    row = _evidence_row()
    result = combat.read_combat(row, now_mono=now)
    assert result is not None
    assert result.expires_at_mono == 50.0
    assert result.observation_id is row.combat.observation_id
    expected = tuple(row.combat.observations[index] for index in indices)
    assert result.observations == expected
    for actual, original in zip(result.observations, expected, strict=True):
        assert actual is original


def test_read_sorts_effect_kinds_stably_without_reordering_or_replacing_input():
    from wingman.telemetry.metrics import _EWAR_ORDER

    neut_a = model.EffectObservation("NEUT", 80.0, (TOKEN, 6), "Z")
    point_a = model.EffectObservation("POINT", 70.0, (TOKEN, 5), "Z")
    scram_a = model.EffectObservation("SCRAM", 60.0, (TOKEN, 4), "Z")
    neut_b = model.EffectObservation("NEUT", 50.0, (TOKEN, 3), "A")
    scram_b = model.EffectObservation("SCRAM", 40.0, (TOKEN, 2), "A")
    point_b = model.EffectObservation("POINT", 30.0, (TOKEN, 1), "A")
    supplied = (neut_a, point_a, scram_a, neut_b, scram_b, point_b)
    activity = model.CombatActivity(90.0, (TOKEN, 7), supplied)
    row = model.FleetRow("Alice", 0, combat=activity)
    result = combat.read_combat(row, now_mono=10.0)
    expected = (scram_a, scram_b, point_a, point_b, neut_a, neut_b)
    assert result.observations == expected
    assert tuple(effect.kind for effect in result.observations[::2]) == _EWAR_ORDER
    for actual, original in zip(result.observations, expected, strict=True):
        assert actual is original
    assert row.combat is activity
    assert activity.observations is supplied


def test_repeated_reads_never_mutate_snapshot_or_renew_deadlines_and_ids():
    row = _evidence_row()
    activity = row.combat
    supplied = activity.observations
    snapshot = model.FleetSnapshot(
        (row,), model.StreamHealth("active"), sampled_at_mono=10.0
    )
    first = combat.read_combat(row, now_mono=20.0)
    for now in (30.0, 40.0, 50.0, 100.0):
        combat.read_combat(row, now_mono=now)
        combat.combat_row_visible(row, now_mono=now)
        combat.next_combat_transition(snapshot.rows, now_mono=now)
    assert combat.read_combat(row, now_mono=20.0) == first
    assert snapshot.sampled_at_mono == 10.0
    assert snapshot.rows[0] is row
    assert row.combat is activity
    assert activity.observations is supplied
    assert (activity.expires_at_mono, activity.observation_id) == (50.0, (TOKEN, 3))
    assert [(effect.expires_at_mono, effect.observation_id) for effect in supplied] == [
        (30.0, (TOKEN, 1)),
        (40.0, (TOKEN, 2)),
    ]


@pytest.mark.parametrize(
    "dps, incoming_dps, visible",
    [
        (None, None, False),
        (0, None, True),
        (None, 0, True),
        (0, 0, True),
        (10, 20, True),
    ],
)
def test_local_visibility_requires_either_available_direction(
    dps, incoming_dps, visible
):
    row = model.FleetRow(
        "Alice",
        dps,
        incoming_dps=incoming_dps,
        combat=model.CombatActivity(50.0, (TOKEN, 1)),
    )
    assert combat.combat_row_visible(row, now_mono=10.0) is visible


@pytest.mark.parametrize(
    "activity", [None, model.CombatActivity(), model.CombatActivity(10.0, (TOKEN, 1))]
)
def test_metrics_and_legacy_ewar_do_not_substitute_for_active_evidence(activity):
    row = model.FleetRow("Alice", 100, ("SCRAM",), incoming_dps=200, combat=activity)
    assert combat.combat_row_visible(row, now_mono=10.0) is False


@pytest.mark.parametrize(
    "now, visible",
    [(20.0, True), (30.0, True), (40.0, True), (49.999, True), (50.0, False)],
)
def test_row_visibility_outlasts_effects_but_ends_at_its_own_deadline(now, visible):
    assert combat.combat_row_visible(_evidence_row(), now_mono=now) is visible


@pytest.mark.parametrize(
    "now, expected",
    [(20.0, 30.0), (30.0, 40.0), (40.0, 50.0), (50.0, None), (100.0, None)],
)
def test_next_transition_advances_through_effect_and_row_deadlines(now, expected):
    assert combat.next_combat_transition((_evidence_row(),), now_mono=now) == expected


def test_next_transition_ignores_absent_and_inactive_rows():
    rows = (
        model.FleetRow("Alice", 0),
        model.FleetRow("Bob", 0, combat=model.CombatActivity()),
    )
    assert combat.next_combat_transition((), now_mono=10.0) is None
    assert combat.next_combat_transition(rows, now_mono=10.0) is None


def test_next_transition_finds_earliest_future_deadline_across_rows():
    rows = (
        _evidence_row(),
        model.FleetRow("Bob", 0, combat=model.CombatActivity(25.0, (TOKEN, 4))),
        model.FleetRow("Carol", 0, combat=model.CombatActivity(10.0, (TOKEN, 5))),
    )
    assert combat.next_combat_transition(rows, now_mono=20.0) == 25.0
    assert combat.next_combat_transition(rows, now_mono=25.0) == 30.0


def test_effect_expiry_is_independent_of_row_expiry_and_metric_availability():
    effect = model.EffectObservation("NEUT", 60.0, (TOKEN, 1))
    activity = model.CombatActivity(50.0, (TOKEN, 2), (effect,))
    row = model.FleetRow("Alice", None, combat=activity)
    result = combat.read_combat(row, now_mono=50.0)
    assert result.expires_at_mono == 50.0
    assert result.observation_id is activity.observation_id
    assert result.observations == (effect,)
    assert result.observations[0] is effect
    assert combat.combat_row_visible(row, now_mono=50.0) is False
    assert combat.next_combat_transition((row,), now_mono=50.0) == 60.0
    assert combat.read_combat(row, now_mono=60.0).observations == ()
    assert combat.next_combat_transition((row,), now_mono=60.0) is None
