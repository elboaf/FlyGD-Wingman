"""Task 7 review regressions: actual owner/JSON seams, no network or DPAPI."""

import threading
import time
from dataclasses import replace
from itertools import pairwise

import pytest
from test_fleetsharing_worker import (
    DEVICE,
    KEY,
    PAIRED_STATE,
    UUID,
    FakeRelayClient,
    _snapshot,
    _worker,
    drive,
    rig,
)

from wingman.fleetsharing import crypto
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing import state as s
from wingman.fleetsharing.client import FleetRelayError


@pytest.mark.parametrize("committed", [False, True])
def test_uncertain_initial_pairing_retains_same_key_retry_across_json_restart(
    tmp_path, committed
):
    path = tmp_path / "sharing.json"
    s.save(path, s.EMPTY)
    worker, client, _, mono = rig(state=s.EMPTY, enabled=False)
    worker._load_state = lambda: s.load(path)
    worker._save_state = lambda state: s.save(path, state)
    generated = []
    worker._generate_private_key = lambda: generated.append(KEY) or KEY
    worker.request_pairing(configured_origin="https://relay.test")
    failures = client.loss if committed else client.precommit_loss
    failures.add("complete_pairing")
    for _ in range(10):
        drive(worker, mono, 1)
        if not failures:
            break
    candidate = s.load(path)
    assert candidate.pending_pairing.completion_attempted
    assert candidate.session_id is None and generated == [KEY]
    assert worker.stop()
    replacement = _worker(
        client,
        clock=lambda: mono[0],
        utc_clock=client.utc,
        sharing_enabled=lambda: False,
    )
    replacement._load_state = lambda: s.load(path)
    replacement._save_state = lambda state: s.save(path, state)
    replacement._generate_private_key = lambda: pytest.fail(
        "retry must reuse candidate key"
    )
    replacement.resume_pending()
    drive(replacement, mono, 16)
    if not committed:
        assert s.load(path).pending_pairing == candidate.pending_pairing
        assert replacement.status().pairing == "needs_retry"
        assert s.load(path).auth_pause is None and not client.registered_keys
        statuses = []
        replacement.subscribe_status(statuses.append)
        assert replacement.request_pairing(mode="fresh")
        drive(replacement, mono, 1)
        assert any(status.pairing == "rejected" for status in statuses)
        assert s.load(path).pending_pairing == candidate.pending_pairing
        assert replacement.request_pairing(mode="initial")
        drive(replacement, mono, 24)
    assert s.load(path).session_id and s.load(path).identity == candidate.identity
    assert (
        s.load(path).pending_pairing is None and s.load(path).pending_recovery is None
    )
    assert len(client.pair_keys) == (1 if committed else 2)
    assert client.recoveries == (1 if committed else 0)
    assert client.cadence_refusals == 0


@pytest.mark.parametrize("transition", ["upgrade", "fresh", "rejected", "wrong_origin"])
def test_queued_off_stop_survive_only_validated_same_identity_transition(transition):
    worker, client, store, mono = rig(enabled=False)
    worker.request_source_stop(UUID)
    worker.request_participation(False)
    if transition == "fresh":
        worker._generate_private_key = lambda: bytes([1]) * 32
        worker._unwrap_private_key = lambda blob: bytes([1]) * 32
        worker.request_pairing(mode="fresh", configured_origin="https://other.test")
    elif transition == "wrong_origin":
        worker.request_pairing(mode="upgrade", configured_origin="https://other.test")
    else:
        worker.request_pairing(mode="fresh" if transition == "rejected" else "upgrade")
    drive(worker, mono, 24)
    if transition == "fresh":
        assert not client.controls and not client.participation_calls
        assert store.load().relay_origin == "https://other.test"
    else:
        assert client.controls == [p.StopSource(UUID, 0)]
        assert client.participation_calls == [(False, 1)]
        assert store.load().identity == PAIRED_STATE.identity
        assert store.load().relay_origin == "https://relay.test"
    assert store.load().pending_participation is None
    assert not store.load().pending_source_commands


