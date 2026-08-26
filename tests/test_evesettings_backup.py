"""Archive naming, integrity, pruning and restore. All on tmp_path."""

import os
import zipfile
from datetime import UTC, datetime

import pytest

from wingman.evesettings import backup


def at(second=0):
    return datetime(2026, 8, 24, 12, 34, second, tzinfo=UTC)


def profile_with(tmp_path, name="settings_Default", files=("core_char_98123456.dat",)):
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
        store, profile / "core_char_98123456.dat", origin="auto", now=at()
    )
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
    assert len(backup.enumerate_backups(store)[0]) == 2


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
    assert backup.enumerate_backups(store) == ([], False)
    assert list(store.iterdir()) == []


def test_an_abandoned_claim_is_not_listable(tmp_path):
    """_claim() creates the FINAL name empty and only then stages and
    replaces. Process death in that window -- a kill, an OOM, a power cut
    mid-copy -- leaves a 0-byte .zip that parse_name accepts, that restore
    can only fail on, and that consumes a prune slot from a real backup."""
    store = tmp_path / "backups"
    claimed = backup._claim(
        store, "20260824-120000", "auto", "character", "aabbccdd", "core_char_1"
    )
    assert claimed.exists() and claimed.stat().st_size == 0
    assert backup.enumerate_backups(store) == ([], False)


def test_backup_contains_the_file_and_a_manifest(tmp_path):
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    made = backup.create_file_backup(
        store, profile / "core_char_98123456.dat", origin="manual", now=at()
    )
    with zipfile.ZipFile(made) as archive:
        assert sorted(archive.namelist()) == [
            "core_char_98123456.dat",
            backup.MANIFEST_NAME,
        ]


def test_profile_backup_holds_every_settings_file(tmp_path):
    profile = profile_with(
        tmp_path, files=("core_char_1.dat", "core_user_2.dat", "notes.txt")
    )
    store = tmp_path / "backups"
    made = backup.create_profile_backup(store, profile, origin="manual", now=at())
    with zipfile.ZipFile(made) as archive:
        assert sorted(archive.namelist()) == [
            "core_char_1.dat",
            "core_user_2.dat",
            backup.MANIFEST_NAME,
        ]


def test_prune_keeps_the_newest_auto_backups(tmp_path):
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    source = profile / "core_char_98123456.dat"
    for second in range(5):
        backup.create_file_backup(store, source, origin="auto", now=at(second))
    removed = backup.prune(store, keep=2)
    assert len(removed) == 3
    assert len(backup.enumerate_backups(store)[0]) == 2


def test_prune_never_touches_manual_backups(tmp_path):
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    source = profile / "core_char_98123456.dat"
    for second in range(4):
        backup.create_file_backup(store, source, origin="manual", now=at(second))
    assert backup.prune(store, keep=1) == []
    assert len(backup.enumerate_backups(store)[0]) == 4


def test_prune_does_not_cross_profiles_for_the_same_character(tmp_path):
    """core_char_<id>.dat exists in EVERY settings set. Grouping by stem
    alone would let one profile's backups evict another's."""
    default = profile_with(tmp_path, name="settings_Default")
    alt = profile_with(tmp_path, name="settings_Alt")
    store = tmp_path / "backups"
    for second in range(3):
        backup.create_file_backup(
            store, default / "core_char_98123456.dat", origin="auto", now=at(second)
        )
    backup.create_file_backup(
        store, alt / "core_char_98123456.dat", origin="auto", now=at(9)
    )
    backup.prune(store, keep=1)
    remaining, _ = backup.enumerate_backups(store)
    assert len(remaining) == 2
    assert {info.src for info in remaining} == {
        backup.source_key(default),
        backup.source_key(alt),
    }


def test_restore_puts_the_file_back(tmp_path):
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    source = profile / "core_char_98123456.dat"
    made = backup.create_file_backup(store, source, origin="manual", now=at())
    source.write_bytes(b"clobbered")
    backup.restore(store, made, tmp_path / "root")
    assert source.read_bytes() == b"payload-core_char_98123456.dat"


