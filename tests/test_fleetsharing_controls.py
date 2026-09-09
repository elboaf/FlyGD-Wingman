"""Single-attempt control/recovery requests through the actual HTTP boundary."""

import base64
import hashlib
import http.client
import io
import json
import traceback
import urllib.error
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
)
from test_fleetsharing_config import BRACKETED_INVALID_ORIGINS
from test_fleetsharing_protocol import (
    CHALLENGE,
    DATE,
    DEVICE,
    ELIGIBILITY,
    PARTICIPATION,
    RECONNECTED,
    ROW,
    SOURCE,
    START,
    TOKEN,
    UUID,
)

from wingman.fleetsharing import crypto
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing.client import FleetRelayClient, FleetRelayError


def signed():
    return {
        "session_id": TOKEN,
        "private_key": crypto.generate_private_key(),
        "revision": 7,
    }


@pytest.mark.parametrize(
    ("name", "method", "path", "payload", "kwargs", "expected"),
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
            {"protocol": 1, "participation": PARTICIPATION},
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
            {"protocol": 1, "sources": [SOURCE], "characters": []},
            {},
            p.Sources((p.parse_source(SOURCE),), ()),
        ),
        (
            "control_source",
            "PUT",
            "sources",
            {"protocol": 1, "source": SOURCE},
            {"command": p.StopSource(UUID, 0)},
            p.parse_source(SOURCE),
        ),
        (
            "read_snapshot",
            "GET",
            "snapshot",
            {"protocol": 1, "rows": [{**ROW, "publication_id": UUID}]},
            {},
            (p.ObservedRemoteRow(42, "Alice", 0, (), "live", 0, UUID),),
        ),
    ],
)
def test_control_methods_sign_exact_request_and_return_dto(
    name, method, path, payload, kwargs, expected
):
    transport = FakeTransport(payload, publication=name == "read_snapshot")
    relay = FleetRelayClient(ORIGIN, transport=transport)
    auth = signed()
    assert getattr(relay, name)(**auth, **kwargs) == expected
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.get_method() == method
    assert request.full_url == ORIGIN + "/api/fleet/v1/" + path
    headers = _headers_of(request)
    if method == "GET":
        assert request.data is None
    elif name == "control_source":
        assert json.loads(request.data) == {
            "protocol": 1,
            "operation": "stop",
            "source_id": UUID,
            "expected_generation": 0,
        }
    else:
        assert json.loads(request.data) == {
            "protocol": 1,
            **{k: list(v) if isinstance(v, tuple) else v for k, v in kwargs.items()},
        }
    digest = hashlib.sha256(request.data or b"").hexdigest()
    assert headers["x-fleet-body-sha256"] == digest
    canonical = f"fleet-v1\n{method}\n/api/fleet/v1/{path}\n{TOKEN}\n{headers['x-fleet-issued-at']}\n7\n{digest}".encode()
    load_der_public_key(crypto.public_key_spki(auth["private_key"])).verify(
        _b64url_decode(headers["x-fleet-signature"]), canonical
    )


def test_source_control_rejects_a_response_for_another_intent():
    transport = FakeTransport(
        {
            "protocol": 1,
            "source": {**SOURCE, "source_id": "00000000-0000-0000-0000-000000000000"},
        }
    )
    relay = FleetRelayClient(ORIGIN, transport=transport)
    with pytest.raises(FleetRelayError) as exc:
        relay.control_source(**signed(), command=p.StopSource(UUID, 0))
    assert exc.value.code == "malformed_response"


def test_start_does_not_refresh_original_intent_or_allocate_a_revision():
    transport = FakeTransport({"protocol": 1, "source": SOURCE})
    relay = FleetRelayClient(ORIGIN, transport=transport)
    command = p.parse_source_command(START)
    auth = signed()
    relay.control_source(**auth, command=command)
    relay.control_source(**{**auth, "revision": 8}, command=command)
    for request in transport.requests:
        assert json.loads(request.data) == {"protocol": 1, **START}


