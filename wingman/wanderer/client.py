"""One authenticated HTTPS attempt; scheduling and all retries belong to worker.

No proxy/cookie jar, redirect handler or production HTTP escape. The socket's
raw reader enforces a monotonic budget below HTTP buffering/chunk parsing: an
ordinary per-read timeout alone lets a trickling peer extend a body forever.
"""

from __future__ import annotations

import http.client
import io
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
from .model import (
    MAX_CONDITIONAL_BYTES,
    MAX_RESPONSE_BYTES,
    Snapshot,
    normalize_base_url,
    normalize_map_identifier,
    parse_snapshot,
)

CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 5.0
BODY_DEADLINE = 10.0
MAX_ERROR_BYTES = 2048
MAX_RETRY_AFTER = 300.0

ErrorCode = Literal[
    "invalid_configuration",
    "invalid_response",
    "unsupported_version",
    "redirect_refused",
    "timeout",
    "tls_error",
    "transport_error",
    "invalid_request",
    "invalid_token",
    "forbidden",
    "scope_forbidden",
    "wrong_map",
    "disabled",
    "subscription_required",
    "map_not_found",
    "not_acceptable",
    "rate_limited",
    "invalid_snapshot",
    "service_unavailable",
]


@dataclass(frozen=True)
class Success:
    snapshot: Snapshot
    etag: str


@dataclass(frozen=True)
class Unchanged:
    etag: str


@dataclass(frozen=True)
class Failure:
    code: ErrorCode
    status: int | None = None
    retry_after: float = 0.0

    @property
    def authentication_failed(self) -> bool:
        # Even malformed/unknown 403 bodies deny permission to use cached data.
        return self.status in (401, 403)


FetchResult = Success | Unchanged | Failure
ConnectionFactory = Callable[[str, int, float], http.client.HTTPConnection]
_ETAG = re.compile(r'W/"[A-Za-z0-9._~-]+"')
_ERRORS: dict[int, tuple[ErrorCode, ...]] = {
    400: ("invalid_request",),
    401: ("invalid_token",),
    403: (
        "forbidden",
        "scope_forbidden",
        "wrong_map",
        "disabled",
        "subscription_required",
    ),
    404: ("map_not_found",),
    406: ("not_acceptable",),
    429: ("rate_limited",),
    503: ("service_unavailable", "invalid_snapshot"),
}


def _connection(host: str, port: int, timeout: float) -> http.client.HTTPSConnection:
    return http.client.HTTPSConnection(
        host, port, timeout=timeout, context=ssl.create_default_context()
    )


def _valid_etag(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= MAX_CONDITIONAL_BYTES
        and _ETAG.fullmatch(value) is not None
    )


class _DeadlineReader(io.RawIOBase):
    def __init__(self, raw, sock, deadline: float, clock: Callable[[], float]):
        self._raw, self._sock = raw, sock
        self._deadline, self._clock = deadline, clock

    def readable(self):
        return True

    def readinto(self, buffer):
        remaining = self._deadline - self._clock()
        if remaining <= 0:
            raise TimeoutError
        self._sock.settimeout(min(READ_TIMEOUT, remaining))
        count = self._raw.readinto(buffer)
        if self._clock() >= self._deadline:
            raise TimeoutError
        return count

    def close(self):
        try:
            self._raw.close()
        finally:
            super().close()


class _DeadlineSocket:
    """HTTPResponse's reader owns a socket file reference after Connection: close."""

    def __init__(self, sock, deadline: float, clock: Callable[[], float]):
        self._sock, self._deadline, self._clock = sock, deadline, clock

    def makefile(self, mode):
        return io.BufferedReader(
            _DeadlineReader(
                self._sock.makefile(mode, buffering=0),
                self._sock,
                self._deadline,
                self._clock,
            )
        )

    def close(self):
        self._sock.close()


def _one(response: http.client.HTTPResponse, name: str) -> str | None:
    values = response.headers.get_all(name, [])
    return values[0] if len(values) == 1 else None


def _json_media(response: http.client.HTTPResponse) -> bool:
    value = _one(response, "Content-Type")
    return value is not None and value.lower() in (
        "application/json",
        "application/json; charset=utf-8",
    )


