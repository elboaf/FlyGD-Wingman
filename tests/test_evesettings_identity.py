import os

import pytest

from wingman.evesettings import identity, tree


def build(tmp_path):
    profile = tmp_path / "EVE" / "server_tranquility" / "settings_Default"
    profile.mkdir(parents=True)
    for name in ("core_user_10.dat", "core_char_20.dat"):
        (profile / name).write_bytes(name.encode())
    return tree.discover(tmp_path / "EVE")


def test_account_identity_prefers_alias_and_keeps_confirmed_characters_secondary():
    got = identity.account_identity(
        "10",
        {"10": "Main multibox"},
        {"10": ["20", "21", "22"]},
        lambda ident: {"20": "Aiga", "21": "Beta", "22": "Gamma"}[ident],
    )
    assert got == {
        "primary": "Main multibox",
        "secondary": "Aiga + 2 · ID 10",
        "option": "Main multibox · Aiga + 2 · ID 10",
    }


def test_account_identity_degrades_without_inventing_a_roster():
    assert identity.account_identity("10", {}, {}, lambda _ident: "unused") == {
        "primary": "Unidentified",
        "secondary": "ID 10",
        "option": "Unidentified · ID 10",
    }


def test_one_changed_pair_is_reported(tmp_path):
    found = build(tmp_path)
    before = identity.take_snapshot(found)
    account = found.accounts[0].path
    character = found.characters[0].path
    account.write_bytes(b"changed account")
    character.write_bytes(b"changed character")

    changed = identity.changes_since(before, tree.discover(tmp_path / "EVE"))

    assert changed.accounts == ("10",)
    assert changed.characters == ("20",)
    assert changed.invalidated is False


def test_added_files_count_as_changed(tmp_path):
    found = build(tmp_path)
    before = identity.take_snapshot(found)
    profile = found.profile
    (profile / "core_char_21.dat").write_bytes(b"new")

    changed = identity.changes_since(before, tree.discover(tmp_path / "EVE"))

    assert changed.characters == ("21",)


def test_removed_file_invalidates_the_snapshot(tmp_path):
    found = build(tmp_path)
    before = identity.take_snapshot(found)
    found.characters[0].path.unlink()

    assert identity.changes_since(before, tree.discover(tmp_path / "EVE")).invalidated


def test_changed_profile_invalidates_the_snapshot(tmp_path):
    found = build(tmp_path)
    before = identity.take_snapshot(found)
    other = found.server / "settings_Alt"
    other.mkdir()
    (other / "core_user_10.dat").write_bytes(b"x")

    changed = identity.changes_since(
        before, tree.discover(tmp_path / "EVE", found.server, other)
    )

    assert changed.invalidated


def test_unreadable_stat_invalidates_comparison(tmp_path, monkeypatch):
    found = build(tmp_path)
    before = identity.take_snapshot(found)
    original = os.stat

    def fail(path, *args, **kwargs):
        if str(path).endswith("core_char_20.dat"):
            raise PermissionError("denied")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(identity.Path, "stat", fail)
    assert identity.changes_since(before, found).invalidated


def test_snapshot_requires_a_selected_profile():
    with pytest.raises(ValueError, match="Choose an EVE settings profile"):
        identity.take_snapshot(tree.Tree())
