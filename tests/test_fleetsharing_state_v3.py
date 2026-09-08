"""V3 adds journals, not permission defaults or a second preference writer."""

import json
from dataclasses import replace

import pytest
from test_fleetsharing_state_v2 import journaled

from wingman.fleetsharing import state as s

NEW_FIELDS = ("pending_pairing", "pending_participation", "auth_pause")


def test_exact_task6_document_survives_migration_without_writing(tmp_path):
    path = tmp_path / "state.json"
    original = journaled()
    s.save(path, original)
    raw = json.loads(path.read_text())
    for key in NEW_FIELDS:
        raw.pop(key, None)
    raw["version"] = 2
    path.write_text(json.dumps(raw))
    before = path.read_bytes()
    assert s.load(path) == original
    assert path.read_bytes() == before
    s.save(path, original)
    assert json.loads(path.read_text())["version"] == 3


def test_new_journals_roundtrip_and_do_not_grant_authority(tmp_path):
    path = tmp_path / "state.json"
    original = replace(
        journaled(),
        pending_pairing=s.PendingPairing(
            "upgrade",
            "pair-id",
            "https://relay.example.test/approve",
            "2026-09-07T12:02:00.000Z",
            True,
        ),
        pending_participation=s.PendingParticipation(
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", False, 7, True
        ),
        auth_pause=s.AuthPause("account_ineligible", "2026-09-07T12:01:00.000Z"),
    )
    s.save(path, original)
    assert s.load(path) == original
    assert original.feature_enabled is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("pending_pairing", {"mode": "initial"}),
        ("pending_participation", {"enabled": True}),
        ("auth_pause", {"result": "unauthorized", "retry_not_before": None}),
    ],
)
def test_malformed_new_journals_fail_closed(tmp_path, field, value):
    path = tmp_path / "state.json"
    s.save(path, journaled())
    raw = json.loads(path.read_text())
    raw[field] = value
    path.write_text(json.dumps(raw))
    assert s.load(path) == s.EMPTY


def test_pairing_url_must_stay_bound_to_identity_origin_before_save(tmp_path):
    path = tmp_path / "state.json"
    original = journaled()
    s.save(path, original)
    before = path.read_bytes()
    bad = replace(
        original,
        pending_pairing=s.PendingPairing(
            "upgrade",
            "pair-id",
            "https://evil.test/approve",
            "2026-09-07T12:02:00.000Z",
        ),
    )
    with pytest.raises(ValueError):
        s.save(path, bad)
    assert path.read_bytes() == before
