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


@pytest.mark.parametrize("named", [False, True])
def test_threaded_startup_waits_for_actual_cut_before_producer_operations(
    tmp_path, monkeypatch, named
):
    authority = _SourceAuthority()
    entered, release, first_roster, first_poll, admitted = (Event() for _ in range(5))
    reset_done = Event()
    observations = []
    metrics = FleetMetrics(_utc_now=lambda: NOW)
    reset = metrics.reset

    def held_reset():
        entered.set()
        assert release.wait(5)
        reset()

    def enumerate_clients():
        observations.append(("roster", reset_done.is_set()))
        first_roster.set()
        return [ALICE] if named else []

    discovery = ClientDiscovery(
        _enumerate_clients=enumerate_clients, _source_admission=authority
    )
    stream = GameLogStream(_utc_now=lambda: NOW, _source_admission=authority)
    begin = stream._begin_operation_locked

    def begin_poll(*args):
        observations.append(("stream", reset_done.is_set()))
        first_poll.set()
        begin(*args)

    applied = authority._reset_applied

    def completed(boundary):
        result = applied(boundary)
        if result:
            reset_done.set()
        return result

    monkeypatch.setattr(metrics, "reset", held_reset)
    monkeypatch.setattr(authority, "_reset_applied", completed)
    monkeypatch.setattr(stream, "_begin_operation_locked", begin_poll)
    coordinator = TelemetryCoordinator(
        preview_enabled=lambda: False,
        fleet_enabled=lambda: True,
        alerts_enabled=lambda: False,
        gamelogs_folder=lambda: tmp_path,
        discovery=discovery,
        stream=stream,
        metrics=metrics,
        _source_admission=authority,
    )
    restatements = []
    stream._subscribe_admission(
        lambda batch, proof: (
            restatements.append(batch)
            if proof is not None and proof.reset is not None
            else None
        )
    )
    coordinator.subscribe_admitted_fleet(
        lambda ticket: admitted.set() if ticket.is_current() else None
    )
    reconciler = Thread(target=coordinator.reconcile)
    reconciler.start()
    try:
        assert entered.wait(5)
        # Checking state alone could miss a thread which has not run. Waiting for
        # either operation detects the old implementation's actual early starts.
        started_early = first_roster.wait(0.1) or first_poll.wait(0.1)
        assert not started_early
        assert not discovery._started and not stream._started
        release.set()
        reconciler.join(5)
        assert not reconciler.is_alive()
        assert first_roster.wait(5) and first_poll.wait(5)
        assert admitted.wait(5)  # Empty sources still require a genuine restatement.
        assert all(after_cut for _, after_cut in observations)
        assert restatements
        if not named:
            assert restatements[0].events == ()
        assert authority._poison_reason is None
    finally:
        release.set()
        reconciler.join(5)
        assert coordinator.stop()


def _threaded_runtime(tmp_path, *, preview=False, alerts=False, **kwargs):
    authority = _SourceAuthority()
    enumerated, polled, admitted = Event(), Event(), Event()

    def enumerate_clients():
        enumerated.set()
        return [ALICE]

    discovery = ClientDiscovery(
        _enumerate_clients=enumerate_clients, _source_admission=authority
    )
    stream = GameLogStream(_utc_now=lambda: NOW, _source_admission=authority)
    begin = stream._begin_operation_locked

    def observe_poll(*args):
        polled.set()
        begin(*args)

    stream._begin_operation_locked = observe_poll
    metrics = FleetMetrics(_utc_now=lambda: NOW)
    enabled = [True]
    folder = [tmp_path]
    coordinator = TelemetryCoordinator(
        preview_enabled=lambda: preview,
        fleet_enabled=lambda: enabled[0],
        alerts_enabled=lambda: alerts,
        gamelogs_folder=lambda: folder[0],
        discovery=discovery,
        stream=stream,
        metrics=metrics,
        _source_admission=authority,
        **kwargs,
    )
    tickets = []

    def receive(ticket):
        tickets.append(ticket)
        if ticket.is_current():
            admitted.set()

    coordinator.subscribe_admitted_fleet(receive)
    return SimpleNamespace(
        authority=authority,
        discovery=discovery,
        stream=stream,
        metrics=metrics,
        coordinator=coordinator,
        enumerated=enumerated,
        polled=polled,
        admitted=admitted,
        tickets=tickets,
        enabled=enabled,
        folder=folder,
    )


