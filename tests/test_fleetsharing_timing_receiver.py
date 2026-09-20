"""Exact receiver evidence; no telemetry source ticket or live relay required."""

from dataclasses import replace
from fractions import Fraction
from math import inf, nan, nextafter
from uuid import UUID

import pytest

from wingman.fleetsharing.protocol import parse_snapshot
from wingman.fleetsharing.timing import TimingContext


def context():
    return TimingContext(
        clock=lambda: 0.0,
        db_continuity_token=object(),
        elapsed_lifetime_token=object(),
    )


def wire_row(*, sample=200, activity=400, effects=(), publication=1, **changes):
    return {
        "character_id": 1,
        "character_name": "Remote",
        "outgoing_dps": None,
        "incoming_dps": 0,
        "state": "live" if sample < 3000 else "stale",
        "age_ms": sample,
        "activity_age_ms": activity,
        "effects": list(effects),
        "publication_id": str(UUID(int=publication, version=4)),
        **changes,
    }


def snapshot(r_db, rows):
    return parse_snapshot({"protocol": 2, "server_time_ms": r_db, "rows": rows})


def prepare(ctx, r_db, a, r, rows):
    assert ctx._start_snapshot_get(started_at=a)
    return ctx._snapshot_candidate(snapshot(r_db, rows), started_at=a, received_at=r)


def accept(ctx, r_db, a, r, rows):
    prepared = prepare(ctx, r_db, a, r, rows)
    assert prepared is not None
    assert ctx._commit_diagnostic(prepared)
    return ctx._state.receiver.payload


def receiver_origin(origin_ms, records, lifetime_ms):
    """Independent literal covering-interval oracle, deliberately a full scan."""
    covering = [
        Fraction(a) - Fraction(r_db, 1000) - Fraction(1, 5)
        for r_db, a in records
        if r_db - lifetime_ms < origin_ms <= r_db
    ]
    return Fraction(origin_ms, 1000) + min(covering)


def test_bad_interval_does_not_permanently_stale_new_origins():
    records = [(104800, 0.0), (105500, 5.48)]
    new = receiver_origin(105300, records, 10000)
    old = receiver_origin(104600, records, 10000)
    assert abs(float(Fraction(11, 2) - new) - 0.42) < 1e-12
    assert old == Fraction(-2, 5)


def test_first_snapshot_is_detached_and_projects_every_direction_and_effect_exactly():
    ctx = context()
    before = ctx._state
    effects = ({"kind": "SCRAM", "observations": [{"name": "A", "age_ms": 600}]},)
    prepared = prepare(ctx, 100000, 0.0, 0.02, [wire_row(effects=effects)])
    assert ctx._state is before
    assert prepared is not None
    row = prepared.state.receiver.payload.rows[0]
    assert (row.outgoing_dps, row.incoming_dps) == (None, 0)
    assert row.sampled_at_mono == Fraction(-2, 5)
    assert row.activity_expires_at_mono == Fraction(147, 5)
    assert row.effects[0].observations[0].expires_at_mono == Fraction(146, 5)
    assert ctx._commit_diagnostic(prepared)
    assert ctx._state.receiver.last_server_time_ms == 100000
    assert ctx._state.anchor.server_time_ms == 100000
    assert ctx._state is prepared.state
    assert not ctx._commit_diagnostic(prepared)


def test_old_origins_keep_the_bad_bound_while_new_origins_use_the_healthy_suffix():
    ctx = context()
    accept(ctx, 104800, 0.0, 4.8, [wire_row()])
    rows = [
        wire_row(sample=200, activity=500),
        wire_row(sample=900, activity=1500, publication=2, character_id=2),
    ]
    payload = accept(ctx, 105500, 5.48, 5.5, rows)
    records = [(104800, 0.0), (105500, 5.48)]
    for timed, wire in zip(payload.rows, rows, strict=True):
        assert timed.sampled_at_mono == receiver_origin(
            105500 - wire["age_ms"], records, 10000
        )
        assert (
            timed.activity_expires_at_mono
            == receiver_origin(105500 - wire["activity_age_ms"], records, 30000) + 30
        )
    assert payload.rows[1].sampled_at_mono == Fraction(-2, 5)


