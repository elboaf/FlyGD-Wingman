"""Real source → dispatcher → metrics proof; no sharing consumer or fake tickets."""

from threading import Event, Thread
from types import SimpleNamespace

import pytest

from tests.test_client_discovery import ALICE, GENERIC
from tests.test_telemetry_gamelogs import NOW, OUTGOING_DAMAGE_LINE, _log
from wingman.telemetry.admission import _SourceAuthority
from wingman.telemetry.clients import ClientDiscovery
from wingman.telemetry.clients import _noop_thread_factory as no_clients
from wingman.telemetry.coordinator import TelemetryCoordinator, _noop_thread_factory
from wingman.telemetry.gamelogs import GameLogStream
from wingman.telemetry.gamelogs import _noop_thread_factory as no_stream
from wingman.telemetry.metrics import FleetMetrics
from wingman.telemetry.model import CombatFact


@pytest.fixture
def real_runtime(tmp_path):
    mono = [1000.0]

    def clock():
        return mono[0]

    roster = [ALICE]
    enabled = [True]
    authority = _SourceAuthority()
    discovery = ClientDiscovery(
        _enumerate_clients=lambda: list(roster),
        _thread_factory=no_clients,
        _source_admission=authority,
    )
    stream = GameLogStream(
        _thread_factory=no_stream,
        _clock=clock,
        _utc_now=lambda: NOW,
        _source_admission=authority,
    )
    metrics = FleetMetrics(_clock=clock, _utc_now=lambda: NOW)
    coordinator = TelemetryCoordinator(
        preview_enabled=lambda: True,
        fleet_enabled=lambda: enabled[0],
        alerts_enabled=lambda: True,
        sharing_enabled=lambda: enabled[0],
        gamelogs_folder=lambda: tmp_path,
        discovery=discovery,
        stream=stream,
        metrics=metrics,
        _thread_factory=_noop_thread_factory,
        _clock=clock,
        _source_admission=authority,
    )
    tickets = []
    coordinator.subscribe_admitted_fleet(tickets.append)
    coordinator.reconcile()
    # Drive startup reset before producing evidence, as the immediate dispatcher
    # can in production. Reset-overlapping evidence is covered separately.
    coordinator.dispatch_once(0)
    discovery.scan_once()
    stream.scan_once(NOW)
    coordinator.dispatch_once(0)
    path = _log(tmp_path, "Alice", OUTGOING_DAMAGE_LINE)
    stream.scan_once(NOW)
    coordinator.dispatch_once(0)
    assert tickets and tickets[-1].is_current()
    yield SimpleNamespace(
        mono=mono,
        roster=roster,
        enabled=enabled,
        authority=authority,
        discovery=discovery,
        stream=stream,
        metrics=metrics,
        coordinator=coordinator,
        tickets=tickets,
        path=path,
    )
    assert coordinator.stop()


def _reset(r):
    # Existing metrics activation transition; Preview/Alerts keep stream alive.
    r.enabled[0] = False
    r.coordinator.reconcile()
    r.coordinator.dispatch_once(0)
    r.enabled[0] = True
    r.coordinator.reconcile()
    r.coordinator.dispatch_once(0)


def test_generic_round_trip_revokes_before_dispatch(real_runtime):
    r = real_runtime
    old = r.tickets[-1]
    r.roster[:] = [GENERIC]
    r.discovery.scan_once()
    assert not old.is_current()
    assert old.snapshot is r.coordinator.snapshot()
    r.roster[:] = [ALICE]
    r.discovery.scan_once()
    r.coordinator.dispatch_once(0)
    assert r.tickets[-1] is not old
    assert r.tickets[-1].is_current()
    assert not old.admit_start(lambda: pytest.fail("obsolete start"))


def test_unchanged_scan_and_facts_keep_original_ticket(real_runtime):
    r = real_runtime
    old = r.tickets[-1]
    r.discovery.scan_once()
    r.stream.scan_once(NOW)
    r.stream.request_source("Alice")
    r.coordinator.dispatch_once(0)
    assert old.is_current()
    assert old.admit_start(lambda: None)
    assert old.admit_start(lambda: None)


