"""One authenticated prime-staging HTTPS attempt; retries belong to the controller.

The outbound half of the pre-jump prime handoff (#281, ADR 0001). The wire
contract is upstream guarzo/wanderer#163's PrejumpPrimeController: a dedicated
prime-scope Bearer token, a bounded `{"prime": ...}` JSON body, an optional
`X-Wanderer-Primes-Version: 1` header we always send, 200 with
`{"staged": true}` (or an idempotent replay of the same event id) meaning
staged. Like client.py: no proxy/cookie jar, no redirect handling — a 3xx is
a refusal — and a bounded body read on the response side.
"""

from __future__ import annotations

import http.client
import json
import re
import ssl
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from .credentials import CredentialError, validate_token
from .model import PrimeIdentity, normalize_base_url, normalize_map_identifier

EVENT_ID_MAX_CHARS = 64
SYSTEM_NAME_MAX_BYTES = 255


def build_prime_record(
    prime, identity: PrimeIdentity, base_url: str, map_identifier: str
) -> dict:
    """The #163 wire record, or raise ValueError for anything unstageable.

    Pure, so the controller tests it without HTTP. Formats the engine's
    32-hex event id into the canonical hyphenated UUID the server requires;
    a value that does not fit a UUID is a rejected record, never a mangled
    one.
    """
    if identity is None or identity.solar_system_id is None:
        raise ValueError("prime has no usable identity")
    event = prime.event
    if len(event) == 32 and all(c in "0123456789abcdef" for c in event):
        event = f"{event[:8]}-{event[8:12]}-{event[12:16]}-{event[16:20]}-{event[20:]}"
    if not _UUID.fullmatch(event):
        raise ValueError("prime event id is not a UUID")
    name = prime.jcode.strip()
    if not 0 < len(name.encode("utf-8")) <= SYSTEM_NAME_MAX_BYTES:
        raise ValueError("prime system name is empty or oversized")
    return {
        "event_id": event,
        "eve_character_id": identity.character_id,
        "source_solar_system_id": identity.solar_system_id,
        "system_name": name,
        "flags": {
            "eol": "e" in prime.flags,
            "half_mass": "/" in prime.flags,
            "critical": "c" in prime.flags,
            "frigate": "f" in prime.flags,
        },
    }


CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 5.0
MAX_BODY_BYTES = 2048

# The server casts Ecto.UUID; only the hyphenated canonical form casts.
_UUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)

ErrorCode = Literal[
    "invalid_configuration",
    "invalid_response",
    "redirect_refused",
    "timeout",
    "tls_error",
    "transport_error",
    # Server-declared staging outcomes (#163 controller @errors).
    "invalid_request",
    "invalid_token",
    "scope_forbidden",
    "wrong_map",
    "forbidden",
    "disabled",
    "subscription_required",
    "map_not_found",
    "not_acceptable",
    "rate_limited",
    "service_unavailable",
]


@dataclass(frozen=True)
class Staged:
    """The server accepted the prime (or replayed a live identical event)."""


@dataclass(frozen=True)
class StagingFailure:
    code: ErrorCode
    status: int | None = None

    @property
    def authentication_failed(self) -> bool:
        # A denied prime credential must stop the feature, not just this POST.
        return self.status in (401, 403)


StageResult = Staged | StagingFailure

# #163's error bodies are `{"error": "...", "code": atom}`. The body is
# untrusted: the status picks the fallback, a recognized body code refines it.
_STATUS_CODES: dict[int, ErrorCode] = {
    400: "invalid_request",
    401: "invalid_token",
    403: "forbidden",
    404: "map_not_found",
    406: "not_acceptable",
    429: "rate_limited",
}
_BODY_CODES: dict[str, ErrorCode] = {
    "invalid_request": "invalid_request",
    "invalid_token": "invalid_token",
    "scope_forbidden": "scope_forbidden",
    "wrong_map": "wrong_map",
    "forbidden": "forbidden",
    "disabled": "disabled",
    "subscription_required": "subscription_required",
    "map_not_found": "map_not_found",
    "not_acceptable": "not_acceptable",
    "rate_limited": "rate_limited",
    "service_unavailable": "service_unavailable",
}


