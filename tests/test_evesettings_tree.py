"""Discovery and containment. Every case builds a fake EVE tree in tmp_path,
so the whole module tests on Linux."""
import os
from pathlib import Path

import pytest

from obs_youtube_uploader.evesettings import tree


def build(root: Path, server="c_eve_sharedcache_tq_tranquility",
          profile="settings_Default", files=("core_char_98123456.dat",)):
    target = root / server / profile
    target.mkdir(parents=True)
    for name in files:
        (target / name).write_bytes(b"x")
    return target


@pytest.mark.parametrize("name,expected", [
    ("core_char_98123456.dat", "character"),
    ("core_user_12345.dat", "account"),
    ("core_char_abc.dat", None),
    ("core_char_.dat", None),
    ("core_char_98123456.txt", None),
    ("settings.dat", None),
    ("core_char_٣.dat", None),
])
def test_file_kind(name, expected):
    """The id must be ASCII digits. isdigit() alone accepts Arabic-Indic
    numerals, which cannot be a character id."""
    assert tree.file_kind(Path("/x") / name) == expected


def test_discover_finds_servers_profiles_and_files(tmp_path):
    build(tmp_path, files=("core_char_98123456.dat", "core_user_12345.dat"))
    found = tree.discover(tmp_path)
    assert [s.key for s in found.servers] == ["tranquility"]
    assert [p.name for p in found.profiles] == ["Default"]
    assert [c.file_id for c in found.characters] == ["98123456"]
    assert [a.file_id for a in found.accounts] == ["12345"]


def test_discover_ignores_files_with_non_numeric_ids(tmp_path):
    build(tmp_path, files=("core_char_98123456.dat", "core_char_abc.dat"))
    found = tree.discover(tmp_path)
    assert [c.file_id for c in found.characters] == ["98123456"]


def test_unknown_server_folder_keeps_its_raw_name(tmp_path):
    build(tmp_path, server="c_eve_sharedcache_xx_newshard")
    found = tree.discover(tmp_path)
    assert found.servers[0].name == "c_eve_sharedcache_xx_newshard"
    assert found.servers[0].key == "c_eve_sharedcache_xx_newshard"


def test_tranquility_sorts_first(tmp_path):
    build(tmp_path, server="c_eve_sharedcache_sisi_singularity")
    build(tmp_path, server="c_eve_sharedcache_tq_tranquility")
    found = tree.discover(tmp_path)
    assert found.servers[0].key == "tranquility"


def test_default_profile_sorts_first(tmp_path):
    build(tmp_path, profile="settings_Alt")
    build(tmp_path, profile="settings_Default")
    found = tree.discover(tmp_path)
    assert found.profiles[0].name == "Default"


def test_normalize_selection_heals_a_root_pointed_at_a_profile(tmp_path):
    profile = build(tmp_path)
    root, server, selected = tree.normalize_selection(profile, None, None)
    assert root == tmp_path
    assert server == profile.parent
    assert selected == profile


def test_normalize_selection_heals_a_root_pointed_at_a_server(tmp_path):
    profile = build(tmp_path)
    root, server, selected = tree.normalize_selection(profile.parent, None, None)
    assert root == tmp_path
    assert server == profile.parent


def test_unreadable_root_is_reported_not_silently_empty(tmp_path):
    def boom(_path):
        raise PermissionError(13, "denied")

    monkey = pytest.MonkeyPatch()
    monkey.setattr(tree.os, "scandir", boom)
    try:
        found = tree.discover(tmp_path)
    finally:
        monkey.undo()
    assert found.unreadable is True and found.servers == []


def test_missing_root_is_not_unreadable(tmp_path):
    found = tree.discover(tmp_path / "absent")
    assert found.unreadable is False and found.servers == []


def test_is_under_accepts_a_child(tmp_path):
    child = tmp_path / "a" / "b"
    child.mkdir(parents=True)
    assert tree.is_under(tmp_path, child) is True


def test_is_under_rejects_a_parent_escape(tmp_path):
    assert tree.is_under(tmp_path / "root", tmp_path / "root" / ".." / "other") is False


def test_is_under_rejects_a_sibling_with_a_shared_prefix(tmp_path):
    """C:\\EVE-evil must not read as being under C:\\EVE."""
    (tmp_path / "EVE").mkdir()
    (tmp_path / "EVE-evil").mkdir()
    assert tree.is_under(tmp_path / "EVE", tmp_path / "EVE-evil") is False


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_is_under_rejects_a_symlink_escaping_the_root(tmp_path):
    """A lexical check cannot see this. Windows junctions behave the same
    way and are something mklink /J creates by accident."""
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    assert tree.is_under(root, root / "link") is False


def test_require_under_raises_for_an_escape(tmp_path):
    with pytest.raises(ValueError):
        tree.require_under(tmp_path, tmp_path / ".." / "elsewhere")


def test_require_under_enforces_the_suffix(tmp_path):
    target = tmp_path / "core_char_1.txt"
    target.write_bytes(b"x")
    with pytest.raises(ValueError):
        tree.require_under(tmp_path, target, suffix=".dat")
