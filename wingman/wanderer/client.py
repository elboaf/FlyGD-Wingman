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
import threading
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
IDLE_TTL = 60.0

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
AuthFailureCallback = Callable[[Failure], None]
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


def _error(
    response: http.client.HTTPResponse,
    on_authentication_failure: AuthFailureCallback | None,
) -> Failure:
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
        # Denial is already authoritative at the headers. A slow/malformed body
        # may refine diagnostics, but must not postpone invalidation of locations.
        if response.status in (401, 403) and on_authentication_failure is not None:
            on_authentication_failure(Failure(fallback, response.status, retry))
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


class _PooledConnection:
    """A keep-alive connection checked out for one request, returned after.

    Wraps the connection transparently (`__getattr__`); `close()` — the
    fetch teardown's error/timeout path — discards instead of returning a
    suspect socket to the pool.
    """

    def __init__(self, connection, on_return):
        self._connection = connection  # None: no pooled lease (must connect)
        self._on_return = on_return

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def swap_socket(self, replacement):
        """Assign on the underlying connection so http.client internals see it."""
        self._connection.sock = replacement

    def release(self):
        """Healthy response fully consumed: return the connection to the pool."""
        connection, self._connection = self._connection, None
        self._on_return(connection)

    def close(self):
        # Teardown must never return a suspect socket to the pool.
        self.discard()

    def discard(self):
        connection, self._connection = self._connection, None
        self._on_return(None)
        if connection is not None:
            with suppress(Exception):
                connection.close()


class _ConnectionPool:
    """Keep-alive connection reuse keyed on normalized base URL.

    Threading model: `fetch()` runs on the worker's scheduler/request thread
    only, but the idle slot is lock-guarded so `close()` from teardown is safe
    from any thread. A server-closed keep-alive resurfaces as ordinary request
    I/O failure inside `fetch()`; the retry there opens one fresh connection.
    """

    def __init__(self, factory: ConnectionFactory, idle_ttl: float, clock):
        self._factory, self._idle_ttl, self._clock = factory, idle_ttl, clock
        self._lock = threading.Lock()
        self._idle: tuple[str, float, http.client.HTTPConnection] | None = None
        self._closed = False

    def lease(self, key: str, host: str, port: int) -> _PooledConnection:
        with self._lock:
            if self._closed:
                # Teardown ran; fetches after close still work (the worker
                # stops calling them) but never repopulate the pool.
                return _PooledConnection(
                    self._factory(host, port, CONNECT_TIMEOUT),
                    lambda _connection: None,
                )
            cached = self._idle
            self._idle = None
            self._pending_key = key
        if cached is not None:
            stale_key, _, connection = cached
            if stale_key != key or self._clock() - cached[1] > self._idle_ttl:
                with suppress(Exception):
                    connection.close()  # Evicted: wrong base or idle past TTL.
                connection = None
            if connection is not None:
                return _PooledConnection(connection, self._store)
        return _PooledConnection(
            self._factory(host, port, CONNECT_TIMEOUT), self._store
        )

    def _store(self, connection):
        with self._lock:
            if self._closed:
                # Teardown already ran; never repopulate the pool afterwards.
                if connection is not None:
                    with suppress(Exception):
                        connection.close()
                return
            key = self._pending_key
            self._idle = (
                None if connection is None else (key, self._clock(), connection)
            )

    def close(self):
        with self._lock:
            cached, self._idle, self._closed = self._idle, None, True
        if cached is not None and cached[2] is not None:
            with suppress(Exception):
                cached[2].close()


