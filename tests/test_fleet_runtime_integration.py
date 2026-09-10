"""Rebase boundary: one local presentation owner and one network owner."""

import threading

import pytest

from tests.test_api_fleetsharing import setup
from tests.test_fleet_bar import PAGE_A, FakeTelemetry, FleetWindow
from tests.test_fleet_bar import (
    _headless_fleet_window_helpers as _headless_fleet_window_helpers,
)
from tests.test_telemetry_coordinator import _harness, _roster, _session
from wingman import settings
from wingman.telemetry.coordinator import _noop_thread_factory
from wingman.telemetry.model import FleetRow


def _failed_fleet_startup(tmp_path):
    harness = _harness(tmp_path, fleet=True, sharing=True)
    builds = iter((None, None, harness.coordinator))

    def factory():
        return next(builds)

    api, worker, *_rest = setup(tmp_path, enabled=True, telemetry=factory())
    api._state.settings["fleet_bar"]["enabled"] = True
    settings.save(api._state.settings)
    api._telemetry_factory = factory
    # Keep real admission/presentation and explicitly drain its existing seam.
    api._fleet_worker._thread_factory = _noop_thread_factory
    with api._fleetbar_lifecycle_lock:
        api._publish_fleet_page_locked(FleetWindow(), PAGE_A)
    harness.coordinator._fleet_enabled = lambda: api._state.settings["fleet_bar"][
        "enabled"
    ]
    harness.coordinator._sharing_enabled = lambda: api._state.settings["fleet_sharing"][
        "enabled"
    ]
    api.start_previews_if_enabled()
    assert api._telemetry is None
    assert api._fleet_expected_generation is None
    assert settings.load()["fleet_bar"]["enabled"]
    return api, worker, harness


def _complete_frame(harness, dps=10):
    harness.metrics.rows = (FleetRow("Alice", dps),)
    harness.discovery.publish(_roster(_session("Alice")))
    harness.pump()
    return harness.coordinator.snapshot()


@pytest.mark.parametrize("action", ["sharing", "preview", "alerts", "folder"])
@pytest.mark.parametrize("early_frame", [False, True])
def test_non_fleet_recovery_admits_completed_frame_to_both_owners(
    tmp_path, action, early_frame
):
    api, worker, harness = _failed_fleet_startup(tmp_path)
    telemetry = harness.coordinator
    reconcile = telemetry.reconcile
    completed = []

    def recovering():
        generation = reconcile()
        if early_frame:
            completed.append(_complete_frame(harness))
        return generation

    telemetry.reconcile = recovering
    try:
        if action == "sharing":
            assert api.fleet_sharing_set_enabled(True)["applied"]
        elif action == "preview":
            assert api.set_preview_enabled(True)
        elif action == "alerts":
            assert api.set_alert_enabled(True)["applied"]
        else:
            assert api.set_folder("gamelogs", str(tmp_path))["applied"]
        if not early_frame:
            completed.append(_complete_frame(harness))
        frame = completed[0]
        assert frame.activation_generation == 1 and frame.rows[0].dps == 10
        assert worker._latest[0] is frame
        assert api._fleet_snapshot is frame
        api._fleet_worker.iterate_once()
        payload = api.fleet_bar_snapshot(PAGE_A)
        assert payload["rows"][0]["character"] == "Alice"
        assert payload["rows"][0]["outgoing_dps"] == 10
        assert payload["rows"][0]["incoming_dps"] is None
        assert any("onFleetSnapshot" in call for call in api._fleetbar_window.calls)
        assert settings.load()["fleet_bar"]["seen"] == ["Alice"]
        assert telemetry._subscribers == [api._receive_fleet_snapshot, worker.submit]

        # An ordinary non-Fleet reconciliation must not clear a live frame,
        # bump its admission/revision, or replace either subscription owner.
        telemetry.reconcile = reconcile
        activation = api._fleet_activation
        revision = api._fleet_presentation_revision
        api.set_folder("gamelogs", str(tmp_path))
        assert api._fleet_snapshot is frame
        assert api._fleet_activation == activation
        assert api._fleet_presentation_revision == revision
        assert telemetry._subscribers == [api._receive_fleet_snapshot, worker.submit]
    finally:
        api.shutdown_previews()
    assert telemetry._subscribers == []