def test_120_seconds_of_continuous_new_origins_recover_without_a_quiet_reset():
    from wingman.ui.remotefleet import RemoteFleetStore

    ctx, store = context(), RemoteFleetStore()
    records = [(104800, 0.0)]
    accept(ctx, 104800, 0.0, 4.8, [wire_row()])
    for second in range(121):
        q = 5.5 + second
        r_db = 105500 + 1000 * second
        a = q - 0.02
        records.append((r_db, a))
        effects = (
            [
                {
                    "kind": "POINT",
                    "observations": [{"name": "old", "age_ms": r_db - 104000}],
                }
            ]
            if r_db - 104000 < 30000
            else []
        )
        rows = [wire_row(effects=effects, publication=second + 1)]
        if r_db - 104600 < 10000:
            rows.append(
                wire_row(
                    sample=r_db - 104600,
                    activity=r_db - 104000,
                    character_id=2,
                    publication=500,
                )
            )
        payload = accept(ctx, r_db, a, q, rows)
        for timed, wire in zip(payload.rows, rows, strict=True):
            assert timed.sampled_at_mono == receiver_origin(
                r_db - wire["age_ms"], records, 10000
            )
            assert (
                timed.activity_expires_at_mono
                == receiver_origin(r_db - wire["activity_age_ms"], records, 30000) + 30
            )
        if effects:
            assert payload.rows[0].effects[0].observations[0].expires_at_mono == 29
        if len(rows) == 2:
            assert payload.rows[1].sampled_at_mono == Fraction(-2, 5)
        store.replace(payload)
        assert store.current(q)[0].state == "live"
    assert ctx._state.receiver.last_server_time_ms == 225500


@pytest.mark.parametrize("origin", [100000, 100001])
@pytest.mark.parametrize("lifetime", [10000, 30000])
def test_covering_upper_end_is_closed_and_next_origin_escapes_old_record(
    origin, lifetime
):
    ctx = context()
    accept(ctx, 100000, -4.8, 0.0, [])
    age = 105500 - origin
    row = wire_row(sample=age if lifetime == 10000 else 200, activity=age)
    payload = accept(ctx, 105500, 5.48, 5.5, [row])
    timed = payload.rows[0]
    actual = (
        timed.sampled_at_mono
        if lifetime == 10000
        else timed.activity_expires_at_mono - 30
    )
    assert actual == receiver_origin(origin, [(100000, -4.8), (105500, 5.48)], lifetime)


@pytest.mark.parametrize("lifetime", [10000, 30000])
def test_covering_lower_end_is_open_just_inside_is_admitted(lifetime):
    ctx = context()
    accept(ctx, 100000, 0.0, 4.8, [])
    r_db = 100000 + lifetime
    before = ctx._state
    age = lifetime
    invalid = wire_row(sample=age if lifetime == 10000 else 200, activity=age)
    with pytest.raises(ValueError):
        snapshot(r_db, [invalid])
    assert ctx._state is before
    valid = wire_row(sample=age - 1 if lifetime == 10000 else 200, activity=age - 1)
    payload = accept(ctx, r_db, lifetime / 1000, lifetime / 1000 + 0.02, [valid])
    timed = payload.rows[0]
    actual = (
        timed.sampled_at_mono
        if lifetime == 10000
        else timed.activity_expires_at_mono - 30
    )
    assert actual == receiver_origin(
        100001, [(100000, 0.0), (r_db, lifetime / 1000)], lifetime
    )


@pytest.mark.parametrize("advance,retained", [(29999, 2), (30000, 1), (30001, 1)])
def test_receiver_prunes_only_at_authenticated_30_second_db_advance(advance, retained):
    ctx = context()
    accept(ctx, 100000, 0.0, 0.0, [])
    payload = accept(ctx, 100000 + advance, advance / 1000, advance / 1000, [])
    assert payload.rows == ()
    assert len(ctx._state.receiver.records) == retained
    assert ctx._state.receiver.last_server_time_ms == 100000 + advance


