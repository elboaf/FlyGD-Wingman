"""The bridge is tested headless through FakeWindow (tests/fakes.py)."""

import os
import threading
from pathlib import Path

import pytest

from tests import fakes
from tests.fakes import FakeWindow
from wingman import paths, settings
from wingman.evesettings import identity as evesettings_identity
from wingman.evesettings import tree
from wingman.preview import discovery as discovery_mod
from wingman.ui import api as api_mod


class ImmediateThread:
    """Runs the worker inline, so a test never races a real thread."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        self._target(*self._args, **self._kwargs)


def build(tmp_path, monkeypatch, answer=True):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    state = api_mod.AppState(
        recording_dir=tmp_path, settings=settings.load(tmp_path / "settings.json")
    )
    built = api_mod.Api(state, spawn=ImmediateThread)
    built._window = FakeWindow()
    built._confirm = lambda title, body, **kw: answer
    # The EVE workers ask through _eve_confirm, which is _confirm with a
    # deadline; both are stubbed so a test never parks on a dialog.
    # **kw swallows round-6's `destructive`, which these tests do not
    # assert; test_the_copy_confirm_is_marked_destructive below does.
    built._eve_confirm = lambda title, body, **kw: answer
    return built


def eve_tree(tmp_path, files=("core_char_1.dat", "core_char_2.dat")):
    profile = tmp_path / "EVE" / "server_tranquility" / "settings_Default"
    profile.mkdir(parents=True)
    for name in files:
        (profile / name).write_bytes(b"payload-" + name.encode())
    return profile


def account_setup(tmp_path, monkeypatch, name="core_user_1.dat"):
    profile = eve_tree(tmp_path, files=(name,))
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    return api, profile / name


def test_state_is_empty_before_a_root_is_chosen(tmp_path, monkeypatch):
    api = build(tmp_path, monkeypatch)
    state = api.eve_settings_state()
    assert state["root"] == "" and state["characters"] == []


def test_state_lists_characters_once_a_root_is_set(tmp_path, monkeypatch):
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    state = api.eve_settings_state()
    assert {c["id"] for c in state["characters"]} == {"1", "2"}
    assert state["profile"] == str(profile)


def test_state_labels_unresolved_characters_with_their_id(tmp_path, monkeypatch):
    eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    state = api.eve_settings_state()
    assert state["characters"][0]["name"] == "Character 1"


def test_state_normalizes_a_legacy_profile_root_without_saving(tmp_path, monkeypatch):
    """An install from before canonical persistence could have `root` set
    to a profile directory. Reading state must show the canonical triple
    without writing anything back -- no-write-on-read holds for a legacy
    value exactly as it does for a fresh one."""
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._eve_section().update({"root": str(profile), "server": None, "profile": None})
    monkeypatch.setattr(
        api_mod.settings_mod,
        "update_section",
        lambda *a, **k: pytest.fail("state must not save"),
    )
    state = api.eve_settings_state()
    assert state["root"] == str(profile.parent.parent)
    assert state["profile"] == str(profile)


def test_state_exposes_the_canonical_selective_copy_groups_and_availability(
    tmp_path, monkeypatch
):
    api = build(tmp_path, monkeypatch)
    monkeypatch.setattr(api_mod.evesettings_codec, "codec_available", lambda: True)

    state = api.eve_settings_state()

    assert state["selective_copy_available"] is True
    assert state["copy_groups"] == {
        "characters": api_mod.evesettings_selective.groups_payload("character"),
        "accounts": api_mod.evesettings_selective.groups_payload("account"),
    }
    assert [
        group for group in state["copy_groups"]["characters"] if not group["default_on"]
    ] == [
        {
            "id": "search_history",
            "label": "Search history & suggestions",
            "default_on": False,
        }
    ]


def test_state_reports_an_unreadable_folder(tmp_path, monkeypatch):
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    eve_tree(tmp_path)

    def boom(_path):
        raise PermissionError(13, "denied")

    monkeypatch.setattr(api_mod.evesettings_tree.os, "scandir", boom)
    assert api.eve_settings_state()["unreadable"] is True


def test_copy_writes_every_target(tmp_path, monkeypatch):
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api.eve_settings_copy(
        str(profile / "core_char_1.dat"), [str(profile / "core_char_2.dat")]
    )
    assert (profile / "core_char_2.dat").read_bytes() == b"payload-core_char_1.dat"


def test_plain_copy_keeps_the_two_argument_byte_copy_path(tmp_path, monkeypatch):
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api._eve_client_running = lambda: False
    called = []

    def plain(source, targets, **kwargs):
        called.append((source, targets, kwargs))
        return api_mod.evesettings_ops.CopyReport(
            [api_mod.evesettings_ops.TargetOutcome(profile / "core_char_2.dat", True)]
        )

    monkeypatch.setattr(api_mod.evesettings_ops, "copy_to_targets", plain)
    monkeypatch.setattr(
        api_mod.evesettings_ops,
        "copy_selected_to_targets",
        lambda *args, **kwargs: pytest.fail("structured copy must not run"),
    )

    api.eve_settings_copy(
        str(profile / "core_char_1.dat"), [str(profile / "core_char_2.dat")]
    )

    assert len(called) == 1


def test_structured_copy_delegates_selected_groups_unchanged(tmp_path, monkeypatch):
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api._eve_client_running_strict = lambda: False
    groups = ["windows", "chat"]
    called = []

    def selected(source, targets, **kwargs):
        called.append(kwargs["selected_groups"])
        return api_mod.evesettings_ops.CopyReport(
            [api_mod.evesettings_ops.TargetOutcome(profile / "core_char_2.dat", True)]
        )

    monkeypatch.setattr(api_mod.evesettings_ops, "copy_selected_to_targets", selected)
    monkeypatch.setattr(
        api_mod.evesettings_ops,
        "copy_to_targets",
        lambda *args, **kwargs: pytest.fail("plain copy must not run"),
    )

    api.eve_settings_copy(
        str(profile / "core_char_1.dat"),
        [str(profile / "core_char_2.dat")],
        groups,
    )

    assert called == [groups]


@pytest.mark.parametrize("probe_result", [True, OSError("window station unavailable")])
def test_structured_copy_refuses_when_eve_is_running_or_the_probe_fails(
    tmp_path, monkeypatch, probe_result
):
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api._alert = fakes.Alerts()
    confirms = []
    api._eve_confirm = lambda *args, **kwargs: confirms.append(args) or True

    def probe():
        if isinstance(probe_result, BaseException):
            raise probe_result
        return probe_result

    api._eve_client_running_strict = probe
    monkeypatch.setattr(
        api_mod.evesettings_ops,
        "copy_selected_to_targets",
        lambda *args, **kwargs: pytest.fail("copy must not run"),
    )

    api.eve_settings_copy(
        str(profile / "core_char_1.dat"),
        [str(profile / "core_char_2.dat")],
        ["windows"],
    )

    assert confirms == []
    assert len(api._alert.raised) == 1
    assert "Close EVE" in api._alert.raised[0][2]
    assert any(
        "onEveSettingsDone" in js and '"ok": false' in js for js in api._window.calls
    )
    assert api._eve_mutation.acquire(blocking=False)
    api._eve_mutation.release()


def test_structured_confirmation_derives_preserved_labels_from_the_kind_table(
    tmp_path, monkeypatch
):
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api._eve_client_running_strict = lambda: False
    asked = confirms(api)

    api.eve_settings_copy(
        str(profile / "core_char_1.dat"),
        [str(profile / "core_char_2.dat")],
        ["windows", "neocom", "infopanels", "dockpanels", "search_history"],
    )

    ((_title, body),) = asked
    assert "Preserved in each target: Chat channels." in body


def test_invalid_selective_groups_are_rejected_before_confirmation(
    tmp_path, monkeypatch
):
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    asked = []
    api._eve_confirm = lambda *args, **kwargs: asked.append(args) or True
    api._eve_client_running_strict = lambda: False

    api.eve_settings_copy(
        str(profile / "core_char_1.dat"),
        [str(profile / "core_char_2.dat")],
        ["overview"],
    )

    assert asked == []


def test_partial_structured_copy_reports_counts_and_still_prunes_backups(
    tmp_path, monkeypatch
):
    profile = eve_tree(
        tmp_path,
        files=("core_char_1.dat", "core_char_2.dat", "core_char_3.dat"),
    )
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api._eve_client_running_strict = lambda: False
    api._alert = fakes.Alerts()
    pruned = []
    outcomes = [
        api_mod.evesettings_ops.TargetOutcome(profile / "core_char_2.dat", True),
        api_mod.evesettings_ops.TargetOutcome(
            profile / "core_char_3.dat", False, "bad target"
        ),
    ]
    monkeypatch.setattr(
        api_mod.evesettings_ops,
        "copy_selected_to_targets",
        lambda *args, **kwargs: api_mod.evesettings_ops.CopyReport(outcomes),
    )
    monkeypatch.setattr(
        api_mod.evesettings_backup,
        "prune",
        lambda store, keep: (
            pruned.append((store, keep)) or api_mod.evesettings_backup.PruneReport()
        ),
    )

    api.eve_settings_copy(
        str(profile / "core_char_1.dat"),
        [str(profile / "core_char_2.dat"), str(profile / "core_char_3.dat")],
        ["windows"],
    )

    assert "Copied to 1 of 2" in api._alert.raised[0][2]
    assert len(pruned) == 1


def test_copy_takes_a_backup_of_each_target(tmp_path, monkeypatch):
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api.eve_settings_copy(
        str(profile / "core_char_1.dat"), [str(profile / "core_char_2.dat")]
    )
    assert len(api.eve_settings_state()["backups"]) == 1


def test_copy_declined_at_the_prompt_changes_nothing(tmp_path, monkeypatch):
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch, answer=False)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api.eve_settings_copy(
        str(profile / "core_char_1.dat"), [str(profile / "core_char_2.dat")]
    )
    assert (profile / "core_char_2.dat").read_bytes() == b"payload-core_char_2.dat"


def test_the_copy_confirm_names_the_source_and_the_targets(tmp_path, monkeypatch):
    """Round 3's P9. The dialog is the last screen before an irreversible
    overwrite and it named neither end of the action. The names must be the
    roster's own -- Api._eve_label produces both, so the dialog cannot name
    a character by one label while the list behind it shows another."""
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch, answer=False)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api._eve_names.names[1] = "Guarzo Opper"
    api._eve_names.names[2] = "Zircon Gravimeld"
    seen = []
    api._eve_confirm = lambda title, body, **kw: seen.append(body) or False

    api.eve_settings_copy(
        str(profile / "core_char_1.dat"), [str(profile / "core_char_2.dat")]
    )

    assert "Guarzo Opper's settings" in seen[0]
    assert "Zircon Gravimeld" in seen[0]
    roster = {c["id"]: c["name"] for c in api.eve_settings_state()["characters"]}
    assert roster["1"] == "Guarzo Opper" and roster["2"] == "Zircon Gravimeld"


def test_the_roster_is_ordered_by_name_not_by_file_id(tmp_path, monkeypatch):
    """R1/D4. evesettings.tree can only order by the id in the filename,
    and 32 characters in id order have no human pattern, which left the
    filter box as the only route to one of them. The names exist one layer
    up, so the roster is ordered there."""
    profile = eve_tree(
        tmp_path, files=("core_char_1.dat", "core_char_2.dat", "core_char_3.dat")
    )
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api._eve_names.names[1] = "Zircon Gravimeld"
    api._eve_names.names[2] = "guarzo opper"
    api._eve_names.names[3] = "Aura"

    names = [c["name"] for c in api.eve_settings_state()["characters"]]

    assert names == ["Aura", "guarzo opper", "Zircon Gravimeld"]
    assert [f.file_id for f in tree.discover(tmp_path / "EVE").characters] == [
        "1",
        "2",
        "3",
    ], "the tree's own order is the stable base the name sort tie-breaks on"
    assert profile.is_dir()


def test_unresolved_names_keep_a_deterministic_roster_order(tmp_path, monkeypatch):
    """Every label degrades to "Character <id>" before ESI answers, and two
    equal labels must not be free to swap places between renders."""
    eve_tree(tmp_path, files=("core_char_10.dat", "core_char_9.dat"))
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")

    twice = [
        [c["id"] for c in api.eve_settings_state()["characters"]] for _ in range(2)
    ]

    assert twice[0] == twice[1]


def test_the_roster_and_the_confirm_share_one_label_producer(tmp_path, monkeypatch):
    """Two producers would be free to disagree, and an unresolved id is
    exactly where they would: the roster degrades to "Character 2" and a
    second implementation could just as easily print the bare path."""
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    state = api.eve_settings_state()
    for character in state["characters"]:
        assert api._eve_label(character["path"]) == character["name"]
    assert api._eve_label(profile / "core_char_2.dat") == "Character 2"


def test_a_second_mutation_is_refused_while_one_holds_the_lock(tmp_path, monkeypatch):
    """_confirm parks each worker independently, so without a lock two
    approved operations can interleave over the same files."""
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api._eve_mutation.acquire()
    try:
        accepted = api.eve_settings_copy(
            str(profile / "core_char_1.dat"), [str(profile / "core_char_2.dat")]
        )
    finally:
        api._eve_mutation.release()
    assert accepted is False
    assert (profile / "core_char_2.dat").read_bytes() == b"payload-core_char_2.dat"


def test_the_lock_is_released_even_when_the_worker_raises(tmp_path, monkeypatch):
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")

    def explode(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(api_mod.evesettings_ops, "copy_to_targets", explode)
    api.eve_settings_copy(
        str(profile / "core_char_1.dat"), [str(profile / "core_char_2.dat")]
    )
    assert api._eve_mutation.acquire(blocking=False) is True
    api._eve_mutation.release()


def test_select_persists_through_the_merging_writer(tmp_path, monkeypatch):
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api.eve_settings_select(str(profile.parent), str(profile))
    stored = settings.load(tmp_path / "FlyGD Wingman" / "settings.json")
    assert stored["eve_settings"]["profile"] == str(profile)


@pytest.mark.parametrize("picked_level", ["root", "server", "profile"])
def test_pick_root_persists_the_canonical_selection(
    tmp_path, monkeypatch, picked_level
):
    """Whichever level of the tree the OS dialog hands back, the picker
    discovers the whole tree from it and persists the canonical triple --
    not just the raw picked path with server/profile cleared."""
    profile = eve_tree(tmp_path)
    root, server = profile.parent.parent, profile.parent
    api = build(tmp_path, monkeypatch)
    picked = {"root": root, "server": server, "profile": profile}[picked_level]
    api._window.create_file_dialog = lambda *a, **k: (str(picked),)
    assert api.eve_settings_pick_root() == str(root)
    assert api._eve_section()["root"] == str(root)
    assert api._eve_section()["server"] == str(server)
    assert api._eve_section()["profile"] == str(profile)


def test_select_rejects_a_fabricated_selection(tmp_path, monkeypatch):
    """discover() falls back to the first server/profile it finds when a
    requested token matches nothing on disk. Persisting that fallback under
    a fabricated request's name would silently swap the user's selection
    for one they never asked for."""
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    assert api.eve_settings_select(str(profile.parent), "nonexistent-profile") is False
    assert api._eve_section()["profile"] is None
    assert api.eve_settings_select("nonexistent-server", str(profile)) is False
    assert api._eve_section()["server"] is None


def test_select_canonicalizes_a_legacy_deep_root(tmp_path, monkeypatch):
    """A stored root that is itself a profile directory -- from before
    canonical persistence -- must be healed by the next selection, not
    merely tolerated in place."""
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(profile)
    assert api.eve_settings_select(str(profile.parent), str(profile)) is True
    section = api._eve_section()
    assert section["root"] == str(profile.parent.parent)
    assert section["server"] == str(profile.parent)
    assert section["profile"] == str(profile)


def test_select_switches_to_a_sibling_profile_from_a_legacy_profile_root(
    tmp_path, monkeypatch
):
    """normalize_selection's profile-dir branch discards the CALLER'S
    requested profile in favor of the one implied by a legacy deep root
    (tree.py's `return root.parent.parent, root.parent, root`). Selection
    must discover from the EFFECTIVE canonical root first, so a genuine
    request to switch to a sibling profile is not overruled by the very
    legacy value it is trying to move away from."""
    profile = eve_tree(tmp_path)
    sibling = profile.parent / "settings_Alt"
    sibling.mkdir()
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(profile)
    assert api.eve_settings_select(str(profile.parent), str(sibling)) is True
    section = api._eve_section()
    assert section["root"] == str(profile.parent.parent)
    assert section["server"] == str(profile.parent)
    assert section["profile"] == str(sibling)


def test_select_switches_to_a_sibling_server_from_a_legacy_server_root(
    tmp_path, monkeypatch
):
    """Same fix, the server-directory branch: normalize_selection discards
    the caller's requested SERVER when the stored root is itself a server
    directory (`return root.parent, root, ...`). A legacy install whose
    root points at one server must still be able to select a different,
    sibling server."""
    profile = eve_tree(tmp_path)
    server = profile.parent
    root = server.parent
    other_server = root / "server_singularity"
    other_profile = other_server / "settings_Default"
    other_profile.mkdir(parents=True)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(server)
    assert api.eve_settings_select(str(other_server), str(other_profile)) is True
    section = api._eve_section()
    assert section["root"] == str(root)
    assert section["server"] == str(other_server)
    assert section["profile"] == str(other_profile)


def test_select_with_an_empty_profile_chooses_the_servers_first_profile(
    tmp_path, monkeypatch
):
    profile = eve_tree(tmp_path)
    (profile.parent / "settings_Alt").mkdir()
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    assert api.eve_settings_select(str(profile.parent), "") is True
    assert api._eve_section()["profile"] == str(profile)


def test_names_are_pushed_once_a_pass_resolves_something(tmp_path, monkeypatch):
    eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api._eve_names.resolve_missing = lambda ids, **kw: True
    api.eve_settings_resolve_names()
    assert any("onEveSettingsNames" in call for call in api._window.calls)


def test_no_push_when_a_pass_resolves_nothing(tmp_path, monkeypatch):
    eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api._eve_names.resolve_missing = lambda ids, **kw: False
    api.eve_settings_resolve_names()
    assert not any("onEveSettingsNames" in call for call in api._window.calls)


def test_copy_refuses_a_target_outside_the_configured_root(tmp_path, monkeypatch):
    """Containment is not the page's job: a junction inside the settings
    tree is what makes a target that looks local land on another disk."""
    profile = eve_tree(tmp_path)
    outside = tmp_path / "elsewhere" / "core_char_2.dat"
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api.eve_settings_copy(str(profile / "core_char_1.dat"), [str(outside)])
    assert not outside.exists() and not outside.parent.exists()


def test_backup_refuses_an_empty_path(tmp_path, monkeypatch):
    """Path("") is the app's own working directory, which
    create_profile_backup would walk and report as a successful backup."""
    eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api.eve_settings_backup("", "profile")
    assert api.eve_settings_state()["backups"] == []
    assert any("Backup failed" in call for call in api._window.calls)


def test_backup_refuses_a_path_that_no_longer_exists(tmp_path, monkeypatch):
    eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    gone = tmp_path / "EVE" / "server_tranquility" / "settings_Gone"
    api.eve_settings_backup(str(gone), "profile")
    assert api.eve_settings_state()["backups"] == []


def test_backup_refuses_a_path_outside_the_configured_root(tmp_path, monkeypatch):
    eve_tree(tmp_path)
    other = tmp_path / "elsewhere"
    other.mkdir()
    (other / "core_char_9.dat").write_bytes(b"x")
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api.eve_settings_backup(str(other), "profile")
    assert api.eve_settings_state()["backups"] == []


def test_restore_authorizes_against_the_effective_root_not_a_legacy_profile_root(
    tmp_path, monkeypatch
):
    """A pre-canonicalization install could have `root` stored pointing
    directly at a profile directory. Restoring a SIBLING profile's backup
    must validate against the canonical root discover() resolves from that
    legacy value -- the profile's grandparent -- not the raw stored path,
    which would reject the sibling as outside a directory that was never
    really the configured root."""
    profile = eve_tree(tmp_path)
    sibling = profile.parent / "settings_Alt"
    sibling.mkdir()
    (sibling / "core_char_9.dat").write_bytes(b"sibling-data")
    api = build(tmp_path, monkeypatch)
    store = paths.eve_settings_backup_dir()
    made = api_mod.evesettings_backup.create_profile_backup(
        store, sibling, origin="manual"
    )
    # Legacy install: `root` points at the original profile, not its
    # grandparent -- the case this task's restore fix authorizes against.
    api._state.settings["eve_settings"]["root"] = str(profile)
    (sibling / "core_char_9.dat").unlink()

    api.eve_settings_restore(str(made))

    assert (sibling / "core_char_9.dat").read_bytes() == b"sibling-data"
    done = [c for c in api._window.calls if "onEveSettingsDone" in c]
    assert len(done) == 1 and '"ok": true' in done[0]


def test_restore_refuses_when_no_root_is_configured(tmp_path, monkeypatch):
    api = build(tmp_path, monkeypatch)
    api.eve_settings_restore("whatever.zip")
    done = [c for c in api._window.calls if "onEveSettingsDone" in c]
    assert len(done) == 1 and '"ok": false' in done[0]
    assert any("Restore failed" in call for call in api._window.calls)


def test_a_failed_spawn_does_not_strand_the_mutation_lock(tmp_path, monkeypatch):
    """Only the worker releases the lock, and a worker that never started
    never will -- every later operation would be refused for good."""
    profile = eve_tree(tmp_path)

    class Refuses:
        def __init__(self, **kwargs):
            pass

        def start(self):
            raise RuntimeError("can't start new thread")

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    state = api_mod.AppState(
        recording_dir=tmp_path, settings=settings.load(tmp_path / "s.json")
    )
    api = api_mod.Api(state, spawn=Refuses)
    api._window = FakeWindow()
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    assert (
        api.eve_settings_copy(
            str(profile / "core_char_1.dat"), [str(profile / "core_char_2.dat")]
        )
        is False
    )
    assert api._eve_mutation.acquire(blocking=False) is True
    api._eve_mutation.release()


def test_a_confirmation_nobody_answers_does_not_strand_the_lock(tmp_path, monkeypatch):
    """_push swallows every evaluate_js failure, so a confirmation whose
    push never reached the page would park the worker forever holding the
    lock. The wait is bounded and a missing answer reads as "no"."""
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    del api._eve_confirm  # back to the real, bounded implementation
    monkeypatch.setattr(api_mod, "EVE_CONFIRM_TIMEOUT_S", 0.05)
    api.eve_settings_copy(
        str(profile / "core_char_1.dat"), [str(profile / "core_char_2.dat")]
    )
    assert (profile / "core_char_2.dat").read_bytes() == b"payload-core_char_2.dat"
    assert api._eve_mutation.acquire(blocking=False) is True
    api._eve_mutation.release()


def test_every_mutation_pushes_a_completion_the_page_can_wait_on(tmp_path, monkeypatch):
    """eve_settings_copy returns as soon as the worker is spawned, so this
    push is the page's only signal that the work is actually done."""
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api.eve_settings_copy(
        str(profile / "core_char_1.dat"), [str(profile / "core_char_2.dat")]
    )
    done = [c for c in api._window.calls if "onEveSettingsDone" in c]
    assert len(done) == 1 and '"ok": true' in done[0]


def test_a_failed_mutation_still_pushes_a_completion(tmp_path, monkeypatch):
    eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api.eve_settings_backup("", "profile")
    done = [c for c in api._window.calls if "onEveSettingsDone" in c]
    assert len(done) == 1 and '"ok": false' in done[0]


def test_state_reports_an_unreadable_backup_store(tmp_path, monkeypatch):
    """ "Couldn't read your backups" and "you have none yet" are different
    answers, and only one of them means something is wrong. Telling a user
    the second when the first is true invites an overwrite they believe is
    protected."""
    eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    store = paths.eve_settings_backup_dir()
    # Guard, not decoration: build() monkeypatches LOCALAPPDATA, and this
    # test chmods the directory to 000. If that redirection ever stopped
    # working, the line below would strip the real user's backup folder of
    # every permission. Fail loudly instead.
    assert str(store).startswith(str(tmp_path)), store
    store.mkdir(parents=True, exist_ok=True)
    store.chmod(0o000)
    try:
        try:
            os.scandir(str(store)).close()
        except PermissionError:
            pass
        else:  # pragma: no cover - root, or a filesystem without modes
            pytest.skip("this user can read a mode-000 directory")
        state = api.eve_settings_state()
        assert state["backups_unreadable"] is True and state["backups"] == []
    finally:
        store.chmod(0o700)


def test_state_does_not_call_a_readable_empty_store_unreadable(tmp_path, monkeypatch):
    eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    assert api.eve_settings_state()["backups_unreadable"] is False


def test_selecting_is_refused_while_a_mutation_holds_the_lock(tmp_path, monkeypatch):
    """`root` is an input to every containment check, so changing it under
    an in-flight restore has that operation validate against a different
    root than the one in effect when the user approved it. _eve_begin's
    stated policy is that EVE Settings mutations are refused rather than
    interleaved, and selection mutates exactly that input."""
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api._eve_mutation.acquire()
    try:
        assert api.eve_settings_select(str(profile.parent), str(profile)) is False
        assert api._state.settings["eve_settings"]["server"] is None
    finally:
        api._eve_mutation.release()
    assert api.eve_settings_select(str(profile.parent), str(profile)) is True


def test_picking_a_root_is_refused_while_a_mutation_holds_the_lock(
    tmp_path, monkeypatch
):
    eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    opened = []

    def dialog(*args, **kwargs):
        opened.append(args)
        return [str(tmp_path / "EVE")]

    api._window.create_file_dialog = dialog
    # webview is not installed on the Linux box these tests run on, and
    # _folder_dialog_kind() imports it before the dialog is ever called.
    monkeypatch.setattr(api_mod, "_folder_dialog_kind", lambda: "FOLDER")
    api._eve_mutation.acquire()
    try:
        assert api.eve_settings_pick_root() == ""
        # Not merely a refused write: the picker never opened, so the user
        # is not asked to choose a folder that is then thrown away.
        assert opened == []
    finally:
        api._eve_mutation.release()
    assert api.eve_settings_pick_root() == str(tmp_path / "EVE")


def test_selecting_releases_the_lock_for_the_next_mutation(tmp_path, monkeypatch):
    """A hold that leaked would refuse every later copy, backup, restore
    and delete until the app restarted."""
    eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api.eve_settings_select("s", "p")
    assert api._eve_mutation.acquire(blocking=False) is True
    api._eve_mutation.release()


def test_a_pick_root_that_raises_still_releases_the_lock(tmp_path, monkeypatch):
    eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("no dialog here")

    api._window.create_file_dialog = boom
    monkeypatch.setattr(api_mod, "_folder_dialog_kind", lambda: "FOLDER")
    with pytest.raises(RuntimeError):
        api.eve_settings_pick_root()
    assert api._eve_mutation.acquire(blocking=False) is True
    api._eve_mutation.release()


def test_state_reads_the_running_pill_from_cache_not_a_fresh_probe(
    tmp_path, monkeypatch
):
    """eve_settings_state is costed in the design as scandir over a few
    dozen files. list_clients() enumerates every top-level window and
    resolves PIDs to executables, which is not that -- so it runs on a
    background thread and state reads the last known answer."""
    eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    calls = []
    api._eve_refresh_running = lambda: calls.append(1)
    api._eve_running = True
    assert api.eve_settings_state()["eve_running"] is True
    # Kicked off, but its answer is never awaited on this thread.
    assert calls == [1]


def test_the_strict_running_probe_opts_in_at_the_discovery_boundary(
    tmp_path, monkeypatch
):
    from wingman.preview import discovery

    api = build(tmp_path, monkeypatch)
    seen = []
    monkeypatch.setattr(
        discovery, "list_clients", lambda **kwargs: seen.append(kwargs) or []
    )

    assert api._eve_client_running_strict() is False
    assert seen == [{"strict": True}]


def test_the_running_probe_pushes_only_when_the_answer_changes(tmp_path, monkeypatch):
    """One push per change, not per refresh: the page has nothing to
    redraw when the pill still says what it already said."""
    eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    pushed = []
    api._push = lambda name, payload: pushed.append((name, payload))

    # None -> False IS a change: the pill was showing "Checking...".
    api._eve_client_running = lambda: False
    api._eve_refresh_running()
    assert pushed == [("onEveSettingsRunning", {"running": False})]

    api._eve_refresh_running()
    assert len(pushed) == 1, "no change, so nothing to push"

    api._eve_client_running = lambda: True
    api._eve_refresh_running()
    assert pushed[-1] == ("onEveSettingsRunning", {"running": True})
    assert len(pushed) == 2 and api._eve_running is True

    api._eve_refresh_running()
    assert len(pushed) == 2, "no change, so nothing to push"


def test_a_probe_that_raises_leaves_the_pill_alone(tmp_path, monkeypatch):
    """Advisory only. A failed probe must never surface as an error."""
    eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    pushed = []
    api._push = lambda name, payload: pushed.append((name, payload))

    def boom():
        raise OSError("no window station")

    api._eve_client_running = boom
    api._eve_refresh_running()
    # Still None: a failed probe must not fabricate "EVE closed", which is
    # the reassuring answer and the only warning before a copy.
    assert pushed == [] and api._eve_running is None


def test_state_refuses_a_root_too_wide_to_be_an_eve_folder(tmp_path, monkeypatch):
    """A mis-picked root costs a scandir per child on the bridge thread.
    Refused with a reason, rather than probed slowly."""
    api = build(tmp_path, monkeypatch)
    wide = tmp_path / "wide"
    wide.mkdir()
    for n in range(api_mod.evesettings_tree.MAX_ROOT_CHILDREN + 1):
        (wide / f"dir{n:03d}").mkdir()
    api._state.settings["eve_settings"]["root"] = str(wide)
    state = api.eve_settings_state()
    assert state["too_broad"] is True and state["servers"] == []


def test_a_normal_root_is_not_reported_as_too_broad(tmp_path, monkeypatch):
    eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    assert api.eve_settings_state()["too_broad"] is False


def test_the_pill_is_unknown_until_the_probe_answers(tmp_path, monkeypatch):
    """False is the reassuring guess, and the pill is the ONLY warning
    before a copy -- the copy confirmation says nothing about a running
    client. The probe was moved off the bridge thread precisely because
    its first, uncached pass is slow, so a fabricated "EVE closed" would
    be on screen for exactly as long as it takes to be wrong about."""
    eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    # Nothing has looked yet; the probe must not be allowed to run inline.
    api._eve_refresh_running = lambda: None
    assert api.eve_settings_state()["eve_running"] is None


def test_a_second_probe_is_skipped_while_one_is_in_flight(tmp_path, monkeypatch):
    """eve_settings_state() fires a probe on every call -- route open and
    after every mutation -- so two overlap easily. Without single-flight a
    slow probe finishing after a fast one publishes the OLDER observation
    and leaves it cached, showing "EVE closed" while EVE is running with
    nothing to correct it."""
    eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    started = []

    class Parked:
        """A spawn that never runs the worker, so the lock stays held."""

        def __init__(self, target=None, args=(), kwargs=None, daemon=None):
            started.append(target)

        def start(self):
            return None

    api._spawn = Parked
    api._eve_refresh_running()
    api._eve_refresh_running()
    assert len(started) == 1, "a second probe was spawned over the first"


def test_a_probe_that_cannot_be_spawned_does_not_wedge_the_lock(tmp_path, monkeypatch):
    """Only the worker releases, and a worker that never started never
    will -- that would freeze the pill for the process's lifetime."""
    eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)

    def no_thread(*args, **kwargs):
        raise RuntimeError("can't start new thread")

    api._spawn = no_thread
    api._eve_refresh_running()
    assert api._eve_probe.acquire(blocking=False) is True
    api._eve_probe.release()


