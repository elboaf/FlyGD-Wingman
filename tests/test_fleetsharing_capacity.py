"""State4 runtime capacity — terminal work never borrows or evicts history.

The former state3 pretty/ASCII fallback and sub-256 byte-bound expectations are
superseded by disjoint state4 reserves. These proofs retain the real writer,
full-count admission, failed-write and callback authority boundaries.
"""

import json
from dataclasses import replace

import pytest

from tests.fleetsharing_capacity_helpers import source_id
from tests.test_fleetsharing_state4_capacity import maximal_document
from tests.test_fleetsharing_worker import DATE, PAIRED_STATE, UUID, drive
from tests.test_fleetsharing_worker_automatic import ON, automatic_rig
from tests.test_fleetsharing_worker_state4 import FileStore, file_rig
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing import state as s


class DiskStore(FileStore):
    def __init__(self, path, state):
        super().__init__(path)
        self.saved = self.saves
        self.rejected = []
        s.save(path, state)


def full_sources():
    return tuple(
        p.SourceStart(source_id(i), p.JS_SAFE_MAX, UUID, "2026-09-07T11:58:00.000Z")
        for i in range(256)
    )


@pytest.mark.parametrize("kind", ["start", "stop"])
def test_full_count_refuses_only_new_unrelated_source(tmp_path, kind):
    worker, client, store, _mono = file_rig(tmp_path)
    sources = full_sources()
    s.save(store.path, replace(s.load(store.path), pending_source_commands=sources))
    worker.resume_pending()
    worker.iterate_once()
    if kind == "start":
        target = worker.request_source_start(1, UUID)
    else:
        target = UUID
        assert worker.request_source_stop(
            target, expected_generation=0, expected_automatic=None
        )
    worker.iterate_once()
    assert s.load(store.path).pending_source_commands == sources
    assert "source:" + target not in worker._commands
    assert any(
        v.source_id == target and v.stage == "rejected"
        for v in worker.status().source_results
    )
    assert not client.controls


def test_full_count_existing_slot_requires_ack_but_does_not_evict_neighbors(tmp_path):
    worker, _client, store, _mono = file_rig(tmp_path)
    sources = full_sources()
    s.save(store.path, replace(s.load(store.path), pending_source_commands=sources))
    worker.resume_pending()
    worker.iterate_once()
    old = sources[0]
    assert worker.request_source_stop(
        old.source_id,
        expected_generation=7,
        expected_automatic=p.AutomaticBinding(3),
        supersedes=old,
    )
    worker.iterate_once()
    saved = s.load(store.path).pending_source_commands
    assert len(saved) == 256 and saved[:-1] == sources[1:]
    assert isinstance(saved[-1], p.SourceStop)
    assert saved[-1].expected_generation == 7 and saved[
        -1
    ].expected_automatic == p.AutomaticBinding(3)


def test_full_memory_queue_preserves_existing_slot_and_refuses_unrelated_growth(
    tmp_path,
):
    worker, _client, store, _mono = file_rig(tmp_path)
    old = full_sources()[0]
    s.save(store.path, replace(s.load(store.path), pending_source_commands=(old,)))
    worker.resume_pending()
    worker.iterate_once()
    queued = [worker.request_source_start(1, UUID) for _ in range(256)]
    assert all(queued)
    assert worker.request_source_stop(
        old.source_id, expected_generation=0, expected_automatic=None, supersedes=old
    )
    worker.iterate_once()
    saved = s.load(store.path).pending_source_commands
    assert len(saved) == 256
    assert any(
        isinstance(c, p.SourceStop) and c.source_id == old.source_id for c in saved
    )
    retained = {c.source_id for c in saved}
    refused = {
        v.source_id for v in worker.status().source_results if v.stage == "rejected"
    }
    assert set(queued) <= retained | refused


