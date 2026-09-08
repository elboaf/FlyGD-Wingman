"""Origin-bound migration and bounded intent journals; no second state writer."""

import base64
import json
from dataclasses import replace
from uuid import UUID as UUIDValue

import pytest
from test_fleetsharing_config import BRACKETED_INVALID_ORIGINS
from test_fleetsharing_crypto import INVALID_RECOVERY_SPKI_CASES, invalid_recovery_spki
from test_fleetsharing_protocol import CHALLENGE, DATE, TOKEN, UUID

from wingman.fleetsharing import crypto
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing import state as s


def paired():
    return s.SharingState(
        identity=s.DeviceIdentity(
            "cHJvdGVjdGVk",
            crypto.canonical_device_public_key_b64(
                crypto.public_key_spki(crypto.generate_private_key())
            ),
        ),
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
            TOKEN, DATE, p.parse_recovery_challenge(CHALLENGE)
        ),
        pending_source_commands=(p.StartSource(UUID, 42, UUID, DATE),),
    )


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("case", INVALID_RECOVERY_SPKI_CASES)
def test_malformed_persisted_public_key_cannot_escape_state_loader(
    tmp_path, version, case
):
    path = tmp_path / "state.json"
    original = paired()
    s.save(path, original)
    data = json.loads(path.read_text())
    if version == 1:
        data = {
            key: data[key]
            for key in ("identity", "relay_origin", "session_id", "last_revision")
        }
    data["version"] = version
    data["identity"]["public_key_spki_b64"] = base64.b64encode(
        invalid_recovery_spki(case)
    ).decode()
    path.write_text(json.dumps(data))
    loaded = s.load(path)
    if version == 1:
        assert loaded == replace(original, identity=None)
    else:
        assert loaded == s.EMPTY


@pytest.mark.parametrize("version", [1, 2])
def test_valid_persisted_der_alias_preserves_the_canonical_identity(tmp_path, version):
    path = tmp_path / "state.json"
    original = paired()
    s.save(path, original)
    data = json.loads(path.read_text())
    if version == 1:
        data = {
            key: data[key]
            for key in ("identity", "relay_origin", "session_id", "last_revision")
        }
    data["version"] = version
    canonical = base64.b64decode(original.identity.public_key_spki_b64)
    data["identity"]["public_key_spki_b64"] = base64.b64encode(
        canonical + b"\x00" * 46
    ).decode()
    path.write_text(json.dumps(data))
    assert s.load(path) == original


def test_v2_roundtrip_preserves_all_bindings_without_remote_payloads(tmp_path):
    path = tmp_path / "state.json"
    state = journaled()
    s.save(path, state)
    assert s.load(path) == state
    raw = json.loads(path.read_text())
    assert raw["version"] == 2
    assert raw["pending_source_commands"] == [
        {
            "operation": "start",
            "source_id": UUID,
            "expected_generation": 0,
            "character_id": 42,
            "character_link_epoch": UUID,
            "intent_created_at": DATE,
        }
    ]
    assert raw["pending_recovery"]["issued_at"] == DATE
    assert (
        "catalogue" not in raw
        and "rows" not in raw
        and "participation_enabled" not in raw
    )


def test_v1_migration_preserves_registered_key_origin_and_opaque_session(tmp_path):
    path = tmp_path / "state.json"
    old = paired()
    data = {
        "version": 1,
        "identity": vars(old.identity),
        "relay_origin": "HTTPS://Relay.Example.test:443/",
        "session_id": "opaque-session-id",
        "last_revision": 429,
    }
    path.write_text(json.dumps(data))
    result = s.load(path)
    assert result.identity == old.identity
    assert result.relay_origin == "https://relay.example.test"
    assert result.session_id == "opaque-session-id" and result.last_revision == 429
    assert result.device_id is None and result.session_expires_at is None
    assert (
        result.approved_capabilities is None and result.observed_participation is None
    )
    s.save(path, result)
    assert json.loads(path.read_text())["version"] == 2


@pytest.mark.parametrize("version", [None, True, 1.0, 0, 3, "2"])
def test_unknown_or_malformed_state_version_is_not_guessed(tmp_path, version):
    path = tmp_path / "state.json"
    state = paired()
    path.write_text(
        json.dumps(
            {
                "version": version,
                "identity": vars(state.identity),
                "relay_origin": state.relay_origin,
                "session_id": TOKEN,
            }
        )
    )
    assert s.load(path) == s.EMPTY


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("session_id", "bad\nsecret"),
        ("last_revision", True),
        ("last_revision", 2147483648),
        ("session_expires_at", "2026-02-30T12:00:00.000Z"),
        ("acknowledged_capabilities", ["unknown"]),
    ],
)
def test_unusable_session_retains_origin_key_and_journal_for_explicit_recovery(
    tmp_path, key, value
):
    path = tmp_path / "state.json"
    original = journaled()
    s.save(path, original)
    raw = json.loads(path.read_text())
    raw[key] = value
    path.write_text(json.dumps(raw))
    loaded = s.load(path)
    assert (
        loaded.identity == original.identity
        and loaded.relay_origin == original.relay_origin
    )
    assert loaded.session_id is None and loaded.last_revision == 0
    assert (
        loaded.session_expires_at is None and loaded.acknowledged_capabilities is None
    )
    assert loaded.pending_recovery == original.pending_recovery
    assert loaded.pending_source_commands == original.pending_source_commands
    assert loaded.observed_participation == original.observed_participation


