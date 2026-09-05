"""Persistent fleet-sharing device identity and session state.

Deliberately narrow, mirroring `wingman.eveauth.state`'s posture at a much
smaller scale (one device, not N characters): this document holds only
what pairing/publishing needs to resume across a restart. It never holds
an EVE character identity, an EVE token, or an authGD browser session
cookie -- fleet sharing authenticates as its own device key, never by
reusing either of those (design doc, "Pairing and device authentication").

`protected_private_key_b64` wraps whatever the injected DPAPI `protect`
callable returned for the raw 32-byte Ed25519 private key
(`crypto.generate_private_key`'s own output) -- never the raw key itself,
and `protect`/`unprotect` here receive only those raw bytes, the same seam
`wingman.eveauth.tokens.wrap`/`unwrap` establish for the EVE refresh token.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from pathlib import Path

from .. import atomicio
from ..eveauth import dpapi

MAX_STATE_FILE_BYTES = 64 * 1024
STATE_VERSION = 1


@dataclass(frozen=True)
class DeviceIdentity:
    """The device's own keypair, at rest.

    `public_key_spki_b64` is the padded standard-base64 SPKI DER --
    `crypto.canonical_device_public_key_b64`'s own output, the same
    canonical form authGD persists and compares device keys by.
    """

    protected_private_key_b64: str
    public_key_spki_b64: str


@dataclass(frozen=True)
class SharingState:
    """Everything fleet sharing needs to resume across a restart.

    `identity`, `relay_origin`, and `session_id` are all `None` before a
    device exists/pairing completes -- there is no partially-paired shape
    below that; a document with only some of these fields present loses
    the incomplete parts on the next load rather than persisting a
    half-identity.
    """

    identity: DeviceIdentity | None = None
    relay_origin: str | None = None
    session_id: str | None = None


EMPTY = SharingState()


def wrap_private_key(raw_private_key: bytes, *, protect=dpapi.protect) -> str:
    """DPAPI-protect *raw_private_key* and return it as base64 text.

    *raw_private_key* must be exactly the 32 raw bytes
    `crypto.generate_private_key` returns -- `protect` never sees a
    `cryptography` key object or any other encoded form. Text, not bytes,
    because the result is stored as a JSON string field.
    """
    return base64.b64encode(protect(raw_private_key)).decode("ascii")


def unwrap_private_key(blob_b64: str, *, unprotect=dpapi.unprotect) -> bytes | None:
    """Reverse of `wrap_private_key`. `None` on any failure to decode or
    decrypt, never an exception -- a corrupted or foreign-machine blob
    costs a new pairing, not a crash, mirroring
    `wingman.eveauth.tokens.unwrap`'s identical posture for the EVE
    refresh token and for the identical reason: this is read while
    loading state, and letting a decode failure propagate would take the
    whole load down for what is, at worst, one re-pairing.
    """
    if not blob_b64:
        return None
    try:
        blob = base64.b64decode(blob_b64.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError):
        return None
    try:
        return unprotect(blob)
    except Exception:  # noqa: BLE001 - a corrupted key costs a re-pair, not a crash
        return None


def _to_dict(state: SharingState) -> dict:
    identity = None
    if state.identity is not None:
        identity = {
            "protected_private_key_b64": state.identity.protected_private_key_b64,
            "public_key_spki_b64": state.identity.public_key_spki_b64,
        }
    return {
        "version": STATE_VERSION,
        "identity": identity,
        "relay_origin": state.relay_origin,
        "session_id": state.session_id,
    }


def _coerce_text(raw: object) -> str | None:
    return raw if isinstance(raw, str) and raw else None


def _from_dict(raw: object) -> SharingState:
    if not isinstance(raw, dict):
        return EMPTY
    identity = None
    raw_identity = raw.get("identity")
    if isinstance(raw_identity, dict):
        protected = _coerce_text(raw_identity.get("protected_private_key_b64"))
        public = _coerce_text(raw_identity.get("public_key_spki_b64"))
        # Never a half-identity: either both fields are present and valid,
        # or the device identity is treated as absent and a re-pair is
        # needed. A blob with no matching public key (or vice versa) is not
        # a state this module can act on safely.
        if protected and public:
            identity = DeviceIdentity(
                protected_private_key_b64=protected, public_key_spki_b64=public
            )
    return SharingState(
        identity=identity,
        relay_origin=_coerce_text(raw.get("relay_origin")),
        session_id=_coerce_text(raw.get("session_id")),
    )


def _read_bounded(path: Path) -> str:
    if path.stat().st_size > MAX_STATE_FILE_BYTES:
        raise ValueError(f"{path.name} exceeds the state file size limit.")
    with path.open("rb") as stream:
        data = stream.read(MAX_STATE_FILE_BYTES + 1)
    if len(data) > MAX_STATE_FILE_BYTES:
        raise ValueError(f"{path.name} exceeds the state file size limit.")
    return data.decode("utf-8")


def load(path: Path) -> SharingState:
    """Load the fleet-sharing state document.

    Missing, unreadable, oversized, or corrupt all collapse to the same
    `EMPTY` result -- the same as never having paired. There is no history
    in this document worth failing loudly to protect; losing it only costs
    a new pairing.
    """
    path = Path(path)
    try:
        raw = json.loads(_read_bounded(path))
    except (OSError, ValueError, UnicodeDecodeError):
        return EMPTY
    return _from_dict(raw)


def save(path: Path, state: SharingState) -> None:
    """Atomically save *state*.

    `atomicio.write_atomic`'s `tempfile.mkstemp` staging file is always
    created at 0600 (unaffected by the process umask -- see
    `wingman.eveskills.state`'s identical note on its own `_save_locked`),
    and `os.replace` carries that mode across unchanged onto *path*: no
    separate `os.chmod` call is needed here, only a rename of an
    already-hardened file. This document has no `.bak` sibling (unlike
    `eveauth.state`/`eveskills.state`) -- there is no multi-row history
    here worth a second on-disk copy; losing this document costs one new
    pairing, not lost identities.
    """
    path = Path(path)
    atomicio.write_atomic(path, json.dumps(_to_dict(state), indent=2))
