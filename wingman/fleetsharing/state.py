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
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from urllib.parse import urlsplit

from .. import atomicio
from ..eveauth import dpapi
from . import crypto, protocol
from .config import canonical_origin
from .legacytext import valid_legacy_url_text

STATE_VERSION = 4
MAX_STATE_FILE_BYTES = 262144
MAX_LEGACY_FILE_BYTES = 65536
MAX_ORIGINAL_BYTES = 65536
MAX_OUTCOMES_BYTES = 32768
MAX_ACTIVE_BYTES = 147456
MAX_AUTOMATIC_BYTES = 8192
MAX_FRAMING_BYTES = 8192
MAX_SOURCE_COMMAND_BYTES = 400
NON_SOURCE_RESERVE_BYTES = 32768
MAX_PENDING_AUTOMATIC_BYTES = 512
MAX_CONSENT_BYTES = 512
MAX_AUTOMATIC_RECEIPT_BYTES = 1024
MAX_AUTOMATIC_COMPLETION_BYTES = 1792

# Frozen disk inventories, independent of current dataclass fields and API2.
_LEGACY_V1_KEYS = "version identity relay_origin session_id last_revision"
_LEGACY_V2_KEYS = (
    _LEGACY_V1_KEYS + " device_id session_expires_at feature_enabled"
    " approved_capabilities session_approved_capabilities acknowledged_capabilities"
    " observed_participation pending_recovery pending_source_commands"
)
_LEGACY_V3_KEYS = _LEGACY_V2_KEYS + " pending_pairing pending_participation auth_pause"
_V4_KEYS = _LEGACY_V3_KEYS + " cutover automatic"


class QuarantineError(ValueError):
    """Unreadable evidence, not permission to initialize or overwrite the file."""


class CapacityError(ValueError):
    """A candidate cannot fit; unlike an atomic I/O failure, retry cannot fix it."""


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
    completion_attempted: bool = False


@dataclass(frozen=True)
class PendingPairing:
    """Candidate key/origin live in SharingState; exposure follows durable admission."""

    mode: str
    pairing_id: str | None = None
    approval_url: str | None = None
    expires_at: str | None = None
    completion_attempted: bool = False
    requested_capabilities: protocol.Capabilities = ()

    def __post_init__(self):
        object.__setattr__(
            self, "requested_capabilities", tuple(self.requested_capabilities)
        )


@dataclass(frozen=True)
class PendingParticipation:
    """An explicit action, not a copy of Settings. Unbound On needs fresh consent."""

    intent_id: str
    enabled: bool
    expected_generation: int | None = None
    attempted: bool = False


@dataclass(frozen=True)
class AuthPause:
    """Only proof outcomes are durable; generic HTTP errors are not revocation."""

    result: str
    retry_not_before: str | None = None


@dataclass(frozen=True)
class CutoverOutcome:
    selector: str
    status: str


@dataclass(frozen=True)
class Cutover:
    """One immutable archive; consumers receive detached decoded evidence only."""

    _original_utf8: bytes
    outcomes: tuple[CutoverOutcome, ...]

    def __post_init__(self):
        if not isinstance(self._original_utf8, (bytes, bytearray)):
            raise ValueError("Invalid fleet archive buffer.")
        object.__setattr__(self, "_original_utf8", bytes(self._original_utf8))
        object.__setattr__(self, "outcomes", tuple(self.outcomes))

    @property
    def original(self) -> dict:
        return protocol.decode_json(self._original_utf8)


@dataclass(frozen=True)
class CancelAfterOn:
    request_id: str
    intent_created_at: str


@dataclass(frozen=True)
class PendingAutomatic:
    command: protocol.AutomaticCommand
    attempted: bool = False
    cancel_after_on: CancelAfterOn | None = None


@dataclass(frozen=True)
class AutomaticCompletion:
    pending: PendingAutomatic
    outcome: str
    receipt: protocol.AutomaticReceipt | None = None


@dataclass(frozen=True)
class AutomaticState:
    observed_consent: protocol.Consent | None = None
    pending: PendingAutomatic | None = None
    last_result: AutomaticCompletion | None = None


