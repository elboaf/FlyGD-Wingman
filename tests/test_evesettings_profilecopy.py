"""Request authority, staging, and publication for whole-profile creation.

Every case builds a real discovered tree in tmp_path, so the module tests
fully on Linux; Windows-only junction tests are skipped where noted.
"""

import os
import subprocess
from pathlib import Path

import pytest

from wingman.evesettings import backup, profilecopy, tree


def _make_junction(link: Path, target: Path) -> None:
    """Create a real Windows directory junction via `mklink /J`.

    Junctions, unlike symbolic links, need neither
    SeCreateSymbolicLinkPrivilege nor Developer Mode -- an ordinary,
    unelevated user can create one, which is what makes a genuine
    reparse-point test usable on a stock CI runner rather than only on a
    developer's elevated shell.

    A failure here fails the test rather than skipping it. `mklink /J`
    working is the normal Windows case, so a silent skip would quietly
    retire the only coverage of IO_REPARSE_TAG_MOUNT_POINT -- the tag
    `Path.is_symlink()` does not report and `_is_reparse_point` exists for.
    cmd's own message is surfaced so a genuinely unsupported volume (a
    non-NTFS temp drive, say) names itself instead of arriving as a bare
    non-zero exit code.
    """
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"mklink /J {link} {target} failed with {result.returncode}: "
            f"{(result.stderr or result.stdout).strip()}"
        )


@pytest.fixture
def discovered_tree(tmp_path):
    server = tmp_path / "EVE" / "server_tranquility"
    profile = server / "settings_Default"
    profile.mkdir(parents=True)
    return tree.discover(tmp_path / "EVE", server, profile)


@pytest.fixture
def copy_plan(tmp_path):
    root = tmp_path / "EVE"
    server = root / "server_tranquility"
    source = server / "settings_Default"
    source.mkdir(parents=True)
    (source / "core_char_1.dat").write_bytes(b"character")
    (source / "core_user_2.dat").write_bytes(b"account")
    (source / "notes.txt").write_bytes(b"not a recognized settings file")
    destination = server / "settings_Fleet"
    return profilecopy.ProfileCopyPlan(
        root=root,
        server=server,
        source=source,
        destination=destination,
        source_name="Default",
        destination_name="Fleet",
        mode="new",
    )


@pytest.fixture
def staged_copy(copy_plan):
    with profilecopy.stage_copy(copy_plan) as staged:
        yield staged


@pytest.fixture
def replace_plan(tmp_path):
    root = tmp_path / "EVE"
    server = root / "server_tranquility"
    source = server / "settings_Default"
    source.mkdir(parents=True)
    (source / "core_char_1.dat").write_bytes(b"A")
    (source / "core_user_2.dat").write_bytes(b"B")
    destination = server / "settings_Fleet"
    destination.mkdir(parents=True)
    (destination / "core_char_1.dat").write_bytes(b"old")
    (destination / "core_char_9.dat").write_bytes(b"remove")
    (destination / "notes.txt").write_bytes(b"keep")
    (destination / "extras").mkdir()
    (destination / "extras" / "thing.txt").write_bytes(b"keep")
    return profilecopy.ProfileCopyPlan(
        root=root,
        server=server,
        source=source,
        destination=destination,
        source_name="Default",
        destination_name="Fleet",
        mode="replace",
    )


# ----- validate_friendly_name --------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "",
        "settings_Fleet",
        ".",
        "..",
        "CON",
        "con.txt",
        "bad/name",
        "bad\\name",
        "bad:name",
        "bad.",
        "x" * 81,
        "bad\x00name",
    ],
)
def test_new_profile_name_is_rejected(value, discovered_tree):
    with pytest.raises(ValueError):
        profilecopy.validate_friendly_name(value, discovered_tree.profiles)


