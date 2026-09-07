"""The bridge is tested headless through FakeWindow (tests/fakes.py)."""

import json
import os
import threading
from pathlib import Path

import pytest

from tests import fakes
from tests.fakes import FakeWindow
from wingman import paths, settings
from wingman.evesettings import controller as ctrl_mod
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


# EVE's own name for the live shard's settings folder. The strict
# predicate (tree.is_tranquility_server) accepts it, so this fixture builds
# the TRUSTED context every account-identity behaviour needs -- the older
# "server_tranquility" only ever passed the display heuristic, which is
# deliberately not enough to authorize identity or deletion cleanup.
TRUSTED_SERVER = "c_ccp_eve_tq_tranquility"


def eve_tree(
    tmp_path, files=("core_char_1.dat", "core_char_2.dat"), server=TRUSTED_SERVER
):
    profile = tmp_path / "EVE" / server / "settings_Default"
    profile.mkdir(parents=True)
    for name in files:
        (profile / name).write_bytes(b"payload-" + name.encode())
    return profile


def account_setup(tmp_path, monkeypatch, name="core_user_1.dat"):
    profile = eve_tree(tmp_path, files=(name,))
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    return api, profile / name


def mark_deleted(api, *character_ids, datasource="tranquility"):
    """Record ESI deletion verdicts the way a resolver pass would."""
    for character_id in character_ids:
        api._profiles._eve_deleted.add((datasource, int(character_id)))


def fake_status(api, monkeypatch, names=None, deleted=(), seen=None, error=None):
    """Answer both ESI paths from memory.

    Nothing in this suite may reach the network: the character-status pass
    is bounded but real, and an unstubbed one costs a request timeout per
    id in every test that opens a trusted profile.
    """

    def resolve(ids, *args, **kwargs):
        if seen is not None:
            seen.append(list(ids))
        if error is not None:
            raise error
        return dict(names or {}), {int(i) for i in deleted}

    monkeypatch.setattr(ctrl_mod.evesettings_characters, "resolve", resolve)
    api._profiles._eve_names.resolve_missing = lambda ids, **kwargs: False


