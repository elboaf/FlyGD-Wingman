"""Archive naming, integrity, pruning and restore. All on tmp_path."""
import zipfile
from datetime import datetime, timezone

import pytest

from obs_youtube_uploader.evesettings import backup


def at(second=0):
    return datetime(2026, 8, 24, 12, 34, second, tzinfo=timezone.utc)


def profile_with(tmp_path, name="settings_Default",
                 files=("core_char_98123456.dat",)):
    target = tmp_path / "root" / "server" / name
    target.mkdir(parents=True)
    for filename in files:
        (target / filename).write_bytes(b"payload-" + filename.encode())
    return target


def test_source_key_is_stable_and_short(tmp_path):
    key = backup.source_key(tmp_path)
    assert key == backup.source_key(tmp_path)
    assert len(key) == 8 and all(c in "0123456789abcdef" for c in key)


def test_source_key_differs_between_profiles(tmp_path):
    a = tmp_path / "settings_Default"
    b = tmp_path / "settings_Alt"
    a.mkdir()
    b.mkdir()
    assert backup.source_key(a) != backup.source_key(b)


def test_parse_name_round_trips_a_created_archive(tmp_path):
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    made = backup.create_file_backup(
        store, profile / "core_char_98123456.dat", origin="auto", now=at())
    info = backup.parse_name(made.name)
    assert info.origin == "auto" and info.kind == "character"
    assert info.stem == "core_char_98123456"
    assert info.src == backup.source_key(profile)


def test_parse_name_rejects_a_foreign_file():
    assert backup.parse_name("holiday-photos.zip") is None
    assert backup.parse_name("20260824-123456-000-auto-character-xx-stem.zip") is None


def test_parse_name_keeps_hyphens_in_the_stem():
    name = "20260824-123456-000-manual-profile-a1b2c3d4-my-odd-profile.zip"
    info = backup.parse_name(name)
    assert info.stem == "my-odd-profile" and info.kind == "profile"


def test_two_backups_in_the_same_second_both_survive(tmp_path):
    """Second-granularity names collide; TriffView's loop dies on the second
    one, leaving a multi-target copy half-applied."""
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    source = profile / "core_char_98123456.dat"
    first = backup.create_file_backup(store, source, origin="auto", now=at())
    second = backup.create_file_backup(store, source, origin="auto", now=at())
    assert first != second
    assert first.exists() and second.exists()
    assert len(backup.enumerate_backups(store)) == 2


def test_a_failed_build_leaves_nothing_listable(tmp_path):
    """A truncated archive under its final name would list as restorable."""
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    source = profile / "core_char_98123456.dat"

    def explode(*args, **kwargs):
        raise OSError("disk full")

    monkey = pytest.MonkeyPatch()
    monkey.setattr(backup.shutil, "copyfileobj", explode)
    try:
        with pytest.raises(OSError):
            backup.create_file_backup(store, source, origin="auto", now=at())
    finally:
        monkey.undo()
    assert backup.enumerate_backups(store) == []
    assert list(store.iterdir()) == []


def test_backup_contains_the_file_and_a_manifest(tmp_path):
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    made = backup.create_file_backup(
        store, profile / "core_char_98123456.dat", origin="manual", now=at())
    with zipfile.ZipFile(made) as archive:
        assert sorted(archive.namelist()) == [
            "core_char_98123456.dat", backup.MANIFEST_NAME]


def test_profile_backup_holds_every_settings_file(tmp_path):
    profile = profile_with(tmp_path, files=("core_char_1.dat",
                                            "core_user_2.dat",
                                            "notes.txt"))
    store = tmp_path / "backups"
    made = backup.create_profile_backup(store, profile, origin="manual",
                                        now=at())
    with zipfile.ZipFile(made) as archive:
        assert sorted(archive.namelist()) == [
            "core_char_1.dat", "core_user_2.dat", backup.MANIFEST_NAME]


def test_prune_keeps_the_newest_auto_backups(tmp_path):
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    source = profile / "core_char_98123456.dat"
    for second in range(5):
        backup.create_file_backup(store, source, origin="auto", now=at(second))
    removed = backup.prune(store, keep=2)
    assert len(removed) == 3
    assert len(backup.enumerate_backups(store)) == 2


def test_prune_never_touches_manual_backups(tmp_path):
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    source = profile / "core_char_98123456.dat"
    for second in range(4):
        backup.create_file_backup(store, source, origin="manual",
                                  now=at(second))
    assert backup.prune(store, keep=1) == []
    assert len(backup.enumerate_backups(store)) == 4


