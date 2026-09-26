"""Retained consumer timing; fake tickets do not certify producer admission."""

from collections.abc import Callable
from fractions import Fraction
from inspect import Parameter, signature
from math import inf, nan, nextafter
from typing import get_type_hints

import pytest

from tests.fleetsharing_timing_helpers import FakePublicationSource
from wingman.combatprofile import LIMITS
from wingman.fleetsharing.model import PublicationSource
from wingman.fleetsharing.scheduling import SIGNED_INTERVAL_S, Scheduler, Work
from wingman.fleetsharing.timing import TimingContext
from wingman.telemetry.model import FleetSnapshot, StreamHealth


def test_publication_source_is_the_exact_structural_boolean_port():
    assert PublicationSource._is_protocol
    assert {name for name in vars(PublicationSource) if not name.startswith("_")} == {
        "snapshot",
        "is_current",
        "admit_start",
    }
    assert isinstance(PublicationSource.snapshot, property)
    assert PublicationSource.snapshot.fset is None
    assert get_type_hints(PublicationSource.snapshot.fget) == {"return": FleetSnapshot}
    assert get_type_hints(PublicationSource.is_current) == {"return": bool}
    assert get_type_hints(PublicationSource.admit_start) == {
        "validate": Callable[[], None],
        "return": bool,
    }


def test_test_ticket_keeps_snapshot_and_refuses_without_validating_after_revoke():
    snapshot = FleetSnapshot((), StreamHealth("active"), sampled_at_mono=3.0)
    ticket = FakePublicationSource(snapshot)
    source: PublicationSource = ticket
    validated = []
    assert source.snapshot is snapshot
    assert source.is_current() is True
    assert source.admit_start(lambda: validated.append(snapshot)) is True
    ticket.revoke()
    assert source.snapshot is snapshot
    assert source.is_current() is False
    assert source.admit_start(lambda: validated.append(None)) is False
    assert validated == [snapshot]


def test_test_ticket_preserves_validator_exception():
    ticket = FakePublicationSource(FleetSnapshot((), StreamHealth("active")))
    error = ValueError("obsolete prepared association")

    def validate():
        raise error

    with pytest.raises(ValueError) as caught:
        ticket.admit_start(validate)
    assert caught.value is error


def context():
    return TimingContext(
        clock=lambda: 0.0,
        db_continuity_token=object(),
        elapsed_lifetime_token=object(),
    )


def candidate(ctx, exchange):
    a, r, t = exchange
    return ctx._diagnostic_candidate(started_at=a, received_at=r, server_time_ms=t)


def test_construction_requires_explicit_clock_and_both_tokens_without_authenticating():
    parameters = signature(TimingContext).parameters
    assert set(parameters) == {"clock", "db_continuity_token", "elapsed_lifetime_token"}
    assert all(p.kind == Parameter.KEYWORD_ONLY for p in parameters.values())
    assert all(p.default == Parameter.empty for p in parameters.values())

    def unread_clock():
        pytest.fail("construction must not sample or substitute the supplied clock")

    db, elapsed = object(), object()
    ctx = TimingContext(
        clock=unread_clock, db_continuity_token=db, elapsed_lifetime_token=elapsed
    )
    assert ctx._clock is unread_clock
    assert ctx._db_continuity_token is db
    assert ctx._elapsed_lifetime_token is elapsed
    assert ctx._state.anchor is None
    assert ctx._state.exchanges == ()
    assert not ctx._inconsistent


def test_first_exchange_is_detached_until_diagnostic_and_anchor_commit():
    ctx = context()
    before = ctx._state
    prepared = candidate(ctx, (0.0, 0.0, 1000))
    assert prepared is not None
    assert ctx._state is before
    assert ctx._state.anchor is None
    assert prepared.state.lo == Fraction(900)
    assert prepared.state.hi == Fraction(1100)
    assert ctx._commit_diagnostic(prepared) is True
    assert ctx._state is prepared.state
    assert ctx._state.anchor.server_time_ms == 1000
    assert ctx._state.anchor.received_at == Fraction(0)
    assert ctx._state.last_started_at == Fraction(0)
    assert ctx._state.last_received_at == Fraction(0)
    assert ctx._state.last_server_time_ms == 1000


def diagnostic_oracle(exchanges):
    """Independent approved exact-ratio oracle, not a production fallback."""
    ratio = Fraction.from_float
    a, r, _ = exchanges[-1]
    assert 0 <= 1000 * (ratio(r) - ratio(a)) <= 5000
    retained = [
        (a_i, r_i, t_i)
        for a_i, r_i, t_i in exchanges
        if 1000 * (ratio(r) - ratio(a_i)) <= 95000
    ]
    lo = max(t - 1000 * ratio(r_i) - 100 for a_i, r_i, t in retained)
    hi = min(t - 1000 * ratio(a_i) + 100 for a_i, r_i, t in retained)
    return retained, lo, hi


