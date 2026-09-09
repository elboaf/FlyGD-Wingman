"""Freshness is admitted at transport, including empty responses, not in a UI."""

import hashlib
import io
import json
from datetime import UTC, datetime
from email.message import Message
from pathlib import Path
from uuid import UUID

import pytest
from test_fleetsharing_client import ORIGIN, _headers_of, error_transport
from test_fleetsharing_protocol import ROW

from wingman.fleetsharing import crypto
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing.client import FleetRelayClient, FleetRelayError

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/fleet-snapshot-publication-v1.json").read_text()
)
PUBLICATION = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OBSERVED = {**ROW, "publication_id": PUBLICATION}
AUTH = dict(
    session_id=FIXTURE["vectors"][1]["session_id"],
    private_key=bytes(32),
    revision=7,
    now=datetime(2026, 1, 1, tzinfo=UTC),
)


def response_headers(binding=FIXTURE["vectors"][1]["binding"]):
    headers = Message()
    headers["X-Fleet-Snapshot-Format"] = "publication-v1"
    headers["X-Fleet-Request-Binding"] = binding
    return headers


class Response(io.BytesIO):
    status = 200

    def __init__(self, payload, headers):
        super().__init__(json.dumps(payload).encode())
        self.headers = headers
        self.reads = []

    def read(self, amount=-1):
        self.reads.append(amount)
        return super().read(amount)


def test_binding_golden_and_each_canonical_field_mutation():
    for vector in FIXTURE["vectors"]:
        fields = {k: v for k, v in vector.items() if k != "binding"}
        canonical = crypto.canonical_fleet_request(**fields)
        assert crypto.snapshot_request_binding(canonical) == vector["binding"]
        assert (
            hashlib.sha256(FIXTURE["domain"].encode() + canonical).hexdigest()
            == vector["binding"]
        )
        for mutation in (
            {"method": "POST"},
            {"path": "/api/fleet/v1/catalogue"},
            {"session_id": "B" * 43},
            {"issued_at": "2026-01-01T00:00:00Z"},
            {"revision": 8},
            {"body_sha256": "0" * 64},
        ):
            assert (
                crypto.snapshot_request_binding(
                    crypto.canonical_fleet_request(**{**fields, **mutation})
                )
                != vector["binding"]
            )
        assert crypto.snapshot_request_binding(canonical + b"\n") != vector["binding"]
        assert hashlib.sha256(canonical).hexdigest() != vector["binding"]


def test_observed_parser_required_frozen_identity_and_legacy_separation():
    rows = p.parse_observed_snapshot({"protocol": 1, "rows": [OBSERVED]})
    assert rows == (p.ObservedRemoteRow(42, "Alice", 0, (), "live", 0, PUBLICATION),)
    with pytest.raises(TypeError):
        p.ObservedRemoteRow(42, "Alice", 0, (), "live", 0)
    for parse, row in ((p.parse_snapshot, OBSERVED), (p.parse_observed_snapshot, ROW)):
        with pytest.raises(ValueError):
            parse({"protocol": 1, "rows": [row]})
    assert p.parse_snapshot({"protocol": 1, "rows": [ROW]})[0].character_id == 42


@pytest.mark.parametrize(
    "publication",
    [
        None,
        "",
        42,
        PUBLICATION.upper(),
        PUBLICATION.replace("-", ""),
        PUBLICATION.replace("4aaa", "1aaa"),
        PUBLICATION.replace("8aaa", "7aaa"),
        "00000000-0000-0000-0000-000000000000",
    ],
)
def test_observed_publication_must_be_canonical_uuid4(publication):
    with pytest.raises(ValueError):
        p.parse_observed_snapshot(
            {"protocol": 1, "rows": [{**OBSERVED, "publication_id": publication}]}
        )


