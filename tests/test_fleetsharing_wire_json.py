"""Exact raw-wire numbers, distinct from strict objects and legacy state parsing."""

import base64
import io
import json
import subprocess
import sys
import urllib.error
from datetime import UTC, datetime
from hashlib import sha256

import pytest
from cryptography.hazmat.primitives.serialization import load_der_public_key
from test_fleetsharing_client import framing_headers, request_binding
from test_fleetsharing_protocol import FIXTURE, TOKEN

from wingman.fleetsharing import client, crypto
from wingman.fleetsharing import protocol as p


@pytest.mark.parametrize(
    "lexeme,expected",
    [
        ("2", 2),
        ("2.0", 2),
        ("2e0", 2),
        ("20e-1", 2),
        ("-0", 0),
        ("-0.000e-999999999999999999999", 0),
        ("0e999999999999999999999", 0),
        ("2e+000000000000000000000", 2),
        ("20E-000000000000000000001", 2),
        ("0E+999999999999999999999", 0),
        ("2.147483647e9", 2147483647),
        ("42949672950e-1", 4294967295),
        ("9007199254740991.0", 9007199254740991),
        ("90071992547409910e-1", 9007199254740991),
        ("9.007199254740991e15", 9007199254740991),
        ("-9.007199254740991e15", -9007199254740991),
        ("1" + "0" * 5000 + "e-5000", 1),
        ("0." + "0" * 5000 + "12300e5003", 123),
        ("100.000e-2", 1),
    ],
    ids=lambda value: str(value)[:65],
)
def test_wire_exact_integral_lexemes(lexeme, expected):
    value = p.decode_wire_json(('{"n":' + lexeme + "}").encode())["n"]
    assert type(value) is int
    assert value == expected


@pytest.mark.parametrize(
    "lexeme",
    [
        "2.0000000000000001",
        "1.99999999999999999",
        "9007199254740990.5",
        "9007199254740991.1",
        "9007199254740992",
        "-9007199254740992",
        "1e-999999999999999999999",
        "1e999999999999999999999",
        "1e-324",
        "1e309",
        "0.1",
        "1001e-3",
        "NaN",
        "Infinity",
        "-Infinity",
        "01",
        "+2",
        ".2",
        "2.",
        "2e",
        "2e+",
        "0x2",
        "2_0",
        "--0",
        "1" * 5000,
    ],
    ids=lambda value: value[:65],
)
def test_wire_rejects_inexact_overflow_and_non_json_numbers(lexeme):
    with pytest.raises(ValueError):
        p.decode_wire_json(('{"n":' + lexeme + "}").encode())


@pytest.mark.parametrize("version", ["2", "2.0", "2e0", "20e-1"])
def test_wire_protocol_spelling_is_not_internal_float_coercion(version):
    value = p.decode_wire_json(
        ('{"protocol":' + version + ',"sampled_at_ms":-0.0,"rows":[]}').encode()
    )
    assert p.parse_combat_put(value).sampled_at_ms == 0


@pytest.mark.parametrize("lexeme,expected", [("1.0", 1), ("3e0", 3)])
def test_unsupported_wire_versions_remain_distinguishable_integers(lexeme, expected):
    value = p.decode_wire_json(
        ('{"protocol":' + lexeme + ',"sampled_at_ms":0,"rows":[]}').encode()
    )
    assert type(value["protocol"]) is int
    assert value["protocol"] == expected
    with pytest.raises(ValueError):
        p.parse_combat_put(value)


@pytest.mark.parametrize("value", [2.0, float("2.0000000000000001"), True])
def test_internal_integer_and_object_dto_validation_never_coerce_float(value):
    with pytest.raises(ValueError):
        p.integer(value)
    with pytest.raises(ValueError):
        p.parse_combat_put({"protocol": value, "sampled_at_ms": 0, "rows": []})
    with pytest.raises(ValueError):
        p.parse_combat_put({"protocol": 2, "sampled_at_ms": value, "rows": []})


