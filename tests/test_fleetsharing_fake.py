"""Scoped fidelity checks for the worker's offline relay model, not backend tests.

Contracts transcribed from A's fleet-device/participation/source/recovery/pairing,
shared-admission and relay services. Signed wire proof stays in the client tests.
"""

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from test_fleetsharing_worker import (
    CAPS,
    DATE,
    DEVICE,
    KEY,
    NOW,
    TOKEN,
    UUID,
    FakeRelayClient,
)

from wingman.fleetsharing import crypto
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing.client import FleetRelayError
from wingman.fleetsharing.model import PublishRow


def signed(client, operation, **extra):
    client.clock = lambda: 1000 + 2 * len(client.completed)
    return getattr(client, operation)(
        session_id="session-1",
        private_key=KEY,
        revision=len(client.calls) + 1,
        **extra,
    )


def arguments(operation):
    return {
        "acknowledge_capabilities": {"capabilities": CAPS},
        "set_participation": {"enabled": False, "expected_generation": 1},
        "control_source": {"command": p.StopSource(UUID, 0)},
        "publish_snapshot": {"rows": (PublishRow(1, 1, ()),)},
    }.get(operation, {})


@pytest.mark.parametrize(
    "missing",
    [
        "feature_enabled",
        "approved_capabilities",
        "session_approved_capabilities",
        "acknowledged_capabilities",
    ],
)
@pytest.mark.parametrize(
    "operation",
    [
        "acknowledge_capabilities",
        "set_participation",
        "control_source",
        "fetch_sources",
        "fetch_eligibility",
        "publish_snapshot",
        "read_snapshot",
    ],
)
def test_fake_operation_authority_is_not_backfilled(missing, operation):
    device = replace(DEVICE, **{missing: False if missing == "feature_enabled" else ()})
    client = FakeRelayClient(device=device)
    if (
        missing == "acknowledged_capabilities"
        and operation == "acknowledge_capabilities"
    ):
        assert (
            signed(client, operation, **arguments(operation)).acknowledged_capabilities
            == CAPS
        )
    else:
        with pytest.raises(FleetRelayError) as caught:
            signed(client, operation, **arguments(operation))
        assert caught.value.code == (
            "forbidden"
            if missing == "feature_enabled" and operation == "publish_snapshot"
            else "feature_disabled"
            if missing == "feature_enabled"
            else "forbidden"
            if operation in ("publish_snapshot", "read_snapshot", "fetch_eligibility")
            else "capability_required"
        )
        assert (
            not client.controls
            and not client.participation_calls
            and not client.publish_calls
        )


@pytest.mark.parametrize(
    "operation", ["fetch_device", "fetch_catalogue", "renew_session"]
)
def test_fake_metadata_catalogue_renewal_do_not_require_shared_permission(operation):
    client = FakeRelayClient(
        device=replace(
            DEVICE,
            feature_enabled=False,
            approved_capabilities=(),
            session_approved_capabilities=(),
            acknowledged_capabilities=(),
            participation=p.Participation(False, 1),
        )
    )
    assert signed(client, operation) is not None


def test_fake_legacy_pairing_exception_does_not_invent_shared_grants_when_disabled():
    client = FakeRelayClient(
        device=replace(DEVICE, feature_enabled=False), registered=False
    )
    client.clock = lambda: 1000 + 2 * len(client.completed)
    admission = client.begin_pairing(
        crypto.public_key_spki(KEY), requested_capabilities=()
    )
    client.complete_pairing(
        pairing_id=admission.pairing_id,
        challenge=crypto.pairing_challenge_preimage(admission.pairing_id),
        private_key=KEY,
    )
    assert client.device.approved_capabilities == ()
    assert client.device.session_approved_capabilities == ()
    assert client.device.participation == p.Participation(False, 0)
    with pytest.raises(FleetRelayError) as caught:
        client.begin_recovery(private_key=KEY, request_id=TOKEN, issued_at=DATE)
    assert caught.value.code == "feature_disabled" and not client.admissions


def test_fake_participation_off_allows_controls_eligibility_and_empty_withdrawal():
    client = FakeRelayClient(
        device=replace(DEVICE, participation=p.Participation(False, 1))
    )
    assert signed(client, "fetch_eligibility").state == "participation_off"
    assert (
        signed(client, "control_source", command=p.StopSource(UUID, 0)).state == "ended"
    )
    signed(client, "publish_snapshot", rows=())
    for operation in ("publish_snapshot", "read_snapshot"):
        with pytest.raises(FleetRelayError) as caught:
            signed(client, operation, **arguments(operation))
        assert caught.value.code == "forbidden"


