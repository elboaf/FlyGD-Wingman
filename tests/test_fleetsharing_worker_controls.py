"""S4-B immutable control runtime proofs with the real state4 writer."""

import json
import threading
from dataclasses import asdict, replace
from datetime import timedelta

import pytest

from tests.test_fleetsharing_client import Response, framing_headers, request_binding
from tests.test_fleetsharing_worker import DATE, DEVICE, NOW, UUID, drive
from tests.test_fleetsharing_worker_state4 import file_rig, legacy_file
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing import state as s
from wingman.fleetsharing.client import FleetRelayClient, FleetRelayError


@pytest.mark.parametrize(
    "age_ms,sent", [(-1, False), (0, True), (59999, True), (60000, False)]
)
def test_start_exact_original_window_never_restamps(tmp_path, age_ms, sent):
    worker, client, store, mono = file_rig(tmp_path)
    command = p.SourceStart(UUID, 1, UUID, DATE)
    s.save(store.path, replace(s.load(store.path), pending_source_commands=(command,)))
    worker._utc_clock = client.utc = lambda: NOW + timedelta(milliseconds=age_ms)
    worker.resume_pending()
    drive(worker, mono, 6)
    assert bool(client.controls) is sent
    assert all(c == command for c in client.controls)
    assert s.load(store.path).pending_source_commands == (() if sent else (command,))


def test_source_case_variants_share_one_bounded_submission_fence(tmp_path):
    worker, _, _, _ = file_rig(tmp_path)
    assert worker.request_source_stop(
        UUID, expected_generation=1, expected_automatic=None
    )
    assert worker.request_source_stop(
        UUID.upper(), expected_generation=2, expected_automatic=None
    )
    assert len(worker._commands) == 1
    assert len(worker._source_generations) == 1
    assert next(iter(worker._commands.values())).payload.source_id == UUID.upper()


def test_source_dismissal_cannot_enqueue_unretained_commands(tmp_path):
    worker, _, _, _ = file_rig(tmp_path)
    worker.resume_pending()
    worker.iterate_once()
    assert (
        worker.request_dismiss_source(
            p.SourceStart(UUID, 1, UUID, DATE), binding=worker.status().metadata.binding
        )
        is False
    )
    assert not worker._commands and not worker._source_generations


def test_expired_start_stays_unknown_after_absent_source_observation(tmp_path):
    worker, client, store, mono = file_rig(tmp_path, enabled=True)
    command = p.SourceStart(UUID, 1, UUID, "2026-09-07T11:58:00.000Z")
    s.save(store.path, replace(s.load(store.path), pending_source_commands=(command,)))
    drive(worker, mono, 8)
    assert s.load(store.path).pending_source_commands == (command,)
    assert not client.controls


def test_ended_source_get_is_not_start_settlement(tmp_path):
    worker, client, store, mono = file_rig(tmp_path, enabled=True)
    command = p.SourceStart(UUID, 1, UUID, DATE)
    s.save(store.path, replace(s.load(store.path), pending_source_commands=(command,)))
    client.source_views[UUID] = p.SourceView(UUID, 2, 1, "ended", "stopped", None, None)
    drive(worker, mono, 8)
    assert s.load(store.path).pending_source_commands == (command,)
    assert worker.status().source_control != "acknowledged"


def test_same_source_stop_cannot_replace_unknown_start_without_exact_ack(tmp_path):
    worker, client, store, mono = file_rig(tmp_path, enabled=True)
    client.errors["control_source"] = FleetRelayError(None, "transport_error", "lost")
    command = p.SourceStart(UUID.upper(), 1, UUID, DATE)
    s.save(store.path, replace(s.load(store.path), pending_source_commands=(command,)))
    worker.iterate_once()
    worker.request_source_stop(UUID, expected_generation=2, expected_automatic=None)
    drive(worker, mono, 3)
    assert s.load(store.path).pending_source_commands == (command,)


def test_explicit_source_stop_keeps_displayed_cas_and_original_spelling(tmp_path):
    worker, _client, store, _mono = file_rig(tmp_path, enabled=True)
    command = p.SourceStart(UUID.upper(), 1, UUID, DATE)
    s.save(store.path, replace(s.load(store.path), pending_source_commands=(command,)))
    worker.iterate_once()
    assert worker.request_source_stop(
        UUID.upper(),
        expected_generation=7,
        expected_automatic=p.AutomaticBinding(4),
        supersedes=command,
    )
    worker.iterate_once()
    saved = s.load(store.path).pending_source_commands
    assert len(saved) == 1 and isinstance(saved[0], p.SourceStop)
    assert saved[0].source_id == UUID.upper()
    assert saved[0].expected_generation == 7
    assert saved[0].expected_automatic == p.AutomaticBinding(4)
    assert saved[0].intent_created_at == DATE


