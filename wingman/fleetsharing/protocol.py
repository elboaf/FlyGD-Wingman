"""Closed fleet-v2 protocol codecs and request-correlation helpers.

Parsers reject the entire payload, never discard unknown fields or truncate lists.
Existing cryptographic primitive domains remain unchanged in `crypto.py`; this
module owns v2 DTO validation, exact protocol numbers and v2 response bindings.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from hashlib import sha256
from itertools import pairwise
from typing import Literal, get_args
from urllib.parse import urlsplit

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_der_public_key

from .. import combatprofile
from .config import canonical_origin
from .model import CatalogueCharacter, FleetCatalogue

API_VERSION = 2
SIGNING_SCHEME_VERSION = 1
INT4_MAX = 2_147_483_647
JS_SAFE_MAX = 9_007_199_254_740_991
MAX_REMOTE_ROWS = combatprofile.LIMITS["get_rows"]
MAX_SOURCE_INTENTS = 256
MAX_LIVE_SOURCES = 16
MAX_SOURCE_CHARACTERS = 256
MAX_CHARACTER_NAME = combatprofile.LIMITS["character_name_scalars"]
MAX_DPS = 10_000_000
MAX_ACTIVITY_AGE_MS = combatprofile.LIMITS["activity_ms"] - 1
MAX_READ_AGE_MS = combatprofile.LIMITS["transport_ms"] - 1
MAX_AUTOMATIC_SOURCES = 16
SIGNED_BINDING_DOMAIN = b"fleet-api-v2\n"
PRE_SESSION_BINDING_PURPOSE = "fleet-api-v2-pre-session"
SHARED_CAPABILITY = "shared-source-v1"
COMBAT_CAPABILITY = "combat-v2"
Capabilities = tuple[str, ...]
SourceState = Literal["pending", "active", "paused", "ended"]
SourceReason = Literal[
    "stopped",
    "expired",
    "superseded",
    "not_in_fleet",
    "boss_lost",
    "identity_changed",
    "fleet_read_invalid",
    "member_lost",
    "device_revoked",
    "token_invalid",
    "mode_transition",
    "service_unavailable",
    "untrustworthy_evidence",
    "timed_out",
    "ended",
]
SOURCE_REASONS = get_args(SourceReason)
ErrorCode = Literal[
    "bad_headers",
    "bad_request",
    "update_required",
    "invalid_intent",
    "invalid_key",
    "unauthorized",
    "forbidden",
    "capability_required",
    "fleet_read_required",
    "not_verified",
    "receipt_not_found",
    "not_found",
    "method_not_allowed",
    "conflict",
    "request_id_conflict",
    "revision_replayed",
    "not_completable",
    "rate_limited",
    "receipt_capacity",
    "feature_disabled",
    "service_unavailable",
]
EFFECT_ORDER = tuple(combatprofile.LIMITS["effect_order"])
EffectKind = Literal["SCRAM", "POINT", "NEUT"]
STOP_EFFECTS = (
    "manual_only",
    "unknown_cancelled",
    "disabled_current",
    "current_already_off",
    "older_generation_only",
)
READINESS_VALUES = (
    "off",
    "global_disabled",
    "member_required",
    "authorization_required",
    "capacity_limited",
    "waiting_for_grant",
    "waiting_for_fleet",
    "verifying",
    "reconnecting",
    "ready",
)
RECOVERY_ACTION_VALUES = (
    "none",
    "restore_membership",
    "authorize_fleet_read",
    "reauthorize_automatic",
    "wait",
)
APPROVER_VALUES = ("none", "this_device", "other_device", "revoked")
_V2_PATH_RE = re.compile(r"^/api/fleet/v2(?:/[A-Za-z0-9._~-]+)+$")
_UUID_RE = re.compile(
    r"(?:[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}|00000000-0000-0000-0000-000000000000|ffffffff-ffff-ffff-ffff-ffffffffffff)",
    re.IGNORECASE,
)
_UUID4_LOWER_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)
_HASH_RE = re.compile(r"[0-9a-f]{64}")
_SIGNATURE_RE = re.compile(r"[A-Za-z0-9_-]{86}")


def _invalid() -> ValueError:
    return ValueError("Fleet protocol value has an unexpected shape.")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _invalid()
        result[key] = value
    return result


def _reject_constant(_value):
    raise _invalid()


def decode_json(raw: bytes) -> object:
    """Callers enforce byte bounds before decoding; reject JSON parser extensions."""
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (ValueError, RecursionError):
        raise _invalid() from None


def exact_object(value: object, fields: str) -> dict:
    if not isinstance(value, dict) or set(value) != set(fields.split()):
        raise _invalid()
    return value


def envelope(value: object, fields: str) -> dict:
    data = exact_object(value, "protocol " + fields)
    integer(data["protocol"], API_VERSION, API_VERSION)
    return data


def integer(value: object, minimum: int = 0, maximum: int = INT4_MAX) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise _invalid()
    return value


def boolean(value: object) -> bool:
    if type(value) is not bool:
        raise _invalid()
    return value


def array(value: object, maximum: int, minimum: int = 0) -> list:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise _invalid()
    return value


def text(value: object, maximum: int = MAX_CHARACTER_NAME) -> str:
    # The installed profile's category predicate is intentionally the sole authority;
    # identity names keep their 200-scalar contract, not tackle normalization.
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= maximum
        or any(combatprofile._forbidden(ord(char)) for char in value)
    ):
        raise _invalid()
    return value


def uuid(value: object) -> str:
    if not isinstance(value, str) or not _UUID_RE.fullmatch(value):
        raise _invalid()
    return value


def uuid4_lower(value: object) -> str:
    if not isinstance(value, str) or not _UUID4_LOWER_RE.fullmatch(value):
        raise _invalid()
    return value


def hash_text(value: object) -> str:
    if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
        raise _invalid()
    return value


def _urlsafe_b64decode(value: str) -> bytes:
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except ValueError:
        raise _invalid() from None
    if base64.urlsafe_b64encode(decoded).decode().rstrip("=") != value:
        raise _invalid()
    return decoded


def token(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", value):
        raise _invalid()
    if len(_urlsafe_b64decode(value)) != 32:
        raise _invalid()
    return value


def signature(value: object) -> str:
    if not isinstance(value, str) or not _SIGNATURE_RE.fullmatch(value):
        raise _invalid()
    if len(_urlsafe_b64decode(value)) != 64:
        raise _invalid()
    return value


def public_key_spki_b64url(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 120:
        raise _invalid()
    decoded = _urlsafe_b64decode(value)
    try:
        key = load_der_public_key(decoded)
    except (ValueError, UnsupportedAlgorithm):
        raise _invalid() from None
    if not isinstance(key, Ed25519PublicKey):
        raise _invalid()
    return value


def utc_date(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z",
        value,
    ):
        raise _invalid()
    try:
        date = datetime.fromisoformat(value)
        if date.isoformat(timespec="milliseconds").replace("+00:00", "Z") != value:
            raise _invalid()
    except ValueError:
        raise _invalid() from None
    return value


def enum(value: object, choices: tuple[str, ...]) -> str:
    if not isinstance(value, str) or value not in choices:
        raise _invalid()
    return value


def parse_error(value: object) -> ErrorCode:
    """Closed common dictionary; the transport owns route/method/status subsets."""
    return enum(envelope(value, "error")["error"], get_args(ErrorCode))


def _parse_date(value: str) -> datetime:
    return datetime.fromisoformat(utc_date(value))


def literal_v2_path(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 2048
        or any(char.isspace() for char in value)
        or "\\" in value
        or not _V2_PATH_RE.fullmatch(value)
    ):
        raise _invalid()
    return value


def signed_request_binding(canonical: bytes) -> str:
    if not isinstance(canonical, (bytes, bytearray)):
        raise _invalid()
    return sha256(SIGNED_BINDING_DOMAIN + bytes(canonical)).hexdigest()


def pre_session_request_binding(
    origin: str, path: str, attempt_token: str, body: bytes
) -> str:
    if not isinstance(body, (bytes, bytearray)):
        raise _invalid()
    return sha256(
        "\n".join(
            (
                PRE_SESSION_BINDING_PURPOSE,
                canonical_origin(origin),
                "POST",
                literal_v2_path(path),
                token(attempt_token),
                sha256(bytes(body)).hexdigest(),
            )
        ).encode("utf-8")
    ).hexdigest()


def capabilities(value: object) -> Capabilities:
    values = tuple(
        enum(capability, (SHARED_CAPABILITY, COMBAT_CAPABILITY))
        for capability in array(value, 2)
    )
    if values not in (
        (),
        (SHARED_CAPABILITY,),
        (SHARED_CAPABILITY, COMBAT_CAPABILITY),
    ):
        raise _invalid()
    return values


def _unique(values: tuple, attribute: str) -> tuple:
    keys = [getattr(value, attribute) for value in values]
    keys = [key.lower() if isinstance(key, str) else key for key in keys]
    if len(set(keys)) != len(keys):
        raise _invalid()
    return values


def _sorted(values: tuple, attribute: str) -> tuple:
    keys = [getattr(value, attribute) for value in values]
    normalized = [key.lower() if isinstance(key, str) else key for key in keys]
    if any(left >= right for left, right in pairwise(normalized)):
        raise _invalid()
    return values


def _exact_day_window(accepted_at: str, expires_at: str) -> None:
    if _parse_date(expires_at) - _parse_date(accepted_at) != timedelta(hours=24):
        raise _invalid()


def _dps(value: object) -> int | None:
    return None if value is None else integer(value, 0, MAX_DPS)


@dataclass(frozen=True)
class Participation:
    enabled: bool
    generation: int


@dataclass(frozen=True)
class DeviceState:
    device_id: str
    session_expires_at: str
    feature_enabled: bool
    approved_capabilities: Capabilities
    session_approved_capabilities: Capabilities
    acknowledged_capabilities: Capabilities
    participation: Participation
    server_time_ms: int


@dataclass(frozen=True)
class SessionState:
    expires_at: str


@dataclass(frozen=True)
class SourceBinding:
    source_id: str
    source_generation: int
    consent_generation: int


@dataclass(frozen=True)
class AutomaticBinding:
    consent_generation: int


@dataclass(frozen=True)
class Consent:
    generation: int
    revision: int
    enabled: bool
    approving_device_id: str | None
    approved_at: str | None
    disabled_at: str | None
    closed_reason: Literal["explicit_off", "source_stop", "approver_revoked"] | None


@dataclass(frozen=True)
class AutomaticStatus:
    consent: Consent
    approver: Literal["none", "this_device", "other_device", "revoked"]
    readiness: Literal[
        "off",
        "global_disabled",
        "member_required",
        "authorization_required",
        "capacity_limited",
        "waiting_for_grant",
        "waiting_for_fleet",
        "verifying",
        "reconnecting",
        "ready",
    ]
    recovery_action: Literal[
        "none",
        "restore_membership",
        "authorize_fleet_read",
        "reauthorize_automatic",
        "wait",
    ]
    retry_at: str | None
    sources: tuple[SourceBinding, ...]


@dataclass(frozen=True)
class AutomaticCommand:
    request_id: str
    intent_created_at: str
    enabled: bool
    expected_generation: int
    expected_revision: int


@dataclass(frozen=True)
class AutomaticReceipt:
    command: AutomaticCommand
    accepted_at: str
    expires_at: str
    result: Consent
    kind: Literal["automatic"] = "automatic"


@dataclass(frozen=True)
class AutomaticGet:
    status: AutomaticStatus


@dataclass(frozen=True)
class AutomaticResult:
    request_id: str
    result: Literal["applied", "replayed", "already_off"]
    receipt: AutomaticReceipt | None
    status: AutomaticStatus


@dataclass(frozen=True)
class SourceView:
    source_id: str
    generation: int
    character_id: int | None
    state: SourceState
    reason: SourceReason | None
    pending_expires_at: str | None
    automatic: AutomaticBinding | None


@dataclass(frozen=True)
class SourceCharacter:
    character_id: int
    character_name: str
    character_link_epoch: str
    has_fleet_read: bool
    token_usable: bool


@dataclass(frozen=True)
class Sources:
    sources: tuple[SourceView, ...]
    characters: tuple[SourceCharacter, ...]


@dataclass(frozen=True)
class SourceStart:
    source_id: str
    character_id: int
    character_link_epoch: str
    intent_created_at: str
    expected_generation: int = 0


@dataclass(frozen=True)
class SourceStop:
    source_id: str
    expected_generation: int
    request_id: str
    intent_created_at: str
    expected_automatic: AutomaticBinding | None


SourceCommand = SourceStart | SourceStop
StartSource = SourceStart
StopSource = SourceStop


@dataclass(frozen=True)
class SourceStartResult:
    source: SourceView


@dataclass(frozen=True)
class SourceStopReceipt:
    command: SourceStop
    accepted_at: str
    expires_at: str
    source: SourceView
    automatic_effect: Literal[
        "manual_only",
        "unknown_cancelled",
        "disabled_current",
        "current_already_off",
        "older_generation_only",
    ]
    consent: Consent
    kind: Literal["source_stop"] = "source_stop"


@dataclass(frozen=True)
class SourceStopResult:
    request_id: str
    result: Literal["applied", "replayed", "already_stopped"]
    receipt: SourceStopReceipt | None
    source: SourceView
    automatic_effect: Literal[
        "manual_only",
        "unknown_cancelled",
        "disabled_current",
        "current_already_off",
        "older_generation_only",
    ]
    status: AutomaticStatus


@dataclass(frozen=True)
class EligibilityEntry:
    character_id: int
    source_id: str
    source_generation: int
    authority_generation: int
    expires_at: str


@dataclass(frozen=True)
class Eligibility:
    participation_generation: int
    state: Literal["ready", "participation_off", "not_verified"]
    characters: tuple[EligibilityEntry, ...]


@dataclass(frozen=True)
class PairingBegun:
    pairing_id: str
    approval_url: str
    expires_at: str


@dataclass(frozen=True)
class PairingCompleted:
    session_id: str
    catalogue: FleetCatalogue


@dataclass(frozen=True)
class RecoveryChallenge:
    challenge_id: str
    request_id: str
    nonce: str
    expires_at: str


@dataclass(frozen=True)
class RecoveryResult:
    result: Literal[
        "reconnected",
        "device_revoked",
        "device_key_conflict",
        "account_ineligible",
        "retry_later",
    ]
    device_id: str | None = None
    session_id: str | None = None
    session_expires_at: str | None = None
    approved_capabilities: Capabilities = ()
    participation: Participation | None = None
    retry_after_ms: int | None = None

    @property
    def requires_fresh_key_setup(self) -> bool:
        return self.result in ("device_revoked", "device_key_conflict")


@dataclass(frozen=True)
class Observation:
    name: str | None
    age_ms: int


@dataclass(frozen=True)
class Effect:
    kind: EffectKind
    observations: tuple[Observation, ...]


@dataclass(frozen=True)
class CombatRow:
    character_id: int
    outgoing_dps: int | None
    incoming_dps: int | None
    activity_age_ms: int
    effects: tuple[Effect, ...]


@dataclass(frozen=True)
class CombatPut:
    sampled_at_ms: int
    rows: tuple[CombatRow, ...]


@dataclass(frozen=True)
class CombatReadRow(CombatRow):
    character_name: str
    state: Literal["live", "stale"]
    age_ms: int
    publication_id: str


@dataclass(frozen=True)
class CombatSnapshot:
    server_time_ms: int
    rows: tuple[CombatReadRow, ...]


RemoteRow = CombatReadRow
ObservedRemoteRow = CombatReadRow
Receipt = AutomaticReceipt | SourceStopReceipt


@dataclass(frozen=True)
class ReceiptGet:
    receipt: Receipt
    status: AutomaticStatus


def parse_participation(value: object) -> Participation:
    d = exact_object(value, "enabled generation")
    return Participation(boolean(d["enabled"]), integer(d["generation"]))


def parse_participation_response(value: object) -> Participation:
    return parse_participation(envelope(value, "participation")["participation"])


def parse_session(value: object) -> SessionState:
    return SessionState(utc_date(envelope(value, "expires_at")["expires_at"]))


def parse_device(value: object) -> DeviceState:
    d = envelope(
        value,
        "device_id session_expires_at feature_enabled approved_capabilities session_approved_capabilities acknowledged_capabilities participation server_time_ms",
    )
    return DeviceState(
        uuid(d["device_id"]),
        utc_date(d["session_expires_at"]),
        boolean(d["feature_enabled"]),
        capabilities(d["approved_capabilities"]),
        capabilities(d["session_approved_capabilities"]),
        capabilities(d["acknowledged_capabilities"]),
        parse_participation(d["participation"]),
        integer(d["server_time_ms"], 0, JS_SAFE_MAX),
    )


def parse_source_binding(value: object) -> SourceBinding:
    d = exact_object(value, "source_id source_generation consent_generation")
    return SourceBinding(
        uuid4_lower(d["source_id"]),
        integer(d["source_generation"], 1),
        integer(d["consent_generation"], 1, JS_SAFE_MAX),
    )


def parse_automatic_binding(value: object) -> AutomaticBinding:
    d = exact_object(value, "consent_generation")
    return AutomaticBinding(integer(d["consent_generation"], 1, JS_SAFE_MAX))


def parse_consent(value: object) -> Consent:
    d = exact_object(
        value,
        "generation revision enabled approving_device_id approved_at disabled_at closed_reason",
    )
    generation = integer(d["generation"], 0, JS_SAFE_MAX)
    revision = integer(d["revision"], 0, JS_SAFE_MAX)
    enabled = boolean(d["enabled"])
    approving_device_id = (
        None if d["approving_device_id"] is None else uuid(d["approving_device_id"])
    )
    approved_at = None if d["approved_at"] is None else utc_date(d["approved_at"])
    disabled_at = None if d["disabled_at"] is None else utc_date(d["disabled_at"])
    closed_reason = (
        None
        if d["closed_reason"] is None
        else enum(
            d["closed_reason"], ("explicit_off", "source_stop", "approver_revoked")
        )
    )
    if revision < generation:
        raise _invalid()
    consent = Consent(
        generation,
        revision,
        enabled,
        approving_device_id,
        approved_at,
        disabled_at,
        closed_reason,
    )
    if generation == 0:
        if consent != Consent(0, 0, False, None, None, None, None):
            raise _invalid()
        return consent
    if approving_device_id is None or approved_at is None:
        raise _invalid()
    if enabled:
        if disabled_at is not None or closed_reason is not None:
            raise _invalid()
    else:
        if disabled_at is None or closed_reason is None:
            raise _invalid()
        if _parse_date(disabled_at) < _parse_date(approved_at):
            raise _invalid()
    return consent


def parse_automatic_status(value: object) -> AutomaticStatus:
    d = exact_object(
        value, "consent approver readiness recovery_action retry_at sources"
    )
    consent = parse_consent(d["consent"])
    sources = tuple(
        parse_source_binding(v) for v in array(d["sources"], MAX_AUTOMATIC_SOURCES)
    )
    _unique(sources, "source_id")
    _sorted(sources, "source_id")
    if (not consent.enabled and sources) or any(
        source.consent_generation != consent.generation for source in sources
    ):
        raise _invalid()
    status = AutomaticStatus(
        consent,
        enum(d["approver"], APPROVER_VALUES),
        enum(d["readiness"], READINESS_VALUES),
        enum(d["recovery_action"], RECOVERY_ACTION_VALUES),
        None if d["retry_at"] is None else utc_date(d["retry_at"]),
        sources,
    )
    if consent.generation == 0 and status != AutomaticStatus(
        consent, "none", "off", "none", None, ()
    ):
        raise _invalid()
    if consent.generation > 0 and status.approver == "none":
        raise _invalid()
    if consent.enabled == (status.readiness == "off"):
        raise _invalid()
    if not consent.enabled and status.retry_at is not None:
        raise _invalid()
    # Only explicit annex mappings: waiting_for_grant has no specified action,
    # and status cannot prove hidden grant/authority facts or readiness precedence.
    expected_action = {
        "off": "none",
        "ready": "none",
        "verifying": "none",
        "waiting_for_fleet": "none",
        "global_disabled": "wait",
        "capacity_limited": "wait",
        "reconnecting": "wait",
        "member_required": "restore_membership",
        "authorization_required": "reauthorize_automatic"
        if status.approver == "revoked"
        else "authorize_fleet_read",
    }.get(status.readiness)
    if expected_action is not None and status.recovery_action != expected_action:
        raise _invalid()
    return status


def parse_automatic_get(value: object) -> AutomaticGet:
    return AutomaticGet(parse_automatic_status(envelope(value, "status")["status"]))


def parse_automatic_command(value: object) -> AutomaticCommand:
    d = envelope(
        value,
        "request_id intent_created_at enabled expected_generation expected_revision",
    )
    return AutomaticCommand(
        uuid4_lower(d["request_id"]),
        utc_date(d["intent_created_at"]),
        boolean(d["enabled"]),
        integer(d["expected_generation"], 0, JS_SAFE_MAX),
        integer(d["expected_revision"], 0, JS_SAFE_MAX),
    )


def automatic_command_body(command: AutomaticCommand) -> dict:
    if not isinstance(command, AutomaticCommand):
        raise _invalid()
    body = {
        "protocol": API_VERSION,
        "request_id": command.request_id,
        "intent_created_at": command.intent_created_at,
        "enabled": command.enabled,
        "expected_generation": command.expected_generation,
        "expected_revision": command.expected_revision,
    }
    parse_automatic_command(body)
    return body


def parse_automatic_receipt(value: object) -> AutomaticReceipt:
    d = exact_object(value, "kind command accepted_at expires_at result")
    enum(d["kind"], ("automatic",))
    command = parse_automatic_command(d["command"])
    accepted_at = utc_date(d["accepted_at"])
    expires_at = utc_date(d["expires_at"])
    _exact_day_window(accepted_at, expires_at)
    intent_age = _parse_date(accepted_at) - _parse_date(command.intent_created_at)
    # Receipt chronology is historical; offline Off deliberately has no max age.
    if intent_age < timedelta(0) or (
        command.enabled and intent_age >= timedelta(seconds=60)
    ):
        raise _invalid()
    result = parse_consent(d["result"])
    if command.enabled:
        if not result.enabled or result.generation != command.expected_generation + 1:
            raise _invalid()
    else:
        if result.enabled or result.generation != command.expected_generation:
            raise _invalid()
    if result.revision != command.expected_revision + 1:
        raise _invalid()
    for candidate in (result.approved_at, result.disabled_at):
        if candidate is not None and _parse_date(candidate) > _parse_date(accepted_at):
            raise _invalid()
    return AutomaticReceipt(command, accepted_at, expires_at, result)


def parse_source(value: object) -> SourceView:
    d = exact_object(
        value,
        "source_id generation character_id state reason pending_expires_at automatic",
    )
    state = enum(d["state"], get_args(SourceState))
    reason = None if d["reason"] is None else enum(d["reason"], SOURCE_REASONS)
    pending_expires_at = (
        None if d["pending_expires_at"] is None else utc_date(d["pending_expires_at"])
    )
    automatic = (
        None if d["automatic"] is None else parse_automatic_binding(d["automatic"])
    )
    if state == "pending" and pending_expires_at is None:
        raise _invalid()
    if state in ("active", "ended") and pending_expires_at is not None:
        raise _invalid()
    if state == "ended" and reason is None:
        raise _invalid()
    return SourceView(
        uuid(d["source_id"]),
        integer(d["generation"], 1),
        None
        if d["character_id"] is None
        else integer(d["character_id"], 1, JS_SAFE_MAX),
        state,
        reason,
        pending_expires_at,
        automatic,
    )


def parse_source_command(value: object) -> SourceCommand:
    if not isinstance(value, dict):
        raise _invalid()
    operation = value.get("operation")
    if operation == "start":
        d = envelope(
            value,
            "operation source_id expected_generation character_id character_link_epoch intent_created_at",
        )
        enum(d["operation"], ("start",))
        return SourceStart(
            uuid(d["source_id"]),
            integer(d["character_id"], 1, JS_SAFE_MAX),
            uuid(d["character_link_epoch"]),
            utc_date(d["intent_created_at"]),
            integer(d["expected_generation"], 0, 0),
        )
    d = envelope(
        value,
        "operation source_id expected_generation request_id intent_created_at expected_automatic",
    )
    enum(d["operation"], ("stop",))
    return SourceStop(
        uuid(d["source_id"]),
        integer(d["expected_generation"], 0, INT4_MAX - 1),
        uuid4_lower(d["request_id"]),
        utc_date(d["intent_created_at"]),
        None
        if d["expected_automatic"] is None
        else parse_automatic_binding(d["expected_automatic"]),
    )


def source_command_body(command: SourceCommand) -> dict:
    if isinstance(command, SourceStart):
        body = {
            "protocol": API_VERSION,
            "operation": "start",
            "source_id": command.source_id,
            "expected_generation": command.expected_generation,
            "character_id": command.character_id,
            "character_link_epoch": command.character_link_epoch,
            "intent_created_at": command.intent_created_at,
        }
    elif isinstance(command, SourceStop):
        body = {
            "protocol": API_VERSION,
            "operation": "stop",
            "source_id": command.source_id,
            "expected_generation": command.expected_generation,
            "request_id": command.request_id,
            "intent_created_at": command.intent_created_at,
            "expected_automatic": None
            if command.expected_automatic is None
            else {"consent_generation": command.expected_automatic.consent_generation},
        }
    else:
        raise _invalid()
    parse_source_command(body)
    return body


def _source_character(value: object) -> SourceCharacter:
    d = exact_object(
        value,
        "character_id character_name character_link_epoch has_fleet_read token_usable",
    )
    return SourceCharacter(
        integer(d["character_id"], 1, JS_SAFE_MAX),
        text(d["character_name"]),
        uuid(d["character_link_epoch"]),
        boolean(d["has_fleet_read"]),
        boolean(d["token_usable"]),
    )


def parse_sources(value: object) -> Sources:
    d = envelope(value, "sources characters")
    sources = tuple(parse_source(v) for v in array(d["sources"], MAX_SOURCE_INTENTS))
    _unique(sources, "source_id")
    _sorted(sources, "source_id")
    if sum(source.state != "ended" for source in sources) > MAX_LIVE_SOURCES:
        raise _invalid()
    characters = tuple(
        _source_character(v) for v in array(d["characters"], MAX_SOURCE_CHARACTERS)
    )
    _unique(characters, "character_id")
    _sorted(characters, "character_id")
    return Sources(sources, characters)


def _validate_stop_effect(source: SourceView, effect: str, consent: Consent) -> None:
    if source.state != "ended":
        raise _invalid()
    if effect in ("manual_only", "unknown_cancelled"):
        if source.automatic is not None:
            raise _invalid()
    elif effect in ("disabled_current", "current_already_off"):
        if (
            source.automatic is None
            or consent.enabled
            or consent.generation != source.automatic.consent_generation
        ):
            raise _invalid()
    elif (
        source.automatic is None
        or source.automatic.consent_generation >= consent.generation
    ):
        raise _invalid()


def parse_source_stop_receipt(value: object) -> SourceStopReceipt:
    d = exact_object(
        value,
        "kind command accepted_at expires_at source automatic_effect consent",
    )
    enum(d["kind"], ("source_stop",))
    command = parse_source_command(d["command"])
    if not isinstance(command, SourceStop):
        raise _invalid()
    accepted_at = utc_date(d["accepted_at"])
    expires_at = utc_date(d["expires_at"])
    _exact_day_window(accepted_at, expires_at)
    intent_age = _parse_date(accepted_at) - _parse_date(command.intent_created_at)
    if not timedelta(0) <= intent_age < timedelta(seconds=60):
        raise _invalid()
    source = parse_source(d["source"])
    effect = enum(d["automatic_effect"], STOP_EFFECTS)
    consent = parse_consent(d["consent"])
    if command.source_id.lower() != source.source_id.lower():
        raise _invalid()
    if source.automatic != command.expected_automatic:
        raise _invalid()
    if effect == "unknown_cancelled" and command.expected_generation != 0:
        raise _invalid()
    _validate_stop_effect(source, effect, consent)
    for candidate in (consent.approved_at, consent.disabled_at):
        if candidate is not None and _parse_date(candidate) > _parse_date(accepted_at):
            raise _invalid()
    return SourceStopReceipt(command, accepted_at, expires_at, source, effect, consent)


# Compare only declared ExistingUuid identities without rewriting decoded DTOs or
# their signing/state bytes. Every other field still participates in exact equality.
def _same_consent(left: Consent, right: Consent) -> bool:
    if left.approving_device_id is None or right.approving_device_id is None:
        return left == right
    return (
        left.approving_device_id.lower() == right.approving_device_id.lower()
        and replace(left, approving_device_id=right.approving_device_id) == right
    )


def _same_source(left: SourceView, right: SourceView) -> bool:
    return (
        left.source_id.lower() == right.source_id.lower()
        and replace(left, source_id=right.source_id) == right
    )


def _same_stop_command(left: SourceStop, right: SourceStop) -> bool:
    return (
        left.source_id.lower() == right.source_id.lower()
        and replace(left, source_id=right.source_id) == right
    )


def parse_source_result(
    value: object, command: SourceCommand | None = None
) -> SourceStartResult | SourceStopResult:
    if not isinstance(value, dict):
        raise _invalid()
    if set(value) == {"protocol", "source"}:
        source = parse_source(envelope(value, "source")["source"])
        if source.automatic is not None:
            raise _invalid()
        if command is not None:
            if not isinstance(command, SourceStart):
                raise _invalid()
            if source.source_id.lower() != command.source_id.lower():
                raise _invalid()
            if source.character_id != command.character_id:
                raise _invalid()
        return SourceStartResult(source)

    d = envelope(value, "request_id result receipt source automatic_effect status")
    request_id = uuid4_lower(d["request_id"])
    result = enum(d["result"], ("applied", "replayed", "already_stopped"))
    receipt = None if d["receipt"] is None else parse_source_stop_receipt(d["receipt"])
    source = parse_source(d["source"])
    automatic_effect = enum(d["automatic_effect"], STOP_EFFECTS)
    status = parse_automatic_status(d["status"])
    if result == "already_stopped":
        if receipt is not None or automatic_effect == "disabled_current":
            raise _invalid()
        # A no-op has no historical receipt: its effect must describe current consent.
        _validate_stop_effect(source, automatic_effect, status.consent)
    else:
        if receipt is None:
            raise _invalid()
        if request_id != receipt.command.request_id:
            raise _invalid()
        if (
            not _same_source(source, receipt.source)
            or automatic_effect != receipt.automatic_effect
        ):
            raise _invalid()
        if status.consent.revision < receipt.consent.revision:
            raise _invalid()
        if status.consent.revision == receipt.consent.revision and not _same_consent(
            status.consent, receipt.consent
        ):
            raise _invalid()
    if command is not None:
        if not isinstance(command, SourceStop):
            raise _invalid()
        if command.request_id != request_id:
            raise _invalid()
        if command.source_id.lower() != source.source_id.lower():
            raise _invalid()
        if command.expected_automatic != source.automatic:
            raise _invalid()
        if automatic_effect == "unknown_cancelled" and command.expected_generation != 0:
            raise _invalid()
        if receipt is not None and not _same_stop_command(command, receipt.command):
            raise _invalid()
        # A read-only no-op cannot advance the source CAS; receipt-bearing terminal
        # transitions can. Unknown cancellation has no exception to this check.
        if (
            result == "already_stopped"
            and command.expected_generation != source.generation
        ):
            raise _invalid()
    return SourceStopResult(
        request_id, result, receipt, source, automatic_effect, status
    )


parse_source_control = parse_source_result


def _eligibility_entry(value: object) -> EligibilityEntry:
    d = exact_object(
        value,
        "character_id source_id source_generation authority_generation expires_at",
    )
    return EligibilityEntry(
        integer(d["character_id"], 1, JS_SAFE_MAX),
        uuid(d["source_id"]),
        integer(d["source_generation"], 1),
        integer(d["authority_generation"]),
        utc_date(d["expires_at"]),
    )


def parse_eligibility(value: object) -> Eligibility:
    d = envelope(value, "participation_generation state characters")
    rows = tuple(_eligibility_entry(v) for v in array(d["characters"], MAX_REMOTE_ROWS))
    _unique(rows, "character_id")
    state = enum(d["state"], ("ready", "participation_off", "not_verified"))
    if bool(rows) != (state == "ready"):
        raise _invalid()
    return Eligibility(integer(d["participation_generation"]), state, rows)


def parse_recovery_challenge(
    value: object, *, expected_request_id: str | None = None
) -> RecoveryChallenge:
    d = envelope(value, "challenge_id request_id nonce expires_at")
    challenge = RecoveryChallenge(
        uuid(d["challenge_id"]),
        token(d["request_id"]),
        token(d["nonce"]),
        utc_date(d["expires_at"]),
    )
    if expected_request_id is not None and challenge.request_id != token(
        expected_request_id
    ):
        raise _invalid()
    return challenge


def parse_recovery_result(value: object) -> RecoveryResult:
    if not isinstance(value, dict):
        raise _invalid()
    result = value.get("result")
    if result == "reconnected":
        d = envelope(
            value,
            "result device_id session_id session_expires_at approved_capabilities participation",
        )
        return RecoveryResult(
            enum(d["result"], ("reconnected",)),
            uuid(d["device_id"]),
            token(d["session_id"]),
            utc_date(d["session_expires_at"]),
            capabilities(d["approved_capabilities"]),
            parse_participation(d["participation"]),
        )
    if result in ("device_revoked", "device_key_conflict"):
        envelope(value, "result")
        return RecoveryResult(enum(result, ("device_revoked", "device_key_conflict")))
    d = envelope(value, "result retry_after_ms")
    return RecoveryResult(
        enum(d["result"], ("account_ineligible", "retry_later")),
        retry_after_ms=integer(d["retry_after_ms"], 1, 86_400_000),
    )


def parse_pairing_begun(value: object, *, origin: str) -> PairingBegun:
    d = envelope(value, "pairing_id approval_url expires_at")
    origin = canonical_origin(origin)
    approval = text(d["approval_url"], 2048)
    if any(char.isspace() for char in approval) or "\\" in approval:
        raise _invalid()
    parsed = urlsplit(approval)
    if (
        not parsed.scheme
        and not parsed.netloc
        and approval.startswith("/")
        and not approval.startswith("//")
    ):
        approval = origin + approval
    elif canonical_origin(f"{parsed.scheme}://{parsed.netloc}") != origin:
        raise _invalid()
    return PairingBegun(uuid(d["pairing_id"]), approval, utc_date(d["expires_at"]))


def _parse_catalogue(
    value: object, *, nested: bool, revision_max: int
) -> FleetCatalogue:
    d = (
        exact_object(value, "revision characters")
        if nested
        else envelope(value, "revision characters")
    )
    characters = []
    for raw in array(d["characters"], MAX_REMOTE_ROWS):
        c = exact_object(raw, "character_id character_name")
        characters.append(
            CatalogueCharacter(
                integer(c["character_id"], 1, JS_SAFE_MAX), text(c["character_name"])
            )
        )
    return FleetCatalogue(
        integer(d["revision"], 0, revision_max),
        _unique(tuple(characters), "character_id"),
    )


def parse_catalogue(value: object, *, nested: bool = False) -> FleetCatalogue:
    return _parse_catalogue(value, nested=nested, revision_max=0xFFFFFFFF)


def parse_pairing_completed(value: object) -> PairingCompleted:
    d = envelope(value, "session_id catalogue")
    return PairingCompleted(
        token(d["session_id"]),
        _parse_catalogue(d["catalogue"], nested=True, revision_max=INT4_MAX),
    )


def parse_observation(value: object) -> Observation:
    d = exact_object(value, "name age_ms")
    name = d["name"]
    if name is not None and not combatprofile.validate_observed_name(name):
        raise _invalid()
    return Observation(name, integer(d["age_ms"], 0, MAX_ACTIVITY_AGE_MS))


def parse_effect(value: object) -> Effect:
    d = exact_object(value, "kind observations")
    kind = enum(d["kind"], EFFECT_ORDER)
    maximum = 1 if kind == "NEUT" else combatprofile.LIMITS["observations_per_tackle"]
    observations = tuple(
        parse_observation(v) for v in array(d["observations"], maximum, 1)
    )
    nulls = sum(observation.name is None for observation in observations)
    named = tuple(
        observation for observation in observations if observation.name is not None
    )
    # Wire identity is exact NFC spelling; only producer retention uses casefold.
    if len({observation.name for observation in named}) != len(named):
        raise _invalid()
    if kind == "NEUT":
        if len(observations) != 1 or observations[0].name is not None:
            raise _invalid()
    else:
        if len(named) > combatprofile.LIMITS["named_per_tackle"] or nulls > 1:
            raise _invalid()
    return Effect(kind, observations)


def _combat_row(value: object) -> CombatRow:
    d = exact_object(
        value,
        "character_id outgoing_dps incoming_dps activity_age_ms effects",
    )
    activity_age_ms = integer(d["activity_age_ms"], 0, MAX_ACTIVITY_AGE_MS)
    effects = tuple(parse_effect(v) for v in array(d["effects"], len(EFFECT_ORDER)))
    if tuple(effect.kind for effect in effects) != tuple(
        sorted((effect.kind for effect in effects), key=EFFECT_ORDER.index)
    ):
        raise _invalid()
    _unique(effects, "kind")
    if (
        sum(len(effect.observations) for effect in effects)
        > combatprofile.LIMITS["observations_per_row"]
    ):
        raise _invalid()
    if (
        sum(
            observation.name is not None
            for effect in effects
            for observation in effect.observations
        )
        > combatprofile.LIMITS["named_per_row"]
    ):
        raise _invalid()
    if any(
        activity_age_ms > observation.age_ms
        for effect in effects
        for observation in effect.observations
    ):
        raise _invalid()
    return CombatRow(
        integer(d["character_id"], 1, JS_SAFE_MAX),
        _dps(d["outgoing_dps"]),
        _dps(d["incoming_dps"]),
        activity_age_ms,
        effects,
    )


def parse_combat_put(value: object) -> CombatPut:
    d = envelope(value, "sampled_at_ms rows")
    rows = tuple(
        _combat_row(v) for v in array(d["rows"], combatprofile.LIMITS["put_rows"])
    )
    _unique(rows, "character_id")
    sampled_at_ms = integer(d["sampled_at_ms"], 0, JS_SAFE_MAX)
    if not rows and sampled_at_ms != 0:
        raise _invalid()
    return CombatPut(sampled_at_ms, rows)


def _combat_read_row(value: object) -> CombatReadRow:
    d = exact_object(
        value,
        "character_id outgoing_dps incoming_dps activity_age_ms effects character_name state age_ms publication_id",
    )
    age_ms = integer(d["age_ms"], 0, MAX_READ_AGE_MS)
    state = enum(d["state"], ("live", "stale"))
    if (state == "live") != (age_ms < combatprofile.LIMITS["stale_ms"]):
        raise _invalid()
    row = _combat_row(
        {
            "character_id": d["character_id"],
            "outgoing_dps": d["outgoing_dps"],
            "incoming_dps": d["incoming_dps"],
            "activity_age_ms": d["activity_age_ms"],
            "effects": d["effects"],
        }
    )
    return CombatReadRow(
        row.character_id,
        row.outgoing_dps,
        row.incoming_dps,
        row.activity_age_ms,
        row.effects,
        text(d["character_name"]),
        state,
        age_ms,
        uuid4_lower(d["publication_id"]),
    )


def parse_snapshot(value: object) -> CombatSnapshot:
    d = envelope(value, "server_time_ms rows")
    rows = tuple(_combat_read_row(v) for v in array(d["rows"], MAX_REMOTE_ROWS))
    _unique(rows, "character_id")
    _unique(rows, "publication_id")
    return CombatSnapshot(integer(d["server_time_ms"], 0, JS_SAFE_MAX), rows)


# Import continuity only — never discard the required DB-time authority.
parse_observed_snapshot = parse_snapshot


def parse_automatic_result(
    value: object, command: AutomaticCommand | None = None
) -> AutomaticResult:
    d = envelope(value, "request_id result receipt status")
    request_id = uuid4_lower(d["request_id"])
    result = enum(d["result"], ("applied", "replayed", "already_off"))
    receipt = None if d["receipt"] is None else parse_automatic_receipt(d["receipt"])
    status = parse_automatic_status(d["status"])
    if result == "already_off":
        if receipt is not None or status.consent.enabled:
            raise _invalid()
        if command is not None and (
            command.enabled
            or command.expected_generation != status.consent.generation
            or command.expected_revision != status.consent.revision
        ):
            raise _invalid()
    else:
        if receipt is None or request_id != receipt.command.request_id:
            raise _invalid()
        if status.consent.revision < receipt.result.revision:
            raise _invalid()
        if status.consent.revision == receipt.result.revision and not _same_consent(
            status.consent, receipt.result
        ):
            raise _invalid()
    if command is not None:
        if request_id != command.request_id:
            raise _invalid()
        if receipt is not None and receipt.command != command:
            raise _invalid()
    return AutomaticResult(request_id, result, receipt, status)


def parse_receipt_get(
    value: object, *, expected_request_id: str | None = None
) -> ReceiptGet:
    d = envelope(value, "receipt status")
    status = parse_automatic_status(d["status"])
    if not isinstance(d["receipt"], dict):
        raise _invalid()
    kind = d["receipt"].get("kind")
    if kind == "automatic":
        receipt = parse_automatic_receipt(d["receipt"])
        revision = receipt.result.revision
        current = receipt.result
    elif kind == "source_stop":
        receipt = parse_source_stop_receipt(d["receipt"])
        revision = receipt.consent.revision
        current = receipt.consent
    else:
        raise _invalid()
    if expected_request_id is not None and receipt.command.request_id != uuid4_lower(
        expected_request_id
    ):
        raise _invalid()
    if status.consent.revision < revision:
        raise _invalid()
    if status.consent.revision == revision and not _same_consent(
        status.consent, current
    ):
        raise _invalid()
    return ReceiptGet(receipt, status)
