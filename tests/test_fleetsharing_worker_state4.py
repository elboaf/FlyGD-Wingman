"""Bounded S4-A owner proofs — real state files, no DPAPI or external HTTP."""

import json
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import timedelta

import pytest

from tests.fleetsharing_state4_helpers import LEGACY_V3
from tests.test_fleetsharing_worker import (
    DEVICE,
    NOW,
    PAIRED_STATE,
    FakeRelayClient,
    _worker,
    drive,
)
from wingman.fleetsharing import state as s
from wingman.fleetsharing.worker import FleetSharingWorker


def test_constructor_cannot_silently_discard_durable_writes():
    with pytest.raises(TypeError, match="save_state"):
        FleetSharingWorker(load_state=lambda: s.EMPTY)


def test_constructor_cannot_mint_an_independent_elapsed_lifetime():
    with pytest.raises(TypeError, match="timing_context"):
        FleetSharingWorker(load_state=lambda: s.EMPTY, save_state=lambda state: None)


class FileStore:
    def __init__(self, path):
        self.path = path
        self.loads = 0
        self.saves = []

    def load(self):
        self.loads += 1
        return s.load(self.path)

    def save(self, state):
        s.save(self.path, state)
        self.saves.append(state)


def file_rig(tmp_path, state=PAIRED_STATE, *, enabled=False):
    store = FileStore(tmp_path / "sharing.json")
    if state is not None:
        s.save(store.path, state)
    mono = [1000.0]
    client = FakeRelayClient(
        device=DEVICE, registered=state is None or state.identity is not None
    )
    worker = _worker(
        client,
        store=store,
        clock=lambda: mono[0],
        utc_clock=lambda: NOW + timedelta(seconds=mono[0] - 1000),
        sharing_enabled=lambda: enabled,
    )
    return worker, client, store, mono


@pytest.mark.parametrize(
    "original", [b'{"version":999,"private":"do not render"}', b"{", b'{"version":3}']
)
def test_quarantine_latches_without_initialization_even_after_fresh_action(
    tmp_path, original
):
    worker, client, store, mono = file_rig(tmp_path, None)
    store.path.write_bytes(original)
    worker.request_pairing(mode="fresh", configured_origin="https://relay.test")
    drive(worker, mono, 8)
    assert worker.status().detail == "state_quarantined"
    assert not worker.status().metadata.loaded
    assert worker._state is None and not store.saves and not client.calls
    assert store.loads == 1 and store.path.read_bytes() == original


def test_load_io_failure_is_retryable_not_empty_or_quarantine(tmp_path, monkeypatch):
    worker, client, store, mono = file_rig(tmp_path)
    stat = type(store.path).stat

    def denied(path, *args, **kwargs):
        if path == store.path:
            raise PermissionError("private stat failure")
        return stat(path, *args, **kwargs)

    monkeypatch.setattr(type(store.path), "stat", denied)
    worker.request_pairing(mode="fresh", configured_origin="https://other.test")
    drive(worker, mono, 2)
    assert worker.status().detail == "state_load_failed"
    assert worker._state is None and not store.saves and not client.calls
    assert store.loads == 1
    monkeypatch.setattr(type(store.path), "stat", stat)
    worker.iterate_once()
    assert store.loads == 2 and worker.status().metadata.loaded


def legacy_file(store):
    # Literal old contract fixture; never serialize a current dataclass as legacy.
    raw = deepcopy(LEGACY_V3)
    raw["identity"] = asdict(PAIRED_STATE.identity)
    raw["relay_origin"] = PAIRED_STATE.relay_origin
    raw["pending_pairing"]["approval_url"] = "https://relay.test/approve"
    raw["auth_pause"] = None
    store.path.write_text(json.dumps(raw), encoding="utf-8")
    return raw


def test_archived_off_bootstraps_once_without_telemetry_and_inhibits_current_on(
    tmp_path,
):
    worker, client, store, mono = file_rig(tmp_path, None)
    original = legacy_file(store)
    worker.resume_pending()
    drive(worker, mono, 16)
    assert client.recoveries == 1
    assert worker.status().local_inhibited
    assert worker.status().detail == "unresolved_previous_choice"
    saved = s.load(store.path)
    assert saved.cutover.original == original
    assert saved.pending_participation is None and not saved.pending_source_commands
    assert (
        not client.controls and not client.participation_calls and not client.pair_keys
    )
    count = len(client.calls)
    drive(worker, mono, 200)
    assert len(client.calls) == count  # Unknown old Start/Stop is not a busy-loop.
    worker._sharing_enabled = lambda: True
    drive(worker, mono, 10)
    assert worker.status().local_inhibited
    assert not client.publish_calls


def test_fresh_setup_cannot_discard_unknown_active_journals(tmp_path):
    original = replace(
        PAIRED_STATE,
        auth_pause=s.AuthPause("device_revoked"),
        pending_participation=s.PendingParticipation(DEVICE.device_id, False, 1, True),
    )
    worker, client, store, mono = file_rig(tmp_path, original)
    worker.request_pairing(mode="fresh", configured_origin="https://other.test")
    drive(worker, mono, 5)
    assert s.load(store.path) == original
    assert not store.saves and not client.calls
    assert worker.status().pairing == "rejected"
    assert worker.status().detail == "unresolved_history"