def test_device_anchors_and_95_seconds_local_passage_leave_receiver_protection_intact():
    from wingman.ui.remotefleet import RemoteFleetStore

    ctx, store = context(), RemoteFleetStore()
    payload = accept(ctx, 100000, 0.0, 0.0, [wire_row()])
    store.replace(payload)
    receiver = ctx._state.receiver
    assert store.current(96) == ()
    store.clear()
    device = ctx._diagnostic_candidate(
        started_at=96.0, received_at=96.0, server_time_ms=196000
    )
    assert ctx._commit_diagnostic(device)
    assert len(ctx._state.exchanges) == 1
    assert ctx._state.receiver is receiver
    assert receiver.payload is payload
    assert receiver.last_server_time_ms == 100000
    # An empty GET may prune, but only because its authenticated R advances.
    accept(ctx, 196500, 96.5, 96.5, [])
    assert len(ctx._state.receiver.records) == 1
    assert ctx._state.receiver.last_server_time_ms == 196500


def test_71_receiver_records_fit_and_overflow_cannot_commit_diagnostic_or_anchor():
    from wingman.combatprofile import LIMITS

    assert LIMITS["receiver_capacity"] == (30000 + 100 + 5000) // 500 + 1 == 71
    ctx = context()
    accept(ctx, 100000, 0.0, 5.0, [wire_row()])
    # Deliberately seed an impossible retained load to test defensive capacity,
    # not to pretend a legal serialized lane can produce all these duplicates.
    receiver = ctx._state.receiver
    ctx._state = replace(
        ctx._state, receiver=replace(receiver, records=receiver.records * 70)
    )
    accept(ctx, 100500, 5.5, 5.5, [wire_row(publication=2)])
    before = ctx._state
    assert len(before.receiver.records) == 71
    assert len(before.exchanges) == 2
    assert prepare(ctx, 101000, 6.0, 6.0, [wire_row(publication=3)]) is None
    assert ctx._state is before
    assert not ctx._inconsistent
    assert before.receiver.payload.rows[0].sampled_at_mono == receiver_origin(
        100300, [(100000, 0.0), (100500, 5.5)], 10000
    )


def test_continuous_half_second_gets_keep_independent_bounded_histories():
    ctx = context()
    for slot in range(241):
        stamp = slot / 2
        accept(ctx, 100000 + slot * 500, stamp, stamp, [wire_row()])
        assert len(ctx._state.receiver.records) == min(slot + 1, 60)
        assert len(ctx._state.exchanges) == min(slot + 1, 191)
    assert ctx._state.receiver.last_server_time_ms == 220000


def test_diagnostic_overflow_cannot_install_receiver_payload_or_last_r():
    ctx = context()
    accept(ctx, 100000, 0.0, 0.0, [wire_row()])
    ctx._state = replace(ctx._state, exchanges=ctx._state.exchanges * 191)
    before = ctx._state
    assert len(before.receiver.records) == 1
    assert prepare(ctx, 100500, 0.5, 0.5, [wire_row(publication=2)]) is None
    assert ctx._state is before


def test_equal_r_can_be_coherent_but_regression_latches_without_partial_receiver_commit():
    ctx = context()
    accept(ctx, 104800, 0.0, 5.0, [wire_row()])
    accept(ctx, 104800, 5.0, 5.0, [wire_row(publication=2)])
    before = ctx._state
    assert len(before.receiver.records) == 2
    assert prepare(ctx, 104799, 5.5, 5.5, []) is None
    assert ctx._state is before
    assert ctx._inconsistent
    assert prepare(ctx, 1100000, 1000.0, 1000.0, []) is None
    assert ctx._state is before