def test_new_profile_name_is_trimmed(discovered_tree):
    assert (
        profilecopy.validate_friendly_name("  Fleet UI  ", discovered_tree.profiles)
        == "Fleet UI"
    )


def test_new_profile_name_rejects_a_case_insensitive_collision(discovered_tree):
    with pytest.raises(ValueError, match="already exists"):
        profilecopy.validate_friendly_name("default", discovered_tree.profiles)


def test_new_profile_name_accepts_a_non_colliding_name(discovered_tree):
    assert (
        profilecopy.validate_friendly_name("Fleet", discovered_tree.profiles) == "Fleet"
    )


def test_new_profile_name_is_not_text_is_rejected(discovered_tree):
    with pytest.raises(ValueError):
        profilecopy.validate_friendly_name(None, discovered_tree.profiles)


# ----- prepare_copy: request authority -------------------------------------


def test_prepare_copy_rejects_a_stale_source(discovered_tree):
    with pytest.raises(ValueError, match="selected profile changed"):
        profilecopy.prepare_copy(discovered_tree, "settings_Old", "new", "Fleet")


def test_prepare_copy_rejects_cross_server_destination(tmp_path):
    root = tmp_path / "EVE"
    source = root / "server_tranquility" / "settings_Default"
    other = root / "server_singularity" / "settings_Other"
    source.mkdir(parents=True)
    other.mkdir(parents=True)
    found = tree.discover(root, source.parent, source)
    with pytest.raises(ValueError, match="selected server"):
        profilecopy.prepare_copy(found, str(source), "replace", str(other))


def test_prepare_copy_accepts_a_matching_source_for_a_new_profile(discovered_tree):
    plan = profilecopy.prepare_copy(
        discovered_tree, str(discovered_tree.profile), "new", "Fleet"
    )
    assert plan.mode == "new"
    assert plan.source == discovered_tree.profile
    assert plan.server == discovered_tree.server
    assert plan.destination == discovered_tree.server / "settings_Fleet"
    assert plan.source_name == "Default"
    assert plan.destination_name == "Fleet"


def test_prepare_copy_accepts_a_matching_source_and_destination_for_replace(tmp_path):
    root = tmp_path / "EVE"
    server = root / "server_tranquility"
    source = server / "settings_Default"
    destination = server / "settings_Alt"
    source.mkdir(parents=True)
    destination.mkdir(parents=True)
    found = tree.discover(root, server, source)
    plan = profilecopy.prepare_copy(found, str(source), "replace", str(destination))
    assert plan.mode == "replace"
    assert plan.destination == destination
    assert plan.destination_name == "Alt"


def test_prepare_copy_rejects_source_equals_destination(tmp_path):
    root = tmp_path / "EVE"
    server = root / "server_tranquility"
    source = server / "settings_Default"
    source.mkdir(parents=True)
    found = tree.discover(root, server, source)
    with pytest.raises(ValueError, match="same profile"):
        profilecopy.prepare_copy(found, str(source), "replace", str(source))


def test_prepare_copy_rejects_an_unknown_mode(discovered_tree):
    with pytest.raises(ValueError, match="mode"):
        profilecopy.prepare_copy(
            discovered_tree, str(discovered_tree.profile), "delete", "Fleet"
        )


def test_prepare_copy_rejects_a_fabricated_destination(tmp_path):
    root = tmp_path / "EVE"
    server = root / "server_tranquility"
    source = server / "settings_Default"
    source.mkdir(parents=True)
    found = tree.discover(root, server, source)
    fabricated = server / "settings_Nonexistent"
    with pytest.raises(ValueError, match="selected server"):
        profilecopy.prepare_copy(found, str(source), "replace", str(fabricated))


