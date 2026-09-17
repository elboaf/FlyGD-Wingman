"""Real-load migration, evidence ownership and explicit quarantine outcomes."""

import base64
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from tests.fleetsharing_state4_helpers import (
    IDENTITY,
    ORIGIN,
    REQUEST,
    UUID,
    active,
    legacy,
    put,
)
from wingman.fleetsharing import state as s


@pytest.mark.parametrize("version", [1, 2, 3])
def test_literal_migration_archives_exact_values_without_write_or_replay(
    tmp_path, version
):
    path = tmp_path / "state.json"
    raw = legacy(version)
    before = put(path, raw)
    loaded = s.load(path)
    assert loaded.session_id is None and loaded.last_revision == 0
    assert loaded.identity.public_key_spki_b64 == IDENTITY["public_key_spki_b64"]
    assert loaded.relay_origin == ORIGIN
    assert loaded.pending_source_commands == () and loaded.pending_recovery is None
    assert loaded.pending_pairing is None and loaded.pending_participation is None
    assert loaded.observed_participation is None and loaded.feature_enabled is None
    assert loaded.session_expires_at is None
    assert loaded.session_approved_capabilities is None
    assert loaded.acknowledged_capabilities is None
    assert loaded.cutover is not None
    assert loaded.cutover.original == raw
    selectors = ["session"]
    if version == 3:
        selectors += ["pairing", "recovery", "participation"]
    elif version == 2:
        selectors += ["recovery"]
    if version >= 2:
        selectors += ["source:" + UUID.lower(), "source:" + REQUEST]
        assert loaded.device_id == UUID
        assert loaded.approved_capabilities == ("shared-source-v1",)
    else:
        assert loaded.device_id is None and loaded.approved_capabilities is None
    assert [(v.selector, v.status) for v in loaded.cutover.outcomes] == [
        (v, "fenced") for v in selectors
    ]
    assert loaded.automatic == s.AutomaticState()
    assert loaded.auth_pause == (
        s.AuthPause("account_ineligible", raw["auth_pause"]["retry_not_before"])
        if version == 3
        else None
    )
    assert path.read_bytes() == before
    s.save(path, loaded)
    assert json.loads(path.read_bytes())["cutover"]["original"] == raw
    assert s.load(path) == loaded
    assert json.loads(path.read_bytes())["version"] == 4


@pytest.mark.parametrize(
    "raw",
    [
        {"version": 1},
        {"version": 1, "identity": None, "session_id": None},
        {"version": 1, "session_id": None, "last_revision": 0},
    ],
)
def test_v1_absence_null_and_no_session_evidence_preserved(tmp_path, raw):
    path = tmp_path / "state.json"
    put(path, raw)
    loaded = s.load(path)
    assert getattr(loaded, "cutover", None) is not None
    assert loaded.cutover.original == raw and loaded.cutover.outcomes == ()


@pytest.mark.parametrize(
    "key,value",
    [
        ("last_revision", True),
        ("last_revision", 0.0),
        ("last_revision", None),
        ("last_revision", -1),
        ("last_revision", 2147483648),
        ("session_id", "bad\nsecret"),
        ("session_id", "\ud800"),
        ("session_expires_at", "bad-date"),
        ("acknowledged_capabilities", ["unknown"]),
        ("session_approved_capabilities", {"invalid": [1, True, None]}),
    ],
)
def test_only_legacy_session_metadata_is_salvaged_as_unchanged_evidence(
    tmp_path, key, value
):
    path = tmp_path / "state.json"
    raw = legacy()
    raw.update(
        session_id=None,
        last_revision=0,
        session_expires_at=None,
        acknowledged_capabilities=None,
        session_approved_capabilities=None,
    )
    raw[key] = value
    before = put(path, raw)
    loaded = s.load(path)
    assert loaded.pending_source_commands == ()
    assert loaded.cutover.original == raw
    assert type(loaded.cutover.original[key]) is type(value)
    assert loaded.cutover.outcomes[0].selector == "session"
    assert path.read_bytes() == before
    s.save(path, loaded)
    assert s.load(path).cutover.original == raw


@pytest.mark.parametrize("version", [1, 2, 3])
@pytest.mark.parametrize(
    "field,value",
    [
        ("identity", {"protected_private_key_b64": "onlyhalf"}),
        ("relay_origin", "https://user@evil.test"),
        ("unknown", None),
    ],
)
def test_invalid_non_session_legacy_fields_quarantine_without_write(
    tmp_path, version, field, value
):
    path = tmp_path / "state.json"
    raw = legacy(version)
    raw[field] = value
    before = put(path, raw)
    with pytest.raises(ValueError):
        s.load(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("device_id", "bad"),
        ("feature_enabled", 1),
        ("approved_capabilities", ["shared-source-v1", "combat-v2"]),
        ("observed_participation", {"enabled": True, "generation": True}),
        (
            "pending_source_commands",
            [
                {
                    "operation": "stop",
                    "source_id": UUID,
                    "expected_generation": 6,
                    "request_id": REQUEST,
                }
            ],
        ),
        (
            "pending_recovery",
            {"request_id": "A" * 43, "issued_at": "bad", "challenge": None},
        ),
        ("pending_pairing", {"mode": "initial"}),
        ("auth_pause", {"result": "unauthorized", "retry_not_before": None}),
    ],
)
def test_malformed_legacy_journals_and_observations_are_not_salvaged(
    tmp_path, field, value
):
    path = tmp_path / "state.json"
    raw = legacy()
    raw[field] = value
    before = put(path, raw)
    with pytest.raises(ValueError):
        s.load(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "data",
    [
        b"{",
        b"[]",
        b'{"version":3,"version":3}',
        b'{"version":5}',
        b'{"version":true}',
        b'{"version":1.0}',
        b'{"version":1,"last_revision":NaN}',
        b"\xff",
    ],
)
def test_bad_files_quarantine_not_empty(tmp_path, data):
    path = tmp_path / "state.json"
    path.write_bytes(data)
    with pytest.raises(ValueError):
        s.load(path)
    assert path.read_bytes() == data