def test_direct_start_result_settles_without_treating_wrapper_as_source(tmp_path):
    worker, _client, store, mono = file_rig(tmp_path, enabled=True)
    source_id = worker.request_source_start(1, UUID)
    drive(worker, mono, 5)
    assert source_id is not None
    assert s.load(store.path).pending_source_commands == ()
    assert worker.status().source_control == "acknowledged"
    assert worker.status().detail is None


def wire(value):
    return json.loads(json.dumps(asdict(value)))


def real_client(worker, store, reply):
    calls = []

    def transport(request, timeout):
        saved = s.load(store.path)
        assert saved.last_revision == int(request.get_header("X-fleet-revision"))
        calls.append((request, saved))
        body, status = reply(request, saved)
        return Response(
            json.dumps(body).encode(), framing_headers(request_binding(request)), status
        )

    worker._client_factory = lambda origin: FleetRelayClient(
        origin, transport=transport
    )
    return calls


def test_stop_receipt_first_runs_without_telemetry_feature_or_session_ack(tmp_path):
    command = p.SourceStop(UUID.upper(), 0, UUID, DATE, None)
    worker, _, store, mono = file_rig(tmp_path)
    s.save(store.path, replace(s.load(store.path), pending_source_commands=(command,)))
    terminal_device = replace(
        DEVICE,
        feature_enabled=False,
        session_approved_capabilities=(),
        acknowledged_capabilities=(),
    )
    off = p.Consent(0, 0, False, None, None, None, None)
    status = p.AutomaticStatus(off, "none", "off", "none", None, ())
    source = p.SourceView(UUID, 1, None, "ended", "stopped", None, None)
    receipt = p.SourceStopReceipt(
        command, DATE, "2026-09-08T12:00:00.000Z", source, "unknown_cancelled", off
    )

    def reply(request, saved):
        if request.full_url.endswith("/device"):
            return {"protocol": 2, **wire(terminal_device)}, 200
        if "/receipts/" in request.full_url:
            return {"protocol": 2, "error": "receipt_not_found"}, 404
        assert request.method == "PUT" and request.full_url.endswith("/sources")
        assert json.loads(request.data) == p.source_command_body(command)
        raw = wire(receipt)
        raw["command"] = p.source_command_body(command)
        return {
            "protocol": 2,
            "request_id": UUID,
            "result": "applied",
            "receipt": raw,
            "source": wire(source),
            "automatic_effect": "unknown_cancelled",
            "status": wire(status),
        }, 200

    calls = real_client(worker, store, reply)
    worker.resume_pending()
    drive(worker, mono, 8)
    assert [r.method for r, _ in calls] == ["GET", "GET", "PUT"]
    assert "/receipts/" in calls[1][0].full_url
    assert s.load(store.path).pending_source_commands == ()
    assert s.load(store.path).automatic.observed_consent == off


def test_source_stop_current_status_can_authorize_fresh_explicit_automatic_off(
    tmp_path,
):
    command = p.SourceStop(UUID, 1, UUID, DATE, None)
    worker, _, store, mono = file_rig(tmp_path)
    s.save(store.path, replace(s.load(store.path), pending_source_commands=(command,)))
    off = p.Consent(0, 0, False, None, None, None, None)
    status = p.AutomaticStatus(off, "none", "off", "none", None, ())
    source = p.SourceView(UUID, 1, 1, "ended", "stopped", None, None)

    def reply(request, saved):
        if request.full_url.endswith("/device"):
            return {"protocol": 2, **wire(DEVICE)}, 200
        if "/receipts/" in request.full_url:
            return {"protocol": 2, "error": "receipt_not_found"}, 404
        body = json.loads(request.data)
        if request.full_url.endswith("/automatic-verification"):
            return {
                "protocol": 2,
                "request_id": body["request_id"],
                "result": "already_off",
                "receipt": None,
                "status": wire(status),
            }, 200
        return {
            "protocol": 2,
            "request_id": UUID,
            "result": "already_stopped",
            "receipt": None,
            "source": wire(source),
            "automatic_effect": "manual_only",
            "status": wire(status),
        }, 200

    real_client(worker, store, reply)
    worker.resume_pending()
    drive(worker, mono, 5)
    action = worker.request_automatic(
        False,
        expected_generation=0,
        expected_revision=0,
        binding=worker.status().metadata.binding,
    )
    assert action is not None
    drive(worker, mono, 3)
    assert s.load(store.path).automatic.last_result.pending.command.request_id == action
    assert s.load(store.path).automatic.last_result.outcome == "already_off"


