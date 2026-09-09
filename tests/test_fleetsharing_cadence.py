"""Virtual waits drive the REAL owner loop, not ideal-time iterate_once calls.

The relay is the existing completion-cadence/CAS fake. Publisher and receiver
run independently against one immutable publication trace; no receiver request
changes publication timing. Only Event waiting, monotonic time and HTTP latency
are virtual. No thread sleeps, sockets, provider state or wall-clock deadlines.
"""

import heapq
import threading
from dataclasses import replace
from datetime import timedelta
from itertools import pairwise
from uuid import UUID

import pytest
from test_fleetsharing_worker import (
    DEVICE,
    NOW,
    OPERATION_BUCKETS,
    PAIRED_STATE,
    FakeRelayClient,
    _InMemoryStateStore,
    _snapshot,
    _worker,
)
from test_fleetsharing_worker import UUID as SOURCE_ID

from wingman.fleetsharing import protocol as p
from wingman.fleetsharing.client import FleetRelayError
from wingman.ui.remotefleet import RemoteFleetStore


class VirtualWait:
    def __init__(self, start, end):
        self.now = start
        self.end = end
        self.stop = threading.Event()
        self.signalled = False
        self.events = []
        self.sequence = 0
        self.waits = []

    def at(self, when, callback):
        self.sequence += 1
        heapq.heappush(self.events, (when, self.sequence, callback))

    def set(self):
        self.signalled = True

    def clear(self):
        self.signalled = False

    def advance(self, until, *, interruptible=False):
        while self.events and self.events[0][0] <= until:
            when, _, callback = heapq.heappop(self.events)
            self.now = when
            callback()
            if interruptible and self.signalled:
                return
        self.now = until
        if self.now >= self.end:
            self.stop.set()

    def wait(self, timeout):
        self.waits.append((self.now, timeout))
        assert len(self.waits) < 10000, "owner spun without advancing virtual time"
        if not self.signalled:
            self.advance(min(self.now + timeout, self.end), interruptible=True)
        return self.signalled


class TimedRelay(FakeRelayClient):
    def __init__(self, timeline, store, latency, publications):
        super().__init__(device=DEVICE)
        self.source_views[SOURCE_ID] = p.SourceView(
            SOURCE_ID, 1, 1, "active", None, None
        )
        self.timeline = timeline
        self.store = store
        self.publications = publications
        self.published = []
        self.delay = latency
        self.latency = lambda: timeline.advance(timeline.now + self.delay)

    def _call(self, operation, args, apply):
        if "revision" in args:
            saved = self.store.load()
            assert (saved.last_revision, saved.session_id) == (
                args["revision"],
                args["session_id"],
            ), "attempt must be saved before I/O"
        return super()._call(operation, args, apply)

    def publish_snapshot(self, **args):
        # The fake applies the publication before waiting for its response.
        # Server age begins there, NOT at response/owner completion.
        published = self.timeline.now
        result = super().publish_snapshot(**args)
        self.published.append((published, args["rows"]))
        return result

    def read_snapshot(self, **args):
        # Sample before full response latency, as the real server may do. A
        # repeat gets the SAME publication ID and advancing server age.
        available = [
            (i, t, rows)
            for i, (t, rows) in enumerate(self.publications, 1)
            if t <= self.timeline.now
        ]
        self.remote = ()
        if available:
            i, published, rows = available[-1]
            age_ms = int((self.timeline.now - published) * 1000)
            if age_ms < 10000:
                self.remote = tuple(
                    p.ObservedRemoteRow(
                        r.character_id,
                        "Alice",
                        r.dps,
                        r.ewar,
                        "live" if age_ms < 3000 else "stale",
                        age_ms,
                        str(UUID(int=i, version=4)),
                    )
                    for r in rows
                )
        return super().read_snapshot(**args)