@pytest.mark.parametrize("superseded", ["participation", "source", "pairing"])
def test_ingestion_snapshot_cannot_adopt_reentrant_replacement_generation(superseded):
    worker, client, store, mono = rig(enabled=False)
    if superseded == "pairing":
        worker.set_source_watch(True)
        drive(worker, mono, 6)
        assert worker.status().sources is not None
        worker.set_source_watch(False)
    trigger_id = worker.request_source_start(1, UUID)
    if superseded == "participation":
        old = worker.request_participation(True)
    elif superseded == "source":
        old = worker.request_source_start(1, UUID)
    else:
        worker.request_pairing(mode="upgrade")
    replacements = []

    def callback(status):
        trigger = (
            status.source_control == "persisted"
            if superseded != "pairing"
            else status.sources is None and bool(store.saves)
        )
        if trigger and not replacements:
            replacements.append(True)
            if superseded == "participation":
                replacements.append(worker.request_participation(False))
            elif superseded == "source":
                worker.request_source_stop(old)
            else:
                worker.request_pairing(mode="upgrade")

    worker.subscribe_status(callback)
    worker.iterate_once()
    assert replacements
    if superseded == "participation":
        assert all(
            not state.pending_participation
            or state.pending_participation.intent_id != old
            for state in store.saves
        )
        assert worker.status().participation == "queued"
    elif superseded == "source":
        assert all(
            not any(
                isinstance(c, p.StartSource) and c.source_id == old
                for c in state.pending_source_commands
            )
            for state in store.saves
        )
        assert worker.status().source_control == "queued"
    else:
        assert worker.status().pairing == "queued"
    drive(worker, mono, 20)
    assert not any(
        isinstance(c, p.StartSource) and c.source_id != trigger_id
        for c in client.controls
    )
    assert not client.participation_calls or all(
        not enabled for enabled, _ in client.participation_calls
    )


def test_stop_retires_near_cap_start_backoff_but_repeated_stop_keeps_own_floor():
    worker, client, store, mono = rig(enabled=False)
    client.errors["control_source"] = FleetRelayError(
        503, "service_unavailable", "before commit"
    )
    source_id = worker.request_source_start(1, UUID)
    drive(worker, mono, 64)
    attempts = [t for op, t, _ in client.calls if op == "control_source"]
    assert len(attempts) == 6 and attempts[-1] - attempts[-2] == 16
    previous_deadline = attempts[-1] + 30
    worker.request_source_stop(source_id)
    worker.iterate_once()
    assert client.calls[-1][0] == "fetch_sources"
    observed_at = mono[0]
    mono[0] += 0.49
    worker.iterate_once()
    assert client.calls[-1][0] == "fetch_sources"
    mono[0] = observed_at + 0.5
    worker.iterate_once()
    assert client.calls[-1][0] == "control_source"
    assert client.calls[-1][1] == observed_at + 0.5 < previous_deadline
    stop_attempt = mono[0]
    # Repeated explicit Stop must not reset the same Stop's retry ownership.
    for _ in range(9):
        mono[0] += 0.1
        worker.request_source_stop(source_id)
        worker.iterate_once()
    assert [t for op, t, _ in client.calls if op == "control_source"][
        -1
    ] == stop_attempt
    client.errors.clear()
    drive(worker, mono, 10)
    assert client.source_views[source_id].state == "ended"
    assert not store.load().pending_source_commands and client.cadence_refusals == 0


@pytest.mark.parametrize("retirement", ["reconciled", "expired", "acknowledged"])
def test_retired_source_work_does_not_accumulate_retry_failure_or_service_history(
    retirement,
):
    worker, client, store, mono = rig(enabled=False)
    for _ in range(12):
        source_id = worker.request_source_start(1, UUID)
        if retirement == "reconciled":
            client.loss.add("control_source")
        else:
            client.precommit_loss.add("control_source")
        for _ in range(6):
            drive(worker, mono, 1)
            if not client.loss and not client.precommit_loss:
                break
        if retirement == "expired":
            mono[0] += 61
        drive(worker, mono, 8)
        assert not store.load().pending_source_commands
        for metadata in (
            worker._scheduler.retry_at,
            worker._scheduler.failures,
            worker._scheduler._served,
        ):
            assert not any(source_id in key for key in metadata)
    assert client.cadence_refusals == 0