@pytest.mark.parametrize("idle", [False, True])
def test_invalidation_during_compute_cannot_seal_snapshot(
    real_runtime, monkeypatch, idle
):
    r = real_runtime
    old = r.tickets[-1]
    before = len(r.tickets)
    compute = r.metrics.snapshot

    def snapshot(*args):
        result = compute(*args)
        r.roster[:] = [GENERIC]
        r.discovery.scan_once()
        return result

    monkeypatch.setattr(r.metrics, "snapshot", snapshot)
    if not idle:
        r.discovery.scan_once()
    r.coordinator.dispatch_once(0)
    assert r.coordinator.snapshot() is not old.snapshot
    assert not old.is_current()
    assert len(r.tickets) == before


@pytest.mark.parametrize("admitted", [False, True])
def test_earlier_subscriber_revokes_original_ticket_without_starving_others(
    real_runtime, admitted
):
    r = real_runtime
    seen = []

    def invalidate(_):
        r.roster[:] = [GENERIC]
        r.discovery.scan_once()
        raise ValueError("isolated subscriber")

    subscribe = (
        r.coordinator.subscribe_admitted_fleet
        if admitted
        else r.coordinator.subscribe_fleet
    )
    subscribe(invalidate)
    r.coordinator.subscribe_admitted_fleet(seen.append)
    r.coordinator.dispatch_once(0)
    assert len(seen) == 1
    assert not seen[0].is_current()
    assert seen[0].snapshot is r.coordinator.snapshot()


def test_same_lifetime_fact_held_across_reset_poison_preserves_legacy_application(
    real_runtime, monkeypatch
):
    r = real_runtime
    held = []
    original = r.coordinator._on_admitted_stream
    monkeypatch.setattr(
        r.coordinator, "_on_admitted_stream", lambda *args: held.append(args)
    )
    with r.path.open("a", encoding="utf-8") as output:
        output.write(OUTGOING_DAMAGE_LINE)
    r.stream.scan_once(NOW)
    assert len(held) == 1 and all(isinstance(e, CombatFact) for e in held[0][0].events)
    lifetime = held[0][1].operation.lifetime
    monkeypatch.setattr(r.coordinator, "_on_admitted_stream", original)
    _reset(r)
    current = r.tickets[-1]
    assert current.is_current()
    assert r.stream._admission_receipt.lifetime is lifetime
    consumed = []
    consume = r.metrics.consume

    def record(envelope):
        consumed.append(envelope.payload)
        consume(envelope)

    monkeypatch.setattr(r.metrics, "consume", record)
    original(*held[0])
    r.coordinator.dispatch_once(0)
    assert consumed == list(held[0][0].events)
    assert not current.is_current()
    assert r.authority._poison_reason
    r.discovery.scan_once()
    r.stream.request_source("Alice")
    r.coordinator.dispatch_once(0)
    assert not r.tickets[-1].is_current()
    _reset(r)
    assert r.tickets[-1].is_current()
    assert not current.is_current()


@pytest.mark.parametrize("failure", ["consume", "reset", "restate", "roster"])
def test_failed_work_stays_poisoned_until_successful_reset_reseed(
    real_runtime, monkeypatch, failure
):
    r = real_runtime
    old = r.tickets[-1]

    def fail(*args):
        raise ValueError("injected model/source failure")

    if failure == "roster":
        target, method = r.discovery, "_snapshot_admission"
    elif failure == "restate":
        target, method = r.stream, "_source_event_locked"
    else:
        target, method = r.metrics, failure
    with monkeypatch.context() as patch:
        patch.setattr(target, method, fail)
        if failure == "consume":
            r.stream.request_source("Alice")
            r.coordinator.dispatch_once(0)
        else:
            _reset(r)
    assert not old.is_current()
    assert r.authority._poison_reason
    r.discovery.scan_once()
    r.coordinator.dispatch_once(0)
    assert not r.tickets[-1].is_current()
    _reset(r)
    assert r.tickets[-1].is_current()