class QueuedThreads:
    """A spawn seam a test drives by hand, to observe the coordinator."""

    def __init__(self):
        self.queued = []

    def spawn(self, target=None, args=(), kwargs=None, daemon=None):
        queued = self.queued

        class Handle:
            def start(self):
                queued.append(lambda: target(*args, **(kwargs or {})))

        return Handle()

    def run_next(self):
        self.queued.pop(0)()


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
    api._state.settings["eve_settings"].update(
        {"root": str(profile), "server": None, "profile": None}
    )
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
    monkeypatch.setattr(ctrl_mod.evesettings_codec, "codec_available", lambda: True)

    state = api.eve_settings_state()

    assert state["selective_copy_available"] is True
    assert state["copy_groups"] == {
        "characters": ctrl_mod.evesettings_selective.groups_payload("character"),
        "accounts": ctrl_mod.evesettings_selective.groups_payload("account"),
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

    monkeypatch.setattr(ctrl_mod.evesettings_tree.os, "scandir", boom)
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
        return ctrl_mod.evesettings_ops.CopyReport(
            [ctrl_mod.evesettings_ops.TargetOutcome(profile / "core_char_2.dat", True)]
        )

    monkeypatch.setattr(ctrl_mod.evesettings_ops, "copy_to_targets", plain)
    monkeypatch.setattr(
        ctrl_mod.evesettings_ops,
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
        return ctrl_mod.evesettings_ops.CopyReport(
            [ctrl_mod.evesettings_ops.TargetOutcome(profile / "core_char_2.dat", True)]
        )

    monkeypatch.setattr(ctrl_mod.evesettings_ops, "copy_selected_to_targets", selected)
    monkeypatch.setattr(
        ctrl_mod.evesettings_ops,
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
        ctrl_mod.evesettings_ops,
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
    assert api._profiles._eve_mutation.acquire(blocking=False)
    api._profiles._eve_mutation.release()


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
        ctrl_mod.evesettings_ops.TargetOutcome(profile / "core_char_2.dat", True),
        ctrl_mod.evesettings_ops.TargetOutcome(
            profile / "core_char_3.dat", False, "bad target"
        ),
    ]
    monkeypatch.setattr(
        ctrl_mod.evesettings_ops,
        "copy_selected_to_targets",
        lambda *args, **kwargs: ctrl_mod.evesettings_ops.CopyReport(outcomes),
    )
    monkeypatch.setattr(
        ctrl_mod.evesettings_backup,
        "prune",
        lambda store, keep: (
            pruned.append((store, keep)) or ctrl_mod.evesettings_backup.PruneReport()
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
    api._profiles._eve_names.names[1] = "Guarzo Opper"
    api._profiles._eve_names.names[2] = "Zircon Gravimeld"
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
    api._profiles._eve_names.names[1] = "Zircon Gravimeld"
    api._profiles._eve_names.names[2] = "guarzo opper"
    api._profiles._eve_names.names[3] = "Aura"

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
        assert api._profiles._eve_label(character["path"]) == character["name"]
    assert api._profiles._eve_label(profile / "core_char_2.dat") == "Character 2"


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
    # Stub the folder-kind constant at test time so the test does not attempt
    # to import pywebview on platforms where it is not available.
    monkeypatch.setattr(api_mod, "_folder_dialog_kind", lambda: "FOLDER")
    assert api.eve_settings_pick_root() == str(root)
    assert api._state.settings["eve_settings"]["root"] == str(root)
    assert api._state.settings["eve_settings"]["server"] == str(server)
    assert api._state.settings["eve_settings"]["profile"] == str(profile)


def test_select_rejects_a_fabricated_selection(tmp_path, monkeypatch):
    """discover() falls back to the first server/profile it finds when a
    requested token matches nothing on disk. Persisting that fallback under
    a fabricated request's name would silently swap the user's selection
    for one they never asked for."""
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    assert api.eve_settings_select(str(profile.parent), "nonexistent-profile") is False
    assert api._state.settings["eve_settings"]["profile"] is None
    assert api.eve_settings_select("nonexistent-server", str(profile)) is False
    assert api._state.settings["eve_settings"]["server"] is None


def test_select_canonicalizes_a_legacy_deep_root(tmp_path, monkeypatch):
    """A stored root that is itself a profile directory -- from before
    canonical persistence -- must be healed by the next selection, not
    merely tolerated in place."""
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(profile)
    assert api.eve_settings_select(str(profile.parent), str(profile)) is True
    section = api._state.settings["eve_settings"]
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
    section = api._state.settings["eve_settings"]
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
    section = api._state.settings["eve_settings"]
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
    assert api._state.settings["eve_settings"]["profile"] == str(profile)


def test_names_are_pushed_once_a_pass_resolves_something(tmp_path, monkeypatch):
    eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    fake_status(api, monkeypatch, names={1: "Pilot One"})
    api.eve_settings_resolve_names()
    assert api._profiles._eve_names.names[1] == "Pilot One"
    assert [call for call in api._window.calls if "onEveSettingsNames" in call]


def test_no_push_when_a_pass_resolves_nothing(tmp_path, monkeypatch):
    eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    fake_status(api, monkeypatch)
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
    made = ctrl_mod.evesettings_backup.create_profile_backup(
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
    assert api._profiles._eve_mutation.acquire(blocking=False) is True
    api._profiles._eve_mutation.release()


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


def test_state_refuses_a_root_too_wide_to_be_an_eve_folder(tmp_path, monkeypatch):
    """A mis-picked root costs a scandir per child on the bridge thread.
    Refused with a reason, rather than probed slowly."""
    api = build(tmp_path, monkeypatch)
    wide = tmp_path / "wide"
    wide.mkdir()
    for n in range(ctrl_mod.evesettings_tree.MAX_ROOT_CHILDREN + 1):
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
    api._profiles._eve_refresh_running = lambda: None
    assert api.eve_settings_state()["eve_running"] is None


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
    api._profiles._eve_running = False  # The stale pill value; must not be the source.
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
    api._state.settings["eve_settings"]["auto_keep"] = 3

    assert api.eve_settings_state()["auto_keep"] == 3


def test_account_payload_uses_name_character_summary_and_account_id(
    tmp_path, monkeypatch
):
    eve_tree(
        tmp_path, files=("core_user_10.dat", "core_char_20.dat", "core_char_21.dat")
    )
    api = build(tmp_path, monkeypatch)
    section = api._state.settings["eve_settings"]
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"10": "LoginName"}
    section["account_characters"] = {"10": ["20", "21"]}
    api._profiles._eve_names.names.update({20: "Aiga Otsolen", 21: "Beta"})

    account = api.eve_settings_state()["accounts"][0]

    assert account["account_name"] == "LoginName"
    assert "alias" not in account
    assert account["display_name"] == "LoginName"
    assert account["display_meta"] == "Aiga Otsolen + 1 · Account 10"
    assert account["name"] == "LoginName · Aiga Otsolen + 1 · Account 10"


def test_unidentified_account_payload_is_explicit(tmp_path, monkeypatch):
    eve_tree(tmp_path, files=("core_user_10.dat",))
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")

    account = api.eve_settings_state()["accounts"][0]

    assert account["account_name"] == ""
    assert account["display_name"] == "Account 10"
    assert account["display_meta"] == "Not identified"


def test_backup_rows_resolve_human_targets_without_opening_archives(
    tmp_path, monkeypatch
):
    profile = eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    api = build(tmp_path, monkeypatch)
    section = api._state.settings["eve_settings"]
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"10": "LoginName"}
    section["account_characters"] = {"10": ["20"]}
    api._profiles._eve_names.names[20] = "Aiga Otsolen"
    store = paths.eve_settings_backup_dir()
    ctrl_mod.evesettings_backup.create_file_backup(
        store, profile / "core_user_10.dat", origin="manual"
    )
    ctrl_mod.evesettings_backup.create_file_backup(
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
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    ctrl_mod.evesettings_backup.create_file_backup(
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
    section = api._state.settings["eve_settings"]
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
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")

    assert api.eve_settings_set_account_name("10", " LoginName ")["applied"] is True
    assert api._state.settings["eve_settings"]["account_names"] == {"10": "LoginName"}
    assert api.eve_settings_set_account_name("10", "")["applied"] is False
    assert api.eve_settings_set_account_name("10", "x" * 81)["applied"] is False
    assert api._state.settings["eve_settings"]["account_names"] == {"10": "LoginName"}


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
    api._profiles._eve_discover = lambda: pytest.fail(
        "busy calls must not inspect the profile"
    )
    api._profiles._eve_mutation.acquire()
    try:
        result = getattr(api, method)(*args)
    finally:
        api._profiles._eve_mutation.release()

    assert result == {
        "applied": False,
        "persisted": False,
        "error": "Another Profiles operation is running.",
    }


def test_manual_identity_endpoint_does_not_interleave_a_blocked_save(
    tmp_path, monkeypatch
):
    eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
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


def test_account_name_is_unique_case_insensitively_except_for_itself(
    tmp_path, monkeypatch
):
    eve_tree(tmp_path, files=("core_user_10.dat", "core_user_11.dat"))
    api = build(tmp_path, monkeypatch)
    section = api._state.settings["eve_settings"]
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
    assert api._state.settings["eve_settings"]["account_names"] == {"10": "LOGINNAME"}
    assert api._state.settings["eve_settings"]["account_characters"] == {"10": ["20"]}


def test_unnamed_account_refuses_character_links(tmp_path, monkeypatch):
    eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")

    result = api.eve_settings_set_account_characters("10", ["20"])

    assert result["error"] == "Name this account before adding characters."
    assert api._state.settings["eve_settings"]["account_characters"] == {}


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
    section = api._state.settings["eve_settings"]
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"10": "LoginName"}

    result = api.eve_settings_set_account_characters("10", ["20", "20", "21", "22"])

    assert result["applied"] is True
    assert api._state.settings["eve_settings"]["account_characters"] == {
        "10": ["20", "21", "22"]
    }


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
    section = api._state.settings["eve_settings"]
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"10": "Source", "11": "Destination"}
    section["account_characters"] = {"10": ["23"], "11": ["20", "21", "22"]}

    result = api.eve_settings_set_account_characters("11", ["20", "21", "22", "23"])

    assert result["error"] == "An EVE account can have up to three characters."
    assert api._state.settings["eve_settings"]["account_characters"] == {
        "10": ["23"],
        "11": ["20", "21", "22"],
    }


def test_unknown_character_is_refused_without_mutation(tmp_path, monkeypatch):
    eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    api = build(tmp_path, monkeypatch)
    section = api._state.settings["eve_settings"]
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"10": "LoginName"}
    section["account_characters"] = {"10": ["20"]}

    result = api.eve_settings_set_account_characters("10", ["99"])

    assert result["applied"] is False
    assert api._state.settings["eve_settings"]["account_characters"] == {"10": ["20"]}


def test_associating_a_character_moves_it_to_a_named_account_with_room(
    tmp_path, monkeypatch
):
    eve_tree(
        tmp_path,
        files=("core_user_10.dat", "core_user_11.dat", "core_char_20.dat"),
    )
    api = build(tmp_path, monkeypatch)
    section = api._state.settings["eve_settings"]
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"10": "Source", "11": "Destination"}
    section["account_characters"] = {"10": ["20"]}

    result = api.eve_settings_set_account_characters("11", ["20"])

    assert result["applied"] is True
    assert api._state.settings["eve_settings"]["account_characters"] == {"11": ["20"]}


def test_removing_every_character_retains_the_account_name(tmp_path, monkeypatch):
    eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    api = build(tmp_path, monkeypatch)
    section = api._state.settings["eve_settings"]
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"10": "LoginName"}
    section["account_characters"] = {"10": ["20"]}

    assert api.eve_settings_set_account_characters("10", [])["applied"] is True
    assert api._state.settings["eve_settings"]["account_names"] == {"10": "LoginName"}
    assert api._state.settings["eve_settings"]["account_characters"] == {}


