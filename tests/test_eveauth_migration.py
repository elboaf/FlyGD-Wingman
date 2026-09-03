import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from wingman.eveauth.migration import (
    LegacyDisposition,
    inspect_legacy_skills,
    migrate_legacy_skills,
)
from wingman.eveauth.state import (
    AuthorityCharacter,
    AuthorityState,
    load_authority,
    save_authority,
)
from wingman.eveskills import state as skills_state

FIXTURES = Path(__file__).parent / "fixtures" / "eveauth"


def copy_fixture(name: str, target: Path) -> None:
    target.write_bytes((FIXTURES / name).read_bytes())


def test_inspection_distinguishes_genuinely_absent_legacy_state(tmp_path):
    result = inspect_legacy_skills(tmp_path / "eve_skills.json")

    assert result.disposition is LegacyDisposition.ABSENT
    assert result.state == skills_state.SkillsState()
    assert result.warnings == ()
    assert result.error == ""


def test_inspection_loads_a_valid_legacy_document(tmp_path):
    target = tmp_path / "eve_skills.json"
    copy_fixture("legacy-valid.json", target)

    result = inspect_legacy_skills(target)

    assert result.disposition is LegacyDisposition.LOADED
    assert result.state is not None
    assert result.state.selected_plan_name == "Interceptors"
    assert result.authority.characters[0].refresh_token_blob == "QUJD"
    assert result.warnings == ()
    assert result.error == ""


def test_empty_but_valid_legacy_document_is_loaded_not_absent(tmp_path):
    target = tmp_path / "eve_skills.json"
    copy_fixture("legacy-empty.json", target)

    result = inspect_legacy_skills(target)

    assert result.disposition is LegacyDisposition.LOADED
    assert result.state == skills_state.SkillsState()
    assert result.error == ""


@pytest.mark.parametrize("document", ["[]", '{"characters": {}}'])
def test_parseable_but_malformed_legacy_envelope_is_failed_not_loaded_empty(
    tmp_path, document
):
    target = tmp_path / "eve_skills.json"
    target.write_text(document, encoding="utf-8")
    before = target.read_bytes()

    result = inspect_legacy_skills(target)

    assert result.disposition is LegacyDisposition.FAILED
    assert result.state is None
    assert result.error
    assert target.read_bytes() == before


def test_malformed_legacy_envelope_recovers_from_valid_backup_without_mutation(
    tmp_path,
):
    target = tmp_path / "eve_skills.json"
    target.write_text('{"characters": {}}', encoding="utf-8")
    backup = target.with_name(target.name + ".bak")
    copy_fixture("legacy-valid.json", backup)
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}

    result = inspect_legacy_skills(target)

    assert result.disposition is LegacyDisposition.RECOVERED
    assert result.state is not None
    assert result.authority.characters[0].refresh_token_blob == "QUJD"
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before


def test_corrupt_primary_recovers_from_valid_backup_without_mutating_evidence(tmp_path):
    target = tmp_path / "eve_skills.json"
    target.write_text("not json", encoding="utf-8")
    backup = target.with_name(target.name + ".bak")
    copy_fixture("legacy-valid.json", backup)
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}

    result = inspect_legacy_skills(target)

    assert result.disposition is LegacyDisposition.RECOVERED
    assert result.state is not None
    assert result.state.characters[0].character_id == 90000001
    assert result.warnings and "backup" in result.warnings[0]
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before


def test_missing_primary_with_valid_backup_is_recovered_without_restore(tmp_path):
    target = tmp_path / "eve_skills.json"
    backup = target.with_name(target.name + ".bak")
    copy_fixture("legacy-valid.json", backup)

    result = inspect_legacy_skills(target)

    assert result.disposition is LegacyDisposition.RECOVERED
    assert result.state is not None
    assert not target.exists()
    assert backup.exists()


def test_access_failure_is_failed_not_absent(tmp_path, monkeypatch):
    target = tmp_path / "eve_skills.json"
    target.write_text("{}", encoding="utf-8")
    real_open = Path.open

    def refusing_open(self, *args, **kwargs):
        if self == target:
            raise PermissionError(13, "Permission denied", str(self))
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", refusing_open)

    result = inspect_legacy_skills(target)

    assert result.disposition is LegacyDisposition.FAILED
    assert result.state is None
    assert "could not be read" in result.error