def test_fake_unknown_key_allocates_nothing_until_pairing_completion_and_is_one_use():
    client = FakeRelayClient(device=DEVICE)
    other_key = bytes([1]) * 32
    client.clock = lambda: 1000 + 2 * len(client.completed)
    for stage in ("before", "admitted"):
        with pytest.raises(FleetRelayError) as caught:
            client.begin_recovery(
                private_key=other_key, request_id=TOKEN, issued_at=DATE
            )
        assert caught.value.status == 401 and client.challenge is None
        if stage == "before":
            admission = client.begin_pairing(
                crypto.public_key_spki(other_key), requested_capabilities=CAPS
            )
    completion = dict(
        pairing_id=admission.pairing_id,
        challenge=crypto.pairing_challenge_preimage(admission.pairing_id),
        private_key=other_key,
    )
    client.complete_pairing(**completion)
    with pytest.raises(FleetRelayError) as caught:
        client.complete_pairing(**completion)
    assert caught.value.status == 409
    assert client.begin_recovery(
        private_key=other_key, request_id=TOKEN, issued_at=DATE
    )


def test_fake_recovery_admission_dedup_binding_and_consumption():
    client = FakeRelayClient(device=DEVICE)
    client.clock = lambda: 1000 + 2 * len(client.completed)
    args = dict(private_key=KEY, request_id=TOKEN, issued_at=DATE)
    challenge = client.begin_recovery(**args)
    assert client.begin_recovery(**args) == challenge
    with pytest.raises(FleetRelayError):
        client.begin_recovery(**{**args, "issued_at": "2026-09-07T12:00:01.000Z"})
    client.complete_recovery(private_key=KEY, challenge=challenge)
    with pytest.raises(FleetRelayError):
        client.begin_recovery(**args)
    with pytest.raises(FleetRelayError):
        client.complete_recovery(private_key=KEY, challenge=challenge)


def test_fake_matching_start_is_idempotent_changed_ended_and_stale_cas_refuse():
    client = FakeRelayClient(device=DEVICE)
    start = p.StartSource(UUID, 1, UUID, DATE)
    view = signed(client, "control_source", command=start)
    assert signed(client, "control_source", command=start) == view
    with pytest.raises(FleetRelayError) as caught:
        signed(
            client,
            "control_source",
            command=replace(start, intent_created_at="2026-09-07T11:59:59.000Z"),
        )
    assert caught.value.code == "conflict"
    with pytest.raises(FleetRelayError):
        signed(client, "control_source", command=p.StopSource(UUID, 0))
    ended = signed(client, "control_source", command=p.StopSource(UUID, 1))
    assert signed(client, "control_source", command=p.StopSource(UUID, 2)) == ended
    with pytest.raises(FleetRelayError):
        signed(client, "control_source", command=start)
    other_id = str(uuid4())
    signed(client, "control_source", command=p.StopSource(other_id, 0))
    with pytest.raises(FleetRelayError):
        signed(client, "control_source", command=replace(start, source_id=other_id))
    client.utc = lambda: NOW + timedelta(seconds=60)
    with pytest.raises(FleetRelayError) as caught:
        signed(client, "control_source", command=replace(start, source_id=str(uuid4())))
    assert caught.value.code == "invalid_intent"


def test_fake_upgrade_does_not_backfill_old_session_ceiling():
    client = FakeRelayClient(
        device=replace(
            DEVICE,
            approved_capabilities=(),
            session_approved_capabilities=(),
            acknowledged_capabilities=(),
        )
    )
    client.clock = lambda: 1000 + 2 * len(client.completed)
    admission = client.begin_pairing(
        crypto.public_key_spki(KEY), requested_capabilities=CAPS
    )
    client.complete_pairing(
        pairing_id=admission.pairing_id,
        challenge=crypto.pairing_challenge_preimage(admission.pairing_id),
        private_key=KEY,
    )
    old = signed(client, "fetch_device")
    assert old.approved_capabilities == CAPS and old.session_approved_capabilities == ()
    with pytest.raises(FleetRelayError) as caught:
        signed(client, "acknowledge_capabilities", capabilities=CAPS)
    assert caught.value.code == "capability_required"