def _pending_identification(
    api, account_id="10", character_ids=("20",), generation=None
):
    """An observation and the offer it authorized, as a check leaves them."""
    api._profiles._eve_identification = evesettings_identity.Snapshot(
        Path("root"), Path("server"), Path("profile"), {}
    )
    _offer_candidate(api, account_id, character_ids, generation)


def _offer_candidate(api, account_id="10", character_ids=("20",), generation=None):
    """Publish an offer, authorized by the current generation by default."""
    api._profiles._eve_identification_candidate = ctrl_mod._EveCandidate(
        api._profiles._eve_identification_generation
        if generation is None
        else generation,
        account_id,
        tuple(character_ids),
    )


def offered(api):
    """The offered pair without its generation, for comparison."""
    candidate = api._profiles._eve_identification_candidate
    if candidate is None:
        return None
    return (candidate.account_id, candidate.character_ids)


def names_pushes(api):
    """Every onEveSettingsNames payload the bridge sent, decoded."""
    return [
        json.loads(call[call.index("(") + 1 : call.rindex(")")])
        for call in api._window.calls
        if "onEveSettingsNames" in call
    ]


def test_identification_start_and_check_report_busy_with_stable_status(
    tmp_path, monkeypatch
):
    eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api._profiles._eve_mutation.acquire()
    try:
        start = api.eve_settings_identification_start()
        check = api.eve_settings_identification_check()
    finally:
        api._profiles._eve_mutation.release()

    assert start == {
        "status": "busy",
        "error": "Another Profiles operation is running.",
        "identification_generation": 0,
    }
    assert check == start


def test_identification_cancellation_and_selection_changes_clear_snapshot_and_candidate(
    tmp_path, monkeypatch
):
    profile = eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")

    _pending_identification(api)
    assert api.eve_settings_identification_cancel()["status"] == "idle"
    assert api._profiles._eve_identification is None
    assert api._profiles._eve_identification_candidate is None

    _pending_identification(api)
    assert api.eve_settings_select(str(profile.parent), str(profile)) is True
    assert api._profiles._eve_identification is None
    assert api._profiles._eve_identification_candidate is None

    _pending_identification(api)
    api._window.create_file_dialog = lambda *args, **kwargs: [str(tmp_path / "other")]
    monkeypatch.setattr(api_mod, "_folder_dialog_kind", lambda: "FOLDER")
    assert api.eve_settings_pick_root() == str(tmp_path / "other")
    assert api._profiles._eve_identification is None
    assert api._profiles._eve_identification_candidate is None


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
    assert api._state.settings["eve_settings"]["account_names"] == {}
    assert api._state.settings["eve_settings"]["account_characters"] == {}


@pytest.mark.parametrize("name", ["", "x" * 81, "other"])
def test_identification_confirmation_rejects_invalid_names_without_partial_write(
    tmp_path, monkeypatch, name
):
    api = build(tmp_path, monkeypatch)
    section = api._state.settings["eve_settings"]
    section["account_names"] = {"11": "Other"}
    section["account_characters"] = {"11": ["21"]}
    _pending_identification(api)

    result = api.eve_settings_identification_confirm("10", "20", name)

    assert result["applied"] is False
    assert api._state.settings["eve_settings"]["account_names"] == {"11": "Other"}
    assert api._state.settings["eve_settings"]["account_characters"] == {"11": ["21"]}
    assert offered(api) == ("10", ("20",))


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
    assert api._state.settings["eve_settings"]["account_names"] == {"10": "Login"}
    assert api._state.settings["eve_settings"]["account_characters"] == {"10": ["20"]}
    assert api._profiles._eve_identification is None
    assert api._profiles._eve_identification_candidate is None


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
    assert api._state.settings["eve_settings"]["account_names"] == {}
    assert api._state.settings["eve_settings"]["account_characters"] == {}
    assert api._profiles._eve_identification is not None
    assert offered(api) == ("10", ("20",))


def test_identification_confirmation_accepts_its_existing_name_and_link_as_a_noop(
    tmp_path, monkeypatch
):
    api = build(tmp_path, monkeypatch)
    section = api._state.settings["eve_settings"]
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
    assert api._profiles._eve_identification is None
    assert api._profiles._eve_identification_candidate is None


