"""Real client/signature/reader/codec integration; only HTTP delivery is doubled."""

import copy
import http.client
import json
import traceback
import urllib.error
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from test_fleetsharing_client import (
    ORIGIN,
    FakeTransport,
    Response,
    _headers_of,
    framing_headers,
    request_binding,
)
from test_fleetsharing_protocol import FIXTURE, TOKEN

from wingman.fleetsharing import client as c
from wingman.fleetsharing import crypto
from wingman.fleetsharing import protocol as p

V = FIXTURE["valid"]
KEY = bytes(32)
AUTH = dict(
    session_id=TOKEN, private_key=KEY, revision=7, now=datetime(2026, 1, 1, tzinfo=UTC)
)
AUTO = p.parse_automatic_command(V["automatic_result"]["receipt"]["command"])
START = p.parse_source_command(V["source_start"])
STOP = p.parse_source_command(V["source_stop"])
COMBAT = p.parse_combat_put(V["combat_put"])

# Literal per-operation budgets; changing the production dispatch must fail here.
CASES = [
    ("fetch_catalogue", "catalogue", {}, "GET", "catalogue", 1048576),
    ("fetch_device", "device", {}, "GET", "device", 1048576),
    (
        "acknowledge_capabilities",
        "device",
        {"capabilities": ("shared-source-v1", "combat-v2")},
        "PUT",
        "device",
        1048576,
    ),
    (
        "set_participation",
        "participation",
        {"enabled": False, "expected_generation": 0},
        "PUT",
        "participation",
        1048576,
    ),
    ("fetch_eligibility", "eligibility", {}, "GET", "eligibility", 1048576),
    ("fetch_sources", "sources", {}, "GET", "sources", 1048576),
    (
        "control_source",
        "source_start_result",
        {"command": START},
        "PUT",
        "sources",
        1048576,
    ),
    (
        "control_source",
        "source_stop_result",
        {"command": STOP},
        "PUT",
        "sources",
        1048576,
    ),
    ("read_snapshot", "combat_get", {}, "GET", "snapshot", 67108864),
    (
        "publish_snapshot",
        None,
        {"sampled_at_ms": COMBAT.sampled_at_ms, "rows": COMBAT.rows},
        "PUT",
        "snapshot",
        1048576,
    ),
    ("renew_session", "session", {}, "PUT", "session", 1048576),
    ("fetch_automatic", "automatic_get", {}, "GET", "automatic-verification", 16384),
    (
        "control_automatic",
        "automatic_result",
        {"command": AUTO},
        "PUT",
        "automatic-verification",
        16384,
    ),
    (
        "fetch_receipt",
        "receipt_get",
        {"request_id": AUTO.request_id},
        "GET",
        "automatic-verification/receipts/" + AUTO.request_id,
        16384,
    ),
]


@pytest.mark.parametrize("name,key,kwargs,method,path,bound", CASES)
def test_all_signed_operations_require_v2_binding_and_full_dto(
    name, key, kwargs, method, path, bound
):
    payload = V[key] if key else {"protocol": 2}
    transport = FakeTransport(payload)
    result = getattr(c.FleetRelayClient(ORIGIN, transport=transport), name)(
        **AUTH, **kwargs
    )
    (request,) = transport.requests
    assert request.full_url == ORIGIN + "/api/fleet/v2/" + path
    assert request.get_method() == method
    headers = _headers_of(request)
    assert headers["accept-encoding"] == "identity"
    assert {k for k in headers if k.startswith("x-fleet-")} == {
        "x-fleet-session",
        "x-fleet-issued-at",
        "x-fleet-revision",
        "x-fleet-body-sha256",
        "x-fleet-signature",
    }
    assert "transfer-encoding" not in headers
    if method == "GET" or name == "renew_session":
        assert request.data is None
        assert headers.get("content-length", "0") == "0"
    else:
        assert json.loads(request.data)["protocol"] == 2
    assert transport.responses[0].reads == [bound + 1]
    assert transport.responses[0].closed
    if name == "read_snapshot":
        assert isinstance(result, p.CombatSnapshot)
        assert result.server_time_ms == payload["server_time_ms"]
        assert result.rows[0].incoming_dps == payload["rows"][0]["incoming_dps"]
    if name == "fetch_device":
        assert result.server_time_ms == payload["server_time_ms"]
    if name == "control_source":
        assert result.source.source_id == kwargs["command"].source_id
    if name == "control_automatic":
        assert result.receipt.command == AUTO
    if name == "fetch_receipt":
        assert result.receipt.command.request_id == AUTO.request_id
    if name == "renew_session":
        assert result == payload["expires_at"]


