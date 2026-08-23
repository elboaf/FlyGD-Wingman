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
    monkeypatch.setattr(hotkeys.procid, "terminate", lambda pid: killed.append(pid))
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
                        lambda pid: order.append("kill"))
    spawner = FakeSpawner()

    eng = engine(tmp_path, spawner)
    eng.apply(section())
    eng.start()
    order.append("spawn")
    assert order == ["kill", "spawn"]