def test_identification_confirmation_refuses_a_fourth_link_without_moving_it(
    tmp_path, monkeypatch
):
    api = build(tmp_path, monkeypatch)
    section = api._state.settings["eve_settings"]
    section["account_names"] = {"10": "Destination", "11": "Source"}
    section["account_characters"] = {"10": ["21", "22", "23"], "11": ["20"]}
    _pending_identification(api)

    result = api.eve_settings_identification_confirm("10", "20", "Destination")

    assert result["applied"] is False
    assert api._state.settings["eve_settings"]["account_characters"] == {
        "10": ["21", "22", "23"],
        "11": ["20"],
    }


def test_identification_confirmation_moves_an_owned_character_only_when_room_exists(
    tmp_path, monkeypatch
):
    api = build(tmp_path, monkeypatch)
    section = api._state.settings["eve_settings"]
    section["account_names"] = {"10": "Destination", "11": "Source"}
    section["account_characters"] = {"10": ["21"], "11": ["20"]}
    _pending_identification(api)

    assert (
        api.eve_settings_identification_confirm("10", "20", "Destination")["applied"]
        is True
    )
    assert api._state.settings["eve_settings"]["account_characters"] == {
        "10": ["21", "20"]
    }


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
    assert api._state.settings["eve_settings"]["account_names"] == {"10": "Login"}
    assert api._state.settings["eve_settings"]["account_characters"] == {"10": ["20"]}


def test_identification_proposes_only_one_changed_account(tmp_path, monkeypatch):
    profile = eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api._profiles._eve_names.names[20] = "Aiga Otsolen"

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
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
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
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
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
    assert api.eve_settings_identification_cancel()["status"] == "idle"
    assert api.eve_settings_backup(str(profile), "profile") is True


# --- identification generations ------------------------------------------
#
# The offer is ephemeral state two threads reach at once: the bridge
# publishes it, the resolver invalidates it, and the page renders it one
# round trip later. The generation is what lets each of them tell a
# current answer from one that was true when it was computed.


def test_a_deletion_learned_after_an_offer_invalidates_it_with_a_newer_generation(
    tmp_path, monkeypatch
):
    profile = eve_tree(tmp_path, files=("core_user_10.dat", "core_char_21.dat"))
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api._eve_client_running_strict = lambda: False
    assert api.eve_settings_identification_start()["status"] == "watching"
    (profile / "core_user_10.dat").write_bytes(b"changed account")
    (profile / "core_char_21.dat").write_bytes(b"changed character")
    offer = api.eve_settings_identification_check()
    fake_status(api, monkeypatch, deleted={21})

    api.eve_settings_resolve_names()

    assert offer["status"] == "candidate"
    assert api._profiles._eve_identification is None
    assert api._profiles._eve_identification_candidate is None
    # Strictly newer than the offer, so a page holding a delayed candidate
    # callback rejects it instead of resurrecting the deleted character.
    assert names_pushes(api) == [
        {
            "identification_generation": offer["identification_generation"] + 1,
            "deleted_candidate_ids": ["21"],
        }
    ]


def test_a_deletion_that_races_a_candidate_publication_invalidates_it(
    tmp_path, monkeypatch
):
    profile = eve_tree(tmp_path, files=("core_user_10.dat", "core_char_21.dat"))
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api._eve_client_running_strict = lambda: False
    assert api.eve_settings_identification_start()["status"] == "watching"
    (profile / "core_user_10.dat").write_bytes(b"changed account")
    (profile / "core_char_21.dat").write_bytes(b"changed character")
    learned = threading.Event()

    def resolve(ids, *args, **kwargs):
        learned.set()
        return {}, {21}

    monkeypatch.setattr(ctrl_mod.evesettings_characters, "resolve", resolve)
    api._profiles._eve_names.resolve_missing = lambda ids, **kwargs: False
    resolver = threading.Thread(target=api.eve_settings_resolve_names)
    started = threading.Event()
    label = api._profiles._eve_names.label

    def label_after_starting_the_resolver(character_id):
        if not started.is_set():
            started.set()
            # The pass learns the deletion while this check still owns
            # _eve_mutation, so its cleanup is parked behind the offer
            # being published right now.
            resolver.start()
            assert learned.wait(5), "the resolver never reached its ESI pass"
        return label(character_id)

    api._profiles._eve_names.label = label_after_starting_the_resolver
    offer = api.eve_settings_identification_check()
    resolver.join(5)

    assert not resolver.is_alive()
    assert offer["status"] == "candidate"
    assert api._profiles._eve_identification_candidate is None
    assert names_pushes(api) == [
        {
            "identification_generation": offer["identification_generation"] + 1,
            "deleted_candidate_ids": ["21"],
        }
    ]


def test_confirmation_prunes_deleted_links_without_re_persisting_them(
    tmp_path, monkeypatch
):
    eve_tree(
        tmp_path,
        files=(
            "core_user_10.dat",
            "core_user_11.dat",
            "core_char_20.dat",
            "core_char_21.dat",
        ),
    )
    api = build(tmp_path, monkeypatch)
    section = api._state.settings["eve_settings"]
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"11": "Second"}
    section["account_characters"] = {"11": ["21"]}
    mark_deleted(api, 21)
    _pending_identification(api, "10", ("20",))

    result = api.eve_settings_identification_confirm("10", "20", "First")

    assert result["applied"] is True
    # The deleted link belongs to an account this confirmation never
    # touched: writing a mapping read before the prune would restore it.
    assert api._state.settings["eve_settings"]["account_characters"] == {"10": ["20"]}
    stored = settings.load(tmp_path / "FlyGD Wingman" / "settings.json")
    assert stored["eve_settings"]["account_characters"] == {"10": ["20"]}


