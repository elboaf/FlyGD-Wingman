"""Virtual waits drive the REAL owner loop, not ideal-time iterate_once calls.

Default scheduler scenarios use validated in-memory state. Explicit publisher,
receiver, and JSON representatives retain durable file crossings. Publisher PUTs
use the real signed client; metadata/CAS use the existing time-enforcing server
double. Publisher and receiver run independently against the actual immutable
Request-byte trace; receiver requests cannot change publication timing. Event
waits, monotonic time and HTTP latency are virtual. No thread sleeps, sockets,
provider state or wall-clock deadlines.
"""

import heapq
import json
import math
import threading
from dataclasses import asdict, dataclass, replace
from datetime import timedelta
from fractions import Fraction
from itertools import pairwise
from typing import ClassVar
from uuid import UUID

import pytest
from test_fleetsharing_worker import (
    DEVICE,
    KEY,
    NOW,
    OPERATION_BUCKETS,
    PAIRED_STATE,
    SignedPublicationRelay,
    _date,
    _InMemoryStateStore,
    _worker,
)
from test_fleetsharing_worker import UUID as SOURCE_ID

from tests.fleetsharing_timing_helpers import FakePublicationSource
from tests.test_fleetsharing_client import Response, framing_headers, request_binding
from tests.test_fleetsharing_worker_state4 import FileStore
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing.client import FleetRelayClient, FleetRelayError
from wingman.telemetry.model import (
    CombatActivity,
    FleetRow,
    FleetSnapshot,
    StreamHealth,
)
from wingman.ui.remotefleet import RemoteFleetStore


def durable_cadence_store(path):
    store = FileStore(path)
    store.save(PAIRED_STATE)
    return store


def cadence_source(now, dps=0):
    # Healthy zero/zero through a genuine 30s combat hold. A new event every
    # twenty seconds keeps the long scenario active without renewing old IDs.
    event = 1000 + math.floor((now - 1000) / 20) * 20 if dps == 0 else now
    activity = CombatActivity(event + 30, (UUID(int=900), int((event - 999) * 1000)))
    return FakePublicationSource(
        FleetSnapshot(
            (FleetRow("Alice", dps, incoming_dps=0, combat=activity),),
            StreamHealth("active"),
            sampled_at_mono=now,
        )
    )


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