def test_discarded_snapshot_and_stale_candidate_cannot_install_any_partial_state():
    ctx = context()
    accept(ctx, 100000, 0.0, 0.0, [wire_row()])
    before = ctx._state
    obsolete = prepare(ctx, 196000, 96.0, 96.0, [])
    assert len(obsolete.state.receiver.records) == 1
    assert ctx._state is before
    device = ctx._diagnostic_candidate(
        started_at=96.5, received_at=96.5, server_time_ms=196500
    )
    assert ctx._commit_diagnostic(device)
    committed = ctx._state
    assert not ctx._commit_diagnostic(obsolete)
    assert ctx._state is committed
    assert ctx._state.receiver is before.receiver


@pytest.mark.parametrize("outcome", ["failed", "malformed", "slow", "obsolete"])
def test_actual_get_start_floor_is_retained_and_consumed_by_every_attempt(outcome):
    ctx = context()
    before = ctx._state
    assert ctx._start_snapshot_get(started_at=0.0)
    if outcome == "malformed":
        with pytest.raises(ValueError):
            snapshot(100000, [wire_row(sample=10000, activity=10000)])
    elif outcome == "slow":
        assert (
            ctx._snapshot_candidate(
                snapshot(105000, []), started_at=0.0, received_at=nextafter(5.0, inf)
            )
            is None
        )
    elif outcome == "obsolete":
        assert (
            ctx._snapshot_candidate(
                snapshot(100000, []), started_at=0.0, received_at=0.02
            )
            is not None
        )
        # Deliberately discard it, as a final outer authority check would.
    assert ctx._state is before
    replacement_borrower = ctx
    assert not replacement_borrower._start_snapshot_get(started_at=nextafter(0.5, -inf))
    assert replacement_borrower._start_snapshot_get(started_at=0.5)
    assert ctx._state is before


def test_get_start_spacing_does_not_subtract_floats_before_comparison():
    ctx = context()
    assert 0.6 - 0.1 == 0.5
    assert Fraction(0.6) - Fraction(0.1) < Fraction(1, 2)
    assert ctx._start_snapshot_get(started_at=0.1)
    assert not ctx._start_snapshot_get(started_at=0.6)
    assert ctx._start_snapshot_get(started_at=nextafter(0.6, inf))


@pytest.mark.parametrize("stamp", [nan, inf, -inf])
def test_nonfinite_start_cannot_install_or_release_actual_attempt_floor(stamp):
    ctx = context()
    assert ctx._start_snapshot_get(started_at=0.0)
    assert not ctx._start_snapshot_get(started_at=stamp)
    assert not ctx._start_snapshot_get(started_at=0.49)
    assert ctx._start_snapshot_get(started_at=0.5)


def test_response_needs_its_exact_actual_start_not_a_source_ticket_or_reconstructed_elapsed():
    ctx = context()
    response = snapshot(100500, [])
    before = ctx._state
    assert ctx._snapshot_candidate(response, started_at=0.0, received_at=0.02) is None
    assert ctx._start_snapshot_get(started_at=0.0)
    assert ctx._start_snapshot_get(started_at=0.5)
    assert ctx._snapshot_candidate(response, started_at=0.0, received_at=0.52) is None
    prepared = ctx._snapshot_candidate(response, started_at=0.5, received_at=0.52)
    assert prepared is not None
    assert ctx._snapshot_candidate(response, started_at=0.5, received_at=0.52) is None
    assert ctx._state is before
    assert ctx._commit_diagnostic(prepared)


@pytest.mark.parametrize(
    "receipt,accepted",
    [(nextafter(5.0, -inf), True), (5.0, True), (nextafter(5.0, inf), False)],
)
def test_snapshot_elapsed_boundary_is_exact_and_refusal_is_atomic(receipt, accepted):
    ctx = context()
    before = ctx._state
    prepared = prepare(ctx, 105000, 0.0, receipt, [wire_row()])
    assert (prepared is not None) is accepted
    assert ctx._state is before
    assert not ctx._inconsistent


