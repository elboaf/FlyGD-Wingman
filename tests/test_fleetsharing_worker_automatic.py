"""Automatic lifecycle proofs at the real writer and signed HTTP boundaries."""

import json
import threading
from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from tests.test_fleetsharing_client import Response, framing_headers, request_binding
from tests.test_fleetsharing_worker import DATE, DEVICE, NOW, UUID, drive
from tests.test_fleetsharing_worker_controls import real_client, wire
from tests.test_fleetsharing_worker_state4 import file_rig
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing import state as s

OFF = p.Consent(0, 0, False, None, None, None, None)
ON = p.Consent(1, 1, True, UUID, DATE, None, None)


def status(consent):
    return p.AutomaticStatus(
        consent,
        "none" if consent.generation == 0 else "this_device",
        "waiting_for_grant" if consent.enabled else "off",
        "none",
        None,
        (),
    )


def receipt_body(command, consent):
    accepted = max(
        command.intent_created_at, consent.approved_at or "", consent.disabled_at or ""
    )
    expires = (
        (datetime.fromisoformat(accepted) + timedelta(hours=24))
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
    body = {
        "kind": "automatic",
        "command": p.automatic_command_body(command),
        "accepted_at": accepted,
        "expires_at": expires,
        "result": wire(consent),
    }
    p.parse_automatic_receipt(body)
    return body


def automatic_rig(tmp_path, pending=None, *, observed=OFF, device=DEVICE):
    worker, _, store, mono = file_rig(tmp_path)
    saved = replace(
        s.load(store.path),
        device_id=UUID,
        automatic=s.AutomaticState(observed, pending),
    )
    s.save(store.path, saved)
    current = [observed]
    attempts = []
    receipts = {}

    def current_status():
        view = status(current[0])
        if current[0].enabled and not device.feature_enabled:
            view = replace(view, readiness="global_disabled", recovery_action="wait")
        return view

    def reply(request, saved):
        if request.full_url.endswith("/device"):
            observation = replace(
                device,
                server_time_ms=DEVICE.server_time_ms + int((mono[0] - 1000) * 1000),
            )
            return {"protocol": 2, **wire(observation)}, 200
        if "/receipts/" in request.full_url:
            receipt = receipts.get(request.full_url.rsplit("/", 1)[1])
            if receipt is not None:
                return {
                    "protocol": 2,
                    "receipt": receipt,
                    "status": wire(current_status()),
                }, 200
            return {"protocol": 2, "error": "receipt_not_found"}, 404
        if request.method == "GET":
            return {"protocol": 2, "status": wire(current_status())}, 200
        command = p.parse_automatic_command(json.loads(request.data))
        attempts.append(saved)
        assert saved.automatic.pending.command == command
        assert saved.automatic.pending.attempted is True
        if not command.enabled and not current[0].enabled:
            return {
                "protocol": 2,
                "request_id": command.request_id,
                "result": "already_off",
                "receipt": None,
                "status": wire(current_status()),
            }, 200
        result = (
            p.Consent(
                command.expected_generation + 1,
                command.expected_revision + 1,
                True,
                UUID,
                command.intent_created_at,
                None,
                None,
            )
            if command.enabled
            else replace(
                current[0],
                enabled=False,
                revision=command.expected_revision + 1,
                disabled_at=max(command.intent_created_at, current[0].approved_at),
                closed_reason="explicit_off",
            )
        )
        current[0] = result
        receipts[command.request_id] = receipt_body(command, result)
        return {
            "protocol": 2,
            "request_id": command.request_id,
            "result": "applied",
            "receipt": receipt_body(command, result),
            "status": wire(status(result)),
        }, 200

    calls = real_client(worker, store, reply)
    worker.resume_pending()
    return worker, store, mono, current, attempts, calls


def test_saved_on_attempt_and_signed_revision_are_atomic_before_real_http(tmp_path):
    command = p.AutomaticCommand(UUID, DATE, True, 0, 0)
    worker, store, mono, _current, attempts, _calls = automatic_rig(
        tmp_path, s.PendingAutomatic(command)
    )
    drive(worker, mono, 12)
    assert len(attempts) == 1
    final = s.load(store.path).automatic
    assert final.pending is None
    assert final.last_result.outcome == "receipt"
    assert final.last_result.pending.attempted is True
    assert final.last_result.pending.command == command
    assert final.observed_consent == ON


@pytest.mark.parametrize(
    "missing",
    [
        "feature_enabled",
        "session_approved_capabilities",
        "acknowledged_capabilities",
        "participation",
        "approved_capabilities",
    ],
)
def test_real_automatic_off_permission_boundary_without_telemetry(tmp_path, missing):
    value = (
        False
        if missing == "feature_enabled"
        else p.Participation(False, 1)
        if missing == "participation"
        else ()
    )
    device = replace(DEVICE, **{missing: value})
    command = p.AutomaticCommand(UUID, DATE, False, 1, 1)
    worker, store, mono, _, attempts, calls = automatic_rig(
        tmp_path, s.PendingAutomatic(command, True), observed=ON, device=device
    )
    drive(worker, mono, 10)
    saved = s.load(store.path).automatic
    if missing == "approved_capabilities":
        assert saved.pending == s.PendingAutomatic(command, True) and not attempts
        assert all(r.full_url.endswith("/device") for r, _ in calls)
    else:
        assert saved.pending is None and saved.last_result.outcome == "receipt"
        assert [v.automatic.pending.command for v in attempts] == [command]
        assert any("/receipts/" in r.full_url for r, _ in calls)
        assert all(not r.full_url.endswith("/snapshot") for r, _ in calls)


@pytest.mark.parametrize("contradiction", [False, True])
def test_historical_on_receipt_never_rolls_back_newer_current_consent(
    tmp_path, contradiction
):
    command = p.AutomaticCommand(UUID, DATE, True, 0, 0)
    pending = s.PendingAutomatic(
        command, True, s.CancelAfterOn("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", DATE)
    )
    newer = p.Consent(2, 2, True, UUID, DATE, None, None)
    worker, store, mono, _, attempts, _ = automatic_rig(
        tmp_path, pending, observed=newer
    )
    offered = (
        replace(newer, approved_at="2026-09-07T12:00:00.001Z")
        if contradiction
        else newer
    )
    response = {
        "protocol": 2,
        "receipt": receipt_body(command, ON),
        "status": wire(status(offered)),
    }
    p.parse_receipt_get(response, expected_request_id=UUID)

    def reply(request, saved):
        if request.full_url.endswith("/device"):
            return {"protocol": 2, **wire(DEVICE)}, 200
        if "/receipts/" in request.full_url:
            return response, 200
        assert request.method == "GET"
        return {"protocol": 2, "status": wire(status(newer))}, 200

    real_client(worker, store, reply)
    drive(worker, mono, 6)
    saved = s.load(store.path).automatic
    assert saved.observed_consent == newer and not attempts
    if contradiction:
        assert saved.pending == pending and saved.last_result is None
    else:
        assert (
            saved.last_result.pending == pending
            and saved.last_result.outcome == "receipt"
        )
        assert not saved.pending.command.enabled
        assert saved.pending.command.expected_generation == 1
        assert saved.pending.command.expected_revision == 1
        assert saved.pending.command.request_id == pending.cancel_after_on.request_id
        assert not saved.pending.attempted


def test_definitive_first_on_refusal_records_rejected_not_unknown_success(tmp_path):
    command = p.AutomaticCommand(UUID, DATE, True, 0, 0)
    worker, store, mono, _, _, _ = automatic_rig(tmp_path, s.PendingAutomatic(command))
    factory = worker._client_factory

    def client_factory(origin):
        client = factory(origin)
        transport = client._transport

        def refused(request, timeout):
            if request.method == "PUT":
                return Response(
                    b'{"protocol":2,"error":"capability_required"}',
                    framing_headers(request_binding(request)),
                    403,
                )
            return transport(request, timeout)

        client._transport = refused
        return client

    worker._client_factory = client_factory
    drive(worker, mono, 8)
    saved = s.load(store.path).automatic
    assert saved.pending is None
    assert saved.last_result.outcome == "rejected"
    assert saved.last_result.pending.command == command
    assert saved.last_result.pending.attempted is True
    assert saved.last_result.receipt is None and saved.observed_consent == OFF


def test_on_crossing_original_expiry_during_real_signing_cannot_start_http(
    tmp_path, monkeypatch
):
    from wingman.fleetsharing import crypto

    command = p.AutomaticCommand(UUID, DATE, True, 0, 0)
    worker, store, mono, _, attempts, calls = automatic_rig(
        tmp_path, s.PendingAutomatic(command)
    )
    drive(worker, mono, 2)
    sign = crypto.sign_request

    def signing(key, canonical):
        result = sign(key, canonical)
        if b"PUT\n/api/fleet/v2/automatic-verification" in canonical:
            worker._utc_clock = lambda: NOW + timedelta(seconds=60)
        return result

    monkeypatch.setattr(crypto, "sign_request", signing)
    worker.iterate_once()
    assert not attempts and all(r.method != "PUT" for r, _ in calls)
    assert s.load(store.path).automatic.pending == s.PendingAutomatic(command, True)


def test_terminal_off_has_no_invalid_session_bypass_after_signing_delay(
    tmp_path, monkeypatch
):
    from wingman.fleetsharing import crypto

    command = p.AutomaticCommand(UUID, DATE, False, 1, 1)
    worker, store, mono, _, attempts, _ = automatic_rig(
        tmp_path, s.PendingAutomatic(command), observed=ON
    )
    drive(worker, mono, 2)
    sign = crypto.sign_request

    def signing(key, canonical):
        result = sign(key, canonical)
        if b"PUT\n/api/fleet/v2/automatic-verification" in canonical:
            mono[0] += 1800
        return result

    monkeypatch.setattr(crypto, "sign_request", signing)
    worker.iterate_once()
    assert not attempts
    assert s.load(store.path).automatic.pending == s.PendingAutomatic(command, True)


def test_automatic_observation_polls_independently_of_telemetry_participation(tmp_path):
    worker, store, mono, current, attempts, calls = automatic_rig(tmp_path, observed=ON)
    drive(worker, mono, 4)
    off = p.Consent(1, 2, False, UUID, DATE, DATE, "explicit_off")
    current[0] = off
    drive(worker, mono, 8)
    assert s.load(store.path).automatic.observed_consent == off
    assert not attempts
    assert all(not r.full_url.endswith("/snapshot") for r, _ in calls)


def test_cancel_unattempted_on_records_unsent_without_http(tmp_path):
    command = p.AutomaticCommand(UUID, DATE, True, 0, 0)
    worker, store, mono, _, attempts, _ = automatic_rig(
        tmp_path, s.PendingAutomatic(command)
    )
    worker.iterate_once()  # Device observation only; saved On has not been attempted.
    binding = worker.status().metadata.binding
    cancel_id = worker.request_cancel_automatic_on(UUID, binding=binding)
    assert cancel_id is not None
    drive(worker, mono, 6)
    final = s.load(store.path).automatic
    assert final.pending is None
    assert final.last_result.outcome == "cancelled_unsent"
    assert final.last_result.pending == s.PendingAutomatic(command)
    assert not attempts


def test_cancel_queued_in_real_on_transport_derives_off_from_exact_receipt(tmp_path):
    command = p.AutomaticCommand(UUID, DATE, True, 0, 0)
    worker, store, mono, _, attempts, _calls = automatic_rig(
        tmp_path, s.PendingAutomatic(command)
    )
    factory = worker._client_factory
    cancel_ids = []

    def factory_with_cancel(origin):
        client = factory(origin)
        transport = client._transport

        def held(request, timeout):
            if request.method == "PUT" and json.loads(request.data)["enabled"]:
                binding = worker.status().metadata.binding
                cancel_ids.append(
                    worker.request_cancel_automatic_on(UUID, binding=binding)
                )
                cancel_ids.append(
                    worker.request_cancel_automatic_on(UUID, binding=binding)
                )
            return transport(request, timeout)

        client._transport = held
        return client

    worker._client_factory = factory_with_cancel
    drive(worker, mono, 15)
    assert cancel_ids[0] is not None and cancel_ids[0] == cancel_ids[1]
    assert [v.automatic.pending.command.enabled for v in attempts] == [True, False]
    final = s.load(store.path).automatic
    assert final.pending is None and final.last_result.outcome == "receipt"
    off = final.last_result.pending.command
    assert off.request_id == cancel_ids[0]
    assert (off.expected_generation, off.expected_revision) == (1, 1)
    assert any(
        v.automatic.pending
        and not v.automatic.pending.command.enabled
        and not v.automatic.pending.attempted
        and v.automatic.last_result.pending.cancel_after_on is not None
        for v in store.saves
    )


def test_attempted_on_supersession_requires_bound_db_expiry_not_receipt_absence(
    tmp_path,
):
    command = p.AutomaticCommand(UUID, DATE, True, 0, 0)
    old = s.PendingAutomatic(
        command, True, s.CancelAfterOn("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", DATE)
    )
    worker, store, mono, _, attempts, _calls = automatic_rig(tmp_path, old)
    drive(worker, mono, 5)
    new_id = worker.request_automatic(
        False,
        expected_generation=0,
        expected_revision=0,
        binding=worker.status().metadata.binding,
        supersedes=old,
    )
    assert new_id is not None
    worker.iterate_once()
    assert s.load(store.path).automatic.pending == old
    assert not attempts
    mono[0] = 1060.0
    drive(worker, mono, 5)
    assert any(
        v.automatic.pending
        and v.automatic.pending.command.request_id == new_id
        and v.automatic.last_result == s.AutomaticCompletion(old, "superseded_unknown")
        for v in store.saves
    )


def test_current_off_converges_pending_off_without_claiming_own_commit(tmp_path):
    command = p.AutomaticCommand(UUID, DATE, False, 1, 1)
    off = p.Consent(1, 2, False, UUID, DATE, DATE, "explicit_off")
    worker, store, mono, _, attempts, _ = automatic_rig(
        tmp_path, s.PendingAutomatic(command, True), observed=off
    )
    drive(worker, mono, 8)
    final = s.load(store.path).automatic
    assert final.pending is None
    assert (
        final.last_result.outcome == "observed_off"
        and final.last_result.receipt is None
    )
    assert final.observed_consent == off and not attempts


def test_automatic_mutation_invalidates_cached_source_evidence(tmp_path):
    command = p.AutomaticCommand(UUID, DATE, True, 0, 0)
    worker, store, mono, _, _, _ = automatic_rig(tmp_path, s.PendingAutomatic(command))
    worker.iterate_once()
    worker._eligibility = p.Eligibility(1, "ready", ())
    worker._sources = p.Sources((), ())
    drive(worker, mono, 6)
    assert s.load(store.path).automatic.last_result.outcome == "receipt"
    assert worker._eligibility is None and worker._sources is None


def test_cancel_during_real_receipt_write_cannot_disappear_with_completed_on(
    tmp_path, monkeypatch
):
    command = p.AutomaticCommand(UUID, DATE, True, 0, 0)
    worker, store, mono, _, attempts, _ = automatic_rig(
        tmp_path, s.PendingAutomatic(command)
    )
    write = s.atomicio.write_atomic
    cancellations = []

    def enqueue_after_write(path, data):
        write(path, data)
        automatic = json.loads(data)["automatic"]
        last = automatic["last_result"]
        if (
            not cancellations
            and last
            and last["outcome"] == "receipt"
            and automatic["pending"] is None
        ):
            cancellations.append(
                worker.request_cancel_automatic_on(
                    UUID, binding=worker.status().metadata.binding
                )
            )

    monkeypatch.setattr(s.atomicio, "write_atomic", enqueue_after_write)
    drive(worker, mono, 12)
    assert cancellations and cancellations[0] is not None
    assert [v.automatic.pending.command.enabled for v in attempts] == [True, False]
    assert (
        s.load(store.path).automatic.last_result.pending.command.request_id
        == cancellations[0]
    )


def test_removing_cancel_retains_the_exact_original_attempted_on(tmp_path):
    command = p.AutomaticCommand(UUID, DATE, True, 0, 0)
    pending = s.PendingAutomatic(
        command, True, s.CancelAfterOn("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", DATE)
    )
    worker, store, _mono, _, _, _ = automatic_rig(tmp_path, pending)
    worker.iterate_once()
    assert worker.request_remove_automatic_cancel(
        pending, binding=worker.status().metadata.binding
    )
    worker.iterate_once()
    assert s.load(store.path).automatic.pending == s.PendingAutomatic(command, True)


def test_cancel_removal_queued_during_receipt_http_prevents_derived_off(tmp_path):
    command = p.AutomaticCommand(UUID, DATE, True, 0, 0)
    pending = s.PendingAutomatic(
        command, True, s.CancelAfterOn("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", DATE)
    )
    worker, store, mono, _, attempts, _ = automatic_rig(tmp_path, pending, observed=ON)
    factory = worker._client_factory
    removals = []

    def client_factory(origin):
        client = factory(origin)
        transport = client._transport

        def remove_during_receipt(request, timeout):
            if request.full_url.endswith("/receipts/" + UUID):
                removals.append(
                    worker.request_remove_automatic_cancel(
                        pending, binding=worker.status().metadata.binding
                    )
                )
                body = {
                    "protocol": 2,
                    "receipt": receipt_body(command, ON),
                    "status": wire(status(ON)),
                }
                return Response(
                    json.dumps(body).encode(), framing_headers(request_binding(request))
                )
            return transport(request, timeout)

        client._transport = remove_during_receipt
        return client

    worker._client_factory = client_factory
    drive(worker, mono, 8)
    assert removals == [True] and not attempts
    saved = s.load(store.path).automatic
    assert saved.pending is None and saved.last_result.outcome == "receipt"
    assert saved.last_result.pending.command == command
    assert saved.last_result.pending.cancel_after_on is None
    assert saved.observed_consent == ON


@pytest.mark.parametrize("expired", [False, True])
def test_expired_on_dismissal_during_receipt_http_retires_unsent_cancellation(
    tmp_path, expired
):
    command = p.AutomaticCommand(
        UUID, "2026-09-07T11:59:00.000Z" if expired else DATE, True, 0, 0
    )
    observed = replace(ON, approved_at="2026-09-07T11:59:01.000Z") if expired else ON
    pending = s.PendingAutomatic(
        command, True, s.CancelAfterOn("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", DATE)
    )
    worker, store, mono, _, attempts, _ = automatic_rig(
        tmp_path, pending, observed=observed
    )
    factory = worker._client_factory
    dismissals = []

    def client_factory(origin):
        client = factory(origin)
        transport = client._transport

        def dismiss_during_receipt(request, timeout):
            if request.full_url.endswith("/receipts/" + UUID):
                dismissals.append(
                    worker.request_dismiss_automatic(
                        pending, binding=worker.status().metadata.binding
                    )
                )
                receipt = receipt_body(command, observed)
                receipt.update(
                    accepted_at=observed.approved_at,
                    expires_at="2026-09-08T11:59:01.000Z"
                    if expired
                    else "2026-09-08T12:00:00.000Z",
                )
                body = {
                    "protocol": 2,
                    "receipt": receipt,
                    "status": wire(status(observed)),
                }
                return Response(
                    json.dumps(body).encode(), framing_headers(request_binding(request))
                )
            return transport(request, timeout)

        client._transport = dismiss_during_receipt
        return client

    worker._client_factory = client_factory
    drive(worker, mono, 8)
    assert dismissals == [True]
    saved = s.load(store.path).automatic
    assert saved.pending is None
    if expired:
        assert not attempts and saved.observed_consent == observed
        assert saved.last_result.receipt.command == command
        assert saved.last_result.pending.cancel_after_on is None
    else:
        assert len(attempts) == 1 and not saved.observed_consent.enabled


def test_stale_whole_pending_ack_cannot_erase_a_newer_cancel(tmp_path):
    command = p.AutomaticCommand(UUID, DATE, True, 0, 0)
    pending = s.PendingAutomatic(
        command, True, s.CancelAfterOn("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", DATE)
    )
    worker, store, _mono, _, _, _ = automatic_rig(tmp_path, pending)
    worker.iterate_once()
    stale = replace(
        pending,
        cancel_after_on=replace(
            pending.cancel_after_on, intent_created_at="2026-09-07T12:00:00.001Z"
        ),
    )
    worker.request_remove_automatic_cancel(
        stale, binding=worker.status().metadata.binding
    )
    worker.iterate_once()
    assert s.load(store.path).automatic.pending == pending


def test_dismiss_attempted_on_cannot_release_admission_before_db_expiry(tmp_path):
    command = p.AutomaticCommand(UUID, DATE, True, 0, 0)
    pending = s.PendingAutomatic(
        command, True, s.CancelAfterOn("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", DATE)
    )
    worker, store, mono, _, attempts, _ = automatic_rig(tmp_path, pending)
    drive(worker, mono, 5)
    binding = worker.status().metadata.binding
    assert worker.request_dismiss_automatic(pending, binding=binding)
    worker.iterate_once()
    assert s.load(store.path).automatic.pending == pending
    # Queue acceptance of a fresh already-Off action is not permission to erase On.
    worker.request_automatic(
        False, expected_generation=0, expected_revision=0, binding=binding
    )
    worker.iterate_once()
    assert s.load(store.path).automatic.pending == pending
    assert not attempts and s.load(store.path).automatic.last_result is None
    mono[0] = 1060.0
    assert worker.request_dismiss_automatic(pending, binding=binding)
    drive(worker, mono, 4)
    saved = s.load(store.path).automatic
    assert saved.pending is None
    assert saved.last_result == s.AutomaticCompletion(pending, "superseded_unknown")


def test_late_cancel_cannot_overwrite_newer_pending_automatic_command(tmp_path):
    command = p.AutomaticCommand(UUID, DATE, True, 0, 0)
    worker, store, mono, _, attempts, _ = automatic_rig(
        tmp_path, s.PendingAutomatic(command)
    )
    entered, release_http = threading.Event(), threading.Event()
    queued, release_queue = threading.Event(), threading.Event()
    factory, enqueue = worker._client_factory, worker._queue

    def client_factory(origin):
        client = factory(origin)
        transport = client._transport

        def hold(request, timeout):
            if request.method == "PUT":
                entered.set()
                assert release_http.wait(5)
            return transport(request, timeout)

        client._transport = hold
        return client

    def delay_queue(key, kind, payload, **kwargs):
        if kind == "cancel_automatic":
            queued.set()
            assert release_queue.wait(5)
        return enqueue(key, kind, payload, **kwargs)

    worker._client_factory, worker._queue = client_factory, delay_queue
    drive(worker, mono, 2)
    owner = threading.Thread(target=worker.iterate_once)
    cancellation = []
    cancel_thread = threading.Thread(
        target=lambda: cancellation.append(
            worker.request_cancel_automatic_on(
                UUID, binding=worker.status().metadata.binding
            )
        )
    )
    owner.start()
    try:
        assert entered.wait(3)
        cancel_thread.start()
        assert queued.wait(3)
        release_http.set()
        owner.join(3)
        assert not owner.is_alive()
        binding = worker.status().metadata.binding
        new_id = worker.request_automatic(
            False, expected_generation=1, expected_revision=1, binding=binding
        )
        assert new_id is not None
        worker.iterate_once()  # Persist before the next completion-based read slot.
        newer = s.load(store.path).automatic.pending
        assert newer.command.request_id == new_id and not newer.attempted
        release_queue.set()
        cancel_thread.join(3)
        assert not cancel_thread.is_alive() and cancellation[0] is not None
        worker.iterate_once()
        assert s.load(store.path).automatic.pending == newer
        assert (
            len(attempts) == 1
        )  # Neither cancellation nor newer Off sent in old slot.
    finally:
        release_http.set()
        release_queue.set()
        owner.join(5)
        if cancel_thread.ident is not None:
            cancel_thread.join(5)


def test_repeat_cancel_while_removal_is_queued_keeps_the_retained_intent(tmp_path):
    command = p.AutomaticCommand(UUID, DATE, True, 0, 0)
    pending = s.PendingAutomatic(
        command, True, s.CancelAfterOn("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", DATE)
    )
    worker, store, _, _, _, _ = automatic_rig(tmp_path, pending)
    worker.iterate_once()
    binding = worker.status().metadata.binding
    assert worker.request_remove_automatic_cancel(pending, binding=binding)
    assert (
        worker.request_cancel_automatic_on(UUID, binding=binding)
        == pending.cancel_after_on.request_id
    )
    worker.iterate_once()
    assert s.load(store.path).automatic.pending == pending


def test_concurrent_cancel_clicks_coalesce_one_original_intent(tmp_path):
    command = p.AutomaticCommand(UUID, DATE, True, 0, 0)
    worker, store, _, _, _, _ = automatic_rig(tmp_path, s.PendingAutomatic(command))
    worker.iterate_once()
    enqueue = worker._queue
    barrier = threading.Barrier(2)
    results = []

    def concurrently(key, kind, payload, **kwargs):
        if kind == "cancel_automatic":
            barrier.wait(3)
        return enqueue(key, kind, payload, **kwargs)

    worker._queue = concurrently
    threads = [
        threading.Thread(
            target=lambda: results.append(
                worker.request_cancel_automatic_on(
                    UUID, binding=worker.status().metadata.binding
                )
            )
        )
        for _ in range(2)
    ]
    before = store.path.read_bytes()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)
    assert all(not thread.is_alive() for thread in threads)
    assert len(results) == 2 and results[0] is not None and results[0] == results[1]
    assert worker._commands["cancel_automatic"].payload[1].request_id == results[0]
    assert store.path.read_bytes() == before


