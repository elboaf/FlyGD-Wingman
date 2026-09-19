"""Real log/discovery → admission → metrics → worker → signed v2 HTTP proofs.

Only elapsed/UTC clocks, OS discovery, thread scheduling, key unwrap and HTTP
are injected. Tickets, observations, durable revisions and client parsing are real.
This is a scripted protocol peer, not a relay database or deployment acceptance.
"""

import base64
import hashlib
import json
from dataclasses import asdict, replace
from datetime import timedelta
from threading import Event, Thread
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from cryptography.hazmat.primitives.serialization import load_der_public_key

from tests.test_client_discovery import GENERIC
from tests.test_fleetsharing_client import (
    Response,
    _headers_of,
    framing_headers,
    request_binding,
)
from tests.test_fleetsharing_worker import COMBAT_DEVICE, KEY, NOW, PAIRED_STATE, UUID
from tests.test_fleetsharing_worker_state4 import FileStore
from tests.test_telemetry_gamelogs import (
    DAMAGE_LINE,
    OUTGOING_DAMAGE_LINE,
    SCRAMBLE_LINE,
    _AttemptSignallingLock,
    _log,
)
from tests.test_telemetry_gamelogs import (
    NOW as LOG_NOW,
)
from tests.test_telemetry_source_admission import real_runtime as real_runtime
from wingman.fleetsharing import crypto
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing.client import FleetRelayClient
from wingman.fleetsharing.timing import TimingContext
from wingman.fleetsharing.worker import (
    FleetSharingWorker,
    _noop_thread_factory,
    _Obsolete,
)
from wingman.ui.remotefleet import RemoteFleetStore


class ScriptedV2Transport:
    """Fail closed on unexpected routes, checking disk/signature before any reply."""

    def __init__(self, reply, store, mono):
        self.reply, self.store, self.mono = reply, store, mono
        self.requests = []
        self.responses = []
        self.hold = None
        self.entered, self.release = Event(), Event()
        self.read_delay = 0.0

    def __call__(self, request, timeout=None):
        headers = _headers_of(request)
        saved = self.store.load()
        assert saved.last_revision == int(headers["x-fleet-revision"])
        assert saved.session_id == headers["x-fleet-session"]
        digest = hashlib.sha256(request.data or b"").hexdigest()
        assert headers["x-fleet-body-sha256"] == digest
        path = urlsplit(request.full_url).path
        assert request.full_url == "https://relay.test" + path
        canonical = "\n".join(
            (
                "fleet-v1",
                request.method,
                path,
                saved.session_id,
                headers["x-fleet-issued-at"],
                str(saved.last_revision),
                digest,
            )
        ).encode()
        signature = headers["x-fleet-signature"]
        load_der_public_key(crypto.public_key_spki(KEY)).verify(
            base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4)),
            canonical,
        )
        self.requests.append(request)
        payload = self.reply(request)
        if (request.method, path) == self.hold:
            self.entered.set()
            assert self.release.wait(5), "scripted HTTP not released"
        owner = self

        class TimedResponse(Response):
            def read(self, amount=-1):
                if not self.reads:
                    owner.mono[0] += owner.read_delay
                return super().read(amount)

        response = TimedResponse(
            json.dumps(payload).encode(), framing_headers(request_binding(request))
        )
        self.responses.append(response)
        return response


