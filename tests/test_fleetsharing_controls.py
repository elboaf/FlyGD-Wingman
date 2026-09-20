"""Single-attempt control/recovery requests through the actual v2 HTTP boundary."""

import base64
import copy
import hashlib
import http.client
import io
import json
import traceback
import urllib.error
from dataclasses import replace
from uuid import UUID as UUIDValue

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.serialization import load_der_public_key
from test_fleetsharing_client import (
    ORIGIN,
    FakeTransport,
    _b64url_decode,
    _headers_of,
    error_transport,
    framing_headers,
    request_binding,
)
from test_fleetsharing_config import BRACKETED_INVALID_ORIGINS
from test_fleetsharing_protocol import (
    CHALLENGE,
    DATE,
    DEVICE,
    ELIGIBILITY,
    FIXTURE,
    PARTICIPATION,
    RECONNECTED,
    ROW,
    START,
    STOP,
    TOKEN,
    UUID,
)

from wingman.fleetsharing import crypto
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing.client import FleetRelayClient, FleetRelayError

V = FIXTURE["valid"]
STOP_COMMAND = p.parse_source_command(STOP)
START_COMMAND = p.parse_source_command(START)


def signed():
    return {
        "session_id": TOKEN,
        "private_key": crypto.generate_private_key(),
        "revision": 7,
    }


@pytest.mark.parametrize(
    "name,method,path,payload,kwargs,expected",
    [
        ("fetch_device", "GET", "device", DEVICE, {}, p.parse_device(DEVICE)),
        (
            "acknowledge_capabilities",
            "PUT",
            "device",
            DEVICE,
            {"capabilities": ("shared-source-v1",)},
            p.parse_device(DEVICE),
        ),
        (
            "set_participation",
            "PUT",
            "participation",
            {"protocol": 2, "participation": PARTICIPATION},
            {"enabled": False, "expected_generation": 0},
            p.Participation(False, 0),
        ),
        (
            "fetch_eligibility",
            "GET",
            "eligibility",
            ELIGIBILITY,
            {},
            p.parse_eligibility(ELIGIBILITY),
        ),
        (
            "fetch_sources",
            "GET",
            "sources",
            V["sources"],
            {},
            p.parse_sources(V["sources"]),
        ),
        (
            "control_source",
            "PUT",
            "sources",
            V["source_stop_result"],
            {"command": STOP_COMMAND},
            p.parse_source_result(V["source_stop_result"], STOP_COMMAND),
        ),
        (
            "read_snapshot",
            "GET",
            "snapshot",
            V["combat_get"],
            {},
            p.parse_snapshot(V["combat_get"]),
        ),
    ],
)
def test_control_methods_sign_exact_request_and_return_dto(
    name, method, path, payload, kwargs, expected
):
    transport = FakeTransport(payload)
    relay = FleetRelayClient(ORIGIN, transport=transport)
    auth = signed()
    assert getattr(relay, name)(**auth, **kwargs) == expected
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.get_method() == method
    assert request.full_url == ORIGIN + "/api/fleet/v2/" + path
    headers = _headers_of(request)
    if method == "GET":
        assert request.data is None
    elif name == "control_source":
        assert json.loads(request.data) == STOP
    else:
        assert json.loads(request.data) == {
            "protocol": 2,
            **{k: list(v) if isinstance(v, tuple) else v for k, v in kwargs.items()},
        }
    digest = hashlib.sha256(request.data or b"").hexdigest()
    assert headers["x-fleet-body-sha256"] == digest
    canonical = f"fleet-v1\n{method}\n/api/fleet/v2/{path}\n{TOKEN}\n{headers['x-fleet-issued-at']}\n7\n{digest}".encode()
    load_der_public_key(crypto.public_key_spki(auth["private_key"])).verify(
        _b64url_decode(headers["x-fleet-signature"]), canonical
    )


def test_source_control_rejects_a_response_for_another_intent():
    payload = copy.deepcopy(V["source_start_result"])
    payload["source"]["source_id"] = "00000000-0000-0000-0000-000000000000"
    with pytest.raises(FleetRelayError) as exc:
        FleetRelayClient(ORIGIN, transport=FakeTransport(payload)).control_source(
            **signed(), command=START_COMMAND
        )
    assert exc.value.code == "malformed_response"