def test_forbidden_publication_invalidates_catalogue_and_refetches_before_retry():
    worker, client, _, mono = rig()
    drive(worker, mono, 10, _snapshot(42))
    client.errors["publish_snapshot"] = FleetRelayError(
        403, "forbidden", "authority changed"
    )
    worker.submit(_snapshot(43))
    for _ in range(8):
        drive(worker, mono, 1)
        if worker.status().detail == "forbidden":
            break
    assert worker._catalogue is None
    before = len(client.calls)
    client.errors.clear()
    drive(worker, mono, 12, _snapshot(44))
    operations = [op for op, _, _ in client.calls[before:]]
    assert "fetch_catalogue" in operations
    assert operations.index("fetch_catalogue") < operations.index("publish_snapshot")
    assert client.cadence_refusals == 0


def test_protocol_mismatch_is_worker_error_not_auth_refusal():
    worker, client, _, mono = rig()
    client.errors["fetch_device"] = FleetRelayError(
        None, "protocol_mismatch", "future server"
    )
    drive(worker, mono, 1)
    assert (
        worker.status().state == "error"
        and worker.status().detail == "protocol_mismatch"
    )
    assert not client.pair_keys and not client.recoveries


def test_repeated_worker_failures_reach_and_stay_at_retry_cap_despite_submissions():
    worker, client, _, mono = rig()
    client.errors["fetch_device"] = FleetRelayError(503, "service_unavailable", "down")
    drive(worker, mono, 250, _snapshot(42))
    times = [t for op, t, _ in client.calls if op == "fetch_device"]
    assert [b - a for a, b in pairwise(times)] == [1, 2, 4, 8, 16, 30, 30, 30]
    assert worker.status().state == "error" and not client.publish_calls
    assert client.cadence_refusals == 0


def test_real_thread_ingestion_callback_off_is_queued_not_obsolete_on_persisted(
    tmp_path,
):
    path = tmp_path / "sharing.json"
    s.save(path, PAIRED_STATE)
    client = FakeRelayClient(device=DEVICE)
    worker = _worker(
        client,
        clock=time.monotonic,
        thread_factory=threading.Thread,
        sharing_enabled=lambda: False,
    )
    worker._load_state = lambda: s.load(path)
    saved = []

    def save(state):
        s.save(path, state)
        saved.append(state)

    worker._save_state = save
    worker.request_source_start(1, UUID)
    old_on = worker.request_participation(True)
    callback_done = threading.Event()
    release = threading.Event()
    stages = []

    def callback(status):
        if status.source_control == "persisted" and not callback_done.is_set():
            callback_done.set()
            worker.request_participation(False)
            stages.append(worker.status().participation)
            assert release.wait(5)

    worker.subscribe_status(callback)
    assert worker.start()
    try:
        assert callback_done.wait(5)
        release.set()
        deadline = time.monotonic() + 5
        while (
            time.monotonic() < deadline
            and worker.status().participation != "acknowledged"
        ):
            time.sleep(0.01)
        assert not client.device.participation.enabled
        assert stages == ["queued"]
        assert all(
            not state.pending_participation
            or state.pending_participation.intent_id != old_on
            for state in saved
        )
        assert s.load(path).pending_participation is None
    finally:
        release.set()
        assert worker.stop(timeout=5)


