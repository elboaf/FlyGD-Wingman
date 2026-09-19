"""Original-source preparation; fake tickets certify no producer wiring."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from math import inf, nan, nextafter
from types import MappingProxyType
from uuid import UUID

import pytest

from tests.fleetsharing_timing_helpers import FakePublicationSource
from wingman.combatprofile import LIMITS
from wingman.fleetsharing.model import CatalogueCharacter, FleetCatalogue
from wingman.fleetsharing.protocol import CombatPut, CombatRow, Effect, Observation
from wingman.fleetsharing.timing import TimingContext
from wingman.telemetry.metrics import FleetMetrics
from wingman.telemetry.model import (
    ClientSessionId,
    CombatActivity,
    CombatFact,
    EffectObservation,
    FleetRow,
    FleetSnapshot,
    RosterClient,
    RosterSnapshot,
    SourceId,
    SourceLifecycle,
    StreamHealth,
    TelemetryEnvelope,
)

CATALOGUE = FleetCatalogue(1, (CatalogueCharacter(42, "Alice"),))
LIFETIME = UUID(int=1)


def context(now=10.0):
    clock = [now]
    ctx = TimingContext(
        clock=lambda: clock[0],
        db_continuity_token=object(),
        elapsed_lifetime_token=object(),
    )
    return ctx, clock


def anchor(ctx, t=100000, a=10.0, r=10.0):
    candidate = ctx._diagnostic_candidate(started_at=a, received_at=r, server_time_ms=t)
    assert candidate is not None
    assert ctx._commit_diagnostic(candidate)


def source(m=10.0, *, x=9.0, sequence=2, observations=(), outgoing=0, incoming=123):
    row = FleetRow(
        "Alice",
        outgoing,
        incoming_dps=incoming,
        combat=CombatActivity(x + 30.0, (LIFETIME, sequence), observations),
    )
    return FakePublicationSource(
        FleetSnapshot((row,), StreamHealth("active"), sampled_at_mono=m)
    )


def stage(ctx, ticket, *, eligible=frozenset({42}), catalogue=CATALOGUE):
    return ctx._stage_publication(ticket, catalogue, eligible_character_ids=eligible)


def candidate_origin(t, x, receipt, lower, upper):
    exact_delta = 1000 * (Fraction(x) - Fraction(receipt))
    c = t + exact_delta.numerator // exact_delta.denominator - 200
    assert 0 <= c and lower <= upper  # noqa: SIM300 — approved independent oracle
    return min(upper, max(lower, c))


def test_delayed_equal_and_later_coordinates_oracle():
    first = candidate_origin(100000, 10.0, 10.0, 0, 2**53 - 1)
    assert first == 99800
    assert candidate_origin(101000, 10.0, 10.0, first, first) == first
    assert candidate_origin(101000, 9.5, 10.0, 0, first) == first
    assert candidate_origin(99900, 10.5, 11.0, first, 2**53 - 1) == first


def test_origin_conversion_floors_once_after_exact_input_ratio_subtraction():
    ctx, _ = context(0.5)
    anchor(ctx, a=0.0, r=0.001)
    expected = candidate_origin(100000, 0.5, 0.001, 0, 2**53 - 1)
    assert expected == 100298  # Float subtraction/multiplication would give 100299.
    prepared = stage(ctx, source(m=0.5, x=0.5))
    assert prepared is not None
    assert prepared.sampled_at_ms == expected
    assert prepared.rows[0].activity_age_ms == 0


def test_staging_retains_exact_source_snapshot_m_and_nullable_wire_measurement():
    ctx, _ = context()
    anchor(ctx)
    ticket = source(
        observations=(EffectObservation("NEUT", 38.0, (LIFETIME, 1)),),
        outgoing=None,
        incoming=0,
    )
    prepared = stage(ctx, ticket)
    assert prepared is not None
    assert prepared.source is ticket
    assert prepared.snapshot is ticket.snapshot
    assert prepared.sampled_at_mono == 10.0
    assert prepared.sampled_at_ms == 99800
    assert prepared.rows == (
        CombatRow(42, None, 0, 1000, (Effect("NEUT", (Observation(None, 2000),)),)),
    )


def test_live_but_unavailable_measurement_is_not_fabricated_zero_or_withdrawal():
    ctx, clock = context()
    anchor(ctx)
    assert stage(ctx, source(outgoing=None, incoming=None)) is None
    assert len(ctx._publisher.associations) == 0
    clock[0] = 10.5
    healthy = stage(ctx, source(outgoing=0, incoming=0))
    assert healthy is not None
    assert healthy.rows == (CombatRow(42, 0, 0, 1000, ()),)


def test_advisory_source_admission_requires_exact_true(monkeypatch):
    ctx, _ = context()
    anchor(ctx)
    ticket = source()
    monkeypatch.setattr(ticket, "is_current", lambda: 1)
    assert stage(ctx, ticket) is None
    assert len(ctx._publisher.associations) == 0


def test_abandoned_original_measurement_and_events_keep_pins_after_ticket_rotation():
    ctx, clock = context()
    anchor(ctx, a=9.0, r=10.0)
    original = source(x=9.5)
    first = stage(ctx, original)
    assert first is not None
    original.revoke()
    clock[0] = 10.5
    anchor(ctx, t=101000, a=10.5, r=10.5)
    rotated = FakePublicationSource(original.snapshot)
    second = stage(ctx, rotated)
    assert second is not None
    assert second.source is rotated
    assert second.snapshot is first.snapshot
    assert (second.sampled_at_ms, second.rows) == (first.sampled_at_ms, first.rows)


def test_new_coordinates_are_sorted_tied_and_bounded_by_retained_origins():
    ctx, clock = context()
    anchor(ctx, a=9.0, r=10.0)
    first = stage(ctx, source(x=10.0))
    assert first is not None
    origin = candidate_origin(100000, 10.0, 10.0, 0, 2**53 - 1)
    assert first.sampled_at_ms == origin
    clock[0] = 10.5
    anchor(ctx, t=101000, a=10.5, r=10.5)
    delayed = stage(ctx, source(m=10.5, x=9.75, sequence=3))
    assert delayed is not None
    delayed_origin = candidate_origin(101000, 9.75, 10.5, 0, origin)
    assert delayed.sampled_at_ms - delayed.rows[0].activity_age_ms == delayed_origin
    clock[0] = 11.0
    anchor(ctx, t=101000, a=10.5, r=11.0)
    later = stage(
        ctx,
        source(
            m=11.0,
            x=10.75,
            sequence=4,
            observations=(
                EffectObservation("SCRAM", 40.75, (LIFETIME, 4), "A"),
                EffectObservation("POINT", 40.0, (LIFETIME, 2), "B"),
            ),
        ),
    )
    assert later is not None
    s = later.sampled_at_ms
    row = later.rows[0]
    expected = candidate_origin(101000, 10.75, 11.0, delayed.sampled_at_ms, 2**53 - 1)
    assert s - row.activity_age_ms == expected
    assert row.effects[0].observations[0].age_ms == row.activity_age_ms
    assert s - row.effects[1].observations[0].age_ms == origin


@pytest.mark.parametrize(
    "m,now,accepted",
    [
        (10.0, 14.999, True),
        (10.0, 15.0, False),
        (10.0, nextafter(15.0, -inf), True),
        (nextafter(0.0, -inf), 5.0, False),
        (10.0, nextafter(10.0, -inf), False),
        (nan, 10.0, False),
        (inf, 10.0, False),
        (10.0, nan, False),
        (10.0, inf, False),
    ],
)
def test_original_sample_age_is_strict_and_uses_exact_input_ratios(m, now, accepted):
    ctx, _ = context(now)
    anchor(ctx, a=0.0, r=0.0)
    ticket = source(m=m, x=-1.0 if m < 0 else 9.0)
    assert (stage(ctx, ticket) is not None) is accepted


@pytest.mark.parametrize(
    "now,accepted",
    [(70.0, True), (nextafter(70.0, inf), False), (nextafter(10.0, -inf), False)],
)
def test_anchor_lifetime_is_inclusive_sixty_seconds_with_no_future_anchor(
    now, accepted
):
    ctx, _ = context(now)
    anchor(ctx)
    assert (stage(ctx, source(m=now, x=now - 1)) is not None) is accepted


def test_failed_stage_consumes_exact_cadence_across_new_borrower_and_ticket():
    ctx, clock = context()
    ticket = source()
    assert stage(ctx, ticket) is None  # No authenticated anchor.
    anchor(ctx)
    clock[0] = nextafter(10.5, -inf)
    assert stage(ctx, FakePublicationSource(ticket.snapshot)) is None
    clock[0] = 10.5
    second_borrower = ctx
    assert stage(second_borrower, ticket) is not None
    clock[0] = nextafter(11.0, -inf)
    assert stage(ctx, source(m=11.0, sequence=3)) is None
    clock[0] = 11.0
    assert stage(ctx, source(m=11.0, sequence=3)) is not None


def test_stale_source_and_latched_context_refuse_without_creating_withdrawal():
    ctx, clock = context()
    anchor(ctx)
    ticket = source()
    ticket.revoke()
    assert stage(ctx, ticket) is None
    clock[0] = 10.5
    ctx._inconsistent = True
    assert stage(ctx, source()) is None
    assert len(ctx._publisher.associations) == 0


@pytest.mark.parametrize(
    "change", ["outgoing", "incoming", "deadline", "effect", "unselected"]
)
def test_same_m_conflicts_compare_original_full_measurement_not_eligible_subset(change):
    ctx, clock = context()
    anchor(ctx)
    ticket = source(
        observations=(EffectObservation("POINT", 38.0, (LIFETIME, 1), "A"),)
    )
    row = ticket.snapshot.rows[0]
    snapshot = replace(ticket.snapshot, rows=(row, replace(row, character="Other")))
    first = stage(ctx, FakePublicationSource(snapshot))
    assert first is not None
    before = ctx._publisher
    if change == "outgoing":
        changed = replace(row, dps=12)
    elif change == "incoming":
        changed = replace(row, incoming_dps=None)
    elif change == "deadline":
        changed = replace(row, combat=replace(row.combat, expires_at_mono=39.5))
    elif change == "effect":
        changed = replace(row, combat=replace(row.combat, observations=()))
    else:
        changed = row
    other = snapshot.rows[1]
    if change == "unselected":
        other = replace(other, incoming_dps=99)
    clock[0] = 10.5
    assert (
        stage(ctx, FakePublicationSource(replace(snapshot, rows=(changed, other))))
        is None
    )
    assert ctx._publisher is before
    clock[0] = 11.0
    assert (
        stage(ctx, FakePublicationSource(snapshot)).sampled_at_ms == first.sampled_at_ms
    )


def test_same_measurement_survives_genuine_effect_pruning_and_eligibility_change():
    ctx, clock = context()
    anchor(ctx)
    old = EffectObservation("SCRAM", 10.5, (LIFETIME, 1), "Old")
    ticket = source(observations=(old,))
    alice = ticket.snapshot.rows[0]
    snapshot = replace(ticket.snapshot, rows=(alice, replace(alice, character="Bravo")))
    catalogue = FleetCatalogue(
        1, (*CATALOGUE.characters, CatalogueCharacter(7, "Bravo"))
    )
    first = stage(ctx, FakePublicationSource(snapshot), catalogue=catalogue)
    assert first is not None
    clock[0] = 10.5
    second = stage(
        ctx,
        FakePublicationSource(snapshot),
        catalogue=catalogue,
        eligible=frozenset({7}),
    )
    assert second is not None
    assert second.sampled_at_ms == first.sampled_at_ms
    assert second.rows == (CombatRow(7, 0, 123, 1000, ()),)
    assert second.snapshot is snapshot


def test_existing_event_id_cannot_change_original_deadline_even_with_new_m():
    ctx, clock = context()
    anchor(ctx)
    assert stage(ctx, source()) is not None
    before = ctx._publisher
    clock[0] = 10.5
    assert stage(ctx, source(m=10.5, x=9.5)) is None
    assert ctx._publisher is before


@pytest.mark.parametrize(
    "t,x,expected", [(200, 10.0, 0), (199, 10.0, None), (2**53 - 1, 10.0, 2**53 - 201)]
)
def test_new_origins_never_repair_a_negative_candidate(t, x, expected):
    ctx, _ = context()
    anchor(ctx, t=t)
    result = stage(ctx, source(x=x))
    if expected is None:
        assert result is None
        assert len(ctx._publisher.associations) == 0
    else:
        assert result.sampled_at_ms == expected


def test_deadline_subtraction_and_sample_order_use_original_exact_ratios():
    ctx, _ = context(-29.5)
    anchor(ctx, a=-29.5, r=-29.5)
    assert (
        stage(
            ctx,
            source(
                m=-29.5,
                x=-30.0,
                observations=(
                    EffectObservation("POINT", nextafter(0.0, inf), (LIFETIME, 1)),
                ),
            ),
        )
        is None
    )
    ctx, _ = context(0.0)
    anchor(ctx, a=0.0, r=0.0)
    assert stage(ctx, source(m=nextafter(0.0, -inf), x=0.0)) is None


@pytest.mark.parametrize(
    "bad",
    [
        EffectObservation("POINT", 38.0, (LIFETIME, 1), "e\u0301"),
        EffectObservation("NEUT", 38.0, (LIFETIME, 1), "Named"),
        EffectObservation("JAM", 38.0, (LIFETIME, 1)),
    ],
)
def test_invalid_effect_dimensions_refuse_entire_batch_before_pin_commit(bad):
    ctx, _ = context()
    anchor(ctx)
    before = ctx._publisher
    assert stage(ctx, source(observations=(bad,))) is None
    assert ctx._publisher is before


@pytest.mark.parametrize("dps", [True, -1, 10_000_001, 1.5])
def test_invalid_measured_dimension_never_allocates_any_pin(dps):
    ctx, _ = context()
    anchor(ctx)
    before = ctx._publisher
    assert stage(ctx, source(outgoing=dps)) is None
    assert ctx._publisher is before


def maximal_source(m=10.0, count=32):
    catalogue = FleetCatalogue(
        1, tuple(CatalogueCharacter(i, str(i)) for i in range(1, count + 1))
    )
    observations = tuple(
        EffectObservation(kind, m + 30.0, (LIFETIME, int(m * 2)), name)
        for kind in ("SCRAM", "POINT", "NEUT")
        for name in (
            (*(f"Name {n}" for n in range(8)), None) if kind != "NEUT" else (None,)
        )
    )
    row = source(m, x=m, sequence=int(m * 2), observations=observations).snapshot.rows[
        0
    ]
    snapshot = FleetSnapshot(
        tuple(replace(row, character=str(i)) for i in range(1, count + 1)),
        StreamHealth("active"),
        sampled_at_mono=m,
    )
    return FakePublicationSource(snapshot), catalogue, frozenset(range(1, count + 1))


def test_maximum_attempt_derives_641_and_33_rows_refuse_without_partial_commit():
    assert LIMITS["associations_per_attempt"] == 32 * (1 + 19) + 1 == 641
    assert LIMITS["association_capacity"] == (30000 // 500 + 1) * 641 == 39101
    ctx, clock = context()
    anchor(ctx)
    ticket, catalogue, eligible = maximal_source()
    prepared = stage(ctx, ticket, catalogue=catalogue, eligible=eligible)
    assert prepared is not None
    assert len(prepared.rows) == 32
    assert len(ctx._publisher.associations) == 641
    before = ctx._publisher
    clock[0] = 10.5
    ticket, catalogue, eligible = maximal_source(m=10.5, count=33)
    assert stage(ctx, ticket, catalogue=catalogue, eligible=eligible) is None
    assert ctx._publisher is before


def test_capacity_reservation_is_atomic_and_never_evicts_a_live_pin():
    ctx, clock = context()
    anchor(ctx)
    prepared = stage(ctx, source())
    # Deliberate impossible retained load exercises the refusal backstop, not
    # an alternative production cap or a claim this exceeds legal cadence.
    template = prepared.pins[1]
    seeded = {}
    for n in range(39099):
        evidence = replace(template.evidence, key=("seed", n))
        seeded[evidence.key] = replace(template, evidence=evidence)
    ctx._publisher = replace(ctx._publisher, associations=MappingProxyType(seeded))
    clock[0] = 10.5
    assert stage(ctx, source(m=10.5)) is not None
    assert len(ctx._publisher.associations) == 39101
    before = ctx._publisher
    clock[0] = 11.0
    assert stage(ctx, source(m=11.0)) is None
    assert ctx._publisher is before
    assert all(ctx._publisher.associations[key] is pin for key, pin in seeded.items())
    clock[0] = nextafter(11.5, -inf)
    assert stage(ctx, source(m=11.5)) is None
    assert ctx._publisher is before


def test_original_horizons_survive_retries_and_shared_timepoint_outlives_sample_key():
    ctx, clock = context()
    anchor(ctx)
    first = stage(ctx, source(x=10.0))
    sample_pin, event_pin = first.pins
    clock[0] = 10.5
    repeated = stage(ctx, source(x=10.0))
    assert repeated.pins == first.pins
    assert repeated.pins[0] is sample_pin
    assert repeated.pins[1] is event_pin
    clock[0] = 20.0
    # Same coordinate, new event ID, after the sample pin's original expiry.
    later = stage(ctx, source(m=20.0, x=10.0, sequence=3))
    assert sample_pin.evidence.key not in ctx._publisher.associations
    assert ctx._publisher.associations[event_pin.evidence.key] is event_pin
    assert later.sampled_at_ms - later.rows[0].activity_age_ms == first.sampled_at_ms
    clock[0] = 40.0
    assert stage(ctx, source(m=40.0, x=40.0, sequence=4)) is not None
    assert event_pin.evidence.key not in ctx._publisher.associations
    assert all(
        pin.evidence.coordinate != 10 for pin in ctx._publisher.associations.values()
    )


def test_final_validator_runs_under_source_leaf_lock_without_reentry(monkeypatch):
    ctx, clock = context()
    anchor(ctx)
    ticket = source()
    prepared = stage(ctx, ticket)
    assert prepared is not None
    before, cadence = ctx._publisher, ctx._next_stage_at

    def forbidden():
        pytest.fail("final timing validation re-entered source authority")

    admit = ticket.admit_start
    monkeypatch.setattr(ticket, "is_current", forbidden)
    monkeypatch.setattr(ticket, "admit_start", lambda _validate: forbidden())
    monkeypatch.setattr(
        FakePublicationSource, "snapshot", property(lambda _self: forbidden())
    )
    clock[0] = 14.999
    assert admit(lambda: ctx._validate_publication(prepared)) is True
    assert ctx._publisher is before
    assert ctx._next_stage_at == cadence
    clock[0] = 15.0
    with pytest.raises(ValueError):
        admit(lambda: ctx._validate_publication(prepared))
    assert ctx._publisher is before  # Expired prepared work never releases pins.


@pytest.mark.parametrize(
    "change", ["source", "snapshot", "sampled_at_mono", "sampled_at_ms", "rows", "pins"]
)
def test_final_validation_refuses_restamping_or_modified_prepared_association(change):
    ctx, _ = context()
    anchor(ctx)
    ticket = source()
    prepared = stage(ctx, ticket)
    changes = {
        "source": FakePublicationSource(ticket.snapshot),
        "snapshot": replace(ticket.snapshot, sampled_at_mono=10.1),
        "sampled_at_mono": 10.1,
        "sampled_at_ms": prepared.sampled_at_ms + 1,
        "rows": (replace(prepared.rows[0], incoming_dps=999),),
        "pins": (),
    }
    with pytest.raises(ValueError):
        ctx._validate_publication(replace(prepared, **{change: changes[change]}))


@pytest.mark.parametrize(
    "expiry", ["row", "effect", "anchor", "latch", "foreign", "revoked"]
)
def test_final_refusal_never_prunes_or_rewrites_signed_selection(expiry):
    ctx, clock = context(69.0 if expiry == "anchor" else 10.0)
    anchor(ctx)
    ticket = source(
        m=clock[0],
        x=clock[0] - 1,
        observations=(EffectObservation("POINT", 10.5, (LIFETIME, 1)),)
        if expiry == "effect"
        else (),
    )
    if expiry == "row":
        ticket = source(x=-19.5)
    prepared = stage(ctx, ticket)
    assert prepared is not None
    before = ctx._publisher
    if expiry in ("row", "effect"):
        clock[0] = 10.5
    elif expiry == "anchor":
        clock[0] = nextafter(70.0, inf)
    elif expiry == "latch":
        ctx._inconsistent = True
    elif expiry == "foreign":
        other, _ = context()
        anchor(other)
        with pytest.raises(ValueError):
            other._validate_publication(prepared)
        return
    else:
        ticket.revoke()
        assert ticket.admit_start(lambda: ctx._validate_publication(prepared)) is False
        return
    with pytest.raises(ValueError):
        ctx._validate_publication(prepared)
    assert ctx._publisher is before


def test_loss_cutoff_blocks_old_dependent_effect_despite_new_row_id_and_ticket():
    ctx, clock = context()
    anchor(ctx)
    old = EffectObservation("POINT", 39.0, (LIFETIME, 1), "A")
    prepared = stage(ctx, source(observations=(old,)))
    before, cadence = ctx._publisher, ctx._next_stage_at
    ctx._publisher_lost_continuity(cutoff=10.0)
    assert ctx._state.anchor is None
    assert ctx._publisher is before
    assert ctx._next_stage_at == cadence
    anchor(ctx, t=101000, a=11.0, r=11.0)
    clock[0] = 11.0
    with pytest.raises(ValueError):
        ctx._validate_publication(prepared)
    assert stage(ctx, source(m=11.0, x=11.0, sequence=99, observations=(old,))) is None
    clock[0] = 11.5
    assert stage(ctx, source(m=11.5, x=10.0, sequence=100)) is None
    clock[0] = 12.0
    fresh = stage(
        ctx,
        source(
            m=12.0,
            x=11.0,
            sequence=99,
            observations=(EffectObservation("POINT", 40.5, (LIFETIME, 98), "A"),),
        ),
    )
    assert fresh is not None
    assert fresh.rows[0].effects[0].observations[0].age_ms == 1500
    clock[0] = 39.0
    # Genuine expiry, not a new ID, removes the pre-cutoff dependency.
    assert (
        stage(ctx, source(m=39.0, x=38.0, sequence=101, observations=(old,)))
        is not None
    )


def test_loss_does_not_unlatch_diagnostic_or_reopen_with_lower_cutoff():
    ctx, clock = context()
    anchor(ctx)
    ctx._publisher_lost_continuity(cutoff=10.0)
    ctx._publisher_lost_continuity(cutoff=9.0)
    anchor(ctx, t=100500, a=10.5, r=10.5)
    clock[0] = 10.5
    assert stage(ctx, source(m=10.0, x=9.0)) is None
    ctx._inconsistent = True
    ctx._publisher_lost_continuity(cutoff=11.0)
    assert ctx._inconsistent
    assert (
        ctx._diagnostic_candidate(
            started_at=1000.0, received_at=1000.0, server_time_ms=1090000
        )
        is None
    )


def test_uncertain_or_empty_projection_is_not_explicit_no_anchor_withdrawal():
    ctx, clock = context()
    empty = FakePublicationSource(FleetSnapshot((), StreamHealth("active")))
    assert stage(ctx, empty) is None
    anchor(ctx)
    clock[0] = 10.5
    assert stage(ctx, source(), eligible=frozenset()) is None
    assert len(ctx._publisher.associations) == 0
    # Existing closed DTO is the distinct intentional API. S4 owns the reason
    # and applicable authority gates; numeric staging never manufactures it.
    withdrawal = CombatPut(sampled_at_ms=0, rows=())
    assert withdrawal.sampled_at_ms == 0 and withdrawal.rows == ()


@pytest.mark.parametrize("member", ["row", "effect"])
def test_locally_live_but_overage_wire_member_refuses_without_repair(member):
    ctx, clock = context()
    anchor(ctx, a=9.0, r=10.0)
    old = EffectObservation("POINT", 39.5, (LIFETIME, 1), "Old")
    assert stage(ctx, source(x=9.5, observations=(old,))) is not None
    before = ctx._publisher
    clock[0] = 39.49
    anchor(ctx, t=130000, a=39.0, r=39.49)
    ticket = source(
        m=39.49,
        x=9.5 if member == "row" else 39.0,
        sequence=2 if member == "row" else 3,
        observations=() if member == "row" else (old,),
    )
    assert stage(ctx, ticket) is None
    assert ctx._publisher is before


def test_sixty_five_maximum_paced_attempts_retain_only_original_live_horizons():
    ctx, clock = context()
    anchor(ctx)
    for attempt in range(65):
        clock[0] = 10.0 + attempt / 2
        ticket, catalogue, eligible = maximal_source(clock[0])
        prepared = stage(ctx, ticket, catalogue=catalogue, eligible=eligible)
        assert prepared is not None
        assert len(ctx._publisher.associations) == min(attempt + 1, 60) * 640 + min(
            attempt + 1, 20
        )
        assert len(ctx._publisher.associations) <= 39101
        assert all(
            pin.evidence.horizon > Fraction(clock[0])
            for pin in ctx._publisher.associations.values()
        )
    assert len(ctx._publisher.associations) == 38420


def test_final_gate_rejects_clock_regression_and_nonfinite_without_mutation():
    ctx, clock = context(10.5)
    anchor(ctx)
    prepared = stage(ctx, source())
    assert prepared is not None
    before = ctx._publisher
    for now in (nextafter(10.5, -inf), nan, inf, -inf):
        clock[0] = now
        with pytest.raises(ValueError):
            ctx._validate_publication(prepared)
        assert ctx._publisher is before


def validation_admitted(ctx, prepared):
    try:
        ctx._validate_publication(prepared)
    except ValueError:
        return False
    return True


def test_final_timing_boundary_and_retained_pin_membership_are_required():
    ctx, clock = context()
    anchor(ctx)
    prepared = stage(ctx, source())
    clock[0] = 14.999
    assert validation_admitted(ctx, prepared)
    clock[0] = 15.0
    assert not validation_admitted(ctx, prepared)
    clock[0] = 14.999
    remaining = dict(ctx._publisher.associations)
    del remaining[prepared.pins[1].evidence.key]
    ctx._publisher = replace(ctx._publisher, associations=MappingProxyType(remaining))
    assert not validation_admitted(ctx, prepared)


def test_impossible_retained_predecessor_successor_order_refuses_atomically():
    ctx, clock = context()
    anchor(ctx)
    first = stage(ctx, source())
    corrupted = dict(ctx._publisher.associations)
    event = first.pins[1]
    corrupted[event.evidence.key] = replace(event, origin_ms=first.sampled_at_ms + 1)
    ctx._publisher = replace(ctx._publisher, associations=MappingProxyType(corrupted))
    before = ctx._publisher
    clock[0] = 10.5
    assert stage(ctx, source(m=10.5, x=9.5, sequence=3)) is None
    assert ctx._publisher is before


def test_loss_cutoff_refuses_invalid_clock_without_mutation():
    ctx, _ = context()
    anchor(ctx)
    before = ctx._state
    for cutoff in (nan, inf, -inf):
        with pytest.raises(ValueError):
            ctx._publisher_lost_continuity(cutoff=cutoff)
        assert ctx._state is before


def test_js_safe_upper_bound_clamps_new_origins_without_losing_order():
    ctx, _ = context(11.0)
    anchor(ctx, t=2**53 - 1)
    prepared = stage(ctx, source(m=11.0, x=10.5))
    assert prepared is not None
    assert prepared.sampled_at_ms == 2**53 - 1
    assert prepared.rows[0].activity_age_ms == 0


@pytest.mark.parametrize(
    "kind,amount,name,outgoing,incoming",
    [
        ("incoming_damage", 900, None, 0, 90),
        ("incoming_damage", 1, None, 0, 0),
        ("outgoing_damage", 1, None, 0, 0),
        ("incoming_neut", None, None, 0, 0),
        ("incoming_scram", None, "é", 0, 0),
    ],
)
def test_real_metrics_sample_rebind_and_ticket_rotation_do_not_reidentify_evidence(
    kind, amount, name, outgoing, incoming
):
    ctx, clock = context()
    anchor(ctx)
    utc = datetime(2026, 1, 1, tzinfo=UTC)
    metrics = FleetMetrics(_clock=ctx._clock, _utc_now=lambda: utc)
    session = ClientSessionId(1, 2, "Alice", 1)
    metrics.consume(
        TelemetryEnvelope(
            1, RosterSnapshot(1, (RosterClient(1, 2, "EVE - Alice", "Alice", session),))
        )
    )
    source_id = SourceId("local-only-log", utc)
    lifecycle = SourceLifecycle("Alice", 1, source_id, True, True)
    metrics.consume(TelemetryEnvelope(2, lifecycle))
    metrics.consume(
        TelemetryEnvelope(
            3, CombatFact("Alice", 1, source_id, utc, kind, amount, observed_name=name)
        )
    )
    snapshot = metrics.snapshot(4, StreamHealth("active"))
    ticket = FakePublicationSource(snapshot)
    first = stage(ctx, ticket)
    assert first is not None
    assert first.snapshot is snapshot
    assert (first.rows[0].outgoing_dps, first.rows[0].incoming_dps) == (
        outgoing,
        incoming,
    )
    assert first.sampled_at_mono == snapshot.sampled_at_mono == 10.0
    assert first.sampled_at_ms == 99800
    assert snapshot.rows[0].combat.expires_at_mono == 40.0
    assert first.rows[0].activity_age_ms == 0
    if kind in ("incoming_neut", "incoming_scram"):
        effect_kind = "NEUT" if kind == "incoming_neut" else "SCRAM"
        assert first.rows[0].effects == (Effect(effect_kind, (Observation(name, 0),)),)
    ticket.revoke()
    metrics.consume(TelemetryEnvelope(5, lifecycle))
    rebound = metrics.snapshot(6, StreamHealth("active"))
    assert rebound.rows[0].combat == snapshot.rows[0].combat
    assert (
        rebound.rows[0].combat.observation_id == snapshot.rows[0].combat.observation_id
    )
    clock[0] = 10.5
    rotated = FakePublicationSource(rebound)
    second = stage(ctx, rotated)
    assert second is not None
    assert second.source is rotated and second.snapshot is rebound
    assert second.sampled_at_ms == first.sampled_at_ms
    assert second.rows == first.rows
    assert all(
        left is right for left, right in zip(first.pins, second.pins, strict=True)
    )
    with pytest.raises(FrozenInstanceError):
        second.source = ticket


def bound_real_metrics(clock, utc):
    metrics = FleetMetrics(_clock=lambda: clock[0], _utc_now=lambda: utc[0])
    session = ClientSessionId(1, 2, "Alice", 1)
    metrics.consume(
        TelemetryEnvelope(
            1, RosterSnapshot(1, (RosterClient(1, 2, "EVE - Alice", "Alice", session),))
        )
    )
    source_id = SourceId("local-only-log", utc[0])
    metrics.consume(
        TelemetryEnvelope(2, SourceLifecycle("Alice", 1, source_id, True, True))
    )
    return metrics, source_id


@pytest.mark.parametrize("kind", ["incoming_damage", "incoming_scram"])
@pytest.mark.parametrize(
    "m, delay_us",
    [
        pytest.param(0.1, 0, id="fractional-same-tick"),
        pytest.param(0.2, 0, id="downward-same-tick"),
        pytest.param(nextafter(2.0, -inf), 0, id="below-32-same-tick"),
        pytest.param(2.0, 0, id="at-32-same-tick"),
        pytest.param(nextafter(2.0, inf), 0, id="above-32-same-tick"),
        pytest.param(0.0, 200_000, id="delayed-duration-up"),
        pytest.param(0.1, 123_457, id="delayed-microseconds"),
    ],
)
def test_real_metrics_fractional_deadlines_stage_and_retry_without_restamping(
    kind, m, delay_us
):
    ctx, clock = context(m)
    anchor(ctx, a=m, r=m)
    utc = [datetime(2026, 1, 1, tzinfo=UTC)]
    metrics, source_id = bound_real_metrics(clock, utc)
    metrics.consume(
        TelemetryEnvelope(
            3,
            CombatFact(
                "Alice",
                1,
                source_id,
                utc[0] - timedelta(microseconds=delay_us),
                kind,
                100 if kind == "incoming_damage" else None,
            ),
        )
    )
    snapshot = metrics.snapshot(4, StreamHealth("active"))
    ticket = FakePublicationSource(snapshot)
    first = stage(ctx, ticket)
    assert first is not None
    row = snapshot.rows[0]
    assert first.snapshot is snapshot
    assert first.sampled_at_mono == snapshot.sampled_at_mono == m
    assert first.rows[0].incoming_dps == (10 if kind == "incoming_damage" else 0)
    assert first.rows[0].outgoing_dps == 0
    seconds, micros = divmod(30_000_000 - delay_us, 1_000_000)
    exact = Fraction(m) + seconds + Fraction(micros, 1_000_000)
    deadline = row.combat.expires_at_mono
    assert Fraction(deadline) <= exact < Fraction(nextafter(deadline, inf))
    assert row.combat.observation_id[1] == 3
    assert first.pins[0].evidence.coordinate == Fraction(m)
    assert first.pins[1].evidence.coordinate == Fraction(deadline) - 30
    assert first.pins[1].evidence.horizon == Fraction(deadline)
    if kind == "incoming_scram":
        assert row.combat.observations == (
            EffectObservation("SCRAM", deadline, row.combat.observation_id),
        )
        assert first.rows[0].effects == (
            Effect("SCRAM", (Observation(None, first.rows[0].activity_age_ms),)),
        )
        assert first.pins[2].evidence.coordinate == first.pins[1].evidence.coordinate
        assert first.pins[2].evidence.horizon == first.pins[1].evidence.horizon
    assert ticket.admit_start(lambda: ctx._validate_publication(first)) is True

    # The earliest representable retry at least 500ms later — m + .5 can
    # round below the exact cadence boundary (notably .1 -> .6).
    retry_at = Fraction(m) + Fraction(1, 2)
    clock[0] = float(retry_at)
    if Fraction(clock[0]) < retry_at:
        clock[0] = nextafter(clock[0], inf)
    second = stage(ctx, ticket)
    assert second is not None
    assert second.snapshot is snapshot
    assert second.snapshot.rows[0] is row
    assert second.sampled_at_mono == m
    assert second.sampled_at_ms == first.sampled_at_ms
    assert second.rows == first.rows
    assert all(a is b for a, b in zip(first.pins, second.pins, strict=True))
    assert ticket.admit_start(lambda: ctx._validate_publication(second)) is True


def test_real_metrics_eight_fractional_samples_with_fresh_damage_and_ewar_stage():
    ctx, clock = context(0.125)
    anchor(ctx, a=0.125, r=0.125)
    mono = [0.1]
    start = datetime(2026, 1, 1, tzinfo=UTC)
    utc = [start]
    metrics, source_id = bound_real_metrics(mono, utc)
    results = []
    for index in range(8):
        mono[0] = 0.1 + index / 2
        utc[0] = start + timedelta(milliseconds=500 * index)
        damage_sequence = 3 + 3 * index
        for sequence, kind in (
            (damage_sequence, "incoming_damage"),
            (damage_sequence + 1, "incoming_scram"),
        ):
            metrics.consume(
                TelemetryEnvelope(
                    sequence,
                    CombatFact(
                        "Alice",
                        1,
                        source_id,
                        utc[0],
                        kind,
                        100 if kind == "incoming_damage" else None,
                    ),
                )
            )
        snapshot = metrics.snapshot(damage_sequence + 2, StreamHealth("active"))
        # Exact 500ms staging cadence, about 25ms after each measurement;
        # do not conflate the producer bug with .1 -> .6 cadence rounding.
        clock[0] = 0.125 + index / 2
        ticket = FakePublicationSource(snapshot)
        results.append((ticket, stage(ctx, ticket)))
    assert [t.snapshot.sampled_at_mono for t, p in results if p is None] == []
    token = results[0][0].snapshot.rows[0].combat.observation_id[0]
    previous_deadline = -inf
    for index, (ticket, prepared) in enumerate(results):
        row = ticket.snapshot.rows[0]
        m = 0.1 + index / 2
        deadline = row.combat.expires_at_mono
        assert prepared.snapshot is ticket.snapshot
        assert prepared.sampled_at_mono == m
        assert prepared.rows[0].incoming_dps == 10 * (index + 1)
        assert row.combat.observation_id == (token, 3 + 3 * index)
        assert row.combat.observations == (
            EffectObservation("SCRAM", deadline, (token, 4 + 3 * index)),
        )
        assert previous_deadline < deadline
        assert (
            Fraction(deadline) <= Fraction(m) + 30 < Fraction(nextafter(deadline, inf))
        )
        previous_deadline = deadline
    ticket, last = results[-1]
    clock[0] += 0.5
    retried = stage(ctx, ticket)
    assert retried is not None
    assert retried.snapshot is last.snapshot
    assert retried.sampled_at_mono == 3.6
    assert (retried.sampled_at_ms, retried.rows) == (last.sampled_at_ms, last.rows)
    assert all(a is b for a, b in zip(last.pins, retried.pins, strict=True))


@pytest.mark.parametrize("member", ["row", "effect"])
def test_changed_deadline_cannot_hide_immutable_conflict_by_becoming_expired(member):
    ctx, clock = context()
    anchor(ctx)
    old = EffectObservation("POINT", 38.0, (LIFETIME, 1), "A")
    ticket = source(observations=(old,))
    row = ticket.snapshot.rows[0]
    other = replace(row, character="Bravo")
    snapshot = replace(ticket.snapshot, rows=(row, other))
    catalogue = FleetCatalogue(
        1, (*CATALOGUE.characters, CatalogueCharacter(7, "Bravo"))
    )
    eligible = frozenset({7, 42})
    assert stage(
        ctx, FakePublicationSource(snapshot), catalogue=catalogue, eligible=eligible
    )
    before = ctx._publisher
    if member == "effect":
        combat = replace(row.combat, observations=(replace(old, expires_at_mono=10.0),))
    else:
        combat = replace(row.combat, expires_at_mono=10.0, observations=())
    changed = replace(
        snapshot, sampled_at_mono=10.5, rows=(replace(row, combat=combat), other)
    )
    clock[0] = 10.5
    assert (
        stage(
            ctx, FakePublicationSource(changed), catalogue=catalogue, eligible=eligible
        )
        is None
    )
    assert ctx._publisher is before