class Routes:
    """Closed DTOs from the accepted combat/state4 fixtures; no client facade."""

    def __init__(self, mono):
        self.mono = mono
        self.participation = COMBAT_DEVICE.participation
        self.puts = []
        self.remote_origin = None

    def utc(self):
        return NOW + timedelta(seconds=self.mono[0] - 1000)

    def __call__(self, request):
        route = (request.method, urlsplit(request.full_url).path)
        data = json.loads(request.data) if request.data else None
        now_ms = int(self.utc().timestamp() * 1000)
        if route == ("GET", "/api/fleet/v2/device"):
            return {
                "protocol": 2,
                **asdict(
                    replace(
                        COMBAT_DEVICE,
                        server_time_ms=now_ms,
                        participation=self.participation,
                    )
                ),
            }
        if route == ("GET", "/api/fleet/v2/catalogue"):
            return {
                "protocol": 2,
                "revision": 1,
                "characters": [{"character_id": 1, "character_name": "Alice"}],
            }
        if route == ("GET", "/api/fleet/v2/eligibility"):
            return {
                "protocol": 2,
                "participation_generation": self.participation.generation,
                "state": "ready" if self.participation.enabled else "participation_off",
                "characters": [
                    asdict(
                        p.EligibilityEntry(
                            1,
                            UUID,
                            1,
                            1,
                            (self.utc() + timedelta(seconds=10))
                            .isoformat(timespec="milliseconds")
                            .replace("+00:00", "Z"),
                        )
                    )
                ]
                if self.participation.enabled
                else [],
            }
        if route == ("GET", "/api/fleet/v2/sources"):
            return {
                "protocol": 2,
                "sources": [],
                "characters": [asdict(p.SourceCharacter(1, "Alice", UUID, True, True))],
            }
        if route == ("GET", "/api/fleet/v2/automatic-verification"):
            return {
                "protocol": 2,
                "status": asdict(
                    p.AutomaticStatus(
                        p.Consent(0, 0, False, None, None, None, None),
                        "none",
                        "off",
                        "none",
                        None,
                        (),
                    )
                ),
            }
        if route == ("PUT", "/api/fleet/v2/snapshot"):
            self.puts.append(p.parse_combat_put(data))
            return {"protocol": 2}
        if route == ("GET", "/api/fleet/v2/snapshot"):
            if self.remote_origin is None:
                self.remote_origin = now_ms
            age = now_ms - self.remote_origin
            return {
                "protocol": 2,
                "server_time_ms": now_ms,
                "rows": [
                    {
                        "character_id": 2,
                        "character_name": "Remote",
                        "outgoing_dps": None,
                        "incoming_dps": 0,
                        "activity_age_ms": age,
                        "effects": [],
                        "state": "live" if age < 3000 else "stale",
                        "age_ms": age,
                        "publication_id": UUID,
                    }
                ]
                if age < 10000
                else [],
            }
        if route == ("PUT", "/api/fleet/v2/participation"):
            assert set(data) == {"protocol", "enabled", "expected_generation"}
            assert data["protocol"] == 2 and data["enabled"] is False
            assert data["expected_generation"] == self.participation.generation
            self.participation = p.Participation(
                False, self.participation.generation + 1
            )
            return {"protocol": 2, "participation": asdict(self.participation)}
        pytest.fail(f"Unexpected signed route: {route}, {data}")


@pytest.fixture
def signed_runtime(real_runtime, tmp_path):
    r = real_runtime
    clock = r.metrics._clock
    assert r.stream._clock is clock and r.coordinator._clock is clock

    # Both real log readers and metrics use the same UTC/elapsed mapping. The
    # provider fixture's initial old line stays old; append actual fresh bytes.
    def utc():
        return LOG_NOW + timedelta(seconds=r.mono[0] - 1000)

    r.stream._utc_now = r.metrics._utc_now = utc
    store = FileStore(tmp_path / "real-signed-sharing.json")
    store.save(PAIRED_STATE)
    routes = Routes(r.mono)
    transport = ScriptedV2Transport(routes, store, r.mono)
    client = FleetRelayClient("https://relay.test", transport=transport)
    context = TimingContext(
        clock=clock, db_continuity_token=object(), elapsed_lifetime_token=object()
    )
    worker = FleetSharingWorker(
        load_state=store.load,
        save_state=store.save,
        client_factory=lambda origin: client,
        unwrap_private_key=lambda blob: KEY,
        sharing_enabled=lambda: True,
        timing_context=context,
        _utc_clock=routes.utc,
        _thread_factory=_noop_thread_factory,
        _jitter=lambda: 0,
    )
    # Authenticate metadata using real GETs before connecting local publication.
    worker.set_source_watch(True)
    for _ in range(12):
        worker.iterate_once()
        r.mono[0] += 0.5
    assert worker._catalogue and worker._eligibility and context._state.anchor
    assert worker.status().sources is not None
    assert worker.status().automatic_status is not None
    assert store.load().automatic.observed_consent == p.Consent(
        0, 0, False, None, None, None, None
    )
    assert worker.status().metadata.loaded and store.load().device_id == UUID
    unsubscribe = r.coordinator.subscribe_admitted_fleet(worker.submit)
    yield SimpleNamespace(
        r=r,
        worker=worker,
        store=store,
        routes=routes,
        transport=transport,
        client=client,
        context=context,
    )
    transport.release.set()
    unsubscribe()
    assert worker.stop()