def test_threaded_reset_timeout_retains_original_owner_and_retries_same_cut(
    tmp_path, monkeypatch
):
    r = _threaded_runtime(tmp_path, _wait_reset=lambda event, timeout: event.wait(0.05))
    entered, release = Event(), Event()
    reset = r.metrics.reset
    resets = []

    def hold_reset():
        resets.append(True)
        entered.set()
        assert release.wait(5)
        reset()

    monkeypatch.setattr(r.metrics, "reset", hold_reset)
    try:
        r.coordinator.reconcile()
        assert entered.is_set()
        assert not r.enumerated.is_set() and not r.polled.is_set()
        owner = r.coordinator._worker
        completion = r.coordinator._reset_completion
        assert owner.is_alive() and not completion.done.is_set()
        release.set()
        assert completion.done.wait(5)
        assert not r.enumerated.is_set() and not r.polled.is_set()
        r.coordinator.reconcile()
        assert r.coordinator._worker is owner
        assert r.coordinator._reset_completion is completion
        assert r.enumerated.wait(5) and r.polled.wait(5) and r.admitted.wait(5)
        assert resets == [True]
        assert r.authority._poison_reason is None
    finally:
        release.set()
        assert r.coordinator.stop()


@pytest.mark.parametrize("action", ["close", "stop"])
def test_stop_or_close_cancels_wait_and_cannot_install_late_producers(
    tmp_path, monkeypatch, action
):
    waiting, entered, release = Event(), Event(), Event()

    def wait_reset(event, timeout):
        waiting.set()
        return event.wait(timeout)

    r = _threaded_runtime(tmp_path, _wait_reset=wait_reset)
    reset = r.metrics.reset

    def hold_reset():
        entered.set()
        assert release.wait(5)
        reset()

    monkeypatch.setattr(r.metrics, "reset", hold_reset)
    reconciler = Thread(target=r.coordinator.reconcile)
    reconciler.start()
    try:
        assert entered.wait(5) and waiting.wait(5)
        old_completion = r.coordinator._reset_completion
        old_owner = r.coordinator._worker
        if action == "close":
            r.coordinator.close_source_admission()
        else:
            assert r.coordinator.stop(timeout=0) is False
        reconciler.join(5)
        assert not reconciler.is_alive()
        assert old_completion.done.is_set()
        assert not r.enumerated.is_set() and not r.polled.is_set()
        r.coordinator.reconcile()
        assert r.coordinator._worker is old_owner
        assert not r.enumerated.is_set() and not r.polled.is_set()
        release.set()
        if action == "stop":
            old_owner.join(5)
            assert not old_owner.is_alive()
            assert r.coordinator.stop()
            r.coordinator.reconcile()
            assert r.coordinator._worker is not old_owner
            assert r.coordinator._reset_completion is not old_completion
            assert r.admitted.wait(5)
            assert r.authority._poison_reason is None
        else:
            r.coordinator.reconcile()
            assert not r.enumerated.is_set() and not r.polled.is_set()
            assert r.tickets == []
    finally:
        release.set()
        reconciler.join(5)
        assert r.coordinator.stop()