def test_whole_pending_ack_cannot_claim_unsent_when_attempt_write_wins(
    tmp_path, monkeypatch
):
    command = p.AutomaticCommand(UUID, DATE, True, 0, 0)
    before_attempt = s.PendingAutomatic(command)
    worker, store, mono, _, attempts, calls = automatic_rig(tmp_path, before_attempt)
    write = s.atomicio.write_atomic
    replacement = []

    def replace_during_attempt(path, text):
        write(path, text)
        pending = json.loads(text)["automatic"]["pending"]
        if pending and pending["attempted"] and not replacement:
            replacement.append(
                worker.request_automatic(
                    False,
                    expected_generation=0,
                    expected_revision=0,
                    binding=worker.status().metadata.binding,
                    supersedes=before_attempt,
                )
            )

    monkeypatch.setattr(s.atomicio, "write_atomic", replace_during_attempt)
    drive(worker, mono, 8)
    assert replacement[0] is not None
    assert s.load(store.path).automatic.pending == s.PendingAutomatic(command, True)
    assert s.load(store.path).automatic.last_result is None
    assert not attempts
    assert any("/receipts/" in r.full_url for r, _ in calls)


def test_terminal_counter_reserve_rejects_new_on_without_dropping_saved_command(
    tmp_path,
):
    maximum = p.JS_SAFE_MAX
    observed = p.Consent(maximum, maximum, True, UUID, DATE, None, None)
    command = p.AutomaticCommand(
        UUID, "2026-09-07T11:58:00.000Z", True, maximum, maximum
    )
    pending = s.PendingAutomatic(command, True)
    worker, store, mono, _, attempts, _ = automatic_rig(
        tmp_path, pending, observed=observed
    )
    drive(worker, mono, 6)
    assert worker.status().automatic_status.consent == observed
    assert (
        worker.request_automatic(
            True,
            expected_generation=maximum,
            expected_revision=maximum,
            binding=worker.status().metadata.binding,
            supersedes=pending,
        )
        is None
    )
    assert s.load(store.path).automatic.pending == pending and not attempts