def test_true_history_loss_clears_payload_anchor_and_pending_work_but_not_baselines_or_pacing():
    ctx = context()
    accept(ctx, 100000, 0.0, 0.0, [wire_row()])
    pending = prepare(ctx, 100500, 0.5, 0.5, [wire_row()])
    before = ctx._state
    ctx._receiver_lost_history()
    assert ctx._state.anchor is None
    assert ctx._state.exchanges is before.exchanges
    assert ctx._state.last_server_time_ms == 100000
    assert ctx._state.receiver.last_server_time_ms == 100000
    assert ctx._state.receiver.records == ()
    assert ctx._state.receiver.payload is None
    assert not ctx._commit_diagnostic(pending)
    assert not ctx._start_snapshot_get(started_at=nextafter(1.0, -inf))


@pytest.mark.parametrize(
    "advance,ready", [(29999, False), (30000, True), (30001, True)]
)
def test_lost_history_waits_for_a_later_get_at_exact_fixed_r0_plus_30s(advance, ready):
    ctx = context()
    accept(ctx, 100000, 0.0, 0.0, [wire_row()])
    ctx._receiver_lost_history()
    assert accept(ctx, 101000, 1.0, 1.0, [wire_row()]) is None
    payload = accept(
        ctx, 101000 + advance, 1.0 + advance / 1000, 1.0 + advance / 1000, [wire_row()]
    )
    assert (payload is not None) is ready
    assert ctx._state.receiver.recovery_r0 == 101000
    assert ctx._state.receiver.recovering is (not ready)


def test_intervening_gets_empty_responses_device_anchors_and_repeated_loss_do_not_move_r0():
    ctx = context()
    ctx._receiver_lost_history()
    # Slow is ineligible evidence and cannot establish a recovery barrier.
    assert prepare(ctx, 105000, 0.0, 5.001, []) is None
    assert ctx._state.receiver.recovery_r0 is None
    # A detached/obsolete first response cannot establish it either.
    discarded = prepare(ctx, 105500, 5.5, 5.5, [])
    assert discarded.state.receiver.recovery_r0 == 105500
    assert ctx._state.receiver.recovery_r0 is None
    assert accept(ctx, 106000, 6.0, 6.0, []) is None
    for second in (7, 10, 20, 35):
        assert (
            accept(
                ctx, 100000 + second * 1000, float(second), float(second), [wire_row()]
            )
            is None
        )
        assert ctx._state.receiver.recovery_r0 == 106000
    before = ctx._state
    ctx._receiver_lost_history()  # Idempotent while already recovering.
    assert ctx._state is before
    device = ctx._diagnostic_candidate(
        started_at=35.5, received_at=35.5, server_time_ms=135500
    )
    assert ctx._commit_diagnostic(device)
    assert ctx._state.receiver is before.receiver
    assert accept(ctx, 136000, 36.0, 36.0, [wire_row()]) is not None
    assert ctx._state.receiver.recovery_r0 == 106000
    assert not ctx._state.receiver.recovering


