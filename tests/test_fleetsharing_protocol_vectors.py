"""Distributable vectors are decoded, not merely hash-checked or self-compared."""

import copy
from dataclasses import asdict
from uuid import UUID

import pytest
from test_fleetsharing_protocol import FIXTURE

from wingman.fleetsharing import protocol as p

ORIGIN = "https://relay.example.test"
DECODERS = {
    "catalogue": p.parse_catalogue,
    "pairing_begun": lambda value: p.parse_pairing_begun(value, origin=ORIGIN),
    "pairing_completed": p.parse_pairing_completed,
    "device": p.parse_device,
    "participation": p.parse_participation_response,
    "session": p.parse_session,
    "eligibility": p.parse_eligibility,
    "recovery_challenge": p.parse_recovery_challenge,
    "recovery_reconnected": p.parse_recovery_result,
    "recovery_retry": p.parse_recovery_result,
    "automatic_get": p.parse_automatic_get,
    "automatic_result": p.parse_automatic_result,
    "automatic_command": p.parse_automatic_command,
    "receipt_get": p.parse_receipt_get,
    "sources": p.parse_sources,
    "source": p.parse_source,
    "source_start": p.parse_source_command,
    "source_stop": p.parse_source_command,
    "source_start_result": p.parse_source_result,
    "source_stop_result": p.parse_source_result,
    "combat_put": p.parse_combat_put,
    "combat_get": p.parse_snapshot,
    "effect": p.parse_effect,
    "consent": p.parse_consent,
    "status": p.parse_automatic_status,
    "token": p.token,
    "date": p.utc_date,
    "text": p.text,
    "capabilities": p.capabilities,
    "integer": lambda value: p.integer(value, -p.JS_SAFE_MAX, p.JS_SAFE_MAX),
}


def descend(value, path):
    for key in path:
        value = value[key]
    return value


def apply_changes(value, changes):
    for path, replacement in changes:
        descend(value, path[:-1])[path[-1]] = replacement


def decode_case(case):
    # Paths are JSON key/index arrays; they do not depend on a Python DTO layout.
    value = copy.deepcopy(
        FIXTURE["valid"][case["base"]] if "base" in case else case["input"]
    )
    apply_changes(value, case.get("set", []))
    for path in case.get("remove", []):
        del descend(value, path[:-1])[path[-1]]
    decoder = p.parse_error if case["decoder"] == "error" else DECODERS[case["decoder"]]
    if "command" in case:
        command = copy.deepcopy(case["command"])
        apply_changes(command, case.get("command_set", []))
        parse = (
            p.parse_automatic_command
            if case["decoder"] == "automatic_result"
            else p.parse_source_command
        )
        return decoder(value, parse(command))
    return decoder(value)


@pytest.mark.parametrize(
    "case", FIXTURE["codec_vectors"], ids=lambda case: case["name"]
)
def test_shared_codec_vector(case):
    if not case["accept"]:
        with pytest.raises(ValueError):
            decode_case(case)
        return
    decoded = decode_case(case)
    value = asdict(decoded) if hasattr(decoded, "__dataclass_fields__") else decoded
    if "expect" in case:
        assert descend(value, case.get("expect_path", [])) == case["expect"]
    # Success can never be established by dropping a malformed row.
    if case["decoder"] in ("combat_put", "combat_get"):
        assert isinstance(decoded, (p.CombatPut, p.CombatSnapshot))


@pytest.mark.parametrize("case", FIXTURE["raw_vectors"], ids=lambda case: case["name"])
def test_fixed_raw_json_vectors(case):
    decoder = p.parse_error if case["decoder"] == "error" else DECODERS[case["decoder"]]
    raw = case["wire"].encode("utf-8")
    assert type(case["accept"]) is bool
    if "decoded_fields" in case:
        # A rejected unsupported integral version must reach the DTO as an int,
        # not fail prematurely because its exact spelling included a decimal.
        value = p.decode_wire_json(raw)
        for path, expected in case["decoded_fields"]:
            actual = descend(value, path)
            assert type(actual) is type(expected)
            assert actual == expected
        if case["accept"]:
            decoder(value)
        else:
            with pytest.raises(ValueError):
                decoder(value)
    else:
        assert case["accept"] is False
        with pytest.raises(ValueError):
            decoder(p.decode_wire_json(raw))