def test_reverse_roster_delivery_skips_old_generation_without_poison(real_runtime):
    r = real_runtime
    entered, release = Event(), Event()
    delivered = []

    def hold(snapshot):
        if snapshot.clients[0].character is None:
            entered.set()
            assert release.wait(5)

    unsubscribe = r.discovery.subscribe(hold)
    r.discovery._subscribe_admission(
        lambda payload, proof: delivered.append((payload, proof))
    )
    r.roster[:] = [GENERIC]
    first = Thread(target=r.discovery.scan_once)
    first.start()
    try:
        assert entered.wait(5)
        r.roster[:] = [ALICE]
        r.discovery.scan_once()
        r.coordinator.dispatch_once(0)
        current = r.tickets[-1]
        assert current.is_current()
    finally:
        release.set()
        first.join(5)
        unsubscribe()
    assert not first.is_alive()
    r.coordinator.dispatch_once(0)
    assert current.is_current()
    assert r.authority._poison_reason is None
    assert delivered[0][0].generation > delivered[1][0].generation
    assert delivered[0][1].receipt.order > delivered[1][1].receipt.order
    assert delivered[0][1].operation.order > delivered[1][1].operation.order


def test_failed_stream_delta_gap_recovers_only_by_full_restatement(
    real_runtime, monkeypatch
):
    from tests.test_telemetry_gamelogs import HEADER, HEADER_DEFAULT_SESSION
    from wingman.telemetry.model import SourceLifecycle

    r = real_runtime
    old = r.tickets[-1]
    consume = r.metrics.consume

    def fail_retirement(envelope):
        if (
            isinstance(envelope.payload, SourceLifecycle)
            and not envelope.payload.active
        ):
            raise ValueError("failed required delta")
        consume(envelope)

    r.path.write_text(
        HEADER.format(name="Alice", session=HEADER_DEFAULT_SESSION), encoding="utf-8"
    )
    r.stream.scan_once(NOW)
    with monkeypatch.context() as patch:
        patch.setattr(r.metrics, "consume", fail_retirement)
        r.coordinator.dispatch_once(0)
    r.path.unlink()
    r.stream.scan_once(NOW)
    r.coordinator.dispatch_once(0)
    assert not old.is_current()
    lane = r.authority._lanes["stream"]
    assert lane.applied != lane.requested.order
    lifetime = lane.lifetime
    _reset(r)
    assert r.tickets[-1].is_current()
    assert lane.lifetime is lifetime
    assert lane.applied == lane.requested.order


def test_successful_facts_or_single_rebind_cannot_ack_failed_invalidation(
    real_runtime, monkeypatch
):
    r = real_runtime
    _log(r.path.parent, "Alice", stem="replacement", session="2026.08.25 11:01:00")
    r.stream.scan_once(NOW)
    lane = r.authority._lanes["stream"]
    prior = lane.applied

    def fail(_):
        raise ValueError("failed invalidation batch")

    with monkeypatch.context() as patch:
        patch.setattr(r.metrics, "consume", fail)
        r.coordinator.dispatch_once(0)
    assert lane.applied == prior
    r.stream.request_source("Alice")
    r.coordinator.dispatch_once(0)
    assert lane.applied == prior
    assert lane.applied != lane.requested.order
    assert not r.tickets[-1].is_current()
    _reset(r)
    assert r.tickets[-1].is_current()


def test_stream_multiple_deltas_never_ack_latest_before_whole_batch(
    real_runtime, monkeypatch
):
    from tests.test_telemetry_gamelogs import HEADER, HEADER_DEFAULT_SESSION
    from wingman.telemetry.model import SourceLifecycle

    r = real_runtime
    old = r.tickets[-1]
    r.path.write_text(
        HEADER.format(name="Alice", session=HEADER_DEFAULT_SESSION), encoding="utf-8"
    )
    r.stream.scan_once(NOW)
    r.path.unlink()
    r.stream.scan_once(NOW)
    consume = r.metrics.consume
    lane = r.authority._lanes["stream"]
    checks = []

    def inspect(envelope):
        consume(envelope)
        if isinstance(envelope.payload, SourceLifecycle):
            checks.append(lane.applied != lane.requested.order)
            assert not old.is_current()
            assert r.authority._capture() is None

    monkeypatch.setattr(r.metrics, "consume", inspect)
    r.coordinator.dispatch_once(0)
    assert checks == [True, True, True]
    assert r.tickets[-1].is_current()