def test_pairing_admission_captures_default_capabilities_before_owner_turn(
    tmp_path, monkeypatch
):
    from wingman.fleetsharing import worker as owner

    worker, client, store, _ = file_rig(tmp_path, s.EMPTY)
    worker.request_pairing(configured_origin="https://relay.test")
    monkeypatch.setattr(owner, "CAPABILITIES", ("shared-source-v1", "combat-v2"))
    worker.iterate_once()
    saved = s.load(store.path).pending_pairing
    assert saved.requested_capabilities == ("shared-source-v1",)
    assert next(iter(client.pairings.values()))[3] == saved.requested_capabilities


def test_recovery_attempt_write_failure_suppresses_one_use_http(tmp_path, monkeypatch):
    worker, client, store, mono = file_rig(
        tmp_path, s.replace_session(PAIRED_STATE, None), enabled=True
    )
    write = s.atomicio.write_atomic
    attempts = []

    def fail_attempt(path, data):
        pending = json.loads(data)["pending_recovery"]
        if pending and pending["completion_attempted"]:
            attempts.append(pending)
            raise OSError("disk full")
        write(path, data)

    monkeypatch.setattr(s.atomicio, "write_atomic", fail_attempt)
    drive(worker, mono, 8)
    assert not any(kind == "complete_recovery" for kind, _, _ in client.calls)
    assert attempts and worker.status().detail == "persistence_failed"
    saved = s.load(store.path).pending_recovery
    assert saved.challenge and not saved.completion_attempted
    assert worker._state == s.load(store.path)


def test_crash_after_recovery_completion_never_replays_consumed_challenge(
    tmp_path, monkeypatch
):
    worker, client, store, mono = file_rig(
        tmp_path, s.replace_session(PAIRED_STATE, None), enabled=True
    )
    write = s.atomicio.write_atomic

    def fail_session(path, data):
        if json.loads(data)["session_id"] is not None:
            raise OSError("session commit failed")
        write(path, data)

    monkeypatch.setattr(s.atomicio, "write_atomic", fail_session)
    drive(worker, mono, 5)
    old = s.load(store.path).pending_recovery
    assert old.challenge and old.completion_attempted and client.recoveries == 1
    worker.stop()
    monkeypatch.setattr(s.atomicio, "write_atomic", write)
    other = _worker(
        client, store=store, timing_context=worker._timing_context, utc_clock=client.utc
    )
    drive(other, mono, 12)
    assert client.recoveries == 2
    assert [kind for kind, _, _ in client.calls].count("complete_recovery") == 2
    assert len(client.admissions) == 2
    assert s.load(store.path).pending_recovery is None


def test_real_client_off_during_signing_refuses_transport_but_keeps_revision(
    tmp_path, monkeypatch
):
    from tests.test_fleetsharing_client import FakeTransport
    from wingman.fleetsharing import crypto
    from wingman.fleetsharing.client import FleetRelayClient

    worker, _, store, _ = file_rig(tmp_path, enabled=True)
    transport = FakeTransport({"protocol": 2})
    worker._client_factory = lambda origin: FleetRelayClient(
        origin, transport=transport
    )
    sign = crypto.sign_request

    def off_after_signing(key, canonical):
        signature = sign(key, canonical)
        worker.request_participation(False)
        return signature

    monkeypatch.setattr(crypto, "sign_request", off_after_signing)
    worker.iterate_once()
    assert transport.requests == []
    assert s.load(store.path).last_revision == 1
    assert worker._scheduler.deadlines["read"] == 0


def test_known_negative_pair_poll_keeps_durable_flag_and_can_finish_live(tmp_path):
    from tests.test_fleetsharing_worker import PAIRED_SESSION
    from wingman.fleetsharing.client import FleetRelayError

    worker, client, store, mono = file_rig(tmp_path, s.EMPTY)
    client.errors["complete_pairing"] = FleetRelayError(
        409, "not_completable", "pending"
    )
    worker.request_pairing(configured_origin="https://relay.test")
    drive(worker, mono, 3)
    pending = s.load(store.path).pending_pairing
    assert pending.completion_attempted
    drive(worker, mono, 8)
    assert [kind for kind, _, _ in client.calls].count("complete_pairing") > 1
    flagged = next(
        i
        for i, value in enumerate(store.saves)
        if value.pending_pairing and value.pending_pairing.completion_attempted
    )
    assert all(
        value.pending_pairing.completion_attempted for value in store.saves[flagged:]
    )
    client.errors.clear()
    drive(worker, mono, 30)
    assert s.load(store.path).session_id == PAIRED_SESSION
    assert client.recoveries == 0