@pytest.mark.parametrize("name,key,kwargs,method,path,bound", CASES)
def test_before_send_is_after_sign_and_immediately_before_transport(
    name, key, kwargs, method, path, bound, monkeypatch
):
    events = []
    transport = FakeTransport(V[key] if key else {"protocol": 2})
    sign = crypto.sign_request

    def signing(*args):
        events.append("sign")
        return sign(*args)

    def send(request, **kw):
        events.append("send")
        return transport(request, **kw)

    original_request = c.urllib.request.Request

    def build_request(*args, **kw):
        result = original_request(*args, **kw)
        events.append("request")
        return result

    monkeypatch.setattr(crypto, "sign_request", signing)
    monkeypatch.setattr(c.urllib.request, "Request", build_request)
    relay = c.FleetRelayClient(ORIGIN, transport=send)
    getattr(relay, name)(**AUTH, **kwargs, before_send=lambda: events.append("admit"))
    assert events == ["sign", "request", "admit", "send"]
    events.clear()
    refusal = OSError("caller admission fence")

    def refuse():
        events.append("refuse")
        raise refusal

    with pytest.raises(OSError) as exc:
        getattr(relay, name)(**AUTH, **kwargs, before_send=refuse)
    assert exc.value is refusal
    assert events == ["sign", "request", "refuse"]
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    "mutation",
    [
        {"revision": 8},
        {"session_id": "A" * 43},
    ],
)
def test_old_signed_whole_response_cannot_settle_new_attempt(mutation):
    transport = FakeTransport(V["device"])
    relay = c.FleetRelayClient(ORIGIN, transport=transport)
    relay.fetch_device(**AUTH)
    old_headers = transport.responses[0].headers
    response = Response(json.dumps(V["device"]).encode(), old_headers)
    relay = c.FleetRelayClient(ORIGIN, transport=lambda *a, **kw: response)
    with pytest.raises(c.FleetRelayError) as exc:
        relay.fetch_device(**{**AUTH, **mutation})
    assert exc.value.code == "malformed_response"
    assert response.closed and response.reads == []


@pytest.mark.parametrize(
    "command",
    [
        replace(AUTO, expected_revision=7),
        replace(AUTO, intent_created_at="2026-09-07T11:59:59.000Z"),
    ],
)
def test_automatic_receipt_is_correlated_with_actual_immutable_command(command):
    with pytest.raises(c.FleetRelayError):
        c.FleetRelayClient(
            ORIGIN, transport=FakeTransport(V["automatic_result"])
        ).control_automatic(**AUTH, command=command)


@pytest.mark.parametrize(
    "command",
    [
        replace(STOP, expected_generation=0),
        replace(STOP, intent_created_at="2026-09-07T11:59:59.000Z"),
    ],
)
def test_source_receipt_is_correlated_with_actual_immutable_command(command):
    with pytest.raises(c.FleetRelayError):
        c.FleetRelayClient(
            ORIGIN, transport=FakeTransport(V["source_stop_result"])
        ).control_source(**AUTH, command=command)