@pytest.mark.parametrize("attempted", [False, True])
def test_off_offline_age_never_refreshes_body_or_cas(tmp_path, attempted):
    command = p.AutomaticCommand(UUID, "2026-09-05T12:00:00.000Z", False, 1, 1)
    worker, store, mono, _, attempts, _ = automatic_rig(
        tmp_path, s.PendingAutomatic(command, attempted), observed=ON
    )
    drive(worker, mono, 10)
    assert len(attempts) == 1 and attempts[0].automatic.pending.command == command
    assert s.load(store.path).automatic.last_result.pending.command == command
    assert s.load(store.path).automatic.last_result.outcome == "receipt"


@pytest.mark.parametrize(
    "current_consent", [OFF, ON, p.Consent(2, 2, True, UUID, DATE, None, None)]
)
def test_purged_on_receipt_never_derives_off_from_current_generation(
    tmp_path, current_consent
):
    command = p.AutomaticCommand(UUID, DATE, True, 0, 0)
    pending = s.PendingAutomatic(
        command, True, s.CancelAfterOn("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", DATE)
    )
    worker, store, mono, _, attempts, _ = automatic_rig(
        tmp_path, pending, observed=current_consent
    )
    drive(worker, mono, 12)
    assert not attempts
    assert s.load(store.path).automatic.pending == pending
    assert s.load(store.path).automatic.last_result is None
    assert s.load(store.path).automatic.observed_consent == current_consent