def test_confirmation_is_refused_while_deleted_links_cannot_be_removed(
    tmp_path, monkeypatch
):
    eve_tree(
        tmp_path,
        files=(
            "core_user_10.dat",
            "core_user_11.dat",
            "core_char_20.dat",
            "core_char_21.dat",
        ),
    )
    api = build(tmp_path, monkeypatch)
    section = api._state.settings["eve_settings"]
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"11": "Second"}
    section["account_characters"] = {"11": ["21"]}
    mark_deleted(api, 21)
    _pending_identification(api, "10", ("20",))

    def fail_write(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(api_mod.settings_mod, "update_section", fail_write)

    result = api.eve_settings_identification_confirm("10", "20", "First")

    assert result["error"] == "Could not remove deleted character links."
    assert api._state.settings["eve_settings"]["account_characters"] == {"11": ["21"]}
    assert offered(api) == ("10", ("20",))


def test_lowering_retention_confirms_exact_count_and_keeps_manual_backups(
    tmp_path, monkeypatch
):
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    store = paths.eve_settings_backup_dir()
    source = profile / "core_char_1.dat"
    for second in range(3):
        ctrl_mod.evesettings_backup.create_file_backup(
            store,
            source,
            origin="auto",
            now=api_mod.datetime.datetime(
                2026, 1, 1, 0, 0, second, tzinfo=api_mod.datetime.UTC
            ),
        )
    manual = ctrl_mod.evesettings_backup.create_file_backup(
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
    assert api._state.settings["eve_settings"]["auto_keep"] == 1
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
        ctrl_mod.evesettings_backup.create_file_backup(
            store,
            source,
            origin="auto",
            now=api_mod.datetime.datetime(
                2026, 1, 1, 0, 0, second, tzinfo=api_mod.datetime.UTC
            ),
        )

    api.eve_settings_set_auto_keep(1)

    assert api._state.settings["eve_settings"]["auto_keep"] == 10
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


# ----- confirmed deletions: filtering, cleanup, and the resolver ---------


def test_confirmed_deleted_character_is_hidden_but_its_file_and_backup_remain(
    tmp_path, monkeypatch
):
    """The verdict hides a row. It never touches EVE's own data: the file
    and every backup of it are recovery artifacts and stay exactly where
    the user left them."""
    profile = eve_tree(tmp_path, files=("core_char_20.dat", "core_char_21.dat"))
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    ctrl_mod.evesettings_backup.create_file_backup(
        paths.eve_settings_backup_dir(), profile / "core_char_21.dat", origin="manual"
    )
    mark_deleted(api, 21)

    state = api.eve_settings_state()

    assert [row["id"] for row in state["characters"]] == ["20"]
    assert (profile / "core_char_21.dat").exists()
    assert any(row["stem"] == "core_char_21" for row in state["backups"])


def test_unresolved_character_remains_visible(tmp_path, monkeypatch):
    """Offline is the normal case, and silence is not a deletion."""
    eve_tree(tmp_path, files=("core_char_20.dat", "core_char_21.dat"))
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")

    assert {row["id"] for row in api.eve_settings_state()["characters"]} == {
        "20",
        "21",
    }


def test_deleted_links_are_filtered_from_account_rows_and_the_identity_picker(
    tmp_path, monkeypatch
):
    eve_tree(
        tmp_path, files=("core_user_10.dat", "core_char_20.dat", "core_char_21.dat")
    )
    api = build(tmp_path, monkeypatch)
    section = api._state.settings["eve_settings"]
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"10": "LoginName"}
    section["account_characters"] = {"10": ["20", "21"]}
    api._profiles._eve_names.names.update({20: "Alpha", 21: "Beta"})
    mark_deleted(api, 21)

    state = api.eve_settings_state()

    assert state["account_identity_available"] is True
    assert state["accounts"][0]["character_ids"] == ["20"]
    assert state["accounts"][0]["display_meta"] == "Alpha · Account 10"
    assert {row["id"] for row in state["identity_characters"]} == {"20"}


@pytest.mark.parametrize("server", ["tranquility_backup", "server_singularity"])
def test_untrusted_servers_expose_no_account_identity_and_filter_nothing(
    tmp_path, monkeypatch, server
):
    """A Tranquility verdict says nothing about another shard, and the
    display heuristic that calls `tranquility_backup` Tranquility is not
    evidence enough to apply Tranquility metadata to it."""
    profile = eve_tree(
        tmp_path,
        files=("core_user_10.dat", "core_char_20.dat", "core_char_21.dat"),
        server=server,
    )
    api = build(tmp_path, monkeypatch)
    section = api._state.settings["eve_settings"]
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"10": "LoginName"}
    section["account_characters"] = {"10": ["20", "21"]}
    mark_deleted(api, 21)

    state = api.eve_settings_state()

    assert state["account_identity_available"] is False
    assert {row["id"] for row in state["characters"]} == {"20", "21"}
    assert state["accounts"][0]["account_name"] == ""
    assert state["accounts"][0]["character_ids"] == []
    assert state["accounts"][0]["display_name"] == "Account 10"
    assert state["identity_characters"] == []
    assert (profile / "core_char_21.dat").exists()
    assert api._state.settings["eve_settings"]["account_characters"] == {
        "10": ["20", "21"]
    }


def test_an_untrusted_server_refuses_identity_edits_and_identification(
    tmp_path, monkeypatch
):
    eve_tree(
        tmp_path,
        files=("core_user_10.dat", "core_char_20.dat"),
        server="server_singularity",
    )
    api = build(tmp_path, monkeypatch)
    section = api._state.settings["eve_settings"]
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"10": "LoginName"}
    unavailable = "Account identity is available only for Tranquility profiles."

    assert api.eve_settings_set_account_name("10", "Other")["error"] == unavailable
    assert api.eve_settings_set_account_characters("10", ["20"])["error"] == unavailable
    assert api.eve_settings_identification_start() == {
        "status": "error",
        "error": unavailable,
        "identification_generation": 1,
    }
    assert api._state.settings["eve_settings"]["account_names"] == {"10": "LoginName"}
    assert api._state.settings["eve_settings"]["account_characters"] == {}


