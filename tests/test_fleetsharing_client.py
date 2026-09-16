"""Actual signed/pre-session HTTP boundary; no external network calls.

Doubles record Requests and return bounded streams. They add v2 framing, never
translate a payload or hide a legacy worker's pending migration.
"""

import base64
import hashlib
import io
import json
import urllib.error
from datetime import UTC, datetime
from email.message import Message
from urllib.parse import urlsplit

import pytest
from cryptography.hazmat.primitives.serialization import load_der_public_key

from wingman.fleetsharing import client as client_mod
from wingman.fleetsharing import crypto
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing.client import FleetRelayClient, FleetRelayError
from wingman.fleetsharing.model import CatalogueCharacter, FleetCatalogue

ORIGIN = "https://relay.example.test"
SESSION = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"
PAIRING = "22222222-2222-2222-8222-222222222222"
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _headers_of(request) -> dict:
    return {key.lower(): value for key, value in request.header_items()}


def framing_headers(binding=None):
    headers = Message()
    headers["Content-Type"] = "application/json; charset=utf-8"
    headers["Cache-Control"] = "no-store"
    if binding is not None:
        headers["X-Fleet-Request-Binding"] = binding
    return headers


def request_binding(request):
    """Independent literal contract, not the production binding helper."""
    headers = _headers_of(request)
    url = urlsplit(request.full_url)
    path = url.path + ("?" + url.query if url.query else "")
    if "x-fleet-session" in headers:
        canonical = "\n".join(
            (
                "fleet-v1",
                request.get_method(),
                path,
                headers["x-fleet-session"],
                headers["x-fleet-issued-at"],
                headers["x-fleet-revision"],
                headers["x-fleet-body-sha256"],
            )
        ).encode()
        return hashlib.sha256(b"fleet-api-v2\n" + canonical).hexdigest()
    preimage = "\n".join(
        (
            "fleet-api-v2-pre-session",
            f"{url.scheme}://{url.netloc}",
            "POST",
            path,
            headers.get("x-fleet-attempt", "missing"),
            hashlib.sha256(request.data or b"").hexdigest(),
        )
    ).encode()
    return hashlib.sha256(preimage).hexdigest()


class Response(io.BytesIO):
    def __init__(self, raw, headers, status=200):
        super().__init__(raw)
        self.headers = headers
        self.status = status
        self.reads = []

    def read(self, amount=-1):
        self.reads.append(amount)
        return super().read(amount)


class FakeTransport:
    """publication is retained only as shared old-worker test syntax.

    It does not negotiate or translate the supplied body into a valid v2 success.
    """

    def __init__(self, payload, status=200, *, publication=False):
        self.publication = publication
        self.body = json.dumps(payload).encode("utf-8")
        self.status = status
        self.requests = []
        self.timeouts = []
        self.responses = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        self.timeouts.append(timeout)
        response = Response(
            self.body,
            framing_headers(request_binding(request) if self.status == 200 else None),
            self.status,
        )
        self.responses.append(response)
        return response


def error_transport(status: int, payload=None):
    def transport(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url,
            status,
            "Error",
            framing_headers(),
            io.BytesIO(json.dumps(payload or {}).encode()),
        )

    return transport


def network_error_transport():
    def transport(request, timeout=None):
        raise OSError("connection refused")

    return transport


def auth(**changes):
    return {
        "session_id": SESSION,
        "private_key": bytes(32),
        "revision": 5,
        "now": NOW,
        **changes,
    }


def verify_signed(request, *, method, path, revision):
    headers = _headers_of(request)
    digest = hashlib.sha256(request.data or b"").hexdigest()
    assert headers["x-fleet-body-sha256"] == digest
    canonical = f"fleet-v1\n{method}\n/api/fleet/v2/{path}\n{SESSION}\n2026-01-01T00:00:00.000Z\n{revision}\n{digest}".encode()
    load_der_public_key(crypto.public_key_spki(bytes(32))).verify(
        _b64url_decode(headers["x-fleet-signature"]),
        canonical,
    )


class TestOriginValidation:
    @pytest.mark.parametrize(
        "origin",
        [
            "http://relay.example.test",
            "https://relay.example.test/api",
            "https://relay.example.test/?x=1",
        ],
    )
    def test_rejects_non_https_or_non_origin_urls(self, origin):
        with pytest.raises(ValueError, match="https"):
            FleetRelayClient(origin)

    def test_accepts_a_bare_https_origin(self):
        FleetRelayClient(ORIGIN, transport=FakeTransport({"protocol": 2}))


