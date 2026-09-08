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
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_der_public_key

from wingman.fleetsharing import crypto

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


INVALID_RECOVERY_SPKI_CASES = (
    "empty",
    "truncated_tag",
    "truncated_envelope",
    "truncated_key",
    "outer_tag",
    "outer_length",
    "algorithm_tag",
    "bitstring_length",
    "unknown_algorithm",
    "x25519",
    "unsupported_curve",
    "oversized",
)


def invalid_recovery_spki(case):
    spki = base64.b64decode(
        _load_fixture("fleet-recovery-v1.json")["public_key_spki_b64"]
    )
    # A real compressed P-256 generator point with an unknown named-curve OID.
    # This 59-byte SPKI reaches cryptography's UnsupportedAlgorithm path within
    # our 90-byte input bound (uncompressed EC SPKI is 91 bytes and cannot).
    unsupported_curve = bytes.fromhex(
        "3039301306072a8648ce3d020106082a8648ce3d03017f032200"
        "036b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296"
    )
    return {
        "empty": b"",
        "truncated_tag": spki[:1],
        "truncated_envelope": spki[:11],
        "truncated_key": spki[:-1],
        "outer_tag": b"\x31" + spki[1:],
        "outer_length": spki[:1] + b"\x29" + spki[2:],
        "algorithm_tag": spki[:2] + b"\x31" + spki[3:],
        "bitstring_length": spki[:10] + b"\x20" + spki[11:],
        "unknown_algorithm": spki[:8] + b"\xff" + spki[9:],
        "x25519": spki[:8] + b"\x6e" + spki[9:],
        "unsupported_curve": unsupported_curve,
        "oversized": spki + b"\x00" * 47,
    }[case]


@pytest.mark.parametrize("case", INVALID_RECOVERY_SPKI_CASES)
def test_recovery_normalizer_rejects_malformed_unsupported_and_oversized_der(case):
    with pytest.raises(ValueError, match="Invalid fleet device public key"):
        crypto.normalize_public_key_spki(invalid_recovery_spki(case))


def test_recovery_normalizer_accepts_alias_at_exact_size_boundary_only():
    canonical = base64.b64decode(
        _load_fixture("fleet-recovery-v1.json")["public_key_spki_b64"]
    )
    alias = canonical + b"\x00" * 46
    assert len(alias) == 90
    assert crypto.normalize_public_key_spki(alias) == canonical
    with pytest.raises(ValueError):
        crypto.normalize_public_key_spki(alias + b"\x00")


def test_real_decoder_unsupported_algorithm_is_redacted_at_normalizer_boundary():
    der = invalid_recovery_spki("unsupported_curve")
    with pytest.raises(UnsupportedAlgorithm):
        load_der_public_key(der)
    with pytest.raises(ValueError) as exc:
        crypto.normalize_public_key_spki(der)
    assert str(exc.value) == "Invalid fleet device public key."
    assert exc.value.__suppress_context__ and exc.value.__cause__ is None


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


class TestRecoveryFixture:
    def test_completion_bytes_and_signature_match_authgd(self):
        fixture = _load_fixture("fleet-recovery-v1.json")
        spki = base64.b64decode(fixture["public_key_spki_b64"])
        preimage = crypto.recovery_challenge_preimage(
            fixture["canonical_origin"], fixture["challenge_id"], fixture["nonce"], spki
        )
        assert preimage == fixture["preimage_utf8"].encode()
        load_der_public_key(spki).verify(
            _b64url_decode(fixture["signature_b64url"]), preimage
        )

    @pytest.mark.parametrize(
        "change", ["origin", "challenge", "nonce", "key", "purpose"]
    )
    def test_completion_proof_cannot_cross_bindings_or_purpose(self, change):
        fixture = _load_fixture("fleet-recovery-v1.json")
        spki = base64.b64decode(fixture["public_key_spki_b64"])
        origin = (
            "https://other.example"
            if change == "origin"
            else fixture["canonical_origin"]
        )
        challenge = (
            "00000000-0000-0000-0000-000000000000"
            if change == "challenge"
            else fixture["challenge_id"]
        )
        nonce = "A" * 43 if change == "nonce" else fixture["nonce"]
        key = (
            crypto.public_key_spki(crypto.generate_private_key())
            if change == "key"
            else spki
        )
        if change == "purpose":
            preimage = crypto.recovery_initiation_preimage(
                origin, nonce, "2026-09-07T12:00:00.000Z", key
            )
        else:
            preimage = crypto.recovery_challenge_preimage(origin, challenge, nonce, key)
        with pytest.raises(InvalidSignature):
            load_der_public_key(spki).verify(
                _b64url_decode(fixture["signature_b64url"]), preimage
            )

    def test_initiation_uses_canonical_der_digest_and_distinct_five_line_label(self):
        fixture = _load_fixture("fleet-recovery-v1.json")
        spki = base64.b64decode(fixture["public_key_spki_b64"])
        # Hand-established from the public completion key/digest, not from Python's builder.
        want = (
            "fleet-recovery-init-v1\nhttps://auth.example\n"
            + "A" * 43
            + "\n2026-09-07T12:00:00.000Z\n"
            "ae34b1ac9afb3737c91055a0d7934bb2e625ab78bf002e8e2297394bfbdd90c9"
        ).encode()
        for der in (spki, spki + b"\x00"):
            assert (
                crypto.recovery_initiation_preimage(
                    "https://AUTH.example:443/",
                    "A" * 43,
                    "2026-09-07T12:00:00.000Z",
                    der,
                )
                == want
            )

    @pytest.mark.parametrize("bad", ["B" * 43, "A" * 42, "A" * 43 + "=", "../x"])
    def test_initiation_rejects_noncanonical_request_tokens(self, bad):
        with pytest.raises(ValueError):
            crypto.recovery_initiation_preimage(
                "https://auth.example",
                bad,
                "2026-09-07T12:00:00.000Z",
                crypto.public_key_spki(crypto.generate_private_key()),
            )


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