class TimedRelay(SignedPublicationRelay):
    def __init__(self, timeline, store, latency, publications):
        super().__init__(device=DEVICE, store=store)
        self.source_views[SOURCE_ID] = p.SourceView(
            SOURCE_ID, 1, 1, "active", None, None, None
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

    def read_snapshot(self, **args):
        # Sample before full response latency, as the real server may do. A
        # repeat gets the SAME publication ID and advancing server age.
        available = [
            (i, body)
            for i, (published, body) in enumerate(self.publications, 1)
            if published <= self.timeline.now
        ]
        db_now = DEVICE.server_time_ms + round((self.timeline.now - 1000) * 1000)
        rows = []
        if available:
            i, body = available[-1]
            # The trace contains actual CombatPut values, never an adapter from
            # legacy PublishRow. Its original S/O survive all later GETs.
            age_ms = db_now - body.sampled_at_ms
            if 0 <= age_ms < 10000:
                for number, source in enumerate(body.rows):
                    row = asdict(source)
                    row["activity_age_ms"] += age_ms
                    if row["activity_age_ms"] >= 30000:
                        continue
                    for effect in row["effects"]:
                        for observation in effect["observations"]:
                            observation["age_ms"] += age_ms
                        effect["observations"] = [
                            o for o in effect["observations"] if o["age_ms"] < 30000
                        ]
                    row["effects"] = [e for e in row["effects"] if e["observations"]]
                    row.update(
                        character_name="Alice",
                        state="live" if age_ms < 3000 else "stale",
                        age_ms=age_ms,
                        publication_id=str(UUID(int=i * 32 + number, version=4)),
                    )
                    rows.append(row)
        # JSON round-trip is the actual tuple/list wire boundary, not a legacy DTO shim.
        self.remote = p.parse_snapshot(
            json.loads(
                json.dumps({"protocol": 2, "server_time_ms": db_now, "rows": rows})
            )
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
    state_store=None,
):
    timeline = VirtualWait(1000 + phase, 1000 + duration)
    store = state_store or _InMemoryStateStore(PAIRED_STATE)
    client = TimedRelay(timeline, store, latency, publications)
    if publisher:
        rights = (p.SHARED_CAPABILITY, p.COMBAT_CAPABILITY)
        client.device = replace(
            client.device,
            approved_capabilities=rights,
            session_approved_capabilities=rights,
            acknowledged_capabilities=rights,
        )
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
        received_rows |= event.payload is not None and bool(event.payload.rows)
        if event.kind == "clear":
            display.clear()
        else:
            display.replace(event.payload)

    worker.subscribe_remote(receive)
    if publisher:
        # Test-only original measurements at the modeled 1s cadence, not a
        # production coordinator wrapper or raw-snapshot authority fallback.
        for second in range(duration if telemetry_until is None else telemetry_until):
            timeline.at(
                1000 + phase + second,
                lambda: worker.submit(cadence_source(timeline.now)),
            )
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


def renewed_source_proof(
    *,
    changing=False,
    source_until=None,
    source_period=6,
    source_phase=2,
    clock_skew=0,
):
    def configure(worker, client, timeline):
        original = client.fetch_eligibility
        server_utc = client.utc
        worker._utc_clock = lambda: server_utc() + timedelta(seconds=clock_skew)

        def eligibility(**args):
            started = timeline.now
            result = original(**args)
            if source_until is not None and started >= source_until:
                return replace(result, state="not_verified", characters=())
            expiry = NOW + timedelta(
                seconds=(
                    math.floor((started - 1000 - source_phase) / source_period)
                    * source_period
                    + source_phase
                    + 10
                )
            )
            return replace(
                result,
                characters=tuple(
                    replace(entry, expires_at=_date(expiry))
                    for entry in result.characters
                ),
            )

        client.fetch_eligibility = eligibility
        if changing:
            for second in range(60):
                timeline.at(
                    1000 + second,
                    lambda n=second: worker.submit(
                        cadence_source(timeline.now, 10 + n % 5)
                    ),
                )

    return configure


@pytest.mark.parametrize("changing", [False, True])
@pytest.mark.parametrize("latency", [0.08, 0.2, 0.4, 0.6])
def test_renewed_source_preserves_active_publications(changing, latency):
    client, _, timeline, _ = run_owner(
        publisher=True,
        watch=True,
        latency=latency,
        duration=60,
        configure=renewed_source_proof(changing=changing),
    )
    assert client.published
    assert all(body.rows for _, body in client.published)
    times = [t for t, _ in client.published]
    assert max(b - a for a, b in pairwise(times)) < 3.0
    assert timeline.end - times[-1] < 3.0
    operations = {op for op, _, _ in client.calls}
    assert {"fetch_sources", "fetch_catalogue", "read_snapshot"} <= operations


def test_authoritative_source_loss_still_withdraws_active_local_metrics():
    client, _, _, _ = run_owner(
        publisher=True,
        watch=True,
        latency=0.6,
        duration=60,
        configure=renewed_source_proof(source_until=1030),
    )
    empty = [(t, body) for t, body in client.published if not body.rows]
    assert len(empty) == 1
    assert empty[0][0] >= 1030
    assert all(not body.rows for t, body in client.published if t >= empty[0][0])


@pytest.mark.parametrize("period", [5, 6])
@pytest.mark.parametrize("phase", [0, 2, 4])
@pytest.mark.parametrize("skew", [-0.5, 0.5])
def test_source_phase_and_small_clock_skew_do_not_withdraw(period, phase, skew):
    client, _, timeline, _ = run_owner(
        publisher=True,
        watch=True,
        latency=0.6,
        duration=60,
        configure=renewed_source_proof(
            source_period=period,
            source_phase=phase,
            clock_skew=skew,
        ),
    )
    assert client.published
    assert all(body.rows for _, body in client.published)
    times = [t for t, _ in client.published]
    assert max(b - a for a, b in pairwise(times)) < 10.0
    assert timeline.end - times[-1] < 10.0


def test_publisher_trace_crosses_real_signed_client(monkeypatch, tmp_path):
    reached = []
    original = FleetRelayClient.publish_snapshot

    def observe(self, **args):
        result = original(self, **args)
        reached.append(True)
        return result

    monkeypatch.setattr(FleetRelayClient, "publish_snapshot", observe)
    store = durable_cadence_store(tmp_path / "publisher-trace.json")
    client, _, _, _ = run_owner(
        publisher=True,
        duration=8,
        state_store=store,
    )
    assert client.store is store
    assert reached, "publisher trace never crossed real FleetRelayClient signing/HTTP"
    assert len(reached) == len(client.published) == len(client.signed_publications)
    assert [
        p.parse_combat_put(json.loads(r["request"].data))
        for r in client.signed_publications
    ] == [body for _, body in client.published]
    assert all(
        r["revision"] == int(r["request"].get_header("X-fleet-revision"))
        for r in client.signed_publications
    )


def test_due_independent_bucket_does_not_wait_for_post_operation_poll():
    client, _, _, _ = run_owner(publisher=True, duration=8)
    assert isinstance(client.store, _InMemoryStateStore)
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
def test_healthy_sparse_publication_stays_live_in_quiet_receiver(
    tmp_path, phase, watch, latency
):
    publisher, _, _, _ = run_owner(publisher=True, watch=watch, latency=latency)
    receiver, samples, _, events = run_trace_owner(
        tmp_path,
        publications=actual_publication_trace(publisher.published),
        phase=phase,
        latency=latency,
    )
    assert publisher.publish_calls and receiver.calls and samples
    assert_mixed_trace_bounds(
        publisher, receiver, samples, events, phase=phase, latency=latency, watch=watch
    )


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
    tmp_path, phase, latency
):
    publisher, _, _, _ = run_owner(
        publisher=True, watch=True, latency=latency, configure=simultaneous_metadata
    )
    receiver, samples, _, events = run_trace_owner(
        tmp_path,
        publications=actual_publication_trace(publisher.published),
        phase=phase,
        watch=True,
        latency=latency,
        configure=simultaneous_metadata,
    )
    for client in (publisher, receiver):
        assert_scenario_fairness(client, watch=True)
    assert_mixed_trace_bounds(
        publisher, receiver, samples, events, phase=phase, latency=latency, watch=True
    )


@pytest.mark.parametrize("latency, expected", [(3.2, ("stale",)), (11, ())])
def test_full_delayed_response_is_honestly_stale_or_expired(
    tmp_path, latency, expected
):
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

    receiver, samples, _, events = run_trace_owner(
        tmp_path,
        publications=actual_publication_trace(publisher.published),
        duration=60,
        configure=delay_reads,
    )
    assert_exact_trace(receiver, samples, events)
    delayed = [
        r - a
        for op, a, r, _, _, _ in receiver.raw
        if op == "read_snapshot" and a >= 1020
    ]
    assert delayed and all(span == pytest.approx(latency) for span in delayed)
    # Even while newer publications exist on the relay, the in-flight response
    # cannot be restamped as fresh or rejuvenated by faster future scheduling.
    assert all(states == expected for t, _, states in samples if t >= 1035)


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


@dataclass(frozen=True)
class ExternalPublication:
    """Original external measurements, never produced by worker/timing/projection."""

    released_at: float
    sample_ms: int
    activity_ms: int
    effect_ms: int | None
    outgoing_dps: int | None = 42
    incoming_dps: int | None = 0


def actual_publication_trace(published):
    """Receiver input from actual PUT bytes, never a legacy PublishRow adapter.

    The mixed scenarios publish one Alice row with no effects. Their trace is
    captured by SignedPublicationRelay at real HTTP, not rebuilt from method args.
    """
    assert published
    trace = []
    for released, body in published:
        assert len(body.rows) == 1
        row = body.rows[0]
        assert row.character_id == 1 and not row.effects
        trace.append(
            ExternalPublication(
                released,
                body.sampled_at_ms,
                body.sampled_at_ms - row.activity_age_ms,
                None,
                row.outgoing_dps,
                row.incoming_dps,
            )
        )
    return tuple(trace)


def scripted_combat_trace(duration=120):
    # Independent publisher's 200ms margin is already in S/O. The receiver must
    # add its OWN margin; receipt/UUID changes cannot recreate these origins.
    return tuple(
        ExternalPublication(
            1000 + second,
            DEVICE.server_time_ms + second * 1000 - 200,
            DEVICE.server_time_ms + second * 1000 - 400,
            DEVICE.server_time_ms - 600,
        )
        for second in range(duration)
    )


