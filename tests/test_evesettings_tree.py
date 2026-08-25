"""Discovery and containment. Every case builds a fake EVE tree in tmp_path,
so the whole module tests on Linux."""

import os
from pathlib import Path

import pytest

from obs_youtube_uploader.evesettings import tree


def build(
    root: Path,
    server="c_eve_sharedcache_tq_tranquility",
    profile="settings_Default",
    files=("core_char_98123456.dat",),
):
    target = root / server / profile
    target.mkdir(parents=True)
    for name in files:
        (target / name).write_bytes(b"x")
    return target


@pytest.mark.parametrize(
    "name,expected",
    [
        ("core_char_98123456.dat", "character"),
        ("core_user_12345.dat", "account"),
        ("core_char_abc.dat", None),
        ("core_char_.dat", None),
        ("core_char_98123456.txt", None),
        ("settings.dat", None),
        ("core_char_٣.dat", None),
    ],
)
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
    root, server, _selected = tree.normalize_selection(profile.parent, None, None)
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


def test_a_root_with_implausibly_many_children_is_refused_not_probed(
    tmp_path, monkeypatch
):
    """Every child directory of the root costs a scandir apiece to probe.

    A mis-picked root like C:\\Users\\me blocks the bridge thread for as
    long as that takes. Refused with a reason, rather than probed slowly
    or silently truncated -- "that is not an EVE folder" and "there is
    nothing in it" are different answers.
    """
    root = tmp_path / "wide"
    root.mkdir()
    for n in range(tree.MAX_ROOT_CHILDREN + 1):
        (root / f"dir{n:03d}").mkdir()
    # A real settings set is in there; it is still not probed for.
    (root / "dir000" / "settings_Default").mkdir()

    probed = []
    real = tree._has_profiles
    monkeypatch.setattr(
        tree, "_has_profiles", lambda p: probed.append(str(p)) or real(p)
    )

    found = tree.discover(root)
    assert found.too_broad is True
    assert found.servers == []
    # The root itself is probed (normalize_selection, then _servers_in);
    # not one of its 65 children is.
    assert set(probed) == {str(root)}


def test_a_root_at_the_cap_is_still_probed(tmp_path):
    """The cap must be generous, not eager: refusing a plausible root is
    worse than the scandirs it saves."""
    root = tmp_path / "eve"
    root.mkdir()
    for n in range(tree.MAX_ROOT_CHILDREN):
        (root / f"dir{n:03d}").mkdir()
    (root / "dir000" / "settings_Default").mkdir()
    found = tree.discover(root)
    assert found.too_broad is False
    assert [s.path for s in found.servers] == [root / "dir000"]


def test_has_profiles_stops_at_the_first_match(tmp_path, monkeypatch):
    """Lazy, not materialised: the old code read every entry with list()
    before testing any of them, so probing one wrong directory could read
    hundreds of thousands of names to answer a yes/no question.

    Driven through a fake scandir rather than real files, because real
    scandir order is arbitrary and "did it stop early" is not observable
    from the answer alone.
    """
    server = tmp_path / "server"
    server.mkdir()
    (server / "settings_Default").mkdir()

    consumed = []

    class Entry:
        def __init__(self, name):
            self.path = str(server / name)

        def is_dir(self):
            return True

    class FakeScan:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def __iter__(self):
            for name in ("settings_Default", "second", "third"):
                consumed.append(name)
                yield Entry(name)

    monkeypatch.setattr(tree.os, "scandir", lambda _p: FakeScan())
    assert tree._has_profiles(server) == tree.Probe(True)
    assert consumed == ["settings_Default"], "it read past the first match"


def test_a_truncated_probe_says_so_rather_than_answering_no(tmp_path, monkeypatch):
    """Returning a bare False here would make a settings set vanish from
    the dropdown with nothing said -- telling the user they have no
    settings sets for a folder that plainly has them, which is the defect
    the design names as TriffView's."""
    monkeypatch.setattr(tree, "MAX_PROBE_ENTRIES", 0)
    server = tmp_path / "server"
    server.mkdir()
    (server / "settings_Default").mkdir()
    assert tree._has_profiles(server) == tree.Probe(False, truncated=True)


def test_a_truncated_child_probe_reaches_the_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(tree, "MAX_PROBE_ENTRIES", 0)
    root = tmp_path / "eve"
    (root / "server_tranquility" / "settings_Default").mkdir(parents=True)
    assert tree.discover(root).too_broad is True


def test_a_denied_probe_says_denied_rather_than_answering_no(tmp_path):
    server = tmp_path / "server"
    server.mkdir()
    server.chmod(0o000)
    try:
        try:
            os.scandir(str(server)).close()
        except PermissionError:
            pass
        else:  # pragma: no cover - root, or a filesystem without modes
            pytest.skip("this user can read a mode-000 directory")
        assert tree._has_profiles(server) == tree.Probe(False, denied=True)
    finally:
        server.chmod(0o700)