def test_corrupt_legacy_without_valid_backup_fails_without_mutating_evidence(tmp_path):
    target = tmp_path / "eve_skills.json"
    target.write_text("not json", encoding="utf-8")
    before = tuple(tmp_path.iterdir())

    result = inspect_legacy_skills(target)

    assert result.disposition is LegacyDisposition.FAILED
    assert result.state is None
    assert result.error
    assert tuple(tmp_path.iterdir()) == before
    assert target.read_text(encoding="utf-8") == "not json"


def test_unreadable_backup_makes_corrupt_primary_failed(tmp_path, monkeypatch):
    target = tmp_path / "eve_skills.json"
    target.write_text("not json", encoding="utf-8")
    backup = target.with_name(target.name + ".bak")
    copy_fixture("legacy-valid.json", backup)
    real_open = Path.open

    def refusing_backup(self, *args, **kwargs):
        if self == backup:
            raise PermissionError(13, "Permission denied", str(self))
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", refusing_backup)

    result = inspect_legacy_skills(target)

    assert result.disposition is LegacyDisposition.FAILED
    assert result.state is None
    assert "backup" in result.error
    assert target.exists() and backup.exists()


def test_oversized_primary_without_valid_backup_is_failed_and_untouched(
    tmp_path, monkeypatch
):
    target = tmp_path / "eve_skills.json"
    target.write_text('{"characters": []}', encoding="utf-8")
    monkeypatch.setattr(skills_state, "MAX_STATE_FILE_BYTES", 5)
    before = target.read_bytes()

    result = inspect_legacy_skills(target)

    assert result.disposition is LegacyDisposition.FAILED
    assert result.state is None
    assert "limit" in result.error
    assert target.read_bytes() == before


