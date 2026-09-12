"""Deployed v1 parity and fail-closed location/identity/URL boundaries."""

import copy
import json
import math
import tomllib
import traceback
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "wanderer" / "deployed-v1.json"


def candidate():
    return json.loads(FIXTURE.read_bytes())


def parse(data=None, receipt=100.0):
    from wingman.wanderer.model import parse_snapshot

    return parse_snapshot(
        json.dumps(candidate() if data is None else data).encode(), receipt
    )


def test_deployed_fixture_display_identity_and_immutable_snapshot():
    from wingman.wanderer.model import parse_snapshot

    snapshot = parse_snapshot(FIXTURE.read_bytes(), 100.0)
    assert snapshot.revision == "fixture-revision"
    assert [r.character_id for r in snapshot.records] == list(range(90000001, 90000006))
    assert [r.display_at(100.0) for r in snapshot.records] == [
        "HOME",
        "Amarr",
        None,
        None,
        None,
    ]
    first = snapshot.record_for("  FIRST PILOT  ")
    assert first is snapshot.records[0]
    assert snapshot.record_for("First") is None
    assert snapshot.record_for("First  Pilot") is None
    assert first.solar_system_id == 30000142
    assert snapshot.records[1].solar_system_id == 30002187
    assert first.deadline_monotonic == 114.0
    assert first.display_at(113.999999) == "HOME"
    assert first.display_at(114.0) is None
    with pytest.raises(FrozenInstanceError):
        first.display_name = "changed"
    with pytest.raises(FrozenInstanceError):
        snapshot.revision = "changed"
    with pytest.raises(TypeError):
        snapshot.by_name["other"] = first


def test_exact_normalized_unicode_identity_without_fuzzy_matching():
    data = candidate()
    data["data"][0]["character_name"] = "Éowyn Pilot"
    snapshot = parse(data)
    assert snapshot.record_for("e\u0301OWYN PILOT").character_id == 90000001
    assert snapshot.record_for("Eowyn Pilot") is None


@pytest.mark.parametrize(
    "display,raw,want",
    [
        (None, "Jita", "Jita"),
        ("", "Jita", "Jita"),
        ("  ", "Jita", "Jita"),
        ("Alias", None, "Alias"),
        (None, None, None),
        ("", "", None),
    ],
)
def test_visible_effective_name_or_raw_fallback_never_synthesized(display, raw, want):
    data = candidate()
    data["data"][0].update(display_name=display, solar_system_name=raw)
    assert parse(data).records[0].display_at(100) == want


@pytest.mark.parametrize(
    "age,deadline", [(0, 115), (1, 114), (14, 101), (15, 100), (16, 100)]
)
def test_server_relative_age_not_local_wall_time(age, deadline):
    data = candidate()
    data["observed_at"] = f"2026-09-10T20:00:{age:02d}Z"
    record = parse(data).records[0]
    assert record.deadline_monotonic == deadline
    assert record.display_at(deadline) is None
    if deadline > 100:
        assert record.display_at(deadline - 0.000001) == "HOME"


def test_fractional_age_preserved():
    data = candidate()
    data["observed_at"] = "2026-09-10T20:00:14.500000Z"
    record = parse(data).records[0]
    assert record.deadline_monotonic == 100.5
    assert record.display_at(100.499999) == "HOME"
    assert record.display_at(100.5) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("character_id", True),
        ("character_id", 0),
        ("character_id", -1),
        ("character_id", 90000001.0),
        ("character_id", "90000001"),
        ("character_id", 9007199254740992),
        ("character_name", None),
        ("character_name", ""),
        ("character_name", "  "),
        ("tracked", False),
        ("tracked", 1),
        ("online", 1),
        ("online", "true"),
        ("solar_system_id", True),
        ("solar_system_id", 0),
        ("solar_system_id", 1.5),
        ("solar_system_id", "30000142"),
        ("solar_system_id", 9007199254740992),
        ("map_system_visible", 1),
        ("map_system_visible", None),
        ("solar_system_name", 123),
        ("display_name", []),
        ("location_observed_at", None),
        ("map_system_updated_at", None),
        ("location_observed_at", "2026-09-10T20:00:01.000001Z"),
        ("map_system_updated_at", "2026-09-10T20:00:02Z"),
    ],
)
def test_rejects_whole_snapshot_for_invalid_record(field, value):
    from wingman.wanderer.model import SnapshotError

    data = candidate()
    data["data"][0][field] = value
    with pytest.raises(SnapshotError):
        parse(data)


