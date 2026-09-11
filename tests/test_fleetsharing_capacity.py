"""Byte-bound admission through the real journal and serialized owner, offline."""

import base64
import threading
import time
from dataclasses import replace
from datetime import timedelta

import pytest

from tests.fleetsharing_capacity_helpers import (
    compact_bytes,
    fixture_bytes,
    legacy_bytes,
    maximal_state,
    start_boundary,
)
from tests.test_fleetsharing_worker import (
    DATE,
    DEVICE,
    NOW,
    PAIRED_STATE,
    UUID,
    FakeRelayClient,
    _worker,
    drive,
)
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing import state as s


class DiskStore:
    def __init__(self, path, state):
        self.path = path
        self.saved = []
        self.rejected = []
        s.save(path, state)

    def load(self):
        return s.load(self.path)

    def save(self, state):
        before = self.path.read_bytes()
        try:
            s.save(self.path, state)
        except ValueError:
            assert self.path.read_bytes() == before
            self.rejected.append(state)
            raise
        self.saved.append(state)


def test_byte_overflow_start_does_not_strand_off_and_another_durable_stop(tmp_path):
    # Count-valid Starts are larger than Stops. Choose the boundary independently,
    # then prove last-fit and next-refusal using the real complete-journal writer.
    state = replace(
        PAIRED_STATE,
        identity=maximal_state().identity,
        device_id=DEVICE.device_id,
        session_expires_at=DEVICE.session_expires_at,
        feature_enabled=True,
        approved_capabilities=DEVICE.approved_capabilities,
        session_approved_capabilities=DEVICE.session_approved_capabilities,
        acknowledged_capabilities=DEVICE.acknowledged_capabilities,
        observed_participation=DEVICE.participation,
    )
    state, candidate = start_boundary(state)
    command = candidate.pending_source_commands[-1]
    store = DiskStore(tmp_path / "fleet.json", state)
    before = fixture_bytes(state)
    assert store.path.read_bytes() == before
    assert store.load() == state
    assert len(candidate.pending_source_commands) <= p.MAX_SOURCE_INTENTS
    with pytest.raises(s.CapacityError, match="size limit"):
        store.save(candidate)
    assert store.path.read_bytes() == before
    assert store.load() == state
    mono = [1000.0]
    client = FakeRelayClient(device=DEVICE)
    worker = _worker(
        client,
        store=store,
        clock=lambda: mono[0],
        utc_clock=lambda: NOW + timedelta(seconds=mono[0] - 1000),
        sharing_enabled=lambda: False,
    )
    # The failing new source heads the queue, Off and a different saved source's
    # Stop follow. Off must inhibit even before the first owner turn.
    assert worker._queue_source(command)
    off = worker.request_participation(False)
    target = state.pending_source_commands[0].source_id
    assert worker.request_source_stop(target)
    assert worker.status().local_inhibited
    worker.iterate_once()
    assert candidate in store.rejected
    drive(worker, mono, 40)
    assert client.device.participation.enabled is False
    assert client.source_views[target].state == "ended"
    assert not any(c.source_id == command.source_id for c in client.controls)
    assert store.load().pending_participation is None
    assert off is not None
    assert client.cadence_refusals == 0
    assert any(
        item.source_id == command.source_id and item.stage == "rejected"
        for item in worker.status().source_results
    )