@pytest.mark.parametrize("unrelated", [False, True])
def test_failed_startup_reset_never_certifies_but_preserves_unrelated_consumers(
    tmp_path, monkeypatch, unrelated
):
    from tests.test_telemetry_coordinator import FakePolicy, FakePreviewHost
    from tests.test_telemetry_gamelogs import DAMAGE_LINE

    preview, policy = FakePreviewHost(), FakePolicy()
    r = _threaded_runtime(
        tmp_path,
        preview=unrelated,
        alerts=unrelated,
        preview_host=preview,
        alert_policy=policy,
    )
    completed = Event()

    def fail_reset():
        raise ValueError("original startup reset failed")

    r.coordinator.subscribe_fleet(lambda snapshot: completed.set())
    try:
        with monkeypatch.context() as patch:
            patch.setattr(r.metrics, "reset", fail_reset)
            r.coordinator.reconcile()
            completion = r.coordinator._reset_completion
            assert completion.done.is_set() and not completion.succeeded
            assert r.authority._poison_reason == "metrics reset failed"
            if unrelated:
                assert r.enumerated.wait(5) and r.polled.wait(5)
                assert completed.wait(5)
                assert preview.rosters
                r.stream.scan_once(NOW)
                _log(tmp_path, "Alice", DAMAGE_LINE)
                handled = Event()
                handle = policy.handle

                def receive(*args, **kwargs):
                    handle(*args, **kwargs)
                    handled.set()

                patch.setattr(policy, "handle", receive)
                r.stream.scan_once(NOW)
                assert handled.wait(5)
                assert policy.calls[-1][0][0].event == "combat"
            else:
                assert not r.enumerated.is_set() and not r.polled.is_set()
            assert r.tickets == []
        # A new real activation, not an implicit retry of the failed reset.
        r.enabled[0] = False
        r.coordinator.reconcile()
        r.enabled[0] = True
        r.coordinator.reconcile()
        assert r.admitted.wait(5)
    finally:
        assert r.coordinator.stop()


def test_threaded_preview_alert_only_startup_never_waits_for_metrics(tmp_path):
    def forbidden_wait(*args):
        pytest.fail("Preview/Alerts must not wait for a metrics reset")

    r = _threaded_runtime(
        tmp_path, preview=True, alerts=True, _wait_reset=forbidden_wait
    )
    r.enabled[0] = False
    try:
        r.coordinator.reconcile()
        assert r.enumerated.wait(5) and r.polled.wait(5)
        assert r.tickets == []
    finally:
        assert r.coordinator.stop()


def test_threaded_ordinary_restart_gets_fresh_cut_and_admission(tmp_path):
    r = _threaded_runtime(tmp_path)
    try:
        r.coordinator.reconcile()
        assert r.admitted.wait(5)
        ticket = r.tickets[-1]
        owner = r.coordinator._worker
        completion = r.coordinator._reset_completion
        assert r.coordinator.stop()
        assert not ticket.is_current() and not owner.is_alive()
        r.admitted.clear()
        r.coordinator.reconcile()
        assert r.admitted.wait(5)
        assert r.coordinator._worker is not owner
        assert r.coordinator._reset_completion is not completion
        assert r.tickets[-1].is_current()
        assert r.authority._poison_reason is None
    finally:
        assert r.coordinator.stop()


def test_initial_event_signal_without_dispatcher_cut_cannot_start_producers(tmp_path):
    def signal_only(event, timeout):
        event.set()
        return True

    r = _threaded_runtime(
        tmp_path, _thread_factory=_noop_thread_factory, _wait_reset=signal_only
    )
    try:
        r.coordinator.reconcile()
        completion = r.coordinator._reset_completion
        assert completion.done.is_set() and completion.owner is None
        assert not r.discovery._started and not r.stream._started
        assert r.tickets == []
        # Only executing the original queued reset can supply owner/success.
        r.coordinator.dispatch_once(0)
        assert completion.succeeded
        r.coordinator.reconcile()
        assert r.enumerated.wait(5) and r.polled.wait(5)
        r.coordinator.dispatch_once(0)
        assert r.admitted.is_set()
    finally:
        assert r.coordinator.stop()


def test_cut_completion_does_not_wait_for_priming_or_ready_ticket(
    tmp_path, monkeypatch
):
    r = _threaded_runtime(tmp_path)
    entered, release = Event(), Event()
    snapshot = r.discovery._snapshot_admission

    def hold_priming():
        entered.set()
        assert release.wait(5)
        return snapshot()

    monkeypatch.setattr(r.discovery, "_snapshot_admission", hold_priming)
    reconciler = Thread(target=r.coordinator.reconcile)
    reconciler.start()
    try:
        assert entered.wait(5)
        reconciler.join(5)
        assert not reconciler.is_alive()
        assert r.coordinator._reset_completion.succeeded
        assert r.enumerated.wait(5) and r.polled.wait(5)
        assert not r.admitted.is_set()
        release.set()
        assert r.admitted.wait(5)
    finally:
        release.set()
        reconciler.join(5)
        assert r.coordinator.stop()