def test_prepare_copy_permits_a_root_that_directly_holds_profiles(tmp_path):
    """found.server == found.root is permitted exactly when discovery
    confirms the root directly contains profiles.

    tree.discover() itself never reaches server == root through its own
    normalize_selection self-healing (a root that directly holds profiles
    is always lifted one level up first), so this constructs the Tree
    directly -- prepare_copy validates whatever Tree it is given,
    independent of how it was produced.
    """
    root = tmp_path / "EVE"
    source = root / "settings_Default"
    source.mkdir(parents=True)
    profile = tree.Profile(path=source, name="Default", file_count=0, modified=0.0)
    found = tree.Tree(root=root, server=root, profile=source, profiles=[profile])
    plan = profilecopy.prepare_copy(found, str(source), "new", "Fleet")
    assert plan.destination == root / "settings_Fleet"


def test_prepare_copy_rejects_a_bare_root_without_confirmed_profiles(tmp_path):
    """server == root is not, by itself, a license to treat root as a
    server -- only discover()'s own confirmation (a populated profiles
    list) is."""
    root = tmp_path / "EVE"
    root.mkdir()
    source = root / "settings_Default"
    found = tree.Tree(root=root, server=root, profile=source, profiles=[])
    with pytest.raises(ValueError, match="selected server"):
        profilecopy.prepare_copy(found, str(source), "new", "Fleet")


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX symlink semantics used to fabricate the escape"
)
def test_prepare_copy_rejects_a_server_junction_outside_the_root(tmp_path):
    """A lexical check cannot see this: `server` sits directly under
    `root` on paper while its target -- and every profile discovered
    beneath it -- resolves somewhere else entirely."""
    root = tmp_path / "EVE"
    root.mkdir()
    outside = tmp_path / "outside-server"
    outside_profile = outside / "settings_Default"
    outside_profile.mkdir(parents=True)
    link = root / "server_tranquility"
    link.symlink_to(outside, target_is_directory=True)

    found = tree.discover(root)
    assert found.server == link, "the escape must reach prepare_copy, not discover()"
    with pytest.raises(ValueError):
        profilecopy.prepare_copy(found, str(found.profile), "new", "Fleet")


@pytest.mark.skipif(os.name != "nt", reason="requires a real Windows junction")
def test_prepare_copy_rejects_a_real_windows_server_junction_outside_the_root(tmp_path):
    """The portable POSIX symlink test above proves the LOGIC; this proves
    the same refusal against an actual `mklink /J` junction, which is what
    ships on a real Windows install and is not detected by
    `Path.is_symlink()` at all."""
    root = tmp_path / "EVE"
    root.mkdir()
    outside = tmp_path / "outside-server"
    outside_profile = outside / "settings_Default"
    outside_profile.mkdir(parents=True)
    link = root / "server_tranquility"
    _make_junction(link, outside)

    found = tree.discover(root)
    assert found.server == link, "the escape must reach prepare_copy, not discover()"
    with pytest.raises(ValueError):
        profilecopy.prepare_copy(found, str(found.profile), "new", "Fleet")


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX symlink semantics used to fabricate the escape"
)
def test_prepare_copy_rejects_a_profile_junction_outside_the_server(tmp_path):
    root = tmp_path / "EVE"
    server = root / "server_tranquility"
    server.mkdir(parents=True)
    outside = tmp_path / "outside-profile"
    outside.mkdir()
    (outside / "core_char_1.dat").write_bytes(b"x")
    link = server / "settings_Default"
    link.symlink_to(outside, target_is_directory=True)

    found = tree.discover(root, server, link)
    assert found.profile == link, "the escape must reach prepare_copy, not discover()"
    with pytest.raises(ValueError):
        profilecopy.prepare_copy(found, str(link), "new", "Fleet")


@pytest.mark.skipif(os.name != "nt", reason="requires a real Windows junction")
def test_prepare_copy_rejects_a_real_windows_profile_junction_outside_the_server(
    tmp_path,
):
    root = tmp_path / "EVE"
    server = root / "server_tranquility"
    server.mkdir(parents=True)
    outside = tmp_path / "outside-profile"
    outside.mkdir()
    (outside / "core_char_1.dat").write_bytes(b"x")
    link = server / "settings_Default"
    _make_junction(link, outside)

    found = tree.discover(root, server, link)
    assert found.profile == link, "the escape must reach prepare_copy, not discover()"
    with pytest.raises(ValueError):
        profilecopy.prepare_copy(found, str(link), "new", "Fleet")