@pytest.mark.parametrize("committed", [False, True])
def test_lost_on_response_with_cancel_recovers_only_an_exact_receipt(
    tmp_path, committed
):
    command = p.AutomaticCommand(UUID, DATE, True, 0, 0)
    worker, store, mono, _, attempts, calls = automatic_rig(
        tmp_path, s.PendingAutomatic(command)
    )
    factory = worker._client_factory
    cancels = []

    def client_factory(origin):
        client = factory(origin)
        transport = client._transport

        def lost(request, timeout):
            if request.method == "PUT" and json.loads(request.data)["enabled"]:
                cancels.append(
                    worker.request_cancel_automatic_on(
                        UUID, binding=worker.status().metadata.binding
                    )
                )
                if committed:
                    with transport(request, timeout):
                        pass
                raise OSError("lost original On response")
            return transport(request, timeout)

        client._transport = lost
        return client

    worker._client_factory = client_factory
    drive(worker, mono, 14)
    assert len(cancels) == 1 and cancels[0] is not None
    saved = s.load(store.path).automatic
    assert any("/receipts/" in r.full_url for r, _ in calls)
    if committed:
        assert saved.pending is None and saved.last_result.outcome == "receipt"
        assert saved.last_result.pending.command.request_id == cancels[0]
        assert [v.automatic.pending.command.enabled for v in attempts] == [True, False]
    else:
        assert saved.pending.command == command and saved.pending.attempted
        assert saved.pending.cancel_after_on.request_id == cancels[0]
        assert saved.last_result is None and not attempts