def _connection(host: str, port: int, timeout: float) -> http.client.HTTPSConnection:
    return http.client.HTTPSConnection(
        host, port, timeout=timeout, context=ssl.create_default_context()
    )


def _valid_prime(prime: object) -> bool:
    """The #163 controller's bounds, enforced before any socket is opened."""
    if not isinstance(prime, dict) or prime.keys() != {
        "event_id",
        "eve_character_id",
        "source_solar_system_id",
        "system_name",
        "flags",
    }:
        return False
    event = prime["event_id"]
    if (
        not isinstance(event, str)
        or len(event) > EVENT_ID_MAX_CHARS
        or not _UUID.fullmatch(event)
    ):
        return False
    for key in ("eve_character_id", "source_solar_system_id"):
        value = prime[key]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            return False
    name = prime["system_name"]
    if not isinstance(name, str):
        return False
    try:
        if not 0 < len(name.strip().encode("utf-8")) <= SYSTEM_NAME_MAX_BYTES:
            return False
    except UnicodeError:
        return False
    flags = prime["flags"]
    if not isinstance(flags, dict) or not set(flags) <= {
        "eol",
        "half_mass",
        "critical",
        "frigate",
    }:
        return False
    return all(isinstance(value, bool) for value in flags.values())


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


class StagingClient:
    def __init__(
        self,
        *,
        connection_factory: Callable[
            [str, int, float], http.client.HTTPConnection
        ] = _connection,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._connection = connection_factory
        self._clock = clock

    def stage(
        self,
        base: str,
        map: str,
        token: str,
        prime: dict,
    ) -> StageResult:
        try:
            base = normalize_base_url(base)
            map = normalize_map_identifier(map)
            token = validate_token(token)
            if not _valid_prime(prime):
                raise ValueError("prime does not satisfy the staging contract")
            body = json.dumps({"prime": prime}, separators=(",", ":")).encode("utf-8")
        except (ValueError, TypeError, CredentialError):
            return StagingFailure("invalid_configuration")
        parsed = urlsplit(base)
        connection = response = None
        try:
            connection = self._connection(
                parsed.hostname, parsed.port or 443, CONNECT_TIMEOUT
            )
            connection.connect()
            connection.sock.settimeout(READ_TIMEOUT)
            connection.request(
                "POST",
                parsed.path + f"/api/maps/{map}/prejump-primes",
                body=body,
                headers={
                    "Authorization": "Bearer " + token,
                    "Content-Type": "application/json",
                    "X-Wanderer-Primes-Version": "1",
                },
            )
            response = connection.getresponse()
            if 300 <= response.status < 400:
                return StagingFailure("redirect_refused", response.status)
            if response.status != 200:
                return self._error(response)
            self._drain(response)
            return Staged()
        except ssl.SSLError:
            return StagingFailure("tls_error")
        except TimeoutError:
            return StagingFailure("timeout")
        except OSError:
            return StagingFailure("transport_error")
        except Exception:  # noqa: BLE001 — transport boundary cannot expose tokens/peer text.
            return StagingFailure("transport_error")
        finally:
            for owner in (response, connection):
                if owner is not None:
                    with suppress(Exception):
                        owner.close()

    def _error(self, response: http.client.HTTPResponse) -> StagingFailure:
        fallback = _STATUS_CODES.get(response.status)
        if fallback is None:
            fallback = (
                "service_unavailable"
                if 500 <= response.status < 600
                else "invalid_response"
            )
        try:
            raw = response.read(MAX_BODY_BYTES + 1)
            if len(raw) > MAX_BODY_BYTES:
                return StagingFailure(fallback, response.status)
            data = json.loads(raw.decode("utf-8"), object_pairs_hook=_object)
            if (
                isinstance(data, dict)
                and data.keys() == {"error", "code"}
                and isinstance(data["error"], str)
                and isinstance(data["code"], str)
                and data["code"] in _BODY_CODES
            ):
                return StagingFailure(_BODY_CODES[data["code"]], response.status)
        except Exception:  # noqa: BLE001, S110 — discard untrusted bodies; the status is authoritative.
            pass
        return StagingFailure(fallback, response.status)

    @staticmethod
    def _drain(response: http.client.HTTPResponse) -> None:
        # Bounded read so a lying Content-Length cannot stream forever.
        while response.read(4096):
            pass