def test_start_does_not_refresh_original_intent_or_allocate_a_revision():
    transport = FakeTransport(V["source_start_result"])
    relay = FleetRelayClient(ORIGIN, transport=transport)
    auth = signed()
    relay.control_source(**auth, command=START_COMMAND)
    relay.control_source(**{**auth, "revision": 8}, command=START_COMMAND)
    assert [int(_headers_of(r)["x-fleet-revision"]) for r in transport.requests] == [
        7,
        8,
    ]
    assert transport.requests[0].data == transport.requests[1].data
    for request in transport.requests:
        assert json.loads(request.data) == START


@pytest.mark.parametrize(
    "name,kwargs",
    [
        ("acknowledge_capabilities", {"capabilities": ("unknown",)}),
        ("acknowledge_capabilities", {"capabilities": ("shared-source-v1",) * 2}),
        ("set_participation", {"enabled": 1, "expected_generation": 0}),
        ("set_participation", {"enabled": False, "expected_generation": True}),
        ("set_participation", {"enabled": False, "expected_generation": 2147483647}),
        (
            "control_source",
            {"command": replace(STOP_COMMAND, expected_generation=2147483647)},
        ),
        (
            "control_source",
            {"command": replace(START_COMMAND, intent_created_at="invalid")},
        ),
    ],
)
def test_invalid_control_fails_before_network(name, kwargs):
    transport = FakeTransport(DEVICE)
    with pytest.raises(ValueError):
        getattr(FleetRelayClient(ORIGIN, transport=transport), name)(
            **signed(), **kwargs
        )
    assert transport.requests == []


@pytest.mark.parametrize("revision", [True, -1, 2147483648, 1.5, 1.0])
def test_invalid_signed_revision_cannot_reach_transport(revision):
    transport = FakeTransport(V["catalogue"])
    with pytest.raises(ValueError):
        FleetRelayClient(ORIGIN, transport=transport).fetch_catalogue(
            **{**signed(), "revision": revision}
        )
    assert transport.requests == []


def test_pairing_requests_capability_without_assuming_new_completion_fields():
    transport = FakeTransport(
        {
            "protocol": 2,
            "pairing_id": UUID,
            "approval_url": "/fleet/pair/" + UUID,
            "expires_at": DATE,
        }
    )
    FleetRelayClient(ORIGIN, transport=transport).begin_pairing(
        crypto.public_key_spki(crypto.generate_private_key()),
        requested_capabilities=("shared-source-v1",),
    )
    assert json.loads(transport.requests[0].data)["requested_capabilities"] == [
        "shared-source-v1"
    ]


@pytest.mark.parametrize("origin", BRACKETED_INVALID_ORIGINS)
def test_approval_url_rejects_unsupported_bracketed_authority(origin):
    transport = FakeTransport(
        {
            "protocol": 2,
            "pairing_id": UUID,
            "approval_url": origin + "/fleet/pair/" + UUID,
            "expires_at": DATE,
        }
    )
    # IPvFuture must not compare equal to ordinary DNS; malformed IPv6
    # prefix/suffix forms must not compare equal to valid IPv6.
    paired_origin = (
        "https://v1.relay.example.test" if "v1." in origin else "https://[2001:db8::1]"
    )
    with pytest.raises(FleetRelayError) as exc:
        FleetRelayClient(paired_origin, transport=transport).begin_pairing(
            crypto.public_key_spki(crypto.generate_private_key())
        )
    assert exc.value.code == "malformed_response"


def test_approval_url_preserves_valid_ipv6_same_origin_normalization():
    url = "HTTPS://[2001:0DB8:0:0:0:0:0:1]:443/fleet/pair/" + UUID
    transport = FakeTransport(
        {"protocol": 2, "pairing_id": UUID, "approval_url": url, "expires_at": DATE}
    )
    assert (
        FleetRelayClient("https://[2001:db8::1]", transport=transport)
        .begin_pairing(crypto.public_key_spki(crypto.generate_private_key()))
        .approval_url
        == url
    )


