"""Ed25519 signing and key management for the fleet-sharing protocol.

Pure cryptographic math only: key generation, the `fleet-v1` canonical byte
contract, and signing. Nothing here touches disk, DPAPI, or the network --
`wingman.fleetsharing.state` owns persistence (and the DPAPI seam) and
`wingman.fleetsharing.client` owns transport. Every function operates on
raw bytes so a caller (or a test) never has to hold a `cryptography` key
object.

Every wire encoding this module produces is pinned to match authGD's own
implementation byte-for-byte (`src/lib/fleet-signature.ts`,
`src/services/fleet-pairing.ts` in the authGD worktree) -- Ed25519
signatures are unpadded base64url, the canonical request text is exactly
authGD's `fleet-v1` line format, and the pairing completion preimage is
exactly `fleet-pairing-v1\\n<pairing-id>`. `tests/fixtures/fleet-signature-v1.json`
and `tests/fixtures/fleet-pairing-v1.json` are authGD's own public test
vectors, copied byte-for-byte, and `test_fleetsharing_crypto.py` verifies
both directly against this module.
"""

from __future__ import annotations

import base64
from hashlib import sha256

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_der_public_key,
)

from . import protocol
from .config import canonical_origin

# The only protocol major this module speaks. authGD rejects any other
# major with an explicit `update_required` response rather than guessing
# field semantics (design doc, "Compatibility and migration").
PROTOCOL_VERSION = 1

# authGD's `pairingChallengePreimage` label (src/services/fleet-pairing.ts).
# Distinct from the `fleet-v1` request-signature label below: pairing
# completion signs a one-time server-issued challenge, not a canonical
# HTTP request.
PAIRING_PREIMAGE_LABEL = "fleet-pairing-v1"

RAW_PRIVATE_KEY_BYTES = 32


def generate_private_key() -> bytes:
    """A fresh, raw 32-byte Ed25519 private key.

    Raw, not PKCS8 or any other encoded format: this is exactly the shape
    `wingman.fleetsharing.state.wrap_private_key` hands to the injected
    DPAPI `protect` callable, and the shape `Ed25519PrivateKey.
    from_private_bytes` accepts everywhere else in this module. Nothing
    above this module ever holds a `cryptography` key object.
    """
    key = Ed25519PrivateKey.generate()
    return key.private_bytes(
        encoding=Encoding.Raw,
        format=PrivateFormat.Raw,
        encryption_algorithm=NoEncryption(),
    )


def public_key_spki(private_key: bytes) -> bytes:
    """The DER SubjectPublicKeyInfo for *private_key*.

    This is what authGD registers and later verifies requests against
    (Task 3's `decodeDevicePublicKeyB64`/`verifyFleetRequest`).
    """
    key = Ed25519PrivateKey.from_private_bytes(private_key)
    return key.public_key().public_bytes(
        encoding=Encoding.DER, format=PublicFormat.SubjectPublicKeyInfo
    )


def canonical_device_public_key_b64(spki: bytes) -> str:
    """Padded standard base64 of *spki*.

    Matches authGD's `canonicalDevicePublicKeyB64` (Task 3 fix round 1)
    exactly: the single form a device's public key is stored and compared
    by on both sides of the relay, so two encodings of the identical key
    bytes can never be treated as two different devices.
    """
    return base64.b64encode(spki).decode("ascii")


def public_key_spki_b64url(spki: bytes) -> str:
    """Unpadded base64url of *spki*.

    The wire form authGD's `POST /api/fleet/v1/pairing-requests` body
    requires for its `public_key_spki_b64url` field -- distinct from
    `canonical_device_public_key_b64`, which is the padded standard form
    used for storage/comparison, never for this request body.
    """
    return _b64url_no_pad(spki)