def test_receipt_get_correlates_the_signed_selector():
    with pytest.raises(c.FleetRelayError):
        c.FleetRelayClient(
            ORIGIN, transport=FakeTransport(V["receipt_get"])
        ).fetch_receipt(**AUTH, request_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


@pytest.mark.parametrize(
    "row",
    [
        replace(COMBAT.rows[0], outgoing_dps=0.0),
        replace(COMBAT.rows[0], incoming_dps=True),
        replace(COMBAT.rows[0], activity_age_ms=float("2.0000000000000001")),
    ],
)
def test_outbound_internal_values_are_not_legitimized_by_wire_roundtrip(row):
    transport = FakeTransport({"protocol": 2})
    admission = []
    with pytest.raises(ValueError):
        c.FleetRelayClient(ORIGIN, transport=transport).publish_snapshot(
            **AUTH,
            sampled_at_ms=COMBAT.sampled_at_ms,
            rows=(row,),
            before_send=lambda: admission.append(True),
        )
    assert transport.requests == [] and admission == []


@pytest.mark.parametrize("status", [401, 409])
@pytest.mark.parametrize(
    "payload",
    [
        {"protocol": 1, "error": "unauthorized"},
        {"protocol": 2, "error": "device_revoked"},
        {"protocol": 2, "error": "conflict", "extra": "secret"},
    ],
)
def test_malformed_errors_cannot_trigger_old_worker_status_branches(status, payload):
    with pytest.raises(c.FleetRelayError) as exc:
        c.FleetRelayClient(
            ORIGIN, transport=FakeTransport(payload, status)
        ).fetch_device(**AUTH)
    assert exc.value.status is None
    assert exc.value.code in ("malformed_response", "protocol_mismatch")


def test_bad_framing_fails_before_body_decode():
    responses = []

    def transport(request, **kw):
        headers = framing_headers(request_binding(request))
        del headers["Cache-Control"]
        response = Response(b"not json", headers)
        responses.append(response)
        return response

    with pytest.raises(c.FleetRelayError) as exc:
        c.FleetRelayClient(ORIGIN, transport=transport).fetch_device(**AUTH)
    assert exc.value.code == "malformed_response"
    assert responses[0].closed and responses[0].reads == []


def test_pairing_cannot_sign_an_arbitrary_caller_preimage():
    transport = FakeTransport(V["pairing_completed"])
    with pytest.raises(ValueError):
        c.FleetRelayClient(ORIGIN, transport=transport).complete_pairing(
            V["pairing_begun"]["pairing_id"], b"arbitrary signing request", KEY
        )
    assert transport.requests == []


BOOT_CASES = [
    (
        "begin_pairing",
        "pairing_begun",
        {"public_key_spki": crypto.public_key_spki(KEY)},
        "pairing-requests",
    ),
    (
        "complete_pairing",
        "pairing_completed",
        {
            "pairing_id": V["pairing_begun"]["pairing_id"],
            "challenge": crypto.pairing_challenge_preimage(
                V["pairing_begun"]["pairing_id"]
            ),
            "private_key": KEY,
        },
        "pairing-requests/" + V["pairing_begun"]["pairing_id"] + "/complete",
    ),
    (
        "begin_recovery",
        "recovery_challenge",
        {
            "private_key": KEY,
            "request_id": TOKEN,
            "issued_at": "2026-09-07T12:00:00.000Z",
        },
        "recovery-challenges",
    ),
    (
        "complete_recovery",
        "recovery_reconnected",
        {
            "private_key": KEY,
            "challenge": p.parse_recovery_challenge(V["recovery_challenge"]),
        },
        "recovery-challenges/" + V["recovery_challenge"]["challenge_id"] + "/complete",
    ),
]


@pytest.mark.parametrize("name,key,kwargs,path", BOOT_CASES)
def test_bootstrap_attempt_is_fresh_but_proof_and_body_are_immutable(
    name, key, kwargs, path
):
    transport = FakeTransport(V[key])
    relay = c.FleetRelayClient(ORIGIN, transport=transport)
    admission = []
    for _ in range(2):
        getattr(relay, name)(
            **kwargs, before_send=lambda: admission.append(len(transport.requests))
        )
    assert admission == [0, 1]
    first, second = transport.requests
    assert first.data == second.data
    assert first.full_url == ORIGIN + "/api/fleet/v2/" + path
    assert first.get_method() == "POST"
    assert json.loads(first.data)["protocol"] == 2
    if name == "begin_pairing":
        assert json.loads(first.data)["requested_capabilities"] == []
    attempts = []
    for request in transport.requests:
        headers = _headers_of(request)
        assert {k for k in headers if k.startswith("x-fleet-")} == {"x-fleet-attempt"}
        assert "cookie" not in headers and headers["accept-encoding"] == "identity"
        attempts.append(p.token(headers["x-fleet-attempt"]))
    assert attempts[0] != attempts[1]
    assert all(r.closed and r.reads == [65537] for r in transport.responses)
    replay = Response(transport.body, transport.responses[0].headers)
    relay = c.FleetRelayClient(ORIGIN, transport=lambda *a, **kw: replay)
    with pytest.raises(c.FleetRelayError) as exc:
        getattr(relay, name)(**kwargs)
    assert exc.value.code == "malformed_response"
    assert replay.closed and replay.reads == []


@pytest.mark.parametrize("name,key,kwargs,method,path,bound", CASES)
def test_signed_success_exact_bound_and_one_over_are_whole_response_gates(
    name, key, kwargs, method, path, bound, monkeypatch
):
    transport = FakeTransport(V[key] if key else {"protocol": 2})
    transport.body += b" " * (bound - len(transport.body))
    relay = c.FleetRelayClient(ORIGIN, transport=transport)
    getattr(relay, name)(**AUTH, **kwargs)
    transport.body += b" "

    def must_not_parse(_raw):
        pytest.fail("Oversize must be refused before JSON parsing")

    monkeypatch.setattr(p, "decode_wire_json", must_not_parse)
    with pytest.raises(c.FleetRelayError) as exc:
        getattr(relay, name)(**AUTH, **kwargs)
    assert exc.value.code == "malformed_response"
    assert all(r.closed and r.reads == [bound + 1] for r in transport.responses)


@pytest.mark.parametrize("name,key,kwargs,path", BOOT_CASES)
def test_bootstrap_success_exact_bound_and_one_over(
    name, key, kwargs, path, monkeypatch
):
    transport = FakeTransport(V[key])
    transport.body += b" " * (65536 - len(transport.body))
    relay = c.FleetRelayClient(ORIGIN, transport=transport)
    getattr(relay, name)(**kwargs)
    transport.body += b" "
    monkeypatch.setattr(
        p, "decode_wire_json", lambda raw: pytest.fail("parsed oversized bootstrap")
    )
    with pytest.raises(c.FleetRelayError):
        getattr(relay, name)(**kwargs)
    assert all(r.closed and r.reads == [65537] for r in transport.responses)


@pytest.mark.parametrize("name,key,kwargs,method,path,bound", CASES)
@pytest.mark.parametrize("over", [False, True])
def test_all_signed_errors_use_only_64k(name, key, kwargs, method, path, bound, over):
    transport = FakeTransport({"protocol": 2, "error": "service_unavailable"}, 503)
    transport.body += b" " * (65536 + over - len(transport.body))
    with pytest.raises(c.FleetRelayError) as exc:
        getattr(c.FleetRelayClient(ORIGIN, transport=transport), name)(**AUTH, **kwargs)
    assert exc.value.code == ("malformed_response" if over else "service_unavailable")
    assert exc.value.status == (None if over else 503)
    assert transport.responses[0].reads == [65537]
    assert transport.responses[0].closed


@pytest.mark.parametrize(
    "name,kwargs,status,code,accepted",
    [
        (
            "fetch_receipt",
            {"request_id": AUTO.request_id},
            404,
            "receipt_not_found",
            True,
        ),
        ("fetch_automatic", {}, 404, "receipt_not_found", False),
        ("control_automatic", {"command": AUTO}, 429, "receipt_capacity", False),
        (
            "control_automatic",
            {"command": replace(AUTO, enabled=True)},
            429,
            "receipt_capacity",
            True,
        ),
        ("fetch_automatic", {}, 429, "receipt_capacity", False),
        ("control_source", {"command": START}, 403, "fleet_read_required", True),
        ("control_source", {"command": STOP}, 403, "fleet_read_required", False),
        ("fetch_sources", {}, 403, "fleet_read_required", False),
        (
            "publish_snapshot",
            {"sampled_at_ms": 0, "rows": ()},
            403,
            "not_verified",
            True,
        ),
        ("fetch_automatic", {}, 403, "not_verified", False),
        ("control_automatic", {"command": AUTO}, 409, "request_id_conflict", True),
        ("fetch_sources", {}, 409, "revision_replayed", True),
    ],
)
def test_errors_are_bound_to_actual_operation_and_command(
    name, kwargs, status, code, accepted
):
    transport = FakeTransport({"protocol": 2, "error": code}, status)
    with pytest.raises(c.FleetRelayError) as exc:
        getattr(c.FleetRelayClient(ORIGIN, transport=transport), name)(**AUTH, **kwargs)
    assert exc.value.code == (code if accepted else "malformed_response")
    assert exc.value.status == (status if accepted else None)


@pytest.mark.parametrize("name,key,kwargs,path", BOOT_CASES)
@pytest.mark.parametrize("over", [False, True])
def test_every_bootstrap_error_has_64k_whole_entity_bound(
    name, key, kwargs, path, over
):
    transport = FakeTransport({"protocol": 2, "error": "service_unavailable"}, 503)
    transport.body += b" " * (65536 + over - len(transport.body))
    with pytest.raises(c.FleetRelayError) as exc:
        getattr(c.FleetRelayClient(ORIGIN, transport=transport), name)(**kwargs)
    assert exc.value.code == ("malformed_response" if over else "service_unavailable")
    assert transport.responses[0].closed and transport.responses[0].reads == [65537]


@pytest.mark.parametrize(
    "index,status,code,accepted",
    [
        (0, 400, "invalid_key", True),
        (1, 400, "invalid_key", False),
        (2, 400, "invalid_key", False),
        (3, 400, "invalid_key", False),
        (0, 409, "not_completable", False),
        (1, 409, "not_completable", True),
        (3, 409, "not_completable", False),
        (0, 404, "not_found", False),
        (1, 404, "not_found", True),
        (2, 404, "not_found", False),
        (3, 404, "not_found", True),
        (0, 401, "unauthorized", False),
        (2, 401, "unauthorized", True),
        (1, 429, "rate_limited", False),
        (3, 429, "rate_limited", True),
        (3, 409, "conflict", False),
    ],
)
def test_pre_session_error_subsets(index, status, code, accepted):
    name, _, kwargs, _ = BOOT_CASES[index]
    with pytest.raises(c.FleetRelayError) as exc:
        getattr(
            c.FleetRelayClient(
                ORIGIN, transport=FakeTransport({"protocol": 2, "error": code}, status)
            ),
            name,
        )(**kwargs)
    assert exc.value.code == (code if accepted else "malformed_response")
    assert exc.value.status == (status if accepted else None)


@pytest.mark.parametrize("name,key,kwargs,method,path,bound", CASES)
@pytest.mark.parametrize("broken", ["binding", "content_type", "no_store", "encoding"])
def test_every_signed_success_requires_framing_before_read(
    name, key, kwargs, method, path, bound, broken
):
    responses = []

    def transport(request, **kw):
        headers = framing_headers(request_binding(request))
        if broken == "binding":
            del headers["X-Fleet-Request-Binding"]
        elif broken == "content_type":
            headers["content-TYPE"] = "text/html"
        elif broken == "no_store":
            del headers["Cache-Control"]
        else:
            headers["Content-Encoding"] = "gzip"
        response = Response(b"not json", headers)
        responses.append(response)
        return response

    with pytest.raises(c.FleetRelayError) as exc:
        getattr(c.FleetRelayClient(ORIGIN, transport=transport), name)(**AUTH, **kwargs)
    assert exc.value.code == "malformed_response"
    assert responses[0].closed and responses[0].reads == []


@pytest.mark.parametrize("name,key,kwargs,path", BOOT_CASES)
@pytest.mark.parametrize("broken", ["binding", "content_type", "no_store", "encoding"])
def test_every_bootstrap_success_requires_framing(name, key, kwargs, path, broken):
    responses = []

    def transport(request, **kw):
        headers = framing_headers(request_binding(request))
        field = {
            "binding": "X-Fleet-Request-Binding",
            "content_type": "Content-Type",
            "no_store": "Cache-Control",
        }.get(broken)
        if field:
            del headers[field]
        else:
            headers["Content-Encoding"] = "br"
        response = Response(b"not json", headers)
        responses.append(response)
        return response

    with pytest.raises(c.FleetRelayError):
        getattr(c.FleetRelayClient(ORIGIN, transport=transport), name)(**kwargs)
    assert responses[0].closed and responses[0].reads == []


@pytest.mark.parametrize(
    "field,values,accepted",
    [
        ("Content-Type", ["application/json"], True),
        ("Content-Type", ['application/json; charset="UTF-8"'], True),
        ("Content-Type", ["application/json; charset=iso-8859-1"], False),
        ("Content-Type", ["application/json", "text/html"], False),
        ("Content-Type", ["application/json; charset=utf-8; charset=latin1"], False),
        ("Cache-Control", ["private, no-store"], True),
        ("Cache-Control", ["no-store", "public"], False),
        ("Cache-Control", ["no-store, no-store"], False),
        ("Cache-Control", ["no-store=true"], False),
        ("Content-Encoding", ["identity"], True),
        ("Content-Encoding", ["gzip"], False),
        ("Content-Encoding", ["identity", "identity"], False),
        ("Content-Encoding", ["identity, gzip"], False),
    ],
)
def test_framing_single_values_not_mixed_or_non_utf8(field, values, accepted):
    def transport(request, **kw):
        headers = framing_headers(request_binding(request))
        del headers[field]
        for value in values:
            headers[field] = value
        return Response(json.dumps(V["device"]).encode(), headers)

    relay = c.FleetRelayClient(ORIGIN, transport=transport)
    if accepted:
        assert (
            relay.fetch_device(**AUTH).server_time_ms == V["device"]["server_time_ms"]
        )
    else:
        with pytest.raises(c.FleetRelayError):
            relay.fetch_device(**AUTH)


@pytest.mark.parametrize("index", range(len(CASES) + len(BOOT_CASES)))
@pytest.mark.parametrize("allow", ["correct", None, "POST, GET", "duplicate"])
def test_method_not_allowed_requires_exact_route_allow(index, allow):
    if index < len(CASES):
        name, _, extra, _, path, _ = CASES[index]
        kwargs = {**AUTH, **extra}
        expected = (
            "GET"
            if path.startswith("automatic-verification/receipts/")
            or path in ("catalogue", "eligibility")
            else "PUT"
            if path in ("session", "participation")
            else "GET, PUT"
        )
    else:
        name, _, kwargs, path = BOOT_CASES[index - len(CASES)]
        expected = "POST"

    def transport(request, **kw):
        headers = framing_headers()
        if allow in ("correct", "duplicate"):
            headers["Allow"] = expected
        if allow == "duplicate":
            headers["allow"] = expected
        elif allow not in ("correct", None):
            headers["Allow"] = allow
        return Response(b'{"protocol":2,"error":"method_not_allowed"}', headers, 405)

    with pytest.raises(c.FleetRelayError) as exc:
        getattr(c.FleetRelayClient(ORIGIN, transport=transport), name)(**kwargs)
    assert exc.value.code == (
        "method_not_allowed" if allow == "correct" else "malformed_response"
    )
    assert exc.value.status == (405 if allow == "correct" else None)


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308, 404, 500])
def test_redirect_html_or_unavailable_v2_is_never_retried_or_downgraded(status):
    transport = FakeTransport({"protocol": 2, "error": "update_required"}, status)
    transport.body = b"<html>old service</html>"
    with pytest.raises(c.FleetRelayError) as exc:
        c.FleetRelayClient(ORIGIN, transport=transport).fetch_device(**AUTH)
    assert exc.value.status is None and exc.value.code == "malformed_response"
    assert len(transport.requests) == 1
    assert "/api/fleet/v2/device" in transport.requests[0].full_url


