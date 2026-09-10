"""Closed control/read DTOs, independent of the sparse publication schema."""

import copy
from dataclasses import FrozenInstanceError
from uuid import UUID as UUIDValue

import pytest

UUID = "3f9c1de2-7b8a-4c1f-9a2e-6d4b8f1c9a01"
TOKEN = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8"
DATE = "2026-09-07T12:00:00.000Z"
PARTICIPATION = {"enabled": False, "generation": 0}
DEVICE = {
    "protocol": 1,
    "device_id": UUID,
    "session_expires_at": DATE,
    "feature_enabled": True,
    "approved_capabilities": [],
    "session_approved_capabilities": ["shared-source-v1"],
    "acknowledged_capabilities": ["shared-source-v1"],
    "participation": PARTICIPATION,
}
SOURCE = {
    "source_id": UUID,
    "generation": 1,
    "character_id": None,
    "state": "ended",
    "reason": "stopped",
    "pending_expires_at": None,
}
CHARACTER = {
    "character_id": 42,
    "character_name": "<Alice & Bob>",
    "character_link_epoch": UUID,
    "has_fleet_read": True,
    "token_usable": False,
}
ELIGIBILITY = {
    "protocol": 1,
    "participation_generation": 0,
    "state": "ready",
    "characters": [
        {
            "character_id": 42,
            "source_id": UUID,
            "source_generation": 1,
            "authority_generation": 0,
            "expires_at": DATE,
        }
    ],
}
ROW = {
    "character_id": 42,
    "character_name": "Alice",
    "dps": 0,
    "ewar": [],
    "state": "live",
    "age_ms": 0,
}
CHALLENGE = {
    "protocol": 1,
    "challenge_id": UUID,
    "request_id": TOKEN,
    "nonce": TOKEN,
    "expires_at": DATE,
}
RECONNECTED = {
    "protocol": 1,
    "result": "reconnected",
    "device_id": UUID,
    "session_id": TOKEN,
    "session_expires_at": DATE,
    "approved_capabilities": ["shared-source-v1"],
    "participation": PARTICIPATION,
}
START = {
    "operation": "start",
    "source_id": UUID,
    "expected_generation": 0,
    "character_id": 42,
    "character_link_epoch": UUID,
    "intent_created_at": DATE,
}


def test_device_keeps_grant_ceiling_and_ack_separate_and_frozen():
    from wingman.fleetsharing import protocol as p

    result = p.parse_device(DEVICE)
    assert result.approved_capabilities == ()
    assert result.session_approved_capabilities == ("shared-source-v1",)
    assert result.acknowledged_capabilities == ("shared-source-v1",)
    assert result.participation == p.Participation(False, 0)
    with pytest.raises(FrozenInstanceError):
        result.feature_enabled = False


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("protocol", True),
        ("protocol", 1.0),
        ("protocol", 2),
        ("device_id", "../x"),
        ("device_id", "3f9c1de27b8a4c1f9a2e6d4b8f1c9a01"),
        ("session_expires_at", "2026-02-30T00:00:00.000Z"),
        ("session_expires_at", "2026-01-01T00:00:00Z"),
        ("session_expires_at", "2026-01-01T00:00:00.000+00:00"),
        ("feature_enabled", 1),
        ("capability_ceiling", []),
        ("approved_capabilities", ["unknown"]),
        ("acknowledged_capabilities", ["shared-source-v1", "shared-source-v1"]),
        ("participation", {"enabled": True, "generation": True}),
        ("participation", {"enabled": False, "generation": 2147483648}),
        ("participation", {"enabled": False, "generation": -1}),
        ("participation", {"enabled": False, "generation": 0, "account_id": 9}),
    ],
)
def test_device_rejects_unknown_and_malformed_fields(key, value):
    from wingman.fleetsharing import protocol as p

    with pytest.raises(ValueError):
        p.parse_device({**DEVICE, key: value})