def test_a_deleted_character_cannot_be_linked_or_confirmed(tmp_path, monkeypatch):
    eve_tree(
        tmp_path, files=("core_user_10.dat", "core_char_20.dat", "core_char_21.dat")
    )
    api = build(tmp_path, monkeypatch)
    section = api._state.settings["eve_settings"]
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"10": "LoginName"}
    mark_deleted(api, 21)
    _pending_identification(api, "10", ("21",))

    linked = api.eve_settings_set_account_characters("10", ["20", "21"])
    confirmed = api.eve_settings_identification_confirm("10", "21", "LoginName")

    assert linked["error"] == "That character no longer exists."
    assert confirmed["error"] == "That character no longer exists."
    assert api._state.settings["eve_settings"]["account_characters"] == {}


def test_identification_does_not_offer_a_confirmed_deleted_character(
    tmp_path, monkeypatch
):
    profile = eve_tree(
        tmp_path, files=("core_user_10.dat", "core_char_20.dat", "core_char_21.dat")
    )
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api._eve_client_running_strict = lambda: False
    mark_deleted(api, 21)
    assert api.eve_settings_identification_start()["status"] == "watching"
    (profile / "core_user_10.dat").write_bytes(b"changed account")
    (profile / "core_char_21.dat").write_bytes(b"changed deleted character")

    assert api.eve_settings_identification_check()["status"] == "none"

    (profile / "core_char_20.dat").write_bytes(b"changed live character")

    result = api.eve_settings_identification_check()

    assert result["status"] == "candidate"
    assert [row["id"] for row in result["characters"]] == ["20"]
    assert offered(api) == ("10", ("20",))


def test_cleanup_removes_deleted_links_from_every_account_and_survives_reload(
    tmp_path, monkeypatch
):
    profile = eve_tree(
        tmp_path,
        files=(
            "core_user_10.dat",
            "core_user_11.dat",
            "core_char_20.dat",
            "core_char_21.dat",
        ),
    )
    api = build(tmp_path, monkeypatch)
    section = api._state.settings["eve_settings"]
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"10": "First", "11": "Second"}
    section["account_characters"] = {"10": ["21"], "11": ["20", "21"]}
    fake_status(api, monkeypatch, names={20: "Alpha"}, deleted={21})

    api.eve_settings_resolve_names()

    assert api._state.settings["eve_settings"]["account_characters"] == {"11": ["20"]}
    stored = settings.load(tmp_path / "FlyGD Wingman" / "settings.json")
    assert stored["eve_settings"]["account_characters"] == {"11": ["20"]}
    assert stored["eve_settings"]["account_names"] == {"10": "First", "11": "Second"}
    assert (profile / "core_char_21.dat").exists()
    assert any("onEveSettingsNames" in call for call in api._window.calls)


def test_cleanup_write_failure_keeps_the_links_but_the_payload_still_hides_them(
    tmp_path, monkeypatch
):
    eve_tree(
        tmp_path, files=("core_user_10.dat", "core_char_20.dat", "core_char_21.dat")
    )
    api = build(tmp_path, monkeypatch)
    section = api._state.settings["eve_settings"]
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"10": "LoginName"}
    section["account_characters"] = {"10": ["20", "21"]}
    fake_status(api, monkeypatch, deleted={21})
    monkeypatch.setattr(
        api_mod.settings_mod,
        "update_section",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )

    api.eve_settings_resolve_names()

    assert api._state.settings["eve_settings"]["account_characters"] == {
        "10": ["20", "21"]
    }
    assert api.eve_settings_state()["accounts"][0]["character_ids"] == ["20"]


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("eve_settings_set_account_name", ("10", "Renamed")),
        ("eve_settings_set_account_characters", ("10", ["20"])),
    ],
)
def test_a_pending_cleanup_that_cannot_save_refuses_the_account_edit(
    tmp_path, monkeypatch, method, args
):
    """The page submits its VISIBLE list as the complete roster, so accepting
    an edit while a hidden link is still saved would either resurrect it or
    delete it silently. Refuse instead."""
    eve_tree(
        tmp_path, files=("core_user_10.dat", "core_char_20.dat", "core_char_21.dat")
    )
    api = build(tmp_path, monkeypatch)
    section = api._state.settings["eve_settings"]
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"10": "LoginName"}
    section["account_characters"] = {"10": ["20", "21"]}
    mark_deleted(api, 21)
    monkeypatch.setattr(
        api_mod.settings_mod,
        "update_section",
        lambda *a, **kw: (_ for _ in ()).throw(OSError("disk full")),
    )

    result = getattr(api, method)(*args)

    assert result == {
        "applied": False,
        "persisted": False,
        "error": "Could not remove deleted character links.",
    }
    assert api._state.settings["eve_settings"]["account_names"] == {"10": "LoginName"}
    assert api._state.settings["eve_settings"]["account_characters"] == {
        "10": ["20", "21"]
    }


def test_a_later_edit_retries_the_pending_cleanup_before_applying(
    tmp_path, monkeypatch
):
    eve_tree(
        tmp_path, files=("core_user_10.dat", "core_char_20.dat", "core_char_21.dat")
    )
    api = build(tmp_path, monkeypatch)
    section = api._state.settings["eve_settings"]
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"10": "LoginName"}
    section["account_characters"] = {"10": ["20", "21"]}
    mark_deleted(api, 21)

    assert api.eve_settings_set_account_name("10", "Renamed")["applied"] is True

    assert api._state.settings["eve_settings"]["account_names"] == {"10": "Renamed"}
    assert api._state.settings["eve_settings"]["account_characters"] == {"10": ["20"]}