def test_full_saved_journal_can_reconcile_off_without_discarding_prior_starts(tmp_path):
    state, _ = start_boundary(replace(PAIRED_STATE, last_revision=9), indented=True)
    path = tmp_path / "full.json"
    # A valid protected blob plus a valid ASCII origin can fill the last few
    # bytes exactly. No source is invalid, expired or over the command count.
    remaining = s.MAX_STATE_FILE_BYTES - len(fixture_bytes(state, indented=True))
    blob_length = len(state.identity.protected_private_key_b64) + remaining // 4 * 4
    state = replace(
        state,
        identity=replace(
            state.identity,
            protected_private_key_b64=base64.b64encode(
                bytes(blob_length // 4 * 3)
            ).decode(),
        ),
        relay_origin="https://relay" + "a" * (remaining % 4) + ".test",
    )
    before = fixture_bytes(state, indented=True)
    path.write_bytes(before)
    assert path.stat().st_size == 65536
    assert s.load(path) == state
    assert path.read_bytes() == before
    assert len(state.pending_source_commands) < p.MAX_SOURCE_INTENTS
    assert len(fixture_bytes(replace(state, last_revision=10), indented=True)) == 65537
    # Loading never rewrites; the first real owner write must compact the file.
    store = DiskStore.__new__(DiskStore)
    store.path, store.saved, store.rejected = path, [], []

    first_write = []

    def save_and_capture_first_write(candidate):
        store.save(candidate)
        if len(store.saved) == 1:
            first_write.append(path.read_bytes())

    mono = [1000.0]
    client = FakeRelayClient(device=DEVICE)
    worker = _worker(
        client,
        store=store,
        clock=lambda: mono[0],
        utc_clock=lambda: NOW + timedelta(seconds=mono[0] - 1000),
        sharing_enabled=lambda: False,
        save_state=save_and_capture_first_write,
    )
    off = worker.request_participation(False)
    assert worker.status().local_inhibited
    drive(worker, mono, 20)
    # Assert outside the save callback: the owner treats callback exceptions as
    # retryable I/O failure, which could otherwise hide a failed assertion.
    assert len(first_write) == 1
    assert len(fixture_bytes(store.saved[0], indented=True)) > 65536
    assert first_write[0] == fixture_bytes(store.saved[0])
    assert len(first_write[0]) < 65536
    assert client.device.participation.enabled is False
    assert off is not None
    assert all(c in state.pending_source_commands for c in client.controls)
    remaining_ids = {c.source_id for c in store.load().pending_source_commands}
    assert all(
        c.source_id in remaining_ids or c.source_id in client.source_views
        for c in state.pending_source_commands
    )


def test_compaction_keeps_all_legal_maximum_fields_and_256_stops(tmp_path):
    state = maximal_state(stops=True)
    assert len(state.identity.protected_private_key_b64) == 8192
    assert len(state.pending_pairing.approval_url) == 2048
    assert len(state.session_id) == 128
    assert len(state.pending_source_commands) == 256
    # Validate every field together, independently of the new capacity helper.
    assert s._parse_v3(p.decode_json(compact_bytes(state))) == state
    assert len(legacy_bytes(state)) > 65536
    assert len(compact_bytes(state)) < 65536
    path = tmp_path / "max-stops.json"
    s.save(path, state)
    assert s.load(path) == state
    assert path.read_bytes() == compact_bytes(state)


def test_compact_maximum_starts_still_refused_with_last_bytes_intact(tmp_path):
    state = maximal_state()
    assert s._parse_v3(p.decode_json(compact_bytes(state))) == state
    assert len(compact_bytes(state)) > 65536
    path = tmp_path / "max-starts.json"
    s.save(path, PAIRED_STATE)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="size limit"):
        s.save(path, state)
    assert path.read_bytes() == before


def test_start_admission_reserves_all_metadata_and_unused_stop_slots(tmp_path):
    # Current bytes alone fit, but accepting all these Starts leaves no room for
    # later bounded metadata, recovery, Off or Stop. Refuse before saving/sending.
    state = replace(
        PAIRED_STATE,
        pending_source_commands=tuple(
            p.StartSource(c.source_id, 1, UUID, DATE)
            for c in maximal_state().pending_source_commands[:200]
        ),
    )
    assert len(compact_bytes(state)) < 65536
    store = DiskStore(tmp_path / "admission.json", state)
    mono = [1000.0]
    client = FakeRelayClient(device=DEVICE)
    worker = _worker(
        client, store=store, clock=lambda: mono[0], sharing_enabled=lambda: False
    )
    new_id = worker.request_source_start(1, UUID)
    worker.iterate_once()
    assert any(
        item.source_id == new_id and item.stage == "rejected"
        for item in worker.status().source_results
    )
    assert all(c.source_id != new_id for c in store.load().pending_source_commands)
    assert client.controls == []


def test_transient_atomic_failure_retains_original_queued_and_durable_intents(
    tmp_path, monkeypatch
):
    store = DiskStore(tmp_path / "transient.json", PAIRED_STATE)
    mono = [1000.0]
    client = FakeRelayClient(device=DEVICE)
    worker = _worker(
        client, store=store, clock=lambda: mono[0], sharing_enabled=lambda: False
    )
    start = worker.request_source_start(1, UUID)
    off = worker.request_participation(False)
    before = store.path.read_bytes()
    with monkeypatch.context() as patch:

        def fail(*args):
            raise OSError("controlled disk failure")

        patch.setattr(s.atomicio, "write_atomic", fail)
        drive(worker, mono, 4)
        assert store.path.read_bytes() == before
        assert worker.status().detail == "persistence_failed"
        assert worker.status().local_inhibited
        assert worker.status().source_results == ()
        assert worker._commands["participation"].payload.intent_id == off
        assert worker._commands["source:" + start].payload.source_id == start
        assert client.calls == []
    drive(worker, mono, 20)
    assert client.device.participation.enabled is False
    assert client.source_views[start].state == "active"
    assert any(c.source_id == start for c in client.controls)


