"""Cadence is enforced by the owner, including the synchronous test seam."""

from dataclasses import replace
from itertools import pairwise

from test_fleetsharing_worker import DEVICE, FakeRelayClient, _worker


def test_consecutive_renewal_and_catalogue_cannot_share_a_read_slot():
    mono = [1000.0]
    calls = []

    class TimedClient(FakeRelayClient):
        def fetch_catalogue(self, **kwargs):
            calls.append(("fetch_catalogue", mono[0], kwargs["revision"]))
            return super().fetch_catalogue(**kwargs)

        def renew_session(self, **kwargs):
            calls.append(("renew_session", mono[0], kwargs["revision"]))
            return super().renew_session(**kwargs)

    client = TimedClient(device=DEVICE)
    worker = _worker(client, clock=lambda: mono[0])
    worker.iterate_once()  # Unknown legacy authority requires device bootstrap.
    worker.iterate_once()  # A same-clock turn cannot consume another read slot.
    mono[0] += 601
    worker.iterate_once()
    for _ in range(8):
        mono[0] += 0.5
        worker.iterate_once()
    assert client.renew_calls and client.fetch_calls
    assert all(b[1] - a[1] >= 0.5 for a, b in pairwise(calls))


def test_scheduler_completion_buckets_and_bounded_control_fairness():
    from wingman.fleetsharing.scheduling import OPERATIONS, Scheduler, Work

    scheduler = Scheduler()
    assert set(OPERATIONS) == {
        "publish_snapshot",
        "fetch_device",
        "acknowledge_capabilities",
        "set_participation",
        "fetch_sources",
        "control_source",
        "fetch_catalogue",
        "fetch_eligibility",
        "read_snapshot",
        "renew_session",
        "begin_pairing",
        "complete_pairing",
        "begin_recovery",
        "complete_recovery",
    }
    ordinary = Work("control_source", "control")
    periodic = Work("read_snapshot", "read", due=0, periodic=True)
    assert scheduler.choose((ordinary, periodic), 10) == ordinary
    scheduler.completed(ordinary, 12)
    assert scheduler.choose((ordinary, periodic), 12.49) is None
    assert scheduler.choose((ordinary, periodic), 12.5) == ordinary
    scheduler.completed(ordinary, 12.5)
    assert scheduler.choose((ordinary, periodic), 13) == periodic
    scheduler.completed(periodic, 13)
    withdrawal = Work("publish_snapshot", "withdraw", priority=0)
    assert scheduler.choose((ordinary, periodic, withdrawal), 13) == withdrawal
    scheduler.completed(withdrawal, 13, failed=True)
    assert scheduler.choose((ordinary,), 13.5) == ordinary
    assert scheduler.choose((withdrawal,), 13.5) is None
    assert scheduler.choose((withdrawal,), 14) == withdrawal
    stop = replace(ordinary, priority=0)
    assert scheduler.choose((stop, periodic), 14) == stop


def test_retiring_command_history_preserves_active_retry_service_and_bucket_deadlines():
    from wingman.fleetsharing.scheduling import Scheduler, Work

    scheduler = Scheduler()
    old = Work("control_source", "source:start:old", periodic=True)
    active = Work("control_source", "source:stop:active", periodic=True)
    for now in (10, 11, 13, 17, 25, 41, 71):
        scheduler.completed(active, now, failed=True)
    scheduler.completed(old, 71.5, failed=True)
    scheduler.retain("source:", {active.key})
    assert old.key not in scheduler.failures
    assert old.key not in scheduler.retry_at
    assert old.key not in scheduler._served
    assert scheduler.retry_at[active.key] == 101
    assert scheduler.failures[active.key] == 6 and scheduler._served[active.key] == 71
    assert scheduler.choose((Work("fetch_device", "device"),), 71.99) is None
    assert scheduler.choose((active,), 100.99) is None
    assert scheduler.choose((active,), 101) == active