def test_restarted_dispatcher_cannot_use_previous_completed_reset(
    tmp_path, monkeypatch
):
    r = _threaded_runtime(tmp_path)
    entered, release = Event(), Event()
    try:
        r.coordinator.reconcile()
        assert r.admitted.wait(5)
        previous = r.coordinator._reset_completion
        assert previous.done.is_set() and previous.succeeded
        assert r.coordinator.stop()
        r.enumerated.clear()
        r.polled.clear()
        r.admitted.clear()
        reset = r.metrics.reset

        def hold_reset():
            entered.set()
            assert release.wait(5)
            reset()

        monkeypatch.setattr(r.metrics, "reset", hold_reset)
        reconciler = Thread(target=r.coordinator.reconcile)
        reconciler.start()
        try:
            assert entered.wait(5)
            assert r.coordinator._reset_completion is not previous
            previous.done.set()
            assert not r.enumerated.wait(0.1) and not r.polled.is_set()
        finally:
            release.set()
            reconciler.join(5)
        assert not reconciler.is_alive()
        assert r.admitted.wait(5)
        assert r.authority._poison_reason is None
    finally:
        release.set()
        assert r.coordinator.stop()


def test_new_activation_cannot_use_old_completion_on_same_dispatcher(
    tmp_path, monkeypatch
):
    r = _threaded_runtime(tmp_path, preview=True, alerts=False)
    disabled, entered, release = Event(), Event(), Event()
    try:
        r.coordinator.reconcile()
        assert r.admitted.wait(5)
        previous = r.coordinator._reset_completion
        owner = r.coordinator._worker
        reset = r.metrics.reset

        def disabled_reset():
            reset()
            disabled.set()

        monkeypatch.setattr(r.metrics, "reset", disabled_reset)
        r.enabled[0] = False
        r.coordinator.reconcile()
        assert disabled.wait(5)
        assert not r.stream._started
        assert r.coordinator._worker is owner
        r.admitted.clear()

        def hold_reset():
            entered.set()
            assert release.wait(5)
            reset()

        monkeypatch.setattr(r.metrics, "reset", hold_reset)
        r.enabled[0] = True
        reconciler = Thread(target=r.coordinator.reconcile)
        reconciler.start()
        try:
            assert entered.wait(5)
            current = r.coordinator._reset_completion
            assert current is not previous
            assert current.generation != previous.generation
            assert previous.owner is r.coordinator._stop_event
            previous.done.set()
            assert not r.stream._started
            assert not current.done.is_set()
        finally:
            release.set()
            reconciler.join(5)
        assert not reconciler.is_alive()
        assert r.admitted.wait(5)
    finally:
        release.set()
        assert r.coordinator.stop()


def test_folder_replacement_starts_only_after_original_folder_reset_cut(
    tmp_path, monkeypatch
):
    r = _threaded_runtime(tmp_path)
    entered, release, new_operation, cut = Event(), Event(), Event(), Event()
    next_folder = tmp_path / "next"
    next_folder.mkdir()
    try:
        r.coordinator.reconcile()
        assert r.admitted.wait(5)
        r.admitted.clear()
        reset = r.metrics.reset
        begin = r.stream._begin_operation_locked
        applied = r.authority._reset_applied
        observations = []

        def hold_reset():
            entered.set()
            assert release.wait(5)
            reset()

        def completed(boundary):
            result = applied(boundary)
            if result:
                cut.set()
            return result

        def observe(*args):
            if r.stream._folder == next_folder:
                observations.append(cut.is_set())
                new_operation.set()
            begin(*args)

        monkeypatch.setattr(r.metrics, "reset", hold_reset)
        monkeypatch.setattr(r.authority, "_reset_applied", completed)
        monkeypatch.setattr(r.stream, "_begin_operation_locked", observe)
        r.folder[0] = next_folder
        reconciler = Thread(target=r.coordinator.reconcile)
        reconciler.start()
        try:
            assert entered.wait(5)
            assert not new_operation.wait(0.1)
        finally:
            release.set()
            reconciler.join(5)
        assert not reconciler.is_alive()
        assert new_operation.wait(5) and r.admitted.wait(5)
        assert observations and all(observations)
        assert r.authority._poison_reason is None
    finally:
        release.set()
        assert r.coordinator.stop()