@pytest.mark.parametrize("fenced", [False, True])
def test_slow_device_db_fact_is_authentication_not_an_anchor_or_reopening(
    tmp_path, fenced
):
    command = p.AutomaticCommand(UUID, DATE, True, 0, 0)
    pending = s.PendingAutomatic(
        command, True, s.CancelAfterOn("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", DATE)
    )
    worker, store, mono, _, attempts, _ = automatic_rig(tmp_path, pending)
    factory = worker._client_factory

    class SlowBody(Response):
        def read(self, amount=-1):
            mono[0] += 6.0
            return super().read(amount)

    def client_factory(origin):
        client = factory(origin)
        transport = client._transport

        def slow(request, timeout):
            if request.full_url.endswith("/device"):
                assert s.load(store.path).last_revision == int(
                    request.get_header("X-fleet-revision")
                )
                body = {
                    "protocol": 2,
                    **wire(
                        replace(DEVICE, server_time_ms=DEVICE.server_time_ms + 60000)
                    ),
                }
                return SlowBody(
                    json.dumps(body).encode(), framing_headers(request_binding(request))
                )
            return transport(request, timeout)

        client._transport = slow
        return client

    worker._client_factory = client_factory
    drive(worker, mono, 5)
    assert worker._timing_context._state.anchor is None
    assert worker._control_auth is not None
    worker._control_time_fenced = (
        fenced  # C's closed-admission handoff, never an unfence.
    )
    new_id = worker.request_automatic(
        False,
        expected_generation=0,
        expected_revision=0,
        binding=worker.status().metadata.binding,
        supersedes=pending,
    )
    assert new_id is not None
    worker.iterate_once()
    if fenced:
        assert s.load(store.path).automatic.pending == pending and not attempts
    else:
        assert any(
            v.automatic.pending
            and v.automatic.pending.command.request_id == new_id
            and v.automatic.last_result
            == s.AutomaticCompletion(pending, "superseded_unknown")
            for v in store.saves
        )