def test_second_account_deleted_link_absent_after_retry_cleanup_and_character_edit(
    tmp_path, monkeypatch
):
    """Regression: section was captured before _eve_prune_deleted_links_locked;
    update_section replaces the nested dict, so reading associations from the
    stale snapshot re-persisted a deleted link from an unedited second account.

    Scenario: account 11 holds deleted character 21; cleanup fails once;
    editing account 10's characters retries cleanup and succeeds; id 21 must
    be absent both in memory and after a fresh reload from disk.
    """
    eve_tree(
        tmp_path,
        files=(
            "core_user_10.dat",
            "core_user_11.dat",
            "core_char_20.dat",
            "core_char_21.dat",
        ),
    )
    api = build(tmp_path, monkeypatch)
    section = api._state.settings["eve_settings"]
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"10": "Alpha", "11": "Beta"}
    # Account 11 links to character 21, which ESI has confirmed deleted.
    section["account_characters"] = {"10": ["20"], "11": ["21"]}
    mark_deleted(api, 21)

    # First cleanup attempt fails (simulates a previous write error leaving a
    # pending state).
    original = api_mod.settings_mod.update_section
    calls = []

    def fail_first(data, name, values):
        if not calls:
            calls.append(values)
            raise OSError("disk full")
        return original(data, name, values)

    monkeypatch.setattr(api_mod.settings_mod, "update_section", fail_first)
    # Trigger the first (failing) cleanup attempt via set_account_name.
    result = api.eve_settings_set_account_name("10", "Alpha")
    assert result["applied"] is False
    assert result["error"] == "Could not remove deleted character links."

    # Restore normal writes; next edit retries cleanup then applies its own
    # change.  Before the fix, the stale section snapshot re-persisted id 21.
    monkeypatch.setattr(api_mod.settings_mod, "update_section", original)
    result = api.eve_settings_set_account_characters("10", ["20"])
    assert result["applied"] is True, result.get("error")

    # Deleted id must be absent in memory ...
    saved = api._state.settings["eve_settings"].get("account_characters") or {}
    all_saved_ids = [cid for ids in saved.values() for cid in ids]
    assert "21" not in all_saved_ids, f"deleted id 21 still in memory: {saved}"
    # ... and absent after a fresh reload from disk.
    import wingman.settings as settings_mod_check

    reloaded = settings_mod_check.load(tmp_path / "settings.json").get(
        "eve_settings", {}
    )
    reloaded_ids = [
        cid
        for ids in (reloaded.get("account_characters") or {}).values()
        for cid in ids
    ]
    assert "21" not in reloaded_ids, f"deleted id 21 persisted on disk: {reloaded}"


def test_cleanup_rereads_the_links_only_after_taking_the_mutation_lock(
    tmp_path, monkeypatch
):
    """The pattern of the blocking-update_section test above: a manual edit
    that lands while the resolver is on the network must survive it. A prune
    computed from a pre-lock read would write back the older roster."""
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
    section = api._state.settings["eve_settings"]
    section["root"] = str(tmp_path / "EVE")
    section["account_names"] = {"10": "LoginName"}
    section["account_characters"] = {"10": ["21"]}
    fake_status(api, monkeypatch, deleted={21})
    original = api_mod.settings_mod.update_section
    writing = threading.Event()
    release_write = threading.Event()

    def blocking_write(data, name, values):
        writing.set()
        assert release_write.wait(5), "test did not release the manual edit"
        return original(data, name, values)

    monkeypatch.setattr(api_mod.settings_mod, "update_section", blocking_write)
    writer = threading.Thread(
        target=lambda: api.eve_settings_set_account_characters("10", ["21", "22"])
    )
    writer.start()
    assert writing.wait(5), "the manual edit never reached the settings write"
    resolver = threading.Thread(target=api.eve_settings_resolve_names)
    resolver.start()
    release_write.set()
    writer.join(5)
    resolver.join(5)

    assert not writer.is_alive() and not resolver.is_alive()
    assert api._state.settings["eve_settings"]["account_characters"] == {"10": ["22"]}