@pytest.mark.parametrize("superseding", ["off", "close", "shutdown", "newer_toggle"])
@pytest.mark.parametrize("held_at", ["reconcile", "snapshot"])
def test_held_non_fleet_recovery_cannot_supersede_fleet_lifecycle(
    tmp_path, superseding, held_at
):
    api, worker, harness = _failed_fleet_startup(tmp_path)
    telemetry = harness.coordinator
    reconcile = telemetry.reconcile
    entered, release = threading.Event(), threading.Event()
    results = []
    old_frame = []
    snapshot = telemetry.snapshot

    def held_snapshot():
        frame = snapshot()
        if not entered.is_set():
            entered.set()
            assert release.wait(5)
        return frame

    def held_reconcile():
        generation = reconcile()
        if not old_frame:
            old_frame.append(_complete_frame(harness))
            if held_at == "reconcile":
                entered.set()
                assert release.wait(5)
            else:
                telemetry.snapshot = held_snapshot
        return generation

    telemetry.reconcile = held_reconcile
    runner = threading.Thread(
        target=lambda: results.append(api.set_folder("gamelogs", str(tmp_path)))
    )
    runner.start()
    try:
        assert entered.wait(2)
        assert worker._latest[0] is old_frame[0]
        assert api._fleet_snapshot is None
        if superseding == "close":
            # Main closes runtime admission before subscriber/native teardown.
            api._close_eve_runtime()
        elif superseding == "shutdown":
            api._close_eve_runtime()
            api.shutdown_fleet_sharing()
            assert api._stop_fleet_presentation()
            assert telemetry._subscribers == []
        else:
            assert api.toggle_fleet_bar(False)["applied"]
            if superseding == "newer_toggle":
                # Metrics remain on for sharing: the coordinator generation
                # alone cannot distinguish this newer local Off/On activation.
                assert api.toggle_fleet_bar(True)["applied"]
                _complete_frame(harness, dps=20)
                assert api._fleet_snapshot.rows[0].dps == 20
        accepted = api._fleet_snapshot
        generation = api._fleet_expected_generation
        activation = api._fleet_activation
        revision = api._fleet_presentation_revision
        release.set()
        runner.join(3)
        assert not runner.is_alive()
        assert results[0]["applied"]
        assert api._fleet_snapshot is accepted
        assert api._fleet_expected_generation == generation
        assert api._fleet_activation == activation
        assert api._fleet_presentation_revision == revision
        if superseding in ("close", "shutdown"):
            api._receive_fleet_snapshot(old_frame[0])
            assert api._fleet_snapshot is None
    finally:
        release.set()
        runner.join(3)
        api.shutdown_previews()
    assert not runner.is_alive()
    assert telemetry._subscribers == []


def test_lazy_admission_waiting_for_fleet_lock_does_not_hold_runtime(tmp_path):
    api, _worker, harness = _failed_fleet_startup(tmp_path)
    snapshot = harness.coordinator.snapshot
    lifecycle = api._fleetbar_lifecycle_lock
    sampled, release, attempted = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )
    results = []

    class ObservedLifecycle:
        def __enter__(self):
            if threading.current_thread() is runner and sampled.is_set():
                attempted.set()
            return lifecycle.__enter__()

        def __exit__(self, *args):
            return lifecycle.__exit__(*args)

    def held_snapshot():
        frame = snapshot()
        sampled.set()
        assert release.wait(5)
        return frame

    api._fleetbar_lifecycle_lock = ObservedLifecycle()
    harness.coordinator.snapshot = held_snapshot
    runner = threading.Thread(
        target=lambda: results.append(api.set_folder("gamelogs", str(tmp_path)))
    )
    runner.start()
    try:
        assert sampled.wait(2)
        with lifecycle:
            release.set()
            assert attempted.wait(2)
            acquired = api._eve_runtime_lock.acquire(timeout=2)
            try:
                assert acquired, "lazy admission inverted Fleet -> runtime lock order"
            finally:
                if acquired:
                    api._eve_runtime_lock.release()
        runner.join(3)
        assert not runner.is_alive()
        assert results[0]["applied"]
    finally:
        release.set()
        runner.join(3)
        api.shutdown_previews()
    assert not runner.is_alive()


