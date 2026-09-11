"""The runtime arbitrates; this host only records calls and supplied outcomes."""

from dataclasses import fields
from threading import Condition, Event, Thread, get_ident

import pytest

from wingman.preview.runtime import HostAck, PreviewRuntime


class RecordingHost:
    def __init__(self):
        self.calls = []
        self.changed = Condition()
        self.callback = None
        self.start_gate = Event()
        self.stop_gate = Event()
        self.start_gate.set()
        self.stop_gate.set()
        self.stop_result = True
        self.is_running = False

    def record(self, name, value=None):
        with self.changed:
            self.calls.append((name, value, get_ident()))
            self.changed.notify_all()

    def wait(self, name, count=1):
        with self.changed:
            assert self.changed.wait_for(
                lambda: sum(c[0] == name for c in self.calls) >= count, 5
            ), self.calls
            return [c for c in self.calls if c[0] == name][count - 1][1]

    def set_lifecycle_callback(self, callback):
        assert self.callback is None
        self.callback = callback

    def set_families(self, demand):
        self.record("families", demand)
        return True

    def close_admission(self):
        self.record("close")

    def start(self):
        assert self.callback is not None
        self.record("start")
        assert self.start_gate.wait(5)
        self.is_running = True

    def stop(self, timeout=5, *, final=False):
        self.record("stop", final)
        assert self.stop_gate.wait(5)
        if self.stop_result:
            self.is_running = False
        return self.stop_result

    def ack(self, outcome, *, pump=1, eve=0, companions=0):
        self.callback(HostAck(pump, eve, companions, outcome))


@pytest.fixture
def owner():
    host = RecordingHost()
    runtime = PreviewRuntime(host)
    yield runtime, host
    host.start_gate.set()
    host.stop_gate.set()
    host.stop_result = True
    host.ack("pump-stopped", pump=runtime.snapshot().pump_epoch)
    assert runtime.shutdown(5)


def observe(runtime, predicate):
    done = Event()
    states = []

    def callback(state):
        states.append(state)
        if predicate(state):
            done.set()

    runtime.set_state_callback(callback)
    if predicate(runtime.snapshot()):
        done.set()
    return done, states


@pytest.mark.parametrize(
    "eve,companions,starts",
    [(False, False, 0), (True, False, 1), (False, True, 1), (True, True, 1)],
)
def test_only_committed_families_or_selection_start_a_pump(
    owner, eve, companions, starts
):
    runtime, host = owner
    runtime.set_eve(eve, 1)
    runtime.set_companions(companions, 1)
    demand = host.wait("families", 2)
    assert (demand.eve, demand.companions) == (eve, companions)
    if starts:
        host.wait("start")
        host.ack("pump-started")
    assert sum(c[0] == "start" for c in host.calls) == starts


def test_ack_is_host_facts_only_and_callback_is_off_pump_outside_lock(owner):
    runtime, host = owner
    assert {f.name for f in fields(HostAck)} == {
        "pump_epoch",
        "eve_epoch",
        "companion_epoch",
        "outcome",
    }
    delivered = Event()
    threads = []

    def callback(state):
        runtime.snapshot()
        threads.append(get_ident())
        if state.eve == "active":
            delivered.set()

    runtime.set_state_callback(callback)
    runtime.set_eve(True, 1)
    host.wait("start")
    host.ack("pump-started")
    host.ack("eve-active", eve=1)
    assert delivered.wait(5)
    assert threads and get_ident() not in threads


def test_family_revision_cannot_overwrite_other_producer_or_replay_stale_demand(owner):
    runtime, host = owner
    runtime.set_eve(True, 10)
    runtime.set_companions(True, 2)
    runtime.set_eve(False, 9)
    runtime.set_companions(False, 1)
    demand = host.wait("families", 2)
    assert demand.eve and demand.companions
    assert demand.revision == 2


