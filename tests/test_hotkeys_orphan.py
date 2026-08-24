"""If Wingman crashes, the engine survives holding a global keyboard hook
with no UI left to disable it. Recovery is the backstop -- but it kills a
process, so identity has to be right."""
import json

from obs_youtube_uploader import hotkeys
from tests.test_hotkeys_lifecycle import FakeSpawner, engine, section


def write_record(tmp_path, pid=999, token="TOKEN123"):
    (tmp_path / "eve_engine.pid").write_text(
        json.dumps({"pid": pid, "token": token}))


def test_kills_a_matching_orphan(tmp_path, monkeypatch):
    write_record(tmp_path)
    killed = []
    monkeypatch.setattr(hotkeys.procid, "describe", lambda pid: {
        "image": r"C:\app\bin\AutoHotkeyU64.exe",
        "cmdline": r'AutoHotkeyU64.exe eve_bookmarks.ahk /token TOKEN123'})
    monkeypatch.setattr(hotkeys.procid, "terminate",
                        lambda pid: killed.append(pid) or True)
    eng = engine(tmp_path, FakeSpawner())
    assert eng.recover_orphan() is True
    assert killed == [999]


def test_does_not_kill_a_reused_pid(tmp_path, monkeypatch):
    """Windows reuses PIDs, and this path runs precisely after an unclean
    shutdown -- the recorded PID may since belong to anything."""
    write_record(tmp_path)
    killed = []
    monkeypatch.setattr(hotkeys.procid, "describe", lambda pid: {
        "image": r"C:\Windows\explorer.exe", "cmdline": "explorer.exe"})
    monkeypatch.setattr(hotkeys.procid, "terminate", lambda pid: killed.append(pid))
    eng = engine(tmp_path, FakeSpawner())
    assert eng.recover_orphan() is False
    assert killed == []


def test_does_not_kill_the_interpreter_running_another_script(tmp_path, monkeypatch):
    """The image path alone is not identity: AutoHotkey is a general
    interpreter and the user may be running their own scripts."""
    write_record(tmp_path)
    killed = []
    monkeypatch.setattr(hotkeys.procid, "describe", lambda pid: {
        "image": r"C:\app\bin\AutoHotkeyU64.exe",
        "cmdline": r"AutoHotkeyU64.exe someone-elses.ahk"})
    monkeypatch.setattr(hotkeys.procid, "terminate", lambda pid: killed.append(pid))
    eng = engine(tmp_path, FakeSpawner())
    assert eng.recover_orphan() is False
    assert killed == []


def test_stale_record_for_a_dead_pid_is_discarded(tmp_path, monkeypatch):
    write_record(tmp_path)
    monkeypatch.setattr(hotkeys.procid, "describe", lambda pid: None)
    eng = engine(tmp_path, FakeSpawner())
    assert eng.recover_orphan() is False
    assert not (tmp_path / "eve_engine.pid").exists()


def test_corrupt_record_is_survivable(tmp_path, monkeypatch):
    (tmp_path / "eve_engine.pid").write_text("{ not json")
    monkeypatch.setattr(hotkeys.procid, "describe", lambda pid: None)
    eng = engine(tmp_path, FakeSpawner())
    assert eng.recover_orphan() is False


def test_no_record_is_not_an_error(tmp_path):
    assert engine(tmp_path, FakeSpawner()).recover_orphan() is False


def test_start_recovers_before_spawning(tmp_path, monkeypatch):
    write_record(tmp_path)
    order = []
    monkeypatch.setattr(hotkeys.procid, "describe", lambda pid: {
        "image": r"bin\AutoHotkeyU64.exe",
        "cmdline": "AutoHotkeyU64.exe eve_bookmarks.ahk /token TOKEN123"})
    monkeypatch.setattr(hotkeys.procid, "terminate",
                        lambda pid: order.append("kill") or True)
    spawner = FakeSpawner()

    eng = engine(tmp_path, spawner)
    eng.apply(section())
    eng.start()
    order.append("spawn")
    assert order == ["kill", "spawn"]


def test_an_undecodable_command_line_does_not_prevent_starting(tmp_path, monkeypatch):
    """describe() must never raise: one foreign-locale process on the
    machine would otherwise stop the engine starting at all."""
    write_record(tmp_path)

    def boom(pid):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad")

    monkeypatch.setattr(hotkeys.procid, "describe", boom)
    eng = engine(tmp_path, FakeSpawner())
    assert eng.recover_orphan() is False
    assert (tmp_path / "eve_engine.pid").exists()   # not discarded


def test_a_failed_kill_keeps_the_record(tmp_path, monkeypatch):
    """The record is the only handle for retrying next start; discarding it
    after a failed kill strands a live keyboard hook."""
    write_record(tmp_path)
    monkeypatch.setattr(hotkeys.procid, "describe", lambda pid: {
        "image": r"C:\app\bin\AutoHotkeyU64.exe",
        "cmdline": "AutoHotkeyU64.exe eve_bookmarks.ahk /token TOKEN123"})
    monkeypatch.setattr(hotkeys.procid, "terminate", lambda pid: False)
    eng = engine(tmp_path, FakeSpawner())
    assert eng.recover_orphan() is False
    assert (tmp_path / "eve_engine.pid").exists()


def test_an_unrelated_exe_under_an_autohotkey_folder_is_not_ours(tmp_path, monkeypatch):
    """Basename equality, not a substring: a folder named AutoHotkeyBackup
    must not make an unrelated executable look like the engine."""
    write_record(tmp_path)
    monkeypatch.setattr(hotkeys.procid, "describe", lambda pid: {
        "image": r"C:\Users\bob\AutoHotkeyBackup\notepad.exe",
        "cmdline": "notepad.exe /token TOKEN123"})
    killed = []
    monkeypatch.setattr(hotkeys.procid, "terminate",
                        lambda pid: killed.append(pid) or True)
    eng = engine(tmp_path, FakeSpawner())
    assert eng.recover_orphan() is False
    assert killed == []


def test_an_unremovable_pid_record_is_logged_not_swallowed(tmp_path, caplog):
    """The bare `except OSError: pass` here left nothing behind at all.

    It is still non-fatal -- every caller has to reach its own outcome
    whether or not the record went away, and the next recover_orphan clears
    it once the pid is dead -- but a record that repeatedly cannot be
    removed means something is holding it, and that was invisible.
    """
    import logging
    eng = engine(tmp_path, FakeSpawner())

    class Boom:
        def unlink(self):
            raise OSError("held open by something")

    eng._pid_path = lambda: Boom()
    with caplog.at_level(logging.WARNING):
        eng._clear_pid_record()          # must not raise
    assert "engine PID record" in caplog.text
    assert "held open by something" in caplog.text
