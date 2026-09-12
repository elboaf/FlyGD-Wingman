"""Pure deployed-v1 contract, identity binding and monotonic display decisions.

Authority and synthetic fixture provenance: tests/fixtures/wanderer/README.md.
No partial acceptance: a bad record must not mix two server revisions or reveal
hidden map metadata. Snapshot assembly time is not a renewed observation.
"""

from __future__ import annotations

import ipaddress
import json
import math
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from datetime import datetime
from types import MappingProxyType
from urllib.parse import urlsplit

MAX_RESPONSE_BYTES = 1_048_576
MAX_RECORDS = 2000
MAX_NAME_CODEPOINTS = 255
MAX_NAME_BYTES = 1024
MAX_BASE_URL_BYTES = 2048
MAX_MAP_BYTES = 255
MAX_CONDITIONAL_BYTES = 1024
FRESHNESS_SECONDS = 15.0
MAX_ID = 9_007_199_254_740_991

_SEGMENT = re.compile(r"[A-Za-z0-9._~-]+")
_UUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")
_UTC_TIME = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|\+00:00)"
)


def normalize_base_url(value: str) -> str:
    """Canonical HTTPS application base, retaining its case-sensitive prefix.

    ASCII DNS (punycode for IDNs), IPv4 and bracketed IPv6 are supported. Refuse
    ambiguous numeric hosts, encoded paths, dot traversal and URL-parser cleanup
    of control characters. Normalization must never change a secret destination.
    """
    try:
        _require(isinstance(value, str) and len(value) <= MAX_BASE_URL_BYTES)
        value = value.strip(" ")
        _require(all(32 < ord(c) < 127 for c in value))
        _require(not any(c in value for c in "\\?#@%"))
        parsed = urlsplit(value)
        host, port = parsed.hostname, parsed.port
        _require(parsed.scheme == "https" and bool(host))
        _require(not parsed.netloc.endswith(":"))
        _require(port is None or 1 <= port <= 65535)
        if "[" in parsed.netloc or "]" in parsed.netloc:
            authority = re.fullmatch(r"\[([^\[\]]+)\](?::[0-9]+)?", parsed.netloc)
            _require(authority is not None)
            host = f"[{ipaddress.IPv6Address(authority[1]).compressed}]"
        else:
            _require(len(host) <= 253)
            _require(
                all(
                    re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part)
                    for part in host.rstrip(".").split(".")
                )
            )
            last = host.rstrip(".").split(".")[-1]
            if last.isdigit() or last.startswith("0x"):
                host = str(ipaddress.IPv4Address(host))
        prefix = parsed.path.removesuffix("/")
        if prefix:
            _require(prefix.startswith("/"))
            _require(
                all(
                    _SEGMENT.fullmatch(part) and part not in (".", "..")
                    for part in prefix[1:].split("/")
                )
            )
        return (
            f"https://{host}" + (f":{port}" if port not in (None, 443) else "") + prefix
        )
    except ValueError:
        pass  # Never retain URL-parser exception context containing user input.
    raise ValueError("Wanderer URL must be a valid HTTPS application base.")


def normalize_map_identifier(value: str) -> str:
    """One bounded slug or UUID, never a path or a query. Slug case is identity."""
    if isinstance(value, str):
        value = value.strip(" ")
        if (
            len(value) <= MAX_MAP_BYTES
            and _SEGMENT.fullmatch(value)
            and value not in (".", "..")
        ):
            return value.lower() if _UUID.fullmatch(value) else value
    raise ValueError("Wanderer map must be a valid slug or UUID.")


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError("Invalid Wanderer value.")


def _name(value: object, *, nullable: bool = False) -> str | None:
    if nullable and value is None:
        return None
    _require(isinstance(value, str) and len(value) <= MAX_NAME_CODEPOINTS)
    _require(len(value.encode("utf-8")) <= MAX_NAME_BYTES)
    # These reach a small single-line native label, not a rich-text renderer.
    _require(
        not any(
            unicodedata.category(c) in ("Cc", "Cf", "Cs", "Zl", "Zp") for c in value
        )
    )
    return value


def normalize_character_name(value: str) -> str:
    """Exact matching only: NFC, outer whitespace trim, then Unicode casefold."""
    try:
        _name(value)
        result = unicodedata.normalize("NFC", value.strip()).casefold()
        _require(bool(result))
        return result
    except ValueError:
        pass
    raise ValueError("Wanderer character name is invalid.")


@dataclass(frozen=True)
class LocationRecord:
    character_id: int
    character_name: str
    tracked: bool
    online: bool | None
    solar_system_id: int | None
    solar_system_name: str | None
    display_name: str | None
    map_system_visible: bool
    location_observed_at: datetime | None
    map_system_updated_at: datetime | None
    deadline_monotonic: float | None

    def display_at(self, now_monotonic: float) -> str | None:
        """A 304 caller retains this record, including the original deadline."""
        if (
            self.deadline_monotonic is None
            or not now_monotonic < self.deadline_monotonic
        ):
            return None
        effective = (self.display_name or "").strip() if self.map_system_visible else ""
        return effective or (self.solar_system_name or "").strip() or None