def test_threaded_kept_alive_fact_crossing_reset_still_poisons(tmp_path, monkeypatch):
    from wingman.telemetry.model import SourceLifecycle

    r = _threaded_runtime(tmp_path, preview=True, alerts=True)
    source_applied = Event()
    consume = r.metrics.consume

    def observe_source(envelope):
        consume(envelope)
        if isinstance(envelope.payload, SourceLifecycle) and envelope.payload.active:
            source_applied.set()

    monkeypatch.setattr(r.metrics, "consume", observe_source)
    try:
        r.coordinator.reconcile()
        assert r.admitted.wait(5)
        path = _log(tmp_path, "Alice", OUTGOING_DAMAGE_LINE)
        r.stream.scan_once(NOW)
        assert source_applied.wait(5)
        held = []
        callback = r.coordinator._on_admitted_stream
        with monkeypatch.context() as patch:
            patch.setattr(
                r.coordinator, "_on_admitted_stream", lambda *args: held.append(args)
            )
            with path.open("a", encoding="utf-8") as output:
                output.write(OUTGOING_DAMAGE_LINE)
            r.stream.scan_once(NOW)
        assert len(held) == 1 and all(
            isinstance(event, CombatFact) for event in held[0][0].events
        )
        stream_owner = r.stream._worker
        lifetime = held[0][1].operation.lifetime
        fresh = Event()
        generation = [None]

        def receive(ticket):
            if (
                ticket.snapshot.activation_generation == generation[0]
                and ticket.is_current()
            ):
                fresh.set()

        r.coordinator.subscribe_admitted_fleet(receive)
        r.enabled[0] = False
        r.coordinator.reconcile()
        r.enabled[0] = True
        generation[0] = r.coordinator.reconcile()
        if r.tickets[-1].snapshot.activation_generation == generation[0]:
            fresh.set()
        assert fresh.wait(5)
        assert r.stream._worker is stream_owner
        assert r.stream._admission_receipt.lifetime is lifetime
        current = r.tickets[-1]
        consumed, published = Event(), Event()

        def observe_fact(envelope):
            consume(envelope)
            if envelope.payload is held[0][0].events[0]:
                consumed.set()

        monkeypatch.setattr(r.metrics, "consume", observe_fact)
        r.coordinator.subscribe_fleet(
            lambda snapshot: published.set() if consumed.is_set() else None
        )
        callback(*held[0])
        assert published.wait(5)
        assert consumed.is_set()
        assert not current.is_current()
        assert r.authority._poison_reason == "obsolete source operation applied"
        r.coordinator.reconcile()
        assert not current.is_current()
        r.admitted.clear()
        r.enabled[0] = False
        r.coordinator.reconcile()
        r.enabled[0] = True
        r.coordinator.reconcile()
        assert r.admitted.wait(5)
    finally:
        assert r.coordinator.stop()


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

    def drive_reset(event, timeout):
        coordinator.dispatch_once(0)
        return event.wait(0)

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
        _wait_reset=drive_reset,
    )
    tickets = []
    coordinator.subscribe_admitted_fleet(tickets.append)
    coordinator.reconcile()
    # Reconcile's injected waiter drives the real reset on the existing manual
    # dispatcher seam. Scans may now run immediately after reconcile returns.
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


def test_startup_handshake_cuts_before_scans_without_extra_reset(
    real_runtime, monkeypatch
):
    r = real_runtime
    assert r.coordinator.stop()
    resets = []
    reset = r.metrics.reset

    def count_reset():
        resets.append(True)
        reset()

    monkeypatch.setattr(r.metrics, "reset", count_reset)
    r.coordinator.reconcile()
    assert resets == [True]
    r.discovery.scan_once()
    r.stream.scan_once(NOW)
    r.coordinator.dispatch_once(0)
    assert r.authority._poison_reason is None
    assert r.tickets[-1].is_current()
    r.discovery.scan_once()
    r.stream.scan_once(NOW)
    r.coordinator.dispatch_once(0)
    assert resets == [True]


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
