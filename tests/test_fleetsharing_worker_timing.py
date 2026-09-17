"""S4-C runtime timing: real worker, signed client, DTOs and atomic state file."""

import threading
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from fractions import Fraction

import pytest

from tests.fleetsharing_worker_control_helpers import ControlRelay
from tests.test_fleetsharing_timing_receiver import wire_row
from tests.test_fleetsharing_worker import NOW
from tests.test_fleetsharing_worker_state4 import file_rig
from wingman.fleetsharing.model import TimedSnapshot


class TimingRelay(ControlRelay):
    def __init__(self, worker, store):
        super().__init__(worker, store)
        self.rows = [
            wire_row(
                effects=[
                    {"kind": "SCRAM", "observations": [{"name": "A", "age_ms": 600}]},
                    {"kind": "NEUT", "observations": [{"name": None, "age_ms": 700}]},
                ]
            )
        ]
        self.db_delta = 0

    def reply(self, request, saved):
        db = 100000 + int((self.worker._clock() - 10) * 1000) + self.db_delta
        if request.full_url.endswith("/snapshot"):
            assert request.method == "GET"  # This fixture never certifies D's PUT.
            return {"protocol": 2, "server_time_ms": db, "rows": self.rows}, 200
        self.device = replace(self.device, server_time_ms=db)
        return super().reply(request, saved)


def timing_rig(tmp_path):
    worker, _, store, mono = file_rig(tmp_path, enabled=True)
    mono[0] = 10.0
    worker._utc_clock = lambda: NOW + timedelta(seconds=mono[0] - 10)
    relay = TimingRelay(worker, store)
    events = []
    worker.subscribe_remote(events.append)
    return worker, relay, store, mono, events


def test_current_shared_read_without_submit_publishes_exact_immutable_payload(tmp_path):
    worker, relay, store, mono, events = timing_rig(tmp_path)
    assert worker._latest is None
    worker.iterate_once()  # Real current Device GET, not persisted-ID authority.
    assert store.load().device_id == relay.device.device_id
    mono[0] = 10.5
    worker.iterate_once()
    assert [request.full_url.rsplit("/", 1)[-1] for request, _ in relay.calls] == [
        "device",
        "snapshot",
    ]
    replacements = [event for event in events if event.kind == "replace"]
    assert len(replacements) == 1
    event = replacements[0]
    assert isinstance(getattr(event, "payload", None), TimedSnapshot)
    row = event.payload.rows[0]
    assert (row.outgoing_dps, row.incoming_dps) == (None, 0)
    assert row.sampled_at_mono == Fraction(101, 10)
    assert row.activity_expires_at_mono == Fraction(399, 10)
    assert row.effects[0].observations[0].expires_at_mono == Fraction(397, 10)
    assert row.effects[1].observations[0].expires_at_mono == Fraction(198, 5)
    assert event.binding == worker.status().metadata.binding
    assert worker._timing_context._state.receiver.payload is event.payload
    assert len(worker._timing_context._state.exchanges) == 2
    with pytest.raises(FrozenInstanceError):
        event.payload = None
    assert worker._latest is None


def test_obsolete_contradiction_during_detached_evaluation_cannot_poison_context(
    tmp_path, monkeypatch
):
    from wingman.fleetsharing import timing

    worker, relay, _, mono, events = timing_rig(tmp_path)
    worker.iterate_once()
    context = worker._timing_context
    before = context._state
    relay.db_delta = -1000  # Whole valid reply; DB regression if CURRENT.
    mono[0] = 10.5
    entered, release = threading.Event(), threading.Event()
    waited = []
    returned = []
    relay.after = lambda request, saved: returned.append(request)
    ratio = timing.Fraction

    def blocked_ratio(value=0, *args):
        result = ratio(value, *args)
        # Enter the real evaluator, after the client fully returned. No callback
        # assertion can be swallowed: the parent witnesses both sides here.
        if (
            returned
            and value == 10.5
            and context._snapshot_started_at is None
            and not entered.is_set()
        ):
            entered.set()
            waited.append(release.wait(5))
        return result

    monkeypatch.setattr(timing, "Fraction", blocked_ratio)
    thread = threading.Thread(target=worker.iterate_once)
    thread.start()
    try:
        assert entered.wait(5)
        assert worker.request_pairing(mode="upgrade")
        release.set()
        thread.join(5)
        assert not thread.is_alive() and waited == [True]
        assert context._state is before
        assert not context._inconsistent, "obsolete contradiction poisoned context"
        assert not [e for e in events if e.kind == "replace"]
        assert context._scheduler.deadlines["read"] == 11.0
    finally:
        release.set()
        thread.join(5)


