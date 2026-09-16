"""Actual crypto primitives consume deterministic shared v2 wire vectors."""

import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.serialization import load_der_public_key

from wingman.fleetsharing import crypto
from wingman.fleetsharing import protocol as p

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fleet-api-v2.json"
FIXTURE_HASH = "e1303bbe8a04f4595611e9555befc8d14d2cdfba6e72c8413b1e1db71d737d06"
FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _b64url_decode(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def test_fixture_hash_is_pinned():
    assert hashlib.sha256(FIXTURE_PATH.read_bytes()).hexdigest() == FIXTURE_HASH


def test_signed_request_binding_golden_and_each_canonical_field_mutation():
    vector = FIXTURE["signed_request"]
    private_key = bytes.fromhex(FIXTURE["private_key_hex"])
    public_key = load_der_public_key(crypto.public_key_spki(private_key))
    assert (
        hashlib.sha256(vector["body_utf8"].encode()).hexdigest()
        == vector["body_sha256"]
    )
    fields = {
        key: vector[key]
        for key in (
            "protocol",
            "method",
            "path",
            "session_id",
            "issued_at",
            "revision",
            "body_sha256",
        )
    }
    canonical = crypto.canonical_fleet_request(**fields)
    assert canonical == vector["canonical_text"].encode("utf-8")
    assert crypto.sign_request(private_key, canonical) == vector["signature_b64url"]
    assert p.signed_request_binding(canonical) == vector["request_binding"]
    public_key.verify(_b64url_decode(vector["signature_b64url"]), canonical)
    withdrawal = p.parse_combat_put(p.decode_json(vector["body_utf8"].encode()))
    assert withdrawal.rows == () and withdrawal.sampled_at_ms == 0
    for mutation in (
        {"method": "GET"},
        {"path": "/api/fleet/v2/catalogue"},
        {"session_id": "B" * 43},
        {"issued_at": "2026-01-01T00:00:00Z"},
        {"revision": 8},
        {"body_sha256": "0" * 64},
    ):
        changed = crypto.canonical_fleet_request(**{**fields, **mutation})
        assert p.signed_request_binding(changed) != vector["request_binding"]
    assert p.signed_request_binding(canonical + b"\n") != vector["request_binding"]
    assert crypto.snapshot_request_binding(canonical) != vector["request_binding"]


@pytest.mark.parametrize(
    "name", ["pairing_complete", "recovery_begin", "recovery_complete"]
)
def test_pre_session_vectors_use_actual_proofs_and_binding(name):
    vector = FIXTURE[name]
    private_key = bytes.fromhex(FIXTURE["private_key_hex"])
    spki = crypto.public_key_spki(private_key)
    assert crypto.public_key_spki_b64url(spki) == FIXTURE["public_key_spki_b64url"]
    assert (
        p.public_key_spki_b64url(FIXTURE["public_key_spki_b64url"])
        == FIXTURE["public_key_spki_b64url"]
    )
    public_key = load_der_public_key(spki)
    assert (
        hashlib.sha256(vector["body_utf8"].encode()).hexdigest()
        == vector["body_sha256"]
    )
    if name == "pairing_complete":
        preimage = crypto.pairing_challenge_preimage(vector["pairing_id"])
    elif name == "recovery_begin":
        preimage = crypto.recovery_initiation_preimage(
            vector["origin"], vector["request_id"], vector["issued_at"], spki
        )
    else:
        preimage = crypto.recovery_challenge_preimage(
            vector["origin"], vector["challenge_id"], vector["nonce"], spki
        )
    assert preimage == vector["preimage_utf8"].encode("utf-8")
    assert crypto.sign_request(private_key, preimage) == vector["signature_b64url"]
    assert p.signature(vector["signature_b64url"]) == vector["signature_b64url"]
    fields = {
        "pairing_complete": "completion_signature",
        "recovery_begin": "public_key_spki_b64url request_id issued_at initiation_signature",
        "recovery_complete": "nonce recovery_signature",
    }
    body = p.envelope(p.decode_json(vector["body_utf8"].encode()), fields[name])
    if name == "recovery_begin":
        p.public_key_spki_b64url(body["public_key_spki_b64url"])
        p.token(body["request_id"])
        p.utc_date(body["issued_at"])
    elif name == "recovery_complete":
        p.token(body["nonce"])
    signature_field = {
        "pairing_complete": "completion_signature",
        "recovery_begin": "initiation_signature",
        "recovery_complete": "recovery_signature",
    }[name]
    assert p.signature(body[signature_field]) == vector["signature_b64url"]
    public_key.verify(_b64url_decode(vector["signature_b64url"]), preimage)
    assert (
        p.pre_session_request_binding(
            vector["origin"],
            vector["path"],
            vector["attempt"],
            vector["body_utf8"].encode(),
        )
        == vector["request_binding"]
    )


@pytest.mark.parametrize(
    ("key", "value", "raises"),
    [
        ("path", FIXTURE["invalid"]["escaped_path"], True),
        ("attempt", "A" * 42, True),
        ("body", b"{}", False),
        ("attempt", "A" * 43, False),
        ("origin", "https://other.example", False),
    ],
)
def test_pre_session_binding_rejects_or_changes_on_mutation(key, value, raises):
    vector = FIXTURE["recovery_complete"]
    fields = {
        "origin": vector["origin"],
        "path": vector["path"],
        "attempt_token": vector["attempt"],
        "body": vector["body_utf8"].encode(),
    }
    fields["attempt_token" if key == "attempt" else key] = value
    if raises:
        with pytest.raises(ValueError):
            p.pre_session_request_binding(**fields)
    else:
        assert p.pre_session_request_binding(**fields) != vector["request_binding"]


@pytest.mark.parametrize(
    "vector", FIXTURE["signed_operations"], ids=lambda vector: vector["name"]
)
def test_signed_operation_vectors_bind_real_commands_and_success_codecs(vector):
    fields = {
        key: vector[key]
        for key in (
            "protocol",
            "method",
            "path",
            "session_id",
            "issued_at",
            "revision",
            "body_sha256",
        )
    }
    assert (
        hashlib.sha256(vector["body_utf8"].encode()).hexdigest()
        == fields["body_sha256"]
    )
    canonical = crypto.canonical_fleet_request(**fields)
    assert canonical.decode() == vector["canonical_text"]
    assert p.signed_request_binding(canonical) == vector["request_binding"]
    key = bytes.fromhex(FIXTURE["private_key_hex"])
    assert crypto.sign_request(key, canonical) == vector["signature_b64url"]
    load_der_public_key(crypto.public_key_spki(key)).verify(
        _b64url_decode(vector["signature_b64url"]), canonical
    )
    response = FIXTURE["valid"][vector["response"]]
    if vector["name"] == "combat-get":
        assert vector["body_utf8"] == ""
        assert p.parse_snapshot(response).server_time_ms == 12500
    elif vector["name"] == "automatic-off":
        command = p.parse_automatic_command(p.decode_json(vector["body_utf8"].encode()))
        assert (
            p.parse_automatic_result(response, command).receipt.result.enabled is False
        )
    else:
        command = p.parse_source_command(p.decode_json(vector["body_utf8"].encode()))
        assert p.parse_source_result(response, command).source.state == "ended"


def test_pairing_begin_binding_consumes_real_key_and_capability_fields():
    vector = FIXTURE["pairing_begin"]
    raw = vector["body_utf8"].encode()
    assert hashlib.sha256(raw).hexdigest() == vector["body_sha256"]
    body = p.envelope(
        p.decode_json(raw), "public_key_spki_b64url requested_capabilities"
    )
    assert p.capabilities(body["requested_capabilities"]) == (
        "shared-source-v1",
        "combat-v2",
    )
    spki = crypto.public_key_spki(bytes.fromhex(FIXTURE["private_key_hex"]))
    assert p.public_key_spki_b64url(
        body["public_key_spki_b64url"]
    ) == crypto.public_key_spki_b64url(spki)
    assert (
        p.pre_session_request_binding(
            vector["origin"], vector["path"], vector["attempt"], raw
        )
        == vector["request_binding"]
    )
    assert p.parse_pairing_begun(
        FIXTURE["valid"]["pairing_begun"], origin=vector["origin"]
    ).approval_url.startswith(vector["origin"] + "/")


@pytest.mark.parametrize(
    "case", FIXTURE["correlation_vectors"], ids=lambda case: case["name"]
)
def test_shared_correlation_negative_vectors(case):
    vector = FIXTURE[case["operation"]]
    if case["mutation"] == "snapshot-domain":
        canonical = crypto.canonical_fleet_request(
            **{
                key: vector[key]
                for key in (
                    "protocol",
                    "method",
                    "path",
                    "session_id",
                    "issued_at",
                    "revision",
                    "body_sha256",
                )
            }
        )
        actual = crypto.snapshot_request_binding(canonical)
    else:
        fields = {
            "origin": vector["origin"],
            "path": vector["path"],
            "attempt_token": vector["attempt"],
            "body": vector["body_utf8"].encode(),
        }
        key = "attempt_token" if case["mutation"] == "attempt" else case["mutation"]
        fields[key] = case["value"].encode() if key == "body" else case["value"]
        actual = p.pre_session_request_binding(**fields)
    assert (actual == vector["request_binding"]) is case["matches"]


def test_pairing_and_recovery_signatures_reject_wrong_purpose_or_origin():
    spki = crypto.public_key_spki(bytes.fromhex(FIXTURE["private_key_hex"]))
    public_key = load_der_public_key(spki)
    pairing = FIXTURE["pairing_complete"]
    with pytest.raises(InvalidSignature):
        public_key.verify(
            _b64url_decode(pairing["signature_b64url"]),
            crypto.pairing_challenge_preimage("00000000-0000-0000-8000-000000000000"),
        )
    recovery = FIXTURE["recovery_complete"]
    with pytest.raises(InvalidSignature):
        public_key.verify(
            _b64url_decode(recovery["signature_b64url"]),
            crypto.recovery_challenge_preimage(
                "https://other.example",
                recovery["challenge_id"],
                recovery["nonce"],
                spki,
            ),
        )
    with pytest.raises(InvalidSignature):
        public_key.verify(
            _b64url_decode(recovery["signature_b64url"]),
            crypto.pairing_challenge_preimage(recovery["challenge_id"]),
        )