def test_prune_does_not_cross_profiles_for_the_same_character(tmp_path):
    """core_char_<id>.dat exists in EVERY settings set. Grouping by stem
    alone would let one profile's backups evict another's."""
    default = profile_with(tmp_path, name="settings_Default")
    alt = profile_with(tmp_path, name="settings_Alt")
    store = tmp_path / "backups"
    for second in range(3):
        backup.create_file_backup(store, default / "core_char_98123456.dat",
                                  origin="auto", now=at(second))
    backup.create_file_backup(store, alt / "core_char_98123456.dat",
                              origin="auto", now=at(9))
    backup.prune(store, keep=1)
    remaining = backup.enumerate_backups(store)
    assert len(remaining) == 2
    assert {info.src for info in remaining} == {
        backup.source_key(default), backup.source_key(alt)}


def test_restore_puts_the_file_back(tmp_path):
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    source = profile / "core_char_98123456.dat"
    made = backup.create_file_backup(store, source, origin="manual", now=at())
    source.write_bytes(b"clobbered")
    backup.restore(store, made, tmp_path / "root")
    assert source.read_bytes() == b"payload-core_char_98123456.dat"


def test_profile_restore_removes_files_absent_from_the_archive(tmp_path):
    profile = profile_with(tmp_path, files=("core_char_1.dat",))
    store = tmp_path / "backups"
    made = backup.create_profile_backup(store, profile, origin="manual",
                                        now=at())
    (profile / "core_char_2.dat").write_bytes(b"added later")
    backup.restore(store, made, tmp_path / "root")
    assert (profile / "core_char_1.dat").exists()
    assert not (profile / "core_char_2.dat").exists()


def test_profile_restore_backs_up_before_deleting(tmp_path):
    profile = profile_with(tmp_path, files=("core_char_1.dat",))
    store = tmp_path / "backups"
    made = backup.create_profile_backup(store, profile, origin="manual",
                                        now=at())
    backup.restore(store, made, tmp_path / "root", now=at(5))
    autos = [i for i in backup.enumerate_backups(store) if i.origin == "auto"]
    assert len(autos) == 1


def test_restore_rejects_an_archive_with_a_path_bearing_entry(tmp_path):
    """Validation is complete and up front, so a bad archive cannot leave
    the profile emptied and half-repopulated."""
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    store.mkdir(parents=True)
    hostile = store / "20260824-123456-000-manual-profile-{}-Default.zip".format(
        backup.source_key(profile))
    with zipfile.ZipFile(hostile, "w") as archive:
        archive.writestr(backup.MANIFEST_NAME, '{"kind": "profile", '
                         '"source": "%s"}' % profile.as_posix())
        archive.writestr("../escape.dat", "nope")
    with pytest.raises(ValueError):
        backup.restore(store, hostile, tmp_path / "root")
    assert (profile / "core_char_98123456.dat").exists()


def test_restore_rejects_an_unexpected_member(tmp_path):
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    store.mkdir(parents=True)
    hostile = store / "20260824-123456-000-manual-profile-{}-Default.zip".format(
        backup.source_key(profile))
    with zipfile.ZipFile(hostile, "w") as archive:
        archive.writestr(backup.MANIFEST_NAME, '{"kind": "profile", '
                         '"source": "%s"}' % profile.as_posix())
        archive.writestr("payload.exe", "nope")
    with pytest.raises(ValueError):
        backup.restore(store, hostile, tmp_path / "root")


def test_restore_rejects_a_target_outside_the_current_root(tmp_path):
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    made = backup.create_file_backup(
        store, profile / "core_char_98123456.dat", origin="manual", now=at())
    with pytest.raises(ValueError):
        backup.restore(store, made, tmp_path / "elsewhere")


def test_delete_removes_one_archive(tmp_path):
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    made = backup.create_file_backup(
        store, profile / "core_char_98123456.dat", origin="manual", now=at())
    backup.delete(store, made)
    assert backup.enumerate_backups(store) == []


def test_delete_refuses_a_path_outside_the_backup_folder(tmp_path):
    store = tmp_path / "backups"
    store.mkdir()
    outsider = tmp_path / "important.zip"
    outsider.write_bytes(b"x")
    with pytest.raises(ValueError):
        backup.delete(store, outsider)
    assert outsider.exists()
