"""Signed HTTP transport for authGD's fleet-relay protocol boundary.

Everything here injects a fake transport; no test in this file performs a
real network call. `FakeTransport` mirrors the shape
`tests/test_eveskills_sso.py`'s own `FakeTransport` uses for the identical
reason: it records the built `urllib.request.Request` and serves a canned
JSON body, so assertions can inspect exactly what would have gone over
the wire.
"""

import base64
import hashlib
import io
import json
import urllib.error
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives.serialization import load_der_public_key

from wingman.fleetsharing import client as client_mod
from wingman.fleetsharing import crypto
from wingman.fleetsharing.client import FleetRelayClient, FleetRelayError
from wingman.fleetsharing.model import CatalogueCharacter, FleetCatalogue, PublishRow

ORIGIN = "https://relay.example.test"


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _headers_of(request) -> dict:
    return {key.lower(): value for key, value in request.header_items()}


class FakeTransport:
    """Records every request and serves one canned JSON body."""

    def __init__(self, payload, status=200):
        self.body = json.dumps(payload).encode("utf-8")
        self.status = status
        self.requests = []
        self.timeouts = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        self.timeouts.append(timeout)
        body, status = self.body, self.status

        class Response:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

            @property
            def status(self_inner):
                return status

            def read(self_inner, amount=None):
                return body if amount is None else body[:amount]

        return Response()


def error_transport(status: int):
    """A transport that raises HTTPError, the way urllib does for a
    non-2xx response."""

    def transport(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, status, "Error", {}, io.BytesIO(b"{}")
        )

    return transport


def network_error_transport():
    def transport(request, timeout=None):
        raise OSError("connection refused")

    return transport


class TestOriginValidation:
    def test_rejects_a_plain_http_origin(self):
        with pytest.raises(ValueError, match="https"):
            FleetRelayClient("http://relay.example.test")

    def test_rejects_an_origin_carrying_a_path(self):
        with pytest.raises(ValueError, match="https"):
            FleetRelayClient("https://relay.example.test/api")

    def test_rejects_an_origin_carrying_a_query_string(self):
        with pytest.raises(ValueError, match="https"):
            FleetRelayClient("https://relay.example.test/?x=1")

    def test_accepts_a_bare_https_origin(self):
        FleetRelayClient(ORIGIN, transport=FakeTransport({"protocol": 1}))


class TestDefaultOpenerRefusesRedirects:
    def test_the_default_opener_has_no_redirect_handler(self):
        """Guards `_default_transport`'s actual wiring, matching
        `test_discord.py`'s identical test for the same reason: every
        other test in this file injects a fake transport, so nothing else
        would catch a refactor that rebuilt `_opener` without the
        no-redirect handler."""
        names = [type(h).__name__ for h in client_mod._opener.handlers]
        assert "HTTPRedirectHandler" not in names
        assert "_NoRedirectHandler" in names