class TestDefaultOpenerRefusesRedirects:
    def test_the_default_opener_has_no_redirect_handler(self):
        # All HTTP tests inject a transport, so separately pin production wiring.
        names = [type(h).__name__ for h in client_mod._opener.handlers]
        assert "HTTPRedirectHandler" not in names
        assert "_NoRedirectHandler" in names
        guard = next(
            h
            for h in client_mod._opener.handlers
            if type(h).__name__ == "_NoRedirectHandler"
        )
        assert (
            guard.redirect_request(None, None, 302, "redirect", {}, "https://evil.test")
            is None
        )


class TestSignedRequests:
    def test_fetch_catalogue_sends_exactly_five_signed_headers(self):
        transport = FakeTransport({"protocol": 2, "revision": 3, "characters": []})
        result = FleetRelayClient(ORIGIN, transport=transport).fetch_catalogue(**auth())
        assert result == FleetCatalogue(3, ())
        request = transport.requests[0]
        assert request.full_url == ORIGIN + "/api/fleet/v2/catalogue"
        assert request.get_method() == "GET" and request.data is None
        headers = _headers_of(request)
        assert {k for k in headers if k.startswith("x-fleet-")} == {
            "x-fleet-session",
            "x-fleet-issued-at",
            "x-fleet-revision",
            "x-fleet-body-sha256",
            "x-fleet-signature",
        }
        assert headers["x-fleet-session"] == SESSION
        assert headers["x-fleet-revision"] == "5"
        assert "=" not in headers["x-fleet-signature"]
        verify_signed(request, method="GET", path="catalogue", revision=5)
        assert transport.timeouts == [5.0]

    def test_publish_snapshot_signs_the_exact_serialized_body(self):
        transport = FakeTransport({"protocol": 2})
        row = p.CombatRow(
            42, 612, None, 25, (p.Effect("POINT", (p.Observation("é", 30),)),)
        )
        FleetRelayClient(ORIGIN, transport=transport).publish_snapshot(
            **auth(revision=9),
            sampled_at_ms=1000,
            rows=(row,),
        )
        request = transport.requests[0]
        assert request.full_url == ORIGIN + "/api/fleet/v2/snapshot"
        assert request.get_method() == "PUT"
        assert (
            request.data
            == b'{"protocol": 2, "sampled_at_ms": 1000, "rows": [{"character_id": 42, "outgoing_dps": 612, "incoming_dps": null, "activity_age_ms": 25, "effects": [{"kind": "POINT", "observations": [{"name": "\\u00e9", "age_ms": 30}]}]}]}'
        )
        verify_signed(request, method="PUT", path="snapshot", revision=9)

    def test_publish_snapshot_encodes_distinct_active_effects(self):
        transport = FakeTransport({"protocol": 2})
        row = p.CombatRow(
            7,
            0,
            0,
            0,
            tuple(
                p.Effect(k, (p.Observation(None, 0),))
                for k in ("SCRAM", "POINT", "NEUT")
            ),
        )
        FleetRelayClient(ORIGIN, transport=transport).publish_snapshot(
            **auth(),
            sampled_at_ms=1000,
            rows=(row,),
        )
        assert json.loads(transport.requests[0].data)["rows"] == [
            {
                "character_id": 7,
                "outgoing_dps": 0,
                "incoming_dps": 0,
                "activity_age_ms": 0,
                "effects": [
                    {"kind": k, "observations": [{"name": None, "age_ms": 0}]}
                    for k in ("SCRAM", "POINT", "NEUT")
                ],
            }
        ]

    def test_publish_snapshot_rejects_an_invalid_batch_before_any_network_call(self):
        transport = FakeTransport({"protocol": 2})
        with pytest.raises(ValueError):
            FleetRelayClient(ORIGIN, transport=transport).publish_snapshot(
                **auth(),
                sampled_at_ms=1000,
                rows=(p.CombatRow(1, 1, 0, 0, ()), p.CombatRow(1, 2, 0, 0, ())),
            )
        assert transport.requests == []

    def test_renew_session_sends_an_empty_signed_body_and_returns_expires_at(self):
        transport = FakeTransport(
            {"protocol": 2, "expires_at": "2026-01-01T00:30:00.000Z"}
        )
        result = FleetRelayClient(ORIGIN, transport=transport).renew_session(
            **auth(revision=7)
        )
        assert result == "2026-01-01T00:30:00.000Z"
        request = transport.requests[0]
        assert request.full_url == ORIGIN + "/api/fleet/v2/session"
        assert request.get_method() == "PUT" and request.data is None
        assert _headers_of(request)["x-fleet-revision"] == "7"
        verify_signed(request, method="PUT", path="session", revision=7)

    def test_renew_session_rejects_a_response_missing_expires_at(self):
        with pytest.raises(FleetRelayError) as exc:
            FleetRelayClient(
                ORIGIN, transport=FakeTransport({"protocol": 2})
            ).renew_session(**auth())
        assert exc.value.code == "malformed_response"