def _bounded_body(response: http.client.HTTPResponse, limit: int) -> bytes:
    lengths = response.headers.get_all("Content-Length", [])
    expected = None
    if lengths:
        if (
            len(lengths) != 1
            or not re.fullmatch(r"[0-9]{1,10}", lengths[0])
            or response.headers.get_all("Transfer-Encoding")
        ):
            raise ValueError
        expected = int(lengths[0])
        if expected > limit:
            raise ValueError
    encodings = response.headers.get_all("Content-Encoding", [])
    if encodings not in ([], ["identity"]):
        raise ValueError
    transfer = response.headers.get_all("Transfer-Encoding", [])
    if transfer not in ([], ["chunked"]):
        raise ValueError
    body = bytearray()
    while len(body) <= limit:
        chunk = response.read1(min(8192, limit + 1 - len(body)))
        if not chunk:
            break
        body.extend(chunk)
    if len(body) > limit or (expected is not None and len(body) != expected):
        raise ValueError
    return bytes(body)


def _retry_after(response: http.client.HTTPResponse) -> float:
    # Deployed v1 sends delta seconds. Refuse arbitrary dates/large parser inputs;
    # neither a desktop wall clock nor an invalid hint can accelerate cadence.
    value = _one(response, "Retry-After")
    if value and re.fullmatch(r"[0-9]{1,10}", value):
        return min(MAX_RETRY_AFTER, float(value))
    return 0.0


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _error(response: http.client.HTTPResponse) -> Failure:
    allowed = _ERRORS.get(response.status, ())
    fallback: ErrorCode = (
        allowed[0]
        if allowed
        else "service_unavailable"
        if 500 <= response.status < 600
        else "invalid_response"
    )
    retry = _retry_after(response)
    try:
        body = _bounded_body(response, MAX_ERROR_BYTES)
        if _json_media(response):
            data = json.loads(body.decode("utf-8"), object_pairs_hook=_object)
            if (
                isinstance(data, dict)
                and data.keys() == {"code", "error"}
                and isinstance(data["error"], str)
                and data["code"] in allowed
            ):
                return Failure(data["code"], response.status, retry)
    except Exception:  # noqa: BLE001 — discard untrusted bodies/errors; retain auth status.
        return Failure(fallback, response.status, retry)
    return Failure(fallback, response.status, retry)


class WandererClient:
    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory = _connection,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._connection = connection_factory
        self._clock = clock

    def fetch(
        self, base: str, map: str, token: str, etag: str | None = None
    ) -> FetchResult:
        try:
            base = normalize_base_url(base)
            map = normalize_map_identifier(map)
            token = validate_token(token)
            if etag is not None and not _valid_etag(etag):
                raise ValueError
        except (ValueError, CredentialError):
            return Failure("invalid_configuration")
        parsed = urlsplit(base)
        connection = response = None
        try:
            connection = self._connection(
                parsed.hostname, parsed.port or 443, CONNECT_TIMEOUT
            )
            connection.connect()
            connection.sock.settimeout(READ_TIMEOUT)
            headers = {
                "Authorization": "Bearer " + token,
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "X-Wanderer-Locations-Version": "1",
            }
            if etag is not None:
                headers["If-None-Match"] = etag
            connection.request(
                "GET",
                parsed.path + f"/api/maps/{map}/tracked-character-locations",
                headers=headers,
            )
            # This includes response headers and chunk framing, not only payload.
            connection.sock = _DeadlineSocket(
                connection.sock, self._clock() + BODY_DEADLINE, self._clock
            )
            response = connection.getresponse()
            if 300 <= response.status < 400 and response.status != 304:
                return Failure("redirect_refused", response.status)
            if response.status not in (200, 304):
                return _error(response)
            if _one(response, "X-Wanderer-Locations-Version") != "1":
                return Failure("unsupported_version", response.status)
            received_etag = _one(response, "ETag")
            if not _valid_etag(received_etag) or not _json_media(response):
                return Failure("invalid_response", response.status)
            if response.status == 304:
                if etag is None or etag != received_etag:
                    return Failure("invalid_response", 304)
                return Unchanged(received_etag)
            body = _bounded_body(response, MAX_RESPONSE_BYTES)
            snapshot = parse_snapshot(body, self._clock())
            if received_etag != f'W/"{snapshot.revision}"':
                return Failure("invalid_response", 200)
            return Success(snapshot, received_etag)
        except ssl.SSLError:
            return Failure("tls_error")
        except TimeoutError:
            return Failure("timeout")
        except ValueError:
            return Failure("invalid_response")
        except Exception:  # noqa: BLE001 — transport boundary cannot expose tokens/peer text.
            return Failure("transport_error")
        finally:
            # Cleanup failures must not replace a safe result with a secret-bearing
            # socket exception. HTTPResponse may already own the closed connection.
            for owner in (response, connection):
                if owner is not None:
                    with suppress(Exception):
                        owner.close()