def test_the_probe_releases_its_lock_even_when_it_raises(tmp_path, monkeypatch):
    eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)

    def boom():
        raise OSError("no window station")

    api._eve_client_running = boom
    api._eve_refresh_running()
    assert api._eve_probe.acquire(blocking=False) is True
    api._eve_probe.release()


# --- the copy confirmation, and the payload behind the backups card -------


def confirms(api):
    """Capture confirm bodies and decline, so nothing is written."""
    asked = []

    def ask(title, body, *, destructive=False):
        asked.append((title, body))
        return False

    api._eve_confirm = ask
    return asked


def test_the_copy_confirm_is_marked_destructive(tmp_path, monkeypatch):
    """Round 6, P0-1: the affirming button must be .btn.danger, not .btn.acc.

    Asserted at the CALL, not in the source. `panel.js` used to hard-code
    `btn acc` on every confirm under a comment claiming upload was the
    app's only irreversible action, so this dialog -- the one that
    overwrites another character's EVE settings -- offered the same
    encouraging purple as `Upload`, auto-focused. The page cannot pick the
    treatment unless the flag actually crosses the bridge, so the flag is
    what this checks.
    """
    api = build(tmp_path, monkeypatch)
    seen = []

    def ask(title, body, *, destructive=False):
        seen.append(destructive)
        return False

    api._eve_confirm = ask
    profile = eve_tree(tmp_path)
    api._eve_client_running = lambda: False

    api.eve_settings_copy(
        str(profile / "core_char_1.dat"), [str(profile / "core_char_2.dat")]
    )

    assert seen == [True], (
        "eve_settings_copy must ask with destructive=True; without it the "
        "page renders Confirm as .btn.acc"
    )