@pytest.mark.parametrize("old_domain", [True, False])
@pytest.mark.parametrize("change", ["path", "method", "body", "issued_at"])
def test_response_binding_covers_actual_canonical_bytes(change, old_domain):
    responses = []

    def transport(request, **kw):
        headers = _headers_of(request)
        fields = dict(
            protocol=1,
            method="PUT",
            path=c.DEVICE_PATH,
            session_id=TOKEN,
            issued_at=headers["x-fleet-issued-at"],
            revision=7,
            body_sha256=headers["x-fleet-body-sha256"],
        )
        fields.update(
            {
                "path": {"path": c.PARTICIPATION_PATH},
                "method": {"method": "GET"},
                "body": {"body_sha256": "0" * 64},
                "issued_at": {"issued_at": "2025-01-01T00:00:00.000Z"},
            }[change]
        )
        canonical = crypto.canonical_fleet_request(**fields)
        binding = (
            crypto.snapshot_request_binding(canonical)
            if old_domain
            else p.signed_request_binding(canonical)
        )
        response = Response(json.dumps(V["device"]).encode(), framing_headers(binding))
        responses.append(response)
        return response

    with pytest.raises(c.FleetRelayError):
        c.FleetRelayClient(ORIGIN, transport=transport).acknowledge_capabilities(
            **AUTH, capabilities=()
        )
    assert responses[0].closed and responses[0].reads == []


