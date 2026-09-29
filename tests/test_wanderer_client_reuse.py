"""Connection reuse across polls: one TCP/TLS connection, transparent reconnect.

Issue #300: fetch() must not open a new connection per poll. Reuse is keyed on
the normalized base URL; a server-closed keep-alive surfaces as a retryable
failure path internally (one reconnect) and never changes the FetchResult
contract, timeouts, ETag flow, or auth-failure callback timing.
"""

import http.client
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

ETAG = 'W/"fixture-revision"'
BASE = "https://wanderer.example/deployment"
TOKEN = "private-test-token"


def keepalive_server(responses, close_after=None):
    """Serve `responses` (list of (status, body, headers)) over keep-alive.

    Returns (server, factory, connection_events, request_events).
    close_after[i] truthy closes the connection after request i instead of
    honoring keep-alive.
    """
    from pathlib import Path

    body = (Path(__file__).parent / "fixtures/wanderer/deployed-v1.json").read_bytes()
    lock = threading.Lock()
    connection_events = []  # (host, port, timeout) per factory call
    request_events = []  # path per request

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            with lock:
                index = len(request_events)
                request_events.append(self.path)
            status, payload, headers = responses[min(index, len(responses) - 1)]
            if payload is None:
                payload = body
            self.send_response(status)
            if status in (200, 304):
                self.send_header("X-Wanderer-Locations-Version", "1")
                self.send_header("ETag", ETAG)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            if close_after is not None and close_after[index]:
                self.close_connection = True

    server = HTTPServer(("127.0.0.1", 0), Handler)
    owner = threading.Thread(target=server.serve_forever, daemon=True)
    owner.start()

    def factory(host, port, timeout):
        with lock:
            connection_events.append((host, port, timeout))
        return http.client.HTTPConnection(
            "127.0.0.1", server.server_port, timeout=timeout
        )

    return server, factory, connection_events, request_events


def fetch(client, base=BASE, etag=None):
    return client.fetch(base, "Map-Slug", TOKEN, etag)


def test_second_consecutive_fetch_reuses_the_same_connection():
    from wingman.wanderer.client import Success, WandererClient

    server, factory, connections, requests = keepalive_server([(200, None, {})])
    try:
        client = WandererClient(connection_factory=factory)
        first = fetch(client, etag=ETAG)
        second = fetch(client, etag=ETAG)
        client.close()  # Release the pooled socket before server shutdown.
    finally:
        server.shutdown()
        server.server_close()
    assert isinstance(first, Success)
    assert isinstance(second, Success)
    assert len(connections) == 1
    assert len(requests) == 2


def test_server_closed_keepalive_reconnects_and_still_succeeds():
    from wingman.wanderer.client import Success, WandererClient

    # First response closes the keep-alive; second fetch must transparently
    # reconnect and succeed rather than fail the poll.
    server, factory, connections, requests = keepalive_server(
        [(200, None, {})], close_after=[True]
    )
    try:
        client = WandererClient(connection_factory=factory)
        first = fetch(client, etag=ETAG)
        second = fetch(client, etag=ETAG)
        client.close()
    finally:
        server.shutdown()
        server.server_close()
    assert isinstance(first, Success)
    assert isinstance(second, Success)
    assert len(connections) == 2
    assert len(requests) == 2


def test_idle_ttl_evicts_and_reconnects():
    from wingman.wanderer.client import IDLE_TTL, Success, WandererClient

    clock = [1000.0]
    server, factory, connections, _requests = keepalive_server([(200, None, {})])
    try:
        client = WandererClient(connection_factory=factory, clock=lambda: clock[0])
        first = fetch(client, etag=ETAG)
        clock[0] += IDLE_TTL + 1.0  # Past the idle TTL: connection evicted.
        second = fetch(client, etag=ETAG)
        client.close()
    finally:
        server.shutdown()
        server.server_close()
    assert isinstance(first, Success)
    assert isinstance(second, Success)
    assert len(connections) == 2  # A fresh connection after the idle TTL.


def test_base_url_change_discards_the_old_pooled_connection():
    from wingman.wanderer.client import Success, WandererClient

    server, factory, connections, _requests = keepalive_server([(200, None, {})])
    other, other_factory, other_connections, _ = keepalive_server([(200, None, {})])
    try:
        client = WandererClient(connection_factory=factory)
        first = fetch(client, etag=ETAG)
        # Swap factories mid-flight by pointing the pool's factory at the other
        # server: same client, different base URL.
        client._pool._factory = other_factory
        second = fetch(client, base="https://other.example/deployment", etag=ETAG)
        client.close()
    finally:
        server.shutdown()
        server.server_close()
        other.shutdown()
        other.server_close()
    assert isinstance(first, Success)
    assert isinstance(second, Success)
    assert len(connections) == 1
    assert len(other_connections) == 1  # Different base: no shared connection.


def test_client_close_closes_the_idle_pooled_socket():
    from wingman.wanderer.client import WandererClient

    server, factory, _connections, _requests = keepalive_server([(200, None, {})])
    try:
        client = WandererClient(connection_factory=factory)
        fetch(client, etag=ETAG)
        assert client._pool._idle is not None
        idle_connection = client._pool._idle[2]
        client.close()
        assert client._pool._idle is None
        assert idle_connection.sock is None  # Closed: socket detached.
    finally:
        server.shutdown()
        server.server_close()


def test_worker_close_admission_closes_the_client_pool():
    """Teardown hygiene: no socket outlives close_admission()."""
    from wingman.wanderer.client import WandererClient
    from wingman.wanderer.worker import WandererWorker

    server, factory, _connections, _requests = keepalive_server([(200, None, {})])
    closed = []
    client = WandererClient(connection_factory=factory)
    original_close = client.close
    client.close = lambda: (original_close(), closed.append(True))
    worker = WandererWorker(client, publish=lambda *args: None)
    # The pool must be exercised for close_admission to have something to do:
    # a single fetch leaves one idle pooled connection.
    fetch(client, etag=ETAG)
    assert client._pool._idle is not None
    worker.close_admission()
    assert closed == [True]
    client.close()
    server.shutdown()
    server.server_close()