class TraceRelay:
    """Raw HTTP for current receiver cases; old FakeRelay is not an oracle.

    Virtual time advances only at the explicit post-lock/body barriers, so raw
    transport entry is the real hook start and read completion is full client
    return (decode/DTO validation consume no virtual time). Separate C tests
    explicitly delay the actual decoder. No local publication is simulated.
    """

    ROUTES: ClassVar[dict[tuple[str, str], str]] = {
        ("GET", "device"): "fetch_device",
        ("PUT", "device"): "acknowledge_capabilities",
        ("GET", "snapshot"): "read_snapshot",
        ("GET", "catalogue"): "fetch_catalogue",
        ("GET", "eligibility"): "fetch_eligibility",
        ("GET", "sources"): "fetch_sources",
        ("GET", "automatic-verification"): "fetch_automatic",
        ("PUT", "session"): "renew_session",
    }

    def __init__(self, timeline, store, publications, latency):
        self.timeline, self.store, self.publications = timeline, store, publications
        self.calls, self.completed, self.raw = [], [], []
        self.errors = {}
        self.latency = lambda: timeline.advance(timeline.now + latency)
        self.before_sample = lambda operation: None
        self.eligibility_expiry = lambda sampled: sampled + 10

    def __call__(self, request, timeout):
        operation = self.ROUTES[(request.method, request.full_url.rsplit("/", 1)[-1])]
        a = self.timeline.now
        revision = int(request.get_header("X-fleet-revision"))
        assert self.store.load().last_revision == revision
        self.calls.append((operation, a, revision))
        self.before_sample(operation)
        sampled = self.timeline.now
        db = DEVICE.server_time_ms + int((sampled - 1000) * 1000)
        code = 200
        if operation in self.errors:
            code, error = self.errors[operation]
            body = {"error": error}
        elif operation in ("fetch_device", "acknowledge_capabilities"):
            body = {**asdict(DEVICE), "server_time_ms": db}
        elif operation == "read_snapshot":
            available = [
                (i, publication)
                for i, publication in enumerate(self.publications)
                if publication.released_at <= sampled
            ]
            rows = []
            if available:
                i, publication = available[-1]
                age = db - publication.sample_ms
                if 0 <= age < 10000 and db - publication.activity_ms < 30000:
                    rows.append(
                        {
                            "character_id": 1,
                            "character_name": "Alice",
                            "outgoing_dps": publication.outgoing_dps,
                            "incoming_dps": publication.incoming_dps,
                            "activity_age_ms": db - publication.activity_ms,
                            "effects": [
                                {
                                    "kind": "SCRAM",
                                    "observations": [
                                        {
                                            "name": "A",
                                            "age_ms": db - publication.effect_ms,
                                        }
                                    ],
                                }
                            ]
                            if publication.effect_ms is not None
                            and db - publication.effect_ms < 30000
                            else [],
                            "age_ms": age,
                            "state": "live" if age < 3000 else "stale",
                            "publication_id": str(UUID(int=i + 1, version=4)),
                        }
                    )
            body = {"server_time_ms": db, "rows": rows}
        elif operation == "fetch_catalogue":
            body = {"revision": 1, "characters": []}
        elif operation == "fetch_eligibility":
            body = {
                "participation_generation": 1,
                "state": "ready",
                "characters": [
                    {
                        "character_id": 1,
                        "source_id": SOURCE_ID,
                        "source_generation": 1,
                        "authority_generation": 1,
                        "expires_at": _date(
                            NOW
                            + timedelta(seconds=self.eligibility_expiry(sampled) - 1000)
                        ),
                    }
                ],
            }
        elif operation == "fetch_sources":
            body = {"sources": [], "characters": []}
        elif operation == "fetch_automatic":
            body = {
                "status": {
                    "consent": {
                        "generation": 0,
                        "revision": 0,
                        "enabled": False,
                        "approving_device_id": None,
                        "approved_at": None,
                        "disabled_at": None,
                        "closed_reason": None,
                    },
                    "approver": "none",
                    "readiness": "off",
                    "recovery_action": "none",
                    "retry_at": None,
                    "sources": [],
                }
            }
        else:
            body = {"expires_at": _date(NOW + timedelta(seconds=sampled - 1000 + 1800))}
        raw = json.dumps({"protocol": 2, **body}).encode()
        relay = self

        class MeasuredResponse(Response):
            def read(self, amount=-1):
                result = super().read(amount)
                relay.latency()
                r = relay.timeline.now
                relay.completed.append((operation, r))
                relay.raw.append((operation, a, r, sampled, code, raw))
                return result

        return MeasuredResponse(raw, framing_headers(request_binding(request)), code)


def run_trace_owner(
    tmp_path,
    *,
    phase=0,
    watch=False,
    latency=0.08,
    duration=120,
    configure=lambda *_: None,
    publications=None,
    state_store=None,
):
    timeline = VirtualWait(1000 + phase, 1000 + duration)
    store = state_store or _InMemoryStateStore(PAIRED_STATE)
    relay = TraceRelay(
        timeline,
        store,
        scripted_combat_trace(duration) if publications is None else publications,
        latency,
    )
    client = FleetRelayClient("https://relay.test", transport=relay)
    worker = _worker(
        client,
        store=store,
        clock=lambda: timeline.now,
        utc_clock=lambda: NOW + timedelta(seconds=timeline.now - 1000),
    )
    worker._pending = timeline
    worker.set_source_watch(watch)
    display = RemoteFleetStore()  # Actual consumer ONLY, never expected values.
    samples, events = [], []

    def receive(event):
        events.append((len(relay.raw), event))
        if event.kind == "clear":
            display.clear()
        else:
            display.replace(event.payload)

    worker.subscribe_remote(receive)
    for tick in range(duration * 20):
        when = 1000 + tick / 20
        if when >= timeline.now:
            timeline.at(
                when,
                lambda: samples.append(
                    (
                        timeline.now,
                        len(relay.raw),
                        tuple(row.state for row in display.current(timeline.now)),
                    )
                ),
            )
    configure(worker, relay, timeline)
    try:
        worker._run(timeline.stop)
    finally:
        assert worker.stop()
    assert worker._latest is None
    assert worker.status().detail is None
    assert all(b[1] >= a[1] + 0.5 for a, b in zip(relay.completed, relay.calls[1:]))
    return relay, samples, timeline, events