REASONS = (
    "clock_inconsistent",
    "db_continuity_lost",
    "elapsed_continuity_lost",
    "elapsed_reset",
)


@pytest.mark.parametrize("reason", REASONS)
def test_public_loss_synchronously_closes_timeproof_and_orders_fixed_loss_after_http(
    tmp_path, reason
):
    worker, relay, _, mono, events = timing_rig(tmp_path)
    worker.iterate_once()
    mono[0] = 10.5
    worker.iterate_once()
    context = worker._timing_context
    before, pins = context._state, context._publisher
    assert before.anchor is not None and before.receiver.payload is not None
    entered, release = threading.Event(), threading.Event()
    waited = []

    def hold(request, saved):
        entered.set()
        waited.append(release.wait(5))

    relay.before = hold
    mono[0] = 11.5
    thread = threading.Thread(target=worker.iterate_once)
    thread.start()
    try:
        assert entered.wait(5)
        mono[0] = 12.0
        worker.fence_timing(reason)
        assert worker._control_time_fenced, "public signal left B proof open"
        assert context._state is before and context._publisher is pins
        assert context._publisher_cutoff is None
        assert events[-1].kind == "clear" and events[-1].payload is None
        clear_order = events[-1].order
        mono[0] = 20.0
        worker.fence_timing(reason)  # Repeated signals cannot move F.
        release.set()
        thread.join(5)
        assert not thread.is_alive() and waited == [True]
        assert context._state.exchanges is before.exchanges
        assert context._state.anchor is None
        assert context._state.receiver.payload is None
        assert context._state.receiver.recovering
        assert context._publisher is pins
        assert context._publisher_cutoff == (
            Fraction(12)
            if reason in ("clock_inconsistent", "db_continuity_lost")
            else None
        ), "loss cutoff moved after its first signal"
        assert not [e for e in events if e.order > clear_order and e.kind == "replace"]
        assert context._scheduler.deadlines["read"] == 20.5
        assert worker.stop() and worker.start()
        relay.before = None
        mono[0] = 51.0
        for _ in range(12):
            worker.iterate_once()
            mono[0] += 0.5
        assert worker._timing_context is context
        assert worker._control_time_fenced and context._state.anchor is None, (
            "restart reopened timing"
        )
        assert context._state.exchanges is before.exchanges
        assert not [e for e in events if e.order > clear_order and e.kind == "replace"]
    finally:
        release.set()
        thread.join(5)
        assert worker.stop()