@pytest.mark.parametrize(
    "operation",
    ["set_participation", "start", "stop", "begin_recovery", "complete_recovery"],
)
@pytest.mark.parametrize("committed", [False, True])
def test_precommit_and_lost_control_responses_reconcile_same_intent_after_json_restart(
    tmp_path, operation, committed
):
    path = tmp_path / "sharing.json"
    original = (
        replace(PAIRED_STATE, session_id=None)
        if "recovery" in operation
        else PAIRED_STATE
    )
    s.save(path, original)
    worker, client, _, mono = rig(state=original, enabled=False)
    worker._load_state = lambda: s.load(path)
    worker._save_state = lambda state: s.save(path, state)
    worker.resume_pending()
    if operation == "set_participation":
        worker.request_participation(False)
    elif operation == "start":
        source_id = worker.request_source_start(1, UUID)
    elif operation == "stop":
        source_id = UUID
        worker.request_source_stop(source_id)
    else:
        # Recovery is explicit pending activity, even while preference is Off.
        worker.set_source_watch(True)
    network_operation = (
        "control_source" if operation in ("start", "stop") else operation
    )
    faults = client.loss if committed else client.precommit_loss
    faults.add(network_operation)
    for _ in range(15):
        drive(worker, mono, 1)
        if not faults:
            break
    assert not faults
    journal = s.load(path)
    admitted = dict(client.admissions)
    assert worker.stop()
    replacement = _worker(
        client,
        clock=lambda: mono[0],
        utc_clock=client.utc,
        sharing_enabled=lambda: False,
    )
    replacement._load_state = lambda: s.load(path)
    replacement._save_state = lambda state: s.save(path, state)
    replacement.resume_pending()
    if "recovery" in operation:
        replacement.set_source_watch(True)
    drive(replacement, mono, 24)
    restored = s.load(path)
    assert restored.identity == original.identity and not client.pair_keys
    if operation == "set_participation":
        assert client.participation_calls == [(False, 1)]
        assert restored.pending_participation is None
    elif operation in ("start", "stop"):
        assert client.controls == [journal.pending_source_commands[0]]
        assert client.controls[0].source_id == source_id
        assert not restored.pending_source_commands
        assert client.source_views[source_id].state == (
            "active" if operation == "start" else "ended"
        )
    else:
        assert restored.session_id and restored.pending_recovery is None
        assert client.recoveries == (
            2 if operation == "complete_recovery" and committed else 1
        )
        if operation == "begin_recovery" and committed:
            assert client.admissions == admitted
    assert client.cadence_refusals == 0


def test_retiring_older_source_preserves_active_command_backoff_and_bucket_floor():
    worker, client, store, mono = rig(enabled=False)
    client.errors["control_source"] = FleetRelayError(
        503, "service_unavailable", "before commit"
    )
    active_id = worker.request_source_start(1, UUID)
    drive(worker, mono, 8)
    active_key = next(key for key in worker._scheduler.retry_at if active_id in key)
    deadline = worker._scheduler.retry_at[active_key]
    failures = worker._scheduler.failures[active_key]
    assert failures == 3
    client.errors.clear()
    retired_id = worker.request_source_start(1, UUID)
    client.loss.add("control_source")
    drive(worker, mono, 3)
    assert [c.source_id for c in store.load().pending_source_commands] == [active_id]
    assert worker._scheduler.retry_at[active_key] == deadline
    assert worker._scheduler.failures[active_key] == failures
    assert not any(retired_id in key for key in worker._scheduler.retry_at)
    before = len(client.calls)
    mono[0] = client.completed[-1][1] + 0.49
    worker.iterate_once()
    assert len(client.calls) == before
    mono[0] = deadline - 0.01
    worker.iterate_once()
    assert len(client.calls) == before
    mono[0] = deadline
    worker.iterate_once()
    assert client.controls[-1].source_id == active_id


def test_real_thread_queued_off_stop_before_upgrade_survive_held_source_read(tmp_path):
    path = tmp_path / "sharing.json"
    s.save(path, PAIRED_STATE)
    client = FakeRelayClient(device=DEVICE)
    client.hold = "fetch_sources"
    worker = _worker(
        client,
        clock=time.monotonic,
        thread_factory=threading.Thread,
        sharing_enabled=lambda: False,
    )
    worker._load_state = lambda: s.load(path)
    worker._save_state = lambda state: s.save(path, state)
    worker.set_source_watch(True)
    assert worker.start()
    try:
        assert client.entered.wait(5)
        worker.request_source_stop(UUID)
        worker.request_participation(False)
        worker.request_pairing(mode="upgrade")
        client.release.set()
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if (
                worker.status().participation == "acknowledged"
                and worker.status().source_control == "acknowledged"
            ):
                break
            time.sleep(0.01)
        assert client.controls == [p.StopSource(UUID, 0)]
        assert client.participation_calls == [(False, 1)]
        assert client.pair_keys == [crypto.public_key_spki(KEY)]
        assert (
            not s.load(path).pending_source_commands
            and s.load(path).pending_participation is None
        )
        assert s.load(path).identity == PAIRED_STATE.identity
        assert client.cadence_refusals == 0
    finally:
        client.release.set()
        assert worker.stop(timeout=5)