@pytest.mark.parametrize("attempted", [False, True])
def test_full_source_count_cannot_strand_automatic_off(tmp_path, attempted):
    command = p.AutomaticCommand(UUID, DATE, False, 1, 1)
    worker, store, mono, _, attempts, _ = automatic_rig(
        tmp_path, s.PendingAutomatic(command, attempted), observed=ON
    )
    sources = full_sources()
    s.save(store.path, replace(s.load(store.path), pending_source_commands=sources))
    drive(worker, mono, 10)
    saved = s.load(store.path)
    assert saved.pending_source_commands == sources
    assert (
        saved.automatic.pending is None
        and saved.automatic.last_result.outcome == "receipt"
    )
    assert len(attempts) == 1 and attempts[0].automatic.pending.attempted


def test_max_digits_full_archive_and_sources_keep_cancel_and_derived_off_capacity(
    tmp_path,
):
    maximum = p.JS_SAFE_MAX
    consent = p.Consent(maximum - 2, maximum - 2, True, UUID, DATE, None, None)
    command = p.AutomaticCommand(UUID, DATE, True, maximum - 2, maximum - 2)
    worker, store, mono, _, attempts, _ = automatic_rig(
        tmp_path, s.PendingAutomatic(command), observed=consent
    )
    raw, _ = maximal_document()
    raw["identity"]["public_key_spki_b64"] = PAIRED_STATE.identity.public_key_spki_b64
    raw["cutover"]["original"]["identity"]["public_key_spki_b64"] = (
        PAIRED_STATE.identity.public_key_spki_b64
    )
    maximal = s._parse_v4(raw)
    original = maximal.cutover
    source_commands = full_sources()
    candidate = replace(
        maximal,
        last_revision=p.INT4_MAX - 5,
        pending_pairing=None,
        pending_recovery=None,
        auth_pause=None,
        pending_participation=None,
        pending_source_commands=source_commands,
        automatic=s.AutomaticState(consent, s.PendingAutomatic(command)),
    )
    s.save(store.path, candidate)
    factory = worker._client_factory
    cancellations = []

    def client_factory(origin):
        client = factory(origin)
        transport = client._transport

        def cancel_on_send(request, timeout):
            if request.method == "PUT" and json.loads(request.data)["enabled"]:
                cancellations.append(
                    worker.request_cancel_automatic_on(
                        UUID, binding=worker.status().metadata.binding
                    )
                )
            return transport(request, timeout)

        client._transport = cancel_on_send
        return client

    worker._client_factory = client_factory
    drive(worker, mono, 12)
    saved = s.load(store.path)
    assert [v.automatic.pending.command.enabled for v in attempts] == [True, False]
    assert (
        saved.pending_source_commands == source_commands and saved.cutover == original
    )
    assert saved.automatic.pending is None
    assert saved.automatic.last_result.receipt.result.revision == maximum
    assert saved.automatic.last_result.pending.command.request_id == cancellations[0]
    assert all(v.cutover == original for v in store.saves)
    assert any(
        v.automatic.pending
        and not v.automatic.pending.command.enabled
        and v.automatic.last_result.pending.cancel_after_on is not None
        for v in store.saves
    )
    assert store.path.stat().st_size <= s.MAX_STATE_FILE_BYTES


def test_atomic_failure_preserves_exact_queue_body_and_last_good_file(
    tmp_path, monkeypatch
):
    worker, client, store, mono = file_rig(tmp_path)
    target = worker.request_source_start(1, UUID)
    command = worker._commands["source:" + target].payload
    before = store.path.read_bytes()
    write = s.atomicio.write_atomic

    def fail(path, text):
        raise OSError("controlled write failure")

    monkeypatch.setattr(s.atomicio, "write_atomic", fail)
    drive(worker, mono, 4)
    assert store.path.read_bytes() == before
    assert worker._commands["source:" + target].payload == command
    assert not client.calls
    monkeypatch.setattr(s.atomicio, "write_atomic", write)
    worker.iterate_once()
    assert command in s.load(store.path).pending_source_commands


def test_reentrant_new_source_during_admission_is_not_relabelled_as_old_ack(tmp_path):
    worker, client, store, _mono = file_rig(tmp_path)
    old = worker.request_source_start(1, UUID)
    save = worker._save_state
    newer = []

    def save_and_queue(candidate):
        save(candidate)
        if not newer:
            newer.append(worker.request_source_start(1, UUID))

    worker._save_state = save_and_queue
    worker.iterate_once()
    assert newer[0] in {v.source_id for v in worker.status().pending_sources}
    assert "source:" + newer[0] in worker._commands
    assert {c.source_id for c in s.load(store.path).pending_source_commands} == {old}
    assert not client.controls