def test_restore_failure_during_extraction_leaves_the_profile_untouched(tmp_path):
    """Extraction now stages every member before anything live is touched.
    A failure partway through must leave the profile bit-for-bit as it was
    -- no files deleted, no partial or leftover staging files -- rather
    than half-repopulated."""
    profile = profile_with(tmp_path, files=("core_char_1.dat", "core_user_2.dat"))
    store = tmp_path / "backups"
    made = backup.create_profile_backup(store, profile, origin="manual", now=at())
    before = {p.name: p.read_bytes() for p in profile.iterdir()}
    backups_before = set(backup.enumerate_backups(store)[0])

    def explode(*args, **kwargs):
        raise OSError("disk full")

    monkey = pytest.MonkeyPatch()
    monkey.setattr(backup.shutil, "copyfileobj", explode)
    try:
        with pytest.raises(OSError):
            backup.restore(store, made, tmp_path / "root")
    finally:
        monkey.undo()

    after = {p.name: p.read_bytes() for p in profile.iterdir()}
    assert after == before
    # No auto-backup was taken either: the failure is in extraction, which
    # now happens before the pre-restore backup, so nothing was even
    # attempted against the live profile.
    assert set(backup.enumerate_backups(store)[0]) == backups_before


def test_restore_failure_in_the_auto_backup_leaves_the_profile_untouched(tmp_path):
    """A failure in the pre-restore auto-backup must abort the same as a
    failure during extraction: every member is already staged by then, but
    nothing live has been touched, so the fix is to unstage and leave the
    profile alone."""
    profile = profile_with(tmp_path, files=("core_char_1.dat",))
    store = tmp_path / "backups"
    made = backup.create_profile_backup(store, profile, origin="manual", now=at())
    before = {p.name: p.read_bytes() for p in profile.iterdir()}

    def explode(*args, **kwargs):
        raise OSError("disk full")

    monkey = pytest.MonkeyPatch()
    monkey.setattr(backup, "create_profile_backup", explode)
    try:
        with pytest.raises(OSError):
            backup.restore(store, made, tmp_path / "root")
    finally:
        monkey.undo()

    after = {p.name: p.read_bytes() for p in profile.iterdir()}
    assert after == before


def test_profile_restore_removes_files_absent_from_the_archive(tmp_path):
    profile = profile_with(tmp_path, files=("core_char_1.dat",))
    store = tmp_path / "backups"
    made = backup.create_profile_backup(store, profile, origin="manual", now=at())
    (profile / "core_char_2.dat").write_bytes(b"added later")
    backup.restore(store, made, tmp_path / "root")
    assert (profile / "core_char_1.dat").exists()
    assert not (profile / "core_char_2.dat").exists()


def test_profile_restore_backs_up_before_deleting(tmp_path):
    profile = profile_with(tmp_path, files=("core_char_1.dat",))
    store = tmp_path / "backups"
    made = backup.create_profile_backup(store, profile, origin="manual", now=at())
    backup.restore(store, made, tmp_path / "root", now=at(5))
    autos = [i for i in backup.enumerate_backups(store)[0] if i.origin == "auto"]
    assert len(autos) == 1


def test_restore_rejects_an_archive_with_a_path_bearing_entry(tmp_path):
    """Validation is complete and up front, so a bad archive cannot leave
    the profile emptied and half-repopulated."""
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    store.mkdir(parents=True)
    hostile = (
        store
        / f"20260824-123456-000-manual-profile-{backup.source_key(profile)}-Default.zip"
    )
    with zipfile.ZipFile(hostile, "w") as archive:
        archive.writestr(
            backup.MANIFEST_NAME,
            f'{{"kind": "profile", "source": "{profile.as_posix()}"}}',
        )
        archive.writestr("../escape.dat", "nope")
    with pytest.raises(ValueError):
        backup.restore(store, hostile, tmp_path / "root")
    assert (profile / "core_char_98123456.dat").exists()


def test_restore_rejects_an_unexpected_member(tmp_path):
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    store.mkdir(parents=True)
    hostile = (
        store
        / f"20260824-123456-000-manual-profile-{backup.source_key(profile)}-Default.zip"
    )
    with zipfile.ZipFile(hostile, "w") as archive:
        archive.writestr(
            backup.MANIFEST_NAME,
            f'{{"kind": "profile", "source": "{profile.as_posix()}"}}',
        )
        archive.writestr("payload.exe", "nope")
    with pytest.raises(ValueError):
        backup.restore(store, hostile, tmp_path / "root")