@dataclass(frozen=True)
class Snapshot:
    records: tuple[LocationRecord, ...]
    observed_at: datetime
    revision: str
    receipt_monotonic: float
    by_name: Mapping[str, LocationRecord] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "by_name",
            MappingProxyType(
                {normalize_character_name(r.character_name): r for r in self.records}
            ),
        )

    def record_for(self, character_name: str) -> LocationRecord | None:
        return self.by_name.get(normalize_character_name(character_name))


_RECORD_KEYS = frozenset(
    f.name for f in fields(LocationRecord) if f.name != "deadline_monotonic"
)


class SnapshotError(ValueError):
    """A whole candidate is incompatible; never carries raw fields or bodies."""

    def __init__(self) -> None:
        super().__init__("Wanderer snapshot is invalid or exceeds supported limits.")


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def _reject_number(_value: str) -> None:
    # The deployed schema has only integer IDs, never floats or JS NaN/Infinity.
    raise ValueError("Invalid JSON number.")


def _timestamp(value: object) -> datetime:
    _require(
        isinstance(value, str) and len(value) <= 32 and bool(_UTC_TIME.fullmatch(value))
    )
    return datetime.fromisoformat(value)


def _id(value: object) -> bool:
    return type(value) is int and 1 <= value <= MAX_ID


def _record(data: object, observed_at: datetime, receipt: float) -> LocationRecord:
    _require(isinstance(data, dict) and data.keys() == _RECORD_KEYS)
    _require(_id(data["character_id"]))
    normalize_character_name(data["character_name"])
    _require(data["tracked"] is True)
    _require(data["online"] is None or type(data["online"]) is bool)
    _require(type(data["map_system_visible"]) is bool)
    _name(data["solar_system_name"], nullable=True)
    _name(data["display_name"], nullable=True)
    location_at = map_at = deadline = None
    if data["solar_system_id"] is None:
        _require(data["online"] is not True and data["map_system_visible"] is False)
        _require(
            all(
                data[key] is None
                for key in (
                    "solar_system_name",
                    "display_name",
                    "location_observed_at",
                    "map_system_updated_at",
                )
            )
        )
    else:
        _require(_id(data["solar_system_id"]) and data["online"] is True)
        location_at = _timestamp(data["location_observed_at"])
        age = (observed_at - location_at).total_seconds()
        _require(age >= 0)
        deadline = receipt + max(0.0, FRESHNESS_SECONDS - age)
        _require(math.isfinite(deadline))
        if data["map_system_visible"]:
            map_at = _timestamp(data["map_system_updated_at"])
            _require(map_at <= observed_at)
        else:
            _require(
                data["display_name"] is None and data["map_system_updated_at"] is None
            )
    return LocationRecord(
        **(
            data
            | {"location_observed_at": location_at, "map_system_updated_at": map_at}
        ),
        deadline_monotonic=deadline,
    )


def parse_snapshot(body: bytes, receipt_monotonic: float) -> Snapshot:
    """Validate one complete deployed snapshot and anchor its server-relative age.

    No desktop wall-clock reads and no partial roster. Timestamps older than the
    grace window get an already-expired deadline; future observations are invalid.
    Exceptions are raised outside the parser's except block to discard even the
    hidden __context__, which can otherwise retain sensitive response data.
    """
    try:
        _require(isinstance(body, bytes) and len(body) <= MAX_RESPONSE_BYTES)
        _require(
            type(receipt_monotonic) in (int, float) and math.isfinite(receipt_monotonic)
        )
        data = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
        _require(
            isinstance(data, dict)
            and data.keys() == {"data", "observed_at", "revision"}
        )
        observed_at = _timestamp(data["observed_at"])
        revision = data["revision"]
        # Leave room for the weak ETag's W/ and quotes in a conditional header.
        _require(
            isinstance(revision, str)
            and 1 <= len(revision) <= MAX_CONDITIONAL_BYTES - 4
            and bool(_SEGMENT.fullmatch(revision))
        )
        _require(isinstance(data["data"], list) and len(data["data"]) <= MAX_RECORDS)
        records = tuple(
            _record(row, observed_at, receipt_monotonic) for row in data["data"]
        )
        ids = [r.character_id for r in records]
        _require(ids == sorted(set(ids)))
        _require(
            len({normalize_character_name(r.character_name) for r in records})
            == len(records)
        )
        return Snapshot(records, observed_at, revision, float(receipt_monotonic))
    except (ValueError, OverflowError, RecursionError):
        pass
    raise SnapshotError()