def append_facts(
    g,
    lines=OUTGOING_DAMAGE_LINE + DAMAGE_LINE + SCRAMBLE_LINE.format(target="Alice"),
    *,
    age=0,
):
    stamp = (LOG_NOW + timedelta(seconds=g.r.mono[0] - 1000 - age)).strftime(
        "%Y.%m.%d %H:%M:%S"
    )
    text = lines.replace("2026.08.25 11:30:00", stamp).replace(
        "2026.08.25 11:30:05", stamp
    )
    with g.r.path.open("a", encoding="utf-8") as output:
        output.write(text)
    g.r.stream.scan_once(g.r.stream._utc_now())
    g.r.coordinator.dispatch_once(0)
    source = g.r.tickets[-1]
    assert source.is_current() and g.worker._latest is source
    return source


def select(g, operation="publish_snapshot"):
    for _ in range(12):
        fence = g.worker._fence()
        work = g.worker._scheduler.choose(g.worker._work(True), g.r.mono[0])
        if work is not None and work.operation == operation:
            return work, fence
        g.worker.iterate_once()
        g.r.mono[0] += 0.5
    pytest.fail(f"Scheduler never selected {operation}: {g.worker.status()}")


def run_selected(g, work, fence):
    errors = []

    def run():
        try:
            with g.worker._iteration_lock:
                g.worker._execute(work, fence)
        except BaseException as exc:  # noqa: BLE001 — forward thread/pytest failures to the test owner.
            errors.append(exc)

    thread = Thread(target=run)
    thread.start()
    return thread, errors


@pytest.mark.parametrize(
    "lines,outgoing,incoming",
    [
        (OUTGOING_DAMAGE_LINE + DAMAGE_LINE, 30, 14),
        (OUTGOING_DAMAGE_LINE, 30, 0),
        (DAMAGE_LINE, 0, 14),
        (OUTGOING_DAMAGE_LINE.replace("299", "0"), 0, 0),
    ],
    ids=["both", "outgoing-only", "incoming-only", "literal-zero"],
)
def test_real_metrics_original_sample_and_observation_reach_signed_put(
    signed_runtime, lines, outgoing, incoming
):
    g = signed_runtime
    source = append_facts(g, lines + SCRAMBLE_LINE.format(target="Alice"), age=2)
    snapshot = source.snapshot
    row = snapshot.rows[0]
    assert (row.dps, row.incoming_dps) == (outgoing, incoming)
    assert row.combat.observation_id and row.combat.observations[0].observation_id
    m = snapshot.sampled_at_mono
    g.r.mono[0] += 0.5  # Selection is later than the actual metrics capture.
    work, fence = select(g)
    assert work.payload.source is source and work.payload.snapshot is snapshot
    g.worker._execute(work, fence)
    put = g.routes.puts[-1]
    # Conservatively mapped original sample, never selection/completion time.
    assert put.sampled_at_ms == 1788782400000 + int((m - 1000) * 1000) - 200
    assert put.rows == (
        p.CombatRow(
            1,
            outgoing,
            incoming,
            2000,
            (p.Effect("SCRAM", (p.Observation(None, 2000),)),),
        ),
    )
    assert g.worker._last_published
    assert source.snapshot is snapshot and snapshot.rows[0].combat is row.combat
    keys = tuple(g.context._publisher.associations)
    assert any(row.combat.observation_id in key for key in keys)
    assert any(row.combat.observations[0].observation_id in key for key in keys)


