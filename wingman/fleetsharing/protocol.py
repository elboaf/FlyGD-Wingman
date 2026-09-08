"""Closed fleet-v1 control/read contracts. Sparse publications stay in model.py.

Parsers reject the entire response, never discard unknown fields or truncate
rows. Bounds here are client admission limits, not a promise that every server
account fits in one response. No DTO schedules work or persists remote data.
"""

from __future__ import annotations

import base64
import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal, get_args

from .model import CatalogueCharacter, FleetCatalogue

INT4_MAX = 2_147_483_647
JS_SAFE_MAX = 9_007_199_254_740_991
MAX_REMOTE_ROWS = 8192
MAX_SOURCE_INTENTS = 256
MAX_LIVE_SOURCES = 16
MAX_SOURCE_CHARACTERS = 256
MAX_CHARACTER_NAME = 200
SHARED_CAPABILITY = "shared-source-v1"
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
    integer(data["protocol"], 1, 1)
    return data


def integer(value: object, minimum: int = 0, maximum: int = INT4_MAX) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise _invalid()
    return value


def boolean(value: object) -> bool:
    if type(value) is not bool:
        raise _invalid()
    return value


def text(value: object, maximum: int = MAX_CHARACTER_NAME) -> str:
    # Markup remains plain text, but controls, bidi formatting and surrogates
    # cannot become misleading names in a future display or local status.
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= maximum
        or any(
            unicodedata.category(c).startswith("C") or c in "\u2028\u2029"
            for c in value
        )
    ):
        raise _invalid()
    return value


def uuid(value: object) -> str:
    # Canonical hyphen layout; accept case as z.uuid does, preserve signed bytes.
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}|00000000-0000-0000-0000-000000000000|ffffffff-ffff-ffff-ffff-ffffffffffff)",
        value,
        re.IGNORECASE,
    ):
        raise _invalid()
    return value


