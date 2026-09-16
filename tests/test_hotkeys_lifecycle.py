"""The supervisor is Windows-only at runtime but must import and be tested
on Linux, the same way ui/chrome.py is
(docs/history/window-resize-plan.md:130-140)."""

import subprocess

from wingman import bookmarks, hotkeys


class FakeProc:
    def __init__(self, pid=4321):
        self.pid = pid
        self.handle = object()  # A real Popen exposes the process handle.
        self._alive = True
        self.terminated = False
        self.killed = False

    def poll(self):
        return None if self._alive else 0

    def terminate(self):
        self.terminated = True
        self._alive = False

    def kill(self):
        self.killed = True
        self._alive = False

    def wait(self, timeout=None):
        if self._alive:
            raise subprocess.TimeoutExpired("ahk", timeout)
        return 0


class FakeSpawner:
    def __init__(self):
        self.calls = []
        self.proc = FakeProc()

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        return self.proc


def section(**over):
    base = {"enabled": True, "keybinds": dict(bookmarks.DEFAULT_BINDS), "windows": {}}
    base.update(over)
    return base


def engine(tmp_path, spawner, job_factory=lambda: None):
    (tmp_path / "ahk.exe").write_text("")
    (tmp_path / "e.ahk").write_text("")
    return hotkeys.HotkeyEngine(
        str(tmp_path / "ahk.exe"),
        tmp_path / "e.ahk",
        tmp_path,
        spawner=spawner,
        token_factory=lambda: "TOKEN123",
        job_factory=job_factory,
    )


def test_apply_writes_the_ini(tmp_path):
    eng = engine(tmp_path, FakeSpawner())
    eng.apply(section(keybinds=dict(bookmarks.DEFAULT_BINDS, FinH="^h")))
    text = (tmp_path / "eve_bookmark_helper.ini").read_text()
    assert "FinH=^h" in text


def test_start_spawns_interpreter_script_and_token(tmp_path):
    spawner = FakeSpawner()
    eng = engine(tmp_path, spawner)
    eng.apply(section())
    assert eng.start() is True
    argv, _kwargs = spawner.calls[0]
    assert argv[0] == str(tmp_path / "ahk.exe")
    assert argv[1] == str(tmp_path / "e.ahk")
    assert "TOKEN123" in argv


def test_start_runs_in_state_dir(tmp_path):
    """The script's IniFile is relative (111unified.ahk:71); cwd is what
    makes it resolve to our generated file rather than beside the exe."""
    spawner = FakeSpawner()
    eng = engine(tmp_path, spawner)
    eng.apply(section())
    eng.start()
    assert spawner.calls[0][1]["cwd"] == str(tmp_path)


def test_start_suppresses_a_console_window_on_windows(tmp_path, monkeypatch):
    """console=False build: without this a console flashes on every spawn
    (stitch.py:22-27)."""
    monkeypatch.setattr(hotkeys.sys, "platform", "win32")
    monkeypatch.setattr(hotkeys, "_NO_WINDOW_KWARGS", {"creationflags": 8})
    spawner = FakeSpawner()
    eng = engine(tmp_path, spawner)
    eng.apply(section())
    eng.start()
    assert spawner.calls[0][1]["creationflags"] == 8


def test_start_records_pid_and_token(tmp_path):
    eng = engine(tmp_path, FakeSpawner())
    eng.apply(section())
    eng.start()
    import json

    record = json.loads((tmp_path / "eve_engine.pid").read_text())
    assert record == {"pid": 4321, "token": "TOKEN123"}


def test_start_fails_cleanly_when_the_binary_is_missing(tmp_path):
    eng = hotkeys.HotkeyEngine(
        None, tmp_path / "e.ahk", tmp_path, spawner=FakeSpawner()
    )
    assert eng.start() is False
    assert eng.is_running() is False
    assert "engine" in (eng.last_error or "").lower()


def test_start_fails_cleanly_when_the_script_is_missing(tmp_path):
    (tmp_path / "ahk.exe").write_text("")
    eng = hotkeys.HotkeyEngine(
        str(tmp_path / "ahk.exe"), None, tmp_path, spawner=FakeSpawner()
    )
    assert eng.start() is False
    assert "engine" in (eng.last_error or "").lower()


def test_start_is_idempotent(tmp_path):
    spawner = FakeSpawner()
    eng = engine(tmp_path, spawner)
    eng.apply(section())
    eng.start()
    eng.start()
    assert len(spawner.calls) == 1


def test_start_stops_the_child_when_the_pid_record_cannot_be_written(
    tmp_path, monkeypatch
):
    """A write failure here must not leave a running, unrecorded child: with
    no PID file on disk, orphan recovery could never find it, yet
    is_running() would keep reporting the engine alive even though start()
    returned False."""
    spawner = FakeSpawner()
    eng = engine(tmp_path, spawner)
    eng.apply(section())

    def boom(path, text):
        raise OSError("disk full")

    monkeypatch.setattr(hotkeys.atomicio, "write_atomic", boom)
    assert eng.start() is False
    assert eng.is_running() is False
    assert spawner.proc.terminated is True
    assert "engine" in (eng.last_error or "").lower()
    assert not (tmp_path / "eve_engine.pid").exists()


def test_stop_terminates_and_clears_the_pid_record(tmp_path):
    eng = engine(tmp_path, FakeSpawner())
    eng.apply(section())
    eng.start()
    eng.stop()
    assert eng.is_running() is False
    assert not (tmp_path / "eve_engine.pid").exists()


