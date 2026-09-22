"""S4-B review regressions — real writer/client, externally witnessed barriers."""

import json
from dataclasses import replace

import pytest

from tests.test_fleetsharing_worker import DATE, DEVICE, UUID, drive
from tests.test_fleetsharing_worker_automatic import (
    OFF,
    ON,
    automatic_rig,
    receipt_body,
    status,
)
from tests.test_fleetsharing_worker_controls import real_client, wire
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing import state as s


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("supersession", [False, True])
@pytest.mark.parametrize("barrier", ["write", "notification"])
def test_committed_automatic_admission_finalizes_despite_new_source_action(
    tmp_path, monkeypatch, enabled, supersession, barrier
):
    old = s.PendingAutomatic(p.AutomaticCommand(UUID, DATE, True, 0, 0))
    worker, store, mono, _, attempts, _ = automatic_rig(tmp_path)
    worker.iterate_once()
    worker.request_automatic_status(binding=worker.status().metadata.binding)
    drive(worker, mono, 3)
    if supersession:
        # Retain an unsent original with the exact displayed acknowledgement.
        s.save(
            store.path,
            replace(s.load(store.path), automatic=s.AutomaticState(OFF, old)),
        )
        worker._state = s.load(store.path)
        worker._project_saved()
    reached = []
    action = worker.request_automatic(
        enabled,
        expected_generation=0,
        expected_revision=0,
        binding=worker.status().metadata.binding,
        supersedes=old if supersession else None,
    )
    assert action

    def interrupt(candidate):
        pending = candidate.automatic.pending
        if pending and pending.command.request_id == action and not reached:
            reached.append(None)
            reached[0] = worker.request_source_start(1, UUID)

    if barrier == "write":
        from wingman import atomicio

        write = atomicio.write_atomic

        def saving(path, text, **kwargs):
            write(path, text, **kwargs)
            interrupt(s.load(store.path))

        monkeypatch.setattr(atomicio, "write_atomic", saving)
    else:
        worker.subscribe_status(lambda value: interrupt(worker._state))
    worker.iterate_once()
    assert reached and reached[0] is not None
    assert s.load(store.path).automatic.pending.command.request_id == action
    assert "automatic" not in worker._commands
    assert worker._automatic_fenced_command is None
    drive(worker, mono, 20)
    assert worker._automatic_fenced_command is None
    final = s.load(store.path).automatic
    assert (
        final.pending is None and final.last_result.pending.command.request_id == action
    )
    assert len(attempts) == 1


@pytest.mark.parametrize("historical", [False, True])
def test_lower_current_on_cannot_converge_using_saved_higher_off(tmp_path, historical):
    command = p.AutomaticCommand(
        UUID, DATE, historical, 0 if historical else 1, 0 if historical else 1
    )
    pending = s.PendingAutomatic(
        command,
        True,
        s.CancelAfterOn("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", DATE)
        if historical
        else None,
    )
    higher_off = p.Consent(1, 2, False, UUID, DATE, DATE, "explicit_off")
    worker, store, mono, _, _, _ = automatic_rig(tmp_path, pending, observed=higher_off)
    offered = [ON]

    def reply(request, saved):
        if request.full_url.endswith("/device"):
            return {"protocol": 2, **wire(DEVICE)}, 200
        if historical and "/receipts/" in request.full_url:
            return {
                "protocol": 2,
                "receipt": receipt_body(command, ON),
                "status": wire(status(offered[0])),
            }, 200
        if "/receipts/" in request.full_url:
            return {"protocol": 2, "error": "receipt_not_found"}, 404
        assert request.method == "GET"
        return {"protocol": 2, "status": wire(status(offered[0]))}, 200

    real_client(worker, store, reply)
    drive(worker, mono, 6)
    saved = s.load(store.path).automatic
    assert saved.observed_consent == higher_off
    assert saved.pending is not None and not saved.pending.command.enabled
    if historical:
        assert saved.last_result.receipt.command == command
        assert saved.pending.command.request_id == pending.cancel_after_on.request_id
    else:
        assert saved.pending == pending and saved.last_result is None
    offered[0] = higher_off
    drive(worker, mono, 8)
    saved = s.load(store.path).automatic
    assert saved.pending is None and saved.last_result.outcome == "observed_off"