def test_diagnostic_vectors():
    assert diagnostic_oracle([(0.0, 0.0, 1000), (1.0, 1.0, 2200)])[1:] == (1100, 1100)
    assert len(diagnostic_oracle([(0.0, 0.0, 1000), (95.0, 95.0, 96000)])[0]) == 2
    lo, hi = diagnostic_oracle([(0.0, 0.0, 1000), (1.0, 1.0, 2150), (2.0, 2.0, 3300)])[
        1:
    ]
    assert lo > hi  # Adjacent pairs overlap; their common intersection is empty.


def assert_candidate_matches_oracle(prepared, exchanges):
    retained, lo, hi = diagnostic_oracle(exchanges)
    assert prepared is not None
    assert [
        (float(e.started_at), float(e.received_at), e.server_time_ms)
        for e in prepared.state.exchanges
    ] == retained
    assert (prepared.state.lo, prepared.state.hi) == (lo, hi)


@pytest.mark.parametrize(
    "exchanges",
    [
        [(0.0, 0.0, 1000), (1.0, 1.0, 2200)],
        [(0.0, 0.0, 1000), (95.0, 95.0, 96000)],
        [(0.1, 0.2, 1200), (1.1, 1.2, 2200)],
    ],
)
def test_each_detached_candidate_matches_common_intersection(exchanges):
    ctx = context()
    for count, exchange in enumerate(exchanges, 1):
        before = ctx._state
        prepared = candidate(ctx, exchange)
        assert ctx._state is before
        assert_candidate_matches_oracle(prepared, exchanges[:count])
        assert ctx._commit_diagnostic(prepared) is True


def test_nonadjacent_contradiction_latches_without_installing_response():
    ctx = context()
    exchanges = [(0.0, 0.0, 1000), (1.0, 1.0, 2150), (2.0, 2.0, 3300)]
    for count, exchange in enumerate(exchanges[:2], 1):
        prepared = candidate(ctx, exchange)
        assert_candidate_matches_oracle(prepared, exchanges[:count])
        assert ctx._commit_diagnostic(prepared) is True
    before = ctx._state
    assert candidate(ctx, exchanges[-1]) is None
    assert ctx._state is before
    assert ctx._state.anchor.server_time_ms == 2150
    assert ctx._inconsistent
    # Expired constraints are not permission to reset-and-accept a singleton.
    assert candidate(ctx, (1000.0, 1000.0, 1001000)) is None
    assert ctx._state is before


@pytest.mark.parametrize(
    "receipt,retained_count",
    [
        (nextafter(95.0, -inf), 2),
        (95.0, 2),
        (nextafter(95.0, inf), 1),
    ],
)
def test_retention_boundary_uses_exact_binary_ratios(receipt, retained_count):
    ctx = context()
    exchanges = [(0.0, 0.0, 1000), (receipt, receipt, 96000)]
    assert ctx._commit_diagnostic(candidate(ctx, exchanges[0]))
    before = ctx._state
    prepared = candidate(ctx, exchanges[1])
    assert_candidate_matches_oracle(prepared, exchanges)
    assert len(prepared.state.exchanges) == retained_count
    assert ctx._state is before
    assert ctx._commit_diagnostic(prepared)


def test_retention_uses_old_request_start_not_old_receipt():
    ctx = context()
    exchanges = [(0.0, 5.0, 5000), (95.5, 95.5, 95500)]
    assert ctx._commit_diagnostic(candidate(ctx, exchanges[0]))
    before = ctx._state
    prepared = candidate(ctx, exchanges[1])
    assert_candidate_matches_oracle(prepared, exchanges)
    assert len(prepared.state.exchanges) == 1
    assert ctx._state is before


def test_rolling_diagnostic_allows_legal_one_ms_per_second_drift_for_2101_prefixes():
    ctx = context()
    exchanges = []
    for second in range(2101):
        exchange = (float(second), float(second), 100000 + 1001 * second)
        exchanges.append(exchange)
        before = ctx._state
        prepared = candidate(ctx, exchange)
        # The protocol retains request starts no older than 95 seconds. This
        # trace has fixed one-second request-start cadence.
        first_retained = max(0, second - 95)
        expected = exchanges[first_retained:]
        assert_candidate_matches_oracle(prepared, expected)
        assert ctx._state is before
        assert ctx._commit_diagnostic(prepared)
        assert len(ctx._state.exchanges) <= 96
    assert ctx._state.last_server_time_ms == 2202100
    assert not ctx._inconsistent