def test_full_capacity_restart_keeps_authentication_and_terminal_journals(tmp_path):
    from tests.fleetsharing_worker_control_helpers import ControlRelay
    from tests.test_fleetsharing_worker import DEVICE, TOKEN, FakeRelayClient, _worker
    from wingman.fleetsharing.client import FleetRelayClient

    sources = full_sources()
    stop = p.SourceStop(sources[0].source_id, 0, UUID, DATE, None)
    automatic = p.AutomaticCommand(
        "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", DATE, False, 1, 1
    )
    original = replace(
        s.replace_session(PAIRED_STATE, None),
        device_id=UUID,
        pending_recovery=s.PendingRecovery(TOKEN, DATE),
        pending_source_commands=(stop, *sources[1:]),
        pending_participation=s.PendingParticipation(UUID, False, 1),
        automatic=s.AutomaticState(ON, s.PendingAutomatic(automatic, True)),
    )
    worker, _, store, mono = file_rig(tmp_path, original)
    relay = ControlRelay(worker, store)
    relay.consent = ON
    worker.resume_pending()
    for _ in range(8):
        drive(worker, mono, 1)
        if s.load(store.path).pending_recovery.challenge:
            break
    saved = s.load(store.path)
    assert (
        saved.pending_recovery.challenge
        and not saved.pending_recovery.completion_attempted
    )
    assert (
        saved.pending_recovery.request_id == TOKEN
        and saved.pending_recovery.issued_at == DATE
    )
    assert saved.pending_source_commands == original.pending_source_commands
    assert worker.stop()
    replacement = _worker(
        FakeRelayClient(device=DEVICE),
        store=store,
        timing_context=worker._timing_context,
        utc_clock=worker._utc_clock,
        sharing_enabled=lambda: False,
    )
    relay.worker = replacement
    replacement._client_factory = lambda origin: FleetRelayClient(
        origin, transport=relay.transport
    )
    replacement.resume_pending()
    unrelated = replacement.request_source_start(1, UUID)
    drive(replacement, mono, 30)
    final = s.load(store.path)
    assert final.pending_recovery is None and final.session_id
    assert final.pending_source_commands == sources[1:]
    assert (
        final.pending_participation is None and not relay.device.participation.enabled
    )
    assert (
        final.automatic.pending is None and not final.automatic.observed_consent.enabled
    )
    assert stop.request_id in relay.receipts and automatic.request_id in relay.receipts
    assert any(
        v.source_id == unrelated and v.stage == "rejected"
        for v in replacement.status().source_results
    )
    complete = [
        (request, state)
        for request, state in relay.calls
        if "/recovery-challenges/" in request.full_url
    ]
    assert len(complete) == 1 and complete[0][1].pending_recovery.completion_attempted
    assert complete[0][1].pending_recovery.request_id == TOKEN
    assert all(state.identity == original.identity for _, state in relay.calls)