@pytest.mark.parametrize("kind", ["remove", "dismiss"])
@pytest.mark.parametrize("boundary", ["before_replace", "after_replace"])
def test_whole_on_action_during_derived_off_write_never_dispatches_off(
    tmp_path, monkeypatch, kind, boundary
):
    from wingman import atomicio

    command = p.AutomaticCommand(UUID, DATE, True, 0, 0)
    original = s.PendingAutomatic(
        command, True, s.CancelAfterOn("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", DATE)
    )
    worker, store, mono, _, _, _ = automatic_rig(tmp_path, original)
    reached, puts = [], []

    def reply(request, saved):
        if request.full_url.endswith("/device"):
            return {
                "protocol": 2,
                **wire(replace(DEVICE, server_time_ms=DEVICE.server_time_ms + 60000)),
            }, 200
        if request.method == "PUT":
            puts.append(json.loads(request.data))
            return {"protocol": 2, "error": "conflict"}, 409
        if "/receipts/" in request.full_url:
            return {
                "protocol": 2,
                "receipt": receipt_body(command, ON),
                "status": wire(status(ON)),
            }, 200
        return {"protocol": 2, "status": wire(status(ON))}, 200

    real_client(worker, store, reply)
    write = atomicio.write_atomic

    def saving(path, text, **kwargs):
        pending = json.loads(text)["automatic"]["pending"]
        target = (
            pending and not pending["command"]["enabled"] and not pending["attempted"]
        )
        if boundary == "after_replace":
            write(path, text, **kwargs)
        if target and not reached:
            reached.append(None)
            action = (
                worker.request_remove_automatic_cancel
                if kind == "remove"
                else worker.request_dismiss_automatic
            )
            reached[0] = action(original, binding=worker.status().metadata.binding)
        if boundary == "before_replace":
            write(path, text, **kwargs)

    monkeypatch.setattr(atomicio, "write_atomic", saving)
    drive(worker, mono, 12)
    assert reached == [True]
    assert not puts
    final = s.load(store.path).automatic
    assert final.pending is None
    assert final.last_result.pending == original
    assert final.last_result.receipt.command == command
    assert final.observed_consent == ON


@pytest.mark.parametrize("kind", ["cancel", "remove"])
@pytest.mark.parametrize("malformed", ["whole_command", "equal_revision"])
def test_whole_automatic_response_validated_before_queued_action_effects(
    tmp_path, kind, malformed
):
    command = p.AutomaticCommand(UUID, DATE, True, 0, 0)
    cancel = s.CancelAfterOn("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", DATE)
    pending = s.PendingAutomatic(command, True, cancel if kind == "remove" else None)
    worker, store, mono, _, _, _ = automatic_rig(tmp_path, pending, observed=ON)
    reached = []
    altered = (
        replace(command, intent_created_at="2026-09-07T11:59:59.000Z")
        if malformed == "whole_command"
        else command
    )
    consent = (
        replace(ON, approved_at="2026-09-07T12:00:00.001Z")
        if malformed == "equal_revision"
        else ON
    )
    response = {
        "protocol": 2,
        "receipt": receipt_body(altered, consent),
        "status": wire(status(consent)),
    }
    p.parse_receipt_get(response, expected_request_id=UUID)

    def reply(request, saved):
        if request.full_url.endswith("/device"):
            return {"protocol": 2, **wire(DEVICE)}, 200
        if "/receipts/" in request.full_url:
            if not reached:
                reached.append(None)
                if kind == "cancel":
                    reached[0] = worker.request_cancel_automatic_on(
                        UUID, binding=worker.status().metadata.binding
                    )
                else:
                    reached[0] = worker.request_remove_automatic_cancel(
                        pending, binding=worker.status().metadata.binding
                    )
            return response, 200
        return {"protocol": 2, "status": wire(status(ON))}, 200

    real_client(worker, store, reply)
    for _ in range(8):
        worker.iterate_once()
        mono[0] += 1
        if reached:
            break
    assert reached and reached[0]
    saved = s.load(store.path).automatic
    assert saved == s.AutomaticState(ON, pending)
    key = "cancel_automatic" if kind == "cancel" else "remove_cancel"
    assert key in worker._commands
    assert worker.status().detail == "malformed_response"
    drive(worker, mono, 4)
    saved = s.load(store.path).automatic
    assert saved.pending.command == command and saved.last_result is None
    assert (saved.pending.cancel_after_on is not None) == (kind == "cancel")
    assert key not in worker._commands