class TestResponseValidation:
    @pytest.mark.parametrize(
        "payload,code",
        [
            ({"protocol": 1, "revision": 1, "characters": []}, "protocol_mismatch"),
            ({"protocol": 3, "revision": 1, "characters": []}, "protocol_mismatch"),
            ({"revision": 1, "characters": []}, "protocol_mismatch"),
            ([1, 2, 3], "malformed_response"),
        ],
    )
    def test_rejects_wrong_version_missing_version_or_non_object(self, payload, code):
        with pytest.raises(FleetRelayError) as exc:
            FleetRelayClient(ORIGIN, transport=FakeTransport(payload)).fetch_catalogue(
                **auth()
            )
        assert exc.value.code == code

    def test_rejects_a_response_body_that_is_not_valid_json(self):
        transport = FakeTransport({"protocol": 2})
        transport.body = b"not json"
        with pytest.raises(FleetRelayError) as exc:
            FleetRelayClient(ORIGIN, transport=transport).fetch_catalogue(**auth())
        assert exc.value.code == "malformed_response"

    @pytest.mark.parametrize(
        "status,code,accepted",
        [
            (403, "forbidden", True),
            (429, "rate_limited", True),
            (500, "service_unavailable", False),
            (503, "service_unavailable", True),
        ],
    )
    def test_status_classification_requires_closed_error(self, status, code, accepted):
        with pytest.raises(FleetRelayError) as exc:
            FleetRelayClient(
                ORIGIN,
                transport=error_transport(status, {"protocol": 2, "error": code}),
            ).fetch_catalogue(**auth())
        assert exc.value.code == (code if accepted else "malformed_response")
        assert exc.value.status == (status if accepted else None)

    def test_a_transport_failure_classifies_as_transport_error_with_no_status(self):
        with pytest.raises(FleetRelayError) as exc:
            FleetRelayClient(
                ORIGIN, transport=network_error_transport()
            ).fetch_catalogue(**auth())
        assert exc.value.status is None and exc.value.code == "transport_error"

    def test_error_message_never_contains_the_signed_session_id(self):
        with pytest.raises(FleetRelayError) as exc:
            FleetRelayClient(
                ORIGIN, transport=error_transport(500, {"echo": SESSION})
            ).fetch_catalogue(**auth())
        assert SESSION not in str(exc.value)

    def test_error_message_excludes_the_actual_signature_even_when_the_error_body_echoes_it(
        self,
    ):
        signatures = []

        def transport(request, timeout=None):
            signature = _headers_of(request)["x-fleet-signature"]
            signatures.append(signature)
            raise urllib.error.HTTPError(
                request.full_url,
                500,
                "Error",
                framing_headers(),
                io.BytesIO(signature.encode()),
            )

        with pytest.raises(FleetRelayError) as exc:
            FleetRelayClient(ORIGIN, transport=transport).fetch_catalogue(**auth())
        assert signatures[0] not in str(exc.value)
        assert signatures[0] not in exc.value.code


def pairing_payload(approval_url=None):
    return {
        "protocol": 2,
        "pairing_id": PAIRING,
        "approval_url": approval_url or ORIGIN + "/fleet/pair/" + PAIRING,
        "expires_at": "2026-01-01T00:10:00.000Z",
    }


def paired_payload():
    return {
        "protocol": 2,
        "session_id": SESSION,
        "catalogue": {
            "revision": 4,
            "characters": [{"character_id": 42, "character_name": "Alice"}],
        },
    }