def test_the_copy_confirm_names_characters_rather_than_files(tmp_path, monkeypatch):
    """The noun is derived from the target paths (evesettings.tree.
    file_kind), not passed by the page: the Characters / Accounts switch
    already decides which files are offered, so a mode argument on the
    bridge would be the same fact written twice."""
    api = build(tmp_path, monkeypatch)
    asked = confirms(api)
    profile = eve_tree(tmp_path)
    api._eve_client_running = lambda: False

    api.eve_settings_copy(
        str(profile / "core_char_1.dat"), [str(profile / "core_char_2.dat")]
    )

    ((title, body),) = asked
    assert title == "Confirm Copy"
    assert "1 other character" in body
    assert "file(s)" not in body


def test_the_copy_confirm_names_accounts_when_accounts_were_selected(
    tmp_path, monkeypatch
):
    api = build(tmp_path, monkeypatch)
    asked = confirms(api)
    profile = eve_tree(tmp_path, files=("core_user_1.dat", "core_user_2.dat"))
    api._eve_client_running = lambda: False

    api.eve_settings_copy(
        str(profile / "core_user_1.dat"), [str(profile / "core_user_2.dat")]
    )

    ((_title, body),) = asked
    assert "1 other account" in body


def test_the_copy_confirm_warns_when_a_client_is_open(tmp_path, monkeypatch):
    """Probed fresh here rather than read from the cached pill value: the
    cache exists so eve_settings_state stays cheap on the bridge thread,
    and this sentence is about what is true at the moment of committing."""
    api = build(tmp_path, monkeypatch)
    asked = confirms(api)
    profile = eve_tree(tmp_path)
    api._eve_running = False  # The stale pill value; must not be the source.
    api._eve_client_running = lambda: True

    api.eve_settings_copy(
        str(profile / "core_char_1.dat"), [str(profile / "core_char_2.dat")]
    )

    ((_title, body),) = asked
    assert "EVE is running" in body


def test_the_state_payload_carries_the_backup_prune_depth(tmp_path, monkeypatch):
    """So the page can say how many backups are kept without typing the
    number into itself. Four places once carried the bookmark-keybind count
    and three of them drifted; DESIGN.md's "state that must not be retyped"
    is the rule this avoids."""
    api = build(tmp_path, monkeypatch)

    assert api.eve_settings_state()["auto_keep"] == 10