@pytest.mark.parametrize("lazy", [False, True])
def test_reconcile_preserves_each_subscription_and_local_start_order(tmp_path, lazy):
    telemetry = FakeTelemetry()
    api, worker, *_rest = setup(tmp_path, telemetry=None if lazy else telemetry)
    created, subscriptions = [], []
    subscribe = telemetry.subscribe_fleet

    def factory():
        created.append(True)
        return telemetry

    def track(callback):
        if callback == api._receive_fleet_snapshot:
            assert api._fleet_worker._running, (
                "local owner must start before subscribing"
            )
        subscriptions.append(callback)
        return subscribe(callback)

    api._telemetry_factory = factory
    telemetry.subscribe_fleet = track
    try:
        if not lazy:
            assert api._start_fleet_presentation()
        for _ in range(3):
            api._reconcile_eve_runtime()
        assert subscriptions == [api._receive_fleet_snapshot, worker.submit]
        assert created == ([True] if lazy else [])
        api.shutdown_previews()
        assert telemetry.subscribers == []
        api._reconcile_eve_runtime()
        assert not api._start_fleet_presentation()
        assert subscriptions == [api._receive_fleet_snapshot, worker.submit]
        assert created == ([True] if lazy else [])
    finally:
        api.shutdown_previews()


def test_local_start_failure_does_not_subscribe_but_sharing_still_works(tmp_path):
    telemetry = FakeTelemetry()
    api, worker, *_rest = setup(tmp_path, telemetry=telemetry)
    owner = api._fleet_worker
    spawn = owner._thread_factory

    def fail(**_kwargs):
        raise RuntimeError("thread unavailable")

    owner._thread_factory = fail
    try:
        api._reconcile_eve_runtime()
        assert telemetry.subscribers == [worker.submit]
        owner._thread_factory = spawn
        api._reconcile_eve_runtime()
        assert api._fleet_worker is owner
        assert telemetry.subscribers.count(worker.submit) == 1
        assert telemetry.subscribers.count(api._receive_fleet_snapshot) == 1
    finally:
        api.shutdown_previews()


def test_reconcile_effect_does_not_hold_runtime_lock(tmp_path):
    telemetry = FakeTelemetry()
    api, _worker, *_rest = setup(tmp_path, telemetry=telemetry)
    acquired = threading.Event()

    def probe():
        with api._eve_runtime_lock:
            acquired.set()

    def reconcile():
        runner = threading.Thread(target=probe)
        runner.start()
        try:
            assert acquired.wait(2), "callback-capable reconcile held lifecycle lock"
        finally:
            runner.join(3)
        return 1

    telemetry.reconcile = reconcile
    try:
        api._reconcile_eve_runtime()
    finally:
        api.shutdown_previews()


@pytest.mark.parametrize("save_fails", [False, True])
def test_sharing_live_apply_does_not_publish_or_block_committed_preview(
    tmp_path, monkeypatch, save_fails
):
    api, worker, *_rest = setup(tmp_path, enabled=True)
    document = api._state.settings
    reader = settings.committed_preview(document)
    snapshot = reader._snapshot
    entered, release = threading.Event(), threading.Event()
    original = settings._save_locked
    results = []

    def held_save(data, path=None):
        assert worker.status().local_inhibited
        entered.set()
        assert release.wait(3)
        if save_fails:
            raise OSError("unavailable")
        original(data, path)

    monkeypatch.setattr(settings, "_save_locked", held_save)
    runner = threading.Thread(
        target=lambda: results.append(api.fleet_sharing_set_enabled(False))
    )
    runner.start()
    try:
        assert entered.wait(2)
        assert reader.snapshot() == snapshot.section
        assert reader.alerts_snapshot() is snapshot.alerts
        assert reader._snapshot is snapshot
    finally:
        release.set()
        runner.join(3)
        api.shutdown_previews()
    assert not runner.is_alive()
    assert reader._snapshot is snapshot
    assert results[0]["applied"]
    assert results[0]["persisted"] is not save_fails
    assert document["fleet_sharing"]["enabled"] is False


