"""Legacy origin/key validation and current bounded intent journals.

Literal legacy documents deliberately do not depend on the old worker's DTOs or
on saving state4 and removing fields. Worker migration failures remain separate.
"""

import base64
import json
from dataclasses import replace
from uuid import UUID as UUIDValue

import pytest
from test_fleetsharing_config import BRACKETED_INVALID_ORIGINS
from test_fleetsharing_crypto import INVALID_RECOVERY_SPKI_CASES, invalid_recovery_spki

from tests.fleetsharing_state4_helpers import (
    DATE,
    IDENTITY,
    TOKEN,
    UUID,
    active,
    legacy,
    put,
)
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing import state as s


def paired():
    return s.SharingState(
        identity=s.DeviceIdentity(**IDENTITY),
        relay_origin="https://relay.example.test",
        session_id=TOKEN,
        last_revision=7,
    )


def journaled():
    return replace(
        paired(),
        device_id=UUID,
        session_expires_at=DATE,
        feature_enabled=False,
        approved_capabilities=(),
        session_approved_capabilities=("shared-source-v1",),
        acknowledged_capabilities=("shared-source-v1",),
        observed_participation=p.Participation(False, 3),
        pending_recovery=s.PendingRecovery(
            TOKEN, DATE, p.RecoveryChallenge(UUID, TOKEN, TOKEN, DATE)
        ),
        pending_source_commands=(p.SourceStart(UUID, 42, UUID, DATE),),
    )


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("case", INVALID_RECOVERY_SPKI_CASES)
def test_malformed_persisted_public_key_cannot_escape_state_loader(
    tmp_path, version, case
):
    path = tmp_path / "state.json"
    data = legacy(version)
    data["identity"]["public_key_spki_b64"] = base64.b64encode(
        invalid_recovery_spki(case)
    ).decode()
    before = put(path, data)
    with pytest.raises(s.QuarantineError):
        s.load(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("version", [1, 2])
def test_valid_persisted_der_alias_preserves_canonical_identity_and_original(
    tmp_path, version
):
    path = tmp_path / "state.json"
    data = legacy(version)
    canonical = base64.b64decode(IDENTITY["public_key_spki_b64"])
    data["identity"]["public_key_spki_b64"] = base64.b64encode(
        canonical + b"\x00" * 46
    ).decode()
    put(path, data)
    loaded = s.load(path)
    assert loaded.identity == paired().identity
    assert loaded.cutover.original == data
    assert loaded.session_id is None


def test_roundtrip_preserves_active_bindings_without_remote_payloads(tmp_path):
    path = tmp_path / "state.json"
    state = journaled()
    s.save(path, state)
    assert s.load(path) == state
    raw = json.loads(path.read_bytes())
    assert raw["version"] == 4
    assert raw["pending_source_commands"] == [
        {
            "protocol": 2,
            "operation": "start",
            "source_id": UUID,
            "expected_generation": 0,
            "character_id": 42,
            "character_link_epoch": UUID,
            "intent_created_at": DATE,
        }
    ]
    assert raw["pending_recovery"]["issued_at"] == DATE
    assert raw["pending_recovery"]["completion_attempted"] is False
    assert not {"catalogue", "rows", "participation_enabled"} & set(raw)


def test_v1_migration_retires_opaque_session_but_keeps_exact_original(tmp_path):
    path = tmp_path / "state.json"
    data = legacy(1)
    data.update(session_id="opaque-session-id", last_revision=429)
    before = put(path, data)
    result = s.load(path)
    assert result.identity == paired().identity
    assert result.relay_origin == "https://relay.example.test"
    assert result.session_id is None and result.last_revision == 0
    assert result.device_id is None and result.session_expires_at is None
    assert (
        result.approved_capabilities is None and result.observed_participation is None
    )
    assert result.cutover.original == data
    assert path.read_bytes() == before
    s.save(path, result)
    assert json.loads(path.read_bytes())["version"] == 4


@pytest.mark.parametrize("version", [None, True, 1.0, 0, 5, "2"])
def test_unknown_or_malformed_state_version_is_not_guessed(tmp_path, version):
    path = tmp_path / "state.json"
    data = legacy(1)
    data["version"] = version
    put(path, data)
    with pytest.raises(s.QuarantineError):
        s.load(path)


@pytest.mark.parametrize(
    "key,value",
    [
        ("session_id", "bad\nsecret"),
        ("last_revision", True),
        ("last_revision", 2147483648),
        ("session_expires_at", "2026-02-30T12:00:00.000Z"),
        ("acknowledged_capabilities", ["unknown"]),
    ],
)
def test_unusable_legacy_session_retains_origin_key_and_archived_journals(
    tmp_path, key, value
):
    path = tmp_path / "state.json"
    raw = legacy(2)
    raw[key] = value
    put(path, raw)
    loaded = s.load(path)
    assert (
        loaded.identity == paired().identity
        and loaded.relay_origin == paired().relay_origin
    )
    assert loaded.session_id is None and loaded.last_revision == 0
    assert (
        loaded.session_expires_at is None and loaded.acknowledged_capabilities is None
    )
    assert loaded.pending_recovery is None and loaded.pending_source_commands == ()
    assert loaded.observed_participation is None
    assert loaded.cutover.original == raw


def test_session_replacement_clears_only_session_metadata_and_revision():
    original = journaled()
    replacement = s.replace_session(original, TOKEN, expires_at=DATE)
    assert replacement == replace(
        original,
        session_id=TOKEN,
        session_expires_at=DATE,
        last_revision=0,
        session_approved_capabilities=None,
        acknowledged_capabilities=None,
    )
    assert s.replace_session(original, None) == replace(
        original,
        session_id=None,
        session_expires_at=None,
        last_revision=0,
        session_approved_capabilities=None,
        acknowledged_capabilities=None,
    )


@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.test/path",
        "https://user@evil.test",
        "https://relay.test\\evil",
        None,
    ],
)
def test_corrupt_origin_cannot_leave_credentials_available_for_default_origin(
    tmp_path, origin
):
    path = tmp_path / "state.json"
    data = legacy(1)
    data["relay_origin"] = origin
    put(path, data)
    with pytest.raises(s.QuarantineError):
        s.load(path)


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("origin", BRACKETED_INVALID_ORIGINS)
def test_bracketed_authority_corruption_cannot_redirect_loaded_identity(
    tmp_path, version, origin
):
    path = tmp_path / "state.json"
    data = legacy(version)
    data["relay_origin"] = origin
    before = put(path, data)
    with pytest.raises(s.QuarantineError):
        s.load(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("version", [1, 2])
def test_valid_ipv6_state_origin_normalizes_without_losing_identity(tmp_path, version):
    path = tmp_path / "state.json"
    data = legacy(version)
    data["relay_origin"] = "HTTPS://[2001:0DB8:0:0:0:0:0:1]:443/"
    put(path, data)
    result = s.load(path)
    assert result.identity == paired().identity
    assert result.relay_origin == "https://[2001:db8::1]"
    assert result.cutover.original == data


def test_recovery_request_and_challenge_survive_crash_boundaries(tmp_path):
    path = tmp_path / "state.json"
    original = replace(
        paired(),
        session_id=None,
        last_revision=0,
        pending_recovery=s.PendingRecovery(TOKEN, DATE),
    )
    s.save(path, original)
    assert s.load(path).pending_recovery == s.PendingRecovery(TOKEN, DATE)
    with_challenge = replace(
        original,
        pending_recovery=s.PendingRecovery(
            TOKEN, DATE, p.RecoveryChallenge(UUID, TOKEN, TOKEN, DATE)
        ),
    )
    s.save(path, with_challenge)
    assert s.load(path).pending_recovery == with_challenge.pending_recovery
    assert s.load(path).pending_recovery.issued_at == DATE


@pytest.mark.parametrize("mutation", ["mismatch", "token", "date"])
def test_corrupt_recovery_journal_is_not_silently_replaced_or_dropped(
    tmp_path, mutation
):
    path = tmp_path / "state.json"
    raw = legacy(2)
    if mutation == "mismatch":
        raw["pending_recovery"]["challenge"]["request_id"] = "_" * 42 + "8"
    elif mutation == "token":
        raw["pending_recovery"]["request_id"] = "B" * 43
    else:
        raw["pending_recovery"]["issued_at"] = "bad"
    put(path, raw)
    with pytest.raises(s.QuarantineError):
        s.load(path)


@pytest.mark.parametrize("kind", ["count", "bytes", "duplicate", "unknown"])
def test_save_refuses_overflow_and_invalid_commands_before_replace(
    tmp_path, monkeypatch, kind
):
    path = tmp_path / "state.json"
    original = paired()
    s.save(path, original)
    before = path.read_bytes()
    commands = tuple(
        p.SourceStop(
            str(UUIDValue(int=i + 1, version=4)),
            0,
            str(UUIDValue(int=i + 1, version=4)),
            DATE,
            None,
        )
        for i in range(257)
    )
    if kind == "count":
        bad = replace(original, pending_source_commands=commands)
    elif kind == "duplicate":
        bad = replace(original, pending_source_commands=(commands[0], commands[0]))
    elif kind == "unknown":
        bad = replace(original, pending_source_commands=(object(),))
    else:
        bad = original
        monkeypatch.setattr(s, "MAX_STATE_FILE_BYTES", len(before) - 1)
    with pytest.raises(ValueError):
        s.save(path, bad)
    assert path.read_bytes() == before
    monkeypatch.undo()
    assert s.load(path) == original


def test_stop_journal_fits_at_exact_count_limit_and_is_not_rewritten(tmp_path):
    path = tmp_path / "state.json"
    commands = tuple(
        p.SourceStop(
            str(UUIDValue(int=i + 1, version=4)),
            0,
            str(UUIDValue(int=i + 1, version=4)),
            DATE,
            None,
        )
        for i in range(256)
    )
    state = replace(paired(), pending_source_commands=commands)
    s.save(path, state)
    assert s.load(path).pending_source_commands == commands


def test_duplicate_json_and_unknown_durable_payload_fail_closed(tmp_path):
    path = tmp_path / "state.json"
    s.save(path, paired())
    path.write_bytes(
        path.read_bytes().replace(b'"version":4', b'"version":4,"version":4')
    )
    with pytest.raises(s.QuarantineError):
        s.load(path)
    data = active()
    data["rows"] = [{"character_name": "remote"}]
    put(path, data)
    with pytest.raises(s.QuarantineError):
        s.load(path)


@pytest.mark.parametrize("unprotected", [b"short", b"x" * 33, "x" * 32, None])
def test_corrupt_dpapi_plaintext_never_becomes_a_private_key(unprotected):
    assert (
        s.unwrap_private_key(
            base64.b64encode(b"cipher").decode(), unprotect=lambda _: unprotected
        )
        is None
    )
