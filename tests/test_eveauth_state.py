import json
import os
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from wingman.eveauth import state
from wingman.eveauth.state import (
    AuthorityCharacter,
    AuthorityState,
    load_authority,
    save_authority,
)


def authority_character(character_id: int = 42) -> AuthorityCharacter:
    return AuthorityCharacter(
        character_id=character_id,
        character_name="Aiga Otsolen",
        owner_hash="owner-123",
        scopes=(
            "esi-skills.read_skills.v1",
            "esi-skills.read_skillqueue.v1",
        ),
        authenticated_utc=datetime(2026, 9, 3, 12, 30, tzinfo=UTC),
        needs_reauth=False,
        refresh_token_blob="QUJD",
    )


def test_authority_round_trip_keeps_only_identity_and_credentials(tmp_path):
    original = AuthorityState(characters=[authority_character()])
    target = tmp_path / "eve_authority.json"

    save_authority(target, original)
    loaded, warnings = load_authority(target)

    assert loaded == original
    assert warnings == ()
    document = target.read_text(encoding="utf-8")
    assert "active_levels" not in document
    assert set(json.loads(document)["characters"][0]) == {
        "character_id",
        "character_name",
        "owner_hash",
        "scopes",
        "authenticated_utc",
        "needs_reauth",
        "refresh_token_blob",
    }


def test_authority_load_caps_characters_and_later_duplicate_wins(tmp_path):
    target = tmp_path / "eve_authority.json"
    rows = [
        {"character_id": 1, "character_name": "stale"},
        *({"character_id": character_id} for character_id in range(2, 60)),
        {"character_id": 1, "character_name": "fresh"},
    ]
    target.write_text(json.dumps({"characters": rows}), encoding="utf-8")

    loaded, warnings = load_authority(target)

    assert loaded is not None
    assert warnings == ()
    assert len(loaded.characters) == state.MAX_CHARACTERS
    assert loaded.characters[0].character_name == "fresh"
    assert len({character.character_id for character in loaded.characters}) == 50