def exact_trace_oracle(relay):
    """Combat §5.4 literally, from original publications + raw HTTP only.

    No production timing, state, projection or display helper is imported/called.
    Brute-force covering intervals deliberately differ from production suffix
    minima. Output maps raw-completion counts to plain expected coordinates.
    """
    history, expected, current = [], {0: None}, None
    for count, (operation, a, r, sampled, code, raw) in enumerate(relay.raw, 1):
        if (
            operation == "read_snapshot"
            and code == 200
            and 0 <= 1000 * (Fraction(r) - Fraction(a)) <= 5000
        ):
            db = json.loads(raw)["server_time_ms"]
            history = [
                (old_db, old_a) for old_db, old_a in history if db - old_db < 30000
            ]
            history.append((db, Fraction(a)))
            available = [
                pub for pub in relay.publications if pub.released_at <= sampled
            ]
            current = None
            if available:
                pub = available[-1]
                if 0 <= db - pub.sample_ms < 10000 and db - pub.activity_ms < 30000:

                    def coordinate(origin, lifetime):
                        covering = [
                            start - Fraction(t, 1000) - Fraction(1, 5)
                            for t, start in history
                            if t - lifetime < origin <= t
                        ]
                        assert covering
                        return Fraction(origin, 1000) + min(covering)

                    current = (
                        pub.sample_ms,
                        coordinate(pub.sample_ms, 10000),
                        coordinate(pub.activity_ms, 30000) + 30,
                        coordinate(pub.effect_ms, 30000) + 30
                        if pub.effect_ms is not None and db - pub.effect_ms < 30000
                        else None,
                    )
        expected[count] = current
    return expected


def assert_exact_trace(relay, samples, events):
    expected = exact_trace_oracle(relay)
    # Callback just collects. These comparisons run outside the worker's
    # catch-all notification path and cannot be swallowed as a subscriber error.
    replaces = [(count, event) for count, event in events if event.kind == "replace"]
    eligible = [
        i
        for i, (op, a, r, _, code, _) in enumerate(relay.raw, 1)
        if op == "read_snapshot"
        and code == 200
        and 0 <= 1000 * (Fraction(r) - Fraction(a)) <= 5000
    ]
    assert [i for i, _ in replaces] == eligible, "admitted response lost or fabricated"
    for count, event in replaces:
        want = expected[count]
        assert event.payload is not None
        assert len(event.payload.rows) == (0 if want is None else 1), (
            "premature receiver withdrawal"
        )
        if want is not None:
            row = event.payload.rows[0]
            assert (row.sampled_at_mono, row.activity_expires_at_mono) == want[1:3], (
                "exact external origin mismatch"
            )
            effects = tuple(
                o.expires_at_mono for e in row.effects for o in e.observations
            )
            assert effects == (() if want[3] is None else (want[3],)), (
                "exact external effect mismatch"
            )
    classified = []
    for now, count, actual in samples:
        want = expected[count]
        state = ()
        if want is not None and Fraction(now) < min(want[1] + 10, want[2]):
            state = ("live",) if Fraction(now) < want[1] + 3 else ("stale",)
        assert actual == state, (
            "exact external freshness mismatch",
            now,
            actual,
            state,
        )
        classified.append((now, state, want[0] if want else None))
    return classified


def assert_scenario_fairness(relay, *, watch, due=1030):
    # Known eligible scenario classes, NOT inferred from successful operations.
    metadata = {"fetch_device", "fetch_eligibility", "fetch_catalogue", "renew_session"}
    if watch:
        metadata |= {"fetch_sources", "fetch_automatic"}
    expected = metadata | {"read_snapshot"}
    # One competing snapshot per metadata admission, including a crossing read;
    # renewal consumes its own metadata slot. No arbitrary enlarged literal.
    bound = 2 * len(metadata)
    admissions = [
        op
        for op, end in relay.completed
        if end >= due and OPERATION_BUCKETS[op] == "read"
    ]
    assert expected <= set(admissions[:bound]), (
        "eligible class starved",
        expected - set(admissions[:bound]),
    )


@pytest.mark.parametrize("phase", [0, 0.2, 0.5, 0.9])
@pytest.mark.parametrize("watch", [False, True])
@pytest.mark.parametrize("latency", [0.025, 0.08, 0.12])
def test_current_receiver_matches_exact_freshness_without_local_publication(
    tmp_path, phase, watch, latency
):
    relay, samples, timeline, events = run_trace_owner(
        tmp_path,
        phase=phase,
        watch=watch,
        latency=latency,
        configure=simultaneous_metadata,
    )
    assert_scenario_fairness(relay, watch=watch)
    classified = assert_exact_trace(relay, samples, events)
    recoveries = assert_healthy_recovery(classified)
    assert_healthy_trace_bounds(
        relay, classified, phase=phase, latency=latency, end=timeline.end
    )
    if watch and (latency, phase) in ((0.08, 0.5), (0.12, 0.9)):
        assert recoveries, "expected stale-to-live callback transition not witnessed"


# Independent healthy-scenario theorem (not a measured-gap or class-count bound):
# - No local PUT/control stream, pending automatic probe/receipt, backoff or sample
#   delay. Watch adds ordinary sources/automatic metadata, not critical work.
# - Startup requires only device, then a 500ms floor and snapshot (caps are ACKed).
# - Next snapshot is due r+1. One read can cross that due instant and hold its
#   completion floor. Then only one renewal and one urgent eligibility refresh
#   can overtake: ordinary metadata loses to a due snapshot with no controls.
#   Renewal re-arms 600s away (injected bursts 30s apart); proof refresh grants
#   10s from sample, so urgency cannot return for 7-L seconds. Both exceed G<3s.
#   Hence G = 1 + 3*(0.5+L) + L, independent of watch/class population.
# - External S = floor(a)-0.2; every covering interval subtracts another 0.2.
#   Thus mapped S > a-1-0.4, and at receipt r it holds LIVE for H=1.6-L.
#   Every receipt is LIVE; a stale episode starts at mapped S+3 and recovers
#   within R=G-H, with genuinely newer original S, not a restamped receipt.
# - Binary64 clocks stay in [1000,2048). q is half an ULP at 2048, covering each
#   local addition across 1024. Latency/floor/due use separate ceilings. Nearby
#   deadline subtraction is exact (Sterbenz), so waiting adds no poll-grid delay.
#   int(1000*(a-1000)) can round upward by <q seconds; allow that once in H.
#   Display ticks can lag a receipt by 1/20+2q, never extend its deadline.
# Delayed/error/bad-interval, slow proof and legacy local-PUT cases have different
# assumptions and keep their own exact oracles; this theorem does not cover them.
_CLOCK_ROUNDING = Fraction(1, 2**42)


