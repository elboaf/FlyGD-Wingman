"""Persistent fleet-sharing device identity and session state.

Pins the DPAPI seam and the persisted document's contents: `protect`/
`unprotect` receive only raw private-key bytes (never a `cryptography` key
object, never an already-encoded string), and the saved document holds
only the protected blob, public key, relay origin, and opaque session
id -- never an EVE token or an authGD browser session cookie, the same
posture `wingman.eveauth.tokens`/`state` hold for the EVE refresh token.
"""

import base64
import json
import stat
import sys

import pytest

from wingman.fleetsharing import crypto
from wingman.fleetsharing import state as state_mod
from wingman.fleetsharing.state import (
    DeviceIdentity,
    SharingState,
    load,
    save,
    unwrap_private_key,
    wrap_private_key,
)


def test_wrap_private_key_passes_only_the_raw_bytes_to_protect():
    calls = []

    def fake_protect(data):
        calls.append(data)
        return b"protected:" + data

    raw = crypto.generate_private_key()
    blob = wrap_private_key(raw, protect=fake_protect)

    assert calls == [raw]
    assert isinstance(calls[0], bytes) and len(calls[0]) == 32
    assert base64.b64decode(blob.encode("ascii")) == b"protected:" + raw


def test_unwrap_private_key_passes_only_the_decoded_blob_to_unprotect():
    calls = []

    def fake_unprotect(blob):
        calls.append(blob)
        return blob.removeprefix(b"protected:")

    raw = crypto.generate_private_key()
    blob = wrap_private_key(raw, protect=lambda data: b"protected:" + data)

    recovered = unwrap_private_key(blob, unprotect=fake_unprotect)

    assert recovered == raw
    assert calls == [b"protected:" + raw]


def test_unwrap_private_key_returns_none_for_an_empty_blob():
    assert unwrap_private_key("", unprotect=lambda blob: blob) is None


def test_unwrap_private_key_returns_none_for_malformed_base64_rather_than_raising():
    def unreachable(blob):
        raise AssertionError("unprotect must not be called for undecodable input")

    assert unwrap_private_key("not-valid-base64!!", unprotect=unreachable) is None


def test_unwrap_private_key_returns_none_when_unprotect_raises():
    def raising_unprotect(blob):
        raise OSError("bad blob")

    encoded = base64.b64encode(b"x").decode("ascii")
    assert unwrap_private_key(encoded, unprotect=raising_unprotect) is None


def test_save_and_load_round_trip(tmp_path):
    target = tmp_path / "fleet_sharing.json"
    original = SharingState(
        identity=DeviceIdentity(
            protected_private_key_b64="cHJvdGVjdGVk",
            public_key_spki_b64=crypto.canonical_device_public_key_b64(
                crypto.public_key_spki(crypto.generate_private_key())
            ),
        ),
        relay_origin="https://relay.example.test",
        session_id="opaque-session-id",
    )

    save(target, original)
    loaded = load(target)

    assert loaded == original


def test_persisted_document_holds_only_the_documented_fields(tmp_path):
    target = tmp_path / "fleet_sharing.json"
    original = SharingState(
        identity=DeviceIdentity(
            protected_private_key_b64="cHJvdGVjdGVk", public_key_spki_b64="c3BraQ=="
        ),
        relay_origin="https://relay.example.test",
        session_id="opaque-session-id",
        last_revision=7,
    )

    save(target, original)

    document = json.loads(target.read_text(encoding="utf-8"))
    assert set(document) == {
        "version",
        "identity",
        "relay_origin",
        "session_id",
        "last_revision",
    }
    assert document["last_revision"] == 7
    assert set(document["identity"]) == {
        "protected_private_key_b64",
        "public_key_spki_b64",
    }
    raw_text = target.read_text(encoding="utf-8")
    for forbidden in (
        "refresh_token",
        "access_token",
        "eve_token",
        "cookie",
        "character_id",
        "character_name",
    ):
        assert forbidden not in raw_text


def test_a_document_with_no_identity_yet_persists_null_fields(tmp_path):
    target = tmp_path / "fleet_sharing.json"
    save(target, SharingState())

    document = json.loads(target.read_text(encoding="utf-8"))
    assert document["identity"] is None
    assert document["relay_origin"] is None
    assert document["session_id"] is None
    assert document["last_revision"] == 0
    assert load(target) == SharingState()


def test_last_revision_round_trips(tmp_path):
    target = tmp_path / "fleet_sharing.json"
    save(target, SharingState(session_id="sess", last_revision=42))
    assert load(target).last_revision == 42


@pytest.mark.parametrize("malformed", [-1, "5", 5.0, True, None])
def test_load_coerces_a_malformed_last_revision_to_zero(tmp_path, malformed):
    target = tmp_path / "fleet_sharing.json"
    target.write_text(
        json.dumps(
            {
                "version": 1,
                "identity": None,
                "relay_origin": None,
                "session_id": "sess",
                "last_revision": malformed,
            }
        ),
        encoding="utf-8",
    )

    assert load(target).last_revision == 0


def test_load_defaults_last_revision_to_zero_when_the_field_is_absent(tmp_path):
    target = tmp_path / "fleet_sharing.json"
    target.write_text(
        json.dumps(
            {
                "version": 1,
                "identity": None,
                "relay_origin": None,
                "session_id": "sess",
            }
        ),
        encoding="utf-8",
    )

    assert load(target).last_revision == 0


def test_load_returns_empty_state_for_a_missing_file(tmp_path):
    assert load(tmp_path / "absent.json") == SharingState()


def test_load_returns_empty_state_for_corrupt_json(tmp_path):
    target = tmp_path / "fleet_sharing.json"
    target.write_text("{not json", encoding="utf-8")
    assert load(target) == SharingState()


def test_load_returns_empty_state_for_a_non_object_document(tmp_path):
    target = tmp_path / "fleet_sharing.json"
    target.write_text("[1, 2, 3]", encoding="utf-8")
    assert load(target) == SharingState()


def test_load_returns_empty_state_for_an_oversized_file(tmp_path, monkeypatch):
    target = tmp_path / "fleet_sharing.json"
    target.write_text(json.dumps({"version": 1}), encoding="utf-8")
    monkeypatch.setattr(state_mod, "MAX_STATE_FILE_BYTES", 4)

    assert load(target) == SharingState()


def test_load_drops_a_half_written_identity_rather_than_constructing_one(tmp_path):
    target = tmp_path / "fleet_sharing.json"
    target.write_text(
        json.dumps(
            {
                "version": 1,
                "identity": {"protected_private_key_b64": "onlyhalf"},
                "relay_origin": "https://relay.example.test",
                "session_id": "sess",
            }
        ),
        encoding="utf-8",
    )

    loaded = load(target)

    assert loaded.identity is None
    assert loaded.relay_origin == "https://relay.example.test"
    assert loaded.session_id == "sess"


@pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX mode bits; Windows relies on DPAPI"
)
def test_saved_file_is_owner_only_on_posix(tmp_path):
    target = tmp_path / "fleet_sharing.json"
    save(target, SharingState(relay_origin="https://relay.example.test"))
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