@pytest.mark.parametrize("reason", REASONS)
def test_public_loss_closes_permanently_when_cutoff_clock_raises(
    tmp_path, caplog, reason
):
    from tests.test_fleetsharing_worker import (
        DEVICE,
        PAIRED_STATE,
        UUID,
        FakeRelayClient,
        _worker,
    )
    from tests.test_fleetsharing_worker_state4 import FileStore
    from wingman.fleetsharing import protocol as p

    store = FileStore(tmp_path / "sharing.json")
    store.save(PAIRED_STATE)
    mono, fail_once, failures = [10.0], [False], []

    def clock():
        if fail_once[0]:
            fail_once[0] = False
            failures.append(True)
            raise RuntimeError("private clock failure detail")
        return mono[0]

    worker = _worker(
        FakeRelayClient(device=DEVICE),
        store=store,
        clock=clock,
        utc_clock=lambda: NOW + timedelta(seconds=mono[0] - 10),
    )
    relay = TimingRelay(worker, store)
    events = []
    worker.subscribe_remote(events.append)
    worker.iterate_once()
    mono[0] = 10.5
    worker.iterate_once()
    context = worker._timing_context
    before, pins, generation = (
        context._state,
        context._publisher,
        context._timing_generation,
    )
    assert before.anchor is not None and before.receiver.payload is not None
    command = p.AutomaticCommand(UUID, "1970-01-01T00:00:00.000Z", True, 0, 0)
    with worker._lock:
        assert worker._on_expired_proven_locked(command)
    entered, release = threading.Event(), threading.Event()
    waited = []

    def hold(request, saved):
        entered.set()
        waited.append(release.wait(5))

    relay.before = hold
    mono[0] = 11.5
    thread = threading.Thread(target=worker.iterate_once)
    thread.start()
    try:
        assert entered.wait(5)
        assert relay.calls[-1][0].full_url.endswith("/snapshot")
        mono[0] = 12.0
        fail_once[0] = True
        worker.fence_timing(reason)
        assert failures == (
            [True] if reason in ("clock_inconsistent", "db_continuity_lost") else []
        )
        fail_once[0] = False  # Untrusted elapsed reasons must not sample at all.
        with worker._lock:
            assert not worker._on_expired_proven_locked(command), (
                "clock failure left B proof usable"
            )
        notice = context._timing_loss
        assert notice is not None, "clock failure left timing admission open"
        assert notice.reason == reason and notice.cutoff is None
        assert context._timing_generation == generation + 1
        assert context._state is before and context._publisher is pins
        assert context._publisher_cutoff is None and not context._loss_applied
        assert events[-1].kind == "clear" and events[-1].payload is None
        clear_order = events[-1].order
        mono[0] = 12.5  # Timely valid reply, NOT excluded by the 5s admission bound.
        worker.fence_timing("db_continuity_lost")
        assert context._timing_loss is notice and notice.cutoff is None
        assert context._timing_generation == generation + 1
        assert context._state is before and context._publisher is pins
        release.set()
        thread.join(5)
        assert not thread.is_alive() and waited == [True]
        assert context._state.exchanges is before.exchanges, (
            "clock failure allowed late timing commit"
        )
        assert context._state.anchor is None and context._state.receiver.payload is None
        assert context._state.receiver.recovering and context._loss_applied
        assert context._publisher is pins and context._publisher_cutoff is None
        assert context._snapshot_started_at is None
        assert context._scheduler.deadlines["read"] == 13.0
        assert not [e for e in events if e.order > clear_order and e.kind == "replace"]
        assert worker.stop() and worker.start()
        relay.before = None
        mono[0] = 51.0
        for _ in range(12):
            worker.iterate_once()
            mono[0] += 0.5
        assert (
            worker._timing_context is context
            and worker._clock is context._clock is clock
        )
        assert worker._control_time_fenced and context._timing_loss is notice
        assert notice.cutoff is None and context._publisher_cutoff is None
        assert (
            context._state.exchanges is before.exchanges
            and context._state.anchor is None
        )
        assert not [e for e in events if e.order > clear_order and e.kind == "replace"]
        assert "private clock failure detail" not in caplog.text
        assert "private clock failure detail" not in repr(worker.status())
    finally:
        fail_once[0] = False
        release.set()
        thread.join(5)
        assert worker.stop()


def test_authenticated_scope_is_not_saved_id_and_survives_same_key_pairing(tmp_path):
    from tests.test_fleetsharing_worker import DEVICE
    from wingman.fleetsharing import state as s

    worker, relay, store, mono, _ = timing_rig(tmp_path)
    s.save(store.path, replace(store.load(), device_id=DEVICE.device_id.upper()))
    context = worker._timing_context
    assert getattr(context, "_authenticated_scope", None) is None
    worker.iterate_once()
    scope = getattr(context, "_authenticated_scope", None)
    assert scope is not None
    assert scope[:2] == (worker.status().metadata.binding, DEVICE.device_id.lower())
    assert scope[2] is context._db_continuity_token
    assert scope[3] is context._elapsed_lifetime_token
    mono[0] = 10.5
    worker.iterate_once()
    receiver, pins = context._state.receiver, context._publisher
    assert worker.request_pairing(mode="upgrade")
    relay.approved = True
    for _ in range(12):
        mono[0] += 0.5
        worker.iterate_once()
    assert any("pairing-requests/" in r.full_url for r, _ in relay.calls)
    assert store.load().pending_pairing is None
    assert context._authenticated_scope is scope
    assert context._publisher is pins
    assert context._state.receiver.records[:1] == receiver.records