def test_stream_out_of_order_application_poisons_even_with_latest_receipt(
    real_runtime, monkeypatch
):
    r = real_runtime
    held = []
    callback = r.coordinator._on_admitted_stream
    monkeypatch.setattr(
        r.coordinator, "_on_admitted_stream", lambda *args: held.append(args)
    )
    r.stream.request_source("Alice")
    r.stream.request_source("Alice")
    assert len(held) == 2
    assert held[0][1].receipt is held[1][1].receipt
    callback(*held[1])
    callback(*held[0])
    r.coordinator.dispatch_once(0)
    assert not r.tickets[-1].is_current()
    assert r.authority._poison_reason == "obsolete source operation applied"


def test_cache_installation_race_uses_original_capture(real_runtime, monkeypatch):
    r = real_runtime
    before = len(r.tickets)
    real_lock = r.coordinator._lock
    compute = r.metrics.snapshot
    computed = [False]

    class CacheLock:
        def __enter__(self):
            return real_lock.__enter__()

        def __exit__(self, *args):
            real_lock.__exit__(*args)
            if computed[0]:
                computed[0] = False
                r.roster[:] = [GENERIC]
                r.discovery.scan_once()

    def snapshot(*args):
        result = compute(*args)
        computed[0] = True
        return result

    monkeypatch.setattr(r.metrics, "snapshot", snapshot)
    monkeypatch.setattr(r.coordinator, "_lock", CacheLock())
    r.coordinator.dispatch_once(0)
    assert len(r.tickets) == before
    assert not r.tickets[-1].is_current()


def test_operation_started_during_reset_is_cut_off_at_completion(
    real_runtime, monkeypatch
):
    r = real_runtime
    r.enabled[0] = False
    r.coordinator.reconcile()
    r.coordinator.dispatch_once(0)
    entered, release = Event(), Event()
    reset = r.metrics.reset
    held = []
    callback = r.coordinator._on_admitted_stream

    def paused_reset():
        entered.set()
        assert release.wait(5)
        reset()

    monkeypatch.setattr(r.metrics, "reset", paused_reset)
    r.enabled[0] = True
    r.coordinator.reconcile()
    dispatcher = Thread(target=lambda: r.coordinator.dispatch_once(0))
    dispatcher.start()
    try:
        assert entered.wait(5)
        with monkeypatch.context() as patch:
            patch.setattr(
                r.coordinator, "_on_admitted_stream", lambda *args: held.append(args)
            )
            with r.path.open("a", encoding="utf-8") as output:
                output.write(OUTGOING_DAMAGE_LINE)
            r.stream.scan_once(NOW)
        assert held
    finally:
        release.set()
        dispatcher.join(5)
    assert not dispatcher.is_alive()
    assert r.tickets[-1].is_current()
    callback(*held[0])
    r.coordinator.dispatch_once(0)
    assert not r.tickets[-1].is_current()
    assert r.authority._poison_reason


def test_each_source_restatement_must_apply_before_recovery(real_runtime, monkeypatch):
    from tests.test_client_discovery import BOB
    from wingman.telemetry.model import SourceLifecycle

    r = real_runtime
    r.roster.append(BOB)
    r.discovery.scan_once()
    r.coordinator.dispatch_once(0)
    consume = r.metrics.consume
    observations = []

    def fail_second(envelope):
        if isinstance(envelope.payload, SourceLifecycle):
            observations.append((envelope.payload.character, r.authority._capture()))
            if envelope.payload.character == "Bob":
                raise ValueError("second restatement failed")
        consume(envelope)

    with monkeypatch.context() as patch:
        patch.setattr(r.metrics, "consume", fail_second)
        _reset(r)
    assert [name for name, _ in observations] == ["Alice", "Bob"]
    assert all(frontier is None for _, frontier in observations)
    assert not r.tickets[-1].is_current()
    _reset(r)
    assert r.tickets[-1].is_current()