@pytest.mark.parametrize(
    "boundary", ["admission", "attempt", "completion", "cancel", "derived"]
)
def test_real_atomic_failure_retains_original_automatic_action(
    tmp_path, monkeypatch, boundary
):
    worker, store, mono, _, attempts, _ = automatic_rig(tmp_path)
    worker.iterate_once()
    binding = worker.status().metadata.binding
    worker.request_automatic_status(binding=binding)
    drive(worker, mono, 3)
    write = s.atomicio.write_atomic
    refused = []
    cancelled = []
    if boundary in ("cancel", "derived"):
        transport = worker._client._transport

        def queue_cancel(request, timeout):
            if (
                request.method == "PUT"
                and json.loads(request.data)["enabled"]
                and not cancelled
            ):
                cancelled.append(
                    worker.request_cancel_automatic_on(
                        json.loads(request.data)["request_id"], binding=binding
                    )
                )
            return transport(request, timeout)

        worker._client._transport = queue_cancel

    def fail_at_boundary(path, text):
        automatic = json.loads(text)["automatic"]
        pending, last = automatic["pending"], automatic["last_result"]
        blocked = {
            "admission": pending is not None and not pending["attempted"],
            "attempt": pending is not None and pending["attempted"],
            "completion": pending is None
            and last is not None
            and last["outcome"] == "receipt",
            "cancel": pending is not None and pending["cancel_after_on"] is not None,
            "derived": pending is not None
            and not pending["command"]["enabled"]
            and last is not None,
        }[boundary]
        if blocked:
            refused.append(automatic)
            raise OSError("controlled atomic failure")
        write(path, text)

    monkeypatch.setattr(s.atomicio, "write_atomic", fail_at_boundary)
    request_id = worker.request_automatic(
        True, expected_generation=0, expected_revision=0, binding=binding
    )
    original = worker._commands["automatic"].payload
    drive(worker, mono, 10)
    assert refused and request_id == original.request_id
    saved = s.load(store.path).automatic
    if boundary == "admission":
        assert (
            saved.pending is None and worker._commands["automatic"].payload == original
        )
    else:
        assert saved.pending.command == original
        assert saved.pending.attempted is (boundary != "attempt")
    assert len(attempts) == (0 if boundary in ("admission", "attempt") else 1)
    assert saved.last_result is None
    monkeypatch.setattr(s.atomicio, "write_atomic", write)
    drive(worker, mono, 14)
    final = s.load(store.path).automatic
    assert final.pending is None and final.last_result.outcome == "receipt"
    if boundary in ("cancel", "derived"):
        assert final.last_result.pending.command.request_id == cancelled[0]
        assert final.last_result.pending.command.expected_generation == 1
    else:
        assert final.last_result.pending.command == original
    assert [v.automatic.pending.command.enabled for v in attempts] == (
        [True, False] if cancelled else [True]
    )


