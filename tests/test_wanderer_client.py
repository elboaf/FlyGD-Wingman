"""Real HTTP parsing over loopback; scripted raw I/O proves deadline boundaries."""

import http.client
import io
import json
import ssl
import threading
from contextlib import suppress
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

BODY = (Path(__file__).parent / "fixtures/wanderer/deployed-v1.json").read_bytes()
ETAG = 'W/"fixture-revision"'
BASE = "https://wanderer.example/deployment"
TOKEN = "private-test-token"
HEADERS = {
    "Content-Type": "application/json; charset=utf-8",
    "X-Wanderer-Locations-Version": "1",
    "ETag": ETAG,
}


def roundtrip(status=200, body=BODY, headers=None, *, etag=None):
    from wingman.wanderer.client import WandererClient

    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append((self.path, dict(self.headers)))
            self.send_response(status)
            for key, value in (HEADERS if headers is None else headers).items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            # Rejected headers/oversized bodies intentionally close early.
            with suppress(BrokenPipeError, ConnectionResetError):
                self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    owner = threading.Thread(target=server.handle_request, daemon=True)
    owner.start()
    connections = []

    def connection(host, port, timeout):
        connections.append((host, port, timeout))
        return http.client.HTTPConnection(
            "127.0.0.1", server.server_port, timeout=timeout
        )

    try:
        result = WandererClient(connection_factory=connection, clock=lambda: 100).fetch(
            BASE, "Map-Slug", TOKEN, etag
        )
        owner.join(2)
        assert not owner.is_alive()
    finally:
        server.server_close()
    return result, seen, connections


def test_success_preserves_prefix_and_sends_only_explicit_auth_and_contract_headers():
    from wingman.wanderer.client import Success

    result, seen, connections = roundtrip(etag=ETAG)
    assert isinstance(result, Success)
    assert result.etag == ETAG
    assert result.snapshot.records[0].display_at(100) == "HOME"
    assert result.snapshot.records[0].deadline_monotonic == 114
    assert connections == [("wanderer.example", 443, 5.0)]
    path, headers = seen[0]
    assert path == "/deployment/api/maps/Map-Slug/tracked-character-locations"
    assert headers["Authorization"] == "Bearer " + TOKEN
    assert headers["Accept"] == "application/json"
    assert headers["X-Wanderer-Locations-Version"] == "1"
    assert headers["If-None-Match"] == ETAG
    assert headers["Accept-Encoding"] == "identity"
    assert not {"Cookie", "X-API-Key"} & headers.keys()


def test_304_has_no_snapshot_and_requires_matching_conditional():
    from wingman.wanderer.client import Unchanged

    result, _, _ = roundtrip(304, b"", etag=ETAG)
    assert result == Unchanged(ETAG)
    for conditional in (None, 'W/"other"'):
        result, _, _ = roundtrip(304, b"", etag=conditional)
        assert result.code == "invalid_response"


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirect_is_never_followed_or_authorized(status):
    result, seen, connections = roundtrip(
        status, b"", {"Location": "https://secret-collector.example/"}
    )
    assert result.code == "redirect_refused"
    assert len(seen) == len(connections) == 1


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"X-Wanderer-Locations-Version": None}, "unsupported_version"),
        ({"X-Wanderer-Locations-Version": "2"}, "unsupported_version"),
        ({"X-Wanderer-Locations-Version": "1, 1"}, "unsupported_version"),
        ({"ETag": None}, "invalid_response"),
        ({"ETag": '"fixture-revision"'}, "invalid_response"),
        ({"ETag": 'W/"other"'}, "invalid_response"),
        ({"ETag": 'W/"x", W/"y"'}, "invalid_response"),
        ({"ETag": 'W/"' + "x" * 1021 + '"'}, "invalid_response"),
        ({"Content-Type": "text/html"}, "invalid_response"),
        ({"Content-Type": None}, "invalid_response"),
        ({"Content-Encoding": "gzip"}, "invalid_response"),
    ],
)
def test_success_headers_fail_closed(changes, code):
    headers = HEADERS | changes
    result, _, _ = roundtrip(
        headers={k: v for k, v in headers.items() if v is not None}
    )
    assert result.code == code


