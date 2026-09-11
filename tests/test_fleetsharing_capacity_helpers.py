"""Small independent byte boundaries for the journal preparation fixture builder."""

import json
from dataclasses import replace

import pytest

from tests import fleetsharing_capacity_helpers as helpers
from tests.test_fleetsharing_worker import DATE, PAIRED_STATE, TOKEN, UUID
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing import state as s

# Transcribed persisted shapes, not the production serializer or the builder.
BASE_DOCUMENT = {
    "version": 3,
    "identity": {
        "protected_private_key_b64": PAIRED_STATE.identity.protected_private_key_b64,
        "public_key_spki_b64": PAIRED_STATE.identity.public_key_spki_b64,
    },
    "relay_origin": "https://relay.test",
    "session_id": "session-1",
    "last_revision": 0,
    "device_id": None,
    "session_expires_at": None,
    "feature_enabled": None,
    "approved_capabilities": None,
    "session_approved_capabilities": None,
    "acknowledged_capabilities": None,
    "observed_participation": None,
    "pending_recovery": None,
    "pending_source_commands": [],
    "pending_pairing": None,
    "pending_participation": None,
    "auth_pause": None,
}
FIRST_STARTS = [
    {
        "operation": "start",
        "source_id": source,
        "character_id": 1,
        "character_link_epoch": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "intent_created_at": "2026-09-07T12:00:00.000Z",
        "expected_generation": 0,
    }
    for source in (
        "00000000-0000-4000-8000-000000000001",
        "00000000-0000-4000-8000-000000000002",
    )
]


@pytest.mark.parametrize("indented", [False, True])
@pytest.mark.parametrize("prefix,delta", [(1, -1), (1, 0), (2, -1), (2, 0)])
def test_start_boundary_keeps_exact_fit_and_refuses_next_byte(indented, prefix, delta):
    # Off-by-one limits, missing array commas, or selecting the wrong prefix
    # change the actual expected journal, not just an implementation count.
    documents = [
        {**BASE_DOCUMENT, "pending_source_commands": FIRST_STARTS[:count]}
        for count in range(3)
    ]
    encoding = {"indent": 2} if indented else {"separators": (",", ":")}
    expected = [json.dumps(doc, **encoding).encode("ascii") for doc in documents]
    limit = len(expected[prefix]) + delta
    last, refused = helpers.start_boundary(PAIRED_STATE, limit=limit, indented=indented)
    wanted = prefix - 1 if delta < 0 else prefix
    assert helpers.fixture_bytes(last, indented=indented) == expected[wanted]
    assert len(helpers.fixture_bytes(last, indented=indented)) <= limit
    assert len(helpers.fixture_bytes(refused, indented=indented)) > limit
    assert refused.pending_source_commands[:-1] == last.pending_source_commands
    assert replace(last, pending_source_commands=()) == PAIRED_STATE


def test_fixture_bytes_preserve_recovery_and_attempted_on_metadata(tmp_path):
    # Dropping a non-default nested field can move the byte boundary and erase
    # the old authority the owner tests are meant to fence.
    state = replace(
        PAIRED_STATE,
        last_revision=9,
        device_id=UUID,
        session_expires_at=DATE,
        feature_enabled=False,
        approved_capabilities=("shared-source-v1",),
        session_approved_capabilities=(),
        acknowledged_capabilities=(),
        observed_participation=p.Participation(True, 7),
        pending_recovery=s.PendingRecovery(
            TOKEN, DATE, p.RecoveryChallenge(UUID, TOKEN, TOKEN, DATE)
        ),
        pending_participation=s.PendingParticipation(UUID, True, 8, True),
        pending_source_commands=(p.StartSource(UUID, 42, UUID, DATE),),
    )
    expected = {
        **BASE_DOCUMENT,
        "last_revision": 9,
        "device_id": UUID,
        "session_expires_at": DATE,
        "feature_enabled": False,
        "approved_capabilities": ["shared-source-v1"],
        "session_approved_capabilities": [],
        "acknowledged_capabilities": [],
        "observed_participation": {"enabled": True, "generation": 7},
        "pending_recovery": {
            "request_id": TOKEN,
            "issued_at": DATE,
            "challenge": {
                "challenge_id": UUID,
                "request_id": TOKEN,
                "nonce": TOKEN,
                "expires_at": DATE,
            },
        },
        "pending_participation": {
            "intent_id": UUID,
            "enabled": True,
            "expected_generation": 8,
            "attempted": True,
        },
        "pending_source_commands": [
            {**FIRST_STARTS[0], "source_id": UUID, "character_id": 42}
        ],
    }
    assert helpers.fixture_bytes(state) == json.dumps(
        expected, separators=(",", ":")
    ).encode("ascii")
    path = tmp_path / "metadata.json"
    path.write_bytes(helpers.fixture_bytes(state, indented=True))
    assert s.load(path) == state
    s.save(path, state)
    assert path.read_bytes() == helpers.fixture_bytes(state, indented=True)


def test_start_boundary_rejects_non_byte_bound_or_unsupported_fixtures():
    # A count-bound result or unsupported text must not masquerade as the byte
    # overflow scenario consumed by the real owner tests.
    with pytest.raises(AssertionError, match="before count"):
        helpers.start_boundary(PAIRED_STATE, limit=1000000)
    with pytest.raises(AssertionError, match="base must fit"):
        helpers.start_boundary(PAIRED_STATE, limit=1)
    with pytest.raises(AssertionError, match="ASCII"):
        helpers.fixture_bytes(replace(PAIRED_STATE, relay_origin="https://é.test"))
    with pytest.raises(AssertionError, match="Start"):
        helpers.fixture_bytes(
            replace(PAIRED_STATE, pending_source_commands=(p.StopSource(UUID, 0),))
        )