def run_owner(
    *,
    publications=(),
    publisher=False,
    phase=0,
    latency=0.08,
    watch=False,
    duration=120,
    configure=lambda *_: None,
    telemetry_until=None,
):
    timeline = VirtualWait(1000 + phase, 1000 + duration)
    store = _InMemoryStateStore(PAIRED_STATE)
    client = TimedRelay(timeline, store, latency, publications)
    worker = _worker(
        client,
        store=store,
        clock=lambda: timeline.now,
        utc_clock=lambda: NOW + timedelta(seconds=timeline.now - 1000),
    )
    worker._pending = timeline
    worker.set_source_watch(watch)
    display = RemoteFleetStore()
    samples = []
    events = []
    received_rows = False

    def receive(event):
        nonlocal received_rows
        events.append(event)
        received_rows |= bool(event.rows)
        if event.kind == "clear":
            display.clear()
        else:
            assert display.replace(
                event.rows, event.receipt_monotonic, event.request_elapsed
            )

    worker.subscribe_remote(receive)
    if publisher:
        # Sparse, unchanged local metrics from the coordinator's 1s idle cadence.
        for second in range(duration if telemetry_until is None else telemetry_until):
            timeline.at(1000 + phase + second, lambda: worker.submit(_snapshot(42)))
    for tick in range(duration * 20):
        when = 1000 + tick / 20
        if when >= timeline.now:
            timeline.at(
                when,
                lambda: (
                    samples.append(
                        (
                            timeline.now,
                            tuple(row.state for row in display.current(timeline.now)),
                        )
                    )
                    if received_rows
                    else None
                ),
            )
    configure(worker, client, timeline)
    try:
        worker._run(timeline.stop)
    finally:
        assert worker.stop()
    assert client.cadence_refusals == 0
    assert worker.status().detail is None
    for bucket in ("read", "publication"):
        attempts = [
            i
            for i, (op, _, _) in enumerate(client.calls)
            if OPERATION_BUCKETS[op] == bucket
        ]
        assert all(
            client.calls[b][1] >= client.completed[a][1] + 0.5
            for a, b in pairwise(attempts)
        )
    return client, samples, timeline, events


def test_due_independent_bucket_does_not_wait_for_post_operation_poll():
    client, _, _, _ = run_owner(publisher=True, duration=8)
    first_publish = next(
        i for i, call in enumerate(client.calls) if call[0] == "publish_snapshot"
    )
    previous_end = client.completed[first_publish - 1][1]
    assert client.calls[first_publish][1] == pytest.approx(previous_end), (
        "eligibility completed with publication ready, but owner slept"
    )


def test_publication_latency_does_not_shift_already_scheduled_read_deadline():
    client, _, _, _ = run_owner(publisher=True, duration=8)
    eligibility = next(
        i for i, call in enumerate(client.calls) if call[0] == "fetch_eligibility"
    )
    read = next(
        call for call in client.calls[eligibility + 1 :] if call[0] == "read_snapshot"
    )
    assert read[1] == pytest.approx(client.completed[eligibility][1] + 0.5)


def test_future_heartbeat_deadline_is_not_rounded_to_idle_poll():
    def quiet_metadata(worker, client, timeline):
        def defer():
            for key in worker._due:
                worker._due[key] = timeline.end

        timeline.at(1003, defer)

    client, _, _, _ = run_owner(publisher=True, duration=8, configure=quiet_metadata)
    first, second = client.published[:2]
    # No competing I/O: unchanged rows are due one second after completion,
    # followed by the full 80ms response. The 500ms idle poll adds no rounding.
    assert second[0] - first[0] == pytest.approx(1.08)


@pytest.mark.parametrize("phase", [0, 0.2, 0.5, 0.9])
@pytest.mark.parametrize("watch", [False, True])
@pytest.mark.parametrize("latency", [0.025, 0.08, 0.12])
def test_healthy_sparse_publication_stays_live_in_quiet_receiver(phase, watch, latency):
    publisher, _, _, _ = run_owner(publisher=True, watch=watch, latency=latency)
    receiver, samples, _, _ = run_owner(
        publications=publisher.published, phase=phase, latency=latency
    )
    assert publisher.publish_calls and receiver.calls and samples
    bad = [(round(t - 1000, 3), states) for t, states in samples if states != ("live",)]
    assert not bad, ("healthy remote continuity", bad[:12])


def simultaneous_metadata(worker, client, timeline):
    def due():
        # Isolate service competition, without changing cadence or choosing work.
        for key in worker._due:
            worker._due[key] = timeline.now
        worker._renew_at = timeline.now

    timeline.at(1030, due)


@pytest.mark.parametrize("phase", [0, 0.2, 0.5, 0.9])
@pytest.mark.parametrize("latency", [0.025, 0.08, 0.12])
def test_source_watch_and_simultaneous_metadata_renewal_do_not_starve_read(
    phase, latency
):
    publisher, _, _, _ = run_owner(
        publisher=True, watch=True, latency=latency, configure=simultaneous_metadata
    )
    receiver, samples, _, _ = run_owner(
        publications=publisher.published,
        phase=phase,
        watch=True,
        latency=latency,
        configure=simultaneous_metadata,
    )
    for client in (publisher, receiver):
        # One renewal plus four metadata classes, interleaved with snapshot
        # reads: all must fit within ten read-bucket admissions, not a relaxed
        # freshness timer. Include an in-flight admission crossing the due time.
        admissions = [
            op
            for op, end in client.completed
            if end >= 1030 and OPERATION_BUCKETS[op] == "read"
        ]
        serviced = set(admissions[:10])
        assert {
            "fetch_device",
            "fetch_sources",
            "fetch_eligibility",
            "fetch_catalogue",
            "renew_session",
            "read_snapshot",
        } <= serviced
    bad = [(round(t - 1000, 3), states) for t, states in samples if states != ("live",)]
    assert samples and not bad, ("metadata competition", bad[:12])