@pytest.mark.parametrize("stage", ["body", "decode"])
@pytest.mark.parametrize(
    "receipt,admitted", [(15.5, True), (15.500000000000002, False), (17.312, False)]
)
def test_full_real_client_body_and_codec_return_bound(
    tmp_path, monkeypatch, stage, receipt, admitted
):
    from tests.test_fleetsharing_client import Response
    from wingman.fleetsharing import protocol as p

    worker, relay, _, mono, events = timing_rig(tmp_path)
    worker.iterate_once()
    before = worker._timing_context._state
    mono[0] = 10.5
    if stage == "body":
        read = Response.read

        def delayed_read(response, *args):
            result = read(response, *args)
            mono[0] = receipt
            return result

        monkeypatch.setattr(Response, "read", delayed_read)
    else:
        parse = p.parse_snapshot

        def delayed_parse(value):
            result = parse(value)
            mono[0] = receipt
            return result

        monkeypatch.setattr(p, "parse_snapshot", delayed_parse)
    worker.iterate_once()
    context = worker._timing_context
    assert len(relay.calls) == 2
    assert bool([e for e in events if e.kind == "replace"]) is admitted
    assert (context._state is not before) is admitted
    if admitted:
        assert context._state.anchor.received_at == Fraction(receipt)
        assert context._state.receiver.payload.rows[0].sampled_at_mono == Fraction(
            101, 10
        )
    assert context._scheduler.deadlines["read"] == receipt + 0.5
    assert context._snapshot_started_at is None


@pytest.mark.parametrize("fault", ["malformed", "binding", "overflow"])
def test_snapshot_refusal_never_partially_installs_anchor_history_or_payload(
    tmp_path, monkeypatch, fault
):
    from tests.test_fleetsharing_client import framing_headers
    from wingman.fleetsharing import timing

    worker, relay, _, mono, events = timing_rig(tmp_path)
    worker.iterate_once()
    mono[0] = 10.5
    worker.iterate_once()
    before = worker._timing_context._state
    old_events = tuple(events)
    if fault == "malformed":
        relay.rows[0]["effects"][0]["observations"][0]["age_ms"] = 299999
    elif fault == "overflow":
        monkeypatch.setattr(timing, "LIMITS", {**timing.LIMITS, "receiver_capacity": 1})
    else:
        transport = relay.transport

        def wrong_binding(request, timeout):
            result = transport(request, timeout)
            result.headers = framing_headers("0" * 64)
            return result

        worker._client._transport = wrong_binding
    mono[0] = 11.5
    worker.iterate_once()
    assert len(relay.calls) == 3
    assert worker._timing_context._state is before, "refusal partly committed timing"
    assert tuple(events) == old_events
    assert not worker._timing_context._inconsistent
    assert worker._scheduler.deadlines["read"] == 12


@pytest.mark.parametrize("reason", REASONS)
def test_fenced_context_cannot_reopen_with_another_worker(tmp_path, reason):
    from tests.test_fleetsharing_worker import DEVICE, FakeRelayClient, _worker

    worker, _, store, mono, _ = timing_rig(tmp_path)
    worker.iterate_once()
    context = worker._timing_context
    worker.fence_timing(reason)
    assert worker.stop()
    other = _worker(
        FakeRelayClient(device=DEVICE),
        store=store,
        timing_context=context,
        utc_clock=worker._utc_clock,
    )
    replacement = TimingRelay(other, store)
    events = []
    other.subscribe_remote(events.append)
    for _ in range(10):
        mono[0] += 0.5
        other.iterate_once()
    assert replacement.calls  # Current authenticated Device response really runs.
    assert other._control_time_fenced, "second worker reopened B proof"
    assert context._state.anchor is None
    assert not [e for e in events if e.kind == "replace"]
    assert other.stop()


@pytest.mark.parametrize("reason", REASONS)
def test_public_loss_closes_existing_db_proof_before_blocked_lane_can_supersede_on(
    tmp_path, reason
):
    from tests.test_fleetsharing_worker import DATE, UUID, drive
    from tests.test_fleetsharing_worker_automatic import automatic_rig
    from wingman.fleetsharing import protocol as p
    from wingman.fleetsharing import state as s

    command = p.AutomaticCommand(UUID, DATE, True, 0, 0)
    pending = s.PendingAutomatic(
        command, True, s.CancelAfterOn("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", DATE)
    )
    worker, store, mono, _, attempts, calls = automatic_rig(tmp_path, pending)
    mono[0] = 1060.0
    drive(worker, mono, 5)
    with worker._lock:
        assert worker._on_expired_proven_locked(command)
    entered, release = threading.Event(), threading.Event()
    waited = []
    transport = worker._client._transport

    def hold(request, timeout):
        entered.set()
        waited.append(release.wait(5))
        return transport(request, timeout)

    worker._client._transport = hold
    binding = worker.status().metadata.binding
    assert worker.request_automatic_status(binding=binding)
    thread = threading.Thread(target=worker.iterate_once)
    thread.start()
    try:
        assert entered.wait(5)
        worker.fence_timing(reason)
        with worker._lock:
            assert not worker._on_expired_proven_locked(command), (
                "public loss left DB proof usable"
            )
        assert worker.request_automatic(
            False,
            expected_generation=0,
            expected_revision=0,
            binding=binding,
            supersedes=pending,
        )
        release.set()
        thread.join(5)
        assert not thread.is_alive() and waited == [True]
        worker._client._transport = transport
        drive(worker, mono, 6)
        assert store.load().automatic.pending == pending
        assert not attempts and worker._latest is None
        assert any(r.full_url.endswith("automatic-verification") for r, _ in calls)
    finally:
        release.set()
        thread.join(5)