def test_opposite_family_producers_merge_even_when_start_is_blocked(owner):
    runtime, host = owner
    host.start_gate.clear()
    runtime.set_eve(True, 1)
    host.wait("start")
    threads = [
        Thread(target=runtime.set_eve, args=(False, 2)),
        Thread(target=runtime.set_companions, args=(True, 1)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)
        assert not thread.is_alive()
    demands = [c[1] for c in host.calls if c[0] == "families"]
    latest = max(demands, key=lambda d: d.revision)
    assert not latest.eve and latest.companions
    assert runtime.snapshot().pump == "starting"
    host.start_gate.set()
    host.ack("pump-started")


def test_last_demand_stop_does_not_hold_owner_lock_and_retains_same_executor(owner):
    runtime, host = owner
    runtime.set_eve(True, 1)
    host.wait("start")
    host.ack("pump-started")
    host.stop_gate.clear()
    runtime.set_eve(False, 2)
    host.wait("stop")
    assert runtime.snapshot().pump == "stopping"
    assert runtime.acquire_selection(42) is None
    runtime.set_companions(True, 1)
    assert runtime.shutdown(0) is False
    assert runtime.acquire_selection(43) is None
    host.stop_gate.set()
    host.ack("pump-stopped", eve=2)
    assert runtime.shutdown(5)
    lifecycle_threads = {c[2] for c in host.calls if c[0] in ("start", "stop")}
    assert len(lifecycle_threads) == 1
    assert sum(c[0] == "start" for c in host.calls) == 1


def test_stop_timeout_waits_for_ack_not_retry_loop_or_replacement(owner):
    runtime, host = owner
    runtime.set_eve(True, 1)
    host.wait("start")
    host.ack("pump-started")
    host.stop_result = False
    runtime.set_eve(False, 2)
    host.wait("stop")
    runtime.set_companions(True, 1)
    done, _ = observe(runtime, lambda s: s.companions == "starting")
    assert done.wait(5)
    assert sum(c[0] == "start" for c in host.calls) == 1
    assert runtime.snapshot().pump == "stopping"
    host.stop_result = True
    host.ack("pump-stopped", eve=2)
    host.wait("start", 2)
    assert runtime.snapshot().pump_epoch == 2


def test_existing_selection_survives_master_off_on_and_stale_release(owner):
    runtime, host = owner
    runtime.set_companions(True, 1)
    host.wait("start")
    host.ack("pump-started")
    host.ack("companions-active", companions=1)
    lease = runtime.acquire_selection(40)
    assert lease is not None and lease.pump_epoch == 1
    assert runtime.acquire_selection(41) is None
    runtime.set_companions(False, 2)
    runtime.set_companions(True, 3)
    assert runtime.snapshot().selection_pending
    runtime.release_selection(type(lease)(99, lease.pump_epoch))
    assert runtime.snapshot().selection_pending
    runtime.release_selection(lease)
    assert not runtime.snapshot().selection_pending


def test_off_master_lease_reserves_actual_prospective_epoch_and_close_revokes(owner):
    runtime, host = owner
    host.start_gate.clear()
    lease = runtime.acquire_selection(7)
    assert lease is not None
    host.wait("start")
    assert runtime.snapshot().pump_epoch == lease.pump_epoch == 1
    assert runtime.snapshot().pump == "starting"
    runtime.close_admission()
    assert not runtime.snapshot().selection_pending
    assert runtime.acquire_selection(8) is None
    host.start_gate.set()
    host.ack("pump-started")
    runtime.release_selection(lease)
    assert not runtime.snapshot().selection_pending


def test_old_pump_and_family_ack_cannot_revive_revoked_family_or_lease(owner):
    runtime, host = owner
    runtime.set_eve(True, 1)
    runtime.set_companions(True, 1)
    host.wait("start")
    host.ack("pump-started")
    host.ack("eve-active", eve=1)
    runtime.set_eve(False, 2)
    runtime.set_eve(True, 3)
    host.ack("eve-active", eve=1)
    assert runtime.snapshot().eve != "active"
    host.ack("eve-stopped", eve=2, companions=0)
    host.ack("companions-active", eve=1, companions=1)
    host.ack("eve-active", eve=3, companions=0)
    assert runtime.snapshot().eve == "active"
    assert runtime.snapshot().companions == "active"
    host.ack("pump-stopped", pump=0)
    assert runtime.snapshot().pump == "active"


def test_failure_retries_only_explicit_unchanged_demand_with_same_owner(owner):
    runtime, host = owner
    runtime.set_eve(True, 1)
    host.wait("start")
    host.ack("pump-failed")
    done, _ = observe(runtime, lambda s: s.pump == "failed")
    assert done.wait(5)
    assert runtime.snapshot().error
    runtime.set_eve(True, 1)
    host.wait("start", 2)
    assert runtime.snapshot().pump_epoch == 2
    host.ack("pump-started", pump=2)
    host.ack("eve-active", pump=2, eve=1)
    assert runtime.snapshot().error is None


def test_coalesced_on_off_during_cleanup_does_not_invent_host_epochs(owner):
    runtime, host = owner
    runtime.set_eve(True, 1)
    runtime.set_companions(True, 1)
    host.wait("start")
    host.ack("pump-started")
    host.ack("eve-active", eve=1)
    runtime.set_eve(False, 2)
    runtime.set_eve(True, 3)
    runtime.set_eve(False, 4)
    runtime.set_eve(True, 5)
    # The host retained one cleanup owner. Coalesced requests never admitted
    # another activation, so the next real active epoch is three, not five.
    host.ack("eve-stopped", eve=2)
    host.ack("eve-active", eve=3)
    assert runtime.snapshot().eve == "active"


def test_failed_pump_cannot_admit_a_lease_for_its_retiring_epoch(owner):
    runtime, host = owner
    runtime.set_companions(True, 1)
    host.wait("start")
    host.stop_gate.clear()
    host.ack("pump-failed")
    host.wait("stop")
    assert runtime.acquire_selection(12) is None


@pytest.mark.parametrize("outcome", ["pump-failed", "pump-stopped"])
def test_pump_failure_revokes_selection_without_reusing_its_epoch(owner, outcome):
    runtime, host = owner
    lease = runtime.acquire_selection(12)
    assert lease is not None
    host.wait("start")
    host.stop_gate.clear()
    host.ack(outcome)
    assert not runtime.snapshot().selection_pending
    assert runtime.acquire_selection(13) is None
    runtime.release_selection(lease)
    runtime.set_companions(True, 1)
    host.wait("stop")
    assert runtime.snapshot().pump_epoch == 1
    assert sum(c[0] == "start" for c in host.calls) == 1
    host.stop_gate.set()
    host.wait("start", 2)
    replacement = runtime.acquire_selection(13)
    assert replacement is not None and replacement.pump_epoch == 2
    host.ack(outcome, pump=1)
    runtime.release_selection(lease)
    assert runtime.snapshot().selection_pending


def test_unavailable_host_never_admits_selection_and_can_close():
    runtime = PreviewRuntime(None)
    assert runtime.acquire_selection(1) is None
    assert runtime.set_eve(True, 1).eve == "failed"
    runtime.close_admission()
    assert runtime.shutdown(0)