@pytest.mark.parametrize("kind", ["source", "participation"])
@pytest.mark.parametrize("boundary", ["write", "notification"])
def test_other_committed_admissions_finish_bookkeeping(
    tmp_path, monkeypatch, kind, boundary
):
    from tests.fleetsharing_worker_control_helpers import ControlRelay
    from tests.test_fleetsharing_worker_state4 import file_rig
    from wingman import atomicio

    worker, _, store, mono = file_rig(tmp_path, enabled=True)
    relay = ControlRelay(worker, store)
    drive(worker, mono, 6)
    if kind == "source":
        assert worker.request_source_stop(
            UUID, expected_generation=0, expected_automatic=None
        )
        key = "source:" + UUID
    else:
        assert worker.request_participation(
            False, expected_generation=1, binding=worker.status().metadata.binding
        )
        key = "participation"
    selected = worker._commands[key]
    reached = []

    def interrupt(candidate):
        installed = (
            selected.payload in candidate.pending_source_commands
            if kind == "source"
            else candidate.pending_participation == selected.payload
        )
        if installed and not reached:
            reached.append(True)
            worker.request_source_start(1, UUID)

    if boundary == "write":
        write = atomicio.write_atomic

        def saving(path, text, **kwargs):
            write(path, text, **kwargs)
            interrupt(s.load(store.path))

        monkeypatch.setattr(atomicio, "write_atomic", saving)
    else:
        worker.subscribe_status(lambda value: interrupt(worker._state))
    worker.iterate_once()
    assert reached == [True]
    assert key not in worker._commands
    if kind == "source":
        assert UUID in worker._source_observe
    else:
        assert worker._part_observe and worker._needs_device
    drive(worker, mono, 12)
    assert key not in worker._commands
    if kind == "participation":
        assert s.load(store.path).pending_participation is None
        assert not relay.device.participation.enabled
    else:
        assert selected.payload.request_id in relay.receipts
        requests = [
            request
            for request, _ in relay.calls
            if selected.payload.request_id in request.full_url
            or (request.method == "PUT" and request.full_url.endswith("/sources"))
        ]
        assert "/receipts/" in requests[0].full_url


