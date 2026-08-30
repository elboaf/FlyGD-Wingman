"""The bridge is tested headless through FakeWindow (tests/fakes.py)."""

import os

import pytest

from tests import fakes
from tests.fakes import FakeWindow
from wingman import paths, settings
from wingman.evesettings import tree
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
    eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._eve_mutation.acquire()
    try:
        assert api.eve_settings_select("s", "p") is False
        assert api._state.settings["eve_settings"]["server"] is None
    finally:
        api._eve_mutation.release()
    assert api.eve_settings_select("s", "p") is True


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


def test_account_labels_share_alias_character_summary_and_raw_id(tmp_path, monkeypatch):
    eve_tree(
        tmp_path, files=("core_user_10.dat", "core_char_20.dat", "core_char_21.dat")
    )
    api = build(tmp_path, monkeypatch)
    section = api._eve_section()
    section["root"] = str(tmp_path / "EVE")
    section["account_aliases"] = {"10": "Main multibox"}
    section["account_characters"] = {"10": ["20", "21"]}
    api._eve_names.names.update({20: "Aiga Otsolen", 21: "Beta"})

    account = api.eve_settings_state()["accounts"][0]

    assert account["display_name"] == "Main multibox"
    assert account["display_meta"] == "Aiga Otsolen + 1 · 10"
    assert account["name"] == "Main multibox · Aiga Otsolen + 1 · 10"


def test_backup_rows_resolve_human_targets_without_opening_archives(
    tmp_path, monkeypatch
):
    profile = eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    api = build(tmp_path, monkeypatch)
    section = api._eve_section()
    section["root"] = str(tmp_path / "EVE")
    section["account_aliases"] = {"10": "Main multibox"}
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
        ("Main multibox", "Account 10"),
        ("Aiga Otsolen", "Character 20"),
    }


def test_identity_editor_keeps_linked_characters_missing_from_current_profile(
    tmp_path, monkeypatch
):
    eve_tree(tmp_path, files=("core_user_10.dat", "core_char_20.dat"))
    api = build(tmp_path, monkeypatch)
    section = api._eve_section()
    section["root"] = str(tmp_path / "EVE")
    section["account_characters"] = {"10": ["20", "99"]}

    identities = api.eve_settings_state()["identity_characters"]

    assert {item["id"] for item in identities} == {"20", "99"}
    assert next(item for item in identities if item["id"] == "99")["name"] == (
        "Character 99"
    )


def test_account_alias_can_be_saved_and_cleared(tmp_path, monkeypatch):
    eve_tree(tmp_path, files=("core_user_10.dat",))
    api = build(tmp_path, monkeypatch)
    api._eve_section()["root"] = str(tmp_path / "EVE")

    assert api.eve_settings_set_account_alias("10", " Main ")["applied"] is True
    assert api._eve_section()["account_aliases"] == {"10": "Main"}
    assert api.eve_settings_set_account_alias("10", "")["applied"] is True
    assert api._eve_section()["account_aliases"] == {}


def test_associating_a_character_moves_it_from_the_previous_account(
    tmp_path, monkeypatch
):
    eve_tree(
        tmp_path,
        files=("core_user_10.dat", "core_user_11.dat", "core_char_20.dat"),
    )
    api = build(tmp_path, monkeypatch)
    section = api._eve_section()
    section["root"] = str(tmp_path / "EVE")
    section["account_characters"] = {"10": ["20"]}

    result = api.eve_settings_set_account_characters("11", ["20"])

    assert result["applied"] is True
    assert api._eve_section()["account_characters"] == {"11": ["20"]}


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
    assert got["name"] == "1"
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