def test_a_denied_child_marks_the_tree_unreadable(tmp_path):
    """An EVE install directory with restrictive ACLs must not silently
    disappear from the server list."""
    root = tmp_path / "eve"
    root.mkdir()
    locked = root / "server_locked"
    locked.mkdir()
    locked.chmod(0o000)
    try:
        try:
            os.scandir(str(locked)).close()
        except PermissionError:
            pass
        else:  # pragma: no cover - root, or a filesystem without modes
            pytest.skip("this user can read a mode-000 directory")
        assert tree.discover(root).unreadable is True
    finally:
        locked.chmod(0o700)


def test_a_missing_directory_is_not_denied(tmp_path):
    """The same distinction _scan draws: absent is not forbidden."""
    assert tree._has_profiles(tmp_path / "nope") == tree.Probe(False)


def test_default_root_uses_localappdata_when_windows_sets_it(monkeypatch):
    """The Windows branch: %LOCALAPPDATA%\\CCP\\EVE is where EVE puts it,
    and this is the path the folder picker is seeded with on first run."""
    monkeypatch.setenv("LOCALAPPDATA", str(Path("C:/Users/me/AppData/Local")))
    assert tree.default_root() == Path("C:/Users/me/AppData/Local/CCP/EVE")


def test_default_root_falls_back_when_localappdata_is_absent(monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert tree.default_root() == Path.home() / ".local/share/CCP/EVE"


def test_default_root_ignores_an_empty_localappdata(monkeypatch):
    """An empty string is falsy, so Path("")/"CCP" would resolve to a
    relative CCP/EVE beside the working directory."""
    monkeypatch.setenv("LOCALAPPDATA", "")
    assert tree.default_root() == Path.home() / ".local/share/CCP/EVE"


def test_the_cap_does_not_cancel_the_self_healing_root(tmp_path):
    """Picking the folder EVE itself shows you lands on a server or
    settings_* directory, and normalize_selection lifts the root ABOVE it.
    If that parent is something wide -- C:/Games, C:/Users/me -- the cap
    would refuse to probe it and the user gets an empty tree plus a
    warning about a folder they never chose, from picking a folder that
    visibly contains their settings. Re-picking cannot escape it, because
    normalize_selection lifts to the same place every time.
    """
    games = tmp_path / "Games"
    picked = games / "eve-tq"
    (picked / "settings_Default").mkdir(parents=True)
    (picked / "settings_Default" / "core_char_98123456.dat").touch()
    for n in range(tree.MAX_ROOT_CHILDREN + 1):
        (games / f"other{n:03d}").mkdir()

    found = tree.discover(picked)
    assert found.root == games, "normalize_selection still lifts the root"
    # The selection is rescued...
    assert [s.path for s in found.servers] == [picked]
    assert found.profile == picked / "settings_Default"
    assert [f.file_id for f in found.characters] == ["98123456"]
    # ...and the page is still told the wider list was not enumerated.
    assert found.too_broad is True


def test_the_rescued_server_must_still_be_a_child_of_the_root(tmp_path):
    """`keep` comes from a stored selection and could point anywhere; it
    is not a way around containment."""
    games = tmp_path / "Games"
    games.mkdir()
    for n in range(tree.MAX_ROOT_CHILDREN + 1):
        (games / f"other{n:03d}").mkdir()
    elsewhere = tmp_path / "Elsewhere" / "eve-tq"
    (elsewhere / "settings_Default").mkdir(parents=True)

    servers, _unreadable, too_broad = tree._servers_in(games, keep=elsewhere)
    assert servers == [] and too_broad is True


def test_a_rescued_keep_without_profiles_is_not_invented(tmp_path):
    games = tmp_path / "Games"
    games.mkdir()
    empty = games / "not-eve"
    empty.mkdir()
    for n in range(tree.MAX_ROOT_CHILDREN + 1):
        (games / f"other{n:03d}").mkdir()
    servers, _unreadable, _too_broad = tree._servers_in(games, keep=empty)
    assert servers == []


def test_a_symlinked_keep_does_not_escape_the_root(tmp_path):
    """The rescued-server path is a containment check like any other, and
    this module's rule is that a lexical compare cannot see a symlink or a
    Windows junction. A link sitting directly under the root, pointing at
    a settings tree outside it, passes `keep.parent == root` lexically."""
    games = tmp_path / "Games"
    games.mkdir()
    for n in range(tree.MAX_ROOT_CHILDREN + 1):
        (games / f"other{n:03d}").mkdir()
    outside = tmp_path / "Elsewhere" / "eve-tq"
    (outside / "settings_Default").mkdir(parents=True)

    link = games / "looks-local"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):  # pragma: no cover - no symlinks
        pytest.skip("this platform/user cannot create symlinks")

    # Lexically it is a direct child of the root; really it is not.
    assert link.parent == games
    servers, _unreadable, _too_broad = tree._servers_in(games, keep=link)
    assert servers == [], "a symlink walked the selection outside the root"