def test_191_constraints_fit_but_impossible_overflow_refuses_without_eviction():
    ctx = context()
    exchanges = []
    for slot in range(191):
        exchange = (slot / 2, slot / 2, 100000 + slot * 500)
        exchanges.append(exchange)
        prepared = candidate(ctx, exchange)
        assert_candidate_matches_oracle(prepared, exchanges)
        assert ctx._commit_diagnostic(prepared)
    before = ctx._state
    assert len(before.exchanges) == 191
    # Deliberately bypass actual-attempt scheduling: cap is a defensive refusal,
    # never permission to evict a protected constraint on an impossible history.
    assert candidate(ctx, exchanges[-1]) is None
    assert ctx._state is before
    assert ctx._state.exchanges[0].started_at == Fraction(0)


@pytest.mark.parametrize(
    "receipt,accepted",
    [
        (nextafter(5.0, -inf), True),
        (5.0, True),
        (nextafter(5.0, inf), False),
    ],
)
def test_request_elapsed_five_second_boundary(receipt, accepted):
    ctx = context()
    before = ctx._state
    prepared = candidate(ctx, (0.0, receipt, 5000))
    assert (prepared is not None) is accepted
    assert ctx._state is before
    assert ctx._state.anchor is None
    assert not ctx._inconsistent  # Slow alone does not contradict the clock.
    if accepted:
        assert_candidate_matches_oracle(prepared, [(0.0, receipt, 5000)])
        assert ctx._commit_diagnostic(prepared)


def test_elapsed_subtraction_must_not_round_a_slow_response_down_to_five_seconds():
    ctx = context()
    a, r = nextafter(0.5, -inf), 5.5
    assert r - a == 5.0  # Ordinary float subtraction hides this violation.
    before = ctx._state
    assert candidate(ctx, (a, r, 5000)) is None
    assert ctx._state is before
    assert not ctx._inconsistent


def test_slow_response_cannot_prune_history_or_install_anchor_and_does_not_latch():
    ctx = context()
    assert ctx._commit_diagnostic(candidate(ctx, (0.0, 0.0, 1000)))
    before = ctx._state
    assert candidate(ctx, (96.0, nextafter(101.0, inf), 102000)) is None
    assert ctx._state is before
    assert not ctx._inconsistent
    prepared = candidate(ctx, (102.0, 102.0, 103000))
    assert_candidate_matches_oracle(
        prepared, [(0.0, 0.0, 1000), (102.0, 102.0, 103000)]
    )
    assert ctx._commit_diagnostic(prepared)


@pytest.mark.parametrize("a,r", [(nan, 1.0), (0.0, nan), (-inf, 1.0), (0.0, inf)])
def test_nonfinite_local_time_refuses_without_changing_retained_state(a, r):
    ctx = context()
    assert ctx._commit_diagnostic(candidate(ctx, (0.0, 0.0, 1000)))
    before = ctx._state
    assert candidate(ctx, (a, r, 2000)) is None
    assert ctx._state is before


@pytest.mark.parametrize(
    "first,regressing",
    [
        (
            (1.0, 1.0, 2000),
            (0.99, 1.1, 2050),
        ),  # Start goes backward, intersection fits.
        ((0.0, 1.0, 2000), (0.5, 0.99, 2050)),  # Receipt goes backward.
        ((0.0, 1.0, 2000), (0.5, 1.1, 2050)),  # Overlaps the preceding signed return.
        ((1.0, 1.0, 2000), (1.2, 1.1, 2100)),  # Own receipt precedes start.
        (
            (1.0, 1.0, 2000),
            (1.01, 1.01, 1999),
        ),  # DB regression inside a feasible interval.
        (
            (0.0, 0.0, 100000),
            (100.0, 100.0, 99999),
        ),  # Even after every old record expires.
    ],
)
def test_local_and_db_order_regressions_latch_without_partial_commit(first, regressing):
    ctx = context()
    assert ctx._commit_diagnostic(candidate(ctx, first))
    before = ctx._state
    assert candidate(ctx, regressing) is None
    assert ctx._state is before
    assert ctx._inconsistent
    assert candidate(ctx, (1000.0, 1000.0, 1100000)) is None
    assert ctx._state is before