@pytest.mark.parametrize(
    ("name", "kwargs"),
    [
        ("acknowledge_capabilities", {"capabilities": ("unknown",)}),
        ("acknowledge_capabilities", {"capabilities": ("shared-source-v1",) * 2}),
        ("set_participation", {"enabled": 1, "expected_generation": 0}),
        ("set_participation", {"enabled": False, "expected_generation": True}),
        ("set_participation", {"enabled": False, "expected_generation": 2147483647}),
        ("control_source", {"command": p.StopSource(UUID, 2147483647)}),
        ("control_source", {"command": p.StartSource(UUID, 42, UUID, "invalid")}),
    ],
)
def test_invalid_control_fails_before_network(name, kwargs):
    transport = FakeTransport(DEVICE)
    relay = FleetRelayClient(ORIGIN, transport=transport)
    with pytest.raises(ValueError):
        getattr(relay, name)(**signed(), **kwargs)
    assert transport.requests == []


@pytest.mark.parametrize("revision", [True, -1, 2147483648, 1.5])
def test_invalid_signed_revision_cannot_reach_transport(revision):
    transport = FakeTransport({"protocol": 1, "revision": 1, "characters": []})
    with pytest.raises(ValueError):
        FleetRelayClient(ORIGIN, transport=transport).fetch_catalogue(
            **{**signed(), "revision": revision}
        )
    assert transport.requests == []


def test_pairing_requests_capability_without_assuming_new_completion_fields():
    transport = FakeTransport(
        {
            "protocol": 1,
            "pairing_id": UUID,
            "approval_url": "/fleet/pair/" + UUID,
            "expires_at": DATE,
        }
    )
    relay = FleetRelayClient(ORIGIN, transport=transport)
    relay.begin_pairing(
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
            "protocol": 1,
            "pairing_id": UUID,
            "approval_url": origin + "/fleet/pair/" + UUID,
            "expires_at": DATE,
        }
    )
    # The IPvFuture form must not compare equal to this ordinary DNS origin;
    # malformed IPv6 prefix/suffix forms must not compare equal to valid IPv6.
    paired_origin = (
        "https://v1.relay.example.test" if "v1." in origin else "https://[2001:db8::1]"
    )
    relay = FleetRelayClient(paired_origin, transport=transport)
    with pytest.raises(FleetRelayError) as exc:
        relay.begin_pairing(crypto.public_key_spki(crypto.generate_private_key()))
    assert exc.value.code == "malformed_response"


