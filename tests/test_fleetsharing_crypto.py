"""Ed25519 signing/key management for the fleet-sharing protocol boundary.

Both fixtures here are authGD's own public test vectors, copied
byte-for-byte from
`/home/tng/workspace/authGD/.claude/worktrees/fleet-telemetry-tracer/tests/fixtures/`
(see each fixture's own `_comment` field). authGD's
`tests/fleet-signature.test.ts` and `tests/fleet-pairing.test.ts` verify
the identical vectors; this file is the Python half of that shared
contract. Every fixture assertion below verifies with `cryptography`
directly against the fixture's own recorded public key -- independent of
whether this module's own sign/verify code is right.
"""

import base64
import json
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_der_public_key

from wingman.fleetsharing import crypto

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class TestFleetSignatureFixture:
    """tests/fixtures/fleet-signature-v1.json."""

    def test_canonical_bytes_match_the_authgd_vector(self):
        fixture = _load_fixture("fleet-signature-v1.json")
        canonical = crypto.canonical_fleet_request(
            protocol=fixture["protocol"],
            method=fixture["method"],
            path=fixture["path"],
            session_id=fixture["session_id"],
            issued_at=fixture["issued_at"],
            revision=fixture["revision"],
            body_sha256=fixture["body_sha256"],
        )
        assert canonical == fixture["canonical_text"].encode("utf-8")

    def test_the_fixture_signature_verifies_against_the_fixture_public_key(self):
        fixture = _load_fixture("fleet-signature-v1.json")
        spki = base64.b64decode(fixture["public_key_spki_b64"])
        public_key = load_der_public_key(spki)
        assert isinstance(public_key, Ed25519PublicKey)
        signature = _b64url_decode(fixture["signature_b64url"])
        canonical = fixture["canonical_text"].encode("utf-8")

        public_key.verify(signature, canonical)  # raises InvalidSignature on failure

    def test_the_fixture_signature_rejects_a_mutated_canonical_text(self):
        fixture = _load_fixture("fleet-signature-v1.json")
        spki = base64.b64decode(fixture["public_key_spki_b64"])
        public_key = load_der_public_key(spki)
        signature = _b64url_decode(fixture["signature_b64url"])
        mutated = fixture["canonical_text"].replace("\n7\n", "\n8\n").encode("utf-8")

        with pytest.raises(InvalidSignature):
            public_key.verify(signature, mutated)


class TestFleetPairingFixture:
    """tests/fixtures/fleet-pairing-v1.json."""

    def test_preimage_matches_the_authgd_vector(self):
        fixture = _load_fixture("fleet-pairing-v1.json")
        preimage = crypto.pairing_challenge_preimage(fixture["pairing_id"])
        assert preimage == fixture["preimage_utf8"].encode("utf-8")
        assert preimage.decode("utf-8") == f"fleet-pairing-v1\n{fixture['pairing_id']}"

    def test_the_fixture_signature_verifies_against_the_fixture_public_key(self):
        fixture = _load_fixture("fleet-pairing-v1.json")
        spki = base64.b64decode(fixture["public_key_spki_b64"])
        public_key = load_der_public_key(spki)
        signature = _b64url_decode(fixture["signature_b64url"])
        preimage = crypto.pairing_challenge_preimage(fixture["pairing_id"])

        public_key.verify(signature, preimage)

    def test_the_fixture_signature_rejects_a_different_pairing_id(self):
        fixture = _load_fixture("fleet-pairing-v1.json")
        spki = base64.b64decode(fixture["public_key_spki_b64"])
        public_key = load_der_public_key(spki)
        signature = _b64url_decode(fixture["signature_b64url"])
        wrong_preimage = crypto.pairing_challenge_preimage(
            "00000000-0000-0000-0000-000000000000"
        )

        with pytest.raises(InvalidSignature):
            public_key.verify(signature, wrong_preimage)


class TestRuntimeGeneratedKeys:
    def test_generate_private_key_returns_32_raw_bytes(self):
        private_key = crypto.generate_private_key()
        assert isinstance(private_key, bytes)
        assert len(private_key) == crypto.RAW_PRIVATE_KEY_BYTES == 32

    def test_generate_private_key_is_not_deterministic(self):
        assert crypto.generate_private_key() != crypto.generate_private_key()

    def test_sign_request_round_trips_against_cryptography_directly(self):
        private_key = crypto.generate_private_key()
        spki = crypto.public_key_spki(private_key)
        public_key = load_der_public_key(spki)
        canonical = crypto.canonical_fleet_request(
            protocol=1,
            method="GET",
            path="/api/fleet/v1/catalogue",
            session_id="session-123",
            issued_at="2026-01-01T00:00:00.000Z",
            revision=1,
            body_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )

        signature_b64url = crypto.sign_request(private_key, canonical)

        assert "=" not in signature_b64url
        public_key.verify(_b64url_decode(signature_b64url), canonical)

    def test_sign_request_signature_rejects_a_mutated_canonical(self):
        private_key = crypto.generate_private_key()
        public_key = load_der_public_key(crypto.public_key_spki(private_key))
        canonical = b"fleet-v1\nGET\n/x\nsess\n2026-01-01T00:00:00.000Z\n1\nabc"

        signature_b64url = crypto.sign_request(private_key, canonical)

        with pytest.raises(InvalidSignature):
            public_key.verify(_b64url_decode(signature_b64url), canonical + b"x")

    def test_sign_pairing_completion_round_trips_against_cryptography_directly(self):
        private_key = crypto.generate_private_key()
        public_key = load_der_public_key(crypto.public_key_spki(private_key))
        pairing_id = "11111111-1111-1111-1111-111111111111"

        signature_b64url = crypto.sign_pairing_completion(private_key, pairing_id)

        assert "=" not in signature_b64url
        public_key.verify(
            _b64url_decode(signature_b64url),
            crypto.pairing_challenge_preimage(pairing_id),
        )

    def test_sign_pairing_completion_rejects_verification_under_a_different_pairing_id(
        self,
    ):
        private_key = crypto.generate_private_key()
        public_key = load_der_public_key(crypto.public_key_spki(private_key))
        signature_b64url = crypto.sign_pairing_completion(private_key, "pairing-a")

        with pytest.raises(InvalidSignature):
            public_key.verify(
                _b64url_decode(signature_b64url),
                crypto.pairing_challenge_preimage("pairing-b"),
            )


class TestCanonicalDevicePublicKey:
    def test_canonical_form_is_padded_standard_base64(self):
        private_key = crypto.generate_private_key()
        spki = crypto.public_key_spki(private_key)

        canonical = crypto.canonical_device_public_key_b64(spki)

        assert canonical == base64.b64encode(spki).decode("ascii")
        # Padded standard alphabet only -- never the base64url alphabet,
        # which is what public_key_spki_b64url below deliberately uses
        # instead for the wire field authGD's pairing route requires.
        assert "-" not in canonical
        assert "_" not in canonical
        assert base64.b64decode(canonical) == spki

    def test_b64url_wire_form_is_unpadded_and_decodes_to_the_same_key(self):
        private_key = crypto.generate_private_key()
        spki = crypto.public_key_spki(private_key)

        wire_form = crypto.public_key_spki_b64url(spki)

        assert "=" not in wire_form
        assert base64.urlsafe_b64decode(wire_form + "=" * (-len(wire_form) % 4)) == spki

    def test_ed25519_spki_der_is_exactly_44_bytes(self):
        """Pins the exact size authGD's own route comment relies on
        (`fleet-signature-v1.json`'s public key is the same length)."""
        spki = crypto.public_key_spki(crypto.generate_private_key())
        assert len(spki) == 44