@pytest.mark.parametrize(
    "field", ["character_name", "display_name", "solar_system_name"]
)
@pytest.mark.parametrize(
    "value",
    [
        "x" * 256,
        "\U00020000" * 256,
        "line\nname",
        "\tname",
        "bad\x00",
        "bad\x7f",
        "bad\u0085",
        "bad\u202e",
        "bad\u2028",
        "bad\u2029",
        "bad\ud800",
    ],
)
def test_name_bounds_and_unsafe_single_line_text(field, value):
    from wingman.wanderer.model import SnapshotError

    data = candidate()
    data["data"][0][field] = value
    with pytest.raises(SnapshotError):
        parse(data)


@pytest.mark.parametrize("value", ["x" * 255, "\U00020000" * 255])
def test_accepts_name_codepoint_boundary(value):
    data = candidate()
    data["data"][0]["display_name"] = value
    assert parse(data).records[0].display_at(100) == value


@pytest.mark.parametrize(
    "field", ["observed_at", "location_observed_at", "map_system_updated_at"]
)
@pytest.mark.parametrize(
    "value",
    [
        "2026-09-10",
        "2026-09-10T20:00:00",
        "2026-09-10 20:00:00Z",
        "2026-09-10T20:00:00+01:00",
        "2026-09-10T20:00:00.1234567Z",
        "2026-02-30T20:00:00Z",
        "0000-01-01T00:00:00Z",
        "x" * 1000,
        123,
        True,
    ],
)
def test_timestamp_syntax_bounds_and_utc_only(field, value):
    from wingman.wanderer.model import SnapshotError

    data = candidate()
    (data if field == "observed_at" else data["data"][0])[field] = value
    with pytest.raises(SnapshotError):
        parse(data)


@pytest.mark.parametrize(
    "changes",
    [
        {"online": False},
        {"online": None},
        {"solar_system_id": None},
        {"map_system_visible": False},
    ],
)
def test_rejects_incoherent_available_record(changes):
    from wingman.wanderer.model import SnapshotError

    data = candidate()
    data["data"][0].update(changes)
    with pytest.raises(SnapshotError):
        parse(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("online", True),
        ("solar_system_name", "Jita"),
        ("display_name", "SECRET"),
        ("location_observed_at", "2026-09-10T20:00:00Z"),
        ("map_system_updated_at", "2026-09-10T19:30:00Z"),
        ("map_system_visible", True),
    ],
)
def test_rejects_incoherent_unavailable_record(field, value):
    from wingman.wanderer.model import SnapshotError

    data = candidate()
    data["data"][3][field] = value
    with pytest.raises(SnapshotError):
        parse(data)


@pytest.mark.parametrize(
    "field,value",
    [("display_name", "SECRET"), ("map_system_updated_at", "2026-09-10T19:30:00Z")],
)
def test_hidden_records_cannot_smuggle_map_data(field, value):
    from wingman.wanderer.model import SnapshotError

    data = candidate()
    data["data"][1][field] = value
    with pytest.raises(SnapshotError):
        parse(data)


@pytest.mark.parametrize(
    "mode",
    [
        "id",
        "name",
        "order",
        "record-extra",
        "record-missing",
        "envelope-extra",
        "envelope-missing",
        "non-object",
        "non-list",
        "non-record",
        "revision-empty",
        "revision-control",
        "revision-huge",
    ],
)
def test_strict_complete_envelope_identity_and_field_allowlists(mode):
    from wingman.wanderer.model import SnapshotError

    data = candidate()
    if mode == "id":
        data["data"][1]["character_id"] = 90000001
    elif mode == "name":
        data["data"][1]["character_name"] = " first PILOT "
    elif mode == "order":
        data["data"].reverse()
    elif mode == "record-extra":
        data["data"][0]["access_token"] = "SENSITIVE_SENTINEL"
    elif mode == "record-missing":
        del data["data"][0]["display_name"]
    elif mode == "envelope-extra":
        data["connections"] = ["SENSITIVE_SENTINEL"]
    elif mode == "envelope-missing":
        del data["revision"]
    elif mode == "non-object":
        data = []
    elif mode == "non-list":
        data["data"] = {}
    elif mode == "non-record":
        data["data"][0] = []
    elif mode == "revision-empty":
        data["revision"] = ""
    elif mode == "revision-control":
        data["revision"] = "SENSITIVE_SENTINEL\r\n"
    else:
        data["revision"] = "x" * 1025
    with pytest.raises(SnapshotError) as caught:
        parse(data)
    assert "SENSITIVE_SENTINEL" not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize(
    "body",
    [
        b'{"data":[],"data":[]}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":1e999}',
        b"\xff",
        b"null",
        b"[",
        b"[" * 2000 + b"]" * 2000,
    ],
)
def test_rejects_malformed_duplicate_nonfinite_or_deep_json(body):
    from wingman.wanderer.model import SnapshotError, parse_snapshot

    with pytest.raises(SnapshotError):
        parse_snapshot(body, 100)