@pytest.mark.parametrize("stop_target", ["same-source", "unrelated"])
def test_real_thread_preserves_inflight_start_and_queued_off_stop_through_io_failure(
    tmp_path, monkeypatch, stop_target
):
    import threading
    import time

    from tests.fleetsharing_worker_control_helpers import ControlRelay
    from tests.test_fleetsharing_worker import DEVICE, NOW, FakeRelayClient, _worker

    sources = full_sources()[:-1]
    store = DiskStore(
        tmp_path / "held.json", replace(PAIRED_STATE, pending_source_commands=sources)
    )
    worker = _worker(
        FakeRelayClient(device=DEVICE),
        store=store,
        clock=time.monotonic,
        utc_clock=lambda: NOW,
        thread_factory=threading.Thread,
        sharing_enabled=lambda: False,
    )
    relay = ControlRelay(worker, store)
    entered, release, failed, allow_write, conflicted = (
        threading.Event() for _ in range(5)
    )
    completions, failed_writes, failure_statuses = [], [], []
    target = worker.request_source_start(1, UUID)

    def before(request, saved):
        if (
            request.method == "PUT"
            and request.full_url.endswith("/sources")
            and json.loads(request.data)["operation"] == "start"
            and not entered.is_set()
        ):
            entered.set()
            completions.append(release.wait(5))

    def status_changed(value):
        if value.detail == "persistence_failed" and failed_writes:
            # This witness runs only after the writer's OSError reached the owner.
            failure_statuses.append(value)
            failed.set()
        if value.detail == "conflict":
            conflicted.set()

    relay.before = before
    worker.subscribe_status(status_changed)
    write = s.atomicio.write_atomic

    def save(path, text):
        candidate = json.loads(text)
        if not allow_write.is_set() and (
            candidate["pending_participation"]
            or any(
                c["operation"] == "stop" for c in candidate["pending_source_commands"]
            )
        ):
            failed_writes.append(candidate)
            raise OSError("queued terminal write failed after held Start")
        write(path, text)

    def wait_for(predicate):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.02)
        pytest.fail("terminal progress not externally witnessed")

    monkeypatch.setattr(s.atomicio, "write_atomic", save)
    assert worker.start()
    try:
        assert entered.wait(5)
        before_bytes = store.path.read_bytes()
        before_state = s.load(store.path)
        start = next(
            c for c in before_state.pending_source_commands if c.source_id == target
        )
        old = start if stop_target == "same-source" else sources[0]
        off = worker.request_participation(
            False, expected_generation=1, binding=worker.status().metadata.binding
        )
        assert off
        assert worker.request_source_stop(
            old.source_id,
            expected_generation=0,
            expected_automatic=None,
            supersedes=old,
            binding=worker.status().metadata.binding,
        )
        queued = dict(worker._commands)
        stop_action = queued["source:" + old.source_id]
        stop = stop_action.payload
        assert stop_action.supersedes == old
        assert stop.expected_generation == 0 and stop.expected_automatic is None
        assert queued["participation"].payload == s.PendingParticipation(off, False, 1)
        assert store.path.read_bytes() == before_bytes
        release.set()
        assert failed.wait(5) and completions == [True]
        assert failed_writes and failure_statuses
        assert worker.status().local_inhibited
        assert store.path.read_bytes() == before_bytes, (
            "failed write changed last good bytes"
        )
        assert s.load(store.path) == before_state
        assert dict(worker._commands) == queued, "failed write changed queued intents"
        assert before_state.pending_source_commands == (*sources, start)
        assert before_state.pending_participation is None
        assert relay.starts == {target: start}
        assert not relay.receipts and relay.device.participation.enabled
        allow_write.set()
        worker._pending.set()
        if stop_target == "same-source":
            # The held Start committed remotely, so the original immutable CAS0
            # must conflict. A fresh observed CAS1 requires a NEW whole-ack action.
            assert worker.set_source_watch(True)
            wait_for(
                lambda: (
                    conflicted.is_set()
                    and worker.status().sources is not None
                    and any(
                        v.source_id == target for v in worker.status().sources.sources
                    )
                )
            )
            observed = next(
                v for v in worker.status().sources.sources if v.source_id == target
            )
            assert observed.generation == 1 and observed.automatic is None
            assert observed.state == "active"
            assert stop in s.load(store.path).pending_source_commands
            assert stop.request_id not in relay.receipts
            original_puts = [
                p.parse_source_command(json.loads(request.data))
                for request, _ in relay.calls
                if request.method == "PUT"
                and request.full_url.endswith("/sources")
                and json.loads(request.data)["operation"] == "stop"
            ]
            assert original_puts and all(command == stop for command in original_puts)
            # Capture the explicit new action before the live owner ingests it.
            with worker._iteration_lock:
                assert worker.request_source_stop(
                    target,
                    expected_generation=observed.generation,
                    expected_automatic=observed.automatic,
                    supersedes=stop,
                    binding=worker.status().metadata.binding,
                )
                replacement_action = worker._commands["source:" + target]
                assert replacement_action.supersedes == stop
                replacement = replacement_action.payload
            assert replacement.request_id != stop.request_id
            assert replacement.expected_generation == 1
            assert replacement.expected_automatic is None
            terminal = replacement
        else:
            terminal = stop

        def settled():
            saved = s.load(store.path)
            return (
                saved.pending_participation is None
                and not relay.device.participation.enabled
                and terminal.request_id in relay.receipts
                and terminal not in saved.pending_source_commands
            )

        wait_for(settled)
        saved = s.load(store.path)
        assert saved.observed_participation == p.Participation(False, 2)
        participation_puts = [
            (json.loads(request.data), state.pending_participation)
            for request, state in relay.calls
            if request.full_url.endswith("/participation")
        ]
        assert participation_puts == [
            (
                {"protocol": 2, "enabled": False, "expected_generation": 1},
                replace(queued["participation"].payload, attempted=True),
            )
        ]
        stop_puts = [
            p.parse_source_command(json.loads(request.data))
            for request, _ in relay.calls
            if request.method == "PUT"
            and request.full_url.endswith("/sources")
            and json.loads(request.data)["operation"] == "stop"
        ]
        assert terminal in stop_puts and all(c in (stop, terminal) for c in stop_puts)
        assert len(relay.receipts) == 1
        receipt = relay.receipts[terminal.request_id]
        assert p.parse_source_command(receipt["command"]) == terminal
        assert receipt["source"]["source_id"] == old.source_id
        assert receipt["source"]["state"] == "ended"
        assert relay.sources[old.source_id].state == "ended"
        assert relay.starts == {target: start}
        if stop_target == "same-source":
            assert saved.pending_source_commands == sources
            assert receipt["automatic_effect"] == "manual_only"
            assert receipt["source"]["generation"] == 2
            assert stop.request_id not in relay.receipts
        else:
            # Exact neighbor preservation; the independent Start may settle only
            # through a separately witnessed replay of its exact original body.
            remaining = tuple(c for c in saved.pending_source_commands if c != start)
            assert remaining == sources[1:]
            if start not in saved.pending_source_commands:
                start_puts = [
                    p.parse_source_command(json.loads(request.data))
                    for request, _ in relay.calls
                    if request.method == "PUT"
                    and request.full_url.endswith("/sources")
                    and json.loads(request.data)["operation"] == "start"
                ]
                assert len(start_puts) >= 2 and all(c == start for c in start_puts)
        assert not worker._commands
    finally:
        release.set()
        allow_write.set()
        assert worker.stop(timeout=5)