@pytest.mark.parametrize(
    "body",
    [b"<html>private-test-token</html>", b"{}", b"x" * 1048577],
    # Pytest puts the ID in PYTEST_CURRENT_TEST; Windows caps it at 32767 chars.
    ids=["html", "empty-object", "oversized"],
)
def test_malformed_or_oversized_success_is_not_partially_accepted(body):
    result, _, _ = roundtrip(body=body)
    assert result.code == "invalid_response"
    assert TOKEN not in repr(result)


@pytest.mark.parametrize(
    "status,code",
    [
        (400, "invalid_request"),
        (401, "invalid_token"),
        (403, "scope_forbidden"),
        (403, "wrong_map"),
        (403, "disabled"),
        (403, "subscription_required"),
        (404, "map_not_found"),
        (406, "not_acceptable"),
        (429, "rate_limited"),
        (503, "invalid_snapshot"),
        (503, "service_unavailable"),
    ],
)
def test_deployed_error_codes_are_status_bound_and_messages_never_escape(status, code):
    body = json.dumps({"error": TOKEN, "code": code}).encode()
    result, _, _ = roundtrip(status, body, {"Content-Type": "application/json"})
    assert result.code == code
    assert result.status == status
    assert result.authentication_failed == (status in (401, 403))
    assert TOKEN not in repr(result)


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"<html>secret</html>",
        b"x" * 2049,
        b'{"error":"secret","code":"disabled"}',
        b'{"error":"secret","code":"invalid_token","extra":1}',
        b'{"error":"secret","code":"wrong_map","code":"invalid_token"}',
    ],
)
def test_malformed_error_cannot_disguise_auth_rejection(body):
    result, _, _ = roundtrip(401, body)
    assert result.code == "invalid_token"
    assert result.authentication_failed
    assert "secret" not in repr(result)


@pytest.mark.parametrize(
    "value,want",
    [
        ("60", 60.0),
        ("0", 0.0),
        ("99999999", 300.0),
        ("-1", 0.0),
        ("1.5", 0.0),
        ("NaN", 0.0),
        ("1, 2", 0.0),
        ("x" * 2000, 0.0),
    ],
)
def test_retry_after_is_bounded_delta_seconds(value, want):
    result, _, _ = roundtrip(429, b"", {"Retry-After": value})
    assert result.retry_after == want


@pytest.mark.parametrize(
    "base,map_id,token,etag",
    [
        ("http://localhost", "map", TOKEN, None),
        (BASE, "../map", TOKEN, None),
        (BASE, "map", "secret\r\nX: bad", None),
        (BASE, "map", TOKEN, 'W/"bad\r\nX: secret"'),
        (BASE, "map", TOKEN, 'W/"' + "a" * 1021 + '"'),
    ],
)
def test_invalid_request_never_opens_connection(base, map_id, token, etag):
    from wingman.wanderer.client import WandererClient

    def forbidden(*_args):
        pytest.fail("invalid configuration reached network")

    result = WandererClient(connection_factory=forbidden).fetch(
        base, map_id, token, etag
    )
    assert result.code == "invalid_configuration"
    assert "secret" not in repr(result)


class Clock:
    now = 100.0

    def __call__(self):
        return self.now


class Raw(io.BytesIO):
    def __init__(self, wire, clock, *, step=0.0, chunk=8192, failure=None):
        super().__init__(wire)
        self.clock, self.step, self.chunk, self.failure = clock, step, chunk, failure
        self.bytes_read = 0

    def readinto(self, buffer):
        if self.failure:
            raise self.failure
        self.clock.now += self.step
        data = self.read(min(len(buffer), self.chunk))
        buffer[: len(data)] = data
        self.bytes_read += len(data)
        return len(data)


class Socket:
    def __init__(self, raw):
        self.raw = raw
        self.timeouts = []
        self.closed = False

    def settimeout(self, value):
        self.timeouts.append(value)

    def makefile(self, mode, buffering=None):
        assert mode == "rb" and buffering == 0
        return self.raw

    def sendall(self, _data):
        pass

    def close(self):
        self.closed = True


def scripted(wire, *, step=0, chunk=8192, failure=None, auth_seen=None):
    from wingman.wanderer.client import WandererClient

    clock = Clock()
    raw = Raw(wire, clock, step=step, chunk=chunk, failure=failure)
    sock = Socket(raw)

    class Connection(http.client.HTTPConnection):
        def connect(self):
            self.sock = sock

    client = WandererClient(
        connection_factory=lambda host, port, timeout: Connection(
            host, port, timeout=timeout
        ),
        clock=clock,
    )
    callbacks = {}
    if auth_seen is not None:
        callbacks["on_authentication_failure"] = lambda result: auth_seen.append(
            (result, clock())
        )
    return client.fetch(BASE, "map", TOKEN, **callbacks), raw, sock


