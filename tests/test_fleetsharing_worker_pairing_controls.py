"""Explicit authentication/history admissions share B's one atomic owner."""

import json
import threading
from dataclasses import replace

import pytest

from tests.test_fleetsharing_client import Response, framing_headers, request_binding
from tests.test_fleetsharing_worker import (
    CAPS,
    DATE,
    EXPIRY,
    PAIRED_STATE,
    TOKEN,
    UUID,
    drive,
)
from tests.test_fleetsharing_worker_automatic import ON, automatic_rig
from tests.test_fleetsharing_worker_state4 import file_rig
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing import state as s
from wingman.fleetsharing.client import FleetRelayClient


def auth_history():
    return (
        s.PendingPairing(
            "initial",
            UUID,
            "https://relay.test/approve",
            EXPIRY,
            True,
            (p.SHARED_CAPABILITY, p.COMBAT_CAPABILITY),
        ),
        s.PendingRecovery(
            TOKEN, DATE, p.RecoveryChallenge(UUID, TOKEN, TOKEN, EXPIRY), True
        ),
    )


def test_explicit_same_key_pairing_ack_replaces_only_exact_authentication_tuple(
    tmp_path,
):
    pairing, recovery = auth_history()
    original = replace(
        PAIRED_STATE,
        last_revision=17,
        pending_pairing=pairing,
        pending_recovery=recovery,
        auth_pause=s.AuthPause("retry_later", EXPIRY),
    )
    worker, client, store, _ = file_rig(tmp_path, original)
    worker.resume_pending()
    worker.iterate_once()
    assert worker.request_pairing(
        mode="initial",
        binding=worker.status().metadata.binding,
        supersedes=(pairing, recovery),
        requested_capabilities=CAPS,
    )
    worker.iterate_once()
    saved = s.load(store.path)
    assert saved.pending_pairing == s.PendingPairing(
        "initial", requested_capabilities=CAPS
    )
    assert saved.pending_recovery is None
    assert (
        saved.identity == original.identity
        and saved.relay_origin == original.relay_origin
    )
    assert saved.session_id == original.session_id and saved.last_revision == 17
    assert saved.approved_capabilities == original.approved_capabilities
    assert not client.calls


def test_settled_automatic_history_retires_only_with_authorized_new_identity(tmp_path):
    history = s.AutomaticState(observed_consent=ON)
    original = replace(
        PAIRED_STATE,
        device_id=UUID,
        automatic=history,
        auth_pause=s.AuthPause("device_revoked"),
    )
    worker, client, store, _ = file_rig(tmp_path, original)
    worker.resume_pending()
    worker.iterate_once()
    context = worker._timing_context
    worker._control_time_fenced = True
    worker._generate_private_key = lambda: bytes([1]) * 32
    client.automatic_consent = ON
    assert worker.request_pairing(
        mode="fresh",
        binding=worker.status().metadata.binding,
        automatic_history=history,
    )
    worker.iterate_once()
    saved = s.load(store.path)
    assert saved.identity != original.identity
    assert saved.automatic == s.AutomaticState()
    assert saved.pending_pairing.mode == "fresh"
    assert worker._timing_context is context and worker._control_time_fenced
    assert client.automatic_consent == ON and not client.controls
    # No intermediate same-identity state loses the account-wide high-water.
    assert all(
        v.identity != original.identity or v.automatic == history for v in store.saves
    )


@pytest.mark.parametrize("kind", ["auth_tuple", "fresh_history"])
def test_acknowledged_admission_write_failure_preserves_prior_evidence(
    tmp_path, monkeypatch, kind
):
    pairing, recovery = auth_history()
    history = s.AutomaticState(observed_consent=ON)
    original = replace(
        PAIRED_STATE,
        last_revision=17,
        device_id=UUID,
        automatic=history if kind == "fresh_history" else s.AutomaticState(),
        pending_pairing=pairing if kind == "auth_tuple" else None,
        pending_recovery=recovery if kind == "auth_tuple" else None,
        auth_pause=s.AuthPause("device_revoked")
        if kind == "fresh_history"
        else s.AuthPause("retry_later", EXPIRY),
    )
    worker, client, store, _ = file_rig(tmp_path, original)
    worker.resume_pending()
    worker.iterate_once()
    before = store.path.read_bytes()
    binding = worker.status().metadata.binding
    if kind == "auth_tuple":
        assert worker.request_pairing(
            mode="initial", binding=binding, supersedes=(pairing, recovery)
        )
    else:
        worker._generate_private_key = lambda: bytes([1]) * 32
        assert worker.request_pairing(
            mode="fresh", binding=binding, automatic_history=history
        )
    write = s.atomicio.write_atomic

    def fail(path, text):
        raise OSError("atomic admission failure")

    monkeypatch.setattr(s.atomicio, "write_atomic", fail)
    worker.iterate_once()
    assert store.path.read_bytes() == before and worker._state == original
    assert worker.status().detail == "persistence_failed" and not client.calls
    monkeypatch.setattr(s.atomicio, "write_atomic", write)