@pytest.mark.parametrize(
    "code",
    [
        "bad_headers",
        "bad_request",
        "update_required",
        "invalid_intent",
        "invalid_key",
        "unauthorized",
        "forbidden",
        "capability_required",
        "fleet_read_required",
        "not_verified",
        "receipt_not_found",
        "not_found",
        "method_not_allowed",
        "conflict",
        "request_id_conflict",
        "revision_replayed",
        "not_completable",
        "rate_limited",
        "receipt_capacity",
        "feature_disabled",
        "service_unavailable",
    ],
)
def test_closed_error_dictionary_is_not_a_success(code):
    error = {"protocol": 2, "error": code}
    assert p.parse_error(error) == code
    for parser in (
        p.parse_snapshot,
        p.parse_device,
        p.parse_automatic_result,
        p.parse_source_result,
        p.parse_recovery_result,
    ):
        with pytest.raises(ValueError):
            parser(error)


@pytest.mark.parametrize(
    "error",
    [
        {"protocol": 2, "error": "provider-secret"},
        {"protocol": 1, "error": "bad_request"},
        {"protocol": 2.0, "error": "bad_request"},
        {"protocol": 2, "error": None},
        {"protocol": 2, "error": "conflict", "status": {}},
        {"protocol": 2},
    ],
)
def test_error_decoder_rejects_unknown_or_malformed_envelopes(error):
    with pytest.raises(ValueError):
        p.parse_error(error)


@pytest.mark.parametrize("case", FIXTURE["list_vectors"], ids=lambda case: case["name"])
def test_shared_list_boundary(case):
    payload = copy.deepcopy(FIXTURE["valid"][case["decoder"]])
    rows = []
    for index in range(case["count"]):
        row = {**payload["rows"][0], "character_id": index + 1}
        if case["decoder"] == "combat_get":
            row["publication_id"] = str(UUID(int=index, version=4))
        rows.append(row)
    payload["rows"] = rows
    if case["accept"]:
        assert len(DECODERS[case["decoder"]](payload).rows) == case["count"]
    else:
        with pytest.raises(ValueError):
            DECODERS[case["decoder"]](payload)


def test_whole_snapshot_row_bound_and_independent_duplicate_keys():
    row = FIXTURE["valid"]["combat_get"]["rows"][0]
    rows = [
        {**row, "character_id": i + 1, "publication_id": str(UUID(int=i, version=4))}
        for i in range(8193)
    ]
    payload = {"protocol": 2, "server_time_ms": 12500, "rows": rows[:8192]}
    assert len(p.parse_snapshot(payload).rows) == 8192
    for invalid in (
        rows,
        [rows[0], {**rows[1], "character_id": 1}],
        [rows[0], {**rows[1], "publication_id": rows[0]["publication_id"]}],
    ):
        with pytest.raises(ValueError):
            p.parse_snapshot({**payload, "rows": invalid})


def test_put_bound_is_whole_batch_not_silent_truncation():
    row = FIXTURE["valid"]["combat_put"]["rows"][0]
    rows = [{**row, "character_id": i + 1} for i in range(33)]
    payload = {"protocol": 2, "sampled_at_ms": 12345, "rows": rows[:32]}
    assert len(p.parse_combat_put(payload).rows) == 32
    with pytest.raises(ValueError):
        p.parse_combat_put({**payload, "rows": rows})


def test_existing_uuid_identity_remains_case_insensitive():
    source = {
        **FIXTURE["valid"]["sources"]["sources"][0],
        "source_id": "abcdefab-abcd-4abc-8abc-abcdefabcdef",
    }
    assert p.parse_source(source).source_id == source["source_id"]
    with pytest.raises(ValueError):
        p.parse_sources(
            {
                "protocol": 2,
                "sources": [
                    source,
                    {**source, "source_id": source["source_id"].upper()},
                ],
                "characters": [],
            }
        )