@pytest.mark.parametrize(
    "kind",
    [
        "automatic_noop",
        "source_noop",
        "automatic_replay",
        "source_replay",
        "source_receipt",
        "withdrawal",
        "empty_snapshot",
        "empty_sources",
    ],
)
def test_noop_empty_and_receipt_variants_use_same_real_boundary(kind):
    if kind == "automatic_noop":
        payload = copy.deepcopy(V["automatic_result"])
        payload.update(result="already_off", receipt=None)
        name, kwargs = (
            "control_automatic",
            {"command": replace(AUTO, expected_revision=9)},
        )
    elif kind == "source_noop":
        payload = copy.deepcopy(V["source_stop_result"])
        payload.update(
            result="already_stopped",
            receipt=None,
            automatic_effect="current_already_off",
        )
        name, kwargs = "control_source", {"command": STOP}
    elif kind in ("automatic_replay", "source_replay"):
        is_auto = kind == "automatic_replay"
        payload = copy.deepcopy(
            V["automatic_result" if is_auto else "source_stop_result"]
        )
        payload["result"] = "replayed"
        name, kwargs = (
            ("control_automatic" if is_auto else "control_source"),
            {"command": AUTO if is_auto else STOP},
        )
    elif kind == "source_receipt":
        source = V["source_stop_result"]
        payload = {
            "protocol": 2,
            "receipt": source["receipt"],
            "status": source["status"],
        }
        name, kwargs = "fetch_receipt", {"request_id": STOP.request_id}
    elif kind == "withdrawal":
        payload, name, kwargs = (
            {"protocol": 2},
            "publish_snapshot",
            {"sampled_at_ms": 0, "rows": ()},
        )
    elif kind == "empty_sources":
        payload, name, kwargs = (
            {"protocol": 2, "sources": [], "characters": []},
            "fetch_sources",
            {},
        )
    else:
        payload, name, kwargs = (
            {"protocol": 2, "server_time_ms": 1, "rows": []},
            "read_snapshot",
            {},
        )
    transport = FakeTransport(payload)
    result = getattr(c.FleetRelayClient(ORIGIN, transport=transport), name)(
        **AUTH, **kwargs
    )
    if "noop" in kind:
        assert result.receipt is None and not result.status.consent.enabled
    if "replay" in kind:
        assert result.result == "replayed" and result.receipt is not None
    if kind == "withdrawal":
        assert (
            transport.requests[0].data
            == b'{"protocol": 2, "sampled_at_ms": 0, "rows": []}'
        )
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    "path,method,bound",
    [
        ("snapshot", "PUT", 524288),
        ("automatic-verification", "PUT", 2048),
        ("sources", "PUT", 2048),
        ("device", "PUT", 1024),
        ("participation", "PUT", 1024),
        ("session", "PUT", 0),
        *[
            (path, "GET", 0)
            for path in (
                "catalogue",
                "device",
                "eligibility",
                "sources",
                "snapshot",
                "automatic-verification",
                "automatic-verification/receipts/" + AUTO.request_id,
            )
        ],
    ],
)
def test_actual_signed_request_raw_ceiling_before_signature_or_admission(
    path, method, bound, monkeypatch
):
    transport = FakeTransport({"protocol": 2})
    relay = c.FleetRelayClient(ORIGIN, transport=transport)
    body = b" " * bound
    relay._send_signed(
        "/api/fleet/v2/" + path, method, body, TOKEN, KEY, 7, AUTH["now"]
    )
    assert transport.requests[0].data == (body or None)
    monkeypatch.setattr(
        crypto, "sign_request", lambda *args: pytest.fail("signed oversize body")
    )
    with pytest.raises(ValueError):
        relay._send_signed(
            "/api/fleet/v2/" + path,
            method,
            body + b" ",
            TOKEN,
            KEY,
            7,
            AUTH["now"],
            before_send=lambda: pytest.fail("admitted oversize body"),
        )
    assert len(transport.requests) == 1