def test_failed_terminal_write_guard_kills_in_memory_queue_loss_mutant(
    tmp_path, monkeypatch
):
    from wingman.fleetsharing import worker as owner

    ingest = owner.FleetSharingWorker._ingest_control

    def discard_failed_admission(self, command, fence):
        try:
            return ingest(self, command, fence)
        except owner._PersistenceFailed:
            if command.kind == "participation":
                self._drop_command("participation", command)
            raise

    monkeypatch.setattr(
        owner.FleetSharingWorker, "_ingest_control", discard_failed_admission
    )
    with pytest.raises(AssertionError, match="failed write changed queued intents"):
        test_real_thread_preserves_inflight_start_and_queued_off_stop_through_io_failure(
            tmp_path, monkeypatch, stop_target="same-source"
        )


def test_held_start_guard_kills_in_memory_source_fence_mutant(tmp_path, monkeypatch):
    from wingman.fleetsharing.worker import FleetSharingWorker

    check = FleetSharingWorker._check_locked

    def admit_stale_source(self, fence, *, work=None):
        # Remove only the same-source queued-command/generation response fence.
        if work is not None and work.operation == "control_source":
            work = replace(work, operation="fetch_receipt")
        return check(self, fence, work=work)

    monkeypatch.setattr(FleetSharingWorker, "_check_locked", admit_stale_source)
    with pytest.raises(AssertionError, match="failed write changed last good bytes"):
        test_real_thread_preserves_inflight_start_and_queued_off_stop_through_io_failure(
            tmp_path, monkeypatch, stop_target="same-source"
        )