def _b64url_no_pad(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def canonical_fleet_request(
    *,
    protocol: int,
    method: str,
    path: str,
    session_id: str,
    issued_at: str,
    revision: int,
    body_sha256: str,
) -> bytes:
    """The exact `fleet-v1` canonical byte sequence authGD's
    `canonicalFleetRequest` (Task 3, `src/lib/fleet-signature.ts`)
    produces: UTF-8 lines, `\\n`-joined, no trailing newline, in this
    fixed order: protocol/method label, method, exact path, session id,
    RFC3339 issued-at, base-10 revision, lowercase SHA-256 hex body
    digest.
    """
    lines = (
        f"fleet-v{protocol}",
        method,
        path,
        session_id,
        issued_at,
        str(revision),
        body_sha256,
    )
    return "\n".join(lines).encode("utf-8")


def snapshot_request_binding(canonical: bytes) -> str:
    """Correlate a publication-v1 response with the exact bytes we signed.

    This is not a relay signature: HTTPS and the relay remain trusted. A stale
    journal restored with its old session must recover/invalidate that session.
    """
    return sha256(b"fleet-snapshot-publication-v1\n" + canonical).hexdigest()


def sign_request(private_key: bytes, canonical: bytes) -> str:
    """Sign *canonical* and return an unpadded base64url Ed25519 signature.

    Unpadded base64url specifically, never padded and never the base64url
    alphabet mixed with padding: authGD's `SIGNATURE_RE`
    (`src/lib/fleet-signature.ts`) rejects anything else outright as
    `bad_headers`, before it ever reaches signature verification.
    """
    key = Ed25519PrivateKey.from_private_bytes(private_key)
    return _b64url_no_pad(key.sign(canonical))


def pairing_challenge_preimage(pairing_id: str) -> bytes:
    """The exact UTF-8 preimage authGD's `pairingChallengePreimage`
    (Task 4, `src/services/fleet-pairing.ts`) signs over:
    `fleet-pairing-v1\\n<pairing-id>`, no trailing newline. The random,
    one-time `pairing_id` authGD issues IS the challenge; there is no
    separate server-issued nonce.
    """
    return f"{PAIRING_PREIMAGE_LABEL}\n{pairing_id}".encode()


def normalize_public_key_spki(spki: bytes) -> bytes:
    """Hash canonical Ed25519 SPKI, never a DER alias or its base64 text.

    V1's raw serializers remain unchanged. Recovery uses the same normalized
    identity as authGD; DER trailing-byte aliases must not create a new digest.
    """
    if not isinstance(spki, bytes) or not 1 <= len(spki) <= 90:
        raise ValueError("Invalid fleet device public key.")
    # Node/OpenSSL accepts trailing bytes after an SPKI; cryptography's strict
    # decoder does not. Strip only the canonical Ed25519 SPKI's known envelope,
    # not arbitrary ASN.1 or guessed key offsets.
    canonical_prefix = bytes.fromhex("302a300506032b6570032100")
    der = spki[:44] if spki.startswith(canonical_prefix) else spki
    try:
        key = load_der_public_key(der)
    except (ValueError, UnsupportedAlgorithm):
        raise ValueError("Invalid fleet device public key.") from None
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("Invalid fleet device public key.")
    return key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)


def recovery_initiation_preimage(
    origin: str, request_id: str, issued_at: str, public_key: bytes
) -> bytes:
    """Caller-owned, already-journaled request ID/time; never mint a retry here."""
    return "\n".join(
        (
            "fleet-recovery-init-v1",
            canonical_origin(origin),
            protocol.token(request_id),
            protocol.utc_date(issued_at),
            sha256(normalize_public_key_spki(public_key)).hexdigest(),
        )
    ).encode("utf-8")


def recovery_challenge_preimage(
    origin: str, challenge_id: str, nonce: str, public_key: bytes
) -> bytes:
    """Purpose- and configured-origin-bound one-use challenge proof."""
    return "\n".join(
        (
            "fleet-recovery-v1",
            canonical_origin(origin),
            protocol.uuid(challenge_id),
            protocol.token(nonce),
            sha256(normalize_public_key_spki(public_key)).hexdigest(),
        )
    ).encode("utf-8")


def sign_pairing_completion(private_key: bytes, pairing_id: str) -> str:
    """Sign the pairing completion challenge for *pairing_id*, returning
    an unpadded base64url signature -- the `completion_signature` field
    `POST /api/fleet/v1/pairing-requests/:id/complete` requires.
    """
    return sign_request(private_key, pairing_challenge_preimage(pairing_id))