@pytest.mark.parametrize("name,key,kwargs,path", BOOT_CASES)
def test_actual_bootstrap_raw_ceiling_before_attempt_or_admission(
    name, key, kwargs, path, monkeypatch
):
    transport = FakeTransport({"protocol": 2})
    relay = c.FleetRelayClient(ORIGIN, transport=transport)
    relay._send_pre_session("/api/fleet/v2/" + path, b" " * 2048)
    assert transport.requests[0].data == b" " * 2048
    monkeypatch.setattr(
        c.secrets, "token_urlsafe", lambda *args: pytest.fail("minted oversize attempt")
    )
    with pytest.raises(ValueError):
        relay._send_pre_session(
            "/api/fleet/v2/" + path,
            b" " * 2049,
            lambda: pytest.fail("admitted oversize body"),
        )
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    "session",
    ["s", "B" * 43, "A" * 42, "A" * 44, TOKEN + "=", "a/../b", "A" * 42 + "\n"],
)
def test_noncanonical_signed_session_is_rejected_before_network(session):
    transport = FakeTransport(V["device"])
    with pytest.raises(ValueError):
        c.FleetRelayClient(ORIGIN, transport=transport).fetch_device(
            **{**AUTH, "session_id": session}
        )
    assert transport.requests == []


@pytest.mark.parametrize(
    "path",
    [
        "/api/fleet/v1/device",
        c.DEVICE_PATH + "/",
        c.DEVICE_PATH + "?x=1",
        c.DEVICE_PATH + "/extra",
        c.DEVICE_PATH.replace("device", "%64evice"),
        c.RECEIPTS_PATH + AUTO.request_id.upper(),
        c.RECEIPTS_PATH + AUTO.request_id + "/",
        c.RECEIPTS_PATH + AUTO.request_id + "?id=x",
        c.RECEIPTS_PATH + AUTO.request_id.replace("-", "%2d"),
        c.RECEIPTS_PATH + "22222222-2222-2222-8222-222222222222",
    ],
)
def test_literal_route_and_receipt_selector_cannot_be_tricked(path):
    transport = FakeTransport(V["device"])
    with pytest.raises(ValueError):
        c.FleetRelayClient(ORIGIN, transport=transport)._send_signed(
            path, "GET", b"", TOKEN, KEY, 7, AUTH["now"]
        )
    assert transport.requests == []


