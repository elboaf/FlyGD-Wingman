"""Origin-bound device identity, session observations and durable in-flight intent.

The worker remains the sole writer. This module only loads/saves values; it never
recovers, rotates identity, retries consent or stores remote rows/catalogues.
User participation intent stays in Settings. Server participation here is only
an observation, not a second preference.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from contextlib import suppress
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

from .. import atomicio
from ..eveauth import dpapi
from . import crypto, protocol
from .config import canonical_origin

MAX_STATE_FILE_BYTES = 64 * 1024
STATE_VERSION = 2


@dataclass(frozen=True)
class DeviceIdentity:
    """DPAPI-protected raw Ed25519 private key and canonical padded-base64 SPKI."""

    protected_private_key_b64: str
    public_key_spki_b64: str


@dataclass(frozen=True)
class PendingRecovery:
    """Persist before admission; add the echoed challenge before one-use completion.

    Both phases belong to this state's identity/origin. Even expired bindings
    survive load unchanged: deciding what to do after response loss is Task 7,
    never a reason to silently mint a new request ID or timestamp here.
    """

    request_id: str
    issued_at: str
    challenge: protocol.RecoveryChallenge | None = None


@dataclass(frozen=True)
class SharingState:
    """Version 2; missing device/expiry/capabilities mean unknown, not unpaired.

    last_revision is the highest ATTEMPTED signed revision, saved BEFORE send.
    All signed calls share it. Replacement sessions reset only session-bound
    metadata; source/recovery bindings and device observations are independent.
    """

    identity: DeviceIdentity | None = None
    relay_origin: str | None = None
    session_id: str | None = None
    last_revision: int = 0
    device_id: str | None = None
    session_expires_at: str | None = None
    feature_enabled: bool | None = None
    approved_capabilities: protocol.Capabilities | None = None
    session_approved_capabilities: protocol.Capabilities | None = None
    acknowledged_capabilities: protocol.Capabilities | None = None
    observed_participation: protocol.Participation | None = None
    pending_recovery: PendingRecovery | None = None
    pending_source_commands: tuple[protocol.SourceCommand, ...] = ()


EMPTY = SharingState()


def wrap_private_key(raw_private_key: bytes, *, protect=dpapi.protect) -> str:
    """The injected DPAPI seam receives only the raw 32-byte private key."""
    if (
        not isinstance(raw_private_key, bytes)
        or len(raw_private_key) != crypto.RAW_PRIVATE_KEY_BYTES
    ):
        raise ValueError("Invalid fleet private key.")
    return base64.b64encode(protect(raw_private_key)).decode("ascii")


def _base64(value: object, maximum: int) -> bytes:
    if not isinstance(value, str) or not 1 <= len(value) <= maximum:
        raise ValueError("Invalid fleet key encoding.")
    try:
        raw = base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError):
        raise ValueError("Invalid fleet key encoding.") from None
    if base64.b64encode(raw).decode("ascii") != value:
        raise ValueError("Invalid fleet key encoding.")
    return raw


def unwrap_private_key(blob_b64: str, *, unprotect=dpapi.unprotect) -> bytes | None:
    """A foreign-machine/corrupt blob is unusable, never a crash or a new key."""
    try:
        blob = _base64(blob_b64, 8192)
    except ValueError:
        return None
    try:
        raw = unprotect(blob)
    except Exception:  # noqa: BLE001 - a corrupt/foreign DPAPI blob must not crash state loading
        return None
    return (
        raw
        if isinstance(raw, bytes) and len(raw) == crypto.RAW_PRIVATE_KEY_BYTES
        else None
    )


def _identity(value: object) -> DeviceIdentity:
    d = protocol.exact_object(value, "protected_private_key_b64 public_key_spki_b64")
    _base64(d["protected_private_key_b64"], 8192)
    spki = _base64(d["public_key_spki_b64"], 120)
    canonical = crypto.normalize_public_key_spki(spki)
    return DeviceIdentity(
        d["protected_private_key_b64"],
        crypto.canonical_device_public_key_b64(canonical),
    )


def _session(value: object) -> str:
    # V1 sessions were opaque. Keep valid legacy spellings while rejecting
    # controls/whitespace/oversize before they could become signed headers.
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise ValueError("Invalid fleet session.")
    return value


def replace_session(
    state: SharingState, session_id: str | None, *, expires_at: str | None = None
) -> SharingState:
    """Pure value replacement, not a writer or recovery/consent coordinator."""
    if session_id is not None:
        _session(session_id)
    if expires_at is not None:
        protocol.utc_date(expires_at)
    return replace(
        state,
        session_id=session_id,
        last_revision=0,
        session_expires_at=expires_at if session_id is not None else None,
        session_approved_capabilities=None,
        acknowledged_capabilities=None,
    )


def _optional(parser, value):
    return None if value is None else parser(value)


def _pending_recovery(value: object) -> PendingRecovery:
    d = protocol.exact_object(value, "request_id issued_at challenge")
    challenge = d["challenge"]
    if challenge is not None:
        protocol.exact_object(challenge, "challenge_id request_id nonce expires_at")
        challenge = protocol.parse_recovery_challenge({"protocol": 1, **challenge})
    pending = PendingRecovery(
        protocol.token(d["request_id"]), protocol.utc_date(d["issued_at"]), challenge
    )
    if challenge is not None and challenge.request_id != pending.request_id:
        raise ValueError("Fleet recovery binding mismatch.")
    return pending


def _pending_commands(value: object) -> tuple[protocol.SourceCommand, ...]:
    commands = tuple(
        protocol.parse_source_command(v)
        for v in protocol.array(value, protocol.MAX_SOURCE_INTENTS)
    )
    if len({c.source_id.lower() for c in commands}) != len(commands):
        raise ValueError("Duplicate pending fleet source intent.")
    return commands


def _session_fields(raw: dict) -> dict:
    session_id = _optional(_session, raw["session_id"])
    revision = protocol.integer(raw["last_revision"])
    expiry = _optional(protocol.utc_date, raw["session_expires_at"])
    ceiling = _optional(protocol.capabilities, raw["session_approved_capabilities"])
    ack = _optional(protocol.capabilities, raw["acknowledged_capabilities"])
    if session_id is None and (
        revision != 0 or any(v is not None for v in (expiry, ceiling, ack))
    ):
        raise ValueError("Session metadata has no session binding.")
    return {
        "session_id": session_id,
        "last_revision": revision,
        "session_expires_at": expiry,
        "session_approved_capabilities": ceiling,
        "acknowledged_capabilities": ack,
    }


def _parse_v2(raw: object, *, salvage_session: bool = False) -> SharingState:
    d = protocol.exact_object(
        raw, "version " + " ".join(f.name for f in fields(SharingState))
    )
    protocol.integer(d["version"], STATE_VERSION, STATE_VERSION)
    identity = _optional(_identity, d["identity"])
    origin = _optional(canonical_origin, d["relay_origin"])
    pending = _optional(_pending_recovery, d["pending_recovery"])
    commands = _pending_commands(d["pending_source_commands"])
    if (identity is not None and origin is None) or (
        (pending or commands) and identity is None
    ):
        raise ValueError("Fleet identity and intents require an origin binding.")
    try:
        session = _session_fields(d)
    except ValueError:
        if not salvage_session:
            raise
        # Bad expiry/revision/ack must not discard a recoverable registered key
        # or silently change a Start/recovery binding. Only the session is lost.
        session = {}
    return SharingState(
        identity=identity,
        relay_origin=origin,
        **session,
        device_id=_optional(protocol.uuid, d["device_id"]),
        feature_enabled=_optional(protocol.boolean, d["feature_enabled"]),
        approved_capabilities=_optional(
            protocol.capabilities, d["approved_capabilities"]
        ),
        observed_participation=_optional(
            protocol.parse_participation, d["observed_participation"]
        ),
        pending_recovery=pending,
        pending_source_commands=commands,
    )


def _migrate_v1(raw: dict) -> SharingState:
    allowed = {"version", "identity", "relay_origin", "session_id", "last_revision"}
    if not set(raw) <= allowed:
        raise ValueError("Unknown fleet state fields.")
    identity = None
    if raw.get("identity") is not None:
        # V1 already dropped incomplete identities on load.
        with suppress(ValueError):
            identity = _identity(raw["identity"])
    origin = _optional(canonical_origin, raw.get("relay_origin"))
    if identity is not None and origin is None:
        raise ValueError("Fleet identity requires its paired origin.")
    try:
        session_id = _optional(_session, raw.get("session_id"))
        revision = protocol.integer(raw.get("last_revision", 0))
    except ValueError:
        session_id, revision = None, 0
    return SharingState(
        identity=identity,
        relay_origin=origin,
        session_id=session_id,
        last_revision=revision if session_id is not None else 0,
    )


def _to_dict(state: SharingState) -> dict:
    if len(state.pending_source_commands) > protocol.MAX_SOURCE_INTENTS:
        raise ValueError("Too many pending fleet source intents.")
    raw = {"version": STATE_VERSION, **asdict(state)}
    # Commands carry a discriminator at rest as on the wire. No remote DTO has
    # a serialization path here; an accidental remote row is refused, not saved.
    raw["pending_source_commands"] = [
        {k: v for k, v in protocol.source_command_body(c).items() if k != "protocol"}
        for c in state.pending_source_commands
    ]
    return raw


def _read_bounded(path: Path) -> bytes:
    if path.stat().st_size > MAX_STATE_FILE_BYTES:
        raise ValueError("Fleet state exceeds the size limit.")
    with path.open("rb") as stream:
        data = stream.read(MAX_STATE_FILE_BYTES + 1)
    if len(data) > MAX_STATE_FILE_BYTES:
        raise ValueError("Fleet state exceeds the size limit.")
    return data


def load(path: Path) -> SharingState:
    """Explicit V1 migration; unknown versions/corrupt journals fail closed.

    Loading never writes a migration or generates an identity. A V1 registered
    key without device ID/expiry remains recoverable at its original origin.
    """
    try:
        raw = protocol.decode_json(_read_bounded(Path(path)))
        if not isinstance(raw, dict) or type(raw.get("version")) is not int:
            return EMPTY
        if raw["version"] == 1:
            return _migrate_v1(raw)
        return _parse_v2(raw, salvage_session=True)
    except (OSError, ValueError):
        return EMPTY


def save(path: Path, state: SharingState) -> None:
    """Validate the whole bounded journal BEFORE atomically replacing old state.

    No truncation and no .bak. atomicio stages at 0600 via mkstemp; os.replace
    retains that mode (Windows additionally protects private material with DPAPI).
    Failed validation/serialization leaves the last durable binding untouched.
    """
    data = json.dumps(_to_dict(state), indent=2, allow_nan=False)
    if len(data.encode("utf-8")) > MAX_STATE_FILE_BYTES:
        raise ValueError("Fleet state exceeds the size limit.")
    _parse_v2(protocol.decode_json(data.encode("utf-8")))
    atomicio.write_atomic(Path(path), data)
