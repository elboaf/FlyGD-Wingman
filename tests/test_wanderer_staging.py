"""The outbound prime-staging lane (#297): one HTTPS attempt, typed results.

Mirrors test_wanderer_client.py: real HTTP parsing over loopback with an
injected connection factory, so no test touches a real network. Scheduling
and retries belong to the controller, exactly as the worker owns them for
the read lane.
"""

import http.client
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from wingman.wanderer.staging import StagingClient

BASE = "https://wanderer.example/deployment"
TOKEN = "wmi_v1_00000000-0000-0000-0000-000000000000_" + "a" * 43
EVENT = "0f0e0d0c-0b0a-0908-0706-050403020100"


def record(**overrides):
    """One valid outbound prime record, per the #163 wire contract."""
    prime = {
        "event_id": EVENT,
        "eve_character_id": 90376521,
        "source_solar_system_id": 31001346,
        "system_name": "J123456",
        "flags": {"eol": True, "half_mass": False, "critical": False, "frigate": True},
    }
    prime.update(overrides)
    return prime


def stage(
    status=200,
    body=b'{"staged":true,"event_id":"' + EVENT.encode() + b'"}',
    headers=None,
    *,
    prime=None,
):
    """One stage() roundtrip against a loopback server that answers `status`."""
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            seen.append((self.path, dict(self.headers), self.rfile.read(length)))
            self.send_response(status)
            for key, value in (
                {
                    "Content-Type": "application/json; charset=utf-8",
                    "X-Wanderer-Primes-Version": "1",
                }
                if headers is None
                else headers
            ).items():
                if value is not None:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
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
        result = StagingClient(connection_factory=connection).stage(
            BASE, "Map-Slug", TOKEN, record() if prime is None else prime
        )
        owner.join(2)
        assert not owner.is_alive()
    finally:
        server.server_close()
    return result, seen, connections


def test_stage_success_posts_the_prime_and_returns_a_typed_result():
    from wingman.wanderer.staging import Staged

    result, seen, connections = stage()
    assert result == Staged()
    assert connections == [("wanderer.example", 443, 5.0)]
    path, headers, body = seen[0]
    assert path == "/deployment/api/maps/Map-Slug/prejump-primes"
    assert headers["Authorization"] == "Bearer " + TOKEN
    assert headers["X-Wanderer-Primes-Version"] == "1"
    assert headers["Content-Type"] == "application/json"
    sent = json.loads(body)
    assert sent == {"prime": record()}


def test_error_body_code_refines_the_status_fallback():
    from wingman.wanderer.staging import StagingFailure

    body = json.dumps(
        {"error": "Token scope is not permitted", "code": "scope_forbidden"}
    ).encode()
    result, _, _ = stage(status=403, body=body)
    assert result == StagingFailure("scope_forbidden", 403)
    # A body claiming a code the staging endpoint never sends is untrusted;
    # the status decides.
    body = json.dumps({"error": "nope", "code": "anything_else"}).encode()
    result, _, _ = stage(status=403, body=body)
    assert result.code == "forbidden"


def test_redirect_is_refused_not_followed():
    from wingman.wanderer.staging import StagingFailure

    result, _, _ = stage(
        status=302, headers={"Location": "https://elsewhere.example/x"}
    )
    assert result == StagingFailure("redirect_refused", 302)


def test_oversized_error_body_yields_the_status_fallback():
    from wingman.wanderer.staging import StagingFailure

    result, _, _ = stage(
        status=400, body=b'{"error":"' + b"x" * 4096 + b'","code":"invalid_request"}'
    )
    assert result == StagingFailure("invalid_request", 400)


def test_invalid_configuration_never_opens_a_socket():
    from wingman.wanderer.staging import StagingFailure

    result = StagingClient().stage(BASE, "Map-Slug", TOKEN, {"event_id": ""})
    assert result == StagingFailure("invalid_configuration")


# ---- build_prime_record: engine prime + identity -> #163 wire record ------


def make_prime(
    jcode="J123456",
    flags=("e", "f"),
    event="0f0e0d0c0b0a090807060504030201 00".replace(" ", ""),
):
    from wingman.hotkeys import PrimeRecord

    return PrimeRecord(jcode=jcode, flags=flags, event=event, captured=100.0)


def make_identity(character_id=90376521, solar_system_id=31001346):
    from wingman.wanderer.model import PrimeIdentity

    return PrimeIdentity(character_id=character_id, solar_system_id=solar_system_id)


def test_build_prime_record_formats_the_engine_event_and_maps_flags():
    from wingman.wanderer.staging import build_prime_record

    out = build_prime_record(make_prime(), make_identity(), BASE, "Map-Slug")
    assert out == {
        "event_id": EVENT,
        "eve_character_id": 90376521,
        "source_solar_system_id": 31001346,
        "system_name": "J123456",
        "flags": {"eol": True, "half_mass": False, "critical": False, "frigate": True},
    }


def test_build_prime_record_accepts_a_hyphenated_event_verbatim():
    from wingman.wanderer.staging import build_prime_record

    prime = make_prime(event=EVENT)
    out = build_prime_record(prime, make_identity(), BASE, "Map-Slug")
    assert out["event_id"] == EVENT


def test_build_prime_record_rejects_a_none_identity_and_unknown_source():
    from wingman.wanderer.staging import build_prime_record

    with pytest.raises(ValueError):
        build_prime_record(make_prime(), None, BASE, "Map-Slug")
    unmapped = make_identity(solar_system_id=None)
    with pytest.raises(ValueError):
        build_prime_record(make_prime(), unmapped, BASE, "Map-Slug")


def test_build_prime_record_rejects_a_non_uuid_event():
    from wingman.wanderer.staging import build_prime_record

    with pytest.raises(ValueError):
        build_prime_record(
            make_prime(event="not-a-uuid-at-all"), make_identity(), BASE, "Map-Slug"
        )
