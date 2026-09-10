"""Transient publication age, not a cache of previous remote payloads."""

from dataclasses import replace
from uuid import UUID

import pytest

from wingman.fleetsharing.protocol import MAX_REMOTE_ROWS, ObservedRemoteRow


def row(publication=1, **changes):
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


def store():
    from wingman.ui.remotefleet import RemoteFleetStore

    return RemoteFleetStore()


def test_elapsed_and_callback_delay_make_stale_at_exact_unrounded_boundary():
    s = store()
    assert s.replace((row(age_ms=400),), 100, 1.6)
    assert s.current(100.999)[0].state == "live"
    assert s.next_transition(100.999) == 101
    assert s.current(101)[0].state == "stale"
    assert s.next_transition(101) == 108
    assert s.current(108) == ()
    assert s.next_transition(108) is None


@pytest.mark.parametrize("clear", ["none", "empty", "clear", "expired"])
def test_same_publication_never_rejuvenates_after_payload_clear(clear):
    s = store()
    s.replace((row(age_ms=1000),), 100, 2)
    if clear == "clear":
        s.clear()
    elif clear == "empty":
        s.replace((), 101, 0)
    elif clear == "expired":
        assert s.current(107) == ()
    s.replace((row(age_ms=100),), 107.1, 0.1)
    assert s.current(107.1) == ()
    # History contains only origins/first receipt, never a previous payload.
    assert all("Remote" not in repr(value) for value in s._timing.values())


def test_equal_metrics_with_new_publication_refresh_and_empty_withdraws():
    s = store()
    s.replace((row(),), 100, 0)
    assert s.current(103)[0].state == "stale"
    s.replace((row(2),), 103, 0)
    assert s.current(103)[0].state == "live"
    s.replace((), 104, 0)
    assert s.current(104) == ()


def test_history_lasts_first_receipt_plus_ttl_not_conservative_display_expiry():
    s = store()
    s.replace((row(),), 100, 9)
    assert s.current(101) == ()
    s.replace((row(age_ms=2000),), 102, 0)
    assert s.current(102) == ()  # forgotten at display expiry would resurrect it
    assert len(s._timing) == 1
    s.current(109.999)
    assert len(s._timing) == 1
    s.current(110)
    assert len(s._timing) == 0  # repeats did not move the first-receipt horizon
    # Sampled before the retention horizon, delivered after it: full RTT proves old.
    s.replace((row(age_ms=1000),), 112, 10)
    assert s.current(112) == ()


def test_cap_is_derived_from_ttl_cadence_and_refuses_whole_replacement(monkeypatch):
    import wingman.ui.remotefleet as remote

    assert remote.MAX_TIMING_ENTRIES == 21 * MAX_REMOTE_ROWS
    monkeypatch.setattr(remote, "MAX_TIMING_ENTRIES", 2)
    s = store()
    s.replace((row(),), 100, 0)
    s.replace((row(2),), 100.5, 0)
    assert not s.replace((row(3), row(4, character_id=2)), 101, 0)
    assert [r.character_id for r in s.current(101)] == [1]
    assert len(s._timing) == 2
    s.replace((row(),), 103, 0)
    assert s.current(103)[0].state == "stale"  # protected oldest was not evicted
    assert s.replace((row(3),), 111, 0)