@pytest.mark.parametrize("blocked", ["save", "page"])
def test_blocked_local_presentation_leaves_network_handoff_and_off_live(
    tmp_path, monkeypatch, blocked
):
    harness = _harness(tmp_path, fleet=True, sharing=True)
    api, worker, client, _store, _mono, _timers = setup(
        tmp_path, enabled=True, telemetry=harness.coordinator
    )
    api._state.settings["fleet_bar"]["enabled"] = True
    entered, release = threading.Event(), threading.Event()
    off_queued = threading.Event()
    original_save = settings._save_locked

    def stall(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        if blocked == "save":
            return original_save(*args, **kwargs)
        return None

    if blocked == "save":
        monkeypatch.setattr(settings, "_save_locked", stall)
    else:
        monkeypatch.setattr(api._window, "evaluate_js", stall)
    worker.subscribe_status(
        lambda status: off_queued.set() if status.local_inhibited else None
    )
    off = threading.Thread(target=lambda: api.fleet_sharing_set_enabled(False))
    try:
        api._reconcile_fleet_generation(transition=True)
        harness.metrics.rows = (FleetRow("Alice", 10),)
        harness.discovery.publish(_roster(_session("Alice")))
        harness.pump()
        assert entered.wait(2)
        assert worker._latest[0].rows[0].dps == 10
        harness.metrics.rows = (FleetRow("Alice", 20),)
        harness.pump()
        assert worker._latest[0].rows[0].dps == 20
        assert api.fleet_sharing_watch(True)["queued"]
        assert worker._watch
        api.close()
        assert not worker._watch
        api._set_sharing_window_visible(True)
        assert worker._watch
        off.start()
        assert off_queued.wait(2)
        assert worker.status().local_inhibited
        assert not client.publish_calls
    finally:
        release.set()
        if off.ident:
            off.join(5)
        api.shutdown_previews()
    assert not off.is_alive()
    assert harness.coordinator._subscribers == []


def test_reconcile_waiting_for_fleet_lock_does_not_invert_toggle_order(tmp_path):
    telemetry = FakeTelemetry()
    api, _worker, *_rest = setup(tmp_path, telemetry=telemetry)
    attempted = threading.Event()
    start = api._start_fleet_presentation

    def observed_start():
        attempted.set()
        return start()

    api._start_fleet_presentation = observed_start
    runner = threading.Thread(target=api._reconcile_eve_runtime)
    try:
        # The Fleet toggle owns this lock before reconciling the runtime.
        # A competing reconciliation must release runtime before waiting here.
        with api._fleetbar_lifecycle_lock:
            runner.start()
            assert attempted.wait(2)
            acquired = api._eve_runtime_lock.acquire(timeout=2)
            try:
                assert acquired, "runtime -> Fleet inverted toggle's lock order"
            finally:
                if acquired:
                    api._eve_runtime_lock.release()
        runner.join(3)
        assert not runner.is_alive()
    finally:
        runner.join(3)
        api.shutdown_previews()


def test_shutdown_during_reconcile_closes_before_stop_without_resubscription(
    tmp_path, monkeypatch
):
    telemetry = FakeTelemetry()
    api, _worker, *_rest = setup(tmp_path, telemetry=telemetry)
    entered, release, detached = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )
    stopped = []

    def reconcile():
        entered.set()
        assert release.wait(5)
        return 1

    def stop():
        assert telemetry.subscribers == []
        assert api._fleetbar_quitting and api._sharing_closed
        stopped.append(True)
        return True

    telemetry.reconcile = reconcile
    telemetry.stop = stop
    local_stop = api._stop_fleet_presentation

    def close_presentation(*args, **kwargs):
        result = local_stop(*args, **kwargs)
        detached.set()
        return result

    monkeypatch.setattr(api, "_stop_fleet_presentation", close_presentation)
    runner = threading.Thread(target=api._reconcile_eve_runtime)
    shutdown = threading.Thread(target=api.shutdown_previews)
    runner.start()
    try:
        assert entered.wait(2)
        # Closing alone may precede subscriber teardown in main. A reconcile
        # finishing in that gap must not stop the coordinator prematurely.
        api._close_eve_runtime()
        release.set()
        runner.join(3)
        assert not stopped
        assert telemetry.subscribers
        shutdown.start()
        assert detached.wait(2)
        shutdown.join(3)
        assert stopped
        assert api._reconcile_eve_runtime() is None
        assert telemetry.subscribers == []
    finally:
        release.set()
        runner.join(3)
        if shutdown.ident:
            shutdown.join(3)
        api.shutdown_previews()
    assert not runner.is_alive() and not shutdown.is_alive()