@pytest.mark.parametrize("index", range(len(BOOT_CASES)))
def test_bootstrap_admission_exception_is_not_disguised_as_http_error(index):
    name, key, kwargs, _ = BOOT_CASES[index]
    transport = FakeTransport(V[key])
    refusal = urllib.error.HTTPError("caller fence", 409, "caller reason", None, None)

    def refuse():
        raise refusal

    with pytest.raises(urllib.error.HTTPError) as exc:
        getattr(c.FleetRelayClient(ORIGIN, transport=transport), name)(
            **kwargs, before_send=refuse
        )
    assert exc.value is refusal
    assert transport.requests == []


@pytest.mark.parametrize("status", [200, 401, 409])
@pytest.mark.parametrize(
    "failure", [OSError, http.client.HTTPException, urllib.error.URLError]
)
def test_returned_response_close_errors_are_sanitized(status, failure):
    responses = []

    class ClosingResponse(Response):
        def close(self):
            super().close()
            raise failure("private close failure")

    def transport(request, **kw):
        payload = (
            V["device"] if status == 200 else {"protocol": 2, "error": "unauthorized"}
        )
        response = ClosingResponse(
            json.dumps(payload).encode(),
            framing_headers(request_binding(request)),
            status,
        )
        responses.append(response)
        return response

    with pytest.raises(c.FleetRelayError) as exc:
        c.FleetRelayClient(ORIGIN, transport=transport).fetch_device(**AUTH)
    assert exc.value.code == "transport_error" and exc.value.status is None
    assert responses[0].closed
    assert "private close failure" not in "".join(traceback.format_exception(exc.value))


@pytest.mark.parametrize("raising", [False, True])
@pytest.mark.parametrize(
    "field,value",
    [
        ("Content-Type", "text/html"),
        ("Cache-Control", "public"),
        ("Content-Encoding", "gzip"),
    ],
)
def test_malformed_error_framing_never_preserves_actionable_status(
    raising, field, value
):
    responses = []

    def transport(request, **kw):
        headers = framing_headers()
        del headers[field]
        headers[field] = value
        response = Response(b'{"protocol":2,"error":"unauthorized"}', headers, 401)
        responses.append(response)
        if raising:
            raise urllib.error.HTTPError(
                request.full_url, 401, "private reason", headers, response
            )
        return response

    with pytest.raises(c.FleetRelayError) as exc:
        c.FleetRelayClient(ORIGIN, transport=transport).fetch_device(**AUTH)
    assert exc.value.code == "malformed_response" and exc.value.status is None
    assert responses[0].closed and responses[0].reads == [65537]


@pytest.mark.parametrize(
    "result,extra",
    [
        ("device_revoked", {}),
        ("device_key_conflict", {}),
        ("account_ineligible", {"retry_after_ms": 86400000}),
        ("retry_later", {"retry_after_ms": 1}),
    ],
)
def test_recovery_definitive_outcomes_only_from_bound_closed_200(result, extra):
    transport = FakeTransport({"protocol": 2, "result": result, **extra})
    parsed = c.FleetRelayClient(ORIGIN, transport=transport).complete_recovery(
        private_key=KEY, challenge=p.parse_recovery_challenge(V["recovery_challenge"])
    )
    assert parsed.result == result
    assert parsed.requires_fresh_key_setup == (
        result in ("device_revoked", "device_key_conflict")
    )
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sampled_at_ms": 1, "rows": ()},
        {"sampled_at_ms": True, "rows": ()},
        {"sampled_at_ms": 0.0, "rows": ()},
        {"sampled_at_ms": -1, "rows": ()},
        {"sampled_at_ms": p.JS_SAFE_MAX + 1, "rows": ()},
        {"sampled_at_ms": 0, "rows": COMBAT.rows},
        {
            "sampled_at_ms": COMBAT.sampled_at_ms,
            "rows": (
                *COMBAT.rows,
                replace(COMBAT.rows[0], character_id=43, activity_age_ms=30000),
            ),
        },
        {
            "sampled_at_ms": COMBAT.sampled_at_ms,
            "rows": tuple(
                replace(COMBAT.rows[0], character_id=i + 1) for i in range(33)
            ),
        },
    ],
)
def test_invalid_whole_combat_batch_cannot_invoke_admission_or_send(kwargs):
    transport = FakeTransport({"protocol": 2})
    with pytest.raises(ValueError):
        c.FleetRelayClient(ORIGIN, transport=transport).publish_snapshot(
            **AUTH, **kwargs, before_send=lambda: pytest.fail("invalid batch admitted")
        )
    assert transport.requests == []