def test_headroom_dominates_all_mutable_bounds_and_256_stop_slots(tmp_path):
    maximum = maximal_state()
    # This assertion deliberately requires a new persisted field to acquire an
    # explicit bound review, rather than silently reserving its default null.
    assert set(s.SharingState.__dataclass_fields__) == {
        "identity",
        "relay_origin",
        "session_id",
        "last_revision",
        "device_id",
        "session_expires_at",
        "feature_enabled",
        "approved_capabilities",
        "session_approved_capabilities",
        "acknowledged_capabilities",
        "observed_participation",
        "pending_recovery",
        "pending_source_commands",
        "pending_pairing",
        "pending_participation",
        "auth_pause",
    }
    admitted = replace(maximum, pending_source_commands=())
    s.check_admission_capacity(admitted)
    for command in maximum.pending_source_commands:
        candidate = replace(
            admitted,
            pending_source_commands=(*admitted.pending_source_commands, command),
        )
        try:
            s.check_admission_capacity(candidate)
        except s.CapacityError:
            break
        admitted = candidate
    else:
        pytest.fail("Maximum legal metadata and Starts must exhaust bytes before count")
    # No magic admitted count: bound is measured from this identity and bytes.
    existing = admitted.pending_source_commands
    filled = replace(
        admitted,
        pending_source_commands=(
            *existing,
            *maximal_state(stops=True).pending_source_commands[len(existing) :],
        ),
    )
    assert s._parse_v3(p.decode_json(compact_bytes(filled))) == filled
    assert (
        len(compact_bytes(filled))
        <= len(s._compact(s._admission_envelope(admitted)).encode())
        <= 65536
    )
    path = tmp_path / "reserved.json"
    s.save(path, filled)
    assert s.load(path) == filled
    assert 0 < len(existing) < 256


def test_full_count_stop_is_retained_until_prior_work_releases_slot_and_restart(
    tmp_path,
):
    state = replace(
        PAIRED_STATE,
        pending_source_commands=tuple(
            p.StartSource(c.source_id, 1, UUID, DATE)
            for c in maximal_state().pending_source_commands
        ),
    )
    store = DiskStore(tmp_path / "full-count.json", state)
    mono = [1000.0]
    client = FakeRelayClient(device=DEVICE)
    worker = _worker(
        client, store=store, clock=lambda: mono[0], sharing_enabled=lambda: False
    )
    target = UUID
    assert worker.request_source_stop(target)
    off = worker.request_participation(False)
    worker.iterate_once()
    assert worker._commands["source:" + target].payload.source_id == target
    assert store.load().pending_participation.intent_id == off
    for _ in range(20):
        drive(worker, mono, 1)
        if any(c.source_id == target for c in store.load().pending_source_commands):
            break
    else:
        pytest.fail("Deferred Stop was dropped or prevented prior reconciliation")
    # Recreate the real disk-backed owner after Stop is saved but before send.
    restarted = _worker(
        client, store=store, clock=lambda: mono[0], sharing_enabled=lambda: False
    )
    restarted.resume_pending()
    drive(restarted, mono, 20)
    assert client.source_views[target].state == "ended"
    assert client.device.participation.enabled is False
    assert client.cadence_refusals == 0


def test_full_memory_queue_still_accepts_stop_for_existing_durable_source(tmp_path):
    state = replace(
        PAIRED_STATE, pending_source_commands=(p.StartSource(UUID, 1, UUID, DATE),)
    )
    store = DiskStore(tmp_path / "full-queue.json", state)
    client = FakeRelayClient(device=DEVICE)
    worker = _worker(client, store=store, sharing_enabled=lambda: False)
    worker.resume_pending()
    worker.iterate_once()
    starts = [worker.request_source_start(1, UUID) for _ in range(p.MAX_SOURCE_INTENTS)]
    assert all(starts)
    assert worker.request_source_stop(UUID)
    assert all("source:" + source in worker._commands for source in starts)
    worker.iterate_once()
    assert any(
        c.source_id == UUID and isinstance(c, p.StopSource)
        for c in store.load().pending_source_commands
    )
    assert all(
        any(c.source_id == source for c in store.load().pending_source_commands)
        or any(
            r.source_id == source and r.stage == "rejected"
            for r in worker.status().source_results
        )
        for source in starts
    )