@pytest.mark.parametrize("reason", REASONS)
@pytest.mark.parametrize("recover", [False, True])
def test_public_timing_loss_does_not_strand_real_off_stop_status_and_receipts(
    tmp_path, reason, recover
):
    from tests.test_fleetsharing_worker import DATE, DEVICE, UUID, drive
    from tests.test_fleetsharing_worker_automatic import ON
    from wingman.fleetsharing import protocol as p
    from wingman.fleetsharing import state as s

    worker, _, store, mono = file_rig(tmp_path)
    off = p.AutomaticCommand(UUID, DATE, False, 1, 1)
    stop = p.SourceStop(
        source_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        expected_generation=0,
        request_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        intent_created_at=DATE,
        expected_automatic=None,
    )
    # Persist complete current control DTOs before the real owner loads them.
    saved = replace(
        store.load(),
        device_id=UUID,
        automatic=s.AutomaticState(ON, s.PendingAutomatic(off, True)),
        pending_source_commands=(stop,),
    )
    s.save(store.path, s.replace_session(saved, None) if recover else saved)
    relay = ControlRelay(worker, store)
    relay.consent = ON
    relay.device = replace(
        DEVICE,
        feature_enabled=False,
        session_approved_capabilities=(),
        acknowledged_capabilities=(),
        participation=p.Participation(False, 1),
    )
    worker.fence_timing(reason)
    worker.resume_pending()
    drive(worker, mono, 18)
    saved = store.load()
    assert saved.automatic.pending is None and not saved.pending_source_commands
    assert saved.automatic.last_result.receipt.command == off
    assert relay.receipts[stop.request_id]["command"] == p.source_command_body(stop)
    assert worker._control_time_fenced and worker._latest is None
    assert any("/receipts/" in r.full_url for r, _ in relay.calls)
    assert not any(
        r.full_url.endswith("/snapshot")
        or (r.full_url.endswith("/device") and r.method == "PUT")
        for r, _ in relay.calls
    )
    if recover:
        paths = [r.full_url for r, _ in relay.calls]
        completed = next(
            i for i, path in enumerate(paths) if "recovery-challenges/" in path
        )
        terminal = max(i for i, (r, _) in enumerate(relay.calls) if r.method == "PUT")
        assert not any(path.endswith("/device") for path in paths[completed:terminal])


@pytest.mark.parametrize("boundary", ["save", "unwrap", "sign", "after_hook"])
def test_public_loss_at_real_start_boundaries_prevents_timing_http_or_completion(
    tmp_path, monkeypatch, boundary
):
    from wingman.fleetsharing import crypto
    from wingman.fleetsharing import state as s

    worker, relay, _, mono, events = timing_rig(tmp_path)
    worker.iterate_once()
    context = worker._timing_context
    baseline = context._state.exchanges
    seen = []

    def lose():
        seen.append(True)
        worker.fence_timing("db_continuity_lost")

    if boundary == "save":
        write = s.atomicio.write_atomic

        def signal_save(*args):
            lose()
            return write(*args)

        monkeypatch.setattr(s.atomicio, "write_atomic", signal_save)
    elif boundary == "unwrap":
        unwrap = worker._unwrap_private_key

        def signal_unwrap(value):
            lose()
            return unwrap(value)

        worker._unwrap_private_key = signal_unwrap
    elif boundary == "sign":
        sign = crypto.sign_request

        def signal_sign(*args):
            result = sign(*args)
            lose()
            return result

        monkeypatch.setattr(crypto, "sign_request", signal_sign)
    else:
        relay.before = lambda request, saved: lose()
    mono[0] = 10.5
    worker.iterate_once()
    assert seen == [True]
    assert len(relay.calls) == (2 if boundary == "after_hook" else 1)
    assert context._state.exchanges is baseline and context._state.anchor is None
    assert not [e for e in events if e.kind == "replace"]
    assert context._scheduler.deadlines["read"] == (
        11.0 if boundary == "after_hook" else 10.5
    )
    assert context._snapshot_started_at is None