def test_sources_and_commands_preserve_exact_bindings_and_nullable_fence():
    from wingman.fleetsharing import protocol as p

    result = p.parse_sources(
        {"protocol": 1, "sources": [SOURCE], "characters": [CHARACTER]}
    )
    assert result.sources[0] == p.SourceView(UUID, 1, None, "ended", "stopped", None)
    assert result.characters[0].character_name == "<Alice & Bob>"
    start = p.parse_source_command(START)
    assert p.source_command_body(start) == {"protocol": 1, **START}
    stop = p.StopSource(UUID, 0)
    assert p.source_command_body(stop) == {
        "protocol": 1,
        "operation": "stop",
        "source_id": UUID,
        "expected_generation": 0,
    }
    # An activated paused source need not retain the old pending deadline.
    paused = {**SOURCE, "character_id": 42, "state": "paused", "reason": "boss_lost"}
    assert (
        p.parse_source_control({"protocol": 1, "source": paused}).pending_expires_at
        is None
    )


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("generation", True),
        ("generation", 0),
        ("generation", 2147483648),
        ("character_id", 0),
        ("character_id", 9007199254740992),
        ("state", "unknown"),
        ("reason", "<script>alert(1)</script>"),
        ("pending_expires_at", "tomorrow"),
        ("account_id", 2),
    ],
)
def test_source_validation(key, value):
    from wingman.fleetsharing import protocol as p

    with pytest.raises(ValueError):
        p.parse_source_control({"protocol": 1, "source": {**SOURCE, key: value}})


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("operation", "restart"),
        ("source_id", "not-uuid"),
        ("expected_generation", True),
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


def test_sources_reject_more_than_sixteen_live_intents_not_retained_fences():
    from wingman.fleetsharing import protocol as p

    sources = [
        {
            **SOURCE,
            "source_id": str(UUIDValue(int=i, version=4)),
            "state": "paused",
            "character_id": i + 1,
        }
        for i in range(17)
    ]
    data = {"protocol": 1, "sources": sources, "characters": []}
    with pytest.raises(ValueError):
        p.parse_sources(data)
    sources[-1]["state"] = "ended"
    assert len(p.parse_sources(data).sources) == 17


def test_eligibility_and_snapshot_allow_real_boundaries():
    from wingman.fleetsharing import protocol as p

    result = p.parse_eligibility(ELIGIBILITY)
    assert result.characters[0] == p.EligibilityEntry(42, UUID, 1, 0, DATE)
    assert p.parse_snapshot({"protocol": 1, "rows": [ROW]}) == (
        p.RemoteRow(42, "Alice", 0, (), "live", 0),
    )
    for age, state in [(2999, "live"), (3000, "stale"), (9999, "stale")]:
        rows = p.parse_snapshot(
            {"protocol": 1, "rows": [{**ROW, "age_ms": age, "state": state}]}
        )
        assert rows[0].age_ms == age
    assert (
        len(
            p.parse_snapshot(
                {
                    "protocol": 1,
                    "rows": [{**ROW, "character_id": i + 1} for i in range(8192)],
                }
            )
        )
        == 8192
    )


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("character_id", True),
        ("character_id", 0),
        ("character_id", 9007199254740992),
        ("character_name", ""),
        ("character_name", "a" * 201),
        ("character_name", "Alice\nsecret"),
        ("character_name", "Alice\u202esecret"),
        ("character_name", "\ud800"),
        ("dps", True),
        ("dps", -1),
        ("dps", 10000001),
        ("ewar", ["SCRAM/POINT", "SCRAM/POINT"]),
        ("ewar", ["WEB"]),
        ("age_ms", 3000),
        ("age_ms", True),
        ("age_ms", 10000),
        ("age_ms", -1),
        ("state", "stale"),
        ("state", "unknown"),
        ("source_id", UUID),
    ],
)
@pytest.mark.parametrize("observed", [False, True])
def test_remote_row_rejects_hostile_or_inconsistent_data(key, value, observed):
    from wingman.fleetsharing import protocol as p

    with pytest.raises(ValueError):
        parse = p.parse_observed_snapshot if observed else p.parse_snapshot
        row = {**ROW, "publication_id": UUID} if observed else ROW
        parse({"protocol": 1, "rows": [{**row, key: value}]})