def test_the_prune_depth_reported_is_the_one_actually_used(tmp_path, monkeypatch):
    """A payload that always said 10 while the copy pruned to something
    else would be worse than no number at all."""
    api = build(tmp_path, monkeypatch)
    api._eve_section()["auto_keep"] = 3

    assert api.eve_settings_state()["auto_keep"] == 3


def test_account_payload_uses_name_character_summary_and_account_id(
    tmp_path, monkeypatch
):
    eve_tree(
        tmp_path, files=("core_user_10.dat", "core_char_20.dat", "core_char_21.dat")
    )
    api = build(tmp_path, monkeypatch)
    section = api._eve_section()
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"10": "LoginName"}
    section["account_characters"] = {"10": ["20", "21"]}
    api._eve_names.names.update({20: "Aiga Otsolen", 21: "Beta"})

    account = api.eve_settings_state()["accounts"][0]

    assert account["account_name"] == "LoginName"
    assert "alias" not in account
    assert account["display_name"] == "LoginName"
    assert account["display_meta"] == "Aiga Otsolen + 1 · Account 10"
    assert account["name"] == "LoginName · Aiga Otsolen + 1 · Account 10"


def test_unidentified_account_payload_is_explicit(tmp_path, monkeypatch):
    eve_tree(tmp_path, files=("core_user_10.dat",))
    api = build(tmp_path, monkeypatch)
    api._eve_section()["root"] = str(tmp_path / "EVE")

    account = api.eve_settings_state()["accounts"][0]

    assert account["account_name"] == ""
    assert account["display_name"] == "Account 10"
    assert account["display_meta"] == "Not identified"


def test_backup_rows_resolve_human_targets_without_opening_archives(
    tmp_path, monkeypatch
):
    profile = eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    api = build(tmp_path, monkeypatch)
    section = api._eve_section()
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"10": "LoginName"}
    section["account_characters"] = {"10": ["20"]}
    api._eve_names.names[20] = "Aiga Otsolen"
    store = paths.eve_settings_backup_dir()
    api_mod.evesettings_backup.create_file_backup(
        store, profile / "core_user_10.dat", origin="manual"
    )
    api_mod.evesettings_backup.create_file_backup(
        store, profile / "core_char_20.dat", origin="manual"
    )

    rows = api.eve_settings_state()["backups"]

    assert {(row["display_name"], row["display_meta"]) for row in rows} == {
        ("LoginName", "Aiga Otsolen · Account 10"),
        ("Aiga Otsolen", "Character 20"),
    }


def test_unidentified_account_backup_is_explicit_without_duplicating_id(
    tmp_path, monkeypatch
):
    profile = eve_tree(tmp_path, files=("core_user_10.dat",))
    api = build(tmp_path, monkeypatch)
    api._eve_section()["root"] = str(tmp_path / "EVE")
    api_mod.evesettings_backup.create_file_backup(
        paths.eve_settings_backup_dir(),
        profile / "core_user_10.dat",
        origin="manual",
    )

    row = api.eve_settings_state()["backups"][0]

    assert row["display_name"] == "Account 10"
    assert row["display_meta"] == "Not identified"
    assert (
        " · ".join((row["display_name"], row["display_meta"])).count("Account 10") == 1
    )


def test_identity_editor_keeps_linked_characters_missing_from_current_profile(
    tmp_path, monkeypatch
):
    eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    api = build(tmp_path, monkeypatch)
    section = api._eve_section()
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"10": "LoginName"}
    section["account_characters"] = {"10": ["20", "99"]}

    identities = api.eve_settings_state()["identity_characters"]

    assert {item["id"] for item in identities} == {"20", "99"}
    assert next(item for item in identities if item["id"] == "99")["name"] == (
        "Character 99"
    )


def test_account_name_is_trimmed_and_cannot_be_cleared(tmp_path, monkeypatch):
    eve_tree(tmp_path, files=("core_user_10.dat",))
    api = build(tmp_path, monkeypatch)
    api._eve_section()["root"] = str(tmp_path / "EVE")

    assert api.eve_settings_set_account_name("10", " LoginName ")["applied"] is True
    assert api._eve_section()["account_names"] == {"10": "LoginName"}
    assert api.eve_settings_set_account_name("10", "")["applied"] is False
    assert api.eve_settings_set_account_name("10", "x" * 81)["applied"] is False
    assert api._eve_section()["account_names"] == {"10": "LoginName"}


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("eve_settings_set_account_name", ("10", "LoginName")),
        ("eve_settings_set_account_characters", ("10", ["20"])),
    ],
)
def test_manual_identity_endpoints_refuse_busy_without_reading_or_writing(
    tmp_path, monkeypatch, method, args
):
    api = build(tmp_path, monkeypatch)
    api._eve_discover = lambda: pytest.fail("busy calls must not inspect the profile")
    api._eve_mutation.acquire()
    try:
        result = getattr(api, method)(*args)
    finally:
        api._eve_mutation.release()

    assert result == {
        "applied": False,
        "persisted": False,
        "error": "Another Profiles operation is running.",
    }


def test_manual_identity_name_and_roster_work_stays_under_the_mutation_lock(
    tmp_path, monkeypatch
):
    eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    api = build(tmp_path, monkeypatch)
    api._eve_section()["root"] = str(tmp_path / "EVE")
    original_discover = api._eve_discover
    original_update = api_mod.settings_mod.update_section

    def checked_discover():
        assert api._eve_mutation.locked()
        return original_discover()

    def checked_update(*args, **kwargs):
        assert api._eve_mutation.locked()
        return original_update(*args, **kwargs)

    monkeypatch.setattr(api, "_eve_discover", checked_discover)
    monkeypatch.setattr(api_mod.settings_mod, "update_section", checked_update)

    assert api.eve_settings_set_account_name("10", "LoginName")["applied"] is True
    assert api.eve_settings_set_account_characters("10", ["20"])["applied"] is True


def test_manual_identity_endpoint_does_not_interleave_a_blocked_save(
    tmp_path, monkeypatch
):
    eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    api = build(tmp_path, monkeypatch)
    api._eve_section()["root"] = str(tmp_path / "EVE")
    writing = threading.Event()
    release_write = threading.Event()
    original = api_mod.settings_mod.update_section

    def blocking_write(data, section, values):
        writing.set()
        assert release_write.wait(5), "test did not release the account-name write"
        return original(data, section, values)

    monkeypatch.setattr(api_mod.settings_mod, "update_section", blocking_write)
    writer = threading.Thread(
        target=lambda: api.eve_settings_set_account_name("10", "LoginName")
    )
    writer.start()
    assert writing.wait(5), "account-name save never reached settings write"

    result = api.eve_settings_set_account_characters("10", ["bad"])
    release_write.set()
    writer.join(5)

    assert not writer.is_alive()
    assert result == {
        "applied": False,
        "persisted": False,
        "error": "Another Profiles operation is running.",
    }


def test_account_identity_helpers_preserve_shared_validation_and_relinking_rules(
    tmp_path, monkeypatch
):
    api = build(tmp_path, monkeypatch)

    assert api._eve_validate_account_name("10", " Login ", {"11": "Other"}) == (
        "Login",
        None,
    )
    assert api._eve_validate_account_name("10", "other", {"11": "Other"}) == (
        None,
        "That EVE Online username is already assigned to another account.",
    )
    assert api._eve_relink_account_characters(
        {"10": ["21"], "11": ["20"]}, "10", ["20"], ["21", "20"]
    ) == ({"10": ["21", "20"]}, None)
    assert api._eve_relink_account_characters(
        {"10": ["21", "22", "23"]}, "10", ["20"], ["21", "22", "23", "20"]
    ) == (None, "An EVE account can have up to three characters.")


def test_account_name_is_unique_case_insensitively_except_for_itself(
    tmp_path, monkeypatch
):
    eve_tree(tmp_path, files=("core_user_10.dat", "core_user_11.dat"))
    api = build(tmp_path, monkeypatch)
    section = api._eve_section()
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"10": "LoginName"}
    section["account_characters"] = {"10": ["20"]}

    result = api.eve_settings_set_account_name("11", "loginname")

    assert result == {
        "applied": False,
        "persisted": False,
        "error": "That EVE Online username is already assigned to another account.",
    }
    assert api.eve_settings_set_account_name("10", "LOGINNAME")["applied"] is True
    assert api._eve_section()["account_names"] == {"10": "LOGINNAME"}
    assert api._eve_section()["account_characters"] == {"10": ["20"]}


def test_unnamed_account_refuses_character_links(tmp_path, monkeypatch):
    eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    api = build(tmp_path, monkeypatch)
    api._eve_section()["root"] = str(tmp_path / "EVE")

    result = api.eve_settings_set_account_characters("10", ["20"])

    assert result["error"] == "Name this account before adding characters."
    assert api._eve_section()["account_characters"] == {}


def test_three_unique_characters_apply_and_duplicates_do_not_consume_slots(
    tmp_path, monkeypatch
):
    eve_tree(
        tmp_path,
        files=(
            "core_user_10.dat",
            "core_char_20.dat",
            "core_char_21.dat",
            "core_char_22.dat",
        ),
    )
    api = build(tmp_path, monkeypatch)
    section = api._eve_section()
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"10": "LoginName"}

    result = api.eve_settings_set_account_characters("10", ["20", "20", "21", "22"])

    assert result["applied"] is True
    assert api._eve_section()["account_characters"] == {"10": ["20", "21", "22"]}


def test_fourth_unique_character_is_refused_without_mutating_either_account(
    tmp_path, monkeypatch
):
    eve_tree(
        tmp_path,
        files=(
            "core_user_10.dat",
            "core_user_11.dat",
            "core_char_20.dat",
            "core_char_21.dat",
            "core_char_22.dat",
            "core_char_23.dat",
        ),
    )
    api = build(tmp_path, monkeypatch)
    section = api._eve_section()
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"10": "Source", "11": "Destination"}
    section["account_characters"] = {"10": ["23"], "11": ["20", "21", "22"]}

    result = api.eve_settings_set_account_characters("11", ["20", "21", "22", "23"])

    assert result["error"] == "An EVE account can have up to three characters."
    assert api._eve_section()["account_characters"] == {
        "10": ["23"],
        "11": ["20", "21", "22"],
    }


def test_unknown_character_is_refused_without_mutation(tmp_path, monkeypatch):
    eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    api = build(tmp_path, monkeypatch)
    section = api._eve_section()
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"10": "LoginName"}
    section["account_characters"] = {"10": ["20"]}

    result = api.eve_settings_set_account_characters("10", ["99"])

    assert result["applied"] is False
    assert api._eve_section()["account_characters"] == {"10": ["20"]}


def test_associating_a_character_moves_it_to_a_named_account_with_room(
    tmp_path, monkeypatch
):
    eve_tree(
        tmp_path,
        files=("core_user_10.dat", "core_user_11.dat", "core_char_20.dat"),
    )
    api = build(tmp_path, monkeypatch)
    section = api._eve_section()
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"10": "Source", "11": "Destination"}
    section["account_characters"] = {"10": ["20"]}

    result = api.eve_settings_set_account_characters("11", ["20"])

    assert result["applied"] is True
    assert api._eve_section()["account_characters"] == {"11": ["20"]}


def test_removing_every_character_retains_the_account_name(tmp_path, monkeypatch):
    eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    api = build(tmp_path, monkeypatch)
    section = api._eve_section()
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"10": "LoginName"}
    section["account_characters"] = {"10": ["20"]}

    assert api.eve_settings_set_account_characters("10", [])["applied"] is True
    assert api._eve_section()["account_names"] == {"10": "LoginName"}
    assert api._eve_section()["account_characters"] == {}


def _pending_identification(api, account_id="10", character_ids=("20",)):
    api._eve_identification = evesettings_identity.Snapshot(
        Path("root"), Path("server"), Path("profile"), {}
    )
    api._eve_identification_candidate = (account_id, tuple(character_ids))


def test_identification_starts_with_no_snapshot_or_candidate(tmp_path, monkeypatch):
    api = build(tmp_path, monkeypatch)

    assert api._eve_identification is None
    assert api._eve_identification_candidate is None