def token(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", value):
        raise _invalid()
    decoded = base64.urlsafe_b64decode(value + "=")
    if base64.urlsafe_b64encode(decoded).decode().rstrip("=") != value:
        raise _invalid()
    return value


def utc_date(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z", value
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


def array(value: object, maximum: int) -> list:
    if not isinstance(value, list) or len(value) > maximum:
        raise _invalid()
    return value


def capabilities(value: object) -> Capabilities:
    return tuple(enum(c, (SHARED_CAPABILITY,)) for c in array(value, 1))


def _unique(values: tuple, attribute: str) -> tuple:
    keys = [getattr(value, attribute) for value in values]
    # UUID casing is not a second identity.
    keys = [key.lower() if isinstance(key, str) else key for key in keys]
    if len(set(keys)) != len(keys):
        raise _invalid()
    return values


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


@dataclass(frozen=True)
class StartSource:
    source_id: str
    character_id: int
    character_link_epoch: str
    intent_created_at: str
    expected_generation: int = 0


@dataclass(frozen=True)
class StopSource:
    source_id: str
    expected_generation: int


SourceCommand = StartSource | StopSource


@dataclass(frozen=True)
class SourceView:
    source_id: str
    generation: int
    character_id: int | None
    state: SourceState
    reason: SourceReason | None
    pending_expires_at: str | None


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
        """Only a proven completion outcome can request explicit fresh-key setup."""
        return self.result in ("device_revoked", "device_key_conflict")


@dataclass(frozen=True)
class RemoteRow:
    character_id: int
    character_name: str
    dps: int
    ewar: tuple[str, ...]
    state: Literal["live", "stale"]
    age_ms: int


def parse_participation(value: object) -> Participation:
    d = exact_object(value, "enabled generation")
    return Participation(boolean(d["enabled"]), integer(d["generation"]))


def parse_participation_response(value: object) -> Participation:
    return parse_participation(envelope(value, "participation")["participation"])


def parse_device(value: object) -> DeviceState:
    d = envelope(
        value,
        "device_id session_expires_at feature_enabled approved_capabilities session_approved_capabilities acknowledged_capabilities participation",
    )
    return DeviceState(
        uuid(d["device_id"]),
        utc_date(d["session_expires_at"]),
        boolean(d["feature_enabled"]),
        capabilities(d["approved_capabilities"]),
        capabilities(d["session_approved_capabilities"]),
        capabilities(d["acknowledged_capabilities"]),
        parse_participation(d["participation"]),
    )


def parse_source_command(value: object) -> SourceCommand:
    if not isinstance(value, dict):
        raise _invalid()
    if value.get("operation") == "start":
        d = exact_object(
            value,
            "operation source_id expected_generation character_id character_link_epoch intent_created_at",
        )
        return StartSource(
            uuid(d["source_id"]),
            integer(d["character_id"], 1, JS_SAFE_MAX),
            uuid(d["character_link_epoch"]),
            utc_date(d["intent_created_at"]),
            integer(d["expected_generation"], 0, 0),
        )
    d = exact_object(value, "operation source_id expected_generation")
    enum(d["operation"], ("stop",))
    return StopSource(
        uuid(d["source_id"]), integer(d["expected_generation"], 0, INT4_MAX - 1)
    )


def source_command_body(command: SourceCommand) -> dict:
    if not isinstance(command, (StartSource, StopSource)):
        raise _invalid()
    d = {
        "operation": "start" if isinstance(command, StartSource) else "stop",
        **asdict(command),
    }
    parse_source_command(d)
    return {"protocol": 1, **d}


def parse_source(value: object) -> SourceView:
    d = exact_object(
        value, "source_id generation character_id state reason pending_expires_at"
    )
    return SourceView(
        uuid(d["source_id"]),
        integer(d["generation"], 1),
        None
        if d["character_id"] is None
        else integer(d["character_id"], 1, JS_SAFE_MAX),
        enum(d["state"], ("pending", "active", "paused", "ended")),
        None if d["reason"] is None else enum(d["reason"], SOURCE_REASONS),
        None if d["pending_expires_at"] is None else utc_date(d["pending_expires_at"]),
    )


def parse_source_control(value: object) -> SourceView:
    return parse_source(envelope(value, "source")["source"])


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
    sources = _unique(
        tuple(parse_source(v) for v in array(d["sources"], MAX_SOURCE_INTENTS)),
        "source_id",
    )
    if sum(source.state != "ended" for source in sources) > MAX_LIVE_SOURCES:
        raise _invalid()
    return Sources(
        sources,
        _unique(
            tuple(
                _source_character(v)
                for v in array(d["characters"], MAX_SOURCE_CHARACTERS)
            ),
            "character_id",
        ),
    )


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
    rows = _unique(
        tuple(_eligibility_entry(v) for v in array(d["characters"], MAX_REMOTE_ROWS)),
        "character_id",
    )
    state = enum(d["state"], ("ready", "participation_off", "not_verified"))
    if bool(rows) != (state == "ready"):
        raise _invalid()
    return Eligibility(integer(d["participation_generation"]), state, rows)


def parse_recovery_challenge(value: object) -> RecoveryChallenge:
    d = envelope(value, "challenge_id request_id nonce expires_at")
    return RecoveryChallenge(
        uuid(d["challenge_id"]),
        token(d["request_id"]),
        token(d["nonce"]),
        utc_date(d["expires_at"]),
    )


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
            result,
            uuid(d["device_id"]),
            token(d["session_id"]),
            utc_date(d["session_expires_at"]),
            capabilities(d["approved_capabilities"]),
            parse_participation(d["participation"]),
        )
    if result in ("device_revoked", "device_key_conflict"):
        envelope(value, "result")
        return RecoveryResult(result)
    d = envelope(value, "result retry_after_ms")
    result = enum(result, ("account_ineligible", "retry_later"))
    delay = 60000 if result == "account_ineligible" else 1000
    return RecoveryResult(
        result, retry_after_ms=integer(d["retry_after_ms"], delay, delay)
    )


def _remote_row(value: object) -> RemoteRow:
    d = exact_object(value, "character_id character_name dps ewar state age_ms")
    age = integer(d["age_ms"], 0, 9999)
    state = enum(d["state"], ("live", "stale"))
    if (state == "live") != (age < 3000):
        raise _invalid()
    return RemoteRow(
        integer(d["character_id"], 1, JS_SAFE_MAX),
        text(d["character_name"]),
        integer(d["dps"], 0, 10_000_000),
        tuple(enum(v, ("SCRAM/POINT",)) for v in array(d["ewar"], 1)),
        state,
        age,
    )


def parse_snapshot(value: object) -> tuple[RemoteRow, ...]:
    d = envelope(value, "rows")
    return _unique(
        tuple(_remote_row(v) for v in array(d["rows"], MAX_REMOTE_ROWS)), "character_id"
    )


def parse_catalogue(value: object, *, nested: bool = False) -> FleetCatalogue:
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
    # A uint32 content hash, not an int4 or a monotonic revision counter.
    return FleetCatalogue(
        integer(d["revision"], 0, 0xFFFFFFFF),
        _unique(tuple(characters), "character_id"),
    )