@pytest.mark.parametrize(
    "case", ["binding", "changed_history", "not_authorized", "pending", "other_journal"]
)
def test_fresh_history_ack_does_not_bypass_binding_or_existing_guards(tmp_path, case):
    history = s.AutomaticState(observed_consent=ON)
    current = (
        replace(history, observed_consent=replace(ON, generation=2, revision=2))
        if case == "changed_history"
        else history
    )
    if case == "pending":
        current = replace(
            history,
            pending=s.PendingAutomatic(p.AutomaticCommand(UUID, DATE, True, 1, 1)),
        )
    original = replace(
        PAIRED_STATE,
        device_id=UUID,
        automatic=current,
        auth_pause=None if case == "not_authorized" else s.AuthPause("device_revoked"),
        pending_participation=s.PendingParticipation(UUID, False, 1, True)
        if case == "other_journal"
        else None,
    )
    worker, client, store, _ = file_rig(tmp_path, original)
    worker.resume_pending()
    worker.iterate_once()
    before = store.path.read_bytes()
    calls = len(client.calls)
    result = worker.request_pairing(
        mode="fresh",
        binding="stale" if case == "binding" else worker.status().metadata.binding,
        automatic_history=current if case == "pending" else history,
    )
    if case in ("binding", "pending"):
        assert result is False
    worker.iterate_once()
    assert store.path.read_bytes() == before and len(client.calls) == calls


def test_same_key_ack_rejects_changed_attempt_tuple_without_erasing_journals(tmp_path):
    pairing, recovery = auth_history()
    original = replace(
        PAIRED_STATE,
        pending_pairing=pairing,
        pending_recovery=recovery,
        auth_pause=s.AuthPause("retry_later", EXPIRY),
    )
    worker, _, store, _ = file_rig(tmp_path, original)
    worker.resume_pending()
    worker.iterate_once()
    assert worker.request_pairing(
        mode="initial",
        binding=worker.status().metadata.binding,
        supersedes=(pairing, replace(recovery, completion_attempted=False)),
    )
    worker.iterate_once()
    assert s.load(store.path) == original and worker.status().pairing == "rejected"


def test_reentrant_old_history_ack_cannot_authorize_second_fresh_identity(
    tmp_path, monkeypatch
):
    history = s.AutomaticState(observed_consent=ON)
    original = replace(
        PAIRED_STATE,
        device_id=UUID,
        automatic=history,
        auth_pause=s.AuthPause("device_revoked"),
    )
    worker, _, store, _ = file_rig(tmp_path, original)
    worker.resume_pending()
    worker.iterate_once()
    binding = worker.status().metadata.binding
    keys, queued = [], []
    worker._generate_private_key = lambda: keys.append(bytes([1]) * 32) or keys[-1]
    write = s.atomicio.write_atomic

    def newer_after_write(path, text):
        write(path, text)
        if not queued:
            queued.append(
                worker.request_pairing(
                    mode="fresh",
                    configured_origin="https://other.test",
                    binding=binding,
                    automatic_history=history,
                )
            )

    monkeypatch.setattr(s.atomicio, "write_atomic", newer_after_write)
    worker.request_pairing(mode="fresh", binding=binding, automatic_history=history)
    worker.iterate_once()
    worker.iterate_once()
    assert queued == [True] and len(keys) == 1
    assert s.load(store.path).relay_origin == original.relay_origin
    assert s.load(store.path).automatic == s.AutomaticState()
    assert worker.status().pairing == "rejected"