@pytest.mark.parametrize("latency, expected", [(3.2, ("stale",)), (11, ())])
def test_full_delayed_response_is_honestly_stale_or_expired(latency, expected):
    publisher, _, _, _ = run_owner(publisher=True, duration=60)

    def delay_reads(worker, client, timeline):
        def response():
            delay = (
                latency
                if (timeline.now >= 1020 and client.calls[-1][0] == "read_snapshot")
                else 0.08
            )
            timeline.advance(timeline.now + delay)

        client.latency = response

    _, samples, _, events = run_owner(
        publications=publisher.published, duration=60, configure=delay_reads
    )
    delayed = [e for e in events if e.kind == "replace" and e.request_elapsed >= 3]
    assert delayed and all(e.request_elapsed == pytest.approx(latency) for e in delayed)
    # Even while newer publications exist on the relay, the in-flight response
    # cannot be restamped as fresh or rejuvenated by faster future scheduling.
    assert all(states == expected for t, states in samples if t >= 1035)


def test_rate_limit_backoff_does_not_spin_or_block_other_bucket():
    def refuse(worker, client, timeline):
        def fail():
            client.errors["read_snapshot"] = FleetRelayError(
                429, "rate_limited", "fixture"
            )

        timeline.at(1020, fail)
        timeline.at(1030, client.errors.clear)

    client, _, timeline, _ = run_owner(publisher=True, duration=40, configure=refuse)
    attempts = [
        t for op, t, _ in client.calls if op == "read_snapshot" and 1020 <= t < 1030
    ]
    assert len(attempts) == 4
    assert all(
        b - a >= delay + 0.08 - 1e-9
        for (a, b), delay in zip(pairwise(attempts), (1, 2, 4), strict=True)
    )
    assert sum(1020 <= t < 1030 for t, _ in client.published) >= 7
    assert len(timeline.waits) < 400


def test_off_withdrawal_preempts_busy_metadata_and_then_stays_inert():
    off_at = 1020
    unwrapped_after_off = []

    def off(worker, client, timeline):
        enabled = [True]
        worker._sharing_enabled = lambda: enabled[0]
        original = worker._unwrap_private_key

        def unwrap(blob):
            if timeline.now > off_at + 2:
                unwrapped_after_off.append(timeline.now)
            return original(blob)

        worker._unwrap_private_key = unwrap

        def disable():
            enabled[0] = False
            worker.request_participation(False)

        timeline.at(off_at, disable)

    client, _, timeline, _ = run_owner(
        publisher=True, duration=60, configure=off, telemetry_until=20
    )
    after = [(op, t) for op, t, _ in client.calls if t >= off_at]
    # Off first reconciles device authority; withdrawal uses its independent
    # bucket before the consent write's next read slot. No periodic work wins.
    assert [op for op, _ in after] == [
        "fetch_device",
        "publish_snapshot",
        "set_participation",
    ]
    assert after[-1][1] <= off_at + 1.5
    assert client.withdrawal_completed and not client.device.participation.enabled
    assert not unwrapped_after_off
    assert all(timeout > 0 for t, timeout in timeline.waits if t > off_at + 2)
    assert len([t for t, _ in timeline.waits if t > off_at + 2]) <= 3


def test_stale_input_makes_no_more_publication_attempts():
    client, _, _, _ = run_owner(publisher=True, duration=30, telemetry_until=10)
    assert client.publish_calls
    assert all(t <= 1014.08 for t, _ in client.published)
    assert any(op == "read_snapshot" and t > 1020 for op, t, _ in client.calls)


def test_empty_mailbox_withdraws_once_without_heartbeat_busy_loop():
    def empty(worker, client, timeline):
        timeline.at(1020, lambda: worker.submit(replace(_snapshot(0), rows=())))

    client, _, timeline, _ = run_owner(
        publisher=True, duration=40, telemetry_until=20, configure=empty
    )
    emptied = [(t, rows) for t, rows in client.published if t >= 1020]
    assert len(emptied) == 1 and emptied[0][1] == ()
    assert emptied[0][0] < 1020.7
    assert len(timeline.waits) < 400
