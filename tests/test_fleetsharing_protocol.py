"""Closed fleet-v2 DTOs, codec semantics and relation checks."""

import copy
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "fleet-api-v2.json").read_text(
        encoding="utf-8"
    )
)

UUID = FIXTURE["valid"]["device"]["device_id"]
TOKEN = FIXTURE["recovery_begin"]["request_id"]
DATE = FIXTURE["valid"]["device"]["session_expires_at"]
PARTICIPATION = FIXTURE["valid"]["participation"]["participation"]
DEVICE = FIXTURE["valid"]["device"]
SOURCE = next(
    source
    for source in FIXTURE["valid"]["sources"]["sources"]
    if source["state"] == "ended"
)
CHARACTER = FIXTURE["valid"]["sources"]["characters"][0]
ELIGIBILITY = FIXTURE["valid"]["eligibility"]
ROW = FIXTURE["valid"]["combat_get"]["rows"][0]
CHALLENGE = FIXTURE["valid"]["recovery_challenge"]
RECONNECTED = FIXTURE["valid"]["recovery_reconnected"]
START = FIXTURE["valid"]["source_start"]
STOP = FIXTURE["valid"]["source_stop"]


def test_versions_device_and_catalogue_hash_boundary_are_closed_and_frozen():
    from wingman.fleetsharing import protocol as p

    result = p.parse_device(DEVICE)
    assert p.API_VERSION == 2
    assert p.SIGNING_SCHEME_VERSION == 1
    assert result.approved_capabilities == ("shared-source-v1", "combat-v2")
    assert result.session_approved_capabilities == ("shared-source-v1", "combat-v2")
    assert result.acknowledged_capabilities == ("shared-source-v1",)
    assert result.participation == p.Participation(False, 0)
    assert result.server_time_ms == 1234567890
    assert p.parse_catalogue(FIXTURE["valid"]["catalogue"]).revision == 4294967295
    with pytest.raises(FrozenInstanceError):
        result.feature_enabled = False


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("protocol", True),
        ("protocol", 2.0),
        ("protocol", 1),
        ("device_id", "../x"),
        ("session_expires_at", "2026-01-01T00:00:00Z"),
        ("feature_enabled", 1),
        ("approved_capabilities", ["combat-v2"]),
        ("acknowledged_capabilities", ["combat-v2"]),
        ("participation", {"enabled": False, "generation": 0, "extra": 1}),
        ("server_time_ms", -1),
        ("server_time_ms", 9007199254740992),
    ],
)
def test_device_rejects_unknown_and_malformed_fields(key, value):
    from wingman.fleetsharing import protocol as p

    with pytest.raises(ValueError):
        p.parse_device({**DEVICE, key: value})


def test_sources_commands_and_results_preserve_exact_bindings():
    from wingman.fleetsharing import protocol as p

    result = p.parse_sources(FIXTURE["valid"]["sources"])
    assert result.sources[0] == p.SourceView(
        SOURCE["source_id"], 1, 42, "ended", "stopped", None, p.AutomaticBinding(7)
    )
    assert result.sources[1].automatic == p.AutomaticBinding(7)
    assert result.characters[0].character_name == "Alice"

    start = p.parse_source_command(START)
    assert p.source_command_body(start) == START

    stop = p.parse_source_command(STOP)
    assert p.source_command_body(stop) == STOP
    assert stop.expected_automatic == p.AutomaticBinding(7)

    parsed_start = p.parse_source_result(FIXTURE["valid"]["source_start_result"], start)
    assert parsed_start.source.automatic is None

    parsed_stop = p.parse_source_result(FIXTURE["valid"]["source_stop_result"], stop)
    assert parsed_stop.automatic_effect == "disabled_current"
    assert parsed_stop.receipt is not None


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("generation", 0),
        ("generation", 2147483648),
        ("character_id", 0),
        ("state", "unknown"),
        ("pending_expires_at", "tomorrow"),
        ("automatic", {"consent_generation": 0}),
        ("extra", 2),
    ],
)
def test_source_validation(key, value):
    from wingman.fleetsharing import protocol as p

    source = copy.deepcopy(SOURCE)
    source[key] = value
    with pytest.raises(ValueError):
        p.parse_source(source)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("operation", "restart"),
        ("source_id", "not-uuid"),
        ("expected_generation", 1),
        ("character_id", True),
        ("character_link_epoch", "x"),
        ("intent_created_at", "2026-02-30T12:00:00.000Z"),
        ("extra", 3),
    ],
)
def test_start_command_validation(key, value):
    from wingman.fleetsharing import protocol as p

    with pytest.raises(ValueError):
        p.parse_source_command({**START, key: value})


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("request_id", FIXTURE["invalid"]["uppercase_request_id"]),
        ("expected_generation", 2147483647),
        ("expected_automatic", {"consent_generation": -1}),
        ("extra", 3),
    ],
)
def test_stop_command_validation(key, value):
    from wingman.fleetsharing import protocol as p

    with pytest.raises(ValueError):
        p.parse_source_command({**STOP, key: value})


