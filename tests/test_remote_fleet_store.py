"""Payload-only presentation of actual context-admitted v2 timing values."""

from dataclasses import replace
from fractions import Fraction
from math import inf, nextafter
from uuid import UUID

import pytest

from tests.test_fleetsharing_timing_receiver import accept, context, wire_row
from wingman.fleetsharing.protocol import ObservedRemoteRow
from wingman.ui.remotefleet import RemoteFleetStore


def row(publication=1, **changes):
    """Legacy helper export for still-unmigrated Api tests, NOT used by S3 proofs.

    Preserve their existing DTO/signature failures rather than a new collection
    ImportError. This old constructor does not create valid combat-v2 timing.
    """
    return replace(
        ObservedRemoteRow(
            1,
            "Remote",
            10,
            ("SCRAM/POINT",),
            "live",
            0,
            str(UUID(int=publication, version=4)),
        ),
        **changes,
    )


@pytest.mark.parametrize(
    "age_ms,state", [(2999, "live"), (3000, "stale"), (9999, "stale"), (10000, None)]
)
def test_effective_sample_age_classifies_at_exact_boundaries(age_ms, state):
    ctx = context()
    payload = accept(ctx, 100000, 0.0, 0.02, [wire_row()])
    store = RemoteFleetStore()
    assert store.replace(payload) is None
    now = Fraction(age_ms - 400, 1000)
    rows = store.current(now)
    assert ([row.state for row in rows] or [None]) == [state]
    if rows:
        assert (rows[0].outgoing_dps, rows[0].incoming_dps) == (None, 0)


def test_elapsed_and_callback_delay_do_not_restart_stale_or_expiry_deadlines():
    payload = accept(context(), 100000, 0.0, 1.5, [wire_row(sample=800, activity=800)])
    store = RemoteFleetStore()
    store.replace(payload)  # Neither callback receipt nor page paint is an input.
    assert store.current(Fraction(1999, 1000))[0].state == "live"
    assert store.next_transition(Fraction(1999, 1000)) == 2
    assert store.current(2)[0].state == "stale"
    assert store.next_transition(2) == 9
    assert store.current(9) == ()
    assert store.next_transition(9) is None


def test_nonrepresentable_wakeup_rounds_up_without_rounding_cached_timing():
    payload = accept(context(), 100000, 0.0, 0.0, [wire_row(sample=500, activity=500)])
    store = RemoteFleetStore()
    store.replace(payload)
    # S=-.7, stale at 2.3. Nearest binary float rounds DOWN.
    exact = Fraction(23, 10)
    assert Fraction(2.3) < exact
    wake = store.next_transition(0.0)
    assert type(wake) is float
    assert wake == nextafter(2.3, inf)
    assert store.current(2.3)[0].state == "live"
    assert store.current(exact)[0].state == "stale"
    assert store.current(wake)[0].state == "stale"
    assert payload.rows[0].sampled_at_mono == Fraction(-7, 10)
    assert store.next_transition(wake) > wake


def test_row_and_named_unknown_and_kind_deadlines_transition_independently():
    effects = [
        {
            "kind": "SCRAM",
            "observations": [
                {"name": None, "age_ms": 29000},
                {"name": "A", "age_ms": 28000},
            ],
        },
        {"kind": "POINT", "observations": [{"name": "A", "age_ms": 28500}]},
        {"kind": "NEUT", "observations": [{"name": None, "age_ms": 29500}]},
    ]
    payload = accept(
        context(), 100000, 0.0, 0.0, [wire_row(activity=26000, effects=effects)]
    )
    store = RemoteFleetStore()
    store.replace(payload)

    def displayed(now):
        return [
            (effect.kind, effect.observations)
            for effect in store.current(now)[0].effects
        ]

    assert displayed(0) == [
        ("SCRAM", (None, "A")),
        ("POINT", ("A",)),
        ("NEUT", (None,)),
    ]
    for boundary, expected in [
        (Fraction(3, 10), [("SCRAM", (None, "A")), ("POINT", ("A",))]),
        (Fraction(4, 5), [("SCRAM", ("A",)), ("POINT", ("A",))]),
        (Fraction(13, 10), [("SCRAM", ("A",))]),
        (Fraction(9, 5), []),
    ]:
        wake = store.next_transition(boundary - Fraction(1, 1000))
        assert type(wake) is float
        assert Fraction(wake) >= boundary
        assert Fraction(nextafter(wake, -inf)) < boundary
        assert displayed(boundary) == expected
    assert store.current(Fraction(2599, 1000))[0].state == "live"
    assert store.current(Fraction(13, 5))[0].state == "stale"
    assert store.current(Fraction(3799, 1000))
    assert store.current(Fraction(19, 5)) == ()  # Row ends before numeric transport.
    assert store.next_transition(Fraction(19, 5)) is None


@pytest.mark.parametrize("clear", ["none", "empty", "clear", "expired"])
@pytest.mark.parametrize("publication", [1, 2])
def test_same_origins_never_rejuvenate_after_clear_new_uuid_or_same_context_recovery(
    clear, publication
):
    ctx, store = context(), RemoteFleetStore()
    payload = accept(ctx, 104800, 0.0, 4.8, [wire_row()])
    store.replace(payload)
    if clear == "clear":
        store.clear()
    elif clear == "empty":
        store.replace(accept(ctx, 105500, 5.48, 5.5, []))
    elif clear == "expired":
        assert store.current(10) == ()
    # A replacement borrower retains this exact context, not a session/UUID map.
    same_device_borrower = ctx
    repeated = accept(
        same_device_borrower,
        110100,
        10.08,
        10.1,
        [wire_row(sample=5500, activity=5700, publication=publication)],
    )
    assert repeated.rows[0].sampled_at_mono == payload.rows[0].sampled_at_mono
    assert (
        repeated.rows[0].activity_expires_at_mono
        == payload.rows[0].activity_expires_at_mono
    )
    store.replace(repeated)
    assert store.current(10.1) == ()
    assert store.next_transition(10.1) is None
    assert all("Remote" not in repr(record) for record in ctx._state.receiver.records)


def test_equal_metrics_require_a_genuinely_new_sample_to_refresh_and_empty_withdraws():
    ctx, store = context(), RemoteFleetStore()
    store.replace(accept(ctx, 100000, 0.0, 0.0, [wire_row()]))
    assert store.current(3)[0].state == "stale"
    # Same metrics and even the same UUID: only a NEW original S refreshes.
    store.replace(accept(ctx, 103000, 3.0, 3.0, [wire_row()]))
    assert store.current(3)[0].state == "live"
    store.replace(accept(ctx, 104000, 4.0, 4.0, []))
    assert store.current(4) == ()
    assert store.next_transition(4) is None


def test_store_sorts_current_rows_and_retains_no_old_payloads_on_replacement():
    ctx, store = context(), RemoteFleetStore()
    store.replace(
        accept(
            ctx,
            100000,
            0.0,
            0.0,
            [
                wire_row(character_id=9, publication=9),
                wire_row(character_id=2, publication=2),
            ],
        )
    )
    assert [row.character_id for row in store.current(0)] == [2, 9]
    store.replace(accept(ctx, 100500, 0.5, 0.5, [wire_row(character_id=2)]))
    assert [row.character_id for row in store.current(0.5)] == [2]
    store.clear()
    assert store._rows == ()
    assert store.current(1) == ()
    assert store.next_transition(1) is None