def test_absence_and_io_failure_are_distinct(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    assert s.load(path) == s.EMPTY
    put(path, legacy())

    def denied(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "open", denied)
    with pytest.raises(PermissionError):
        s.load(path)


def test_raw_legacy_bound_does_not_borrow_v4_space(tmp_path):
    path = tmp_path / "state.json"
    path.write_bytes(b'{"version":1}' + b" " * 65536)
    with pytest.raises(ValueError):
        s.load(path)
    assert path.stat().st_size > 65536


def test_archive_is_deeply_detached_and_never_unwraps_key(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    raw = legacy()
    put(path, raw)

    def forbidden(*args, **kwargs):
        raise AssertionError("DPAPI must not run")

    monkeypatch.setattr(s.dpapi, "unprotect", forbidden)
    monkeypatch.setattr(s, "unwrap_private_key", forbidden)
    loaded = s.load(path)
    assert loaded.pending_source_commands == ()
    detached = loaded.cutover.original
    detached["identity"]["protected_private_key_b64"] = "changed"
    detached["pending_source_commands"].clear()
    assert loaded.cutover.original == raw
    with pytest.raises(FrozenInstanceError):
        loaded.cutover.outcomes = ()
    s.save(path, loaded)
    assert s.load(path).cutover.original == raw


def test_canonical_alias_binding_does_not_rewrite_original(tmp_path):
    path = tmp_path / "state.json"
    raw = legacy(1)
    raw["identity"]["public_key_spki_b64"] = base64.b64encode(
        base64.b64decode(IDENTITY["public_key_spki_b64"]) + b"\0" * 46
    ).decode()
    put(path, raw)
    loaded = s.load(path)
    assert loaded.session_id is None
    assert loaded.identity.public_key_spki_b64 == IDENTITY["public_key_spki_b64"]
    assert loaded.cutover.original == raw
    s.save(path, loaded)
    for candidate in [
        replace(loaded, relay_origin="https://other.test"),
        replace(
            loaded, identity=replace(loaded.identity, protected_private_key_b64="eA==")
        ),
    ]:
        before = path.read_bytes()
        with pytest.raises(ValueError):
            s.save(path, candidate)
        assert path.read_bytes() == before


@pytest.mark.parametrize(
    "url,valid",
    [
        (ORIGIN + "/\U00010000", True),
        (
            ORIGIN + "/\U0001fae8",
            False,
        ),  # Unicode 15 assignment was Cn in the legacy host.
        ("/relative", False),
        ("https://user@relay.example.test/x", False),
        (ORIGIN + "/a b", False),
        (ORIGIN + "/\\evil", False),
    ],
)
def test_legacy_pairing_retains_historical_text_and_absolute_origin_rules(
    tmp_path, url, valid
):
    path = tmp_path / "state.json"
    raw = legacy()
    raw["pending_pairing"]["approval_url"] = url
    put(path, raw)
    if valid:
        loaded = s.load(path)
        assert loaded.pending_pairing is None
        assert loaded.cutover.original == raw
    else:
        with pytest.raises(ValueError):
            s.load(path)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "duplicate",
        "order",
        "extra",
        "stop_expired",
        "wrong_kind",
        "nested",
        "binding",
    ],
)
def test_v4_archive_requires_exact_selector_coverage_and_allowed_outcomes(
    tmp_path, mutation
):
    path = tmp_path / "state.json"
    raw = active()
    raw["cutover"] = {
        "original": legacy(),
        "outcomes": [
            {"selector": selector, "status": "fenced"}
            for selector in [
                "session",
                "pairing",
                "recovery",
                "participation",
                "source:" + UUID.lower(),
                "source:" + REQUEST,
            ]
        ],
    }
    if mutation == "missing":
        raw["cutover"]["outcomes"].pop()
    elif mutation == "duplicate":
        raw["cutover"]["outcomes"][1] = raw["cutover"]["outcomes"][0]
    elif mutation == "order":
        raw["cutover"]["outcomes"].reverse()
    elif mutation == "extra":
        raw["cutover"]["outcomes"].append({"selector": "renewal", "status": "fenced"})
    elif mutation == "stop_expired":
        raw["cutover"]["outcomes"][-1]["status"] = "expired_unproven"
    elif mutation == "wrong_kind":
        raw["cutover"]["outcomes"][-1]["status"] = "recovered_identity"
    elif mutation == "nested":
        raw["cutover"]["original"] = active()
    else:
        raw["cutover"]["original"]["relay_origin"] = "https://other.test"
    before = put(path, raw)
    with pytest.raises(ValueError):
        s.load(path)
    assert path.read_bytes() == before