def test_terminal_source_retirement_repeats_real_durable_lifecycle(tmp_path):
    from tests.fleetsharing_worker_control_helpers import ControlRelay
    from tests.test_fleetsharing_worker_state4 import file_rig

    worker, _, store, mono = file_rig(tmp_path)
    relay = ControlRelay(worker, store)
    reply = relay.reply

    def unavailable(request, saved):
        if "/receipts/" in request.full_url:
            return {"protocol": 2, "error": "service_unavailable"}, 503
        return reply(request, saved)

    relay.reply = unavailable
    worker.resume_pending()
    drive(worker, mono, 3)
    assert worker.request_source_stop(
        UUID, expected_generation=0, expected_automatic=None
    )
    drive(worker, mono, 3)
    persistent = s.load(store.path).pending_source_commands[0]
    stable = worker._source_work_key(persistent)
    # Preserve another command's long independent retry deadline across every prune.
    worker._scheduler.retry_at[stable] = mono[0] + 100000
    deadline = worker._scheduler.retry_at[stable]
    worker._scheduler.failures[stable] = 6
    worker._scheduler._served[stable] = 99
    floor = worker._scheduler.deadlines["read"]
    for n in range(3):
        source = f"{n + 1:08x}-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        assert worker.request_source_stop(
            source, expected_generation=0, expected_automatic=None
        )
        drive(worker, mono, 2)
        command = next(
            c
            for c in s.load(store.path).pending_source_commands
            if c.source_id == source
        )
        assert source in worker._source_observe
        assert any(
            request.full_url.endswith("/receipts/" + command.request_id)
            for request, _ in relay.calls
        )
        assert worker.request_dismiss_source(
            command, binding=worker.status().metadata.binding
        )
        worker.iterate_once()
        assert worker._scheduler.retry_at[stable] == deadline
        assert worker._scheduler.failures[stable] == 6
        assert worker._scheduler._served[stable] == 99
        assert worker._scheduler.deadlines["read"] >= floor
        floor = worker._scheduler.deadlines["read"]
    worker.iterate_once()
    assert worker._source_observe == {persistent.source_id}
    assert len(worker._source_generations) <= 1
    for metadata in (
        worker._scheduler.retry_at,
        worker._scheduler.failures,
        worker._scheduler._served,
    ):
        assert all(not key.startswith("source:") or key == stable for key in metadata)


@pytest.mark.parametrize(
    "retired_count",
    [
        p.MAX_SOURCE_INTENTS - 1,
        p.MAX_SOURCE_INTENTS,
        p.MAX_SOURCE_INTENTS + 1,
    ],
)
def test_terminal_only_source_retirement_bounds_observation_and_retry_metadata(
    tmp_path, retired_count
):
    from tests.fleetsharing_worker_control_helpers import ControlRelay
    from tests.test_fleetsharing_worker_state4 import file_rig

    worker, _, store, mono = file_rig(tmp_path)
    relay = ControlRelay(worker, store)
    reply = relay.reply

    def unavailable(request, saved):
        if "/receipts/" in request.full_url:
            return {"protocol": 2, "error": "service_unavailable"}, 503
        return reply(request, saved)

    relay.reply = unavailable
    worker.resume_pending()
    drive(worker, mono, 3)
    assert worker.request_source_stop(
        UUID, expected_generation=0, expected_automatic=None
    )
    drive(worker, mono, 3)
    persistent = s.load(store.path).pending_source_commands[0]

    retired = {
        f"{number + 1:08x}-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        for number in range(retired_count)
    }
    stable = worker._source_work_key(persistent)
    stale_keys = {f"source:stop:{source_id}" for source_id in retired}
    worker._source_observe = retired | {persistent.source_id}
    worker._source_generations = {source_id: 1 for source_id in retired}
    worker._source_generations[persistent.source_id] = 7

    unrelated = "automatic:stable"
    deadline = mono[0] + 100000
    for key in stale_keys | {stable, unrelated}:
        worker._scheduler.retry_at[key] = deadline
        worker._scheduler.failures[key] = 6
        worker._scheduler._served[key] = 99
    read_deadline = worker._scheduler.deadlines["read"]

    worker.iterate_once()

    assert worker._source_observe == {persistent.source_id}
    assert worker._source_generations == {persistent.source_id: 7}
    for metadata in (
        worker._scheduler.retry_at,
        worker._scheduler.failures,
        worker._scheduler._served,
    ):
        assert all(not key.startswith("source:") or key == stable for key in metadata)
    assert worker._scheduler.retry_at[stable] == deadline
    assert worker._scheduler.failures[stable] == 6
    assert worker._scheduler._served[stable] == 99
    assert worker._scheduler.retry_at[unrelated] == deadline
    assert worker._scheduler.failures[unrelated] == 6
    assert worker._scheduler._served[unrelated] == 99
    assert worker._scheduler.deadlines["read"] >= read_deadline