def test_wire_decoding_still_applies_independent_field_limits():
    raw = b'{"protocol":2e0,"revision":42949672950e-1,"characters":[]}'
    assert p.parse_catalogue(p.decode_wire_json(raw)).revision == 4294967295
    value = p.decode_wire_json(b'{"enabled":true,"generation":2147483648.0}')
    with pytest.raises(ValueError):
        p.parse_participation(value)


@pytest.mark.parametrize("reader", ["decode_json", "decode_wire_json"])
@pytest.mark.parametrize(
    "raw",
    [
        b'{"x":1,"x":2}',
        b'{"a":{"x":1,"x":2}}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":"\xff"}',
        b"[" * 2000,
    ],
    ids=lambda value: repr(value)[:65],
)
def test_json_readers_share_utf8_duplicate_constant_depth_rejection(reader, raw):
    with pytest.raises(ValueError):
        getattr(p, reader)(raw)


def test_legacy_persisted_json_semantics_are_unchanged():
    # state.load/save use this entry point, not the new wire reader.
    value = p.decode_json(b'{"version":2.0,"fraction":1.5,"underflow":1e-9999}')
    assert type(value["version"]) is float
    assert value["fraction"] == 1.5
    assert value["underflow"] == 0.0
    assert p.decode_json(b"9007199254740992") == 9007199254740992


@pytest.mark.parametrize("value", ['{"n":2}', {"n": 2}, 2.0, bytearray(b"2")])
def test_wire_reader_accepts_only_raw_bytes(value):
    with pytest.raises(ValueError):
        p.decode_wire_json(value)


class Response(io.BytesIO):
    def __init__(self, raw, status=200):
        super().__init__(raw)
        self.status = status
        self.headers = framing_headers()
        self.read_sizes = []

    def read(self, size=-1):
        self.read_sizes.append(size)
        return super().read(size)


@pytest.mark.parametrize("lexeme", [b"2.0", b"2e0", b"20e-1"])
def test_actual_client_reader_exact_numbers_with_v2_framing(lexeme):
    response = Response(b'{"protocol":2,"revision":' + lexeme + b',"characters":[]}')

    def transport(request, **kwargs):
        response.headers = framing_headers(request_binding(request))
        return response

    result = client.FleetRelayClient(
        "https://relay.example.test", transport=transport
    ).fetch_catalogue(
        session_id=TOKEN,
        private_key=bytes(32),
        revision=1,
    )
    assert type(result.revision) is int and result.revision == 2
    assert response.closed
    assert response.read_sizes == [1048577]


@pytest.mark.parametrize(
    "lexeme", [b"2.0000000000000001", b"1e-99999", b"9007199254740992"]
)
def test_actual_client_reader_refuses_lossy_numbers_before_dto_acceptance(lexeme):
    response = Response(b'{"protocol":2,"revision":' + lexeme + b',"characters":[]}')

    def transport(request, **kwargs):
        response.headers = framing_headers(request_binding(request))
        return response

    with pytest.raises(client.FleetRelayError) as error:
        client.FleetRelayClient(
            "https://relay.example.test", transport=transport
        ).fetch_catalogue(
            session_id=TOKEN,
            private_key=bytes(32),
            revision=1,
        )
    assert error.value.code == "malformed_response"
    assert response.closed


def test_actual_client_admits_exact_integral_v2_success_after_transport_migration():
    response = Response(b'{"protocol":2.0,"revision":0,"characters":[]}')

    def transport(request, **kwargs):
        response.headers = framing_headers(request_binding(request))
        return response

    result = client.FleetRelayClient(
        "https://relay.example.test", transport=transport
    ).fetch_catalogue(
        session_id=TOKEN,
        private_key=bytes.fromhex(FIXTURE["private_key_hex"]),
        revision=1,
    )
    assert result.revision == 0 and result.characters == ()


