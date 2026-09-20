"""Request binding admits the complete combat DTO, including empty responses."""

import hashlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from test_fleetsharing_client import (
    ORIGIN,
    SESSION,
    _headers_of,
    error_transport,
    framing_headers,
)

from wingman.fleetsharing import crypto
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing.client import FleetRelayClient, FleetRelayError

ROW = {
    "character_id": 42,
    "character_name": "Alice",
    "outgoing_dps": 0,
    "incoming_dps": None,
    "activity_age_ms": 0,
    "effects": [],
    "state": "live",
    "age_ms": 0,
}
FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/fleet-snapshot-publication-v1.json").read_text()
)
PUBLICATION = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OBSERVED = {**ROW, "publication_id": PUBLICATION}
AUTH = dict(
    session_id=SESSION,
    private_key=bytes(32),
    revision=7,
    now=datetime(2026, 1, 1, tzinfo=UTC),
)
# Independent v2 HTTP expectation; the v1 fixture below remains primitive-only.
BINDING = hashlib.sha256(
    b"fleet-api-v2\nfleet-v1\nGET\n/api/fleet/v2/snapshot\n"
    + SESSION.encode()
    + b"\n2026-01-01T00:00:00.000Z\n7\n"
    + hashlib.sha256(b"").hexdigest().encode()
).hexdigest()


def response_headers(binding=BINDING):
    return framing_headers(binding)


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
    snapshot = p.parse_observed_snapshot(
        {"protocol": 2, "server_time_ms": 10, "rows": [OBSERVED]}
    )
    assert snapshot == p.CombatSnapshot(
        10, (p.CombatReadRow(42, 0, None, 0, (), "Alice", "live", 0, PUBLICATION),)
    )
    with pytest.raises(TypeError):
        p.CombatReadRow(42, 0, None, 0, (), "Alice", "live", 0)
    for parse in (p.parse_snapshot, p.parse_observed_snapshot):
        with pytest.raises(ValueError):
            parse({"protocol": 2, "server_time_ms": 10, "rows": [ROW]})
        with pytest.raises(ValueError):
            parse(
                {
                    "protocol": 1,
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
            )


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
            {
                "protocol": 2,
                "server_time_ms": 10,
                "rows": [{**OBSERVED, "publication_id": publication}],
            }
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
    assert (
        len(
            p.parse_observed_snapshot(
                {"protocol": 2, "server_time_ms": 10, "rows": rows[:8192]}
            ).rows
        )
        == 8192
    )
    for invalid in (
        rows,
        [OBSERVED, {**OBSERVED, "character_id": 43}],
        [OBSERVED, {**OBSERVED, "publication_id": str(UUID(int=1, version=4))}],
    ):
        with pytest.raises(ValueError):
            p.parse_observed_snapshot(
                {"protocol": 2, "server_time_ms": 10, "rows": invalid}
            )


@pytest.mark.parametrize("rows", [[], [OBSERVED]])
def test_transport_admits_matching_binding_before_complete_rows(rows):
    response = Response(
        {"protocol": 2, "server_time_ms": 10, "rows": rows}, response_headers()
    )
    requests = []

    def transport(request, timeout=None):
        requests.append(request)
        return response

    result = FleetRelayClient(ORIGIN, transport=transport).read_snapshot(**AUTH)
    assert result.server_time_ms == 10 and len(result.rows) == len(rows)
    if rows:
        assert result.rows[0].publication_id == PUBLICATION
    assert "x-fleet-snapshot-format" not in _headers_of(requests[0])
    assert requests[0].data is None
    assert response.closed and response.reads == [67108865]


@pytest.mark.parametrize("rows", [[], [OBSERVED]])
@pytest.mark.parametrize("mutation", [{"revision": 8}, {"session_id": "A" * 43}])
def test_old_whole_success_is_rejected_even_at_frozen_time(rows, mutation):
    response = Response(
        {"protocol": 2, "server_time_ms": 10, "rows": rows}, response_headers()
    )
    with pytest.raises(FleetRelayError) as exc:
        FleetRelayClient(ORIGIN, transport=lambda *a, **k: response).read_snapshot(
            **{**AUTH, **mutation}
        )
    assert exc.value.code == "malformed_response"
    assert response.closed and response.reads == []


@pytest.mark.parametrize(
    "field,value,duplicate",
    [
        ("Content-Type", None, False),
        ("Content-Type", "text/html", False),
        ("Content-Type", "application/json", True),
        ("Content-Type", "application/json, application/json", False),
        ("Cache-Control", None, False),
        ("Cache-Control", "public, max-age=60", False),
        ("Cache-Control", "no-store", True),
        ("X-Fleet-Request-Binding", None, False),
        ("X-Fleet-Request-Binding", "0" * 64, False),
        ("X-Fleet-Request-Binding", BINDING.upper(), False),
        ("x-FLEET-request-BINDING", BINDING, True),
        ("X-Fleet-Request-Binding", BINDING + ", " + BINDING, False),
        ("X-Fleet-Request-Binding", " " + BINDING, False),
    ],
)
def test_missing_stripped_duplicate_or_malformed_headers_fail_before_json(
    field, value, duplicate
):
    headers = response_headers()
    if not duplicate:
        del headers[field]
    if value is not None:
        headers[field] = value
    response = Response({"protocol": 2, "server_time_ms": 10, "rows": []}, headers)
    with pytest.raises(FleetRelayError) as exc:
        FleetRelayClient(ORIGIN, transport=lambda *a, **k: response).read_snapshot(
            **AUTH
        )
    assert exc.value.code == "malformed_response"
    assert response.closed and response.reads == []


def test_disabled_read_is_recognized_without_success_binding():
    with pytest.raises(FleetRelayError) as exc:
        FleetRelayClient(
            ORIGIN,
            transport=error_transport(
                503, {"protocol": 2, "error": "feature_disabled"}
            ),
        ).read_snapshot(**AUTH)
    assert exc.value.code == "feature_disabled" and exc.value.status == 503