def test_real_thread_preserves_inflight_start_and_queued_off_stop_through_io_failure(
    tmp_path,
):
    store = DiskStore(tmp_path / "inflight.json", PAIRED_STATE)
    client = FakeRelayClient(device=DEVICE)
    client.hold = "control_source"
    fail_disk, failed = threading.Event(), threading.Event()

    def save(state):
        if fail_disk.is_set():
            failed.set()
            raise OSError("controlled atomic failure")
        store.save(state)

    worker = _worker(
        client,
        store=store,
        clock=time.monotonic,
        thread_factory=threading.Thread,
        sharing_enabled=lambda: False,
        save_state=save,
    )
    source = worker.request_source_start(1, UUID)
    assert worker.start()
    try:
        assert client.entered.wait(5)
        before = store.path.read_bytes()
        original = store.load().pending_source_commands[0]
        assert original.source_id == source
        fail_disk.set()
        off = worker.request_participation(False)
        assert worker.request_source_stop(source)
        assert worker.status().local_inhibited
        client.hold = None
        client.release.set()
        assert failed.wait(3)
        assert store.path.read_bytes() == before
        assert store.load().pending_source_commands == (original,)
        assert worker._commands["participation"].payload.intent_id == off
        assert isinstance(worker._commands["source:" + source].payload, p.StopSource)
        fail_disk.clear()
        worker._pending.set()
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            saved = store.load()
            if (
                client.source_views.get(source)
                and client.source_views[source].state == "ended"
                and not client.device.participation.enabled
                and not saved.pending_source_commands
                and saved.pending_participation is None
            ):
                break
            time.sleep(0.01)
        else:
            pytest.fail("Real owner did not finish retained safety controls")
        assert client.source_intents[source] == original
        assert client.cadence_refusals == 0
    finally:
        fail_disk.clear()
        client.release.set()
        assert worker.stop()


def test_recovery_request_and_off_survive_restart_near_admission_capacity(tmp_path):
    # Fill from actual byte headroom, not a guessed number of commands.
    state = replace(PAIRED_STATE, identity=maximal_state().identity, session_id=None)
    for command in maximal_state().pending_source_commands:
        candidate = replace(
            state, pending_source_commands=(*state.pending_source_commands, command)
        )
        try:
            s.check_admission_capacity(candidate)
        except s.CapacityError:
            break
        state = candidate
    from tests.test_fleetsharing_worker import TOKEN

    state = replace(state, pending_recovery=s.PendingRecovery(TOKEN, DATE))
    store = DiskStore(tmp_path / "recovery.json", state)
    mono = [1000.0]
    client = FakeRelayClient(device=DEVICE)
    client.loss.add("begin_recovery")
    worker = _worker(
        client, store=store, clock=lambda: mono[0], sharing_enabled=lambda: False
    )
    off = worker.request_participation(False)
    target = state.pending_source_commands[0].source_id
    assert worker.request_source_stop(target)
    drive(worker, mono, 3)
    pending = store.load().pending_recovery
    assert pending.request_id == TOKEN and pending.issued_at == DATE
    assert pending.challenge is None
    assert store.load().pending_participation.intent_id == off
    restarted = _worker(
        client, store=store, clock=lambda: mono[0], sharing_enabled=lambda: False
    )
    restarted.resume_pending()
    drive(restarted, mono, 40)
    assert client.device.participation.enabled is False
    assert client.source_views[target].state == "ended"
    assert store.load().pending_recovery is None
    assert store.load().pending_participation is None
    assert len(client.admissions) == 1
    assert next(iter(client.admissions))[1] == TOKEN
    assert client.cadence_refusals == 0


def test_compact_candidate_io_failure_preserves_last_good_bytes(tmp_path, monkeypatch):
    path = tmp_path / "compact-io.json"
    s.save(path, PAIRED_STATE)
    before = path.read_bytes()
    candidate = maximal_state(stops=True)
    reached = []

    def fail(target, data):
        assert len(data.encode()) < 65536
        assert data == compact_bytes(candidate).decode()
        reached.append(target)
        raise OSError("controlled disk failure")

    monkeypatch.setattr(s.atomicio, "write_atomic", fail)
    with pytest.raises(OSError):
        s.save(path, candidate)
    assert reached == [path]
    assert path.read_bytes() == before
    assert s.load(path) == PAIRED_STATE


def test_upgrade_admission_cannot_consume_future_pairing_response_headroom(tmp_path):
    state = replace(
        PAIRED_STATE,
        pending_source_commands=maximal_state().pending_source_commands[:200],
    )
    store = DiskStore(tmp_path / "upgrade-capacity.json", state)
    client = FakeRelayClient(device=DEVICE)
    worker = _worker(client, store=store, sharing_enabled=lambda: False)
    assert worker.request_pairing(mode="upgrade")
    worker.iterate_once()
    assert worker.status().pairing == "rejected"
    assert store.load().pending_pairing is None
    assert store.load().session_id == state.session_id
    assert store.load().pending_source_commands == state.pending_source_commands
    assert client.pair_keys == []