def test_identification_start_replaces_an_old_candidate_and_check_records_latest_pair(
    tmp_path, monkeypatch
):
    profile = eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    api = build(tmp_path, monkeypatch)
    api._eve_section()["root"] = str(tmp_path / "EVE")
    api._eve_identification_candidate = ("old", ("candidate",))
    api._eve_client_running_strict = lambda: False

    assert api.eve_settings_identification_start()["status"] == "watching"
    assert api._eve_identification_candidate is None
    (profile / "core_user_10.dat").write_bytes(b"changed account")
    (profile / "core_char_20.dat").write_bytes(b"changed character")

    assert api.eve_settings_identification_check()["status"] == "candidate"
    assert api._eve_identification_candidate == ("10", ("20",))


def test_identification_start_and_check_report_busy_with_stable_status(
    tmp_path, monkeypatch
):
    eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    api = build(tmp_path, monkeypatch)
    api._eve_section()["root"] = str(tmp_path / "EVE")
    api._eve_mutation.acquire()
    try:
        start = api.eve_settings_identification_start()
        check = api.eve_settings_identification_check()
    finally:
        api._eve_mutation.release()

    assert start == {
        "status": "busy",
        "error": "Another Profiles operation is running.",
    }
    assert check == start


def test_identification_check_clears_obsolete_candidate_on_no_change(
    tmp_path, monkeypatch
):
    eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    api = build(tmp_path, monkeypatch)
    api._eve_section()["root"] = str(tmp_path / "EVE")
    api._eve_client_running_strict = lambda: False
    assert api.eve_settings_identification_start()["status"] == "watching"
    api._eve_identification_candidate = ("10", ("20",))

    result = api.eve_settings_identification_check()

    assert result == {
        "status": "none",
        "error": "No account and character changes were found. Make a small settings change in the client, then close it completely and check again.",
    }
    assert api._eve_identification is not None
    assert api._eve_identification_candidate is None


def test_identification_check_clears_candidate_on_ambiguity_and_invalidation(
    tmp_path, monkeypatch
):
    profile = eve_tree(
        tmp_path,
        files=("core_user_10.dat", "core_user_11.dat", "core_char_20.dat"),
    )
    api = build(tmp_path, monkeypatch)
    api._eve_section()["root"] = str(tmp_path / "EVE")
    api._eve_client_running_strict = lambda: False
    assert api.eve_settings_identification_start()["status"] == "watching"
    api._eve_identification_candidate = ("10", ("20",))
    for name in ("core_user_10.dat", "core_user_11.dat", "core_char_20.dat"):
        (profile / name).write_bytes(b"changed with a different size " + name.encode())

    assert api.eve_settings_identification_check()["status"] == "ambiguous"
    assert api._eve_identification_candidate is None
    api._eve_identification_candidate = ("10", ("20",))
    (profile / "core_char_20.dat").unlink()

    assert api.eve_settings_identification_check()["status"] == "invalidated"
    assert api._eve_identification is None
    assert api._eve_identification_candidate is None


def test_identification_check_preserves_snapshot_but_clears_candidate_while_eve_runs(
    tmp_path, monkeypatch
):
    eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    api = build(tmp_path, monkeypatch)
    api._eve_section()["root"] = str(tmp_path / "EVE")
    assert api.eve_settings_identification_start()["status"] == "watching"
    snapshot = api._eve_identification
    api._eve_identification_candidate = ("10", ("20",))
    api._eve_client_running_strict = lambda: True

    assert api.eve_settings_identification_check()["status"] == "watching"
    assert api._eve_identification is snapshot
    assert api._eve_identification_candidate is None


def test_identification_cancellation_and_selection_changes_clear_snapshot_and_candidate(
    tmp_path, monkeypatch
):
    profile = eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    api = build(tmp_path, monkeypatch)
    api._eve_section()["root"] = str(tmp_path / "EVE")

    _pending_identification(api)
    assert api.eve_settings_identification_cancel() is True
    assert api._eve_identification is None
    assert api._eve_identification_candidate is None

    _pending_identification(api)
    assert api.eve_settings_select(str(profile.parent), str(profile)) is True
    assert api._eve_identification is None
    assert api._eve_identification_candidate is None

    _pending_identification(api)
    api._window.create_file_dialog = lambda *args, **kwargs: [str(tmp_path / "other")]
    monkeypatch.setattr(api_mod, "_folder_dialog_kind", lambda: "FOLDER")
    assert api.eve_settings_pick_root() == str(tmp_path / "other")
    assert api._eve_identification is None
    assert api._eve_identification_candidate is None


def test_identification_confirmation_refuses_missing_or_stale_candidates(
    tmp_path, monkeypatch
):
    api = build(tmp_path, monkeypatch)

    assert (
        api.eve_settings_identification_confirm("10", "20", "Login")["applied"] is False
    )
    _pending_identification(api)
    assert (
        api.eve_settings_identification_confirm("11", "20", "Login")["applied"] is False
    )
    assert (
        api.eve_settings_identification_confirm("10", "21", "Login")["applied"] is False
    )
    assert api._eve_section()["account_names"] == {}
    assert api._eve_section()["account_characters"] == {}


@pytest.mark.parametrize("name", ["", "x" * 81, "other"])
def test_identification_confirmation_rejects_invalid_names_without_partial_write(
    tmp_path, monkeypatch, name
):
    api = build(tmp_path, monkeypatch)
    section = api._eve_section()
    section["account_names"] = {"11": "Other"}
    section["account_characters"] = {"11": ["21"]}
    _pending_identification(api)

    result = api.eve_settings_identification_confirm("10", "20", name)

    assert result["applied"] is False
    assert api._eve_section()["account_names"] == {"11": "Other"}
    assert api._eve_section()["account_characters"] == {"11": ["21"]}
    assert api._eve_identification_candidate == ("10", ("20",))


def test_identification_confirmation_persists_name_and_link_in_one_write(
    tmp_path, monkeypatch
):
    api = build(tmp_path, monkeypatch)
    _pending_identification(api)
    original = api_mod.settings_mod.update_section
    writes = []

    def record_write(data, section, values):
        writes.append((section, values))
        return original(data, section, values)

    monkeypatch.setattr(api_mod.settings_mod, "update_section", record_write)

    assert api.eve_settings_identification_confirm("10", "20", " Login ") == {
        "applied": True,
        "persisted": True,
        "error": None,
    }
    assert writes == [
        (
            "eve_settings",
            {"account_names": {"10": "Login"}, "account_characters": {"10": ["20"]}},
        )
    ]
    assert api._eve_section()["account_names"] == {"10": "Login"}
    assert api._eve_section()["account_characters"] == {"10": ["20"]}
    assert api._eve_identification is None
    assert api._eve_identification_candidate is None


def test_identification_confirmation_retains_candidate_when_atomic_write_fails(
    tmp_path, monkeypatch
):
    api = build(tmp_path, monkeypatch)
    _pending_identification(api)

    def fail_write(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(api_mod.settings_mod, "update_section", fail_write)

    result = api.eve_settings_identification_confirm("10", "20", "Login")

    assert result == {
        "applied": False,
        "persisted": False,
        "error": "Could not save this account identity.",
    }
    assert api._eve_section()["account_names"] == {}
    assert api._eve_section()["account_characters"] == {}
    assert api._eve_identification is not None
    assert api._eve_identification_candidate == ("10", ("20",))


def test_identification_confirmation_accepts_its_existing_name_and_link_as_a_noop(
    tmp_path, monkeypatch
):
    api = build(tmp_path, monkeypatch)
    section = api._eve_section()
    section["account_names"] = {"10": "Login"}
    section["account_characters"] = {"10": ["20"]}
    _pending_identification(api)
    monkeypatch.setattr(
        api_mod.settings_mod,
        "update_section",
        lambda *args, **kwargs: pytest.fail("an unchanged link must not be written"),
    )

    assert (
        api.eve_settings_identification_confirm("10", "20", "Login")["applied"] is True
    )
    assert api._eve_identification is None
    assert api._eve_identification_candidate is None


def test_identification_confirmation_refuses_a_fourth_link_without_moving_it(
    tmp_path, monkeypatch
):
    api = build(tmp_path, monkeypatch)
    section = api._eve_section()
    section["account_names"] = {"10": "Destination", "11": "Source"}
    section["account_characters"] = {"10": ["21", "22", "23"], "11": ["20"]}
    _pending_identification(api)

    result = api.eve_settings_identification_confirm("10", "20", "Destination")

    assert result["applied"] is False
    assert api._eve_section()["account_characters"] == {
        "10": ["21", "22", "23"],
        "11": ["20"],
    }


def test_identification_confirmation_moves_an_owned_character_only_when_room_exists(
    tmp_path, monkeypatch
):
    api = build(tmp_path, monkeypatch)
    section = api._eve_section()
    section["account_names"] = {"10": "Destination", "11": "Source"}
    section["account_characters"] = {"10": ["21"], "11": ["20"]}
    _pending_identification(api)

    assert (
        api.eve_settings_identification_confirm("10", "20", "Destination")["applied"]
        is True
    )
    assert api._eve_section()["account_characters"] == {"10": ["21", "20"]}


def test_identification_confirmation_cannot_be_consumed_twice(tmp_path, monkeypatch):
    api = build(tmp_path, monkeypatch)
    _pending_identification(api)
    original = api_mod.settings_mod.update_section
    writing = threading.Event()
    release_write = threading.Event()
    results = []

    def blocking_write(data, section, values):
        writing.set()
        assert release_write.wait(5), "test did not release the atomic write"
        return original(data, section, values)

    monkeypatch.setattr(api_mod.settings_mod, "update_section", blocking_write)
    first = threading.Thread(
        target=lambda: results.append(
            api.eve_settings_identification_confirm("10", "20", "Login")
        )
    )
    first.start()
    assert writing.wait(5), "confirmation never reached the settings write"

    results.append(api.eve_settings_identification_confirm("10", "20", "Login"))
    release_write.set()
    first.join(5)

    assert not first.is_alive()
    assert [result["applied"] for result in results].count(True) == 1
    assert [result["applied"] for result in results].count(False) == 1
    assert api._eve_section()["account_names"] == {"10": "Login"}
    assert api._eve_section()["account_characters"] == {"10": ["20"]}


def test_identification_proposes_only_one_changed_account(tmp_path, monkeypatch):
    profile = eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    api = build(tmp_path, monkeypatch)
    api._eve_section()["root"] = str(tmp_path / "EVE")
    api._eve_names.names[20] = "Aiga Otsolen"

    assert api.eve_settings_identification_start()["status"] == "watching"
    (profile / "core_user_10.dat").write_bytes(b"changed account")
    (profile / "core_char_20.dat").write_bytes(b"changed character")
    result = api.eve_settings_identification_check()

    assert result["status"] == "candidate"
    assert result["account"]["id"] == "10"
    assert result["characters"] == [{"id": "20", "name": "Aiga Otsolen"}]


def test_identification_waits_until_eve_is_closed(tmp_path, monkeypatch):
    eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    api = build(tmp_path, monkeypatch)
    api._eve_section()["root"] = str(tmp_path / "EVE")
    api.eve_settings_identification_start()
    api._eve_client_running_strict = lambda: True

    result = api.eve_settings_identification_check()

    assert result["status"] == "watching"
    assert "still running" in result["error"]


def test_identification_never_guesses_between_changed_accounts(tmp_path, monkeypatch):
    profile = eve_tree(
        tmp_path,
        files=("core_user_10.dat", "core_user_11.dat", "core_char_20.dat"),
    )
    api = build(tmp_path, monkeypatch)
    api._eve_section()["root"] = str(tmp_path / "EVE")
    api.eve_settings_identification_start()
    for name in ("core_user_10.dat", "core_user_11.dat", "core_char_20.dat"):
        (profile / name).write_bytes(b"changed with a different size " + name.encode())

    assert api.eve_settings_identification_check()["status"] == "ambiguous"


def test_identification_blocks_mutations_until_cancelled(tmp_path, monkeypatch):
    profile = eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api.eve_settings_identification_start()

    assert api.eve_settings_backup(str(profile), "profile") is False
    assert api.eve_settings_identification_cancel() is True
    assert api.eve_settings_backup(str(profile), "profile") is True


def test_lowering_retention_confirms_exact_count_and_keeps_manual_backups(
    tmp_path, monkeypatch
):
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    store = paths.eve_settings_backup_dir()
    source = profile / "core_char_1.dat"
    for second in range(3):
        api_mod.evesettings_backup.create_file_backup(
            store,
            source,
            origin="auto",
            now=api_mod.datetime.datetime(
                2026, 1, 1, 0, 0, second, tzinfo=api_mod.datetime.UTC
            ),
        )
    manual = api_mod.evesettings_backup.create_file_backup(
        store,
        source,
        origin="manual",
        now=api_mod.datetime.datetime(2026, 1, 1, 0, 1, tzinfo=api_mod.datetime.UTC),
    )
    asked = []
    api._eve_confirm = lambda title, body, **kwargs: asked.append(body) or True

    result = api.eve_settings_set_auto_keep(1)

    assert result["accepted"] is True
    assert "delete 2 older automatic backups" in asked[0]
    assert api._eve_section()["auto_keep"] == 1
    assert manual.exists()


@pytest.mark.parametrize("value", [0, 101, True, 1.5, "1.5", "nope"])
def test_invalid_retention_is_refused_without_starting_a_worker(
    tmp_path, monkeypatch, value
):
    api = build(tmp_path, monkeypatch)
    result = api.eve_settings_set_auto_keep(value)
    assert result == {
        "accepted": False,
        "value": 10,
        "error": "Enter a number from 1 to 100.",
    }


def test_declining_retention_deletion_changes_nothing(tmp_path, monkeypatch):
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch, answer=False)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    store = paths.eve_settings_backup_dir()
    source = profile / "core_char_1.dat"
    for second in range(2):
        api_mod.evesettings_backup.create_file_backup(
            store,
            source,
            origin="auto",
            now=api_mod.datetime.datetime(
                2026, 1, 1, 0, 0, second, tzinfo=api_mod.datetime.UTC
            ),
        )

    api.eve_settings_set_auto_keep(1)

    assert api._eve_section()["auto_keep"] == 10
    assert len(api.eve_settings_state()["backups"]) == 2