@dataclass(frozen=True)
class SharingState:
    """Version 4; missing device/expiry/capabilities mean unknown, not unpaired.

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
    pending_pairing: PendingPairing | None = None
    pending_participation: PendingParticipation | None = None
    auth_pause: AuthPause | None = None
    cutover: Cutover | None = None
    automatic: AutomaticState = AutomaticState()

    def __post_init__(self):
        # Callers can supply lists, but no mutable collection becomes saved intent.
        for name in (
            "approved_capabilities",
            "session_approved_capabilities",
            "acknowledged_capabilities",
            "pending_source_commands",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, tuple(value))


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


def replace_session(
    state: SharingState, session_id: str | None, *, expires_at: str | None = None
) -> SharingState:
    """Pure value replacement, not a writer or recovery/consent coordinator."""
    if session_id is not None:
        protocol.token(session_id)
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
    d = protocol.exact_object(
        value, "request_id issued_at challenge completion_attempted"
    )
    challenge = d["challenge"]
    if challenge is not None:
        protocol.exact_object(challenge, "challenge_id request_id nonce expires_at")
        challenge = protocol.parse_recovery_challenge({"protocol": 2, **challenge})
    pending = PendingRecovery(
        protocol.token(d["request_id"]),
        protocol.utc_date(d["issued_at"]),
        challenge,
        protocol.boolean(d["completion_attempted"]),
    )
    if pending.completion_attempted and challenge is None:
        raise ValueError("Fleet recovery completion requires its challenge.")
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
    session_id = _optional(protocol.token, raw["session_id"])
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


def _pending_pairing(value: object, origin: str | None) -> PendingPairing:
    d = protocol.exact_object(
        value,
        "mode pairing_id approval_url expires_at completion_attempted requested_capabilities",
    )
    mode = protocol.enum(d["mode"], ("initial", "upgrade", "fresh"))
    attempted = protocol.boolean(d["completion_attempted"])
    pair_id, url, expiry = d["pairing_id"], d["approval_url"], d["expires_at"]
    if pair_id is None:
        if url is not None or expiry is not None or attempted:
            raise ValueError("Incomplete fleet pairing journal.")
    else:
        begun = protocol.parse_pairing_begun(
            {
                "protocol": 2,
                "pairing_id": pair_id,
                "approval_url": url,
                "expires_at": expiry,
            },
            origin=origin,
        )
        url = protocol.text(begun.approval_url, 2048)
    return PendingPairing(
        mode,
        pair_id,
        url,
        expiry,
        attempted,
        protocol.capabilities(d["requested_capabilities"]),
    )


def _pending_participation(value: object) -> PendingParticipation:
    d = protocol.exact_object(value, "intent_id enabled expected_generation attempted")
    pending = PendingParticipation(
        protocol.uuid(d["intent_id"]),
        protocol.boolean(d["enabled"]),
        _optional(
            lambda v: protocol.integer(v, 0, protocol.INT4_MAX - 1),
            d["expected_generation"],
        ),
        protocol.boolean(d["attempted"]),
    )
    if pending.attempted and pending.expected_generation is None:
        raise ValueError("Attempted participation requires its CAS.")
    return pending


def _auth_pause(value: object) -> AuthPause:
    d = protocol.exact_object(value, "result retry_not_before")
    result = protocol.enum(
        d["result"],
        ("device_revoked", "device_key_conflict", "account_ineligible", "retry_later"),
    )
    deadline = _optional(protocol.utc_date, d["retry_not_before"])
    if (result in ("account_ineligible", "retry_later")) != (deadline is not None):
        raise ValueError("Invalid fleet authentication pause.")
    return AuthPause(result, deadline)


def _parse_v4(raw: object) -> SharingState:
    d = protocol.exact_object(raw, _V4_KEYS)
    protocol.integer(d["version"], STATE_VERSION, STATE_VERSION)
    identity = _optional(_identity, d["identity"])
    origin = _optional(canonical_origin, d["relay_origin"])
    pending = _optional(_pending_recovery, d["pending_recovery"])
    commands = _pending_commands(d["pending_source_commands"])
    pairing = (
        None
        if d["pending_pairing"] is None
        else _pending_pairing(d["pending_pairing"], origin)
    )
    participation = _optional(_pending_participation, d["pending_participation"])
    pause = _optional(_auth_pause, d["auth_pause"])
    if (identity is not None and origin is None) or (
        (pending or commands or pairing or participation or pause) and identity is None
    ):
        raise ValueError("Fleet identity and intents require an origin binding.")
    automatic = _automatic(d["automatic"])
    device_id = _optional(protocol.uuid, d["device_id"])
    if automatic != AutomaticState() and (
        identity is None or origin is None or device_id is None
    ):
        raise ValueError("Automatic evidence requires its device binding.")
    cutover = None if d["cutover"] is None else _cutover(d["cutover"], identity, origin)
    return SharingState(
        identity=identity,
        relay_origin=origin,
        **_session_fields(d),
        device_id=device_id,
        feature_enabled=_optional(protocol.boolean, d["feature_enabled"]),
        approved_capabilities=_optional(
            protocol.capabilities, d["approved_capabilities"]
        ),
        observed_participation=_optional(
            protocol.parse_participation, d["observed_participation"]
        ),
        pending_recovery=pending,
        pending_source_commands=commands,
        pending_pairing=pairing,
        pending_participation=participation,
        auth_pause=pause,
        cutover=cutover,
        automatic=automatic,
    )


def _legacy_capabilities(value: object) -> tuple[str, ...]:
    return tuple(
        protocol.enum(c, ("shared-source-v1",)) for c in protocol.array(value, 1)
    )


def _validate_legacy_recovery(value: object) -> None:
    d = protocol.exact_object(value, "request_id issued_at challenge")
    request = protocol.token(d["request_id"])
    protocol.utc_date(d["issued_at"])
    if d["challenge"] is not None:
        c = protocol.exact_object(
            d["challenge"], "challenge_id request_id nonce expires_at"
        )
        protocol.uuid(c["challenge_id"])
        protocol.token(c["nonce"])
        protocol.utc_date(c["expires_at"])
        if protocol.token(c["request_id"]) != request:
            raise ValueError("Legacy recovery binding mismatch.")


def _validate_legacy_pairing(value: object, origin: str | None) -> None:
    d = protocol.exact_object(
        value, "mode pairing_id approval_url expires_at completion_attempted"
    )
    protocol.enum(d["mode"], ("initial", "upgrade", "fresh"))
    attempted = protocol.boolean(d["completion_attempted"])
    pair_id, url, expiry = d["pairing_id"], d["approval_url"], d["expires_at"]
    if pair_id is None:
        if url is not None or expiry is not None or attempted:
            raise ValueError("Incomplete legacy pairing journal.")
        return
    if not isinstance(pair_id, str) or not re.fullmatch(
        r"[A-Za-z0-9._-]{1,128}", pair_id
    ):
        raise ValueError("Invalid legacy pairing ID.")
    # Legacy protocol.text used the Python 3.11 Unicode14 predicate, not API2's
    # Unicode16 profile: newly assigned scalars must not invent valid old data.
    if (
        not isinstance(url, str)
        or not 1 <= len(url) <= 2048
        or not valid_legacy_url_text(url)
        or "\\" in url
    ):
        raise ValueError("Invalid legacy approval URL.")
    parsed = urlsplit(url)
    if canonical_origin(f"{parsed.scheme}://{parsed.netloc}") != origin:
        raise ValueError("Legacy approval URL origin mismatch.")
    protocol.utc_date(expiry)


def _validate_legacy_commands(value: object) -> None:
    seen = set()
    for item in protocol.array(value, 256):
        if isinstance(item, dict) and item.get("operation") == "start":
            d = protocol.exact_object(
                item,
                "operation source_id expected_generation character_id character_link_epoch intent_created_at",
            )
            protocol.integer(d["expected_generation"], 0, 0)
            protocol.integer(d["character_id"], 1, protocol.JS_SAFE_MAX)
            protocol.uuid(d["character_link_epoch"])
            protocol.utc_date(d["intent_created_at"])
        else:
            d = protocol.exact_object(item, "operation source_id expected_generation")
            protocol.enum(d["operation"], ("stop",))
            protocol.integer(d["expected_generation"], 0, protocol.INT4_MAX - 1)
        source_id = protocol.uuid(d["source_id"]).lower()
        if source_id in seen:
            raise ValueError("Duplicate legacy source intent.")
        seen.add(source_id)


def _legacy_observations(raw: object) -> SharingState:
    if not isinstance(raw, dict):
        raise ValueError("Invalid legacy document.")
    version = protocol.integer(raw.get("version"), 1, 3)
    if version == 1:
        if not set(raw) <= set(_LEGACY_V1_KEYS.split()):
            raise ValueError("Unknown legacy fields.")
    else:
        protocol.exact_object(raw, _LEGACY_V2_KEYS if version == 2 else _LEGACY_V3_KEYS)
    identity = _optional(_identity, raw.get("identity"))
    origin = _optional(canonical_origin, raw.get("relay_origin"))
    if identity is not None and origin is None:
        raise ValueError("Legacy identity requires its origin.")
    if version == 1:
        return SharingState(identity=identity, relay_origin=origin)
    device = _optional(protocol.uuid, raw["device_id"])
    approvals = _optional(_legacy_capabilities, raw["approved_capabilities"])
    _optional(protocol.boolean, raw["feature_enabled"])
    _optional(protocol.parse_participation, raw["observed_participation"])
    _optional(_validate_legacy_recovery, raw["pending_recovery"])
    _validate_legacy_commands(raw["pending_source_commands"])
    if raw.get("pending_pairing") is not None:
        _validate_legacy_pairing(raw["pending_pairing"], origin)
    if raw.get("pending_participation") is not None:
        d = protocol.exact_object(
            raw["pending_participation"],
            "intent_id enabled expected_generation attempted",
        )
        protocol.uuid(d["intent_id"])
        protocol.boolean(d["enabled"])
        _optional(
            lambda v: protocol.integer(v, 0, protocol.INT4_MAX - 1),
            d["expected_generation"],
        )
        protocol.boolean(d["attempted"])
    pause = _optional(_auth_pause, raw.get("auth_pause"))
    if (
        any(
            raw.get(k)
            for k in (
                "pending_recovery",
                "pending_source_commands",
                "pending_pairing",
                "pending_participation",
                "auth_pause",
            )
        )
        and identity is None
    ):
        raise ValueError("Legacy journals require an identity binding.")
    # Every session-related value is retired, even valid opaque V1 spellings.
    # Invalid session metadata alone is salvageable and remains in original.
    return SharingState(
        identity=identity,
        relay_origin=origin,
        device_id=device,
        approved_capabilities=approvals,
        auth_pause=pause,
    )


def _legacy_selectors(raw: dict) -> tuple[tuple[str, tuple[str, ...]], ...]:
    selectors = []
    revision = raw.get("last_revision", 0)
    if (
        type(revision) is not int
        or revision != 0
        or any(
            raw.get(k) is not None
            for k in (
                "session_id",
                "session_expires_at",
                "session_approved_capabilities",
                "acknowledged_capabilities",
            )
        )
    ):
        selectors.append(("session", ("fenced", "superseded_session", "dismissed")))
    for field, statuses in (
        ("pairing", ("fenced", "recovered_identity", "expired_unproven", "dismissed")),
        ("recovery", ("fenced", "recovered_identity", "expired_unproven", "dismissed")),
        ("participation", ("fenced", "observed_choice", "dismissed")),
    ):
        if raw.get("pending_" + field) is not None:
            selectors.append((field, statuses))
    for command in raw.get("pending_source_commands", []):
        statuses = (
            ("fenced", "expired_unproven", "dismissed")
            if command["operation"] == "start"
            else ("fenced", "dismissed")
        )
        selectors.append(("source:" + command["source_id"].lower(), statuses))
    return tuple(selectors)


def _cutover(
    value: object, identity: DeviceIdentity | None, origin: str | None
) -> Cutover:
    d = protocol.exact_object(value, "original outcomes")
    original = d["original"]
    observations = _legacy_observations(original)
    if observations.identity != identity or observations.relay_origin != origin:
        raise ValueError("Fleet archive identity/origin mismatch.")
    selectors = _legacy_selectors(original)
    items = protocol.array(d["outcomes"], 260)
    if len(items) != len(selectors):
        raise ValueError("Incomplete fleet archive outcomes.")
    outcomes = []
    for item, (selector, allowed) in zip(items, selectors, strict=True):
        outcome = protocol.exact_object(item, "selector status")
        if outcome["selector"] != selector:
            raise ValueError("Fleet archive selector mismatch.")
        outcomes.append(
            CutoverOutcome(selector, protocol.enum(outcome["status"], allowed))
        )
    return Cutover(_compact_utf8(original).encode("utf-8"), tuple(outcomes))


def _migrate_legacy(raw: dict) -> SharingState:
    observations = _legacy_observations(raw)
    archive = Cutover(
        _compact_utf8(raw).encode("utf-8"),
        tuple(
            CutoverOutcome(selector, "fenced") for selector, _ in _legacy_selectors(raw)
        ),
    )
    return replace(observations, cutover=archive)


def _pending_automatic(value: object) -> PendingAutomatic:
    d = protocol.exact_object(value, "command attempted cancel_after_on")
    command = protocol.parse_automatic_command(d["command"])
    attempted = protocol.boolean(d["attempted"])
    cancel = None
    if d["cancel_after_on"] is not None:
        c = protocol.exact_object(d["cancel_after_on"], "request_id intent_created_at")
        cancel = CancelAfterOn(
            protocol.uuid4_lower(c["request_id"]),
            protocol.utc_date(c["intent_created_at"]),
        )
        if (
            not command.enabled
            or not attempted
            or cancel.request_id == command.request_id
        ):
            raise ValueError("Invalid fleet cancellation binding.")
    return PendingAutomatic(command, attempted, cancel)


def _automatic_completion(value: object) -> AutomaticCompletion:
    d = protocol.exact_object(value, "pending outcome receipt")
    pending = _pending_automatic(d["pending"])
    outcome = protocol.enum(
        d["outcome"],
        (
            "receipt",
            "already_off",
            "observed_off",
            "rejected",
            "superseded_unknown",
            "cancelled_unsent",
        ),
    )
    receipt = _optional(protocol.parse_automatic_receipt, d["receipt"])
    if outcome == "receipt":
        if receipt is None or receipt.command != pending.command:
            raise ValueError("Fleet automatic receipt binding mismatch.")
    elif receipt is not None:
        raise ValueError("Unexpected fleet automatic receipt.")
    if outcome in ("already_off", "observed_off") and pending.command.enabled:
        raise ValueError("Off observation cannot settle an On.")
    if outcome == "cancelled_unsent" and pending.attempted:
        raise ValueError("Attempted work cannot be cancelled unsent.")
    return AutomaticCompletion(pending, outcome, receipt)


def _automatic(value: object) -> AutomaticState:
    d = protocol.exact_object(value, "observed_consent pending last_result")
    return AutomaticState(
        _optional(protocol.parse_consent, d["observed_consent"]),
        _optional(_pending_automatic, d["pending"]),
        _optional(_automatic_completion, d["last_result"]),
    )


def _pending_automatic_dict(pending: PendingAutomatic) -> dict:
    return {
        **asdict(pending),
        "command": protocol.automatic_command_body(pending.command),
    }


def _receipt_dict(receipt: protocol.AutomaticReceipt) -> dict:
    return {
        **asdict(receipt),
        "command": protocol.automatic_command_body(receipt.command),
    }


def _to_dict(state: SharingState) -> dict:
    if not isinstance(state, SharingState):
        raise ValueError("Invalid fleet state candidate.")
    if len(state.pending_source_commands) > protocol.MAX_SOURCE_INTENTS:
        raise ValueError("Too many pending fleet source intents.")
    raw = {"version": STATE_VERSION, **asdict(state)}
    raw["pending_source_commands"] = [
        protocol.source_command_body(c) for c in state.pending_source_commands
    ]
    raw["cutover"] = (
        None
        if state.cutover is None
        else {
            "original": state.cutover.original,
            "outcomes": [asdict(outcome) for outcome in state.cutover.outcomes],
        }
    )
    automatic = raw["automatic"]
    if state.automatic.pending is not None:
        automatic["pending"] = _pending_automatic_dict(state.automatic.pending)
    if state.automatic.last_result is not None:
        completion = state.automatic.last_result
        automatic["last_result"] = {
            "pending": _pending_automatic_dict(completion.pending),
            "outcome": completion.outcome,
            "receipt": None
            if completion.receipt is None
            else _receipt_dict(completion.receipt),
        }
    return raw


def _read_bounded(path: Path) -> bytes | None:
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return None
    # Once existence was observed, even ENOENT during open/read is a failed read,
    # not authority to initialize over a concurrent removal or inaccessible file.
    if size > MAX_STATE_FILE_BYTES:
        raise ValueError("Fleet state exceeds the size limit.")
    with path.open("rb") as stream:
        data = stream.read(MAX_STATE_FILE_BYTES + 1)
    if len(data) > MAX_STATE_FILE_BYTES:
        raise ValueError("Fleet state exceeds the size limit.")
    return data


def load(path: Path) -> SharingState:
    """No writes: absence is EMPTY, corruption quarantines, other I/O propagates.

    A failed read must never become permission to initialize. The owner chooses
    recovery/dismissal explicitly; this codec never renames or deletes evidence.
    """
    try:
        data = _read_bounded(Path(path))
    except ValueError:
        raise QuarantineError("Fleet state requires quarantine.") from None
    if data is None:
        return EMPTY
    try:
        raw = protocol.decode_json(data)
        if not isinstance(raw, dict) or type(raw.get("version")) is not int:
            raise ValueError("Invalid fleet state version.")
        if raw["version"] in (1, 2, 3):
            if len(data) > MAX_LEGACY_FILE_BYTES:
                raise CapacityError("Legacy fleet state exceeds its size limit.")
            state = _migrate_legacy(raw)
        else:
            state = _parse_v4(raw)
        _check_capacity(_to_dict(state))
        return state
    except (ValueError, TypeError, RecursionError):
        raise QuarantineError("Fleet state requires quarantine.") from None


def _compact_utf8(raw: object) -> str:
    # JSON still owns control/quote/backslash escaping. Escape only code points
    # UTF-8 cannot encode (lone surrogates), never replace their decoded value.
    data = json.dumps(raw, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return data.encode("utf-8", errors="backslashreplace").decode("utf-8")


def _size(value: object) -> int:
    return len(_compact_utf8(value).encode("utf-8"))


def _within(value: object, maximum: int) -> int:
    size = _size(value)
    if size > maximum:
        raise CapacityError("Fleet state exceeds a reserved partition.")
    return size


def _check_capacity(raw: dict) -> None:
    whole = _within(raw, MAX_STATE_FILE_BYTES)
    cutover = raw["cutover"]
    original_size = outcomes_size = 0
    if cutover is not None:
        original_size = _within(cutover["original"], MAX_ORIGINAL_BYTES)
        outcomes_size = _within(cutover["outcomes"], MAX_OUTCOMES_BYTES)
    active = {k: v for k, v in raw.items() if k not in ("cutover", "automatic")}
    active_size = _within(active, MAX_ACTIVE_BYTES)
    commands = active["pending_source_commands"]
    command_bytes = sum(_within(c, MAX_SOURCE_COMMAND_BYTES) for c in commands)
    _within({**active, "pending_source_commands": []}, NON_SOURCE_RESERVE_BYTES)
    # Keep actual command bytes immutable and charge EVERY unused slot. The
    # non-source envelope already contains []; add all future separating commas.
    active_reserve = (
        NON_SOURCE_RESERVE_BYTES
        + command_bytes
        + (protocol.MAX_SOURCE_INTENTS - len(commands)) * MAX_SOURCE_COMMAND_BYTES
        + protocol.MAX_SOURCE_INTENTS
        - 1
    )
    if active_reserve > MAX_ACTIVE_BYTES:
        raise CapacityError("Fleet state has no room for future source/control growth.")
    automatic = raw["automatic"]
    automatic_size = _within(automatic, MAX_AUTOMATIC_BYTES)
    if automatic["observed_consent"] is not None:
        _within(automatic["observed_consent"], MAX_CONSENT_BYTES)
    if automatic["pending"] is not None:
        _within(automatic["pending"], MAX_PENDING_AUTOMATIC_BYTES)
    last = automatic["last_result"]
    if last is not None:
        _within(last, MAX_AUTOMATIC_COMPLETION_BYTES)
        _within(last["pending"], MAX_PENDING_AUTOMATIC_BYTES)
        if last["receipt"] is not None:
            _within(last["receipt"], MAX_AUTOMATIC_RECEIPT_BYTES)
            _within(last["receipt"]["result"], MAX_CONSENT_BYTES)
    automatic_framing = _size(dict.fromkeys(automatic)) - 3 * len("null")
    automatic_reserve = (
        MAX_PENDING_AUTOMATIC_BYTES
        + MAX_CONSENT_BYTES
        + MAX_AUTOMATIC_COMPLETION_BYTES
        + automatic_framing
    )
    if automatic_reserve > MAX_AUTOMATIC_BYTES:
        raise CapacityError("Fleet state has no room for automatic completion.")
    framing = whole - active_size - automatic_size - original_size - outcomes_size
    if framing > MAX_FRAMING_BYTES:
        raise CapacityError("Fleet state exceeds framing headroom.")
    # Do not borrow archive/outcome partitions, even before migration evidence or
    # automatic work exists. These disjoint maxima leave documented safety room.
    if (
        MAX_ORIGINAL_BYTES
        + MAX_OUTCOMES_BYTES
        + active_reserve
        + automatic_reserve
        + MAX_FRAMING_BYTES
        > MAX_STATE_FILE_BYTES
    ):
        raise CapacityError("Fleet state has no room for future terminal evidence.")


def _validated(state: SharingState) -> tuple[SharingState, dict]:
    # Serialize first to detach all caller buffers and normalize JSON containers.
    # Parse validates exact shapes; serialize AGAIN stores canonical key/origin/URL.
    raw = protocol.decode_json(_compact_utf8(_to_dict(state)).encode("utf-8"))
    candidate = _parse_v4(raw)
    raw = _to_dict(candidate)
    _check_capacity(raw)
    return candidate, raw


def check_control_capacity(state: SharingState) -> None:
    """Full validation and the same future reserves as admission/save/load."""
    _validated(state)


def check_admission_capacity(state: SharingState) -> None:
    """No actual-command-only exception: terminal capacity is always reserved."""
    _validated(state)


def settle_automatic_receipt(
    state: SharingState, receipt: protocol.AutomaticReceipt
) -> SharingState:
    """Pure exact-receipt settlement, optionally deriving the already-authorized Off.

    No I/O, clocks, current-status inference or lane/user-action admission here.
    The worker must prove transport binding/drain before calling and save this ONE
    candidate before acknowledgement. Historical receipt results never roll back
    observed consent and are the ONLY CAS authority for a saved cancellation.
    """
    state, _ = _validated(state)
    receipt = protocol.parse_automatic_receipt(_receipt_dict(receipt))
    pending = state.automatic.pending
    if pending is None or receipt.command != pending.command:
        raise ValueError("Fleet automatic receipt binding mismatch.")
    following = None
    if pending.cancel_after_on is not None:
        cancel = pending.cancel_after_on
        following = PendingAutomatic(
            protocol.AutomaticCommand(
                cancel.request_id,
                cancel.intent_created_at,
                False,
                receipt.result.generation,
                receipt.result.revision,
            )
        )
    candidate = replace(
        state,
        automatic=replace(
            state.automatic,
            pending=following,
            last_result=AutomaticCompletion(pending, "receipt", receipt),
        ),
    )
    return _validated(candidate)[0]


def save(path: Path, state: SharingState) -> None:
    """Detach/validate/size the complete candidate, then exactly one replacement.

    No truncation or .bak. atomicio stages at 0600; DPAPI protects private material
    on Windows. Failed serialization/validation/staging leaves old intent intact.
    atomicio does not fsync the parent directory: no full power-loss guarantee.
    """
    _, raw = _validated(state)
    atomicio.write_atomic(Path(path), _compact_utf8(raw))