def test_observed_parser_retains_count_and_unique_character_and_publication_bounds():
    rows = [
        {
            **OBSERVED,
            "character_id": i + 1,
            "publication_id": str(UUID(int=i, version=4)),
        }
        for i in range(8193)
    ]
    assert len(p.parse_observed_snapshot({"protocol": 1, "rows": rows[:8192]})) == 8192
    for invalid in (
        rows,
        [OBSERVED, {**OBSERVED, "character_id": 43}],
        [OBSERVED, {**OBSERVED, "publication_id": str(UUID(int=1, version=4))}],
    ):
        with pytest.raises(ValueError):
            p.parse_observed_snapshot({"protocol": 1, "rows": invalid})


@pytest.mark.parametrize("rows", [[], [OBSERVED]])
def test_transport_negotiates_and_admits_matching_binding_before_rows(rows):
    response = Response({"protocol": 1, "rows": rows}, response_headers())
    requests = []

    def transport(request, timeout=None):
        requests.append(request)
        return response

    result = FleetRelayClient(ORIGIN, transport=transport).read_snapshot(**AUTH)
    assert len(result) == len(rows)
    if rows:
        assert result[0].publication_id == PUBLICATION
    assert _headers_of(requests[0])["x-fleet-snapshot-format"] == "publication-v1"
    assert requests[0].data is None
    assert response.closed and response.reads == [1024 * 1024 + 1]


@pytest.mark.parametrize("rows", [[], [OBSERVED]])
@pytest.mark.parametrize("mutation", [{"revision": 8}, {"session_id": "B" * 43}])
def test_old_whole_success_is_rejected_even_at_frozen_time(rows, mutation):
    response = Response({"protocol": 1, "rows": rows}, response_headers())
    relay = FleetRelayClient(ORIGIN, transport=lambda *a, **k: response)
    with pytest.raises(FleetRelayError) as exc:
        relay.read_snapshot(**{**AUTH, **mutation})
    assert exc.value.code == "malformed_response"
    assert response.closed and response.reads == []


@pytest.mark.parametrize(
    "field,value,duplicate,code",
    [
        ("X-Fleet-Snapshot-Format", None, False, "protocol_mismatch"),
        ("X-Fleet-Snapshot-Format", "legacy", False, "protocol_mismatch"),
        ("X-Fleet-Snapshot-Format", "publication-v1", True, "protocol_mismatch"),
        (
            "X-Fleet-Snapshot-Format",
            "publication-v1, publication-v1",
            False,
            "protocol_mismatch",
        ),
        ("X-Fleet-Request-Binding", None, False, "malformed_response"),
        ("X-Fleet-Request-Binding", "0" * 64, False, "malformed_response"),
        (
            "X-Fleet-Request-Binding",
            FIXTURE["vectors"][1]["binding"].upper(),
            False,
            "malformed_response",
        ),
        (
            "X-Fleet-Request-Binding",
            FIXTURE["vectors"][1]["binding"],
            True,
            "malformed_response",
        ),
        (
            "X-Fleet-Request-Binding",
            FIXTURE["vectors"][1]["binding"] + ", " + FIXTURE["vectors"][1]["binding"],
            False,
            "malformed_response",
        ),
        (
            "X-Fleet-Request-Binding",
            " " + FIXTURE["vectors"][1]["binding"],
            False,
            "malformed_response",
        ),
    ],
)
def test_missing_stripped_duplicate_or_malformed_headers_fail_before_json(
    field, value, duplicate, code
):
    headers = response_headers()
    if not duplicate:
        del headers[field]
    if value is not None:
        headers[field] = value
    response = Response({"protocol": 1, "rows": []}, headers)
    relay = FleetRelayClient(ORIGIN, transport=lambda *a, **k: response)
    with pytest.raises(FleetRelayError) as exc:
        relay.read_snapshot(**AUTH)
    assert exc.value.code == code
    assert response.closed and response.reads == []


def test_disabled_negotiated_read_is_recognized_without_success_headers():
    relay = FleetRelayClient(
        ORIGIN,
        transport=error_transport(503, {"protocol": 1, "error": "feature_disabled"}),
    )
    with pytest.raises(FleetRelayError) as exc:
        relay.read_snapshot(**AUTH)
    assert exc.value.code == "feature_disabled"