def test_loss_clear_overtakes_blocked_replace_callback_without_reopening_display(
    tmp_path,
):
    worker, _, _, mono, _ = timing_rig(tmp_path)
    worker.iterate_once()
    entered, release = threading.Event(), threading.Event()
    waited, seen = [], []

    def block(event):
        if event.kind == "replace":
            entered.set()
            waited.append(release.wait(5))

    worker.subscribe_remote(block)
    worker.subscribe_remote(seen.append)
    mono[0] = 10.5
    thread = threading.Thread(target=worker.iterate_once)
    thread.start()
    try:
        assert entered.wait(5)
        worker.fence_timing("elapsed_reset")
        assert len(seen) == 1 and seen[0].kind == "clear" and seen[0].payload is None
        release.set()
        thread.join(5)
        assert not thread.is_alive() and waited == [True]
        assert len(seen) == 1
    finally:
        release.set()
        thread.join(5)


def test_different_authenticated_origin_refuses_old_timing_without_rebinding(tmp_path):
    worker, relay, _, mono, events = timing_rig(tmp_path)
    worker.iterate_once()
    mono[0] = 10.5
    worker.iterate_once()
    context = worker._timing_context
    scope, before = context._authenticated_scope, context._state
    event_count = len(events)
    relay.approval_url = "https://other.test/approve"
    relay.approved = True
    assert worker.request_pairing(mode="fresh", configured_origin="https://other.test")
    for _ in range(14):
        mono[0] += 0.5
        worker.iterate_once()
    assert worker.status().metadata.paired_origin == "https://other.test"
    assert any(
        r.full_url == "https://other.test/api/fleet/v2/device" for r, _ in relay.calls
    )
    assert context._authenticated_scope is scope and context._state is before, (
        "new origin reidentified retained timing"
    )
    assert worker.status().detail == "timing_scope_mismatch"
    assert not [e for e in events[event_count:] if e.kind == "replace"]


def test_fence_during_real_expensive_projection_discards_the_whole_candidate(
    tmp_path, monkeypatch
):
    from wingman.fleetsharing import timing

    worker, _, _, mono, events = timing_rig(tmp_path)
    worker.iterate_once()
    context = worker._timing_context
    before = context._state
    entered, release = threading.Event(), threading.Event()
    waited = []
    payload = timing.TimedSnapshot

    def project(*args):
        result = payload(*args)
        entered.set()
        waited.append(release.wait(5))
        return result

    monkeypatch.setattr(timing, "TimedSnapshot", project)
    mono[0] = 10.5
    thread = threading.Thread(target=worker.iterate_once)
    thread.start()
    try:
        assert entered.wait(5)
        worker.fence_timing("db_continuity_lost")
        assert context._state is before
        release.set()
        thread.join(5)
        assert not thread.is_alive() and waited == [True]
        assert context._state.exchanges is before.exchanges, (
            "late candidate installed diagnostic"
        )
        assert context._state.receiver.last_server_time_ms is None
        assert context._state.anchor is None
        assert not [e for e in events if e.kind == "replace"]
    finally:
        release.set()
        thread.join(5)


def test_shared_only_permission_receives_combat_without_automatic_or_local_publication(
    tmp_path,
):
    from wingman.fleetsharing import protocol as p

    worker, relay, _, mono, events = timing_rig(tmp_path)
    shared = (p.SHARED_CAPABILITY,)
    relay.device = replace(
        relay.device,
        approved_capabilities=shared,
        session_approved_capabilities=shared,
        acknowledged_capabilities=shared,
    )
    worker.iterate_once()
    mono[0] = 10.5
    worker.iterate_once()
    assert [request.full_url.rsplit("/", 1)[-1] for request, _ in relay.calls] == [
        "device",
        "snapshot",
    ]
    assert events[-1].kind == "replace" and events[-1].payload.rows
    assert worker._latest is None and not relay.consent.enabled