def test_receipt_selector_match_is_insufficient_for_whole_source_command(tmp_path):
    command = p.SourceStop(UUID, 0, UUID, DATE, None)
    worker, _, store, mono = file_rig(tmp_path)
    s.save(store.path, replace(s.load(store.path), pending_source_commands=(command,)))
    altered = replace(command, expected_generation=1)
    off = p.Consent(0, 0, False, None, None, None, None)
    receipt = p.SourceStopReceipt(
        altered,
        DATE,
        "2026-09-08T12:00:00.000Z",
        p.SourceView(UUID, 2, 1, "ended", "stopped", None, None),
        "manual_only",
        off,
    )
    raw = wire(receipt)
    raw["command"] = p.source_command_body(altered)
    result = {
        "protocol": 2,
        "receipt": raw,
        "status": wire(p.AutomaticStatus(off, "none", "off", "none", None, ())),
    }
    p.parse_receipt_get(result, expected_request_id=UUID)

    def reply(request, saved):
        if request.full_url.endswith("/device"):
            return {"protocol": 2, **wire(DEVICE)}, 200
        assert "/receipts/" in request.full_url
        return result, 200

    real_client(worker, store, reply)
    worker.resume_pending()
    drive(worker, mono, 5)
    saved = s.load(store.path)
    assert saved.pending_source_commands == (command,)
    assert saved.automatic.observed_consent is None
    assert worker.status().detail == "malformed_response"


def test_participation_ack_rejects_integer_attempt_flag(tmp_path):
    old = s.PendingParticipation(UUID, False, 1, True)
    worker, _, store, _ = file_rig(tmp_path)
    s.save(
        store.path,
        replace(
            s.load(store.path),
            pending_participation=old,
            auth_pause=s.AuthPause("device_revoked"),
        ),
    )
    worker.resume_pending()
    worker.iterate_once()
    assert (
        worker.request_participation(
            True,
            binding=worker.status().metadata.binding,
            supersedes=replace(old, attempted=1),
        )
        is None
    )
    assert s.load(store.path).pending_participation == old


def test_bound_participation_off_never_rebases_after_newer_on(tmp_path):
    worker, client, store, mono = file_rig(tmp_path, enabled=True)
    intent = s.PendingParticipation(UUID, False, 1, True)
    s.save(store.path, replace(s.load(store.path), pending_participation=intent))
    client.device = replace(DEVICE, participation=p.Participation(True, 3))
    drive(worker, mono, 6)
    assert s.load(store.path).pending_participation == intent
    assert not client.participation_calls
    assert worker.status().participation == "needs_confirmation"


def test_pending_stop_duplicate_preserves_original_request_time_and_body(tmp_path):
    command = p.SourceStop(UUID, 4, UUID, DATE, None)
    worker, _client, store, mono = file_rig(tmp_path)
    s.save(store.path, replace(s.load(store.path), pending_source_commands=(command,)))
    worker.resume_pending()
    worker.iterate_once()
    mono[0] += 20
    assert worker.request_source_stop(
        UUID.upper(), expected_generation=4, expected_automatic=None
    )
    worker.iterate_once()
    assert s.load(store.path).pending_source_commands == (command,)
    assert worker.status().source_control != "needs_confirmation"


def test_archive_selector_boundary_rejects_nontext_without_raising(tmp_path):
    worker, _, _, _ = file_rig(tmp_path)
    worker.resume_pending()
    worker.iterate_once()
    assert (
        worker.request_dismiss_cutover([], binding=worker.status().metadata.binding)
        is False
    )
    assert not worker._commands


def test_dismissal_and_explicit_archive_removal_never_rewrite_original(tmp_path):
    worker, client, store, _mono = file_rig(tmp_path, None)
    original = legacy_file(store)
    worker.resume_pending()
    worker.iterate_once()
    binding = worker.status().metadata.binding
    outcomes = worker.status().cutover_outcomes
    assert worker.request_remove_cutover(outcomes, binding=binding)
    worker.iterate_once()
    assert s.load(store.path).cutover.original == original
    for item in worker.status().cutover_outcomes:
        assert worker.request_dismiss_cutover(item.selector, binding=binding)
    worker.iterate_once()
    saved = s.load(store.path)
    assert saved.cutover.original == original
    assert all(v.status == "dismissed" for v in saved.cutover.outcomes)
    assert worker.request_remove_cutover(saved.cutover.outcomes, binding=binding)
    worker.iterate_once()
    assert s.load(store.path).cutover is None
    assert s.load(store.path).identity == saved.identity
    assert not client.controls and not client.participation_calls


