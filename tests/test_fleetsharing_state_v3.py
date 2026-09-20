"""Legacy V3 journals remain evidence, never current permission defaults."""

import json
from dataclasses import replace

import pytest
from test_fleetsharing_state_v2 import journaled

from tests.fleetsharing_state4_helpers import DATE, UUID, legacy, put
from wingman.fleetsharing import state as s


def test_exact_task6_document_migrates_to_archive_without_writing(tmp_path):
    path = tmp_path / "state.json"
    raw = legacy(2)
    before = put(path, raw)
    loaded = s.load(path)
    assert loaded.cutover.original == raw
    assert loaded.pending_source_commands == ()
    assert loaded.pending_recovery is None
    assert loaded.pending_pairing is None and loaded.pending_participation is None
    assert path.read_bytes() == before
    s.save(path, loaded)
    assert json.loads(path.read_bytes())["version"] == 4


def test_new_journals_roundtrip_and_do_not_grant_authority(tmp_path):
    path = tmp_path / "state.json"
    original = replace(
        journaled(),
        pending_pairing=s.PendingPairing(
            "upgrade",
            UUID,
            "https://relay.example.test/approve",
            DATE,
            True,
            ("shared-source-v1", "combat-v2"),
        ),
        pending_participation=s.PendingParticipation(UUID, False, 7, True),
        auth_pause=s.AuthPause("account_ineligible", DATE),
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
def test_malformed_legacy_v3_journals_fail_closed(tmp_path, field, value):
    path = tmp_path / "state.json"
    raw = legacy(3)
    raw[field] = value
    before = put(path, raw)
    with pytest.raises(s.QuarantineError):
        s.load(path)
    assert path.read_bytes() == before


def test_pairing_url_must_stay_bound_to_identity_origin_before_save(tmp_path):
    path = tmp_path / "state.json"
    original = journaled()
    s.save(path, original)
    before = path.read_bytes()
    bad = replace(
        original,
        pending_pairing=s.PendingPairing(
            "upgrade", UUID, "https://evil.test/approve", DATE
        ),
    )
    with pytest.raises(ValueError):
        s.save(path, bad)
    assert path.read_bytes() == before