def test_migration_saves_authority_before_stripped_skills(tmp_path):
    legacy_path = tmp_path / "eve_skills.json"
    authority_path = tmp_path / "eve_authority.json"
    copy_fixture("legacy-valid.json", legacy_path)
    calls = []

    def record_authority(path, authority):
        calls.append(("authority", path, authority))

    def record_skills(skills, path):
        calls.append(("skills", path, skills))

    result = migrate_legacy_skills(
        legacy_path,
        authority_path,
        authority_saver=record_authority,
        skills_saver=record_skills,
    )

    assert result.completed is True
    assert result.error == ""
    assert [call[0] for call in calls] == ["authority", "skills"]
    authority = calls[0][2]
    assert authority.characters == [
        AuthorityCharacter(
            character_id=90000001,
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
    ]
    stripped = calls[1][2]
    assert stripped.authority_migrated is True
    assert stripped.selected_plan_name == "Interceptors"
    character = stripped.characters[0]
    assert character.character_id == 90000001
    assert character.active_levels == {3300: 5}
    for field in (
        "character_name",
        "owner_hash",
        "scopes",
        "authenticated_utc",
        "needs_reauth",
        "refresh_token_blob",
    ):
        assert not hasattr(character, field)


def test_failed_legacy_inspection_writes_neither_document_nor_marker(tmp_path):
    legacy_path = tmp_path / "eve_skills.json"
    authority_path = tmp_path / "eve_authority.json"
    legacy_path.write_text("not json", encoding="utf-8")
    calls = []

    result = migrate_legacy_skills(
        legacy_path,
        authority_path,
        authority_saver=lambda *_args: calls.append("authority"),
        skills_saver=lambda *_args: calls.append("skills"),
    )

    assert result.completed is False
    assert result.skills is None
    assert result.error
    assert calls == []
    assert not authority_path.exists()
    assert legacy_path.read_text(encoding="utf-8") == "not json"


def test_authority_save_failure_never_strips_skills(tmp_path):
    legacy_path = tmp_path / "eve_skills.json"
    authority_path = tmp_path / "eve_authority.json"
    copy_fixture("legacy-valid.json", legacy_path)
    calls = []

    def fail_authority(_path, _authority):
        calls.append("authority")
        raise OSError("disk full")

    result = migrate_legacy_skills(
        legacy_path,
        authority_path,
        authority_saver=fail_authority,
        skills_saver=lambda *_args: calls.append("skills"),
    )

    assert result.completed is False
    assert result.skills is None
    assert "disk full" in result.error
    assert calls == ["authority"]
    unchanged = json.loads(legacy_path.read_text(encoding="utf-8"))
    assert unchanged["characters"][0]["refresh_token_blob"] == "QUJD"
    assert "authority_migrated" not in unchanged


def test_interruption_after_authority_save_resumes_without_reimporting_credentials(
    tmp_path,
):
    legacy_path = tmp_path / "eve_skills.json"
    authority_path = tmp_path / "eve_authority.json"
    copy_fixture("legacy-valid.json", legacy_path)

    def fail_skills(_skills, _path):
        raise OSError("interrupted")

    first = migrate_legacy_skills(legacy_path, authority_path, skills_saver=fail_skills)

    assert first.completed is False
    assert first.authority is not None
    assert first.skills is None
    saved_authority, warnings = load_authority(authority_path)
    assert warnings == ()
    assert saved_authority is not None
    assert saved_authority.characters[0].refresh_token_blob == "QUJD"

    second = migrate_legacy_skills(legacy_path, authority_path)

    assert second.completed is True
    loaded_skills, warnings = skills_state.load(legacy_path)
    assert warnings == []
    assert loaded_skills.authority_migrated is True
    assert not hasattr(loaded_skills.characters[0], "refresh_token_blob")
    reloaded_authority, warnings = load_authority(authority_path)
    assert warnings == ()
    assert reloaded_authority == saved_authority


def test_existing_valid_authority_is_one_way_authoritative(tmp_path):
    legacy_path = tmp_path / "eve_skills.json"
    authority_path = tmp_path / "eve_authority.json"
    copy_fixture("legacy-valid.json", legacy_path)
    existing = AuthorityState(
        [
            AuthorityCharacter(
                character_id=77,
                character_name="Already authoritative",
                refresh_token_blob="EXISTING",
            )
        ]
    )
    save_authority(authority_path, existing)

    result = migrate_legacy_skills(legacy_path, authority_path)

    assert result.completed is True
    loaded_authority, _warnings = load_authority(authority_path)
    assert loaded_authority == existing
    loaded_skills, _warnings = skills_state.load(legacy_path)
    assert loaded_skills.authority_migrated is True
    assert not hasattr(loaded_skills.characters[0], "refresh_token_blob")


def test_genuine_empty_existing_authority_is_one_way_authoritative(tmp_path):
    legacy_path = tmp_path / "eve_skills.json"
    authority_path = tmp_path / "eve_authority.json"
    copy_fixture("legacy-valid.json", legacy_path)
    save_authority(authority_path, AuthorityState())

    result = migrate_legacy_skills(legacy_path, authority_path)

    assert result.completed is True
    assert result.authority == AuthorityState()
    loaded_skills, warnings = skills_state.load(legacy_path)
    assert warnings == []
    assert loaded_skills.authority_migrated is True
    assert not hasattr(loaded_skills.characters[0], "refresh_token_blob")


def test_all_dropped_authority_rows_fail_closed_without_stripping_legacy(tmp_path):
    legacy_path = tmp_path / "eve_skills.json"
    authority_path = tmp_path / "eve_authority.json"
    copy_fixture("legacy-valid.json", legacy_path)
    authority_path.write_text(
        json.dumps({"characters": [None, {"character_id": 0}]}), encoding="utf-8"
    )
    before = legacy_path.read_bytes()

    result = migrate_legacy_skills(legacy_path, authority_path)

    assert result.completed is False
    assert result.authority == AuthorityState()
    assert result.skills is None
    assert "dropped" in result.error.lower()
    assert legacy_path.read_bytes() == before


def test_all_dropped_authority_backup_rows_remain_failed_on_retry(tmp_path):
    legacy_path = tmp_path / "eve_skills.json"
    authority_path = tmp_path / "eve_authority.json"
    copy_fixture("legacy-valid.json", legacy_path)
    authority_path.with_name(authority_path.name + ".bak").write_text(
        json.dumps({"characters": [None, {"character_id": 0}]}), encoding="utf-8"
    )
    before = legacy_path.read_bytes()

    first = migrate_legacy_skills(legacy_path, authority_path)
    second = migrate_legacy_skills(legacy_path, authority_path)

    assert first.completed is False
    assert first.skills is None
    assert second.completed is False
    assert second.skills is None
    assert not authority_path.exists()
    assert legacy_path.read_bytes() == before


def test_corrupt_existing_authority_never_falls_back_to_legacy_credentials(tmp_path):
    legacy_path = tmp_path / "eve_skills.json"
    authority_path = tmp_path / "eve_authority.json"
    copy_fixture("legacy-valid.json", legacy_path)
    authority_path.write_text("not json", encoding="utf-8")

    result = migrate_legacy_skills(legacy_path, authority_path)

    assert result.completed is False
    assert result.authority is None
    assert "authority" in result.error.lower()
    unchanged = json.loads(legacy_path.read_text(encoding="utf-8"))
    assert unchanged["characters"][0]["refresh_token_blob"] == "QUJD"
    assert "authority_migrated" not in unchanged
    assert len(list(tmp_path.glob("eve_authority.json.corrupt-*"))) == 1


def test_preserved_corrupt_authority_blocks_legacy_fallback_on_later_launch(tmp_path):
    legacy_path = tmp_path / "eve_skills.json"
    authority_path = tmp_path / "eve_authority.json"
    copy_fixture("legacy-valid.json", legacy_path)
    authority_path.write_text("not json", encoding="utf-8")

    first = migrate_legacy_skills(legacy_path, authority_path)
    second = migrate_legacy_skills(legacy_path, authority_path)

    assert first.completed is False
    assert second.completed is False
    assert second.authority is None
    assert "preserved corrupt authority" in second.error.lower()
    unchanged = json.loads(legacy_path.read_text(encoding="utf-8"))
    assert unchanged["characters"][0]["refresh_token_blob"] == "QUJD"
    assert "authority_migrated" not in unchanged


def test_completion_marker_without_authority_never_resurrects_legacy_credentials(
    tmp_path,
):
    legacy_path = tmp_path / "eve_skills.json"
    authority_path = tmp_path / "eve_authority.json"
    raw = json.loads((FIXTURES / "legacy-valid.json").read_text(encoding="utf-8"))
    raw["authority_migrated"] = True
    legacy_path.write_text(json.dumps(raw), encoding="utf-8")

    result = migrate_legacy_skills(legacy_path, authority_path)

    assert result.completed is False
    assert result.skills is None
    assert "completion marker" in result.error
    assert not authority_path.exists()
    unchanged = json.loads(legacy_path.read_text(encoding="utf-8"))
    assert unchanged["characters"][0]["refresh_token_blob"] == "QUJD"


def test_absent_legacy_migrates_to_empty_authority_and_completion_marker(tmp_path):
    legacy_path = tmp_path / "eve_skills.json"
    authority_path = tmp_path / "eve_authority.json"

    result = migrate_legacy_skills(legacy_path, authority_path)

    assert result.completed is True
    authority, authority_warnings = load_authority(authority_path)
    assert authority == AuthorityState()
    assert authority_warnings == ()
    skills, skills_warnings = skills_state.load(legacy_path)
    assert skills == skills_state.SkillsState(authority_migrated=True)
    assert skills_warnings == []


def test_valid_authority_does_not_make_corrupt_legacy_safe_to_rewrite(tmp_path):
    legacy_path = tmp_path / "eve_skills.json"
    authority_path = tmp_path / "eve_authority.json"
    legacy_path.write_text("not json", encoding="utf-8")
    existing = AuthorityState([AuthorityCharacter(character_id=77)])
    save_authority(authority_path, existing)
    before = legacy_path.read_bytes()

    result = migrate_legacy_skills(legacy_path, authority_path)

    assert result.completed is False
    assert result.authority == existing
    assert legacy_path.read_bytes() == before


def test_already_completed_migration_is_idempotent(tmp_path):
    legacy_path = tmp_path / "eve_skills.json"
    authority_path = tmp_path / "eve_authority.json"
    existing = AuthorityState([AuthorityCharacter(character_id=77)])
    save_authority(authority_path, existing)
    skills_state.save(skills_state.SkillsState(authority_migrated=True), legacy_path)
    writes = []

    result = migrate_legacy_skills(
        legacy_path,
        authority_path,
        authority_saver=lambda *_args: writes.append("authority"),
        skills_saver=lambda *_args: writes.append("skills"),
    )

    assert result.completed is True
    assert writes == []