class TestSignedRequests:
    def test_fetch_catalogue_sends_exactly_five_signed_headers(self):
        private_key = crypto.generate_private_key()
        public_key = load_der_public_key(crypto.public_key_spki(private_key))
        transport = FakeTransport({"protocol": 1, "revision": 3, "characters": []})
        relay = FleetRelayClient(ORIGIN, transport=transport)
        now = datetime(2026, 1, 1, tzinfo=UTC)

        relay.fetch_catalogue(
            session_id="sess-abc", private_key=private_key, revision=5, now=now
        )

        request = transport.requests[0]
        assert request.full_url == ORIGIN + "/api/fleet/v1/catalogue"
        assert request.get_method() == "GET"
        headers = _headers_of(request)
        signed_names = {
            "x-fleet-session",
            "x-fleet-issued-at",
            "x-fleet-revision",
            "x-fleet-body-sha256",
            "x-fleet-signature",
        }
        assert signed_names <= headers.keys()
        assert headers["x-fleet-session"] == "sess-abc"
        assert headers["x-fleet-issued-at"] == "2026-01-01T00:00:00.000Z"
        assert headers["x-fleet-revision"] == "5"
        assert headers["x-fleet-body-sha256"] == hashlib.sha256(b"").hexdigest()

        canonical = (
            "fleet-v1\nGET\n/api/fleet/v1/catalogue\nsess-abc\n"
            "2026-01-01T00:00:00.000Z\n5\n" + hashlib.sha256(b"").hexdigest()
        ).encode("utf-8")
        signature = headers["x-fleet-signature"]
        assert "=" not in signature
        public_key.verify(_b64url_decode(signature), canonical)

        assert transport.timeouts == [5.0]

    def test_publish_snapshot_signs_the_exact_serialized_body(self):
        private_key = crypto.generate_private_key()
        public_key = load_der_public_key(crypto.public_key_spki(private_key))
        transport = FakeTransport({"protocol": 1})
        relay = FleetRelayClient(ORIGIN, transport=transport)
        now = datetime(2026, 1, 1, tzinfo=UTC)
        rows = (PublishRow(character_id=42, dps=612, ewar=()),)

        relay.publish_snapshot(
            session_id="sess-abc",
            private_key=private_key,
            revision=9,
            rows=rows,
            now=now,
        )

        request = transport.requests[0]
        assert request.full_url == ORIGIN + "/api/fleet/v1/snapshot"
        assert request.get_method() == "PUT"
        body = request.data
        assert json.loads(body) == {
            "protocol": 1,
            "rows": [{"character_id": 42, "dps": 612, "ewar": []}],
        }
        headers = _headers_of(request)
        assert headers["x-fleet-body-sha256"] == hashlib.sha256(body).hexdigest()
        canonical = (
            "fleet-v1\nPUT\n/api/fleet/v1/snapshot\nsess-abc\n"
            "2026-01-01T00:00:00.000Z\n9\n" + hashlib.sha256(body).hexdigest()
        ).encode("utf-8")
        public_key.verify(_b64url_decode(headers["x-fleet-signature"]), canonical)

    def test_publish_snapshot_encodes_active_ewar(self):
        transport = FakeTransport({"protocol": 1})
        relay = FleetRelayClient(ORIGIN, transport=transport)
        rows = (PublishRow(character_id=7, dps=0, ewar=("SCRAM/POINT",)),)

        relay.publish_snapshot(
            session_id="s",
            private_key=crypto.generate_private_key(),
            revision=1,
            rows=rows,
        )

        assert json.loads(transport.requests[0].data)["rows"] == [
            {"character_id": 7, "dps": 0, "ewar": ["SCRAM/POINT"]}
        ]


class TestResponseValidation:
    def test_rejects_a_response_with_the_wrong_protocol_major(self):
        transport = FakeTransport({"protocol": 2, "revision": 1, "characters": []})
        relay = FleetRelayClient(ORIGIN, transport=transport)

        with pytest.raises(FleetRelayError) as excinfo:
            relay.fetch_catalogue(
                session_id="s", private_key=crypto.generate_private_key(), revision=1
            )
        assert excinfo.value.code == "protocol_mismatch"

    def test_rejects_a_response_with_no_protocol_field_at_all(self):
        transport = FakeTransport({"revision": 1, "characters": []})
        relay = FleetRelayClient(ORIGIN, transport=transport)

        with pytest.raises(FleetRelayError) as excinfo:
            relay.fetch_catalogue(
                session_id="s", private_key=crypto.generate_private_key(), revision=1
            )
        assert excinfo.value.code == "protocol_mismatch"

    def test_rejects_a_response_body_that_is_not_valid_json(self):
        transport = FakeTransport({"protocol": 1})
        transport.body = b"not json"
        relay = FleetRelayClient(ORIGIN, transport=transport)

        with pytest.raises(FleetRelayError) as excinfo:
            relay.fetch_catalogue(
                session_id="s", private_key=crypto.generate_private_key(), revision=1
            )
        assert excinfo.value.code == "malformed_response"

    def test_rejects_a_json_response_that_is_not_an_object(self):
        transport = FakeTransport([1, 2, 3])
        relay = FleetRelayClient(ORIGIN, transport=transport)

        with pytest.raises(FleetRelayError) as excinfo:
            relay.fetch_catalogue(
                session_id="s", private_key=crypto.generate_private_key(), revision=1
            )
        assert excinfo.value.code == "malformed_response"

    @pytest.mark.parametrize(
        ("status", "expected_code"),
        [
            (403, "forbidden"),
            (429, "rate_limited"),
            (500, "server_error"),
            (503, "server_error"),
        ],
    )
    def test_status_classification(self, status, expected_code):
        relay = FleetRelayClient(ORIGIN, transport=error_transport(status))

        with pytest.raises(FleetRelayError) as excinfo:
            relay.fetch_catalogue(
                session_id="s", private_key=crypto.generate_private_key(), revision=1
            )
        assert excinfo.value.status == status
        assert excinfo.value.code == expected_code

    def test_a_transport_failure_classifies_as_transport_error_with_no_status(self):
        relay = FleetRelayClient(ORIGIN, transport=network_error_transport())

        with pytest.raises(FleetRelayError) as excinfo:
            relay.fetch_catalogue(
                session_id="s", private_key=crypto.generate_private_key(), revision=1
            )
        assert excinfo.value.status is None
        assert excinfo.value.code == "transport_error"

    def test_error_message_never_contains_the_signed_session_id(self):
        relay = FleetRelayClient(ORIGIN, transport=error_transport(500))

        with pytest.raises(FleetRelayError) as excinfo:
            relay.fetch_catalogue(
                session_id="super-secret-session-id",
                private_key=crypto.generate_private_key(),
                revision=1,
            )
        assert "super-secret-session-id" not in str(excinfo.value)

    def test_error_message_never_contains_the_signature(self):
        private_key = crypto.generate_private_key()
        relay = FleetRelayClient(ORIGIN, transport=error_transport(500))
        with pytest.raises(FleetRelayError) as excinfo:
            relay.fetch_catalogue(session_id="s", private_key=private_key, revision=1)
        message = str(excinfo.value)
        # No unpadded base64url token of plausible signature length (64
        # raw bytes -> 86 chars) appears anywhere in the message.
        assert not any(len(word) >= 80 for word in message.split())