# --- detecting the root, the way Folders detects OBS's ----------------------
#
# Profiles 4: `Detect` existed in Settings > Folders AND on first run, for a
# folder shallower and better known than this one, while the EVE settings
# root -- the folder the product is named for -- got `Choose folder...`
# alone. These cover the three answers the probe can give.


def test_detect_root_finds_the_default_location_and_commits_it(tmp_path, monkeypatch):
    """Commits, rather than suggesting. Its neighbour `Choose folder...`
    writes the moment the dialog closes, and a Detect that only proposed
    would be two behaviours for one question on one screen."""
    api = build(tmp_path, monkeypatch)
    api._alert = fakes.Alerts()
    root = tmp_path / "CCP" / "EVE"
    (root / "server_tranquility" / "settings_Default").mkdir(parents=True)

    found = api.eve_settings_detect_root()

    assert found == str(root)
    assert api._state.settings["eve_settings"]["root"] == str(root)
    assert api._alert.raised == []


def test_detect_root_names_where_it_looked_when_there_is_nothing_there(
    tmp_path, monkeypatch
):
    """The path is the useful half of the answer: a user whose EVE lives
    elsewhere learns where we looked, which is what tells them
    `Choose folder...` is the way out."""
    api = build(tmp_path, monkeypatch)
    api._alert = fakes.Alerts()

    found = api.eve_settings_detect_root()

    assert found == ""
    ((kind, _title, body),) = api._alert.raised
    assert kind == "info"
    assert str(tmp_path / "CCP" / "EVE") in body
    assert "Choose folder" in body
    # Nothing written: the section keeps its unset default.
    assert api._state.settings["eve_settings"]["root"] is None


def test_detect_root_reports_agreement_rather_than_rewriting_the_selection(
    tmp_path, monkeypatch
):
    """detect_folder's rule, and the reason it compares before writing. The
    write path clears server and profile, so a detection that merely agrees
    with what is already set would throw away a selection for no reason."""
    api = build(tmp_path, monkeypatch)
    api._alert = fakes.Alerts()
    root = tmp_path / "CCP" / "EVE"
    (root / "server_tranquility" / "settings_Default").mkdir(parents=True)
    settings.update_section(
        api._state.settings,
        "eve_settings",
        {"root": str(root), "server": "tranquility", "profile": "Default"},
    )

    found = api.eve_settings_detect_root()

    assert found == ""
    ((_kind, _title, body),) = api._alert.raised
    assert "Already set" in body
    # The selection survived.
    section = api._state.settings["eve_settings"]
    assert section["server"] == "tranquility"
    assert section["profile"] == "Default"


def _fake_codec(monkeypatch, doc, *, available=True):
    """Route the seam at codec.read_document/write_document to an in-memory doc."""
    from wingman.evesettings import codec as codec_mod
    from wingman.ui import api as api_mod

    store = {"doc": doc, "written": []}

    def read_document(path, **kw):
        return codec_mod.Document(doc=store["doc"], had_crc=False)

    def write_document(path, document, *, backup, **kw):
        backup(path)
        store["written"].append((path, document))

    monkeypatch.setattr(api_mod.evesettings_codec, "read_document", read_document)
    monkeypatch.setattr(api_mod.evesettings_codec, "write_document", write_document)
    monkeypatch.setattr(
        api_mod.evesettings_codec, "codec_available", lambda **kw: available
    )
    return store


FORMATION_DOC = {
    "bytes:ui": {
        "bytes:probescanning.customFormations": {
            "tuple": [
                "long:1",
                {
                    "int:0": {
                        "tuple": [
                            "utf8:Test",
                            [{"tuple": [{"tuple": [1.0, 2.0, 3.0]}, 4.0]}],
                        ]
                    },
                    "int:-4": {"tuple": ["bytes:tempFormation", []]},
                },
            ]
        },
        "bytes:probescanning.selectedFormationID": {"tuple": ["long:1", 0]},
    }
}


def test_state_reports_whether_formations_are_available(tmp_path, monkeypatch):
    api = build(tmp_path, monkeypatch)
    _fake_codec(monkeypatch, {}, available=False)
    state = api.eve_settings_state()
    assert state["formations_available"] is False
    assert state["selective_copy_available"] is False
    _fake_codec(monkeypatch, {}, available=True)
    state = api.eve_settings_state()
    assert state["formations_available"] is True
    assert state["selective_copy_available"] is True


def test_formations_read_returns_the_user_formations_in_meters(tmp_path, monkeypatch):
    api, account = account_setup(tmp_path, monkeypatch)
    _fake_codec(monkeypatch, FORMATION_DOC)
    got = api.eve_settings_formations(str(account))
    assert got["ok"] is True
    assert got["name"] == "Account 1 · Not identified"
    assert got["formations"] == [
        {
            "id": 0,
            "name": "Test",
            "probes": [{"x": 1.0, "y": 2.0, "z": 3.0, "range": 4.0}],
        }
    ]


def test_formations_read_refuses_a_path_outside_the_root(tmp_path, monkeypatch):
    api, _account = account_setup(tmp_path, monkeypatch)
    _fake_codec(monkeypatch, FORMATION_DOC)
    outside = tmp_path / "elsewhere" / "core_user_9.dat"
    outside.parent.mkdir()
    outside.write_bytes(b"")
    got = api.eve_settings_formations(str(outside))
    assert got["ok"] is False and "outside" in got["error"]


def test_formations_read_refuses_a_character_file(tmp_path, monkeypatch):
    api, char = account_setup(tmp_path, monkeypatch, name="core_char_1.dat")
    _fake_codec(monkeypatch, FORMATION_DOC)
    got = api.eve_settings_formations(str(char))
    assert got["ok"] is False and "account" in got["error"]


def test_formations_read_reports_a_codec_failure_as_an_error_not_an_exception(
    tmp_path, monkeypatch
):
    from wingman.evesettings import codec as codec_mod
    from wingman.ui import api as api_mod

    api, account = account_setup(tmp_path, monkeypatch)

    def boom(path, **kw):
        raise codec_mod.CodecError("bad header")

    monkeypatch.setattr(api_mod.evesettings_codec, "read_document", boom)
    got = api.eve_settings_formations(str(account))
    assert got == {"ok": False, "error": "bad header"}

    # A document that decodes cleanly but is not something read_formations
    # understands must not open the editor on a partial parse either --
    # write_formations would rebuild the key from whatever was returned and
    # silently drop the part it could not read.
    _fake_codec(monkeypatch, FORMATION_DOC)

    def refuse(doc):
        raise ValueError("This file has a formation entry Wingman does not understand.")

    monkeypatch.setattr(api_mod.evesettings_formations, "read_formations", refuse)
    got = api.eve_settings_formations(str(account))
    assert got == {
        "ok": False,
        "error": "This file has a formation entry Wingman does not understand.",
    }


def test_save_backs_up_writes_and_reports_done(tmp_path, monkeypatch):
    api, account = account_setup(tmp_path, monkeypatch)
    store = _fake_codec(monkeypatch, FORMATION_DOC)
    api._eve_client_running = lambda: False
    backups = []
    api._eve_auto_backup = lambda p: backups.append(p)
    accepted = api.eve_settings_save_formations(
        str(account),
        [{"id": None, "name": "New", "probes": [{"x": 1, "y": 0, "z": 0, "range": 2}]}],
    )
    assert accepted is True
    assert backups == [account]
    ((path, document),) = store["written"]
    assert path == account
    entries = document.doc["bytes:ui"]["bytes:probescanning.customFormations"]["tuple"][
        1
    ]
    assert sorted(entries) == ["int:-4", "int:1"]
    assert entries["int:1"]["tuple"][0] == "utf8:New"
    assert any(
        "onEveSettingsDone" in js and '"ok": true' in js for js in api._window.calls
    )


def test_save_is_refused_when_the_strict_running_probe_fails(tmp_path, monkeypatch):
    api, account = account_setup(tmp_path, monkeypatch)
    store = _fake_codec(monkeypatch, FORMATION_DOC)
    api._alert = fakes.Alerts()
    backups = []
    api._eve_auto_backup = lambda path: backups.append(path)

    def boom():
        raise OSError("window station unavailable")

    api._eve_client_running_strict = boom
    api.eve_settings_save_formations(str(account), [])

    assert store["written"] == [] and backups == []
    assert len(api._alert.raised) == 1
    assert "Close EVE" in api._alert.raised[0][2]


def test_save_is_refused_while_an_eve_client_is_running(tmp_path, monkeypatch):
    api, account = account_setup(tmp_path, monkeypatch)
    store = _fake_codec(monkeypatch, FORMATION_DOC)
    api._eve_client_running_strict = lambda: True
    api.eve_settings_save_formations(str(account), [])
    assert store["written"] == []
    assert any("Close EVE" in js for js in api._window.calls)
    assert any(
        "onEveSettingsDone" in js and '"ok": false' in js for js in api._window.calls
    )


def test_save_rejects_an_invalid_formation_before_touching_the_file(
    tmp_path, monkeypatch
):
    api, account = account_setup(tmp_path, monkeypatch)
    store = _fake_codec(monkeypatch, FORMATION_DOC)
    api._eve_client_running = lambda: False
    backups = []
    api._eve_auto_backup = lambda p: backups.append(p)
    api.eve_settings_save_formations(
        str(account), [{"id": None, "name": "", "probes": []}]
    )
    assert store["written"] == [] and backups == []
    assert any("needs a name" in js for js in api._window.calls)


def test_save_holds_and_releases_the_mutation_lock(tmp_path, monkeypatch):
    api, account = account_setup(tmp_path, monkeypatch)
    _fake_codec(monkeypatch, FORMATION_DOC)
    api._eve_client_running = lambda: False
    api.eve_settings_save_formations(str(account), [])
    assert api._eve_mutation.acquire(blocking=False)
    api._eve_mutation.release()


# ---- whole-profile copy ---------------------------------------------------