@pytest.mark.parametrize(
    "changes",
    [
        {"request_id": AUTO.request_id.upper()},
        {"expected_revision": 1.0},
        {"expected_generation": True},
        {"expected_generation": p.JS_SAFE_MAX + 1},
        {"intent_created_at": "0000-01-01T00:00:00.000Z"},
        {"enabled": 1},
    ],
)
def test_invalid_automatic_command_is_rejected_as_internal_value_before_json(changes):
    transport = FakeTransport(V["automatic_result"])
    with pytest.raises(ValueError):
        c.FleetRelayClient(ORIGIN, transport=transport).control_automatic(
            **AUTH,
            command=replace(AUTO, **changes),
            before_send=lambda: pytest.fail("invalid command admitted"),
        )
    assert transport.requests == []


@pytest.mark.parametrize(
    "id",
    [
        "FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF",
        "00000000-0000-0000-0000-000000000000",
        "ABCDEFAB-CDEF-8ABC-9ABC-ABCDEFABCDEF",
    ],
)
def test_existing_uuid_preserves_original_spelling_in_pairing_path_and_proof(id):
    transport = FakeTransport(V["pairing_completed"])
    proof = crypto.pairing_challenge_preimage(id)
    c.FleetRelayClient(ORIGIN, transport=transport).complete_pairing(id, proof, KEY)
    assert (
        transport.requests[0].full_url
        == ORIGIN + "/api/fleet/v2/pairing-requests/" + id + "/complete"
    )
    assert json.loads(transport.requests[0].data)[
        "completion_signature"
    ] == crypto.sign_request(KEY, proof)


@pytest.mark.parametrize(
    "which,field,value",
    [
        ("automatic_result", "receipt", None),
        ("automatic_result", "request_id", "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        ("source_stop_result", "receipt", None),
        ("source_stop_result", "automatic_effect", "manual_only"),
        ("source_start_result", "extra", 0),
    ],
)
def test_closed_result_and_null_relations_are_checked_through_http(which, field, value):
    payload = copy.deepcopy(V[which])
    payload[field] = value
    name = "control_automatic" if which == "automatic_result" else "control_source"
    command = (
        AUTO
        if which == "automatic_result"
        else START
        if which == "source_start_result"
        else STOP
    )
    with pytest.raises(c.FleetRelayError) as exc:
        getattr(c.FleetRelayClient(ORIGIN, transport=FakeTransport(payload)), name)(
            **AUTH, command=command
        )
    assert exc.value.code == "malformed_response"


@pytest.mark.parametrize("version", [1, 2])
def test_shared_old_worker_helper_never_adapts_old_snapshot_success(version):
    payload = {
        "protocol": version,
        "rows": [
            {
                "character_id": 42,
                "character_name": "Alice",
                "dps": 0,
                "ewar": [],
                "state": "live",
                "age_ms": 0,
            }
        ],
    }
    if version == 2:
        payload["server_time_ms"] = 10
    transport = FakeTransport(payload, publication=True)
    with pytest.raises(c.FleetRelayError) as exc:
        c.FleetRelayClient(ORIGIN, transport=transport).read_snapshot(**AUTH)
    assert exc.value.code == (
        "protocol_mismatch" if version == 1 else "malformed_response"
    )
    assert exc.value.status is None
    assert len(transport.requests) == 1


def test_publication_retry_preserves_original_sample_and_aggregates():
    transport = FakeTransport({"protocol": 2})
    relay = c.FleetRelayClient(ORIGIN, transport=transport)
    for now, revision in ((AUTH["now"], 7), (datetime(2027, 1, 1, tzinfo=UTC), 99)):
        relay.publish_snapshot(
            **{**AUTH, "now": now, "revision": revision},
            sampled_at_ms=COMBAT.sampled_at_ms,
            rows=COMBAT.rows,
        )
    assert transport.requests[0].data == transport.requests[1].data
    assert json.loads(transport.requests[1].data) == V["combat_put"]


@pytest.mark.parametrize("key", [b"", b"not DER", b"x" * 121])
def test_pairing_rejects_invalid_public_key_before_serialization_and_admission(
    key, monkeypatch
):
    transport = FakeTransport(V["pairing_begun"])
    monkeypatch.setattr(
        c, "_json", lambda value: pytest.fail("serialized invalid SPKI")
    )
    with pytest.raises(ValueError):
        c.FleetRelayClient(ORIGIN, transport=transport).begin_pairing(
            key, before_send=lambda: pytest.fail("admitted invalid SPKI")
        )
    assert transport.requests == []