# ----- staging and creation -------------------------------------------------


def test_stage_contains_only_byte_identical_recognized_files(copy_plan):
    with profilecopy.stage_copy(copy_plan) as staged:
        assert staged.members == ("core_char_1.dat", "core_user_2.dat")
        assert (staged.path / "core_char_1.dat").read_bytes() == b"character"
        assert (staged.path / "core_user_2.dat").read_bytes() == b"account"
        assert not (staged.path / "notes.txt").exists()


def test_stage_copy_removes_its_directory_on_exit(copy_plan):
    with profilecopy.stage_copy(copy_plan) as staged:
        stage_path = staged.path
        assert stage_path.is_dir()
    assert not stage_path.exists()


def test_stage_copy_names_its_stage_with_the_reserved_prefix(copy_plan):
    with profilecopy.stage_copy(copy_plan) as staged:
        assert staged.path.name.startswith(profilecopy.STAGE_PREFIX)
        assert staged.path.name.endswith(profilecopy.STAGE_SUFFIX)
        assert staged.path.parent == copy_plan.server


def test_stage_is_never_discovered_as_a_profile(copy_plan):
    with profilecopy.stage_copy(copy_plan):
        found = tree.discover(copy_plan.root, copy_plan.server, copy_plan.source)
        assert all(
            not p.path.name.startswith(profilecopy.STAGE_PREFIX) for p in found.profiles
        )


def test_stage_copy_cleans_up_a_failed_copy(copy_plan, monkeypatch):
    def boom(source, target):
        raise OSError("disk full")

    monkeypatch.setattr(profilecopy.atomicio, "copy_atomic", boom)
    with pytest.raises(OSError), profilecopy.stage_copy(copy_plan):
        pass  # pragma: no cover - never reached
    leftover = [
        p
        for p in copy_plan.server.iterdir()
        if p.name.startswith(profilecopy.STAGE_PREFIX)
    ]
    assert leftover == []


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX symlink semantics used to fabricate the escape"
)
def test_stage_copy_rejects_a_recognized_file_link_outside_the_profile(tmp_path):
    """Full hierarchy validation refuses the whole copy over one escaping
    file -- it does not silently clone around it and publish a partial
    profile missing exactly the file an attacker or a stray link chose."""
    root = tmp_path / "EVE"
    server = root / "server_tranquility"
    source = server / "settings_Default"
    source.mkdir(parents=True)
    (source / "core_char_1.dat").write_bytes(b"character")
    outside = tmp_path / "secret_core_user_9.dat"
    outside.write_bytes(b"exfiltrated")
    (source / "core_user_9.dat").symlink_to(outside)

    plan = profilecopy.ProfileCopyPlan(
        root=root,
        server=server,
        source=source,
        destination=server / "settings_Fleet",
        source_name="Default",
        destination_name="Fleet",
        mode="new",
    )
    with pytest.raises(ValueError), profilecopy.stage_copy(plan):
        pass  # pragma: no cover - never reached
    # Refused before publication, and nothing partial is left behind.
    leftover = [
        p for p in server.iterdir() if p.name.startswith(profilecopy.STAGE_PREFIX)
    ]
    assert leftover == []


def test_recognized_members_refuses_when_the_source_cannot_be_read(
    tmp_path, monkeypatch
):
    """An unreadable or vanished source must not read as "no recognized
    files" -- that would let stage_copy silently publish an EMPTY profile
    instead of failing loudly."""
    profile = tmp_path / "settings_Default"
    profile.mkdir()

    def boom(_path):
        raise PermissionError(13, "denied")

    monkeypatch.setattr(profilecopy.os, "scandir", boom)
    with pytest.raises(OSError):
        profilecopy._recognized_members(profile)