@pytest.mark.parametrize("when", ["before", "after"])
def test_real_source_retirement_either_side_of_logical_start(
    signed_runtime, monkeypatch, when
):
    g = signed_runtime
    source = append_facts(g)
    work, fence = select(g)
    revision = g.store.load().last_revision
    if when == "before":
        original = crypto.sign_request

        def signing(*args, **kwargs):
            result = original(*args, **kwargs)
            g.r.path.unlink()
            g.r.stream.scan_once(g.r.stream._utc_now())
            assert not source.is_current()  # No dispatcher has run the retirement.
            return result

        monkeypatch.setattr(crypto, "sign_request", signing)
        with pytest.raises(_Obsolete):
            g.worker._execute(work, fence)
    else:
        g.transport.hold = ("PUT", "/api/fleet/v2/snapshot")
        thread, errors = run_selected(g, work, fence)
        try:
            assert g.transport.entered.wait(5)
            g.r.path.unlink()
            g.r.stream.scan_once(g.r.stream._utc_now())
            assert not source.is_current()
        finally:
            g.transport.release.set()
            thread.join(5)
        assert not thread.is_alive()
        assert len(errors) == 1 and isinstance(errors[0], _Obsolete)
    assert len(g.routes.puts) == (when == "after")
    assert not g.worker._last_published
    assert g.store.load().last_revision == revision + 1
    assert g.context._next_stage_at is not None
    if when == "after":
        assert g.worker._scheduler.deadlines["publication"] == g.r.mono[0] + 0.5


@pytest.mark.parametrize("boundary", ["revision_save", "signing"])
def test_off_while_durable_revision_or_signature_is_held(
    signed_runtime, monkeypatch, boundary
):
    g = signed_runtime
    source = append_facts(g)
    work, fence = select(g)
    revision = g.store.load().last_revision
    entered, release = Event(), Event()
    original = (
        g.worker._save_state if boundary == "revision_save" else crypto.sign_request
    )

    def held(*args, **kwargs):
        result = original(*args, **kwargs)
        entered.set()
        assert release.wait(5)
        return result

    if boundary == "revision_save":
        monkeypatch.setattr(g.worker, "_save_state", held)
    else:
        monkeypatch.setattr(crypto, "sign_request", held)
    thread, errors = run_selected(g, work, fence)
    try:
        assert entered.wait(5)
        assert g.store.load().last_revision == revision + 1
        assert g.worker.request_participation(
            False, expected_generation=1, binding=g.worker.status().metadata.binding
        )
        assert g.worker.status().local_inhibited and source.is_current()
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], _Obsolete)
    assert g.routes.puts == [] and not g.worker._last_published
    assert g.store.load().last_revision == revision + 1


@pytest.mark.parametrize("wait_seconds,allowed", [(0.25, True), (5.0, False)])
def test_real_leaf_contention_samples_start_after_wait(
    signed_runtime, monkeypatch, wait_seconds, allowed
):
    g = signed_runtime
    source = append_facts(g)
    work, fence = select(g)
    signed, release_signing = Event(), Event()
    sign = crypto.sign_request
    lock = _AttemptSignallingLock(g.r.authority._lock)
    monkeypatch.setattr(g.r.authority, "_lock", lock)

    def hold_signature(*args, **kwargs):
        result = sign(*args, **kwargs)
        signed.set()
        assert release_signing.wait(5)
        return result

    monkeypatch.setattr(crypto, "sign_request", hold_signature)
    thread, errors = run_selected(g, work, fence)
    try:
        assert signed.wait(5)
        with lock:
            lock.watch(thread.ident)
            release_signing.set()
            assert lock.attempted.wait(5), "sender never reached the held source lock"
            g.r.mono[0] = source.snapshot.sampled_at_mono + wait_seconds
    finally:
        release_signing.set()
        thread.join(5)
    assert not thread.is_alive()
    assert len(g.routes.puts) == allowed
    if allowed:
        assert not errors and g.worker._last_published
    else:
        assert len(errors) == 1 and isinstance(errors[0], _Obsolete)
        assert not g.worker._last_published