def wire(body=BODY, *, headers=b"", status=b"200 OK"):
    return (
        b"HTTP/1.1 " + status + b"\r\nContent-Type: application/json\r\n"
        b'X-Wanderer-Locations-Version: 1\r\nETag: W/"fixture-revision"\r\n'
        + headers
        + b"\r\n"
        + body
    )


@pytest.mark.parametrize(
    "extra,code",
    [
        (b'ETag: W/"fixture-revision"\r\n', "invalid_response"),
        (b"X-Wanderer-Locations-Version: 1\r\n", "unsupported_version"),
    ],
)
def test_duplicate_success_headers_are_not_merged(extra, code):
    result, _, sock = scripted(wire(headers=extra))
    assert result.code == code
    assert sock.closed


@pytest.mark.parametrize("chunked", [False, True])
def test_total_deadline_bounds_trickle_including_chunk_framing(chunked):
    body = b"1\r\nx\r\n" * 100 if chunked else b"x" * 500
    header = b"Transfer-Encoding: chunked\r\n" if chunked else b""
    result, raw, sock = scripted(wire(body, headers=header), step=0.2, chunk=5)
    assert result.code == "timeout"
    assert raw.bytes_read < len(wire(body, headers=header))
    assert all(0 < t <= 5 for t in sock.timeouts)
    assert min(sock.timeouts) < 1
    assert sock.closed


def test_body_bound_without_content_length_and_incomplete_body():
    result, raw, sock = scripted(wire(b"x" * 1100000))
    assert result.code == "invalid_response"
    # Buffered HTTP reads may prefetch one buffer, never the remaining body.
    assert raw.bytes_read <= 1048577 + 8192
    assert sock.closed
    result, _, _ = scripted(wire(headers=b"Content-Length: 999999\r\n"))
    assert result.code == "invalid_response"


@pytest.mark.parametrize(
    "failure,code",
    [
        (TimeoutError(TOKEN), "timeout"),
        (OSError(TOKEN), "transport_error"),
        (ssl.SSLCertVerificationError(TOKEN), "tls_error"),
        (http.client.HTTPException(TOKEN), "transport_error"),
    ],
)
def test_transport_failure_is_single_attempt_safe_and_closed(failure, code, caplog):
    result, _, sock = scripted(wire(), failure=failure)
    assert result.code == code
    assert TOKEN not in repr(result) + caplog.text
    assert sock.closed


@pytest.mark.parametrize(
    "status,code",
    [(b"401 Unauthorized", "invalid_token"), (b"403 Forbidden", "forbidden")],
)
def test_slow_auth_error_preserves_denial_despite_body_deadline(status, code):
    result, raw, sock = scripted(wire(b"x" * 500, status=status), step=0.2, chunk=5)
    assert result.authentication_failed and result.code == code
    assert raw.bytes_read < 500
    assert sock.closed


@pytest.mark.parametrize("status", [b"401 Unauthorized", b"403 Forbidden"])
def test_auth_signal_precedes_slow_body_and_contains_no_external_text(status):
    auth_seen = []
    result, raw, _ = scripted(
        wire(b"x" * 500, status=status), step=0.2, chunk=5, auth_seen=auth_seen
    )
    assert len(auth_seen) == 1
    signal, when = auth_seen[0]
    assert signal.authentication_failed and signal.status == result.status
    assert when < raw.clock.now  # The body then ran out its separate I/O budget.
    assert TOKEN not in repr(signal)


def test_default_factory_uses_verified_https(monkeypatch):
    from wingman.wanderer.client import WandererClient

    seen = []

    def connection(host, port, *, timeout, context):
        seen.append((host, port, timeout, context))
        raise OSError(TOKEN)

    monkeypatch.setattr(http.client, "HTTPSConnection", connection)
    result = WandererClient().fetch(BASE, "map", TOKEN)
    assert result.code == "transport_error"
    assert len(seen) == 1
    assert seen[0][:3] == ("wanderer.example", 443, 5.0)
    assert seen[0][3].check_hostname
    assert seen[0][3].verify_mode == ssl.CERT_REQUIRED