class TestPairing:
    def test_begin_pairing_sends_no_signed_headers_or_cookie(self):
        transport = FakeTransport(pairing_payload())
        spki = crypto.public_key_spki(bytes(32))
        result = FleetRelayClient(ORIGIN, transport=transport).begin_pairing(spki)
        request = transport.requests[0]
        assert request.full_url == ORIGIN + "/api/fleet/v2/pairing-requests"
        assert request.get_method() == "POST"
        headers = _headers_of(request)
        assert {k for k in headers if k.startswith("x-fleet-")} == {"x-fleet-attempt"}
        assert "cookie" not in headers
        body = json.loads(request.data)
        assert body == {
            "protocol": 2,
            "public_key_spki_b64url": crypto.public_key_spki_b64url(spki),
            "requested_capabilities": [],
        }
        assert "=" not in body["public_key_spki_b64url"]
        assert result.pairing_id == PAIRING
        assert result.approval_url == ORIGIN + "/fleet/pair/" + PAIRING
        assert result.expires_at == "2026-01-01T00:10:00.000Z"

    def test_begin_pairing_resolves_a_relative_approval_url_against_the_configured_origin(
        self,
    ):
        result = FleetRelayClient(
            ORIGIN, transport=FakeTransport(pairing_payload("/fleet/pair/" + PAIRING))
        ).begin_pairing(crypto.public_key_spki(bytes(32)))
        assert result.approval_url == ORIGIN + "/fleet/pair/" + PAIRING

    @pytest.mark.parametrize(
        "url",
        [
            "https://evil.example.test/fleet/pair/x",
            "http://relay.example.test/fleet/pair/x",
            "https://attacker:pw@relay.example.test/fleet/pair/x",
            "//evil.example.test/fleet/pair/x",
            "/fleet/pair/x y",
            "/fleet\\pair/x",
        ],
    )
    def test_begin_pairing_rejects_unsafe_approval_url(self, url):
        with pytest.raises(FleetRelayError) as exc:
            FleetRelayClient(
                ORIGIN, transport=FakeTransport(pairing_payload(url))
            ).begin_pairing(crypto.public_key_spki(bytes(32)))
        assert exc.value.code == "malformed_response"

    def test_complete_pairing_signs_the_given_challenge_and_returns_only_session_and_catalogue(
        self,
    ):
        challenge = crypto.pairing_challenge_preimage(PAIRING)
        transport = FakeTransport(paired_payload())
        result = FleetRelayClient(ORIGIN, transport=transport).complete_pairing(
            PAIRING, challenge, bytes(32)
        )
        request = transport.requests[0]
        assert (
            request.full_url
            == ORIGIN + "/api/fleet/v2/pairing-requests/" + PAIRING + "/complete"
        )
        headers = _headers_of(request)
        assert "x-fleet-session" not in headers and "cookie" not in headers
        assert json.loads(request.data) == {
            "protocol": 2,
            "completion_signature": crypto.sign_request(bytes(32), challenge),
        }
        assert result.session_id == SESSION
        assert result.catalogue == FleetCatalogue(4, (CatalogueCharacter(42, "Alice"),))
        assert vars(result).keys() == {"session_id", "catalogue"}

    @pytest.mark.parametrize(
        "pairing_id",
        [
            "../snapshot",
            "p-1\r\nX-Injected: 1",
            "",
            "p-1",
            "weird/id",
            "weird%2Fid",
            PAIRING + "/",
            PAIRING + "?x=1",
            PAIRING.replace("-", "%2d"),
        ],
    )
    def test_complete_pairing_rejects_invalid_or_encoded_selector_before_network(
        self, pairing_id
    ):
        # V2 rejects selectors instead of percent-quoting an arbitrary opaque ID.
        transport = FakeTransport(paired_payload())
        with pytest.raises(ValueError, match="unexpected shape"):
            FleetRelayClient(ORIGIN, transport=transport).complete_pairing(
                pairing_id, crypto.pairing_challenge_preimage(pairing_id), bytes(32)
            )
        assert transport.requests == []

    def test_complete_pairing_request_never_carries_the_raw_private_key(self):
        private = crypto.generate_private_key()
        transport = FakeTransport(paired_payload())
        FleetRelayClient(ORIGIN, transport=transport).complete_pairing(
            PAIRING, crypto.pairing_challenge_preimage(PAIRING), private
        )
        request = transport.requests[0]
        wire_text = repr(request.data) + repr(_headers_of(request))
        assert private.hex() not in wire_text
        assert base64.b64encode(private).decode() not in wire_text

    def test_complete_pairing_rejects_a_malformed_catalogue(self):
        payload = {**paired_payload(), "catalogue": {"revision": 1}}
        with pytest.raises(FleetRelayError) as exc:
            FleetRelayClient(ORIGIN, transport=FakeTransport(payload)).complete_pairing(
                PAIRING, crypto.pairing_challenge_preimage(PAIRING), bytes(32)
            )
        assert exc.value.code == "malformed_response"