def test_reset_full_restatement_then_new_delta_completes_latest_frontier(real_runtime):
    r = real_runtime
    once = [True]

    def replace_while_restatement_is_detached(event):
        if once[0]:
            once[0] = False
            r.path.unlink()
            r.stream.scan_once(NOW)

    unsubscribe = r.stream.subscribe(replace_while_restatement_is_detached)
    try:
        _reset(r)
    finally:
        unsubscribe()
    assert r.authority._poison_reason is None
    assert r.tickets[-1].is_current()
    assert r.authority._pending_reset is None


def test_request_source_preserves_actual_observation_identity(real_runtime):
    r = real_runtime
    with r.path.open("a", encoding="utf-8") as output:
        output.write(OUTGOING_DAMAGE_LINE.replace("11:30:00", "12:00:00"))
    r.stream.scan_once(NOW)
    r.coordinator.dispatch_once(0)
    before = r.tickets[-1]
    identity = before.snapshot.rows[0].combat.observation_id
    assert identity is not None
    r.stream.request_source("Alice")
    r.coordinator.dispatch_once(0)
    assert r.tickets[-1].snapshot.rows[0].combat.observation_id == identity
    assert before.is_current()


def test_failed_enumeration_and_failed_baseline_do_not_revoke(
    real_runtime, monkeypatch
):
    from wingman.preview.discovery import EnumerationResult

    r = real_runtime
    old = r.tickets[-1]
    with monkeypatch.context() as patch:
        patch.setattr(
            r.discovery, "_enumerate_clients", lambda: EnumerationResult(False, [])
        )
        r.discovery.scan_once()
    tracked = r.stream._tracked["Alice"]
    original = r.path.read_text(encoding="utf-8")
    r.path.write_text(
        original.replace("2026.08.25 11:00:00", "2026.08.25 11:01:00"), encoding="utf-8"
    )

    def fail_baseline(_):
        raise OSError("unreadable candidate")

    monkeypatch.setattr(r.stream, "_get_file_size", fail_baseline)
    r.stream.scan_once(NOW)
    r.coordinator.dispatch_once(0)
    assert r.stream._tracked["Alice"] is tracked
    assert old.is_current()


@pytest.mark.parametrize("change", ["retire", "replace", "folder_loss"])
def test_source_invalidation_reserves_before_actual_old_state_changes(
    real_runtime, monkeypatch, change
):
    from pathlib import Path

    r = real_runtime
    tracked = r.stream._tracked["Alice"]
    original = dict(r.stream._tracked)
    ticket = r.tickets[-1]
    reserve = r.authority._reserve
    seen = []

    def before_mutation(lane, lifetime):
        receipt = reserve(lane, lifetime)
        if lane != "stream":
            return receipt
        assert not ticket.is_current()
        assert r.stream._tracked == original
        assert r.stream._tracked["Alice"] is tracked
        seen.append(receipt)
        return receipt

    monkeypatch.setattr(r.authority, "_reserve", before_mutation)
    if change == "retire":
        r.path.unlink()
    elif change == "replace":
        _log(r.path.parent, "Alice", stem="new", session="2026.08.25 11:01:00")
    else:

        def fail_glob(*args):
            raise OSError("folder unavailable")

        monkeypatch.setattr(Path, "glob", fail_glob)
    r.stream.scan_once(NOW)
    assert len(seen) == 1
    assert r.stream._tracked.get("Alice") is not tracked


def test_roster_stream_roster_reservations_delivered_stream_roster_roster(real_runtime):
    r = real_runtime
    entered, release = Event(), Event()
    order = []

    def hold(snapshot):
        if snapshot.clients[0].character is None:
            entered.set()
            assert release.wait(5)

    unsubscribe = r.discovery.subscribe(hold)
    r.discovery._subscribe_admission(lambda payload, proof: order.append(proof))
    r.stream._subscribe_admission(lambda payload, proof: order.append(proof))
    r.roster[:] = [GENERIC]
    first = Thread(target=r.discovery.scan_once)
    first.start()
    try:
        assert entered.wait(5)
        r.path.unlink()
        r.stream.scan_once(NOW)
    finally:
        release.set()
        first.join(5)
        unsubscribe()
    assert not first.is_alive()
    r.roster[:] = [ALICE]
    r.discovery.scan_once()
    assert [proof.receipt.lane for proof in order] == ["stream", "roster", "roster"]
    assert order[1].receipt.order < order[0].receipt.order < order[2].receipt.order
    r.coordinator.dispatch_once(0)
    assert r.tickets[-1].is_current()
    assert r.authority._poison_reason is None