def test_restore_rejects_a_file_archive_carrying_a_passenger_member(tmp_path):
    """A character archive backs up exactly one file. An extra member would be
    written into the live profile while the pre-restore backup covers only the
    declared source -- clobbering an unrelated character with no way back."""
    profile = profile_with(tmp_path)
    bystander = profile / "core_char_222.dat"
    bystander.write_bytes(b"unrelated")
    store = tmp_path / "backups"
    store.mkdir(parents=True)
    source = profile / "core_char_98123456.dat"
    hostile = (
        store
        / f"20260824-123456-000-manual-character-{backup.source_key(profile)}-core_char_98123456.zip"
    )
    with zipfile.ZipFile(hostile, "w") as archive:
        archive.writestr(
            backup.MANIFEST_NAME,
            f'{{"kind": "character", "source": "{source.as_posix()}"}}',
        )
        archive.writestr("core_char_98123456.dat", "restored")
        archive.writestr("core_char_222.dat", "passenger")
    with pytest.raises(ValueError):
        backup.restore(store, hostile, tmp_path / "root")
    assert bystander.read_bytes() == b"unrelated"


def test_restore_rejects_a_target_outside_the_current_root(tmp_path):
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    made = backup.create_file_backup(
        store, profile / "core_char_98123456.dat", origin="manual", now=at()
    )
    with pytest.raises(ValueError):
        backup.restore(store, made, tmp_path / "elsewhere")


def test_delete_removes_one_archive(tmp_path):
    profile = profile_with(tmp_path)
    store = tmp_path / "backups"
    made = backup.create_file_backup(
        store, profile / "core_char_98123456.dat", origin="manual", now=at()
    )
    backup.delete(store, made)
    assert backup.enumerate_backups(store) == ([], False)


def test_delete_refuses_a_path_outside_the_backup_folder(tmp_path):
    store = tmp_path / "backups"
    store.mkdir()
    outsider = tmp_path / "important.zip"
    outsider.write_bytes(b"x")
    with pytest.raises(ValueError):
        backup.delete(store, outsider)
    assert outsider.exists()


def test_an_unreadable_store_is_reported_not_read_as_empty(tmp_path):
    """The conflation tree._scan was written to avoid, on the backup side.

    A store that denied us and a store that has never been written are
    different answers. Collapsing both into [] tells a user "no backups
    yet" about a directory that is full of them -- and this feature's
    whole promise is that every overwrite is backed up first.
    """
    store = tmp_path / "backups"
    store.mkdir()
    (store / "20260824-120000-000-auto-character-aabbccdd-x.zip").write_bytes(
        b"not empty"
    )
    store.chmod(0o000)
    try:
        try:
            os.scandir(str(store)).close()
        except PermissionError:
            pass
        else:  # pragma: no cover - root, or a filesystem without modes
            pytest.skip("this user can read a mode-000 directory")
        assert backup.enumerate_backups(store) == ([], True)
    finally:
        store.chmod(0o700)


def test_a_missing_store_is_empty_but_not_unreadable(tmp_path):
    """The other half of the same distinction: never written is not denied."""
    assert backup.enumerate_backups(tmp_path / "nope") == ([], False)


def test_pruning_an_unreadable_store_deletes_nothing(tmp_path):
    store = tmp_path / "backups"
    store.mkdir()
    store.chmod(0o000)
    try:
        try:
            os.scandir(str(store)).close()
        except PermissionError:
            pass
        else:  # pragma: no cover - root, or a filesystem without modes
            pytest.skip("this user can read a mode-000 directory")
        assert backup.prune(store, 1) == []
    finally:
        store.chmod(0o700)


def test_every_declared_kind_and_origin_round_trips_through_the_name():
    """_KINDS and _ORIGINS are the source of truth for the filename grammar.

    They used to be spelled a second time inside _NAME_RE, where adding a
    kind to one and not the other would write names that parse_name then
    refuses to read -- a backup on disk, invisible to listing, pruning and
    restore. This asserts the two cannot drift apart again.
    """
    for kind in backup._KINDS:
        for origin in backup._ORIGINS:
            name = f"20260824-120000-000-{origin}-{kind}-aabbccdd-stem.zip"
            info = backup.parse_name(name)
            assert info is not None, name
            assert info.kind == kind and info.origin == origin