def test_approval_url_preserves_valid_ipv6_same_origin_normalization():
    url = "HTTPS://[2001:0DB8:0:0:0:0:0:1]:443/fleet/pair/" + UUID
    transport = FakeTransport(
        {"protocol": 1, "pairing_id": UUID, "approval_url": url, "expires_at": DATE}
    )
    relay = FleetRelayClient("https://[2001:db8::1]", transport=transport)
    assert (
        relay.begin_pairing(
            crypto.public_key_spki(crypto.generate_private_key())
        ).approval_url
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
    assert request.full_url == ORIGIN + "/api/fleet/v1/recovery-challenges"
    assert request.get_method() == "POST"
    body = json.loads(request.data)
    assert set(body) == {
        "protocol",
        "public_key_spki_b64url",
        "request_id",
        "issued_at",
        "initiation_signature",
    }
    assert body["request_id"] == TOKEN and body["issued_at"] == DATE
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
    result = relay.complete_recovery(private_key=private, challenge=challenge)
    assert result == p.parse_recovery_result(RECONNECTED)
    request = transport.requests[1]
    assert (
        request.full_url
        == ORIGIN + "/api/fleet/v1/recovery-challenges/" + UUID + "/complete"
    )
    body = json.loads(request.data)
    assert set(body) == {"protocol", "nonce", "recovery_signature"}
    assert body["nonce"] == TOKEN
    complete = f"fleet-recovery-v1\n{ORIGIN}\n{UUID}\n{TOKEN}\n{digest}".encode()
    key.verify(_b64url_decode(body["recovery_signature"]), complete)
    with pytest.raises(InvalidSignature):
        key.verify(_b64url_decode(body["recovery_signature"]), preimage)
    for request in transport.requests:
        headers = _headers_of(request)
        assert not any(k.startswith("x-fleet") or k == "cookie" for k in headers)
    assert len(transport.requests) == 2


def test_recovery_begin_checks_echoed_request_id():
    transport = FakeTransport({**CHALLENGE, "request_id": "A" * 43})
    relay = FleetRelayClient(ORIGIN, transport=transport)
    with pytest.raises(FleetRelayError, match="unexpected shape") as exc:
        relay.begin_recovery(
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
    assert exc.value.code == "transport_error"
    assert len(requests) == 1
    assert "secret provider context" not in "".join(
        traceback.format_exception(exc.value)
    )


@pytest.mark.parametrize(
    ("method", "status", "code", "want"),
    [
        ("fetch_device", 503, "feature_disabled", "server_error"),
        ("fetch_device", 409, "revision_replayed", "revision_replayed"),
        ("fetch_device", 403, "capability_required", "forbidden"),  # only PUT/device
        ("fetch_device", 409, "conflict", "conflict"),
        ("fetch_device", 400, "invalid_intent", "invalid_intent"),
        ("fetch_sources", 403, "capability_required", "capability_required"),
        ("fetch_sources", 403, "fleet_read_required", "forbidden"),  # only PUT/sources
        ("fetch_sources", 400, "update_required", "bad_request"),  # only PUT
        ("fetch_sources", 401, "device_revoked", "unauthorized"),
        ("fetch_device", 401, "feature_disabled", "unauthorized"),
        ("fetch_device", 503, "device_key_conflict", "server_error"),
    ],
)
def test_error_codes_are_endpoint_method_and_status_local(method, status, code, want):
    relay = FleetRelayClient(
        ORIGIN, transport=error_transport(status, {"protocol": 1, "error": code})
    )
    with pytest.raises(FleetRelayError) as exc:
        getattr(relay, method)(**signed())
    assert exc.value.status == status and exc.value.code == want


@pytest.mark.parametrize(
    ("status", "code", "want"),
    [
        (400, "update_required", "update_required"),
        (401, "unauthorized", "unauthorized"),
        (429, "rate_limited", "rate_limited"),
        (503, "feature_disabled", "feature_disabled"),
        (503, "service_unavailable", "service_unavailable"),
        (401, "device_revoked", "unauthorized"),
        (401, "device_key_conflict", "unauthorized"),
    ],
)
def test_recovery_errors_never_turn_into_proven_outcomes(status, code, want):
    relay = FleetRelayClient(
        ORIGIN, transport=error_transport(status, {"protocol": 1, "error": code})
    )
    with pytest.raises(FleetRelayError) as exc:
        relay.complete_recovery(
            private_key=crypto.generate_private_key(),
            challenge=p.parse_recovery_challenge(CHALLENGE),
        )
    assert exc.value.code == want


@pytest.mark.parametrize(
    "raw",
    [
        b'{"protocol":1,"error":"feature_disabled","extra":"secret"}',
        b'{"protocol":1.0,"error":"feature_disabled"}',
        b'{"protocol":true,"error":"feature_disabled"}',
        b'{"protocol":1,"error":"feature_disabled","error":"feature_disabled"}',
        b'{"protocol":1,"error":"secret <script>"}',
        b'{"protocol":1,"error":"feature_disabled"}' + b" " * 65536,
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
            request.full_url, 503, "secret exception reason", {}, stream
        )

    with pytest.raises(FleetRelayError) as exc:
        FleetRelayClient(ORIGIN, transport=transport).fetch_device(**signed())
    assert exc.value.code == "server_error"
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
            assert amount == 65537
            raise failure

    stream = BrokenStream()
    stream.status = 200

    def transport(request, timeout=None):
        if error_response:
            raise urllib.error.HTTPError(
                request.full_url, 503, "secret reason", {}, stream
            )
        return stream

    with pytest.raises(FleetRelayError) as exc:
        FleetRelayClient(ORIGIN, transport=transport).fetch_device(**signed())
    assert exc.value.code == ("server_error" if error_response else "transport_error")
    assert stream.closed
    assert "secret" not in "".join(traceback.format_exception(exc.value))


class ClosingErrorStream(io.BytesIO):
    """Real HTTPError wraps this stream, including its close side effects."""

    def __init__(self, close_type, read_type=None):
        super().__init__(b'{"protocol":1,"error":"service_unavailable"}')
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
        super().close()  # Avoid a later destructor retry masking this attempt.
        raise self.close_type(self.private_context)


def closing_error_transport(stream):
    def transport(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, 503, stream.private_context, {}, stream
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
    relay = FleetRelayClient(ORIGIN, transport=closing_error_transport(stream))
    with pytest.raises(FleetRelayError) as exc:
        getattr(relay, method)(**signed())
    assert exc.value.status == 503
    assert exc.value.code == (
        "service_unavailable"
        if method == "fetch_device" and read_type is None
        else "server_error"
    )
    assert stream.read_amounts == [65537]  # Snapshot error is NOT a 1MiB read.
    assert stream.close_attempts == 1 and stream.closed
    assert exc.value.__suppress_context__ and exc.value.__cause__ is None
    formatted = "".join(traceback.format_exception(exc.value))
    assert stream.private_context not in formatted


def test_begin_retry_preserves_the_exact_body_and_client_does_not_retry_itself():
    transport = FakeTransport(CHALLENGE)
    relay = FleetRelayClient(ORIGIN, transport=transport)
    private = crypto.generate_private_key()
    for _ in range(2):
        relay.begin_recovery(private_key=private, request_id=TOKEN, issued_at=DATE)
    assert len(transport.requests) == 2
    assert transport.requests[0].data == transport.requests[1].data


def test_nonraising_error_transport_is_still_classified_not_parsed_as_success():
    relay = FleetRelayClient(
        ORIGIN,
        transport=FakeTransport(
            {"protocol": 1, "result": "device_revoked"}, status=401
        ),
    )
    with pytest.raises(FleetRelayError) as exc:
        relay.complete_recovery(
            private_key=crypto.generate_private_key(),
            challenge=p.parse_recovery_challenge(CHALLENGE),
        )
    assert exc.value.code == "unauthorized"


def test_snapshot_has_explicit_larger_byte_bound_and_never_truncates():
    transport = FakeTransport(
        {
            "protocol": 1,
            "rows": [
                {
                    **ROW,
                    "character_id": i + 1,
                    "publication_id": str(UUIDValue(int=i, version=4)),
                }
                for i in range(700)
            ],
        },
        publication=True,
    )
    assert len(transport.body) > 65536
    relay = FleetRelayClient(ORIGIN, transport=transport)
    assert len(relay.read_snapshot(**signed())) == 700
    transport.body = b" " * (1024 * 1024 + 1)
    with pytest.raises(FleetRelayError) as exc:
        relay.read_snapshot(**signed())
    assert exc.value.code == "malformed_response"
    transport.publication = False
    transport.body = json.dumps(DEVICE).encode() + b" " * 65536
    with pytest.raises(FleetRelayError):
        relay.fetch_device(**signed())


@pytest.mark.parametrize(
    "payload",
    [
        {"protocol": 1.0, "revision": 0, "characters": []},
        {"protocol": 1, "revision": -1, "characters": []},
        {"protocol": 1, "revision": 4294967296, "characters": []},
        {
            "protocol": 1,
            "revision": 0,
            "characters": [{"character_id": 1, "character_name": "Alice"}] * 2,
        },
        {"protocol": 1, "revision": 0, "characters": [], "account_id": 2},
    ],
)
def test_existing_catalogue_is_also_exact_and_bounded(payload):
    with pytest.raises(FleetRelayError):
        FleetRelayClient(ORIGIN, transport=FakeTransport(payload)).fetch_catalogue(
            **signed()
        )


def test_catalogue_hash_is_unsigned32_not_a_session_revision():
    result = FleetRelayClient(
        ORIGIN,
        transport=FakeTransport(
            {"protocol": 1, "revision": 4294967295, "characters": []}
        ),
    ).fetch_catalogue(**signed())
    assert result.revision == 4294967295


@pytest.mark.parametrize(
    "date", ["bad", "2026-02-30T00:00:00.000Z", "2026-01-01T00:00:00Z"]
)
def test_renewal_rejects_invalid_dates(date):
    with pytest.raises(FleetRelayError):
        FleetRelayClient(
            ORIGIN, transport=FakeTransport({"protocol": 1, "expires_at": date})
        ).renew_session(**signed())