@dataclass(frozen=True)
class HealthyBounds:
    first_receipt: Fraction
    gap: Fraction
    live_hold: Fraction
    grid: Fraction

    @property
    def recovery(self):
        return self.gap - self.live_hold


def healthy_bounds(*, phase, latency):
    assert 0 <= phase < 1 and latency in (0.025, 0.08, 0.12)
    q = _CLOCK_ROUNDING
    ell, floor, due = Fraction(latency) + q, Fraction(1, 2) + q, 1 + q
    return HealthyBounds(
        Fraction(1000 + phase) + 2 * ell + floor,
        due + 3 * (floor + ell) + ell,
        3 - 1 - Fraction(2, 5) - ell - q,
        Fraction(1, 20) + 2 * q,
    )


def assert_mixed_trace_bounds(
    publisher, receiver, samples, events, *, phase, latency, watch, end=1120
):
    """Original local releases + two independent serialized lanes, no backoff.

    A ready heartbeat can be overtaken by one read only: its completion closes
    the read bucket for500ms, leaving the independent PUT ready immediately.
    Hence consecutive PUT starts differ by at most P=1+2L (heartbeat1, previous
    PUT responseL, crossing readL). Each selects the newest one-second m.

    Publisher GETs may additionally wait for a PUT crossing each of the four
    read starts in the C theorem: own Gp=G+4L. L<=120ms fits inside each500ms
    completion floor; no second PUT can cross that same read opportunity.
    Renewal/urgent proof cannot recur within Gp (600s and7-L respectively).
    This is explicitly not the receiver-only theorem silently applied to PUT.

    Latest available PUT started less than P ago; m is less than1s older.
    Publisher anchor mapping loses L+200ms, receiver projection200ms and its
    return loses another L. Therefore every useful receipt has LIVE hold
    H=3-P-1-2L-400ms. Millisecond floors and the fake UTC microsecond/float
    representation have independently bounded loss below, not an observed fit.
    Receiver has no local PUT, so its original C service G still applies and
    every stale episode recovers within G-H using a newer original measurement.
    """
    q = _CLOCK_ROUNDING
    ell = Fraction(latency) + q
    floor = Fraction(1, 2) + q
    receiver_bounds = healthy_bounds(phase=phase, latency=latency)
    pub_gap = 1 + q + 2 * ell
    # Publisher fixture's int(utc.timestamp()*1000), mapper's floor, and
    # receiver DB floor: three1ms quantizations; UTC timedelta rounds to1us,
    # timestamp float in[2**30,2**31) has ULP2**-22 seconds.
    quantization = Fraction(3, 1000) + Fraction(1, 1000000) + Fraction(1, 2**22) + 4 * q
    live_hold = 3 - pub_gap - 1 - 2 * ell - Fraction(2, 5) - quantization
    assert live_hold > 0
    # Device authentication, then at most one preferred snapshot per initial
    # metadata class (catalogue/eligibility + sources/automatic when watching).
    metadata = 2 + 2 * watch
    first_put = Fraction(1000) + ell + 2 * metadata * (floor + ell)
    starts = [Fraction(t) for t, body in publisher.published if body.rows and t <= end]
    assert_snapshot_service(
        starts,
        bounds=HealthyBounds(first_put, pub_gap, live_hold, receiver_bounds.grid),
        end=end,
    )
    own_gets = [
        r
        for (op, _, _), (_, r) in zip(publisher.calls, publisher.completed, strict=True)
        if op == "read_snapshot"
    ]
    assert_snapshot_service(
        own_gets,
        bounds=replace(
            healthy_bounds(phase=0, latency=latency), gap=receiver_bounds.gap + 4 * ell
        ),
        end=end,
    )
    classified = assert_exact_trace(receiver, samples, events)
    expected = exact_trace_oracle(receiver)
    installed = []
    bounds = replace(
        receiver_bounds,
        first_receipt=first_put + ell + receiver_bounds.gap,
        live_hold=live_hold,
    )
    for count, (op, _, r, _, code, _) in enumerate(receiver.raw, 1):
        if op != "read_snapshot" or r > end:
            continue
        assert code == 200
        want = expected[count]
        if want is None:
            assert not installed and r < bounds.first_receipt, (
                "mixed publication disappeared"
            )
        else:
            installed.append((Fraction(r), want[0], want[1]))
    assert_snapshot_service([r for r, _, _ in installed], bounds=bounds, end=end)
    return assert_stale_recovery(
        installed, bounds=bounds, end=end, classified=classified
    )


def assert_snapshot_service(receipts, *, bounds, end):
    end = Fraction(end)
    receipts = [Fraction(r) for r in receipts if r <= end]
    if not receipts:
        assert end < bounds.first_receipt, "snapshot service startup deadline missed"
        return
    assert receipts[0] <= bounds.first_receipt, (
        "snapshot service startup deadline missed"
    )
    for a, b in pairwise(receipts):
        assert b <= a + bounds.gap, (
            "snapshot service gap deadline missed",
            a,
            b,
            bounds.gap,
        )
    # A receipt at its deadline counts, but an unmet deadline at end fails.
    # Discard post-end receipts BEFORE inspecting the final open interval.
    assert end < receipts[-1] + bounds.gap, "snapshot service end deadline missed"


@dataclass(frozen=True)
class StaleEpisode:
    start: Fraction
    original_sample_ms: int
    recovered_at: Fraction | None
    newer_sample_ms: int | None
    observed_live_at: Fraction | None