def test_session_replacement_clears_only_session_metadata_and_revision():
    original = journaled()
    replacement = s.replace_session(original, "A" * 43, expires_at=DATE)
    assert replacement == replace(
        original,
        session_id="A" * 43,
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
    original = paired()
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "identity": vars(original.identity),
                "relay_origin": origin,
                "session_id": TOKEN,
            }
        )
    )
    assert s.load(path) == s.EMPTY


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize("origin", BRACKETED_INVALID_ORIGINS)
def test_bracketed_authority_corruption_cannot_redirect_loaded_identity(
    tmp_path, version, origin
):
    path = tmp_path / "state.json"
    s.save(path, paired())
    data = json.loads(path.read_text())
    if version == 1:
        data = {
            key: data[key]
            for key in ("identity", "relay_origin", "session_id", "last_revision")
        }
    data.update(version=version, relay_origin=origin)
    path.write_text(json.dumps(data))
    before = path.read_bytes()
    assert s.load(path) == s.EMPTY
    assert path.read_bytes() == before  # Loading must not persist a rewritten host.


@pytest.mark.parametrize("version", [1, 2])
def test_valid_ipv6_state_origin_normalizes_without_losing_identity(tmp_path, version):
    path = tmp_path / "state.json"
    original = paired()
    s.save(path, original)
    data = json.loads(path.read_text())
    if version == 1:
        data = {
            key: data[key]
            for key in ("identity", "relay_origin", "session_id", "last_revision")
        }
    data.update(version=version, relay_origin="HTTPS://[2001:0DB8:0:0:0:0:0:1]:443/")
    path.write_text(json.dumps(data))
    assert s.load(path) == replace(original, relay_origin="https://[2001:db8::1]")


def test_recovery_request_and_challenge_survive_crash_boundaries(tmp_path):
    path = tmp_path / "state.json"
    original = replace(
        paired(),
        session_id=None,
        last_revision=0,
        pending_recovery=s.PendingRecovery(TOKEN, DATE),
    )
    s.save(path, original)  # BEFORE begin_recovery, whose response may be lost
    assert s.load(path).pending_recovery == s.PendingRecovery(TOKEN, DATE)
    with_challenge = replace(
        original,
        pending_recovery=s.PendingRecovery(
            TOKEN, DATE, p.parse_recovery_challenge(CHALLENGE)
        ),
    )
    s.save(path, with_challenge)  # BEFORE complete_recovery, which is one-use
    assert s.load(path).pending_recovery == with_challenge.pending_recovery
    # Merely loading an expired binding does not mint a new ID or extend consent.
    assert s.load(path).pending_recovery.issued_at == DATE


@pytest.mark.parametrize(
    "bad",
    [
        {
            "request_id": TOKEN,
            "issued_at": DATE,
            "challenge": {
                **{k: v for k, v in CHALLENGE.items() if k != "protocol"},
                "request_id": "A" * 43,
            },
        },
        {"request_id": "B" * 43, "issued_at": DATE, "challenge": None},
        {"request_id": TOKEN, "issued_at": "bad", "challenge": None},
    ],
)
def test_corrupt_recovery_journal_is_not_silently_replaced_or_dropped(tmp_path, bad):
    path = tmp_path / "state.json"
    s.save(path, journaled())
    raw = json.loads(path.read_text())
    raw["pending_recovery"] = bad
    path.write_text(json.dumps(raw))
    assert s.load(path) == s.EMPTY


@pytest.mark.parametrize("kind", ["count", "bytes", "duplicate", "unknown"])
def test_save_refuses_overflow_and_invalid_commands_before_replace(tmp_path, kind):
    path = tmp_path / "state.json"
    original = paired()
    s.save(path, original)
    before = path.read_bytes()
    commands = tuple(
        p.StopSource(str(UUIDValue(int=i + 1, version=4)), 0) for i in range(257)
    )
    if kind == "count":
        bad = replace(original, pending_source_commands=commands)
    elif kind == "duplicate":
        bad = replace(original, pending_source_commands=(commands[0], commands[0]))
    elif kind == "unknown":
        bad = replace(
            original,
            pending_source_commands=(p.RemoteRow(42, "Alice", 1, (), "live", 1),),
        )
    else:
        # 256 Start commands fit the count cap but exceed 64KiB including identity.
        bad = replace(
            original,
            pending_source_commands=tuple(
                p.StartSource(c.source_id, 9007199254740991, UUID, DATE)
                for c in commands[:256]
            ),
        )
    with pytest.raises(ValueError):
        s.save(path, bad)
    assert path.read_bytes() == before and s.load(path) == original


def test_stop_journal_fits_at_exact_count_limit_and_is_not_rewritten(tmp_path):
    path = tmp_path / "state.json"
    commands = tuple(
        p.StopSource(str(UUIDValue(int=i + 1, version=4)), 0) for i in range(256)
    )
    state = replace(paired(), pending_source_commands=commands)
    s.save(path, state)
    assert s.load(path).pending_source_commands == commands


def test_duplicate_json_and_unknown_durable_payload_fail_closed(tmp_path):
    path = tmp_path / "state.json"
    s.save(path, paired())
    raw = path.read_text()
    path.write_text(raw.replace('"version": 2', '"version": 2, "version": 2'))
    assert s.load(path) == s.EMPTY
    s.save(path, paired())
    data = json.loads(path.read_text())
    data["rows"] = [{"character_name": "remote"}]
    path.write_text(json.dumps(data))
    assert s.load(path) == s.EMPTY


@pytest.mark.parametrize("unprotected", [b"short", b"x" * 33, "x" * 32, None])
def test_corrupt_dpapi_plaintext_never_becomes_a_private_key(unprotected):
    assert (
        s.unwrap_private_key(
            base64.b64encode(b"cipher").decode(), unprotect=lambda _: unprotected
        )
        is None
    )