def test_timed_out_runtime_shutdown_retains_owner_and_late_effect_stops(tmp_path):
    telemetry = FakeTelemetry()
    api, _worker, *_rest = setup(tmp_path, telemetry=telemetry)
    entered, release, idle = threading.Event(), threading.Event(), threading.Event()
    stopped = []

    class NoWait:
        def clear(self):
            idle.clear()

        def set(self):
            idle.set()

        def wait(self, timeout):
            return idle.is_set()

    api._eve_runtime_idle = NoWait()

    def reconcile():
        entered.set()
        assert release.wait(5)
        return 1

    def stop():
        assert telemetry.subscribers == []
        stopped.append(True)
        return True

    telemetry.reconcile = reconcile
    telemetry.stop = stop
    runner = threading.Thread(target=api._reconcile_eve_runtime)
    runner.start()
    try:
        assert entered.wait(2)
        api.shutdown_previews()
        assert not stopped
        assert api._telemetry is telemetry
        assert api._reconcile_eve_runtime() is None
        release.set()
        runner.join(3)
        assert stopped == [True]
    finally:
        release.set()
        runner.join(3)
        api.shutdown_previews()
    assert not runner.is_alive()


def test_sharing_start_racing_shutdown_cannot_restart_or_repeat_resume(tmp_path):
    api, worker, *_rest = setup(tmp_path)
    entered, release = threading.Event(), threading.Event()
    resumes, outcomes = [], []
    closed = threading.Event()
    unsubscribe = api._sharing_status_unsubscribe

    def detach_status():
        unsubscribe()
        closed.set()

    api._sharing_status_unsubscribe = detach_status
    resume, start = worker.resume_pending, worker.start

    def record_resume():
        resumes.append(True)
        return resume()

    def held_start():
        entered.set()
        assert release.wait(5)
        return start()

    worker.resume_pending = record_resume
    worker.start = held_start
    runner = threading.Thread(
        target=lambda: outcomes.append(api._start_fleet_sharing())
    )
    shutdown = threading.Thread(target=api.shutdown_previews)
    runner.start()
    try:
        assert entered.wait(2)
        assert not api._start_fleet_sharing()
        shutdown.start()
        # Closing status delivery precedes waiting on the admitted start().
        assert closed.wait(2)
        assert api._sharing_closed
        release.set()
        runner.join(3)
        shutdown.join(3)
        assert outcomes == [False]
        assert resumes == [True]
        assert not api._start_fleet_sharing()
        assert not worker._running
    finally:
        release.set()
        runner.join(3)
        if shutdown.ident:
            shutdown.join(3)
        api.shutdown_previews()
    assert not runner.is_alive() and not shutdown.is_alive()