@pytest.mark.parametrize("operation", ["device", "ack"])
def test_slow_valid_device_facts_are_authorized_but_never_clock_anchors(
    tmp_path, monkeypatch, operation
):
    import json

    from tests.test_fleetsharing_client import Response

    worker, relay, store, mono, events = timing_rig(tmp_path)
    if operation == "ack":
        relay.device = replace(relay.device, acknowledged_capabilities=())
        worker.iterate_once()
        mono[0] = 10.5
        reply = relay.reply

        def acknowledge(request, saved):
            if request.method == "PUT" and request.full_url.endswith("/device"):
                relay.device = replace(
                    relay.device,
                    acknowledged_capabilities=tuple(
                        json.loads(request.data)["capabilities"]
                    ),
                )
            return reply(request, saved)

        relay.reply = acknowledge
    context = worker._timing_context
    before = context._state
    started = mono[0]
    read = Response.read

    def slow(response, amount=-1):
        result = read(response, amount)
        mono[0] = started + 6.812
        return result

    monkeypatch.setattr(Response, "read", slow)
    worker.iterate_once()
    assert relay.calls[-1][0].method == ("GET" if operation == "device" else "PUT")
    assert relay.calls[-1][0].full_url.endswith("/device")
    assert store.load().device_id == relay.device.device_id
    assert (
        store.load().acknowledged_capabilities == relay.device.acknowledged_capabilities
    )
    with worker._lock:
        assert worker._control_auth_current_locked(), (
            "slow authenticated facts were discarded"
        )
    assert worker._control_db_fact[-1] == 100000 + int((started - 10) * 1000)
    assert context._state is before, "slow valid device installed timing"
    assert context._scheduler.deadlines["read"] == mono[0] + 0.5
    assert not [event for event in events if event.kind == "replace"]


def test_device_ack_snapshot_share_actual_completion_bucket_despite_status_latency(
    tmp_path, monkeypatch
):
    import json

    from tests.test_fleetsharing_client import Response

    worker, relay, _, mono, events = timing_rig(tmp_path)
    relay.device = replace(relay.device, acknowledged_capabilities=())
    reply = relay.reply
    wire = []

    def responding(request, saved):
        wire.append((request.method, request.full_url.rsplit("/", 1)[-1], mono[0]))
        if request.method == "PUT":
            relay.device = replace(
                relay.device,
                acknowledged_capabilities=tuple(
                    json.loads(request.data)["capabilities"]
                ),
            )
        return reply(request, saved)

    relay.reply = responding
    read = Response.read

    def full_body(response, amount=-1):
        result = read(response, amount)
        mono[0] += 0.2
        return result

    monkeypatch.setattr(Response, "read", full_body)
    delayed = []

    def status_delay(status):
        if status.observed_participation is not None and wire and not delayed:
            delayed.append(mono[0])
            mono[0] += 0.3

    worker.subscribe_status(status_delay)
    worker.iterate_once()
    assert delayed == [10.2]  # Externally checked, not inside catch-all callback.
    context = worker._timing_context
    assert context._state.anchor.received_at == Fraction(10.2)
    assert context._scheduler.deadlines["read"] == 10.7
    mono[0] = 10.699
    worker.iterate_once()
    assert len(wire) == 1
    mono[0] = 10.7
    worker.iterate_once()
    assert context._scheduler.deadlines["read"] == (10.7 + 0.2) + 0.5
    mono[0] = context._scheduler.deadlines["read"]
    worker.iterate_once()
    assert [(method, path) for method, path, _ in wire] == [
        ("GET", "device"),
        ("PUT", "device"),
        ("GET", "snapshot"),
    ]
    assert len(context._state.exchanges) == 3 and events[-1].kind == "replace"
    assert [e.started_at for e in context._state.exchanges] == [
        Fraction(start) for _, _, start in wire
    ]
    assert [e.received_at for e in context._state.exchanges] == [
        Fraction(start + 0.2) for _, _, start in wire
    ]
    deadline = context._scheduler.deadlines["read"]
    assert worker.stop() and worker.start()
    assert worker._timing_context is context
    assert context._scheduler.deadlines["read"] == deadline
    assert worker.stop()


@pytest.mark.parametrize("reason", REASONS)
def test_same_key_pairing_and_settings_toggles_cannot_unfence_retained_timing(
    tmp_path, reason
):
    worker, relay, _, mono, events = timing_rig(tmp_path)
    worker.iterate_once()
    mono[0] = 10.5
    worker.iterate_once()
    context = worker._timing_context
    scope, exchanges = context._authenticated_scope, context._state.exchanges
    worker.fence_timing(reason)
    boundary = len(events)
    enabled = [False]
    worker._sharing_enabled = lambda: enabled[0]
    worker.iterate_once()
    enabled[0] = True
    relay.approved = True
    assert worker.request_pairing(mode="upgrade")
    for _ in range(14):
        mono[0] += 0.5
        worker.iterate_once()
    assert any("pairing-requests/" in request.full_url for request, _ in relay.calls)
    assert sum(request.full_url.endswith("/device") for request, _ in relay.calls) >= 2
    assert worker._control_time_fenced and context._timing_loss.reason == reason
    assert (
        context._authenticated_scope is scope and context._state.exchanges is exchanges
    )
    assert context._state.anchor is None
    assert not [event for event in events[boundary:] if event.kind == "replace"]