def test_receipt_backoff_does_not_block_unrelated_start(tmp_path):
    stop = p.SourceStop(UUID, 0, UUID, DATE, None)
    worker, client, store, mono = file_rig(tmp_path, enabled=True)
    s.save(store.path, replace(s.load(store.path), pending_source_commands=(stop,)))
    client.errors["fetch_receipt"] = FleetRelayError(429, "rate_limited", "bounded")
    start = worker.request_source_start(1, UUID)
    drive(worker, mono, 12)
    assert any(c.source_id == start for c in client.controls)
    assert stop in s.load(store.path).pending_source_commands
    assert client.cadence_refusals == 0


def test_source_catalogue_cannot_replace_failed_stop_receipt_recovery(tmp_path):
    stop = p.SourceStop(UUID, 0, UUID, DATE, None)
    start = p.SourceStart("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", 1, UUID, DATE)
    worker, client, store, mono = file_rig(tmp_path, enabled=True)
    s.save(
        store.path, replace(s.load(store.path), pending_source_commands=(stop, start))
    )
    client.errors["fetch_receipt"] = FleetRelayError(None, "transport_error", "lost")
    drive(worker, mono, 12)
    assert start in client.controls
    assert not any(isinstance(c, p.SourceStop) for c in client.controls)
    assert stop in s.load(store.path).pending_source_commands


def test_real_start_http_drains_before_explicit_stop_and_never_rebases_it(tmp_path):
    worker, _, store, mono = file_rig(tmp_path)
    entered, release = threading.Event(), threading.Event()
    off = p.Consent(0, 0, False, None, None, None, None)
    status = p.AutomaticStatus(off, "none", "off", "none", None, ())

    def reply(request, saved):
        if request.full_url.endswith("/device"):
            return {"protocol": 2, **wire(DEVICE)}, 200
        if "/receipts/" in request.full_url:
            return {"protocol": 2, "error": "receipt_not_found"}, 404
        command = p.parse_source_command(json.loads(request.data))
        if isinstance(command, p.SourceStart):
            entered.set()
            assert release.wait(5)
            return {
                "protocol": 2,
                "source": wire(
                    p.SourceView(command.source_id, 1, 1, "active", None, None, None)
                ),
            }, 200
        if command.expected_generation == 0:
            return {"protocol": 2, "error": "conflict"}, 409
        source = p.SourceView(command.source_id, 2, 1, "ended", "stopped", None, None)
        accepted = worker._utc_text()
        expiry = (
            (worker._utc_now() + timedelta(days=1))
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
        receipt = {
            "kind": "source_stop",
            "command": p.source_command_body(command),
            "accepted_at": accepted,
            "expires_at": expiry,
            "source": wire(source),
            "automatic_effect": "manual_only",
            "consent": wire(off),
        }
        return {
            "protocol": 2,
            "request_id": command.request_id,
            "result": "applied",
            "receipt": receipt,
            "source": wire(source),
            "automatic_effect": "manual_only",
            "status": wire(status),
        }, 200

    calls = real_client(worker, store, reply)
    source_id = worker.request_source_start(1, UUID)
    worker.iterate_once()
    mono[0] += 0.5
    owner = threading.Thread(target=worker.iterate_once)
    owner.start()
    try:
        assert entered.wait(3)
        original = s.load(store.path).pending_source_commands[0]
        before = store.path.read_bytes()
        assert worker.request_source_stop(
            source_id,
            expected_generation=0,
            expected_automatic=None,
            supersedes=original,
        )
        assert store.path.read_bytes() == before
        release.set()
        owner.join(3)
        assert not owner.is_alive()
        worker.iterate_once()
        stop = s.load(store.path).pending_source_commands[0]
        assert isinstance(stop, p.SourceStop) and stop.expected_generation == 0
        drive(worker, mono, 7)
        assert s.load(store.path).pending_source_commands == (stop,)
        assert worker.request_source_stop(
            source_id, expected_generation=1, expected_automatic=None, supersedes=stop
        )
        drive(worker, mono, 12)
        assert s.load(store.path).pending_source_commands == ()
        bodies = [json.loads(r.data) for r, _ in calls if r.method == "PUT"]
        assert bodies[0] == p.source_command_body(original)
        assert any(b == p.source_command_body(stop) for b in bodies)
        assert (
            bodies[-1]["expected_generation"] == 1
            and bodies[-1]["request_id"] != stop.request_id
        )
    finally:
        release.set()
        owner.join(5)


def test_new_unbound_on_needs_fresh_confirmation_after_device_observation(tmp_path):
    worker, client, store, mono = file_rig(tmp_path, enabled=True)
    client.device = replace(DEVICE, participation=p.Participation(False, 1))
    intent_id = worker.request_participation(True)
    drive(worker, mono, 6)
    assert s.load(store.path).pending_participation == s.PendingParticipation(
        intent_id, True
    )
    assert not client.participation_calls
    assert worker.status().participation == "needs_confirmation"