def test_loss_hooks_preserve_publisher_pins_and_do_not_unlatch_clock_contradiction():
    from tests.fleetsharing_timing_helpers import FakePublicationSource
    from wingman.fleetsharing.model import CatalogueCharacter, FleetCatalogue
    from wingman.telemetry.model import (
        CombatActivity,
        EffectObservation,
        FleetRow,
        FleetSnapshot,
        StreamHealth,
    )

    clock = [0.0]
    ctx = TimingContext(
        clock=lambda: clock[0],
        db_continuity_token=object(),
        elapsed_lifetime_token=object(),
    )
    accept(ctx, 100000, clock[0], clock[0], [wire_row()])
    # The fake supplies local publisher authority only; receiver methods never
    # consume it. Populate real sample/row/effect pins rather than an empty map.
    source = FakePublicationSource(
        FleetSnapshot(
            (
                FleetRow(
                    "Alice",
                    12,
                    incoming_dps=34,
                    combat=CombatActivity(
                        30.0,
                        (UUID(int=1), 2),
                        (EffectObservation("SCRAM", 29.5, (UUID(int=1), 1), "A"),),
                    ),
                ),
            ),
            StreamHealth("active"),
            sampled_at_mono=clock[0],
        )
    )
    publication = ctx._stage_publication(
        source,
        FleetCatalogue(1, (CatalogueCharacter(42, "Alice"),)),
        eligible_character_ids=frozenset({42}),
    )
    assert publication is not None
    assert len(publication.rows) == 1
    assert len(publication.pins) == len(ctx._publisher.associations) == 3
    assert len(ctx._state.receiver.records) == 1
    pins, scheduler = ctx._publisher, ctx._scheduler
    assert all(pins.associations[pin.evidence.key] is pin for pin in publication.pins)

    source.revoke()
    assert source.is_current() is False
    clock[0] = 0.5
    remote = accept(ctx, 100500, clock[0], clock[0], [wire_row()])
    assert remote is not None and len(remote.rows) == 1
    assert len(ctx._state.receiver.records) == 2
    assert ctx._publisher is pins

    clock[0] = 1.0
    assert prepare(ctx, 102000, clock[0], clock[0], []) is None
    assert ctx._inconsistent
    ctx._publisher_lost_continuity(cutoff=clock[0])
    ctx._receiver_lost_history()
    assert ctx._publisher is pins
    assert all(pins.associations[pin.evidence.key] is pin for pin in publication.pins)
    assert ctx._scheduler is scheduler
    assert ctx._publisher_cutoff == 1
    assert ctx._state.anchor is None
    assert ctx._state.receiver.payload is None
    before = ctx._state
    clock[0] = 100.0
    assert prepare(ctx, 200000, clock[0], clock[0], []) is None
    assert ctx._state is before
    assert ctx._inconsistent
    assert ctx._state.receiver.recovery_r0 is None


@pytest.mark.parametrize(
    "full_return,admitted", [(7.0, True), (nextafter(7.0, inf), False)]
)
def test_real_signed_client_start_is_after_signing_and_elapsed_includes_full_return(
    monkeypatch, full_return, admitted
):
    import json

    from tests.test_fleetsharing_client import (
        ORIGIN,
        Response,
        auth,
        framing_headers,
        request_binding,
        verify_signed,
    )
    from wingman.fleetsharing import client as client_mod
    from wingman.fleetsharing.client import FleetRelayClient
    from wingman.fleetsharing.scheduling import Work
    from wingman.ui.remotefleet import RemoteFleetStore

    now = [0.0]
    ctx = TimingContext(
        clock=lambda: now[0],
        db_continuity_token=object(),
        elapsed_lifetime_token=object(),
    )
    real_sign, real_decode, real_parse = (
        client_mod.crypto.sign_request,
        client_mod._decode_response,
        client_mod.protocol.parse_snapshot,
    )
    phases = []

    def sign(*args):
        signed = real_sign(*args)
        now[0] = 2.0  # Key/signing preparation is NOT part of request elapsed.
        phases.append("signed")
        return signed

    class TimedResponse(Response):
        def read(self, amount=-1):
            raw = super().read(amount)
            now[0] = 6.5
            phases.append("body")
            return raw

    def decode(raw):
        value = real_decode(raw)
        now[0] = 6.75
        phases.append("decoded")
        return value

    def parse(value):
        parsed = real_parse(value)
        now[0] = full_return
        phases.append("validated")
        return parsed

    def transport(request, timeout):
        assert timeout == 5.0
        verify_signed(request, method="GET", path="snapshot", revision=5)
        phases.append("http")
        assert now[0] == 6.0
        return TimedResponse(
            json.dumps(
                {"protocol": 2, "server_time_ms": 106500, "rows": [wire_row()]}
            ).encode(),
            framing_headers(request_binding(request)),
        )

    monkeypatch.setattr(client_mod.crypto, "sign_request", sign)
    monkeypatch.setattr(client_mod, "_decode_response", decode)
    monkeypatch.setattr(client_mod.protocol, "parse_snapshot", parse)
    starts = []

    def before_send():
        starts.append(ctx._clock())
        assert ctx._start_snapshot_get(started_at=starts[-1])
        phases.append("start")
        now[0] = 6.0  # A pause AFTER logical start still counts toward elapsed.

    client = FleetRelayClient(ORIGIN, transport=transport)
    result = client.read_snapshot(**auth(), before_send=before_send)
    received = ctx._clock()  # After decoding AND closed whole-payload validation.
    work = Work("read_snapshot", "first")
    ctx._scheduler.completed(work, received)
    assert phases == ["signed", "start", "http", "body", "decoded", "validated"]
    assert starts == [2.0]
    assert received == full_return
    before = ctx._state
    prepared = ctx._snapshot_candidate(
        result, started_at=starts[0], received_at=received
    )
    assert (prepared is not None) is admitted
    assert ctx._state is before
    if admitted:
        assert ctx._commit_diagnostic(prepared)
        payload = ctx._state.receiver.payload
        assert (
            payload.rows[0].sampled_at_mono
            == receiver_origin(106300, [(106500, 2.0)], 10000)
            == Fraction(8, 5)
        )
        assert ctx._state.anchor.received_at == Fraction(full_return)
        store = RemoteFleetStore()
        store.replace(payload)
        assert store.current(7.0)[0].state == "stale"
    else:
        assert ctx._state.anchor is None
        assert ctx._state.receiver.payload is None
    borrowed_scheduler = ctx._scheduler
    next_read = Work("fetch_device", "next")
    assert (
        borrowed_scheduler.choose((next_read,), nextafter(received + 0.5, -inf)) is None
    )
    assert borrowed_scheduler.choose((next_read,), received + 0.5) is next_read