def test_publish_new_renames_the_stage_into_place(copy_plan):
    with profilecopy.stage_copy(copy_plan) as staged:
        published = profilecopy.publish_new(staged)
    assert published == copy_plan.destination
    assert (copy_plan.destination / "core_char_1.dat").read_bytes() == b"character"
    assert not staged.path.exists()


def test_publish_new_refuses_a_destination_race(staged_copy):
    staged_copy.plan.destination.mkdir()
    with pytest.raises(FileExistsError):
        profilecopy.publish_new(staged_copy)
    assert list(staged_copy.plan.destination.iterdir()) == []


# ----- publish_replacement: exact replacement and rollback -----------------


def test_publish_replacement_replaces_recognized_files_and_keeps_the_rest(
    replace_plan,
):
    """The concrete before/after transition from the design doc: recognized
    source files land exactly as the source has them, a recognized
    destination-only file is removed, and unrelated entries -- a plain file
    and a subdirectory -- are untouched."""
    destination = replace_plan.destination
    with profilecopy.stage_copy(replace_plan) as staged:
        published = profilecopy.publish_replacement(
            staged, rollback=lambda: pytest.fail("must not roll back on success")
        )
    assert published == destination
    assert (destination / "core_char_1.dat").read_bytes() == b"A"
    assert (destination / "core_user_2.dat").read_bytes() == b"B"
    assert not (destination / "core_char_9.dat").exists()
    assert (destination / "notes.txt").read_bytes() == b"keep"
    assert (destination / "extras" / "thing.txt").read_bytes() == b"keep"