def copy_profile_setup(tmp_path, monkeypatch, others=()):
    """A root holding settings_Default (the source) plus named siblings.

    The EVE-client probe is stubbed CLOSED here for every copy test that
    does not care about it. Left real, it short-circuits to CLOSED off
    Windows (`sys.platform != "win32"`) and enumerates the developer's OWN
    live windows on Windows -- so the whole profile-copy suite passed on
    Linux and refused with "Copy not started" on a Windows machine that
    happened to have any window titled "EVE..." open. That is test
    isolation, not a softened rule: the production probe stays fail-closed,
    and the running/unknown refusals are asserted by the tests that override
    this stub deliberately (see probe_returning).
    """
    source = eve_tree(tmp_path)
    for name in others:
        other = source.parent / f"{tree.PROFILE_PREFIX}{name}"
        other.mkdir()
        (other / "core_char_9.dat").write_bytes(b"old-9")
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api._alert = fakes.Alerts()
    monkeypatch.setattr(
        discovery_mod,
        "probe_eve_client_state",
        probe_returning(discovery_mod.EveClientState.CLOSED),
    )
    return api, source


def probe_returning(*states):
    """A probe_eve_client_state double answering one state per call."""
    answers = list(states)

    def probe(*args, **kwargs):
        state = answers.pop(0) if len(answers) > 1 else answers[0]
        return discovery_mod.EveClientProbe(state=state)

    return probe


def watch(order, label, func):
    def wrapper(*args, **kwargs):
        order.append(label)
        return func(*args, **kwargs)

    return wrapper


def order_spies(api, monkeypatch):
    """Record the whole orchestration sequence, real behaviour intact."""
    order = []
    api._eve_discover = watch(order, "discover", api._eve_discover)
    api._eve_persist_selection = watch(order, "persist", api._eve_persist_selection)
    api._eve_confirm = watch(order, "confirm", api._eve_confirm)
    api._eve_prune = watch(order, "prune", api._eve_prune)
    api._eve_done = watch(order, "done", api._eve_done)
    for module, name, label in (
        (api_mod.evesettings_profilecopy, "prepare_copy", "prepare"),
        (api_mod.evesettings_profilecopy, "stage_copy", "stage"),
        (api_mod.evesettings_profilecopy, "publish_new", "publish"),
        (api_mod.evesettings_profilecopy, "publish_replacement", "publish"),
        (api_mod.evesettings_backup, "create_profile_backup", "backup"),
        (discovery_mod, "probe_eve_client_state", "probe"),
    ):
        monkeypatch.setattr(module, name, watch(order, label, getattr(module, name)))
    return order


def stages_left(server):
    return [
        entry.name
        for entry in server.iterdir()
        if entry.name.startswith(api_mod.evesettings_profilecopy.STAGE_PREFIX)
    ]


def test_profile_copy_returns_an_inline_refusal_when_another_operation_runs(
    tmp_path, monkeypatch
):
    """The page renders this beside its own button, so the refusal is the
    return value rather than an alert -- and it is decided before anything
    reads the tree, exactly as the character copy's busy check is."""
    api, source = copy_profile_setup(tmp_path, monkeypatch)
    api._eve_discover = lambda: pytest.fail("busy must not inspect the tree")
    assert api._eve_mutation.acquire(blocking=False)
    try:
        assert api.eve_settings_copy_profile(str(source), "new", "Fleet") == {
            "accepted": False,
            "error": "Another Profiles operation is running.",
        }
    finally:
        api._eve_mutation.release()
    assert not (source.parent / "settings_Fleet").exists()


def test_profile_copy_is_refused_while_account_identification_is_active(
    tmp_path, monkeypatch
):
    api, source = copy_profile_setup(tmp_path, monkeypatch)
    api._eve_identification = object()
    result = api.eve_settings_copy_profile(str(source), "new", "Fleet")
    assert result == {
        "accepted": False,
        "error": "Finish or cancel account identification first.",
    }
    assert not (source.parent / "settings_Fleet").exists()
    assert api._eve_mutation.acquire(blocking=False)
    api._eve_mutation.release()


@pytest.mark.parametrize(
    ("mode", "destination", "fragment"),
    [
        ("new", "Fleet/1", "cannot contain /"),
        ("new", "   ", "cannot be empty"),
        ("new", "Default", "already exists"),
        ("new", "settings_Fleet", "without the settings_ prefix"),
        ("replace", "nowhere", "not on the selected server"),
        ("sideways", "Fleet", "Unknown copy mode"),
    ],
)
def test_profile_copy_refuses_an_invalid_request_before_starting_a_worker(
    tmp_path, monkeypatch, mode, destination, fragment
):
    api, source = copy_profile_setup(tmp_path, monkeypatch)
    api._spawn = lambda **kwargs: pytest.fail("a refused request starts no worker")
    result = api.eve_settings_copy_profile(str(source), mode, destination)
    assert result["accepted"] is False
    assert fragment in result["error"]
    assert sorted(p.name for p in source.parent.iterdir()) == ["settings_Default"]
    assert api._eve_mutation.acquire(blocking=False)
    api._eve_mutation.release()


def test_profile_copy_refuses_a_stale_expected_source(tmp_path, monkeypatch):
    """The page may have rendered one source while a separate selection
    request was still in flight. The token it showed must still name the
    freshly discovered profile."""
    api, source = copy_profile_setup(tmp_path, monkeypatch, others=("Backup",))
    result = api.eve_settings_copy_profile(
        str(source.parent / "settings_Backup"), "new", "Fleet"
    )
    assert result["accepted"] is False
    assert "selected profile changed" in result["error"]
    assert not (source.parent / "settings_Fleet").exists()


def test_profile_copy_aborts_untouched_when_the_canonical_save_fails(
    tmp_path, monkeypatch
):
    """A legacy deep root is canonicalized before any file is touched, and
    a copy whose selection could not be saved must not proceed: the tree it
    validated against is not the one that would be persisted."""
    api, source = copy_profile_setup(tmp_path, monkeypatch)
    api._spawn = lambda **kwargs: pytest.fail("a refused request starts no worker")

    def refuse(*args, **kwargs):
        raise OSError("settings.json is read-only")

    monkeypatch.setattr(api_mod.settings_mod, "update_section", refuse)
    result = api.eve_settings_copy_profile(str(source), "new", "Fleet")
    assert result["accepted"] is False
    assert "nothing was copied" in result["error"]
    assert sorted(p.name for p in source.parent.iterdir()) == ["settings_Default"]
    assert api._eve_mutation.acquire(blocking=False)
    api._eve_mutation.release()


def test_profile_copy_releases_the_lock_when_the_worker_cannot_start(
    tmp_path, monkeypatch
):
    """Only the worker releases the lock, so a worker that never started
    would refuse every later Profiles operation for good."""
    source = eve_tree(tmp_path)

    class Refuses:
        def __init__(self, **kwargs):
            pass

        def start(self):
            raise RuntimeError("can't start new thread")

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    state = api_mod.AppState(
        recording_dir=tmp_path, settings=settings.load(tmp_path / "s.json")
    )
    api = api_mod.Api(state, spawn=Refuses)
    api._window = FakeWindow()
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    result = api.eve_settings_copy_profile(str(source), "new", "Fleet")
    assert result == {
        "accepted": False,
        "error": "Profile copy could not be started.",
    }
    assert api._eve_mutation.acquire(blocking=False) is True
    api._eve_mutation.release()


def test_creating_a_profile_copies_every_recognized_file_and_selects_it(
    tmp_path, monkeypatch
):
    api, source = copy_profile_setup(tmp_path, monkeypatch)
    api._eve_confirm = lambda *args, **kwargs: pytest.fail("creation never confirms")
    monkeypatch.setattr(
        api_mod.evesettings_backup,
        "create_profile_backup",
        lambda *args, **kwargs: pytest.fail("creation overwrites nothing"),
    )
    sent = fakes.record_pushes(api)

    result = api.eve_settings_copy_profile(str(source), "new", "Fleet")

    created = source.parent / "settings_Fleet"
    assert result == {"accepted": True, "error": None}
    assert sorted(p.name for p in created.iterdir()) == [
        "core_char_1.dat",
        "core_char_2.dat",
    ]
    assert (created / "core_char_1.dat").read_bytes() == (
        source / "core_char_1.dat"
    ).read_bytes()
    assert stages_left(source.parent) == []
    stored = settings.load(tmp_path / "FlyGD Wingman" / "settings.json")
    assert stored["eve_settings"]["profile"] == str(created)
    assert fakes.payloads(sent, "onEveSettingsDone") == [
        {
            "ok": True,
            "operation": "profile_copy",
            "mode": "new",
            "published": True,
            "selection_persisted": True,
            "error": None,
        }
    ]
    assert api._eve_mutation.acquire(blocking=False)
    api._eve_mutation.release()


def test_a_created_profile_survives_a_failed_selection_save(tmp_path, monkeypatch):
    """Publication and remembering the selection are separate outcomes. The
    profile exists, so a retry must not imply it was not created."""
    api, source = copy_profile_setup(tmp_path, monkeypatch)
    real_update = api_mod.settings_mod.update_section
    calls = []

    def flaky(*args, **kwargs):
        calls.append(args)
        if len(calls) > 1:
            raise OSError("settings.json is read-only")
        return real_update(*args, **kwargs)

    monkeypatch.setattr(api_mod.settings_mod, "update_section", flaky)
    sent = fakes.record_pushes(api)

    result = api.eve_settings_copy_profile(str(source), "new", "Fleet")

    created = source.parent / "settings_Fleet"
    assert result == {"accepted": True, "error": None}
    assert (created / "core_char_1.dat").exists()
    stored = settings.load(tmp_path / "FlyGD Wingman" / "settings.json")
    assert stored["eve_settings"]["profile"] == str(source)
    ((payload,)) = fakes.payloads(sent, "onEveSettingsDone")
    assert payload["ok"] is True
    assert payload["published"] is True
    assert payload["selection_persisted"] is False
    assert "Select it from Profile" in payload["error"]
    assert api._alert.raised[0][0] == "warning"
    assert "Select it from Profile" in api._alert.raised[0][2]


def test_profile_copy_runs_its_steps_in_the_documented_order(tmp_path, monkeypatch):
    api, source = copy_profile_setup(tmp_path, monkeypatch, others=("Backup",))
    order = order_spies(api, monkeypatch)

    result = api.eve_settings_copy_profile(
        str(source), "replace", str(source.parent / "settings_Backup")
    )

    assert result == {"accepted": True, "error": None}
    assert order == [
        "discover",
        "prepare",
        "persist",
        "probe",
        "stage",
        "confirm",
        "probe",
        "backup",
        "publish",
        "prune",
        "done",
    ]


def test_replacing_a_profile_copies_the_recognized_set_and_keeps_the_source_selected(
    tmp_path, monkeypatch
):
    api, source = copy_profile_setup(tmp_path, monkeypatch, others=("Backup",))
    destination = source.parent / "settings_Backup"
    (destination / "notes.txt").write_text("mine", encoding="utf-8")
    asked = []
    api._eve_confirm = lambda title, body, **kw: asked.append((title, body, kw)) or True
    sent = fakes.record_pushes(api)

    result = api.eve_settings_copy_profile(str(source), "replace", str(destination))

    assert result == {"accepted": True, "error": None}
    assert sorted(p.name for p in destination.iterdir()) == [
        "core_char_1.dat",
        "core_char_2.dat",
        "notes.txt",
    ]
    assert (destination / "core_char_1.dat").read_bytes() == (
        source / "core_char_1.dat"
    ).read_bytes()
    assert (destination / "notes.txt").read_text(encoding="utf-8") == "mine"
    assert stages_left(source.parent) == []
    ((_title, body, kw),) = asked
    assert "Default" in body and "Backup" in body and "backed up" in body
    assert kw["destructive"] is True
    stored = settings.load(tmp_path / "FlyGD Wingman" / "settings.json")
    assert stored["eve_settings"]["profile"] == str(source)
    ((payload,)) = fakes.payloads(sent, "onEveSettingsDone")
    assert payload == {
        "ok": True,
        "operation": "profile_copy",
        "mode": "replace",
        "published": True,
        "selection_persisted": True,
        "error": None,
    }
    archives = list(paths.eve_settings_backup_dir().glob("*.zip"))
    assert len(archives) == 1