@pytest.mark.parametrize(
    "bad",
    [
        (None,),
        (["session", "dismissed"],),
        tuple(range(261)),
        (s.CutoverOutcome("session", "invalid"),),
    ],
)
def test_cutover_removal_rejects_unbounded_or_mutable_ack_before_queue(tmp_path, bad):
    from tests.test_fleetsharing_worker_state4 import file_rig

    worker, _, _, _ = file_rig(tmp_path)
    worker.resume_pending()
    worker.iterate_once()
    assert (
        worker.request_remove_cutover(bad, binding=worker.status().metadata.binding)
        is False
    )
    assert "remove_cutover" not in worker._commands


def test_fresh_binding_never_projects_previous_live_automatic_or_roster(tmp_path):
    from tests.fleetsharing_worker_control_helpers import ControlRelay

    worker, store, mono, _, _, _ = automatic_rig(tmp_path, observed=ON)
    relay = ControlRelay(worker, store)
    relay.consent = ON
    relay.sources[UUID] = p.SourceView(UUID, 1, 1, "active", None, None, None)
    worker.set_source_watch(True)
    drive(worker, mono, 8)
    assert worker.status().automatic_status == status(ON)
    action = worker.request_automatic(
        True,
        expected_generation=1,
        expected_revision=1,
        binding=worker.status().metadata.binding,
    )
    assert action
    drive(worker, mono, 10)
    old = worker.status()
    assert old.sources and old.sources.sources
    assert old.automatic_request_id == action and old.automatic_stage == "settled"
    assert old.automatic.last_result.receipt is not None
    binding = worker.status().metadata.binding
    worker._generate_private_key = lambda: bytes([1]) * 32
    values = []
    worker.subscribe_status(values.append)
    assert worker.request_pairing(
        mode="fresh",
        configured_origin="https://other.test",
        binding=binding,
        automatic_history=s.load(store.path).automatic,
    )
    worker.iterate_once()
    fresh = [value for value in values if value.metadata.binding != binding]
    assert fresh and worker.status().metadata.binding != binding
    assert all(value.automatic == s.AutomaticState() for value in fresh)
    assert all(value.sources is None and value.eligibility is None for value in fresh)
    assert all(value.automatic_status is None for value in fresh)
    assert all(
        value.automatic_request_id is None and value.automatic_stage is None
        for value in fresh
    )


def test_old_cancel_removal_cannot_retire_new_explicit_pending_after_derived_off(
    tmp_path, monkeypatch
):
    from tests.fleetsharing_worker_control_helpers import ControlRelay

    command = p.AutomaticCommand(UUID, DATE, True, 0, 0)
    original = s.PendingAutomatic(
        command, True, s.CancelAfterOn("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", DATE)
    )
    current = p.Consent(2, 2, True, UUID, DATE, None, None)
    worker, store, mono, _, _, _ = automatic_rig(tmp_path, original, observed=current)
    relay = ControlRelay(worker, store)
    relay.consent = current
    relay.receipts[UUID] = receipt_body(command, ON)
    drive(worker, mono, 6)
    derived = s.load(store.path).automatic.pending
    assert derived and not derived.command.enabled and not derived.attempted
    new_id = worker.request_automatic(
        True,
        expected_generation=2,
        expected_revision=2,
        supersedes=derived,
        binding=worker.status().metadata.binding,
    )
    assert new_id
    reached = []
    write = s.atomicio.write_atomic

    def saving(path, text):
        write(path, text)
        pending = s.load(store.path).automatic.pending
        if pending and pending.command.request_id == new_id and not reached:
            reached.append(
                worker.request_remove_automatic_cancel(
                    original, binding=worker.status().metadata.binding
                )
            )

    monkeypatch.setattr(s.atomicio, "write_atomic", saving)
    drive(worker, mono, 12)
    assert reached == [True]
    saved = s.load(store.path).automatic
    assert (
        saved.pending is None and saved.last_result.receipt.command.request_id == new_id
    )
    mutations = [
        p.parse_automatic_command(json.loads(request.data))
        for request, _ in relay.calls
        if request.method == "PUT"
        and request.full_url.endswith("/automatic-verification")
    ]
    assert (
        len(mutations) == 1
        and mutations[0].enabled
        and mutations[0].request_id == new_id
    )