@pytest.mark.parametrize(
    "name,old,new,regression",
    [
        (
            "dismiss_expiry_gap",
            "    def _on_expired_proven_locked(self, command):\n        fact = self._control_db_fact",
            "    def _on_expired_proven_locked(self, command):\n        return True\n        fact = self._control_db_fact",
            "test_dismiss_attempted_on_cannot_release_admission_before_db_expiry",
        ),
        (
            "late_cancel_overwrites_newer",
            "        if pending is None:\n            completed = self._state.automatic.last_result",
            "        if pending is None or pending.command.request_id != request_id:\n            completed = self._state.automatic.last_result",
            "test_late_cancel_cannot_overwrite_newer_pending_automatic_command",
        ),
        (
            "omit_attempt_write",
            "pending=replace(pending, attempted=True)",
            "pending=pending",
            "test_saved_on_attempt_and_signed_revision_are_atomic_before_real_http",
        ),
        (
            "weak_source_receipt",
            ") or not p._same_stop_command(work.payload, result.receipt.command):",
            "):",
            "test_receipt_selector_match_is_insufficient_for_whole_source_command",
        ),
        (
            "equal_revision_contradiction",
            "if incoming.revision == old.revision and not p._same_consent(old, incoming):",
            "if False:",
            "test_historical_on_receipt_never_rolls_back_newer_current_consent",
        ),
        (
            "missing_final_expiry",
            "remaining = self._remaining(command.intent_created_at)",
            "remaining = -1",
            "test_on_crossing_original_expiry_during_real_signing_cannot_start_http",
        ),
        (
            "time_fence_bypass",
            "not self._control_time_fenced",
            "True",
            "test_slow_device_db_fact_is_authentication_not_an_anchor_or_reopening",
        ),
        (
            "source_journal_eviction",
            "        clear = False\n        self._source_observe.intersection_update(",
            "        self._persist(replace(self._state, pending_source_commands=()), fence, work=work)\n        clear = False\n        self._source_observe.intersection_update(",
            "test_ended_source_get_is_not_start_settlement",
        ),
        (
            "participation_cas_rebase",
            "            elif device.participation.generation != intent.expected_generation:\n                self._needs_fresh_intent = True",
            "            elif device.participation.generation != intent.expected_generation:\n                candidate = replace(candidate, pending_participation=replace(intent, expected_generation=device.participation.generation, attempted=False))\n                self._needs_fresh_intent = True",
            "test_bound_participation_off_never_rebases_after_newer_on",
        ),
        (
            "telemetry_gate_on_terminal",
            "    def _terminal_source_work(self):\n",
            "    def _terminal_source_work(self):\n        if self._latest is None:\n            return ()\n",
            "test_stop_receipt_first_runs_without_telemetry_feature_or_session_ack",
        ),
        (
            "retimestamp_off",
            "        command = pending.command\n        consent = automatic.observed_consent",
            "        command = pending.command\n        if not command.enabled:\n            command = replace(command, intent_created_at=self._utc_text())\n            self._state = replace(self._state, automatic=replace(automatic, pending=replace(pending, command=command)))\n        consent = automatic.observed_consent",
            "test_off_offline_age_never_refreshes_body_or_cas",
        ),
    ],
)
def test_control_barrier_regressions_kill_in_memory_mutants(
    tmp_path, monkeypatch, name, old, new, regression
):
    import inspect
    import sys
    from pathlib import Path
    from types import ModuleType

    from tests.test_fleetsharing_worker import _worker
    from wingman.fleetsharing import worker as production

    source = Path(production.__file__).read_text(encoding="utf-8")
    assert source.count(old) == 1, name
    module = ModuleType("wingman.fleetsharing._b_mutant")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    exec(
        compile(source.replace(old, new), production.__file__, "exec"), module.__dict__
    )
    monkeypatch.setitem(
        _worker.__globals__, "FleetSharingWorker", module.FleetSharingWorker
    )
    from tests import test_fleetsharing_worker_controls as controls

    exercise = globals().get(regression) or getattr(controls, regression)
    params = inspect.signature(exercise).parameters
    kwargs = {"tmp_path": tmp_path}
    if "monkeypatch" in params:
        kwargs["monkeypatch"] = monkeypatch
    for parameter in ("contradiction", "fenced", "attempted"):
        if parameter in params:
            kwargs[parameter] = True
    with pytest.raises((AssertionError, pytest.fail.Exception)):
        exercise(**kwargs)
