"""The bridge is tested headless through FakeWindow (tests/fakes.py)."""
import threading

import pytest

from obs_youtube_uploader import settings
from obs_youtube_uploader.ui import api as api_mod
from tests.fakes import FakeWindow


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
    state = api_mod.AppState(recording_dir=tmp_path,
                             settings=settings.load(tmp_path / "settings.json"))
    built = api_mod.Api(state, spawn=ImmediateThread)
    built._window = FakeWindow()
    built._confirm = lambda title, body: answer
    # The EVE workers ask through _eve_confirm, which is _confirm with a
    # deadline; both are stubbed so a test never parks on a dialog.
    built._eve_confirm = lambda title, body: answer
    return built


def eve_tree(tmp_path, files=("core_char_1.dat", "core_char_2.dat")):
    profile = tmp_path / "EVE" / "server_tranquility" / "settings_Default"
    profile.mkdir(parents=True)
    for name in files:
        (profile / name).write_bytes(b"payload-" + name.encode())
    return profile


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
    api.eve_settings_copy(str(profile / "core_char_1.dat"),
                          [str(profile / "core_char_2.dat")])
    assert (profile / "core_char_2.dat").read_bytes() == b"payload-core_char_1.dat"


def test_copy_takes_a_backup_of_each_target(tmp_path, monkeypatch):
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api.eve_settings_copy(str(profile / "core_char_1.dat"),
                          [str(profile / "core_char_2.dat")])
    assert len(api.eve_settings_state()["backups"]) == 1


def test_copy_declined_at_the_prompt_changes_nothing(tmp_path, monkeypatch):
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch, answer=False)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api.eve_settings_copy(str(profile / "core_char_1.dat"),
                          [str(profile / "core_char_2.dat")])
    assert (profile / "core_char_2.dat").read_bytes() == b"payload-core_char_2.dat"


def test_a_second_mutation_is_refused_while_one_holds_the_lock(tmp_path,
                                                               monkeypatch):
    """_confirm parks each worker independently, so without a lock two
    approved operations can interleave over the same files."""
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api._eve_mutation.acquire()
    try:
        accepted = api.eve_settings_copy(str(profile / "core_char_1.dat"),
                                          [str(profile / "core_char_2.dat")])
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
    api.eve_settings_copy(str(profile / "core_char_1.dat"),
                          [str(profile / "core_char_2.dat")])
    assert api._eve_mutation.acquire(blocking=False) is True
    api._eve_mutation.release()


def test_select_persists_through_the_merging_writer(tmp_path, monkeypatch):
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api.eve_settings_select(str(profile.parent), str(profile))
    stored = settings.load(tmp_path / "OBSYouTubeUploader" / "settings.json")
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


def test_copy_refuses_a_target_outside_the_configured_root(tmp_path,
                                                           monkeypatch):
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


def test_backup_refuses_a_path_outside_the_configured_root(tmp_path,
                                                           monkeypatch):
    eve_tree(tmp_path)
    other = tmp_path / "elsewhere"
    other.mkdir()
    (other / "core_char_9.dat").write_bytes(b"x")
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api.eve_settings_backup(str(other), "profile")
    assert api.eve_settings_state()["backups"] == []


def test_a_failed_spawn_does_not_strand_the_mutation_lock(tmp_path,
                                                          monkeypatch):
    """Only the worker releases the lock, and a worker that never started
    never will -- every later operation would be refused for good."""
    profile = eve_tree(tmp_path)

    class Refuses:
        def __init__(self, **kwargs):
            pass

        def start(self):
            raise RuntimeError("can't start new thread")

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    state = api_mod.AppState(recording_dir=tmp_path,
                             settings=settings.load(tmp_path / "s.json"))
    api = api_mod.Api(state, spawn=Refuses)
    api._window = FakeWindow()
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    assert api.eve_settings_copy(str(profile / "core_char_1.dat"),
                                 [str(profile / "core_char_2.dat")]) is False
    assert api._eve_mutation.acquire(blocking=False) is True
    api._eve_mutation.release()


def test_a_confirmation_nobody_answers_does_not_strand_the_lock(tmp_path,
                                                                monkeypatch):
    """_push swallows every evaluate_js failure, so a confirmation whose
    push never reached the page would park the worker forever holding the
    lock. The wait is bounded and a missing answer reads as "no"."""
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    del api._eve_confirm  # back to the real, bounded implementation
    monkeypatch.setattr(api_mod, "EVE_CONFIRM_TIMEOUT_S", 0.05)
    api.eve_settings_copy(str(profile / "core_char_1.dat"),
                          [str(profile / "core_char_2.dat")])
    assert (profile / "core_char_2.dat").read_bytes() == b"payload-core_char_2.dat"
    assert api._eve_mutation.acquire(blocking=False) is True
    api._eve_mutation.release()


def test_every_mutation_pushes_a_completion_the_page_can_wait_on(tmp_path,
                                                                 monkeypatch):
    """eve_settings_copy returns as soon as the worker is spawned, so this
    push is the page's only signal that the work is actually done."""
    profile = eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api.eve_settings_copy(str(profile / "core_char_1.dat"),
                          [str(profile / "core_char_2.dat")])
    done = [c for c in api._window.calls if "onEveSettingsDone" in c]
    assert len(done) == 1 and '"ok": true' in done[0]


def test_a_failed_mutation_still_pushes_a_completion(tmp_path, monkeypatch):
    eve_tree(tmp_path)
    api = build(tmp_path, monkeypatch)
    api._state.settings["eve_settings"]["root"] = str(tmp_path / "EVE")
    api.eve_settings_backup("", "profile")
    done = [c for c in api._window.calls if "onEveSettingsDone" in c]
    assert len(done) == 1 and '"ok": false' in done[0]