def test_diagnostic_db_and_local_order_allow_equality_independently_of_pacing():
    ctx = context()
    exchange = (1.0, 1.0, 2000)
    assert ctx._commit_diagnostic(candidate(ctx, exchange))
    prepared = candidate(ctx, exchange)
    assert_candidate_matches_oracle(prepared, [exchange, exchange])
    assert ctx._commit_diagnostic(prepared)


def test_discarded_candidate_does_not_prune_or_advance_any_accepted_baseline():
    ctx = context()
    assert ctx._commit_diagnostic(candidate(ctx, (0.0, 0.0, 1000)))
    before = ctx._state
    discarded = candidate(ctx, (96.0, 96.0, 97000))
    assert_candidate_matches_oracle(discarded, [(0.0, 0.0, 1000), (96.0, 96.0, 97000)])
    assert len(discarded.state.exchanges) == 1
    # Another admission check refuses: no commit, including no new anchor.
    assert ctx._state is before
    accepted = candidate(ctx, (1.0, 1.0, 2000))
    assert_candidate_matches_oracle(accepted, [(0.0, 0.0, 1000), (1.0, 1.0, 2000)])
    assert ctx._commit_diagnostic(accepted)
    assert ctx._state.last_server_time_ms == 2000
    assert not ctx._inconsistent


def test_stale_candidate_cannot_roll_back_diagnostic_or_anchor_and_commit_is_one_use():
    ctx = context()
    older = candidate(ctx, (0.0, 0.0, 1000))
    newer = candidate(ctx, (1.0, 1.0, 2000))
    assert ctx._commit_diagnostic(newer)
    before = ctx._state
    assert ctx._commit_diagnostic(older) is False
    assert ctx._state is before
    assert ctx._commit_diagnostic(newer) is False
    assert ctx._state is before


def test_equal_but_foreign_base_cannot_commit_into_another_context():
    ctx, foreign = context(), context()
    assert ctx._state == foreign._state
    prepared = candidate(foreign, (0.0, 0.0, 1000))
    before = ctx._state
    assert ctx._commit_diagnostic(prepared) is False
    assert ctx._state is before


def test_inconsistency_invalidates_already_detached_candidate_commit():
    ctx = context()
    assert ctx._commit_diagnostic(candidate(ctx, (0.0, 0.0, 1000)))
    prepared = candidate(ctx, (1.0, 1.0, 2000))
    assert prepared is not None
    before = ctx._state
    assert candidate(ctx, (2.0, 2.0, 3300)) is None
    assert ctx._inconsistent
    assert ctx._commit_diagnostic(prepared) is False
    assert ctx._state is before


def test_hidden_unsupported_clock_jump_can_pass_the_diagnostic():
    # Suppose actual DB sample instants are 2.5s and 8s, and DB jumps +2000ms
    # between them. That violates the <=100ms operational premise, but the RTT
    # uncertainty hides it. Passing this diagnostic is deliberately NOT proof.
    exchanges = [(0.0, 5.0, 100000), (5.5, 10.5, 107500), (11.0, 11.0, 110500)]
    assert (107500 - 100000) - 1000 * (8.0 - 2.5) == 2000
    ctx = context()
    for count, exchange in enumerate(exchanges, 1):
        prepared = candidate(ctx, exchange)
        assert_candidate_matches_oracle(prepared, exchanges[:count])
        assert ctx._commit_diagnostic(prepared)
    assert not ctx._inconsistent


@pytest.mark.parametrize(
    "operation,failed",
    [
        ("fetch_device", False),
        ("acknowledge_capabilities", False),
        ("read_snapshot", True),
        ("fetch_catalogue", True),
    ],
)
def test_context_retains_the_existing_read_bucket_on_failed_and_discarded_completions(
    operation, failed
):
    ctx = context()
    first_consumer = ctx._scheduler
    assert isinstance(first_consumer, Scheduler)
    assert Fraction(SIGNED_INTERVAL_S) * 1000 == LIMITS["signed_interval_ms"]
    assert ctx._commit_diagnostic(candidate(ctx, (0.0, 0.0, 1000)))
    before = ctx._state
    first_consumer.completed(Work(operation, "old-attempt"), 5.0, failed=failed)
    # No response is installed (failure or obsolete result). A later consumer
    # borrows this same retained scheduler; this is NOT a worker-wiring proof.
    replacement_consumer = ctx._scheduler
    next_read = Work("read_snapshot", "new-read")
    assert replacement_consumer.choose((next_read,), nextafter(5.5, -inf)) is None
    assert replacement_consumer.choose((next_read,), 5.5) is next_read
    assert replacement_consumer is first_consumer
    publication = Work("publish_snapshot", "publication")
    assert replacement_consumer.choose((publication,), 5.0) is publication
    assert ctx._state is before