class TestPairing:
    def test_begin_pairing_sends_no_signed_headers_or_cookie(self):
        transport = FakeTransport(
            {
                "protocol": 1,
                "pairing_id": "p-1",
                "approval_url": "https://relay.example.test/fleet/pair/p-1",
                "expires_at": "2026-01-01T00:10:00.000Z",
            }
        )
        relay = FleetRelayClient(ORIGIN, transport=transport)
        private_key = crypto.generate_private_key()
        spki = crypto.public_key_spki(private_key)

        result = relay.begin_pairing(spki)

        request = transport.requests[0]
        assert request.full_url == ORIGIN + "/api/fleet/v1/pairing-requests"
        assert request.get_method() == "POST"
        headers = _headers_of(request)
        assert "x-fleet-session" not in headers
        assert "x-fleet-signature" not in headers
        assert "cookie" not in headers
        body = json.loads(request.data)
        assert body["protocol"] == 1
        assert body["public_key_spki_b64url"] == crypto.public_key_spki_b64url(spki)
        assert "=" not in body["public_key_spki_b64url"]

        assert result.pairing_id == "p-1"
        assert result.approval_url == "https://relay.example.test/fleet/pair/p-1"
        assert result.expires_at == "2026-01-01T00:10:00.000Z"

    def test_complete_pairing_signs_the_given_challenge_and_returns_only_session_and_catalogue(
        self,
    ):
        private_key = crypto.generate_private_key()
        challenge = crypto.pairing_challenge_preimage("p-1")
        transport = FakeTransport(
            {
                "protocol": 1,
                "session_id": "sess-xyz",
                "catalogue": {
                    "revision": 4,
                    "characters": [{"character_id": 42, "character_name": "Alice"}],
                },
            }
        )
        relay = FleetRelayClient(ORIGIN, transport=transport)

        result = relay.complete_pairing("p-1", challenge, private_key)

        request = transport.requests[0]
        assert (
            request.full_url == ORIGIN + "/api/fleet/v1/pairing-requests/p-1/complete"
        )
        headers = _headers_of(request)
        assert "x-fleet-session" not in headers
        assert "cookie" not in headers
        body = json.loads(request.data)
        assert body["protocol"] == 1
        assert body["completion_signature"] == crypto.sign_request(
            private_key, challenge
        )

        assert result.session_id == "sess-xyz"
        assert result.catalogue == FleetCatalogue(
            revision=4,
            characters=(CatalogueCharacter(character_id=42, character_name="Alice"),),
        )
        assert vars(result).keys() == {"session_id", "catalogue"}

    def test_complete_pairing_request_never_carries_the_raw_private_key(self):
        private_key = crypto.generate_private_key()
        challenge = crypto.pairing_challenge_preimage("p-1")
        transport = FakeTransport(
            {
                "protocol": 1,
                "session_id": "s",
                "catalogue": {"revision": 1, "characters": []},
            }
        )
        relay = FleetRelayClient(ORIGIN, transport=transport)

        relay.complete_pairing("p-1", challenge, private_key)

        request = transport.requests[0]
        wire_text = repr(request.data) + repr(_headers_of(request))
        assert private_key.hex() not in wire_text
        assert base64.b64encode(private_key).decode("ascii") not in wire_text

    def test_complete_pairing_rejects_a_malformed_catalogue(self):
        transport = FakeTransport(
            {"protocol": 1, "session_id": "s", "catalogue": {"revision": 1}}
        )
        relay = FleetRelayClient(ORIGIN, transport=transport)

        with pytest.raises(FleetRelayError) as excinfo:
            relay.complete_pairing(
                "p-1",
                crypto.pairing_challenge_preimage("p-1"),
                crypto.generate_private_key(),
            )
        assert excinfo.value.code == "malformed_response"