def test_recovery_proofs_are_origin_and_purpose_separated_without_hidden_retries():
    private = crypto.generate_private_key()
    spki = crypto.public_key_spki(private)
    key = load_der_public_key(spki)
    digest = hashlib.sha256(spki).hexdigest()
    transport = FakeTransport(CHALLENGE)
    relay = FleetRelayClient(ORIGIN, transport=transport)
    challenge = relay.begin_recovery(
        private_key=private, request_id=TOKEN, issued_at=DATE
    )
    assert challenge == p.parse_recovery_challenge(CHALLENGE)
    request = transport.requests[0]
    assert request.full_url == ORIGIN + "/api/fleet/v2/recovery-challenges"
    assert request.get_method() == "POST"
    body = json.loads(request.data)
    assert set(body) == {
        "protocol",
        "public_key_spki_b64url",
        "request_id",
        "issued_at",
        "initiation_signature",
    }
    assert (
        body["protocol"] == 2
        and body["request_id"] == TOKEN
        and body["issued_at"] == DATE
    )
    assert body["public_key_spki_b64url"] == base64.urlsafe_b64encode(
        spki
    ).decode().rstrip("=")
    preimage = f"fleet-recovery-init-v1\n{ORIGIN}\n{TOKEN}\n{DATE}\n{digest}".encode()
    key.verify(_b64url_decode(body["initiation_signature"]), preimage)
    with pytest.raises(InvalidSignature):
        key.verify(
            _b64url_decode(body["initiation_signature"]),
            preimage.replace(ORIGIN.encode(), b"https://other.test"),
        )
    transport.body = json.dumps(RECONNECTED).encode()
    assert relay.complete_recovery(
        private_key=private, challenge=challenge
    ) == p.parse_recovery_result(RECONNECTED)
    request = transport.requests[1]
    assert (
        request.full_url
        == ORIGIN
        + "/api/fleet/v2/recovery-challenges/"
        + challenge.challenge_id
        + "/complete"
    )
    body = json.loads(request.data)
    assert set(body) == {"protocol", "nonce", "recovery_signature"}
    assert body["nonce"] == challenge.nonce and body["protocol"] == 2
    complete = f"fleet-recovery-v1\n{ORIGIN}\n{challenge.challenge_id}\n{challenge.nonce}\n{digest}".encode()
    key.verify(_b64url_decode(body["recovery_signature"]), complete)
    with pytest.raises(InvalidSignature):
        key.verify(_b64url_decode(body["recovery_signature"]), preimage)
    for request in transport.requests:
        headers = _headers_of(request)
        assert {k for k in headers if k.startswith("x-fleet")} == {"x-fleet-attempt"}
        assert "cookie" not in headers
    assert len(transport.requests) == 2


def test_recovery_begin_checks_echoed_request_id():
    with pytest.raises(FleetRelayError, match="unexpected shape") as exc:
        FleetRelayClient(
            ORIGIN, transport=FakeTransport({**CHALLENGE, "request_id": "A" * 43})
        ).begin_recovery(
            private_key=crypto.generate_private_key(), request_id=TOKEN, issued_at=DATE
        )
    assert exc.value.code == "malformed_response"


@pytest.mark.parametrize("phase", ["begin", "complete"])
def test_recovery_response_loss_is_unknown_not_revocation_and_never_retried(phase):
    requests = []

    def transport(request, timeout=None):
        requests.append(request)
        raise OSError("secret provider context")

    relay = FleetRelayClient(ORIGIN, transport=transport)
    with pytest.raises(FleetRelayError) as exc:
        if phase == "begin":
            relay.begin_recovery(
                private_key=crypto.generate_private_key(),
                request_id=TOKEN,
                issued_at=DATE,
            )
        else:
            relay.complete_recovery(
                private_key=crypto.generate_private_key(),
                challenge=p.parse_recovery_challenge(CHALLENGE),
            )
    assert exc.value.code == "transport_error" and len(requests) == 1
    assert "secret provider context" not in "".join(
        traceback.format_exception(exc.value)
    )


@pytest.mark.parametrize(
    "method,status,code,accepted",
    [
        ("fetch_device", 503, "feature_disabled", False),
        ("fetch_device", 409, "revision_replayed", True),
        ("fetch_device", 403, "capability_required", False),
        ("fetch_device", 409, "conflict", False),
        ("fetch_device", 400, "invalid_intent", True),
        ("fetch_sources", 403, "capability_required", True),
        ("fetch_sources", 403, "fleet_read_required", False),
        ("fetch_sources", 400, "update_required", True),
        ("fetch_sources", 401, "device_revoked", False),
        ("fetch_device", 401, "feature_disabled", False),
        ("fetch_device", 503, "device_key_conflict", False),
    ],
)
def test_error_codes_are_endpoint_method_and_status_local(
    method, status, code, accepted
):
    with pytest.raises(FleetRelayError) as exc:
        getattr(
            FleetRelayClient(
                ORIGIN,
                transport=error_transport(status, {"protocol": 2, "error": code}),
            ),
            method,
        )(**signed())
    assert exc.value.status == (status if accepted else None)
    assert exc.value.code == (code if accepted else "malformed_response")