def test_fake_legacy_pairing_limits_new_session_to_request_not_existing_device_grant():
    client = FakeRelayClient(device=DEVICE)
    client.clock = lambda: 1000 + 2 * len(client.completed)
    admission = client.begin_pairing(
        crypto.public_key_spki(KEY), requested_capabilities=()
    )
    paired = client.complete_pairing(
        pairing_id=admission.pairing_id,
        challenge=crypto.pairing_challenge_preimage(admission.pairing_id),
        private_key=KEY,
    )
    device = client.fetch_device(
        session_id=paired.session_id, private_key=KEY, revision=1
    )
    assert device.approved_capabilities == CAPS
    assert device.session_approved_capabilities == ()
    with pytest.raises(FleetRelayError) as caught:
        client.acknowledge_capabilities(
            session_id=paired.session_id,
            private_key=KEY,
            revision=2,
            capabilities=CAPS,
        )
    assert caught.value.code == "capability_required" and caught.value.status == 403
    assert client.device.acknowledged_capabilities == ()

    # Recovery deliberately differs: registered-key proof snapshots the complete
    # device grant, but still requires a fresh session acknowledgement.
    challenge = client.begin_recovery(private_key=KEY, request_id=TOKEN, issued_at=DATE)
    recovered = client.complete_recovery(private_key=KEY, challenge=challenge)
    device = client.fetch_device(
        session_id=recovered.session_id, private_key=KEY, revision=1
    )
    assert device.approved_capabilities == CAPS
    assert device.session_approved_capabilities == CAPS
    assert device.acknowledged_capabilities == ()
    acknowledged = client.acknowledge_capabilities(
        session_id=recovered.session_id,
        private_key=KEY,
        revision=2,
        capabilities=CAPS,
    )
    assert acknowledged.acknowledged_capabilities == CAPS


@pytest.mark.parametrize(
    "operation",
    [
        "begin_pairing",
        "complete_pairing",
        "begin_recovery",
        "complete_recovery",
        "set_participation",
        "start",
        "stop",
    ],
)
@pytest.mark.parametrize("committed", [False, True])
def test_fake_precommit_loss_is_distinct_from_committed_response_loss(
    operation, committed
):
    client = FakeRelayClient(device=DEVICE)
    client.clock = lambda: 1000 + 2 * len(client.completed)
    if operation == "complete_pairing":
        admission = client.begin_pairing(
            crypto.public_key_spki(KEY), requested_capabilities=CAPS
        )
    elif operation == "complete_recovery":
        challenge = client.begin_recovery(
            private_key=KEY, request_id=TOKEN, issued_at=DATE
        )

    def invoke():
        if operation == "begin_pairing":
            return client.begin_pairing(
                crypto.public_key_spki(KEY), requested_capabilities=CAPS
            )
        if operation == "complete_pairing":
            return client.complete_pairing(
                pairing_id=admission.pairing_id,
                challenge=crypto.pairing_challenge_preimage(admission.pairing_id),
                private_key=KEY,
            )
        if operation == "begin_recovery":
            return client.begin_recovery(
                private_key=KEY, request_id=TOKEN, issued_at=DATE
            )
        if operation == "complete_recovery":
            return client.complete_recovery(private_key=KEY, challenge=challenge)
        if operation == "set_participation":
            return signed(client, operation, enabled=False, expected_generation=1)
        command = (
            p.StartSource(UUID, 1, UUID, DATE)
            if operation == "start"
            else p.StopSource(UUID, 0)
        )
        return signed(client, "control_source", command=command)

    failures = client.loss if committed else client.precommit_loss
    failures.add("control_source" if operation in ("start", "stop") else operation)
    with pytest.raises(FleetRelayError) as caught:
        invoke()
    effect = {
        "begin_pairing": bool(client.pairings),
        "complete_pairing": client.device.acknowledged_capabilities != CAPS,
        "begin_recovery": bool(client.admissions),
        "complete_recovery": bool(client.recoveries),
        "set_participation": not client.device.participation.enabled,
        "start": bool(client.source_views),
        "stop": bool(client.source_views),
    }[operation]
    assert caught.value.code == "transport_error"
    assert effect is committed and not failures