class WandererClient:
    def __init__(
        self,
        *,
        connection_factory: ConnectionFactory = _connection,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._connection = connection_factory
        self._clock = clock
        self._pool = _ConnectionPool(connection_factory, IDLE_TTL, clock)

    def close(self) -> None:
        """Close any pooled idle connection (worker teardown)."""
        self._pool.close()

    def fetch(
        self,
        base: str,
        map: str,
        token: str,
        etag: str | None = None,
        *,
        on_authentication_failure: AuthFailureCallback | None = None,
    ) -> FetchResult:
        """Signal known auth denial before body I/O; return final safe diagnostics.

        The optional signal runs on this request's caller, not on the scheduler.
        It must only hand off cached state, never wait on UI/native/disk work.
        """
        try:
            base = normalize_base_url(base)
            map = normalize_map_identifier(map)
            token = validate_token(token)
            if etag is not None and not _valid_etag(etag):
                raise ValueError
        except (ValueError, CredentialError):
            return Failure("invalid_configuration")
        parsed = urlsplit(base)
        key = f"{parsed.hostname}:{parsed.port or 443}"
        try:
            return self._attempt(
                parsed, key, map, token, etag, on_authentication_failure
            )
        except ssl.SSLError:
            return Failure("tls_error")
        except TimeoutError:
            return Failure("timeout")
        except ValueError:
            return Failure("invalid_response")
        except Exception:  # noqa: BLE001 — transport boundary cannot expose tokens/peer text.
            return Failure("transport_error")

    def _attempt(
        self, parsed, key, map, token, etag, on_authentication_failure
    ) -> FetchResult:
        """One pooled keep-alive attempt; a stale socket gets one fresh retry.

        The retry happens only when no response headers were seen — the request
        may already have been sent, but this is an idempotent GET, so a single
        re-send on a fresh connection is safe and cadence-neutral (the worker
        still counts one fetch per poll: superseded requests consume the
        lane's cadence).
        """
        connection = response = None
        keep = False
        try:
            for attempt in (0, 1):
                try:
                    connection = self._pool.lease(
                        key, parsed.hostname, parsed.port or 443
                    )
                    if connection.sock is None:
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
                    connection.swap_socket(
                        _DeadlineSocket(
                            connection.sock, self._clock() + BODY_DEADLINE, self._clock
                        )
                    )
                    response = connection.getresponse()
                    break
                except ssl.SSLError:
                    raise
                except (OSError, http.client.HTTPException):
                    # Server closed the keep-alive before any response: the
                    # request may have been sent but no headers were seen, so
                    # one retry of this idempotent GET on a fresh connection
                    # is safe and cadence-neutral.
                    connection.discard()  # The stale socket is not re-pooled.
                    if attempt == 1:
                        raise
                    connection = None
                    response = None
            if 300 <= response.status < 400 and response.status != 304:
                return Failure("redirect_refused", response.status)
            if response.status not in (200, 304):
                return _error(response, on_authentication_failure)
            if _one(response, "X-Wanderer-Locations-Version") != "1":
                return Failure("unsupported_version", response.status)
            received_etag = _one(response, "ETag")
            if not _valid_etag(received_etag):
                return Failure("invalid_response", response.status)
            if response.status == 304:
                if etag is None or etag != received_etag:
                    return Failure("invalid_response", 304)
                keep = True  # A 304 has no body: the exchange is fully consumed.
                return Unchanged(received_etag)
            # A 304 has no body; only a 200 needs the JSON representation header.
            if not _json_media(response):
                return Failure("invalid_response", 200)
            body = _bounded_body(response, MAX_RESPONSE_BYTES)
            snapshot = parse_snapshot(body, self._clock())
            if received_etag != f'W/"{snapshot.revision}"':
                return Failure("invalid_response", 200)
            keep = True  # Body fully consumed: the connection is cleanly idle.
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
            if response is not None:
                with suppress(Exception):
                    response.close()
            if connection is not None:
                if keep:
                    # Fully consumed exchange (200 body read or empty 304):
                    # restore the raw socket reference and return the
                    # connection to the pool. Anything else (error statuses
                    # with unread bodies, malformed framing) discards.
                    # response.close() detached the socket (fp -> None) — that
                    # detachment is exactly the keep-alive handback; the
                    # DeadlineSocket wrapper now belongs to the released
                    # response, and the connection needs its raw socket back.
                    raw_socket = (
                        connection.sock._sock
                        if isinstance(connection.sock, _DeadlineSocket)
                        else None
                    )
                    if raw_socket is not None:
                        connection.swap_socket(raw_socket)
                        connection.release()
                    # else: the socket never returned (already detached) —
                    # nothing pooled; drop the wrapper silently.
                else:
                    connection.discard()