@pytest.mark.parametrize(
    "fault",
    [
        "receipt_before_start",
        "start_before_last_receipt",
        "db_regression",
        "intersection",
    ],
)
def test_automatic_contradiction_preserves_elapsed_trust_classification(
    tmp_path, monkeypatch, fault
):
    from tests.test_fleetsharing_client import Response
    from wingman.fleetsharing import crypto

    worker, relay, _, mono, events = timing_rig(tmp_path)
    worker.iterate_once()  # Current accepted (a=10, r=10, DB=100000).
    context = worker._timing_context
    scope, before, pins = (
        context._authenticated_scope,
        context._state,
        context._publisher,
    )
    mono[0] = 10.5
    reply = relay.reply
    stamps = []
    accept = worker._accept

    def response(request, saved):
        body, code = reply(request, saved)
        if request.full_url.endswith("/snapshot"):
            # DB is independent from the broken local clock. Both local-reset
            # cases have a nondecreasing, otherwise valid authenticated DB value.
            body["server_time_ms"] = {
                "db_regression": 99999,
                "intersection": 100800,
            }.get(fault, 100500)
        return body, code

    def observed(work, result, fence, started, receipt):
        stamps.append((started, receipt, result.server_time_ms))
        return accept(work, result, fence, started, receipt)

    relay.reply = response
    worker._accept = observed
    if fault == "receipt_before_start":
        read = Response.read

        def reset_during_body(response, amount=-1):
            result = read(response, amount)
            mono[0] = 10.25
            return result

        monkeypatch.setattr(Response, "read", reset_during_body)
    elif fault == "start_before_last_receipt":
        sign = crypto.sign_request

        def reset_during_signing(*args):
            result = sign(*args)
            mono[0] = 9.5
            return result

        monkeypatch.setattr(crypto, "sign_request", reset_during_signing)
    worker.iterate_once()
    assert len(relay.calls) == 2 and relay.calls[-1][0].full_url.endswith("/snapshot")
    assert stamps == [
        {
            "receipt_before_start": (10.5, 10.25, 100500),
            "start_before_last_receipt": (9.5, 9.5, 100500),
            "db_regression": (10.5, 10.5, 99999),
            "intersection": (10.5, 10.5, 100800),
        }[fault]
    ]
    elapsed_lost = fault in ("receipt_before_start", "start_before_last_receipt")
    assert context._timing_loss is not None and worker._control_time_fenced
    assert context._inconsistent
    if elapsed_lost:
        assert context._timing_loss.cutoff is None, (
            "detected local regression fabricated comparable F"
        )
        assert context._publisher_cutoff is None
        assert context._timing_loss.reason == "elapsed_reset"
    else:
        assert context._timing_loss.reason == "clock_inconsistent"
        assert context._timing_loss.cutoff == 10.5
        assert context._publisher_cutoff == Fraction(21, 2)
    assert context._state.exchanges is before.exchanges
    assert context._state.anchor is None and context._state.receiver.recovering
    assert context._publisher is pins and context._authenticated_scope is scope
    assert context._snapshot_started_at is None
    assert events[-1].kind == "clear" and not [e for e in events if e.kind == "replace"]
    # Restoring a working clock and starting the same worker is NOT a new model
    # lifetime or a continuity assurance. No old context may obtain a fresh anchor.
    if fault == "receipt_before_start":
        monkeypatch.setattr(Response, "read", read)
    elif fault == "start_before_last_receipt":
        monkeypatch.setattr(crypto, "sign_request", sign)
    worker._accept = accept
    relay.reply = reply
    assert worker.stop() and worker.start()
    mono[0] = 80.0
    for _ in range(6):
        worker.iterate_once()
        mono[0] += 0.5
    assert worker._timing_context is context
    assert (
        context._state.exchanges is before.exchanges and context._state.anchor is None
    )
    assert not [e for e in events if e.kind == "replace"]
    if elapsed_lost:
        assert context._publisher_cutoff is None
    assert worker.stop()