def _fake_codec(monkeypatch, doc, *, available=True):
    """Route the seam at codec.read_document/write_document to an in-memory doc."""
    from wingman.evesettings import codec as codec_mod

    store = {"doc": doc, "written": []}

    def read_document(path, **kw):
        return codec_mod.Document(doc=store["doc"], had_crc=False)

    def write_document(path, document, *, backup, **kw):
        backup(path)
        store["written"].append((path, document))

    monkeypatch.setattr(ctrl_mod.evesettings_codec, "read_document", read_document)
    monkeypatch.setattr(ctrl_mod.evesettings_codec, "write_document", write_document)
    monkeypatch.setattr(
        ctrl_mod.evesettings_codec, "codec_available", lambda **kw: available
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


def test_save_backs_up_writes_and_reports_done(tmp_path, monkeypatch):
    api, account = account_setup(tmp_path, monkeypatch)
    store = _fake_codec(monkeypatch, FORMATION_DOC)
    api._eve_client_running_strict = lambda: False
    backups = []
    api._profiles._eve_auto_backup = lambda p: backups.append(p)
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


def stages_left(server):
    return [
        entry.name
        for entry in server.iterdir()
        if entry.name.startswith(ctrl_mod.evesettings_profilecopy.STAGE_PREFIX)
    ]


def test_profile_copy_returns_an_inline_refusal_when_another_operation_runs(
    tmp_path, monkeypatch
):
    """The page renders this beside its own button, so the refusal is the
    return value rather than an alert -- and it is decided before anything
    reads the tree, exactly as the character copy's busy check is."""
    api, source = copy_profile_setup(tmp_path, monkeypatch)
    api._profiles._eve_discover = lambda: pytest.fail("busy must not inspect the tree")
    assert api._profiles._eve_mutation.acquire(blocking=False)
    try:
        assert api.eve_settings_copy_profile(str(source), "new", "Fleet") == {
            "accepted": False,
            "error": "Another Profiles operation is running.",
        }
    finally:
        api._profiles._eve_mutation.release()
    assert not (source.parent / "settings_Fleet").exists()


def test_profile_copy_is_refused_while_account_identification_is_active(
    tmp_path, monkeypatch
):
    api, source = copy_profile_setup(tmp_path, monkeypatch)
    api._profiles._eve_identification = object()
    result = api.eve_settings_copy_profile(str(source), "new", "Fleet")
    assert result == {
        "accepted": False,
        "error": "Finish or cancel account identification first.",
    }
    assert not (source.parent / "settings_Fleet").exists()
    assert api._profiles._eve_mutation.acquire(blocking=False)
    api._profiles._eve_mutation.release()


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
    assert api._profiles._eve_mutation.acquire(blocking=False)
    api._profiles._eve_mutation.release()


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
    assert api._profiles._eve_mutation.acquire(blocking=False)
    api._profiles._eve_mutation.release()


def test_creating_a_profile_copies_every_recognized_file_and_selects_it(
    tmp_path, monkeypatch
):
    api, source = copy_profile_setup(tmp_path, monkeypatch)
    api._eve_confirm = lambda *args, **kwargs: pytest.fail("creation never confirms")
    monkeypatch.setattr(
        ctrl_mod.evesettings_backup,
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
    assert api._profiles._eve_mutation.acquire(blocking=False)
    api._profiles._eve_mutation.release()


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


def test_a_published_replacement_survives_a_failed_stage_cleanup(tmp_path, monkeypatch):
    """The stage is removed AFTER the destination has settled, so a scanner
    still holding it open must not convert a replacement that happened into
    "Copy failed" -- an alert that both misreports the destination and
    invites a retry of a copy already on disk. The stage is left for the
    next run's sweep, in the namespace discovery can never offer.
    """
    api, source = copy_profile_setup(tmp_path, monkeypatch, others=("Backup",))
    destination = source.parent / "settings_Backup"
    api._eve_confirm = lambda *args, **kwargs: True
    real_rmtree = ctrl_mod.evesettings_profilecopy.shutil.rmtree

    def rmtree(path, *args, **kwargs):
        if Path(path).name.startswith(ctrl_mod.evesettings_profilecopy.STAGE_PREFIX):
            raise OSError("handle open")
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(ctrl_mod.evesettings_profilecopy.shutil, "rmtree", rmtree)
    sent = fakes.record_pushes(api)

    result = api.eve_settings_copy_profile(str(source), "replace", str(destination))

    assert result == {"accepted": True, "error": None}
    assert sorted(p.name for p in destination.iterdir()) == [
        "core_char_1.dat",
        "core_char_2.dat",
    ]
    ((payload,)) = fakes.payloads(sent, "onEveSettingsDone")
    assert payload == {
        "ok": True,
        "operation": "profile_copy",
        "mode": "replace",
        "published": True,
        "selection_persisted": True,
        "error": None,
    }
    assert api._alert.raised == []
    # The one visible trace is the stage the next run will clean up.
    assert stages_left(source.parent) != []


def test_a_declined_replacement_creates_no_backup_and_changes_nothing(
    tmp_path, monkeypatch
):
    api, source = copy_profile_setup(tmp_path, monkeypatch, others=("Backup",))
    destination = source.parent / "settings_Backup"
    api._eve_confirm = lambda *args, **kwargs: False
    monkeypatch.setattr(
        ctrl_mod.evesettings_backup,
        "create_profile_backup",
        lambda *args, **kwargs: pytest.fail("a declined copy backs nothing up"),
    )
    prunes = []
    api._profiles._eve_prune = lambda *args, **kwargs: prunes.append(args)
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
    assert api._profiles._eve_mutation.acquire(blocking=False)
    api._profiles._eve_mutation.release()


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
        monkeypatch.setattr(
            ctrl_mod.evesettings_backup, "create_profile_backup", refuse
        )
    elif failure == "rollback restored":
        failing_publication(monkeypatch, destination)
    elif failure == "rollback failed":
        failing_publication(monkeypatch, destination)
        monkeypatch.setattr(ctrl_mod.evesettings_backup, "restore", refuse)
    else:
        # A worker failure after acceptance that is not one of the handled
        # arms: the outer catch must report the same retained selection.
        monkeypatch.setattr(
            ctrl_mod.evesettings_profilecopy, "publish_replacement", explode
        )
    sent = fakes.record_pushes(api)

    api.eve_settings_copy_profile(str(source), "replace", str(destination))

    ((payload,)) = fakes.payloads(sent, "onEveSettingsDone")
    assert payload["ok"] is False and payload["published"] is False
    assert payload["selection_persisted"] is True
    stored = settings.load(tmp_path / "FlyGD Wingman" / "settings.json")
    assert stored["eve_settings"]["profile"] == str(source)
    assert api._profiles._eve_mutation.acquire(blocking=False)
    api._profiles._eve_mutation.release()


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
        ctrl_mod.evesettings_profilecopy,
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
    assert api._profiles._eve_mutation.acquire(blocking=False)
    api._profiles._eve_mutation.release()


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
        ctrl_mod.evesettings_backup,
        "create_profile_backup",
        lambda *args, **kwargs: pytest.fail("a refused copy backs nothing up"),
    )

    api.eve_settings_copy_profile(str(source), "replace", str(destination))

    assert sorted(p.name for p in destination.iterdir()) == ["core_char_9.dat"]
    assert stages_left(source.parent) == []
    assert "EVE is running" in api._alert.raised[0][2]
    assert api._profiles._eve_mutation.acquire(blocking=False)
    api._profiles._eve_mutation.release()


def test_a_failed_destination_backup_leaves_the_destination_unchanged(
    tmp_path, monkeypatch
):
    api, source = copy_profile_setup(tmp_path, monkeypatch, others=("Backup",))
    destination = source.parent / "settings_Backup"

    def refuse(*args, **kwargs):
        raise OSError("the backup store is read-only")

    monkeypatch.setattr(ctrl_mod.evesettings_backup, "create_profile_backup", refuse)
    monkeypatch.setattr(
        ctrl_mod.evesettings_profilecopy,
        "publish_replacement",
        lambda *args, **kwargs: pytest.fail("publication needs a backup first"),
    )
    prunes = []
    api._profiles._eve_prune = lambda *args, **kwargs: prunes.append(args)
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
    assert api._profiles._eve_mutation.acquire(blocking=False)
    api._profiles._eve_mutation.release()


def failing_publication(monkeypatch, destination):
    """Break the second per-file replacement, so publication fails after it
    has already changed the destination."""
    real_copy = ctrl_mod.evesettings_profilecopy.atomicio.copy_atomic

    def flaky(source, target, **kwargs):
        if Path(target).parent == destination and Path(target).name.endswith("2.dat"):
            raise OSError("the destination went away")
        return real_copy(source, target, **kwargs)

    monkeypatch.setattr(ctrl_mod.evesettings_profilecopy.atomicio, "copy_atomic", flaky)