@pytest.mark.parametrize("outcome", ["bad_binding", "malformed", "network", "obsolete"])
def test_real_client_failed_or_obsolete_get_preserves_timing_but_spends_both_cadences(
    outcome,
):
    import json

    from tests.test_fleetsharing_client import (
        ORIGIN,
        Response,
        auth,
        framing_headers,
        request_binding,
    )
    from wingman.fleetsharing.client import FleetRelayClient, FleetRelayError
    from wingman.fleetsharing.scheduling import Work

    now = [1.0]
    ctx = TimingContext(
        clock=lambda: now[0],
        db_continuity_token=object(),
        elapsed_lifetime_token=object(),
    )
    accept(ctx, 100000, 0.0, 0.0, [wire_row()])
    before = ctx._state
    starts = []

    def before_send():
        starts.append(ctx._clock())
        assert ctx._start_snapshot_get(started_at=starts[-1])

    def transport(request, timeout):
        now[0] = 1.25
        if outcome == "network":
            raise OSError("disconnected")
        rows = [wire_row(outgoing_dps=True)] if outcome == "malformed" else [wire_row()]
        binding = "0" * 64 if outcome == "bad_binding" else request_binding(request)
        return Response(
            json.dumps(
                {"protocol": 2, "server_time_ms": 101000, "rows": rows}
            ).encode(),
            framing_headers(binding),
        )

    client = FleetRelayClient(ORIGIN, transport=transport)
    if outcome == "obsolete":
        result = client.read_snapshot(**auth(), before_send=before_send)
        prepared = ctx._snapshot_candidate(
            result, started_at=starts[0], received_at=ctx._clock()
        )
        assert prepared is not None  # Outer fence discards; no commit.
    else:
        with pytest.raises(FleetRelayError) as caught:
            client.read_snapshot(**auth(), before_send=before_send)
        expected = "transport_error" if outcome == "network" else "malformed_response"
        assert caught.value.code == expected
    ctx._scheduler.completed(
        Work("read_snapshot", "old"), ctx._clock(), failed=outcome != "obsolete"
    )
    assert ctx._state is before
    assert not ctx._start_snapshot_get(started_at=nextafter(1.5, -inf))
    assert ctx._start_snapshot_get(started_at=1.5)
    new_read = Work("read_snapshot", "new")
    assert ctx._scheduler.choose((new_read,), nextafter(1.75, -inf)) is None
    assert ctx._scheduler.choose((new_read,), 1.75) is new_read