def assert_stale_recovery(installed, *, bounds, end, classified=None):
    end = Fraction(end)
    installed = [
        (Fraction(r), origin, Fraction(mapped))
        for r, origin, mapped in installed
        if r <= end
    ]
    episodes = []
    for i, (receipt, origin, mapped) in enumerate(installed):
        assert receipt < mapped + 3, "healthy snapshot receipt is not LIVE"
        assert mapped + 3 - receipt >= bounds.live_hold, (
            "healthy LIVE-hold lower bound missed"
        )
        start = mapped + 3
        successor = installed[i + 1] if i + 1 < len(installed) else None
        if start > end or (successor is not None and start >= successor[0]):
            continue
        # Enumerate actual payload lifetimes, including sub-grid episodes. A
        # first stale display tick alone would miss episodes shorter than 50ms.
        deadline = start + bounds.recovery
        recovered, newer, observed = None, None, None
        if successor is None:
            assert end < deadline, (
                "stale recovery end deadline missed",
                start,
                end,
                deadline,
            )
        else:
            recovered, newer, _ = successor
            assert recovered <= deadline, (
                "stale recovery deadline missed",
                start,
                recovered,
                deadline,
            )
            assert newer > origin, "stale recovery without newer original measurement"
            if classified is not None:
                # VirtualWait drains a tick exactly at r before HTTP read()
                # returns/publishes. The first strictly later tick observes it.
                after = next(
                    (
                        (Fraction(t), state, s)
                        for t, state, s in classified
                        if recovered < t <= end
                    ),
                    None,
                )
                if after is not None:
                    observed, state, sample = after
                    assert observed <= recovered + bounds.grid, (
                        "recovery observation missed sample grid"
                    )
                    assert state == ("live",) and sample == newer, (
                        "recovery observation not newer LIVE"
                    )
                else:
                    # A valid receipt near end need not have a subsequent tick.
                    assert end <= recovered + bounds.grid, (
                        "recovery observation missing before end"
                    )
        episodes.append(StaleEpisode(start, origin, recovered, newer, observed))
    return episodes


def healthy_installations(relay, *, end, latency=0.08):
    expected = exact_trace_oracle(relay)
    installed = []
    for count, (op, a, r, sampled, code, _) in enumerate(relay.raw, 1):
        assert 1000 <= a <= r < 2048, "outside derived binary clock range"
        assert abs(Fraction(r) - Fraction(a) - Fraction(latency)) <= _CLOCK_ROUNDING, (
            "outside constant-latency healthy scenario"
        )
        if op == "read_snapshot":
            assert code == 200 and sampled == a, "not a healthy GET scenario"
            if r <= end:
                want = expected[count]
                assert want is not None, "healthy snapshot missing original measurement"
                installed.append((Fraction(r), want[0], want[1]))
    return installed


def assert_healthy_trace_bounds(relay, classified, *, phase, latency, end):
    bounds = healthy_bounds(phase=phase, latency=latency)
    installed = healthy_installations(relay, end=end, latency=latency)
    assert_snapshot_service([r for r, _, _ in installed], bounds=bounds, end=end)
    return assert_stale_recovery(
        installed, bounds=bounds, end=end, classified=classified
    )


@pytest.mark.parametrize(
    "receipts,end,error",
    [
        ([2, 5, 8], 10, None),
        ([2, 5, 8], 8, None),
        ([], 1, None),
        ([], 2, "startup"),
        ([3], 4, "startup"),
        ([2, 5 + Fraction(1, 2**60)], 6, "gap"),
        ([2, 5], 8, "end"),
        ([2, 5, 9], 8, "end"),
        ([2, 5, 100], 7, None),
    ],
    ids=[
        "covered",
        "receipt-at-end",
        "startup-not-due",
        "missing-at-startup",
        "late-startup",
        "exact-gap-exceeded",
        "missing-at-end",
        "post-end-cannot-cover",
        "post-end-irrelevant",
    ],
)
def test_snapshot_service_exact_deadlines_include_startup_and_tail(
    receipts, end, error
):
    # Literal schedule: first receipt due2, next at most3s later. No worker
    # output or scenario duration supplies the expected deadline.
    bounds = HealthyBounds(Fraction(2), Fraction(3), Fraction(1), Fraction(1, 20))
    if error is None:
        assert_snapshot_service(receipts, bounds=bounds, end=end)
    else:
        with pytest.raises(AssertionError, match=f"snapshot service {error}"):
            assert_snapshot_service(receipts, bounds=bounds, end=end)


@pytest.mark.parametrize(
    "successor,end,error",
    [
        ((5, 11, 4), 6, None),
        ((5, 11, 4), 5, None),
        ((5 + Fraction(1, 2**60), 11, 4), 6, "stale recovery deadline"),
        ((5, 10, 4), 6, "without newer original"),
        ((3, 11, 2), 4, None),
        ((Fraction(301, 100), 11, 2), 4, None),
        (None, 4, None),
        (None, 5, "stale recovery end deadline"),
        ((6, 11, 5), 5, "stale recovery end deadline"),
        ((6, 11, 5), 4, None),
    ],
    ids=[
        "deadline-equality",
        "recovery-at-end",
        "exact-deadline-exceeded",
        "restamped-origin",
        "no-stale-interval",
        "sub-grid-stale-interval",
        "right-censored",
        "censored-deadline-at-end",
        "post-end-cannot-recover",
        "post-end-irrelevant",
    ],
)
def test_stale_episode_exact_deadlines_and_new_origins(successor, end, error):
    bounds = HealthyBounds(Fraction(2), Fraction(3), Fraction(1), Fraction(1, 20))
    # Receipt1 installs coordinate0: actual staleness starts3, not the next
    # display tick. Recovery is due5 (gap3 minus minimum LIVE hold1).
    installed = [(1, 10, Fraction(0))] + ([successor] if successor else [])
    if error is not None:
        with pytest.raises(AssertionError, match=error):
            assert_stale_recovery(installed, bounds=bounds, end=end)
    else:
        episodes = assert_stale_recovery(installed, bounds=bounds, end=end)
        if successor is not None and successor[0] == 3:
            assert episodes == []
        else:
            recovered = successor is not None and successor[0] <= end
            assert episodes == [
                StaleEpisode(
                    Fraction(3),
                    10,
                    Fraction(successor[0]) if recovered else None,
                    successor[1] if recovered else None,
                    None,
                )
            ]


@pytest.mark.parametrize("late", [False, True])
def test_recovery_observation_grid_does_not_extend_receipt_deadline(late):
    bounds = HealthyBounds(Fraction(2), Fraction(3), Fraction(1), Fraction(1, 20))
    observed = Fraction(101, 20) + (Fraction(1, 2**60) if late else 0)
    kwargs = {
        "bounds": bounds,
        "end": 6,
        "classified": [(5, ("stale",), 10), (observed, ("live",), 11)],
    }
    installed = [(1, 10, Fraction(0)), (5, 11, Fraction(4))]
    if late:
        with pytest.raises(AssertionError, match="missed sample grid"):
            assert_stale_recovery(installed, **kwargs)
    else:
        assert assert_stale_recovery(installed, **kwargs) == [
            StaleEpisode(Fraction(3), 10, Fraction(5), 11, observed)
        ]