def test_sources_enforce_sorted_ids_and_sixteen_live_limit():
    from wingman.fleetsharing import protocol as p

    data = copy.deepcopy(FIXTURE["valid"]["sources"])
    with pytest.raises(ValueError):
        p.parse_sources({**data, "sources": list(reversed(data["sources"]))})

    sources = []
    for index in range(17):
        sources.append(
            {
                **SOURCE,
                "source_id": f"{index + 1:08d}-1111-1111-8111-111111111111",
                "state": "active",
                "reason": None,
                "pending_expires_at": None,
                "automatic": None,
            }
        )
    with pytest.raises(ValueError):
        p.parse_sources({"protocol": 2, "sources": sources, "characters": []})
    sources[-1]["state"] = "ended"
    sources[-1]["reason"] = "stopped"
    assert (
        len(
            p.parse_sources(
                {"protocol": 2, "sources": sources, "characters": []}
            ).sources
        )
        == 17
    )


def test_eligibility_and_combat_codecs_allow_real_boundaries():
    from wingman.fleetsharing import protocol as p

    result = p.parse_eligibility(ELIGIBILITY)
    assert result.characters[0] == p.EligibilityEntry(
        42, SOURCE["source_id"], 1, 0, DATE
    )

    put = p.parse_combat_put(FIXTURE["valid"]["combat_put"])
    assert put.sampled_at_ms == 12345
    assert put.rows[0].effects[0].kind == "SCRAM"

    snapshot = p.parse_snapshot(FIXTURE["valid"]["combat_get"])
    assert snapshot.server_time_ms == 12500
    assert snapshot.rows[0] == p.CombatReadRow(
        character_id=42,
        outgoing_dps=0,
        incoming_dps=12,
        activity_age_ms=1000,
        effects=(
            p.Effect(
                "SCRAM",
                (
                    p.Observation("Pilot", 1000),
                    p.Observation(None, 1500),
                ),
            ),
            p.Effect("POINT", (p.Observation("A  B", 1500),)),
            p.Effect("NEUT", (p.Observation(None, 2000),)),
        ),
        character_name="Alice",
        state="live",
        age_ms=500,
        publication_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    )

    for age, state in [(2999, "live"), (3000, "stale"), (9999, "stale")]:
        data = copy.deepcopy(FIXTURE["valid"]["combat_get"])
        data["rows"][0]["age_ms"] = age
        data["rows"][0].update(state=state, activity_age_ms=10000, effects=[])
        assert p.parse_snapshot(data).rows[0].age_ms == age

    rows = [
        {**FIXTURE["valid"]["combat_put"]["rows"][0], "character_id": index + 1}
        for index in range(32)
    ]
    assert (
        len(
            p.parse_combat_put(
                {"protocol": 2, "sampled_at_ms": 12345, "rows": rows}
            ).rows
        )
        == 32
    )
    assert (
        p.parse_combat_put({"protocol": 2, "sampled_at_ms": 0, "rows": []}).rows == ()
    )


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("character_id", True),
        ("character_id", 0),
        ("outgoing_dps", -1),
        ("incoming_dps", 10000001),
        ("activity_age_ms", 30000),
        (
            "effects",
            [
                {
                    "kind": "POINT",
                    "observations": [
                        {"name": None, "age_ms": 1000},
                        {"name": None, "age_ms": 1001},
                    ],
                }
            ],
        ),
        (
            "effects",
            [{"kind": "NEUT", "observations": [{"name": "Pilot", "age_ms": 1000}]}],
        ),
        (
            "effects",
            [
                {
                    "kind": "POINT",
                    "observations": [
                        {
                            "name": FIXTURE["invalid"]["decomposed_observed_name"],
                            "age_ms": 1000,
                        }
                    ],
                }
            ],
        ),
        (
            "effects",
            [
                {
                    "kind": "POINT",
                    "observations": [
                        {"name": None, "age_ms": 999},
                        {"name": "Pilot", "age_ms": 1000},
                    ],
                }
            ],
        ),
        (
            "effects",
            [
                {"kind": "POINT", "observations": [{"name": "Pilot", "age_ms": 1000}]},
                {"kind": "SCRAM", "observations": [{"name": "Pilot", "age_ms": 1000}]},
            ],
        ),
    ],
)
def test_combat_rows_reject_hostile_or_inconsistent_data(key, value):
    from wingman.fleetsharing import protocol as p

    payload = copy.deepcopy(FIXTURE["valid"]["combat_put"])
    payload["rows"][0][key] = value
    with pytest.raises(ValueError):
        p.parse_combat_put(payload)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update(result="already_off"),
        lambda payload: payload.update(
            request_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc"
        ),
        lambda payload: payload["receipt"]["command"].update(
            request_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc"
        ),
        lambda payload: payload["receipt"]["result"].update(revision=10),
        lambda payload: payload["status"]["consent"].update(revision=8),
    ],
)
def test_automatic_result_relation_validation(mutation):
    from wingman.fleetsharing import protocol as p

    payload = copy.deepcopy(FIXTURE["valid"]["automatic_result"])
    mutation(payload)
    with pytest.raises(ValueError):
        p.parse_automatic_result(
            payload,
            p.parse_automatic_command(
                FIXTURE["valid"]["automatic_result"]["receipt"]["command"]
            ),
        )