@pytest.mark.parametrize(
    "status,code,accepted",
    [
        (400, "update_required", True),
        (401, "unauthorized", True),
        (429, "rate_limited", True),
        (503, "feature_disabled", True),
        (503, "service_unavailable", True),
        (401, "device_revoked", False),
        (401, "device_key_conflict", False),
        (409, "device_key_conflict", False),
    ],
)
def test_recovery_errors_never_turn_into_proven_outcomes(status, code, accepted):
    with pytest.raises(FleetRelayError) as exc:
        FleetRelayClient(
            ORIGIN, transport=error_transport(status, {"protocol": 2, "error": code})
        ).complete_recovery(
            private_key=crypto.generate_private_key(),
            challenge=p.parse_recovery_challenge(CHALLENGE),
        )
    assert exc.value.code == (code if accepted else "malformed_response")
    assert exc.value.status == (status if accepted else None)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"protocol":2,"error":"service_unavailable","extra":"secret"}',
        b'{"protocol":2.0000000000000001,"error":"service_unavailable"}',
        b'{"protocol":true,"error":"service_unavailable"}',
        b'{"protocol":2,"error":"service_unavailable","error":"service_unavailable"}',
        b'{"protocol":2,"error":"secret <script>"}',
        # Windows cannot export the full payload in PYTEST_CURRENT_TEST.
        pytest.param(
            b'{"protocol":2,"error":"service_unavailable"}' + b" " * 65536,
            id="oversized",
        ),
        b"[" * 2000,
    ],
)
def test_error_reads_are_bounded_closed_and_do_not_expose_arbitrary_context(raw):
    class Stream(io.BytesIO):
        def __init__(self, data):
            super().__init__(data)
            self.amounts = []

        def read(self, amount=-1):
            self.amounts.append(amount)
            return super().read(amount)

    stream = Stream(raw)

    def transport(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, 503, "secret exception reason", framing_headers(), stream
        )

    with pytest.raises(FleetRelayError) as exc:
        FleetRelayClient(ORIGIN, transport=transport).fetch_device(**signed())
    assert exc.value.code in ("malformed_response", "protocol_mismatch")
    assert exc.value.status is None
    assert stream.amounts == [65537] and stream.closed
    assert "secret" not in "".join(traceback.format_exception(exc.value))


@pytest.mark.parametrize("error_response", [True, False])
@pytest.mark.parametrize(
    "failure",
    [TimeoutError("secret timeout"), http.client.IncompleteRead(b"secret partial")],
)
def test_response_loss_during_bounded_read_closes_stream_and_stays_safe(
    error_response, failure
):
    class BrokenStream(io.BytesIO):
        def read(self, amount=-1):
            assert amount == (65537 if error_response else 1048577)
            raise failure

    stream = BrokenStream()
    stream.status = 200

    def transport(request, timeout=None):
        stream.headers = framing_headers(request_binding(request))
        if error_response:
            raise urllib.error.HTTPError(
                request.full_url, 503, "secret reason", framing_headers(), stream
            )
        return stream

    with pytest.raises(FleetRelayError) as exc:
        FleetRelayClient(ORIGIN, transport=transport).fetch_device(**signed())
    assert exc.value.code == "transport_error" and exc.value.status is None
    assert stream.closed
    assert "secret" not in "".join(traceback.format_exception(exc.value))


class ClosingErrorStream(io.BytesIO):
    """Real HTTPError wraps this stream; exported for the later worker migration."""

    def __init__(self, close_type, read_type=None):
        super().__init__(b'{"protocol":2,"error":"service_unavailable"}')
        self.close_type = close_type
        self.read_type = read_type
        self.read_amounts = []
        self.close_attempts = 0
        self.private_context = "private-error-stream-context"

    def read(self, amount=-1):
        self.read_amounts.append(amount)
        if self.read_type is not None:
            raise self.read_type(self.private_context)
        return super().read(amount)

    def close(self):
        self.close_attempts += 1
        super().close()  # Avoid a destructor retry masking this close attempt.
        raise self.close_type(self.private_context)


def closing_error_transport(stream):
    def transport(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, 503, stream.private_context, framing_headers(), stream
        )

    return transport