def test_duplicate_stop_cannot_coalesce_with_an_obsolete_credential_action(tmp_path):
    original = replace(PAIRED_STATE, auth_pause=s.AuthPause("device_revoked"))
    worker, _, _store, _ = file_rig(tmp_path, original)
    worker.resume_pending()
    worker.iterate_once()
    old_binding = worker.status().metadata.binding
    save = worker._save_state
    queued = []

    def queue_old_binding_during_save(candidate):
        save(candidate)
        if not queued:
            queued.append(
                worker.request_source_stop(
                    UUID,
                    expected_generation=0,
                    expected_automatic=None,
                    binding=old_binding,
                )
            )

    worker._save_state = queue_old_binding_during_save
    worker.request_pairing(mode="fresh", configured_origin="https://other.test")
    worker.iterate_once()
    assert queued == [True]
    new_binding = worker.status().metadata.binding
    assert new_binding != old_binding
    assert worker.request_source_stop(
        UUID, expected_generation=0, expected_automatic=None, binding=new_binding
    )
    assert worker._commands["source:" + UUID].binding == new_binding


def test_same_key_new_admission_waits_for_real_old_completion_http_drain(tmp_path):
    pairing = replace(auth_history()[0], completion_attempted=False)
    original = replace(PAIRED_STATE, last_revision=17, pending_pairing=pairing)
    worker, _, store, mono = file_rig(tmp_path, original)
    entered, release = threading.Event(), threading.Event()
    requests = []

    def transport(request, timeout):
        requests.append(request)
        assert s.load(store.path).pending_pairing.completion_attempted
        entered.set()
        assert release.wait(5)
        body = {
            "protocol": 2,
            "session_id": "B" * 42 + "A",
            "catalogue": {"revision": 1, "characters": []},
        }
        return Response(
            json.dumps(body).encode(), framing_headers(request_binding(request))
        )

    worker._client_factory = lambda origin: FleetRelayClient(
        origin, transport=transport
    )
    worker.resume_pending()
    worker.iterate_once()
    mono[0] += 1
    owner = threading.Thread(target=worker.iterate_once)
    owner.start()
    try:
        assert entered.wait(3)
        attempted = s.load(store.path)
        before = store.path.read_bytes()
        assert worker.request_pairing(
            mode="upgrade",
            binding=worker.status().metadata.binding,
            supersedes=(attempted.pending_pairing, attempted.pending_recovery),
        )
        assert store.path.read_bytes() == before
        release.set()
        owner.join(3)
        assert not owner.is_alive()
        worker.iterate_once()
        saved = s.load(store.path)
        assert saved.pending_pairing == s.PendingPairing(
            "upgrade", requested_capabilities=CAPS
        )
        assert saved.session_id == original.session_id and saved.last_revision == 17
        assert saved.identity == original.identity and len(requests) == 1
    finally:
        release.set()
        owner.join(5)


def test_pending_browser_approval_does_not_strand_off_on_valid_old_session(tmp_path):
    command = p.AutomaticCommand(UUID, DATE, False, 1, 1)
    worker, store, mono, _, attempts, _ = automatic_rig(
        tmp_path, s.PendingAutomatic(command), observed=ON
    )
    pairing = s.PendingPairing(
        "upgrade",
        UUID,
        "https://relay.test/approve",
        EXPIRY,
        requested_capabilities=(p.SHARED_CAPABILITY, p.COMBAT_CAPABILITY),
    )
    s.save(store.path, replace(s.load(store.path), pending_pairing=pairing))
    factory = worker._client_factory

    def client_factory(origin):
        client = factory(origin)
        transport = client._transport

        def pending_approval(request, timeout):
            if "/pairing-requests/" in request.full_url:
                return Response(
                    b'{"protocol":2,"error":"not_completable"}',
                    framing_headers(request_binding(request)),
                    409,
                )
            return transport(request, timeout)

        client._transport = pending_approval
        return client

    worker._client_factory = client_factory
    drive(worker, mono, 8)
    assert len(attempts) == 1 and not attempts[0].automatic.pending.command.enabled
    assert s.load(store.path).automatic.pending is None
    assert s.load(store.path).automatic.last_result.outcome == "receipt"
    assert s.load(store.path).session_id == PAIRED_STATE.session_id