def test_authenticated_device_mismatch_cannot_rebind_saved_identity(tmp_path):
    original = replace(PAIRED_STATE, device_id=DEVICE.device_id)
    worker, client, store, mono = file_rig(tmp_path, original, enabled=True)
    client.device = replace(DEVICE, device_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    worker.iterate_once()
    assert s.load(store.path).device_id == original.device_id
    assert worker.status().detail == "identity_mismatch"
    assert worker.status().local_inhibited
    count = len(client.calls)
    drive(worker, mono, 20)
    assert len(client.calls) == count


def test_revision_exhaustion_recovers_without_resetting_old_attempted_floor(
    tmp_path, monkeypatch
):
    from wingman.fleetsharing import protocol as p

    original = replace(
        PAIRED_STATE, last_revision=p.INT4_MAX, device_id=DEVICE.device_id
    )
    worker, client, store, mono = file_rig(tmp_path, original, enabled=True)
    write = s.atomicio.write_atomic

    def fail_replacement(path, data):
        if json.loads(data)["session_id"] != original.session_id:
            raise OSError("replacement failed")
        write(path, data)

    monkeypatch.setattr(s.atomicio, "write_atomic", fail_replacement)
    drive(worker, mono, 6)
    assert client.recoveries == 1
    saved = s.load(store.path)
    assert saved.session_id == original.session_id and saved.last_revision == p.INT4_MAX
    assert all(revision is None for _, _, revision in client.calls)
    monkeypatch.setattr(s.atomicio, "write_atomic", write)
    drive(worker, mono, 12)
    saved = s.load(store.path)
    assert saved.session_id != original.session_id and saved.last_revision < 20
    assert saved.identity == original.identity


def test_upgrade_cannot_erase_an_unresolved_recovery_or_old_floor(tmp_path):
    from tests.test_fleetsharing_worker import DATE, TOKEN

    original = replace(
        PAIRED_STATE, last_revision=17, pending_recovery=s.PendingRecovery(TOKEN, DATE)
    )
    worker, client, store, _ = file_rig(tmp_path, original)
    worker.request_pairing(mode="upgrade")
    worker.iterate_once()
    assert s.load(store.path) == original
    assert worker.status().pairing == "rejected"
    assert not client.pair_keys


def test_real_recovery_transport_observes_durable_attempt_before_http(tmp_path):
    from tests.test_fleetsharing_client import (
        Response,
        framing_headers,
        request_binding,
    )
    from tests.test_fleetsharing_worker import EXPIRY, TOKEN
    from wingman.fleetsharing.client import FleetRelayClient

    worker, _, store, mono = file_rig(
        tmp_path, s.replace_session(PAIRED_STATE, None), enabled=True
    )
    attempts = []

    def transport(request, timeout):
        pending = s.load(store.path).pending_recovery
        if request.full_url.endswith("/complete"):
            assert pending.completion_attempted and pending.challenge
            attempts.append(pending)
            body = {"protocol": 2, "result": "retry_later", "retry_after_ms": 1000}
        else:
            assert pending and not pending.completion_attempted
            assert json.loads(request.data)["request_id"] == pending.request_id
            body = {
                "protocol": 2,
                "challenge_id": DEVICE.device_id,
                "request_id": pending.request_id,
                "nonce": TOKEN,
                "expires_at": EXPIRY,
            }
        return Response(
            json.dumps(body).encode(), framing_headers(request_binding(request))
        )

    worker._client_factory = lambda origin: FleetRelayClient(
        origin, transport=transport
    )
    drive(worker, mono, 5)
    assert len(attempts) == 1
    assert s.load(store.path).auth_pause.result == "retry_later"


def test_logical_start_excludes_signing_and_completion_pacing_survives_restart(
    tmp_path, monkeypatch
):
    from tests.test_fleetsharing_client import FakeTransport
    from wingman.fleetsharing import crypto
    from wingman.fleetsharing.client import FleetRelayClient

    worker, _, _, mono = file_rig(tmp_path, enabled=True)
    mono[0] = 9.0
    worker._utc_clock = lambda: NOW
    body = {"protocol": 2, **asdict(DEVICE)}
    for key in (
        "approved_capabilities",
        "session_approved_capabilities",
        "acknowledged_capabilities",
    ):
        body[key] = list(body[key])
    transport = FakeTransport(body)
    sign = crypto.sign_request
    spans = []
    accept = worker._accept

    def signing(key, canonical):
        result = sign(key, canonical)
        if mono[0] < 10:
            mono[0] = 10.0
        return result

    def send(request, timeout):
        response = transport(request, timeout)
        mono[0] += 0.2
        return response

    def observe(work, result, fence, started, receipt):
        spans.append((started, receipt))
        accept(work, result, fence, started, receipt)

    monkeypatch.setattr(crypto, "sign_request", signing)
    worker._accept = observe
    worker._client_factory = lambda origin: FleetRelayClient(origin, transport=send)
    context = worker._timing_context
    worker.iterate_once()
    assert spans == [(10.0, 10.2)]
    assert context._scheduler.deadlines["read"] == 10.7
    order, epoch = worker.status().order, worker._epoch
    assert worker.stop() and worker.start()
    mono[0] = 10.69
    worker.iterate_once()
    assert len(transport.requests) == 1
    mono[0] = 10.7
    worker.iterate_once()
    assert len(transport.requests) == 2
    assert worker._timing_context is context
    assert worker._scheduler is context._scheduler and worker._clock is context._clock
    assert worker._epoch > epoch and worker.status().order >= order
    assert worker.stop()


def test_recovery_mismatch_retains_all_old_session_and_command_evidence(tmp_path):
    from tests.fleetsharing_state4_helpers import ACTIVE_V4
    from wingman.fleetsharing import protocol as p

    worker, client, store, mono = file_rig(tmp_path, None, enabled=True)
    raw = deepcopy(ACTIVE_V4)
    raw["identity"] = asdict(PAIRED_STATE.identity)
    raw["relay_origin"] = PAIRED_STATE.relay_origin
    raw["pending_pairing"]["approval_url"] = "https://relay.test/approve"
    raw["auth_pause"] = None
    raw["last_revision"] = p.INT4_MAX
    store.path.write_text(json.dumps(raw), encoding="utf-8")
    original = s.load(store.path)
    client.device = replace(DEVICE, device_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
    drive(worker, mono, 10)
    saved = s.load(store.path)
    assert client.recoveries == 1 and worker.status().detail == "identity_mismatch"
    assert saved.device_id == original.device_id
    assert (saved.session_id, saved.last_revision) == (
        original.session_id,
        original.last_revision,
    )
    assert saved.pending_source_commands == original.pending_source_commands
    assert saved.pending_participation == original.pending_participation
    assert saved.pending_pairing == original.pending_pairing
    assert saved.pending_recovery.completion_attempted


def test_matching_case_insensitive_recovery_preserves_automatic_sources_and_pins(
    tmp_path,
):
    from tests.test_fleetsharing_timing_publisher import anchor, source, stage
    from tests.test_fleetsharing_worker import DATE
    from wingman.fleetsharing import protocol as p

    automatic = s.AutomaticState(
        pending=s.PendingAutomatic(
            p.AutomaticCommand(DEVICE.device_id, DATE, False, 0, 0),
            True,
        )
    )
    original = replace(
        PAIRED_STATE,
        device_id=DEVICE.device_id.upper(),
        last_revision=p.INT4_MAX,
        automatic=automatic,
        pending_source_commands=(
            p.StartSource(DEVICE.device_id, 1, DEVICE.device_id, DATE),
        ),
    )
    worker, client, store, mono = file_rig(tmp_path, original, enabled=True)
    context = worker._timing_context
    anchor(context, a=1000, r=1000)
    assert stage(context, source(m=1000, x=999)) is not None
    pins = context._publisher
    drive(worker, mono, 5)
    saved = s.load(store.path)
    assert client.recoveries == 1
    assert saved.automatic == original.automatic
    assert saved.pending_source_commands == original.pending_source_commands
    assert worker._authenticated_device.lower() == original.device_id.lower()
    assert worker._timing_context is context and context._publisher is pins
    assert worker.stop() and worker.start()
    worker.iterate_once()
    assert context._publisher is pins
    assert worker.stop()


def test_known_negative_pair_poll_knowledge_does_not_survive_same_worker_restart(
    tmp_path,
):
    from wingman.fleetsharing.client import FleetRelayError

    worker, client, store, mono = file_rig(tmp_path, s.EMPTY)
    worker.request_pairing(configured_origin="https://relay.test")
    client.errors["complete_pairing"] = FleetRelayError(
        409, "not_completable", "pending"
    )
    drive(worker, mono, 3)
    pending = s.load(store.path).pending_pairing
    assert pending.completion_attempted
    assert worker.stop() and worker.start()
    client.errors.clear()
    drive(worker, mono, 12)
    assert [kind for kind, _, _ in client.calls].count("complete_pairing") == 1
    assert any(kind == "begin_recovery" for kind, _, _ in client.calls)
    assert s.load(store.path).pending_pairing == pending
    assert worker.stop()


@pytest.mark.parametrize("failure", ["open", "read", "disappeared"])
def test_real_file_read_failures_never_initialize_or_access_keys(
    tmp_path, monkeypatch, failure
):
    from contextlib import contextmanager

    worker, client, store, mono = file_rig(tmp_path)
    original = store.path.read_bytes()
    open_file = type(store.path).open

    @contextmanager
    def failed_read(path, *args, **kwargs):
        if path != store.path:
            with open_file(path, *args, **kwargs) as stream:
                yield stream
            return
        if failure == "open":
            raise PermissionError("private open failure")
        if failure == "disappeared":
            raise FileNotFoundError("vanished after stat")
        with open_file(path, *args, **kwargs) as stream:

            def read(_size):
                raise OSError("private read failure")

            monkeypatch.setattr(stream, "read", read)
            yield stream

    def forbidden(*args):
        pytest.fail("key access during failed load")

    worker._generate_private_key = worker._unwrap_private_key = forbidden
    monkeypatch.setattr(type(store.path), "open", failed_read)
    worker.request_pairing(mode="fresh", configured_origin="https://other.test")
    drive(worker, mono, 5)
    assert worker.status().detail == "state_load_failed"
    assert worker._state is None and not store.saves and not client.calls
    monkeypatch.setattr(type(store.path), "open", open_file)
    assert store.path.read_bytes() == original


def test_real_begin_retry_keeps_request_time_and_proof_but_refreshes_attempt(tmp_path):
    from tests.test_fleetsharing_client import (
        Response,
        framing_headers,
        request_binding,
    )
    from tests.test_fleetsharing_worker import EXPIRY, TOKEN
    from wingman.fleetsharing.client import FleetRelayClient

    worker, _, store, mono = file_rig(
        tmp_path, s.replace_session(PAIRED_STATE, None), enabled=True
    )
    requests = []

    def transport(request, timeout):
        requests.append(request)
        saved = s.load(store.path).pending_recovery
        assert json.loads(request.data)["request_id"] == saved.request_id
        if len(requests) == 1:
            return Response(b"not JSON", framing_headers(request_binding(request)))
        body = {
            "protocol": 2,
            "challenge_id": DEVICE.device_id,
            "request_id": saved.request_id,
            "nonce": TOKEN,
            "expires_at": EXPIRY,
        }
        return Response(
            json.dumps(body).encode(), framing_headers(request_binding(request))
        )

    worker._client_factory = lambda origin: FleetRelayClient(
        origin, transport=transport
    )
    drive(worker, mono, 5)
    assert len(requests) == 2
    assert requests[0].data == requests[1].data
    headers = [
        dict((k.lower(), v) for k, v in request.header_items()) for request in requests
    ]
    assert headers[0]["x-fleet-attempt"] != headers[1]["x-fleet-attempt"]
    assert s.load(store.path).pending_recovery.challenge


def test_pairing_url_atomic_failure_never_exposes_browser_url_or_completes(
    tmp_path, monkeypatch
):
    worker, client, store, mono = file_rig(tmp_path, s.EMPTY)
    write = s.atomicio.write_atomic
    statuses = []
    worker.subscribe_status(statuses.append)

    def fail_url(path, data):
        if json.loads(data)["pending_pairing"]["pairing_id"] is not None:
            raise OSError("admission write failed")
        write(path, data)

    monkeypatch.setattr(s.atomicio, "write_atomic", fail_url)
    capabilities = ["shared-source-v1", "combat-v2"]
    assert worker.request_pairing(
        configured_origin="https://relay.test", requested_capabilities=capabilities
    )
    capabilities.clear()
    drive(worker, mono, 5)
    saved = s.load(store.path).pending_pairing
    assert saved.requested_capabilities == ("shared-source-v1", "combat-v2")
    assert saved.pairing_id is None
    assert all(value.approval_url is None for value in statuses)
    assert client.pairings and all(
        v[3] == saved.requested_capabilities for v in client.pairings.values()
    )
    assert not any(kind == "complete_pairing" for kind, _, _ in client.calls)


@pytest.mark.parametrize(
    "boundary,revision", [("save", 1), ("unwrap", 0), ("client", 0)]
)
def test_nonsnapshot_preparation_barriers_are_outside_lock_and_cannot_send(
    tmp_path, boundary, revision
):
    worker, client, store, _ = file_rig(tmp_path, enabled=True)
    if boundary == "save":

        def save(value):
            store.save(value)
            worker.request_participation(False)

        worker._save_state = save
    elif boundary == "unwrap":
        unwrap = worker._unwrap_private_key

        def key(blob):
            value = unwrap(blob)
            worker.request_participation(False)
            return value

        worker._unwrap_private_key = key
    else:

        def factory(origin):
            worker.request_participation(False)
            return client

        worker._client_factory = factory
    worker.iterate_once()
    assert not client.calls
    assert s.load(store.path).last_revision == revision
    assert worker.status().participation == "queued"
    assert worker._scheduler.deadlines["read"] == 0


def test_matching_archive_choice_settles_observation_never_own_commit(tmp_path):
    from wingman.fleetsharing import protocol as p

    worker, client, store, mono = file_rig(tmp_path, None)
    original = legacy_file(store)
    client.device = replace(DEVICE, participation=p.Participation(False, 17))
    worker.resume_pending()
    drive(worker, mono, 12)
    saved = s.load(store.path)
    assert saved.cutover.original == original
    assert (
        dict((v.selector, v.status) for v in saved.cutover.outcomes)["participation"]
        == "observed_choice"
    )
    assert worker.status().participation == "observed_choice"
    assert not client.participation_calls


def test_client_without_logical_start_cannot_acknowledge_or_consume_bucket(tmp_path):
    worker, client, store, _ = file_rig(tmp_path, enabled=True)
    client.fetch_device = lambda **args: DEVICE
    worker.iterate_once()
    assert s.load(store.path).last_revision == 1
    assert s.load(store.path).device_id is None
    assert worker._scheduler.deadlines["read"] == 0
    assert worker._authenticated_device is None


def test_archive_observation_projection_cannot_overwrite_new_queued_choice(tmp_path):
    from wingman.fleetsharing import protocol as p

    worker, client, store, mono = file_rig(tmp_path, None)
    legacy_file(store)
    client.device = replace(DEVICE, participation=p.Participation(False, 17))
    update = worker._update_status
    queued = []

    def race(**changes):
        if changes.get("participation") == "observed_choice" and not queued:
            queued.append(worker.request_participation(True))
        update(**changes)

    worker._update_status = race
    worker.resume_pending()
    for _ in range(12):
        drive(worker, mono, 1)
        if queued:
            break
    assert queued
    assert worker.status().participation == "queued"
    assert worker.status().participation_intent_id == queued[0]


def test_genuine_absence_is_empty_until_explicit_initial_pairing(tmp_path):
    worker, client, store, mono = file_rig(tmp_path, None)
    worker.resume_pending()
    drive(worker, mono, 4)
    assert worker._state == s.EMPTY and not store.path.exists()
    assert not client.calls and not store.saves
    assert worker.request_pairing(configured_origin="https://relay.test")
    worker.iterate_once()
    saved = s.load(store.path)
    assert saved.identity and saved.pending_pairing.pairing_id


def test_archived_evidence_refuses_fresh_origin_before_generating_key(tmp_path):
    worker, client, store, _ = file_rig(tmp_path, None)
    original = legacy_file(store)
    generated = []
    worker._generate_private_key = lambda: generated.append(True)
    worker.request_pairing(mode="fresh", configured_origin="https://other.test")
    worker.iterate_once()
    assert generated == [] and not client.calls
    assert all(
        value.identity == PAIRED_STATE.identity
        and value.relay_origin == PAIRED_STATE.relay_origin
        for value in store.saves
    )
    assert worker.status().pairing == "rejected"
    assert s.load(store.path).cutover.original == original


def test_failed_actual_attempt_charges_client_return_not_error_presentation(tmp_path):
    from wingman.fleetsharing.client import FleetRelayError

    worker, client, _, mono = file_rig(tmp_path, enabled=True)
    mono[0] = 10.0
    client.errors["fetch_device"] = FleetRelayError(503, "service_unavailable", "down")
    client.latency = lambda: mono.__setitem__(0, 10.2)
    relay_error = worker._relay_error

    def present(work, exc, fence):
        relay_error(work, exc, fence)
        mono[0] = 10.3

    worker._relay_error = present
    worker.iterate_once()
    assert worker._scheduler.deadlines["read"] == 10.7
    assert worker._scheduler.retry_at["device"] == 11.2


def test_coarse_pairing_conflict_does_not_restore_poll_permission(tmp_path):
    from wingman.fleetsharing.client import FleetRelayError

    worker, client, store, mono = file_rig(tmp_path, s.EMPTY)
    worker.request_pairing(configured_origin="https://relay.test")
    client.errors["complete_pairing"] = FleetRelayError(409, "conflict", "coarse")
    drive(worker, mono, 12)
    saved = s.load(store.path)
    assert saved.pending_pairing.completion_attempted
    assert saved.auth_pause is None
    assert [kind for kind, _, _ in client.calls].count("complete_pairing") == 1
    assert any(kind == "begin_recovery" for kind, _, _ in client.calls)
    assert len(client.pair_keys) == 1


@pytest.mark.parametrize("operation", ["device", "recovery"])
@pytest.mark.parametrize("invalidate", ["pairing", "stop"])
def test_obsolete_identity_guard_cannot_latch_after_response_check_gap(
    tmp_path, operation, invalidate
):
    original = replace(PAIRED_STATE, device_id=DEVICE.device_id)
    if operation == "recovery":
        original = s.replace_session(original, None)
    worker, client, store, mono = file_rig(tmp_path, original, enabled=True)
    client.device = replace(DEVICE, device_id="ffffffff-ffff-ffff-ffff-ffffffffffff")
    guard = worker._check_device_identity
    crossed = []

    def gap(*args, **kwargs):
        crossed.append(True)
        if invalidate == "pairing":
            assert worker.request_pairing(mode="upgrade")
        else:
            assert worker.stop()
        return guard(*args, **kwargs)

    worker._check_device_identity = gap
    for _ in range(6):
        drive(worker, mono, 1)
        if crossed:
            break
    assert crossed
    assert not worker._identity_mismatch
    assert s.load(store.path).device_id == original.device_id
    assert s.load(store.path).session_id == original.session_id
    assert worker.status().detail != "identity_mismatch"
    if invalidate == "pairing":
        assert worker.status().pairing == "queued"
    assert any(
        kind == ("fetch_device" if operation == "device" else "complete_recovery")
        for kind, _, _ in client.calls
    )


def test_fresh_admission_postsave_off_keeps_its_action_and_does_not_readmit(tmp_path):
    action = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    original = replace(PAIRED_STATE, auth_pause=s.AuthPause("device_revoked"))
    worker, client, store, mono = file_rig(tmp_path, original)
    generated, committed, statuses = [], [], []
    worker.subscribe_status(statuses.append)

    def generate():
        generated.append(True)
        return b"\x01" * 32

    def save(value):
        store.save(value)
        if value.pending_pairing is not None and not committed:
            committed.append(value)
            worker.request_participation(False)

    worker._generate_private_key = generate
    worker._save_state = save
    assert worker.request_pairing(
        mode="fresh", configured_origin="https://relay.test", action_id=action
    )
    worker.iterate_once()
    assert s.load(store.path) == committed[0]
    assert worker._pairing_action_id == action
    assert "pairing" not in worker._commands
    for _ in range(6):
        drive(worker, mono, 1)
        if worker.status().approval_url:
            break
    assert generated == [True]
    assert len(client.pair_keys) == 1
    assert worker.status().approval_url == "https://relay.test/approve"
    assert worker.status().pairing_action_id == action
    assert not any(status.pairing == "rejected" for status in statuses)
    assert all(value.identity == committed[0].identity for value in store.saves)


def test_committed_admission_does_not_drop_or_reassociate_newer_pairing(tmp_path):
    old_action = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    new_action = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    rich = ("shared-source-v1", "combat-v2")
    original = replace(PAIRED_STATE, auth_pause=s.AuthPause("device_revoked"))
    worker, client, store, mono = file_rig(tmp_path, original)
    committed, statuses = [], []
    worker.subscribe_status(statuses.append)

    def save(value):
        store.save(value)
        if value.pending_pairing is not None and not committed:
            committed.append(value)
            assert worker.request_pairing(
                mode="upgrade", action_id=new_action, requested_capabilities=rich
            )

    worker._save_state = save
    worker.request_pairing(
        mode="fresh", configured_origin="https://relay.test", action_id=old_action
    )
    worker.iterate_once()
    assert s.load(store.path) == committed[0]
    assert worker._pairing_action_id == old_action
    assert worker._commands["pairing"].payload[2] == new_action
    assert worker.status().pairing_action_id == new_action
    for _ in range(6):
        drive(worker, mono, 1)
        if worker.status().approval_url:
            break
    assert len(client.pair_keys) == 1
    assert s.load(store.path).pending_pairing.requested_capabilities == rich
    assert worker.status().pairing_action_id == new_action
    assert worker.status().approval_url == "https://relay.test/approve"
    assert all(
        status.pairing_action_id == new_action
        for status in statuses
        if status.approval_url
    )


def test_last_signed_revision_401_preserves_exhausted_floor_until_recovery_commit(
    tmp_path, monkeypatch
):
    from wingman.fleetsharing import protocol as p
    from wingman.fleetsharing.client import FleetRelayError

    original = replace(
        PAIRED_STATE, last_revision=p.INT4_MAX - 1, device_id=DEVICE.device_id
    )
    worker, client, store, mono = file_rig(tmp_path, original, enabled=True)
    client.errors["fetch_device"] = FleetRelayError(
        401, "unauthorized", "last revision"
    )
    write = s.atomicio.write_atomic

    def fail_replacement(path, data):
        # Allow the old buggy 401->None write: only a recovered session fails.
        if json.loads(data)["session_id"] not in (None, original.session_id):
            raise OSError("replacement session write failed")
        write(path, data)

    monkeypatch.setattr(s.atomicio, "write_atomic", fail_replacement)
    for _ in range(12):
        drive(worker, mono, 1)
        if client.recoveries:
            break
    assert client.recoveries == 1
    assert client.calls[0][0] == "fetch_device" and client.calls[0][2] == p.INT4_MAX
    saved = s.load(store.path)
    assert (saved.session_id, saved.last_revision) == (original.session_id, p.INT4_MAX)
    assert saved.pending_recovery.completion_attempted
    assert worker.stop()
    replacement = _worker(
        client, store=store, timing_context=worker._timing_context, utc_clock=client.utc
    )
    drive(replacement, mono, 2)
    saved = s.load(store.path)
    assert (saved.session_id, saved.last_revision) == (original.session_id, p.INT4_MAX)
    assert [revision for _, _, revision in client.calls if revision is not None] == [
        p.INT4_MAX
    ]
    monkeypatch.setattr(s.atomicio, "write_atomic", write)
    client.errors.clear()
    for _ in range(12):
        drive(replacement, mono, 1)
        if s.load(store.path).session_id != original.session_id:
            break
    saved = s.load(store.path)
    assert saved.session_id is not None and saved.session_id != original.session_id
    assert saved.last_revision == 0 and saved.identity == original.identity


def test_unfulfilled_rich_pairing_survives_recovery_and_parks_across_file_restart(
    tmp_path,
):
    rich = ("shared-source-v1", "combat-v2")
    worker, client, store, mono = file_rig(tmp_path)
    statuses = []
    worker.subscribe_status(statuses.append)
    client.precommit_loss.add("complete_pairing")
    assert worker.request_pairing(mode="upgrade", requested_capabilities=rich)
    for _ in range(12):
        drive(worker, mono, 1)
        if client.recoveries:
            break
    assert client.recoveries == 1
    attempted = next(
        value.pending_pairing
        for value in store.saves
        if value.pending_pairing and value.pending_pairing.completion_attempted
    )
    assert attempted.requested_capabilities == rich
    saved = s.load(store.path)
    assert saved.pending_pairing == attempted
    assert saved.approved_capabilities == ("shared-source-v1",)
    assert saved.session_id and saved.session_id != PAIRED_STATE.session_id
    assert not any(status.pairing == "acknowledged" for status in statuses)
    drive(worker, mono, 20)
    assert worker.status().pairing == "unresolved_approval"
    assert worker.status().detail == "unresolved_approval"
    calls = len(client.calls)
    drive(worker, mono, 100)
    assert len(client.calls) == calls
    assert (
        worker._iterate()[0] == 15.0
    )  # Parked intent alone is not an active work loop.
    assert worker.stop()
    replacement = _worker(
        client,
        store=store,
        timing_context=worker._timing_context,
        utc_clock=client.utc,
        sharing_enabled=lambda: False,
    )
    replacement.subscribe_status(statuses.append)
    replacement.resume_pending()
    drive(replacement, mono, 20)
    assert s.load(store.path).pending_pairing == attempted
    assert (
        client.recoveries == 2
    )  # One bounded fresh identity probe after file restart.
    calls = len(client.calls)
    drive(replacement, mono, 100)
    assert len(client.calls) == calls
    assert [kind for kind, _, _ in client.calls].count("complete_pairing") == 1
    assert not any(status.pairing == "acknowledged" for status in statuses)
    assert replacement.status().pairing == "unresolved_approval"
    flagged = next(
        i for i, value in enumerate(store.saves) if value.pending_pairing == attempted
    )
    assert all(value.pending_pairing == attempted for value in store.saves[flagged:])
    assert replacement.stop() and replacement.start()
    drive(replacement, mono, 20)
    assert len(client.calls) == calls
    assert replacement.stop()


def test_fulfilled_rich_pairing_recovery_can_acknowledge_actual_approvals(tmp_path):
    rich = ("shared-source-v1", "combat-v2")
    worker, client, store, mono = file_rig(tmp_path)
    statuses = []
    worker.subscribe_status(statuses.append)
    client.loss.add("complete_pairing")  # The registration/approval committed.
    worker.request_pairing(mode="upgrade", requested_capabilities=rich)
    drive(worker, mono, 16)
    saved = s.load(store.path)
    assert client.recoveries == 1
    assert saved.pending_pairing is None
    assert saved.approved_capabilities == rich
    assert worker.status().pairing == "acknowledged"
    assert not any(status.pairing == "unresolved_approval" for status in statuses)
    assert [kind for kind, _, _ in client.calls].count("complete_pairing") == 1
    calls = len(client.calls)
    drive(worker, mono, 100)
    assert len(client.calls) == calls


# These execute altered copies in memory, never mutate checked-out production.
_MUTANTS = [
    (
        "archive_inhibit",
        [
            (
                "    def _archived_choice(self, state=None):\n",
                "    def _archived_choice(self, state=None):\n        return None\n",
            )
        ],
        "test_archived_off_bootstraps_once_without_telemetry_and_inhibits_current_on",
    ),
    (
        "attempt_write",
        [
            (
                "                            completion_attempted=True,",
                "                            completion_attempted=False,",
            )
        ],
        "test_real_recovery_transport_observes_durable_attempt_before_http",
    ),
    (
        "consumed_one_use",
        [("if expired or pending.completion_attempted:", "if expired:")],
        "test_crash_after_recovery_completion_never_replays_consumed_challenge",
    ),
    (
        "identity_rebind",
        [
            (
                "if expected is not None and expected.lower() != device_id.lower():",
                "if False:",
            )
        ],
        "test_authenticated_device_mismatch_cannot_rebind_saved_identity",
    ),
    (
        "wrong_clock",
        [("self._clock = timing_context._clock", "self._clock = lambda: 0.0")],
        "test_logical_start_excludes_signing_and_completion_pacing_survives_restart",
    ),
    (
        "new_scheduler",
        [
            (
                "self._scheduler = timing_context._scheduler",
                "self._scheduler = type(timing_context._scheduler)()",
            )
        ],
        "test_logical_start_excludes_signing_and_completion_pacing_survives_restart",
    ),
    (
        "pre_client_start",
        [
            (
                "        started = receipt = None",
                "        started = receipt = None\n        selected_at = self._clock()",
            ),
            (
                "                started = self._clock()",
                "                started = selected_at",
            ),
        ],
        "test_logical_start_excludes_signing_and_completion_pacing_survives_restart",
    ),
    (
        "retained_negative_poll",
        [
            (
                "    def _reset_session(self):\n        # Only a typed negative from this live attempt permits another poll.\n        self._pairing_pollable = None",
                "    def _reset_session(self):",
            )
        ],
        "test_known_negative_pair_poll_knowledge_does_not_survive_same_worker_restart",
    ),
]


_REVIEW_MUTANTS = [
    (
        "obsolete_identity_latch",
        [
            (
                "    def _check_device_identity(self, device_id, fence, work):\n        with self._lock:\n            self._check_locked(fence, work=work)",
                "    def _check_device_identity(self, device_id, fence, work):\n        with self._lock:",
            )
        ],
        "test_obsolete_identity_guard_cannot_latch_after_response_check_gap",
        {"operation": "recovery", "invalidate": "pairing"},
    ),
    (
        "lost_committed_action",
        [
            (
                "            if self._state is candidate:",
                "            if self._state is candidate and self._fence().participation == fence.participation:",
            )
        ],
        "test_fresh_admission_postsave_off_keeps_its_action_and_does_not_readmit",
        {},
    ),
    (
        "last_401_floor_reset",
        [
            (
                "            if self._state.last_revision < p.INT4_MAX:",
                "            if True:",
            )
        ],
        "test_last_signed_revision_401_preserves_exhausted_floor_until_recovery_commit",
        {},
    ),
    (
        "unfulfilled_pairing_discard",
        [
            (
                "                pending_pairing=unfulfilled,",
                "                pending_pairing=None,",
            )
        ],
        "test_unfulfilled_rich_pairing_survives_recovery_and_parks_across_file_restart",
        {},
    ),
    (
        "unfulfilled_pairing_spin",
        [
            (
                "            self._parked_pairing = unfulfilled",
                "            self._parked_pairing = None",
            )
        ],
        "test_unfulfilled_rich_pairing_survives_recovery_and_parks_across_file_restart",
        {},
    ),
]


@pytest.mark.parametrize(
    "name,replacements,test,arguments",
    [(*case, {}) for case in _MUTANTS] + _REVIEW_MUTANTS,
    ids=[v[0] for v in (*_MUTANTS, *_REVIEW_MUTANTS)],
)
def test_a_regressions_kill_in_memory_worker_mutants(
    tmp_path, monkeypatch, name, replacements, test, arguments
):
    import inspect
    import sys
    from pathlib import Path
    from types import ModuleType

    from wingman.fleetsharing import worker as production

    source = Path(production.__file__).read_text(encoding="utf-8")
    for old, new in replacements:
        assert source.count(old) == 1, name
        source = source.replace(old, new)
    mutant = ModuleType("wingman.fleetsharing._worker_state4_mutant")
    monkeypatch.setitem(sys.modules, mutant.__name__, mutant)
    exec(compile(source, production.__file__, "exec"), mutant.__dict__)
    monkeypatch.setitem(
        _worker.__globals__, "FleetSharingWorker", mutant.FleetSharingWorker
    )
    regression = globals()[test]
    kwargs = {"tmp_path": tmp_path, **arguments}
    if "monkeypatch" in inspect.signature(regression).parameters:
        kwargs["monkeypatch"] = monkeypatch
    with pytest.raises((AssertionError, pytest.fail.Exception)):
        regression(**kwargs)