def test_recovery_bound_rejects_115_second_stale_episode_accepted_by_old_helper():
    classified = [(0, ("live",), 10), (1, ("stale",), 10), (116, ("live",), 11)]
    assert assert_healthy_recovery(classified) == [116]
    bounds = HealthyBounds(Fraction(2), Fraction(3), Fraction(1), Fraction(1, 20))
    with pytest.raises(AssertionError, match="stale recovery deadline missed"):
        assert_stale_recovery(
            [(0, 10, Fraction(-2)), (116, 11, Fraction(115))], bounds=bounds, end=117
        )


def assert_healthy_recovery(classified):
    seen_live, stale_origin, recoveries = False, None, []
    for now, states, origin in classified:
        if states == ("live",):
            seen_live = True
            if stale_origin is not None:
                assert origin > stale_origin, (
                    "stale recovery without newer original measurement"
                )
                recoveries.append(now)
                stale_origin = None
        elif seen_live:
            assert states == ("stale",), "healthy receiver permanently lost visibility"
            if stale_origin is None:
                stale_origin = origin
    assert seen_live and stale_origin is None, "brief stale interval never recovered"
    return recoveries


@pytest.mark.parametrize("latency,expected", [(3.2, ("stale",)), (11, ())])
def test_current_receiver_delayed_get_cannot_rejuvenate_old_payload(
    tmp_path, latency, expected
):
    def delay_reads(worker, client, timeline):
        def response():
            delay = (
                latency
                if timeline.now >= 1020 and client.calls[-1][0] == "read_snapshot"
                else 0.08
            )
            timeline.advance(timeline.now + delay)

        client.latency = response

    relay, samples, _, events = run_trace_owner(
        tmp_path, duration=60, configure=delay_reads
    )
    assert_exact_trace(relay, samples, events)
    assert samples and all(states == expected for t, _, states in samples if t >= 1035)
    delayed = [
        r - a for op, a, r, _, _, _ in relay.raw if op == "read_snapshot" and a >= 1020
    ]
    assert delayed and all(span == pytest.approx(latency) for span in delayed)


def test_current_read_backoff_and_metadata_progress_without_publication(tmp_path):
    def refuse(worker, client, timeline):
        timeline.at(
            1020, lambda: client.errors.update(read_snapshot=(429, "rate_limited"))
        )
        timeline.at(1030, client.errors.clear)

    relay, samples, timeline, events = run_trace_owner(
        tmp_path, duration=40, configure=refuse
    )
    assert_exact_trace(relay, samples, events)
    attempts = [
        t for op, t, _ in relay.calls if op == "read_snapshot" and 1020 <= t < 1030
    ]
    assert len(attempts) == 4
    assert all(
        b - a >= delay + 0.08 - 1e-9
        for (a, b), delay in zip(pairwise(attempts), (1, 2, 4), strict=True)
    )
    assert any(
        op == "fetch_eligibility" and 1020 <= t < 1030 for op, t, _ in relay.calls
    )
    assert len(timeline.waits) < 400


def test_bad_postlock_interval_does_not_bias_genuinely_new_origins(tmp_path):
    held = []

    def slow_once(worker, relay, timeline):
        def before_sample(operation):
            if operation == "read_snapshot" and timeline.now >= 1020 and not held:
                held.append(timeline.now)
                timeline.advance(timeline.now + 4.8)

        relay.before_sample = before_sample

    relay, samples, _, events = run_trace_owner(
        tmp_path, latency=0.02, configure=slow_once
    )
    assert len(held) == 1
    classified = assert_exact_trace(relay, samples, events)
    bad_index, bad = next(
        (i, exchange)
        for i, exchange in enumerate(relay.raw, 1)
        if exchange[0] == "read_snapshot" and exchange[1] == held[0]
    )
    assert 4800 < 1000 * (Fraction(bad[2]) - Fraction(bad[1])) <= 5000
    bad_db = json.loads(bad[-1])["server_time_ms"]
    assert any(
        count == bad_index and state == ("stale",) for _, count, state in samples
    ), "bad interval was not witnessed stale"
    # A later callback really installs a new-origin LIVE payload while the bad
    # record is still within its 30s protective lifetime — no clear/reset/reseed.
    recovered = [
        (now, origin)
        for now, state, origin in classified
        if now > bad[2]
        and origin is not None
        and origin > bad_db
        and state == ("live",)
    ]
    assert recovered and recovered[0][0] < bad[2] + 3, (
        "new origins remain permanently stale"
    )
    assert all(
        state == ("live",) for now, state, _ in classified if now >= recovered[0][0]
    ), "recovered origin freshness regressed"
    assert not [
        event
        for count, event in events[:-1]
        if count >= bad_index and event.kind == "clear"
    ]


@pytest.mark.parametrize("period", [5, 6])
@pytest.mark.parametrize("phase", [0, 2, 4])
@pytest.mark.parametrize("skew", [-0.5, 0.5])
def test_expiring_proof_refresh_progress_is_independent_of_local_publication(
    tmp_path, period, phase, skew
):
    def proof(worker, relay, timeline):
        worker._utc_clock = lambda: NOW + timedelta(seconds=timeline.now - 1000 + skew)
        relay.eligibility_expiry = lambda sampled: (
            1010 + math.floor((sampled - 1000 - phase) / period) * period + phase
        )
        simultaneous_metadata(worker, relay, timeline)

    relay, samples, timeline, events = run_trace_owner(
        tmp_path, duration=60, watch=True, latency=0.6, configure=proof
    )
    assert_exact_trace(relay, samples, events)
    proofs = [
        (r, relay.eligibility_expiry(sampled))
        for op, _, r, sampled, code, _ in relay.raw
        if op == "fetch_eligibility" and code == 200
    ]
    assert len(proofs) > 2
    assert_eligibility_coverage(proofs, end=timeline.end)