@pytest.mark.parametrize("boundary", ["compute", "fanout"])
def test_final_source_fence_rejects_snapshot_invalidated_during_dispatch(
    signed_runtime, monkeypatch, boundary
):
    g = signed_runtime
    source = append_facts(g)
    work, fence = select(g)
    entered, release = Event(), Event()
    computed = g.r.metrics.snapshot

    def held_snapshot(*args):
        result = computed(*args)
        entered.set()
        assert release.wait(5)
        return result

    def held_subscriber(snapshot):
        entered.set()
        assert release.wait(5)

    if boundary == "compute":
        monkeypatch.setattr(g.r.metrics, "snapshot", held_snapshot)
    else:
        g.r.coordinator.subscribe_fleet(held_subscriber)
    dispatcher = Thread(target=lambda: g.r.coordinator.dispatch_once(0))
    dispatcher.start()
    try:
        assert entered.wait(5)
        g.r.roster[:] = [GENERIC]
        g.r.discovery.scan_once()
        assert not source.is_current()
    finally:
        release.set()
        dispatcher.join(5)
    assert not dispatcher.is_alive()
    with pytest.raises(_Obsolete):
        g.worker._execute(work, fence)
    assert not g.routes.puts
    assert not g.r.tickets[-1].is_current()


def test_held_http_does_not_block_actual_log_consumption(signed_runtime):
    g = signed_runtime
    original = append_facts(g, OUTGOING_DAMAGE_LINE)
    work, fence = select(g)
    g.transport.hold = ("PUT", "/api/fleet/v2/snapshot")
    thread, errors = run_selected(g, work, fence)
    try:
        assert g.transport.entered.wait(5)
        g.r.mono[0] += 1
        newer = append_facts(g, DAMAGE_LINE)
        assert newer is not original
        assert newer.snapshot.sampled_at_mono > original.snapshot.sampled_at_mono
        assert newer.snapshot.rows[0].incoming_dps == 14
        assert original.snapshot.rows[0].incoming_dps == 0
        assert g.worker._latest is newer and original.is_current()
    finally:
        g.transport.release.set()
        thread.join(5)
    assert not thread.is_alive() and errors == []
    assert g.routes.puts[0].rows[0].incoming_dps == 0
    g.r.mono[0] += 0.5
    g.worker._execute(*select(g))
    assert g.routes.puts[-1].rows[0].incoming_dps == 14


def test_close_precedes_join_and_late_real_worker_completion_is_fenced(
    signed_runtime, monkeypatch
):
    g = signed_runtime
    source = append_facts(g)
    g.transport.hold = ("PUT", "/api/fleet/v2/snapshot")
    monkeypatch.setattr(g.worker, "_thread_factory", Thread)
    turn_done = Event()
    iterate, reply = g.worker._iterate, g.transport.reply

    def observed_iteration():
        result = iterate()
        turn_done.set()
        return result

    def observed_reply(request):
        result = reply(request)
        if request.method == "PUT" and request.full_url.endswith("/snapshot"):
            turn_done.set()
        return result

    monkeypatch.setattr(g.worker, "_iterate", observed_iteration)
    monkeypatch.setattr(g.transport, "reply", observed_reply)
    assert g.worker.start()
    try:
        # Advance only after a real completed iteration. No fake completion,
        # secondary signed lane, or elapsed wall-time sleep drives this owner.
        for _ in range(12):
            assert turn_done.wait(5)
            turn_done.clear()
            if g.routes.puts:
                break
            g.r.mono[0] += 0.5
            g.worker._pending.set()
        assert g.transport.entered.wait(5)
        owner = g.worker._worker
        g.r.coordinator.close_source_admission()
        joined = []
        join = owner.join

        def observe_join(timeout=None):
            joined.append(not source.is_current())
            return join(timeout)

        monkeypatch.setattr(owner, "join", observe_join)
        assert g.worker.stop(timeout=0) is False
        assert joined == [True]
        assert g.worker._worker is owner and not g.worker.start()
        assert not source.is_current()
    finally:
        g.transport.release.set()
        assert g.worker.stop(timeout=5)
    assert not g.worker._last_published
    assert len(g.routes.puts) == 1
    g.r.coordinator.reconcile()
    assert not source.is_current()