@pytest.mark.parametrize("key", ["data", "character_name"])
def test_duplicate_fields_rejected_in_otherwise_valid_snapshot(key):
    from wingman.wanderer.model import SnapshotError, parse_snapshot

    body = json.dumps(candidate()).encode()
    marker = f'"{key}":'.encode()
    body = body.replace(marker, marker + b' "SENSITIVE_SENTINEL", ' + marker, 1)
    with pytest.raises(SnapshotError) as caught:
        parse_snapshot(body, 100)
    assert caught.value.__context__ is None


def test_record_count_and_encoded_body_bounds():
    from wingman.wanderer.model import SnapshotError, parse_snapshot

    data = candidate()
    base = copy.deepcopy(data["data"][3])
    data["data"] = [
        dict(base, character_id=i + 1, character_name=f"Pilot {i}") for i in range(2000)
    ]
    assert len(parse(data).records) == 2000
    data["data"].append(dict(base, character_id=2001, character_name="One Too Many"))
    with pytest.raises(SnapshotError):
        parse(data)
    empty = b'{"data":[],"observed_at":"2026-09-10T20:00:00Z","revision":"empty"}'
    assert parse_snapshot(empty.ljust(1048576), 100).records == ()
    with pytest.raises(SnapshotError):
        parse_snapshot(empty.ljust(1048577), 100)


@pytest.mark.parametrize(
    "receipt", [math.nan, math.inf, -math.inf, True, "100", 10**1000]
)
def test_receipt_cannot_create_immortal_or_invalid_deadlines(receipt):
    from wingman.wanderer.model import SnapshotError

    with pytest.raises(SnapshotError):
        parse(receipt=receipt)


@pytest.mark.parametrize(
    "value,want",
    [
        ("https://Example.COM/", "https://example.com"),
        (
            " HTTPS://Example.COM:443/Wanderer/nested/ ",
            "https://example.com/Wanderer/nested",
        ),
        ("https://example.com:8443/prefix", "https://example.com:8443/prefix"),
        ("https://[2001:0db8::1]:443/prefix", "https://[2001:db8::1]/prefix"),
        ("https://127.0.0.1/wingman", "https://127.0.0.1/wingman"),
    ],
)
def test_https_normalization_preserves_application_prefix(value, want):
    from wingman.wanderer.model import normalize_base_url

    assert normalize_base_url(value) == want
    assert normalize_base_url(want) == want


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "http://example.com",
        "ftp://example.com",
        "//example.com",
        "https://user:SENSITIVE_SENTINEL@example.com",
        "https://example.com?token=SENSITIVE_SENTINEL",
        "https://example.com/#",
        "https://example.com?",
        "https://example.com/\\evil",
        "https://example.com/../evil",
        "https://example.com/%2e%2e/evil",
        "https://example.com/%2f/evil",
        "https://example.com//evil",
        "https://example.com/\r\nSENSITIVE_SENTINEL",
        "https://example.com:\n443",
        "https://example.com:0",
        "https://example.com:65536",
        "https://example.com:",
        "https://[v1.example]/",
        "https://[::1]evil/",
        "https://127.1",
        "https://0x7f000001",
        "https://example.com/" + "x" * 2048,
    ],
)
def test_url_security_and_safe_errors(value):
    from wingman.wanderer.model import normalize_base_url

    with pytest.raises(ValueError) as caught:
        normalize_base_url(value)
    assert "SENSITIVE_SENTINEL" not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__context__ is None


@pytest.mark.parametrize(
    "value,want",
    [
        (" My-Map ", "My-Map"),
        (
            "AABBCCDD-1234-5678-9ABC-123456789ABC",
            "aabbccdd-1234-5678-9abc-123456789abc",
        ),
        ("x" * 255, "x" * 255),
    ],
)
def test_map_identifier_is_one_bounded_selector_preserving_slug_case(value, want):
    from wingman.wanderer.model import normalize_map_identifier

    assert normalize_map_identifier(value) == want


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "  ",
        ".",
        "..",
        "map/name",
        "map\\name",
        "%2F",
        "map?token",
        "map#fragment",
        "bad\nmap",
        "x" * 256,
    ],
)
def test_invalid_map_identifier(value):
    from wingman.wanderer.model import normalize_map_identifier

    with pytest.raises(ValueError):
        normalize_map_identifier(value)


def test_package_is_in_explicit_distribution_list():
    project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    assert "wingman.wanderer" in project["tool"]["setuptools"]["packages"]