def test_automatic_variants_and_recovery_results_are_closed():
    from wingman.fleetsharing import protocol as p

    status = p.parse_automatic_get(FIXTURE["valid"]["automatic_get"]).status
    assert status.sources == (
        p.SourceBinding("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", 2, 7),
    )

    result = p.parse_automatic_result(
        FIXTURE["valid"]["automatic_result"],
        p.parse_automatic_command(
            FIXTURE["valid"]["automatic_result"]["receipt"]["command"]
        ),
    )
    assert result.receipt is not None
    assert result.receipt.result.revision == 9
    assert (
        p.parse_receipt_get(
            FIXTURE["valid"]["receipt_get"],
            expected_request_id=FIXTURE["valid"]["automatic_result"]["request_id"],
        ).receipt.kind
        == "automatic"
    )

    assert (
        p.parse_recovery_challenge(CHALLENGE, expected_request_id=TOKEN).request_id
        == TOKEN
    )
    assert p.parse_recovery_result(RECONNECTED).participation == p.Participation(
        False, 0
    )
    assert (
        p.parse_recovery_result(FIXTURE["valid"]["recovery_retry"]).retry_after_ms
        == 86400000
    )
    for result_name in ("device_revoked", "device_key_conflict"):
        parsed = p.parse_recovery_result({"protocol": 2, "result": result_name})
        assert parsed.result == result_name
        assert parsed.requires_fresh_key_setup


@pytest.mark.parametrize(
    "payload",
    [
        {"protocol": 2, "result": "device_revoked", "session_id": TOKEN},
        {"protocol": 2, "result": "retry_later", "retry_after_ms": True},
        {**RECONNECTED, "approved_capabilities": ["combat-v2"]},
        {**RECONNECTED, "session_id": "B" * 43},
    ],
)
def test_recovery_rejects_malformed_variants(payload):
    from wingman.fleetsharing import protocol as p

    with pytest.raises(ValueError):
        p.parse_recovery_result(payload)


@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize(
    "revision,accept",
    [
        (0, True),
        (2147483647, True),
        (2147483648, True),
        (3820012610, True),  # Actual empty service catalogue fingerprint.
        (3112514310, True),  # Actual 92100001:Alpha service fingerprint.
        (4294967295, True),
        (-1, False),
        (4294967296, False),
        (1.5, False),
        (True, False),
    ],
)
def test_catalogue_uint32_fingerprint_standalone_and_pairing(nested, revision, accept):
    from wingman.fleetsharing import protocol as p

    catalogue = {"revision": revision, "characters": []}
    if nested:
        payload = {"protocol": 2, "session_id": TOKEN, "catalogue": catalogue}
        parser = p.parse_pairing_completed
    else:
        payload = {"protocol": 2, **catalogue}
        parser = p.parse_catalogue
    if not accept:
        with pytest.raises(ValueError):
            parser(payload)
        return
    result = parser(payload)
    assert (result.catalogue if nested else result).revision == revision


def test_catalogue_uint32_does_not_widen_signed_or_source_counters():
    from wingman.fleetsharing import protocol as p

    assert p.integer(2147483647) == 2147483647
    for value in (2147483648, 3820012610, 4294967295, 2.0, True):
        with pytest.raises(ValueError):
            p.integer(value)
        with pytest.raises(ValueError):
            p.parse_source({**SOURCE, "generation": value})


@pytest.mark.parametrize(
    "kind",
    ["combat_get", "sources", "eligibility"],
)
def test_rejects_duplicates_in_lists(kind):
    from wingman.fleetsharing import protocol as p

    if kind == "combat_get":
        payload = copy.deepcopy(FIXTURE["valid"]["combat_get"])
        payload["rows"] = payload["rows"] * 2
        parser = p.parse_snapshot
    elif kind == "sources":
        payload = copy.deepcopy(FIXTURE["valid"]["sources"])
        payload["sources"] = payload["sources"] * 2
        parser = p.parse_sources
    else:
        payload = copy.deepcopy(FIXTURE["valid"]["eligibility"])
        payload["characters"] = payload["characters"] * 2
        parser = p.parse_eligibility
    with pytest.raises(ValueError):
        parser(payload)


@pytest.mark.parametrize(
    "raw",
    [b'{"protocol":2,"protocol":2}', b'{"a":{"x":0,"x":1}}', b'{"x":NaN}', b"[" * 2000],
)
def test_json_rejects_duplicate_keys_nonfinite_and_depth(raw):
    from wingman.fleetsharing import protocol as p

    with pytest.raises(ValueError):
        p.decode_json(raw)