def test_a_declined_replacement_creates_no_backup_and_changes_nothing(
    tmp_path, monkeypatch
):
    api, source = copy_profile_setup(tmp_path, monkeypatch, others=("Backup",))
    destination = source.parent / "settings_Backup"
    api._eve_confirm = lambda *args, **kwargs: False
    monkeypatch.setattr(
        api_mod.evesettings_backup,
        "create_profile_backup",
        lambda *args, **kwargs: pytest.fail("a declined copy backs nothing up"),
    )
    prunes = []
    api._eve_prune = lambda *args, **kwargs: prunes.append(args)
    sent = fakes.record_pushes(api)

    api.eve_settings_copy_profile(str(source), "replace", str(destination))

    assert sorted(p.name for p in destination.iterdir()) == ["core_char_9.dat"]
    assert stages_left(source.parent) == []
    assert prunes == []
    ((payload,)) = fakes.payloads(sent, "onEveSettingsDone")
    assert payload["ok"] is False and payload["published"] is False
    # Nothing was published, and the source the page still shows selected is
    # the one persisted when the request was accepted.
    assert payload["selection_persisted"] is True
    assert api._eve_mutation.acquire(blocking=False)
    api._eve_mutation.release()


@pytest.mark.parametrize(
    "failure",
    [
        "declined",
        "eve started",
        "backup",
        "rollback restored",
        "rollback failed",
        "raised",
    ],
)
def test_a_replacement_that_never_publishes_still_reports_the_retained_selection(
    tmp_path, monkeypatch, failure
):
    """Replacement never moves the selection, and the source it keeps was
    persisted with the whole canonical triple before the worker started.
    Reporting selection_persisted=False on these paths would tell the page
    Wingman had forgotten a selection that is sitting in settings.json."""
    api, source = copy_profile_setup(tmp_path, monkeypatch, others=("Backup",))
    destination = source.parent / "settings_Backup"

    def refuse(*args, **kwargs):
        raise OSError("the backup store is read-only")

    def explode(*args, **kwargs):
        raise RuntimeError("boom")

    if failure == "declined":
        api._eve_confirm = lambda *args, **kwargs: False
    elif failure == "eve started":
        monkeypatch.setattr(
            discovery_mod,
            "probe_eve_client_state",
            probe_returning(
                discovery_mod.EveClientState.CLOSED,
                discovery_mod.EveClientState.RUNNING,
            ),
        )
    elif failure == "backup":
        monkeypatch.setattr(api_mod.evesettings_backup, "create_profile_backup", refuse)
    elif failure == "rollback restored":
        failing_publication(monkeypatch, destination)
    elif failure == "rollback failed":
        failing_publication(monkeypatch, destination)
        monkeypatch.setattr(api_mod.evesettings_backup, "restore", refuse)
    else:
        # A worker failure after acceptance that is not one of the handled
        # arms: the outer catch must report the same retained selection.
        monkeypatch.setattr(
            api_mod.evesettings_profilecopy, "publish_replacement", explode
        )
    sent = fakes.record_pushes(api)

    api.eve_settings_copy_profile(str(source), "replace", str(destination))

    ((payload,)) = fakes.payloads(sent, "onEveSettingsDone")
    assert payload["ok"] is False and payload["published"] is False
    assert payload["selection_persisted"] is True
    stored = settings.load(tmp_path / "FlyGD Wingman" / "settings.json")
    assert stored["eve_settings"]["profile"] == str(source)
    assert api._eve_mutation.acquire(blocking=False)
    api._eve_mutation.release()


@pytest.mark.parametrize(
    ("state", "fragment"),
    [
        (discovery_mod.EveClientState.RUNNING, "EVE is running"),
        (discovery_mod.EveClientState.UNKNOWN, "could not verify"),
    ],
)
def test_profile_copy_refuses_unless_the_probe_proves_eve_is_closed(
    tmp_path, monkeypatch, state, fragment
):
    api, source = copy_profile_setup(tmp_path, monkeypatch)
    monkeypatch.setattr(discovery_mod, "probe_eve_client_state", probe_returning(state))
    monkeypatch.setattr(
        api_mod.evesettings_profilecopy,
        "stage_copy",
        lambda *args, **kwargs: pytest.fail("a refused copy stages nothing"),
    )
    sent = fakes.record_pushes(api)

    result = api.eve_settings_copy_profile(str(source), "new", "Fleet")

    assert result == {"accepted": True, "error": None}
    assert not (source.parent / "settings_Fleet").exists()
    assert len(api._alert.raised) == 1
    assert fragment in api._alert.raised[0][2]
    ((payload,)) = fakes.payloads(sent, "onEveSettingsDone")
    assert payload["ok"] is False and payload["published"] is False
    # New mode is the one with a destination selection to save, and it
    # never got as far as making one.
    assert payload["selection_persisted"] is False
    assert fragment in payload["error"]
    assert api._eve_mutation.acquire(blocking=False)
    api._eve_mutation.release()


def test_a_replacement_probes_again_after_the_confirmation(tmp_path, monkeypatch):
    """EVE can start while the confirmation is on screen, and everything
    after it writes into the destination."""
    api, source = copy_profile_setup(tmp_path, monkeypatch, others=("Backup",))
    destination = source.parent / "settings_Backup"
    monkeypatch.setattr(
        discovery_mod,
        "probe_eve_client_state",
        probe_returning(
            discovery_mod.EveClientState.CLOSED, discovery_mod.EveClientState.RUNNING
        ),
    )
    monkeypatch.setattr(
        api_mod.evesettings_backup,
        "create_profile_backup",
        lambda *args, **kwargs: pytest.fail("a refused copy backs nothing up"),
    )

    api.eve_settings_copy_profile(str(source), "replace", str(destination))

    assert sorted(p.name for p in destination.iterdir()) == ["core_char_9.dat"]
    assert stages_left(source.parent) == []
    assert "EVE is running" in api._alert.raised[0][2]
    assert api._eve_mutation.acquire(blocking=False)
    api._eve_mutation.release()


def test_a_failed_destination_backup_leaves_the_destination_unchanged(
    tmp_path, monkeypatch
):
    api, source = copy_profile_setup(tmp_path, monkeypatch, others=("Backup",))
    destination = source.parent / "settings_Backup"

    def refuse(*args, **kwargs):
        raise OSError("the backup store is read-only")

    monkeypatch.setattr(api_mod.evesettings_backup, "create_profile_backup", refuse)
    monkeypatch.setattr(
        api_mod.evesettings_profilecopy,
        "publish_replacement",
        lambda *args, **kwargs: pytest.fail("publication needs a backup first"),
    )
    prunes = []
    api._eve_prune = lambda *args, **kwargs: prunes.append(args)
    sent = fakes.record_pushes(api)

    api.eve_settings_copy_profile(str(source), "replace", str(destination))

    assert sorted(p.name for p in destination.iterdir()) == ["core_char_9.dat"]
    assert (destination / "core_char_9.dat").read_bytes() == b"old-9"
    assert stages_left(source.parent) == []
    assert prunes == []
    assert api._alert.raised[0][1] == "Destination unchanged"
    ((payload,)) = fakes.payloads(sent, "onEveSettingsDone")
    assert payload["ok"] is False and payload["published"] is False
    assert payload["selection_persisted"] is True
    assert api._eve_mutation.acquire(blocking=False)
    api._eve_mutation.release()


def failing_publication(monkeypatch, destination):
    """Break the second per-file replacement, so publication fails after it
    has already changed the destination."""
    real_copy = api_mod.evesettings_profilecopy.atomicio.copy_atomic

    def flaky(source, target, **kwargs):
        if Path(target).parent == destination and Path(target).name.endswith("2.dat"):
            raise OSError("the destination went away")
        return real_copy(source, target, **kwargs)

    monkeypatch.setattr(api_mod.evesettings_profilecopy.atomicio, "copy_atomic", flaky)


def test_a_failed_publication_rolls_back_from_the_backup_it_just_took(
    tmp_path, monkeypatch
):
    api, source = copy_profile_setup(tmp_path, monkeypatch, others=("Backup",))
    destination = source.parent / "settings_Backup"
    archives = []
    real_backup = api_mod.evesettings_backup.create_profile_backup

    def record(*args, **kwargs):
        archives.append(real_backup(*args, **kwargs))
        return archives[-1]

    restores = []
    real_restore = api_mod.evesettings_backup.restore

    def watched_restore(store, archive, root, **kwargs):
        restores.append((Path(archive), kwargs))
        return real_restore(store, archive, root, **kwargs)

    monkeypatch.setattr(api_mod.evesettings_backup, "create_profile_backup", record)
    monkeypatch.setattr(api_mod.evesettings_backup, "restore", watched_restore)
    failing_publication(monkeypatch, destination)
    prunes = []
    api._eve_prune = lambda *args, **kwargs: prunes.append(args)
    sent = fakes.record_pushes(api)

    api.eve_settings_copy_profile(str(source), "replace", str(destination))

    assert sorted(p.name for p in destination.iterdir()) == ["core_char_9.dat"]
    assert (destination / "core_char_9.dat").read_bytes() == b"old-9"
    assert restores == [(archives[0], {"backup_current": False})]
    assert stages_left(source.parent) == []
    # Settled: the destination is back to what it was, so retention may run.
    assert len(prunes) == 1
    assert api._alert.raised[0][1] == "Replacement failed"
    assert "restored" in api._alert.raised[0][2]
    ((payload,)) = fakes.payloads(sent, "onEveSettingsDone")
    assert payload["ok"] is False and payload["published"] is False
    assert payload["selection_persisted"] is True
    assert "restored" in payload["error"]
    assert api._eve_mutation.acquire(blocking=False)
    api._eve_mutation.release()


def test_a_failed_rollback_names_the_backup_and_prunes_nothing(tmp_path, monkeypatch):
    """The durable archive is the only way back, so it is named in the
    message and retention does not get to consider deleting anything."""
    api, source = copy_profile_setup(tmp_path, monkeypatch, others=("Backup",))
    destination = source.parent / "settings_Backup"
    archives = []
    real_backup = api_mod.evesettings_backup.create_profile_backup

    def record(*args, **kwargs):
        archives.append(real_backup(*args, **kwargs))
        return archives[-1]

    def refuse_restore(*args, **kwargs):
        raise OSError("the archive could not be read")

    monkeypatch.setattr(api_mod.evesettings_backup, "create_profile_backup", record)
    monkeypatch.setattr(api_mod.evesettings_backup, "restore", refuse_restore)
    failing_publication(monkeypatch, destination)
    prunes = []
    api._eve_prune = lambda *args, **kwargs: prunes.append(args)
    sent = fakes.record_pushes(api)

    api.eve_settings_copy_profile(str(source), "replace", str(destination))

    assert prunes == []
    assert archives[0].exists()
    kind, _title, body = api._alert.raised[0]
    assert kind == "error"
    assert archives[0].name in body
    assert "Backups" in body
    ((payload,)) = fakes.payloads(sent, "onEveSettingsDone")
    assert payload["ok"] is False and payload["published"] is False
    assert payload["selection_persisted"] is True
    assert archives[0].name in payload["error"]
    assert api._eve_mutation.acquire(blocking=False)
    api._eve_mutation.release()


def test_an_unexpected_worker_failure_still_releases_and_completes_once(
    tmp_path, monkeypatch
):
    api, source = copy_profile_setup(tmp_path, monkeypatch)

    def explode(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(api_mod.evesettings_profilecopy, "stage_copy", explode)
    sent = fakes.record_pushes(api)

    api.eve_settings_copy_profile(str(source), "new", "Fleet")

    ((payload,)) = fakes.payloads(sent, "onEveSettingsDone")
    assert payload["ok"] is False and payload["published"] is False
    assert payload["selection_persisted"] is False
    assert payload["error"]
    assert api._eve_mutation.acquire(blocking=False)
    api._eve_mutation.release()