def test_stop_escalates_to_kill_when_terminate_is_ignored(tmp_path):
    """A hung engine still holds a keyboard hook; leaving it is worse than
    killing it."""
    spawner = FakeSpawner()

    class Stubborn(FakeProc):
        def terminate(self):
            self.terminated = True  # ignores it

    spawner.proc = Stubborn()
    eng = engine(tmp_path, spawner)
    eng.apply(section())
    eng.start()
    eng.stop(timeout=0.01)
    assert spawner.proc.killed is True


def test_stop_is_safe_when_never_started(tmp_path):
    engine(tmp_path, FakeSpawner()).stop()


def test_is_running_reflects_process_death(tmp_path):
    spawner = FakeSpawner()
    eng = engine(tmp_path, spawner)
    eng.apply(section())
    eng.start()
    assert eng.is_running() is True
    spawner.proc._alive = False
    assert eng.is_running() is False


def test_no_window_kwargs_matches_the_platform():
    """CREATE_NO_WINDOW does not exist off Windows, so passing creationflags
    there would raise. The sibling test patches this constant directly, so
    nothing else would catch the idiom being computed wrongly."""
    if hotkeys.sys.platform == "win32":
        assert "creationflags" in hotkeys._NO_WINDOW_KWARGS
    else:
        assert hotkeys._NO_WINDOW_KWARGS == {}


def test_stop_clears_the_record_even_if_terminate_raises(tmp_path):
    """An already-reaped process raises from terminate(). Leaving the record
    behind would hand orphan recovery a pid that names nothing."""
    spawner = FakeSpawner()

    class Vanished(FakeProc):
        def terminate(self):
            raise ProcessLookupError("no such process")

    spawner.proc = Vanished()
    eng = engine(tmp_path, spawner)
    eng.apply(section())
    eng.start()
    eng.stop()
    assert not (tmp_path / "eve_engine.pid").exists()
    assert eng.is_running() is False


def test_stop_clears_the_record_even_if_kill_raises(tmp_path):
    spawner = FakeSpawner()

    class Stubborn(FakeProc):
        def terminate(self):
            self.terminated = True

        def kill(self):
            raise OSError("bad handle")

    spawner.proc = Stubborn()
    eng = engine(tmp_path, spawner)
    eng.apply(section())
    eng.start()
    eng.stop(timeout=0.01)
    assert not (tmp_path / "eve_engine.pid").exists()


def test_a_failed_terminate_escalates_to_kill(tmp_path):
    """Only ProcessLookupError means the process was already gone. Any other
    OSError means terminate() failed and the engine is still running -- and
    still holding a global keyboard hook. Returning there would report a
    clean stop while the hook survives."""
    spawner = FakeSpawner()

    class Denied(FakeProc):
        def terminate(self):
            raise PermissionError("access denied")

    spawner.proc = Denied()
    eng = engine(tmp_path, spawner)
    eng.apply(section())
    eng.start()
    eng.stop(timeout=0.01)
    assert spawner.proc.killed is True
    assert not (tmp_path / "eve_engine.pid").exists()


def test_a_vanished_process_is_not_escalated(tmp_path):
    """ProcessLookupError is the one case that really does mean gone; killing
    again would be pointless noise."""
    spawner = FakeSpawner()

    class Vanished(FakeProc):
        def terminate(self):
            raise ProcessLookupError("no such process")

    spawner.proc = Vanished()
    eng = engine(tmp_path, spawner)
    eng.apply(section())
    eng.start()
    eng.stop()
    assert spawner.proc.killed is False
    assert not (tmp_path / "eve_engine.pid").exists()


class FakeJob:
    def __init__(self):
        self.assigned = None
        self.closed = False

    def assign(self, proc):
        self.assigned = proc
        return True

    def close(self):
        self.closed = True


def test_start_assigns_the_engine_to_a_kill_on_close_job(tmp_path):
    """The job is what kills the engine when this process dies by any means
    the code does not get a say in -- the kernel closes our handle and the
    job's KILL_ON_JOB_CLOSE limit does the rest."""
    spawner = FakeSpawner()
    job = FakeJob()
    eng = engine(tmp_path, spawner, job_factory=lambda: job)
    eng.apply(section())
    eng.start()
    assert job.assigned is spawner.proc.handle
    assert not job.closed


def test_stop_closes_the_job(tmp_path):
    spawner = FakeSpawner()
    job = FakeJob()
    eng = engine(tmp_path, spawner, job_factory=lambda: job)
    eng.apply(section())
    eng.start()
    eng.stop()
    assert job.closed is True


def test_a_failed_job_assignment_falls_back_to_stop_only(tmp_path):
    """Nested-job denial or a bad handle must not fail the start; the
    historical stop()-only cleanup is the fallback, not an error."""
    spawner = FakeSpawner()

    class Denied(FakeJob):
        def assign(self, proc):
            return False

    job = Denied()
    eng = engine(tmp_path, spawner, job_factory=lambda: job)
    eng.apply(section())
    assert eng.start() is True
    assert eng.is_running() is True
    assert job.closed is True
    eng.stop()
    assert spawner.proc.terminated is True


def test_a_raising_job_factory_does_not_block_start(tmp_path):
    spawner = FakeSpawner()

    def boom():
        raise OSError("no kernel32")

    eng = engine(tmp_path, spawner, job_factory=boom)
    eng.apply(section())
    assert eng.start() is True
    assert eng.is_running() is True


def test_default_job_factory_is_inert_off_windows():
    if hotkeys.sys.platform != "win32":
        assert hotkeys._default_job() is None