def test_publish_replacement_rolls_back_the_whole_before_set_on_a_caught_failure(
    replace_plan, tmp_path, monkeypatch
):
    """A caller takes a durable backup of the destination before staging and
    publishing; a failure partway through publication (after one recognized
    file has already been replaced) must restore that entire before-set, not
    merely undo the one replacement that happened to land."""
    destination = replace_plan.destination
    store = tmp_path / "backups"
    made = backup.create_profile_backup(store, destination, origin="manual")

    calls = {"n": 0}
    real_copy_atomic = profilecopy.atomicio.copy_atomic

    def flaky_after_one(source, target, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk full")
        return real_copy_atomic(source, target, *args, **kwargs)

    def rollback():
        backup.restore(store, made, replace_plan.root, backup_current=False)

    with profilecopy.stage_copy(replace_plan) as staged:
        # Patched only now: stage_copy's own staging copy must run for
        # real, so the failure injected below lands in publish_replacement,
        # not while the stage is still being built.
        monkeypatch.setattr(profilecopy.atomicio, "copy_atomic", flaky_after_one)
        with pytest.raises(profilecopy.ReplacementFailed) as excinfo:
            profilecopy.publish_replacement(staged, rollback=rollback)

    assert isinstance(excinfo.value.publication_error, OSError)
    assert excinfo.value.rollback_error is None
    assert excinfo.value.destination_restored
    assert (destination / "core_char_1.dat").read_bytes() == b"old"
    assert (destination / "core_char_9.dat").read_bytes() == b"remove"
    assert (destination / "notes.txt").read_bytes() == b"keep"
    assert (destination / "extras" / "thing.txt").read_bytes() == b"keep"


def test_publish_replacement_records_a_rollback_that_also_failed(
    replace_plan, monkeypatch
):
    def boom(source, target, *args, **kwargs):
        raise OSError("disk full")

    def failing_rollback():
        raise RuntimeError("rollback also failed")

    with profilecopy.stage_copy(replace_plan) as staged:
        monkeypatch.setattr(profilecopy.atomicio, "copy_atomic", boom)
        with pytest.raises(profilecopy.ReplacementFailed) as excinfo:
            profilecopy.publish_replacement(staged, rollback=failing_rollback)

    assert isinstance(excinfo.value.publication_error, OSError)
    assert isinstance(excinfo.value.rollback_error, RuntimeError)
    assert not excinfo.value.destination_restored


def test_publish_replacement_does_not_roll_back_on_system_exit(
    replace_plan, monkeypatch
):
    """SystemExit (and any other BaseException) is the caller's own
    interruption, not a publication failure -- rollback must never run
    behind it."""

    def boom(source, target, *args, **kwargs):
        raise SystemExit(1)

    rollback_calls = []

    with profilecopy.stage_copy(replace_plan) as staged:
        monkeypatch.setattr(profilecopy.atomicio, "copy_atomic", boom)
        with pytest.raises(SystemExit):
            profilecopy.publish_replacement(
                staged, rollback=lambda: rollback_calls.append(1)
            )

    assert rollback_calls == []


# ----- abandoned-stage cleanup ----------------------------------------------


def test_cleanup_removes_an_ordinary_abandoned_stage(copy_plan):
    server = copy_plan.server
    abandoned = server / f"{profilecopy.STAGE_PREFIX}deadbeef{profilecopy.STAGE_SUFFIX}"
    abandoned.mkdir()
    (abandoned / "core_char_1.dat").write_bytes(b"leftover")

    profilecopy.cleanup_abandoned_stages(server)

    assert not abandoned.exists()


def test_cleanup_leaves_an_unrelated_directory_alone(copy_plan):
    server = copy_plan.server
    unrelated = server / "not-a-stage"
    unrelated.mkdir()

    profilecopy.cleanup_abandoned_stages(server)

    assert unrelated.exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")
def test_cleanup_refuses_a_stage_shaped_symlink_rather_than_following_it(copy_plan):
    server = copy_plan.server
    outside = server.parent / "outside-real-profile"
    outside.mkdir()
    (outside / "keepme.dat").write_bytes(b"do not delete me")
    link = server / f"{profilecopy.STAGE_PREFIX}fakeuuid{profilecopy.STAGE_SUFFIX}"
    link.symlink_to(outside, target_is_directory=True)

    with pytest.raises(OSError):
        profilecopy.cleanup_abandoned_stages(server)

    assert outside.exists()
    assert (outside / "keepme.dat").exists()


@pytest.mark.skipif(os.name != "nt", reason="requires a real Windows junction")
def test_cleanup_refuses_a_stage_shaped_windows_junction_rather_than_following_it(
    tmp_path,
):
    server = tmp_path / "server_tranquility"
    server.mkdir()
    outside = tmp_path / "outside-real-profile"
    outside.mkdir()
    (outside / "keepme.dat").write_bytes(b"do not delete me")
    link = server / f"{profilecopy.STAGE_PREFIX}fakeuuid{profilecopy.STAGE_SUFFIX}"
    _make_junction(link, outside)

    with pytest.raises(OSError):
        profilecopy.cleanup_abandoned_stages(server)

    assert outside.exists()
    assert (outside / "keepme.dat").exists()


def test_cleanup_refuses_when_the_server_cannot_be_listed(tmp_path, monkeypatch):
    server = tmp_path / "server_tranquility"
    server.mkdir()

    def boom(_path):
        raise PermissionError(13, "denied")

    monkeypatch.setattr(profilecopy.os, "scandir", boom)
    with pytest.raises(OSError):
        profilecopy.cleanup_abandoned_stages(server)


def test_stage_copy_cleans_up_an_abandoned_stage_before_staging(copy_plan):
    server = copy_plan.server
    abandoned = server / f"{profilecopy.STAGE_PREFIX}stale{profilecopy.STAGE_SUFFIX}"
    abandoned.mkdir()

    with profilecopy.stage_copy(copy_plan):
        assert not abandoned.exists()