def assert_eligibility_coverage(proofs, *, end):
    # Coverage begins at the first receipt, not request/sample time. An in-flight
    # response completing beyond the scenario cannot cover its final interval.
    proofs = [(r, expiry) for r, expiry in proofs if r <= end]
    assert proofs, "eligible proof unavailable before scenario end"
    assert proofs[0][0] < proofs[0][1], "eligible proof expired at acquisition"
    assert all(next_r < expiry for (_, expiry), (next_r, _) in pairwise(proofs)), (
        "eligible proof expired before refresh"
    )
    assert end < proofs[-1][1], "eligible proof coverage does not reach scenario end"


@pytest.mark.parametrize(
    "proofs,end,error",
    [
        ([(1, 10), (9, 20), (19, 31)], 30, None),
        ([(1, 10), (9, 20), (19, 30)], 30, "does not reach scenario end"),
        ([(1, 10), (9, 20), (20, 31)], 30, "expired before refresh"),
        ([(1, 10), (9, 20), (19, 29), (31, 40)], 30, "does not reach scenario end"),
        ([(1, 10), (9, 20), (19, 31), (32, 40)], 30, None),
        ([(1, 1), (1, 20), (19, 31)], 30, "expired at acquisition"),
    ],
    ids=[
        "covered",
        "expiry-equality",
        "renewal-equality",
        "late-cannot-cover",
        "late-irrelevant",
        "expired-first",
    ],
)
def test_eligibility_coverage_requires_strict_uninterrupted_scenario_end(
    proofs, end, error
):
    if error is None:
        assert_eligibility_coverage(proofs, end=end)
    else:
        with pytest.raises(AssertionError, match=error):
            assert_eligibility_coverage(proofs, end=end)


@pytest.mark.parametrize("with_effects", [False, True])
def test_timed_relay_captures_valid_combat_rows_at_json_boundary(
    with_effects, tmp_path
):
    # Fixture proof only: already-valid CombatRows through the signed boundary.
    # Worker source association is proved by the separate original-source tests.
    effects = (
        (
            p.Effect(
                "SCRAM",
                (p.Observation("A", 600), p.Observation(None, 700)),
            ),
        )
        if with_effects
        else ()
    )
    rows = (
        p.CombatRow(1, None, 0, 400, effects),
        p.CombatRow(2, 0, None, 500, ()),
    )
    timeline = VirtualWait(1000, 1010)
    store = FileStore(tmp_path / "timed-relay.json")
    store.save(replace(PAIRED_STATE, last_revision=1))
    relay = TimedRelay(timeline, store, 0.2, ())
    relay.clock = lambda: timeline.now
    relay.publish_snapshot(
        private_key=KEY,
        session_id=PAIRED_STATE.session_id,
        revision=1,
        now=NOW,
        sampled_at_ms=DEVICE.server_time_ms - 200,
        rows=rows,
    )
    assert timeline.now == 1000.2
    assert len(relay.published) == 1
    released, body = relay.published[0]
    assert released == 1000, "trace publication was restamped at response completion"
    assert body.sampled_at_ms == DEVICE.server_time_ms - 200
    assert [(row.outgoing_dps, row.incoming_dps) for row in body.rows] == [
        (None, 0),
        (0, None),
    ]
    assert [body.sampled_at_ms - row.activity_age_ms for row in body.rows] == [
        DEVICE.server_time_ms - 600,
        DEVICE.server_time_ms - 700,
    ]
    expected_effects = (
        (
            (
                "SCRAM",
                (
                    ("A", DEVICE.server_time_ms - 800),
                    (None, DEVICE.server_time_ms - 900),
                ),
            ),
        )
        if with_effects
        else ()
    )
    assert (
        tuple(
            (
                effect.kind,
                tuple(
                    (o.name, body.sampled_at_ms - o.age_ms) for o in effect.observations
                ),
            )
            for effect in body.rows[0].effects
        )
        == expected_effects
    )
    assert body.rows[1].effects == ()


def test_external_put_trace_preserves_original_origins_and_nullable_values(tmp_path):
    # External wire fixture only; local source admission is proved separately.
    body = p.parse_combat_put(
        {
            "protocol": 2,
            "sampled_at_ms": DEVICE.server_time_ms - 200,
            "rows": [
                {
                    "character_id": 1,
                    "outgoing_dps": 0,
                    "incoming_dps": None,
                    "activity_age_ms": 200,
                    "effects": [],
                }
            ],
        }
    )
    trace = actual_publication_trace(((1000, body),))
    assert trace == (
        ExternalPublication(
            1000,
            DEVICE.server_time_ms - 200,
            DEVICE.server_time_ms - 400,
            None,
            0,
            None,
        ),
    )
    relay, samples, _, events = run_trace_owner(
        tmp_path,
        duration=20,
        publications=trace,
        state_store=durable_cadence_store(tmp_path / "external-trace.json"),
    )
    assert_exact_trace(relay, samples, events)
    rows = [
        row
        for _, event in events
        if event.payload is not None
        for row in event.payload.rows
    ]
    assert rows and all(
        (row.outgoing_dps, row.incoming_dps) == (0, None) for row in rows
    )
    assert samples[-1][-1] == ()


def test_repeated_metadata_bursts_service_every_known_eligible_class(tmp_path):
    def repeated(worker, relay, timeline):
        for due in (1030, 1060, 1090):

            def ready():
                for key in worker._due:
                    worker._due[key] = timeline.now
                worker._renew_at = timeline.now

            timeline.at(due, ready)

    relay, samples, timeline, events = run_trace_owner(
        tmp_path, watch=True, configure=repeated
    )
    for due in (1030, 1060, 1090):
        assert_scenario_fairness(relay, watch=True, due=due)
    classified = assert_exact_trace(relay, samples, events)
    assert_healthy_trace_bounds(
        relay, classified, phase=0, latency=0.08, end=timeline.end
    )


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
            worker.request_participation(
                False,
                expected_generation=worker.status().observed_participation.generation,
                binding=worker.status().metadata.binding,
            )

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
        timeline.at(
            1020,
            lambda: worker.submit(
                FakePublicationSource(
                    FleetSnapshot(
                        (), StreamHealth("active"), sampled_at_mono=timeline.now
                    )
                )
            ),
        )

    client, _, timeline, _ = run_owner(
        publisher=True, duration=40, telemetry_until=20, configure=empty
    )
    emptied = [(t, rows) for t, rows in client.published if t >= 1020]
    assert len(emptied) == 1 and emptied[0][1].rows == ()
    assert emptied[0][0] < 1020.7
    assert len(timeline.waits) < 400