@pytest.mark.parametrize(
    "kind", ["snapshot", "sources", "source_characters", "eligibility"]
)
def test_rejects_duplicates_in_lists(kind):
    from wingman.fleetsharing import protocol as p

    cases = {
        "snapshot": (p.parse_snapshot, {"protocol": 1, "rows": [ROW, ROW]}),
        "sources": (
            p.parse_sources,
            {"protocol": 1, "sources": [SOURCE, SOURCE], "characters": []},
        ),
        "source_characters": (
            p.parse_sources,
            {"protocol": 1, "sources": [], "characters": [CHARACTER, CHARACTER]},
        ),
        "eligibility": (
            p.parse_eligibility,
            {**ELIGIBILITY, "characters": ELIGIBILITY["characters"] * 2},
        ),
    }
    parse, value = cases[kind]
    with pytest.raises(ValueError):
        parse(value)


@pytest.mark.parametrize(
    ("kind", "maximum"),
    [("snapshot", 8192), ("sources", 256), ("source_characters", 256)],
)
def test_rejects_oversized_lists_without_truncation(kind, maximum):
    from wingman.fleetsharing import protocol as p

    if kind == "snapshot":
        parse, data = (
            p.parse_snapshot,
            {
                "protocol": 1,
                "rows": [{**ROW, "character_id": i + 1} for i in range(maximum + 1)],
            },
        )
    else:
        parse = p.parse_sources
        data = {"protocol": 1, "sources": [], "characters": []}
        data["sources" if kind == "sources" else "characters"] = [
            SOURCE if kind == "sources" else CHARACTER
        ] * (maximum + 1)
    with pytest.raises(ValueError):
        parse(data)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("source_generation", 0),
        ("authority_generation", -1),
        ("authority_generation", True),
        ("expires_at", "bad"),
    ],
)
def test_eligibility_entry_checks(key, value):
    from wingman.fleetsharing import protocol as p

    data = copy.deepcopy(ELIGIBILITY)
    data["characters"][0][key] = value
    with pytest.raises(ValueError):
        p.parse_eligibility(data)


def test_recovery_variants_are_closed_and_preserve_postproof_outcome():
    from wingman.fleetsharing import protocol as p

    assert p.parse_recovery_challenge(CHALLENGE).request_id == TOKEN
    assert p.parse_recovery_result(RECONNECTED).participation == p.Participation(
        False, 0
    )
    for result in ("device_revoked", "device_key_conflict"):
        parsed = p.parse_recovery_result({"protocol": 1, "result": result})
        assert parsed.result == result
        assert parsed.requires_fresh_key_setup
    for result, delay in [("account_ineligible", 60000), ("retry_later", 1000)]:
        assert (
            p.parse_recovery_result(
                {"protocol": 1, "result": result, "retry_after_ms": delay}
            ).retry_after_ms
            == delay
        )


@pytest.mark.parametrize(
    "data",
    [
        {"protocol": 1, "result": "device_revoked", "session_id": TOKEN},
        {"protocol": 1, "result": "device_key_conflict", "retry_after_ms": 1},
        {"protocol": 1, "result": "unauthorized"},
        {"protocol": 1, "result": "account_ineligible", "retry_after_ms": 1000},
        {"protocol": 1, "result": "retry_later", "retry_after_ms": True},
        {**RECONNECTED, "session_id": "B" * 43},
        {**RECONNECTED, "approved_capabilities": ["unknown"]},
        {**RECONNECTED, "session_approved_capabilities": []},
    ],
)
def test_recovery_rejects_malformed_variants(data):
    from wingman.fleetsharing import protocol as p

    with pytest.raises(ValueError):
        p.parse_recovery_result(data)


@pytest.mark.parametrize(
    "raw",
    [b'{"protocol":1,"protocol":1}', b'{"a":{"x":0,"x":1}}', b'{"x":NaN}', b"[" * 2000],
)
def test_json_rejects_duplicate_keys_nonfinite_and_depth(raw):
    from wingman.fleetsharing import protocol as p

    with pytest.raises(ValueError):
        p.decode_json(raw)