@pytest.mark.parametrize("http_error", [False, True])
@pytest.mark.parametrize(
    "version,code",
    [
        ("2.0", "update_required"),
        ("20e-1", "update_required"),
        ("2.0000000000000001", "malformed_response"),
        ("1.0", "protocol_mismatch"),
        ("3e0", "protocol_mismatch"),
    ],
)
def test_actual_client_error_reader_exact_version_and_safe_fallback(
    http_error, version, code
):
    raw = ('{"protocol":' + version + ',"error":"update_required"}').encode()
    response = Response(raw, 400)

    def transport(request, **kwargs):
        if http_error:
            raise urllib.error.HTTPError(
                request.full_url, 400, "test", response.headers, response
            )
        return response

    relay = client.FleetRelayClient("https://relay.example.test", transport=transport)
    with pytest.raises(client.FleetRelayError) as error:
        relay.begin_pairing(
            crypto.public_key_spki(bytes.fromhex(FIXTURE["private_key_hex"]))
        )
    assert error.value.code == code
    assert response.closed
    assert response.read_sizes == [client.MAX_RESPONSE_BYTES + 1]


def test_actual_client_signs_original_bytes_not_decoded_numeric_values():
    raw = b'{"protocol":2.0,"capabilities":[]}'
    assert p.decode_wire_json(raw) == {"protocol": 2, "capabilities": []}
    requests = []

    def transport(request, **kwargs):
        requests.append(request)
        response = Response(b'{"protocol":2}')
        response.headers = framing_headers(request_binding(request))
        return response

    key = bytes.fromhex(FIXTURE["private_key_hex"])
    relay = client.FleetRelayClient("https://relay.example.test", transport=transport)
    relay._send_signed(
        client.DEVICE_PATH, "PUT", raw, TOKEN, key, 1, datetime(2026, 1, 1, tzinfo=UTC)
    )
    (request,) = requests
    assert request.data == raw
    headers = {name.lower(): value for name, value in request.header_items()}
    assert headers["x-fleet-body-sha256"] == sha256(raw).hexdigest()
    canonical = crypto.canonical_fleet_request(
        protocol=1,
        method="PUT",
        path=client.DEVICE_PATH,
        session_id=TOKEN,
        issued_at=headers["x-fleet-issued-at"],
        revision=1,
        body_sha256=sha256(raw).hexdigest(),
    )
    load_der_public_key(crypto.public_key_spki(key)).verify(
        base64.urlsafe_b64decode(headers["x-fleet-signature"] + "=="), canonical
    )


def test_numeric_adversaries_have_bounded_time_and_allocation_in_subprocess():
    # This exercises bounded numeric parsing, not a 64-MiB HTTP response admission.
    program = """
import json, time, tracemalloc
from wingman.fleetsharing import protocol as p
n = 100_000
cases = [
    (b"0e" + b"9" * n, 0),
    (b"-0.0e-" + b"9" * n, 0),
    (b"2e+" + b"0" * n, 2),
    (b"1e" + b"9" * n, None),
    (b"1e-" + b"9" * n, None),
    (b"1" + b"0" * n + b"e-100000", 1),
    (b"0." + b"0" * n + b"123e100003", 123),
    (b"2." + b"0" * n + b"1", None),
]
tracemalloc.start()
start = time.perf_counter()
for raw, expected in cases:
    try:
        result = p.decode_wire_json(raw)
    except ValueError:
        assert expected is None
    else:
        assert expected is not None and type(result) is int and result == expected
elapsed = time.perf_counter() - start
_, peak = tracemalloc.get_traced_memory()
print(json.dumps({"seconds": elapsed, "peak_bytes": peak, "cases": len(cases), "max_raw_bytes": max(len(raw) for raw, _ in cases)}))
assert peak < 16 * 1024 * 1024
assert elapsed < 5
"""
    result = subprocess.run(
        [sys.executable, "-c", program], text=True, capture_output=True, timeout=15
    )
    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout)
    print(evidence)
    assert evidence["cases"] == 8