@pytest.mark.parametrize("method", ["fetch_device", "read_snapshot"])
@pytest.mark.parametrize(
    "close_type", [OSError, http.client.HTTPException, urllib.error.URLError]
)
@pytest.mark.parametrize(
    "read_type", [None, OSError, http.client.HTTPException, urllib.error.URLError]
)
def test_http_error_close_failure_cannot_escape_safe_classification(
    method, close_type, read_type
):
    stream = ClosingErrorStream(close_type, read_type)
    with pytest.raises(FleetRelayError) as exc:
        getattr(
            FleetRelayClient(ORIGIN, transport=closing_error_transport(stream)), method
        )(**signed())
    assert exc.value.status == (503 if read_type is None else None)
    assert exc.value.code == (
        "service_unavailable" if read_type is None else "transport_error"
    )
    assert stream.read_amounts == [65537]  # Never the 64MiB snapshot success ceiling.
    assert stream.close_attempts == 1 and stream.closed
    assert exc.value.__suppress_context__ and exc.value.__cause__ is None
    assert stream.private_context not in "".join(traceback.format_exception(exc.value))


def test_begin_retry_preserves_the_exact_body_and_client_does_not_retry_itself():
    transport = FakeTransport(CHALLENGE)
    relay = FleetRelayClient(ORIGIN, transport=transport)
    private = crypto.generate_private_key()
    for _ in range(2):
        relay.begin_recovery(private_key=private, request_id=TOKEN, issued_at=DATE)
    assert len(transport.requests) == 2
    assert transport.requests[0].data == transport.requests[1].data
    assert json.loads(transport.requests[1].data)["issued_at"] == DATE
    assert (
        _headers_of(transport.requests[0])["x-fleet-attempt"]
        != _headers_of(transport.requests[1])["x-fleet-attempt"]
    )


def test_nonraising_error_transport_is_still_classified_not_parsed_as_success():
    with pytest.raises(FleetRelayError) as exc:
        FleetRelayClient(
            ORIGIN,
            transport=FakeTransport({"protocol": 2, "result": "device_revoked"}, 401),
        ).complete_recovery(
            private_key=crypto.generate_private_key(),
            challenge=p.parse_recovery_challenge(CHALLENGE),
        )
    assert exc.value.code == "malformed_response" and exc.value.status is None


def test_snapshot_has_explicit_larger_byte_bound_and_never_truncates():
    transport = FakeTransport(
        {
            "protocol": 2,
            "server_time_ms": 12500,
            "rows": [
                {
                    **ROW,
                    "character_id": i + 1,
                    "publication_id": str(UUIDValue(int=i, version=4)),
                }
                for i in range(700)
            ],
        }
    )
    assert len(transport.body) > 65536
    relay = FleetRelayClient(ORIGIN, transport=transport)
    assert len(relay.read_snapshot(**signed()).rows) == 700
    # Whitespace keeps this exercise about raw bytes, not row cardinality.
    transport.body += b" " * 1048576
    assert len(relay.read_snapshot(**signed()).rows) == 700
    transport.body = json.dumps(DEVICE).encode() + b" " * 1048576
    with pytest.raises(FleetRelayError):
        relay.fetch_device(**signed())


@pytest.mark.parametrize(
    "payload",
    [
        {"protocol": 1.0, "revision": 0, "characters": []},
        {"protocol": 2, "revision": -1, "characters": []},
        {"protocol": 2, "revision": 4294967296, "characters": []},
        {
            "protocol": 2,
            "revision": 0,
            "characters": [{"character_id": 1, "character_name": "Alice"}] * 2,
        },
        {"protocol": 2, "revision": 0, "characters": [], "account_id": 2},
    ],
)
def test_existing_catalogue_is_also_exact_and_bounded(payload):
    with pytest.raises(FleetRelayError):
        FleetRelayClient(ORIGIN, transport=FakeTransport(payload)).fetch_catalogue(
            **signed()
        )


def test_catalogue_hash_is_unsigned32_not_a_session_revision():
    assert (
        FleetRelayClient(
            ORIGIN,
            transport=FakeTransport(
                {"protocol": 2, "revision": 4294967295, "characters": []}
            ),
        )
        .fetch_catalogue(**signed())
        .revision
        == 4294967295
    )


@pytest.mark.parametrize(
    "date",
    [
        "bad",
        "2026-02-30T00:00:00.000Z",
        "2026-01-01T00:00:00Z",
        "0000-01-01T00:00:00.000Z",
    ],
)
def test_renewal_rejects_invalid_dates(date):
    with pytest.raises(FleetRelayError):
        FleetRelayClient(
            ORIGIN, transport=FakeTransport({"protocol": 2, "expires_at": date})
        ).renew_session(**signed())