def test_poisoned_real_provider_does_not_strand_authorized_read_or_off(
    signed_runtime, monkeypatch
):
    g = signed_runtime
    source = append_facts(g)

    def fail_consume(envelope):
        raise ValueError("injected real metrics consume failure")

    with monkeypatch.context() as patch:
        patch.setattr(g.r.metrics, "consume", fail_consume)
        g.r.stream.request_source("Alice")
        g.r.coordinator.dispatch_once(0)
    assert g.r.authority._poison_reason and not source.is_current()
    g.r.coordinator.dispatch_once(0)
    assert not g.r.tickets[-1].is_current()
    before = len(g.transport.requests)
    g.worker._execute(*select(g, "read_snapshot"))
    assert any(
        request.method == "GET" and request.full_url.endswith("/snapshot")
        for request in g.transport.requests[before:]
    )
    assert not g.routes.puts
    assert g.worker.request_participation(
        False, expected_generation=1, binding=g.worker.status().metadata.binding
    )
    for _ in range(12):
        g.worker.iterate_once()
        g.r.mono[0] += 0.5
        if not g.routes.participation.enabled:
            break
    assert not g.routes.participation.enabled
    assert g.store.load().pending_participation is None
    assert g.worker.status().participation == "acknowledged"
    assert g.r.authority._poison_reason and not source.is_current()


@pytest.mark.parametrize("operation", ["read_snapshot", "fetch_device"])
def test_slow_complete_client_return_refuses_timing_without_rejuvenation(
    signed_runtime, operation
):
    g = signed_runtime
    if operation == "fetch_device":
        # Bring the existing periodic class due; do not alter its authority or
        # fabricate a device result to test the full real-client return boundary.
        g.worker._due["device"] = g.r.mono[0]
    work, fence = select(g, operation)
    before = g.context._state
    assert before.receiver.payload is not None
    display = RemoteFleetStore()
    display.replace(before.receiver.payload)
    assert display.current(g.r.mono[0]), "positive control must still be visible"
    # A normal prior bound GET accepted None versus zero without coercion.
    assert before.receiver.payload.rows
    remote = before.receiver.payload.rows[0]
    assert (remote.outgoing_dps, remote.incoming_dps) == (None, 0)
    start = g.r.mono[0]
    g.transport.read_delay = 6.812
    g.worker._execute(work, fence)
    assert g.r.mono[0] - start == pytest.approx(6.812)
    assert g.transport.responses[-1].reads
    assert g.context._state is before  # anchor, diagnostic, last-R and history atomic
    assert g.worker._scheduler.deadlines["read"] == g.r.mono[0] + 0.5
    assert g.worker._control_auth_current_locked()
    assert g.worker.status().metadata.device_id == UUID
    # Identity is still authenticated; body latency is not an authorization error.
    assert g.worker.status().detail not in ("unauthorized", "malformed_response")
    assert display.current(g.r.mono[0]) == ()


def test_same_worker_restart_preserves_pins_history_and_attempt_cadence(signed_runtime):
    g = signed_runtime
    source = append_facts(g)
    g.worker._execute(*select(g))
    pins, state = g.context._publisher, g.context._state
    stage_floor = g.context._next_stage_at
    deadlines = dict(g.worker._scheduler.deadlines)
    count = len(g.routes.puts)
    assert g.worker.start() and g.worker.stop() and g.worker.start()
    assert g.worker._timing_context is g.context
    assert g.context._publisher is pins and g.context._state is state
    assert g.context._next_stage_at == stage_floor
    assert g.worker._scheduler.deadlines == deadlines
    g.worker.submit(source)
    g.worker.iterate_once()
    assert len(g.routes.puts) == count
    assert source.is_current()


def test_real_no_log_unknown_is_not_fabricated_zero_publication(signed_runtime):
    g = signed_runtime
    g.r.path.unlink()
    g.r.stream.scan_once(g.r.stream._utc_now())
    g.r.coordinator.dispatch_once(0)
    source = g.r.tickets[-1]
    assert source.is_current()
    assert (source.snapshot.rows[0].dps, source.snapshot.rows[0].incoming_dps) == (
        None,
        None,
    )
    assert not any(
        work.operation == "publish_snapshot" for work in g.worker._work(True)
    )
    assert not g.routes.puts
    # A genuinely new file, not a known path reopened at EOF, restores measured 0.
    g.r.path = _log(g.r.path.parent, "Alice", stem="new-zero-log")
    source = append_facts(g, OUTGOING_DAMAGE_LINE.replace("299", "0"))
    assert (source.snapshot.rows[0].dps, source.snapshot.rows[0].incoming_dps) == (0, 0)
    g.worker._execute(*select(g))
    assert g.routes.puts[-1].rows[0].outgoing_dps == 0
    assert g.routes.puts[-1].rows[0].incoming_dps == 0