def test_new_reservation_while_old_application_waits_to_ack(real_runtime, monkeypatch):
    r = real_runtime
    entered, release = Event(), Event()
    applied = r.authority._applied
    observed = []
    first = [True]

    def pause_ack(receipt):
        if receipt.lane == "stream" and first[0]:
            first[0] = False
            entered.set()
            assert release.wait(5)
            applied(receipt)
            observed.append(r.authority._capture())
        else:
            applied(receipt)

    monkeypatch.setattr(r.authority, "_applied", pause_ack)
    r.path.unlink()
    r.stream.scan_once(NOW)
    dispatcher = Thread(target=lambda: r.coordinator.dispatch_once(0))
    dispatcher.start()
    try:
        assert entered.wait(5)
        _log(r.path.parent, "Alice")
        r.stream.scan_once(NOW)
    finally:
        release.set()
        dispatcher.join(5)
    assert not dispatcher.is_alive()
    assert observed == [None]
    assert r.tickets[-1].is_current()


def test_failed_finalization_retains_dead_owner_and_refuses_replacement(
    real_runtime, monkeypatch
):
    r = real_runtime
    worker = r.coordinator._worker
    receipt = r.coordinator._control_receipt

    def fail():
        raise ValueError("failed final model reset")

    with monkeypatch.context() as patch:
        patch.setattr(r.metrics, "reset", fail)
        assert r.coordinator.stop() is False
        assert r.coordinator._worker is worker
        r.coordinator.reconcile()
        assert r.coordinator._worker is worker
        assert not r.tickets[-1].is_current()
        assert r.coordinator._control_receipt is receipt
    assert r.coordinator.stop()


def test_startup_cut_blocks_prequeued_evidence_without_automatic_reset(
    real_runtime, monkeypatch
):
    r = real_runtime
    assert r.coordinator.stop()
    r.coordinator.reconcile()
    # Match the supplied fixture's ordering: scans finish before the dispatcher
    # applies activation reset. Their original operations are inside its cut.
    r.discovery.scan_once()
    r.stream.scan_once(NOW)
    r.coordinator.dispatch_once(0)
    assert r.authority._poison_reason == "obsolete source operation applied"
    assert not r.tickets[-1].is_current()
    resets = []
    reset = r.metrics.reset

    def count_reset():
        resets.append(True)
        reset()

    with monkeypatch.context() as patch:
        patch.setattr(r.metrics, "reset", count_reset)
        r.discovery.scan_once()
        r.stream.scan_once(NOW)
        r.coordinator.dispatch_once(0)
    assert resets == []
    assert not r.tickets[-1].is_current()
    _reset(r)
    assert r.tickets[-1].is_current()


def test_stop_revokes_before_unsubscribe_and_final_close_never_reopens(
    real_runtime, monkeypatch
):
    r = real_runtime
    old = r.tickets[-1]
    unsubscribe = r.coordinator._discovery_unsub
    observed = []

    def detach():
        observed.append(old.is_current())
        unsubscribe()

    monkeypatch.setattr(r.coordinator, "_discovery_unsub", detach)
    assert r.coordinator.stop()
    assert observed == [False]
    r.coordinator.reconcile()
    r.coordinator.dispatch_once(0)
    r.discovery.scan_once()
    r.stream.scan_once(NOW)
    r.coordinator.dispatch_once(0)
    assert r.tickets[-1].is_current()
    r.coordinator.close_source_admission()
    assert not r.tickets[-1].is_current()
    _reset(r)
    assert not r.tickets[-1].is_current()