def test_authority_load_bounds_and_deduplicates_scopes(tmp_path):
    target = tmp_path / "eve_authority.json"
    target.write_text(
        json.dumps(
            {
                "characters": [
                    {
                        "character_id": 7,
                        "scopes": ["same", "same", 3]
                        + [f"scope-{index}" for index in range(state.MAX_SCOPES + 20)],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    loaded, _warnings = load_authority(target)

    assert loaded is not None
    assert len(loaded.characters[0].scopes) == state.MAX_SCOPES
    assert loaded.characters[0].scopes[:2] == ("same", "scope-0")


def test_authority_load_drops_an_oversized_dpapi_blob(tmp_path):
    target = tmp_path / "eve_authority.json"
    target.write_text(
        json.dumps(
            {
                "characters": [
                    {
                        "character_id": 7,
                        "refresh_token_blob": "x"
                        * (state.MAX_REFRESH_TOKEN_BLOB_CHARS + 1),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    loaded, _warnings = load_authority(target)

    assert loaded is not None
    assert loaded.characters[0].refresh_token_blob == ""
    assert loaded.characters[0].needs_reauth is True


def test_authority_load_drops_invalid_character_ids(tmp_path):
    target = tmp_path / "eve_authority.json"
    target.write_text(
        json.dumps(
            {
                "characters": [
                    {"character_id": True},
                    {"character_id": 0},
                    {"character_id": -1},
                    {"character_id": 8},
                ]
            }
        ),
        encoding="utf-8",
    )

    loaded, _warnings = load_authority(target)

    assert loaded is not None
    assert [character.character_id for character in loaded.characters] == [8]


def test_authority_save_refuses_more_than_fifty_characters(tmp_path):
    target = tmp_path / "eve_authority.json"
    authority = AuthorityState(
        [AuthorityCharacter(character_id=index) for index in range(1, 52)]
    )

    with pytest.raises(ValueError, match="up to 50"):
        save_authority(target, authority)

    assert not target.exists()


def test_authority_save_refuses_duplicate_character_ids(tmp_path):
    target = tmp_path / "eve_authority.json"
    authority = AuthorityState(
        [AuthorityCharacter(character_id=7), AuthorityCharacter(character_id=7)]
    )

    with pytest.raises(ValueError, match="unique"):
        save_authority(target, authority)

    assert not target.exists()


def test_authority_save_refuses_too_many_scopes(tmp_path):
    target = tmp_path / "eve_authority.json"
    authority = AuthorityState(
        [
            AuthorityCharacter(
                character_id=7,
                scopes=tuple(f"scope-{index}" for index in range(state.MAX_SCOPES + 1)),
            )
        ]
    )

    with pytest.raises(ValueError, match="at most 100"):
        save_authority(target, authority)

    assert not target.exists()


def test_authority_save_refuses_an_oversized_dpapi_blob(tmp_path):
    target = tmp_path / "eve_authority.json"
    authority = AuthorityState(
        [
            AuthorityCharacter(
                character_id=7,
                refresh_token_blob="x" * (state.MAX_REFRESH_TOKEN_BLOB_CHARS + 1),
            )
        ]
    )

    with pytest.raises(ValueError, match="too large"):
        save_authority(target, authority)

    assert not target.exists()


def test_authority_save_keeps_previous_document_as_sibling_backup(tmp_path):
    target = tmp_path / "eve_authority.json"
    save_authority(target, AuthorityState([authority_character(1)]))
    save_authority(target, AuthorityState([authority_character(2)]))

    backup = json.loads(target.with_name(target.name + ".bak").read_text())

    assert backup["characters"][0]["character_id"] == 1
    loaded, _warnings = load_authority(target)
    assert loaded is not None
    assert loaded.characters[0].character_id == 2


def test_authority_save_failure_leaves_primary_and_backup_untouched(
    tmp_path, monkeypatch
):
    target = tmp_path / "eve_authority.json"
    save_authority(target, AuthorityState([authority_character(1)]))
    save_authority(target, AuthorityState([authority_character(2)]))
    before_primary = target.read_bytes()
    backup_path = target.with_name(target.name + ".bak")
    before_backup = backup_path.read_bytes()

    def fail_write(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(state.atomicio, "write_atomic", fail_write)

    with pytest.raises(OSError, match="disk full"):
        save_authority(target, AuthorityState([authority_character(3)]))

    assert target.read_bytes() == before_primary
    assert backup_path.read_bytes() == before_backup


def test_corrupt_authority_is_preserved_and_recovered_from_backup(tmp_path):
    target = tmp_path / "eve_authority.json"
    save_authority(target, AuthorityState([authority_character(1)]))
    save_authority(target, AuthorityState([authority_character(2)]))
    target.write_text("not json", encoding="utf-8")

    loaded, warnings = load_authority(target)

    assert loaded is not None
    assert loaded.characters[0].character_id == 1
    assert warnings and "Recovered" in warnings[0]
    assert len(list(tmp_path.glob("eve_authority.json.corrupt-*"))) == 1
    reloaded, second_warnings = load_authority(target)
    assert reloaded == loaded
    assert second_warnings == ()


@pytest.mark.parametrize("document", ["[]", '{"characters": "not-a-list"}'])
def test_structurally_corrupt_authority_fails_closed_and_is_preserved(
    tmp_path, document
):
    target = tmp_path / "eve_authority.json"
    target.write_text(document, encoding="utf-8")

    loaded, warnings = load_authority(target)

    assert loaded is None
    assert warnings and "could not be recovered" in warnings[0]
    assert not target.exists()
    assert len(list(tmp_path.glob("eve_authority.json.corrupt-*"))) == 1


def test_unrecoverable_corrupt_authority_fails_closed_and_is_preserved(tmp_path):
    target = tmp_path / "eve_authority.json"
    target.write_text("not json", encoding="utf-8")

    loaded, warnings = load_authority(target)

    assert loaded is None
    assert warnings and "could not be recovered" in warnings[0]
    assert not target.exists()
    assert len(list(tmp_path.glob("eve_authority.json.corrupt-*"))) == 1


def test_missing_primary_recovers_from_authority_backup(tmp_path):
    target = tmp_path / "eve_authority.json"
    save_authority(target, AuthorityState([authority_character(1)]))
    save_authority(target, AuthorityState([authority_character(2)]))
    target.unlink()

    loaded, warnings = load_authority(target)

    assert loaded is not None
    assert loaded.characters[0].character_id == 1
    assert warnings and "was missing" in warnings[0]
    assert target.exists()


def test_missing_authority_is_empty_and_silent(tmp_path):
    loaded, warnings = load_authority(tmp_path / "eve_authority.json")

    assert loaded == AuthorityState()
    assert warnings == ()


def test_unreadable_authority_fails_closed(tmp_path, monkeypatch):
    target = tmp_path / "eve_authority.json"
    target.write_text("{}", encoding="utf-8")
    real_open = Path.open

    def refusing_open(self, *args, **kwargs):
        if self == target:
            raise PermissionError(13, "Permission denied", str(self))
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", refusing_open)

    loaded, warnings = load_authority(target)

    assert loaded is None
    assert warnings and "could not be read" in warnings[0]


def test_authority_read_is_bounded_before_json_decode(tmp_path, monkeypatch):
    target = tmp_path / "eve_authority.json"
    target.write_text('{"characters": []}', encoding="utf-8")
    monkeypatch.setattr(state, "MAX_STATE_FILE_BYTES", 5)

    loaded, warnings = load_authority(target)

    assert loaded is None
    assert warnings and "could not be recovered" in warnings[0]
    assert len(list(tmp_path.glob("eve_authority.json.corrupt-*"))) == 1


@pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX mode bits; Windows relies on DPAPI"
)
def test_authority_primary_and_backup_are_owner_only_on_posix(tmp_path):
    target = tmp_path / "eve_authority.json"
    target.write_text("{}", encoding="utf-8")
    os.chmod(target, 0o644)

    save_authority(target, AuthorityState([authority_character()]))

    backup = target.with_name(target.name + ".bak")
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
