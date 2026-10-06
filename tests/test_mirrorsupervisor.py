"""MirrorSupervisor (issue #317): engine-pattern guardianship for
wingman-mirror.exe, on the extracted ProcGuard core.

Fakes come from test_hotkeys_lifecycle (the engine's own harness) on
purpose: the supervisor must be substitutable at exactly the seams the
engine already proved -- spawner, run token, job factory -- plus procid
for orphan identity. Linux-runnable throughout; no mirror process, no
window, no sleeper threads: restart accounting is clock-injected, the
way AlertPolicy's cooldowns are.
"""

import json

from tests.test_hotkeys_lifecycle import FakeProc, FakeSpawner
from wingman import mirrorsupervisor


def supervisor(tmp_path, spawner, **kw):
    (tmp_path / "wingman-mirror.exe").write_text("")
    kw.setdefault("token_factory", lambda: "TOKEN123")
    kw.setdefault("job_factory", lambda: None)
    return mirrorsupervisor.MirrorSupervisor(
        str(tmp_path / "wingman-mirror.exe"),
        tmp_path,
        spawner=spawner,
        **kw,
    )


def test_start_spawns_the_exe_with_a_run_token_and_writes_the_record(tmp_path):
    spawner = FakeSpawner()
    sup = supervisor(tmp_path, spawner)

    assert sup.start() is True

    argv = spawner.calls[0][0]
    assert argv[0].endswith("wingman-mirror.exe")
    assert "--token" in argv and argv[argv.index("--token") + 1] == "TOKEN123"
    record = json.loads((tmp_path / "wingman_mirror.pid").read_text(encoding="utf-8"))
    assert record == {"pid": spawner.proc.pid, "token": "TOKEN123"}
    assert sup.is_running() is True


def test_start_binds_the_child_to_the_job_object(tmp_path):
    assigned = []

    class Job:
        def assign(self, handle):
            assigned.append(handle)
            return True

        def close(self):
            pass

    spawner = FakeSpawner()
    sup = supervisor(tmp_path, spawner, job_factory=Job)

    assert sup.start() is True
    assert assigned == [spawner.proc._handle]


def test_start_with_a_missing_exe_reports_and_stays_down(tmp_path):
    spawner = FakeSpawner()
    sup = mirrorsupervisor.MirrorSupervisor(
        str(tmp_path / "absent.exe"),
        tmp_path,
        spawner=spawner,
        token_factory=lambda: "T",
        job_factory=lambda: None,
    )

    assert sup.start() is False
    assert sup.last_error
    assert sup.is_running() is False
    assert spawner.calls == []


def test_stop_terminates_and_clears_the_record(tmp_path):
    spawner = FakeSpawner()
    sup = supervisor(tmp_path, spawner)
    sup.start()

    sup.stop()

    assert spawner.proc.terminated
    assert not (tmp_path / "wingman_mirror.pid").exists()
    assert sup.is_running() is False


def test_ensure_running_restarts_an_out_of_band_death(tmp_path):
    """Discord's own UI, a user killing it, a crash: a dead mirror the
    user asked for is restarted -- this is the recovery the card row
    reflects. The pid record must be rewritten (fresh pid, fresh token),
    or the next recovery would chase a corpse."""
    spawner = FakeSpawner()
    spawner.proc = FakeProc(pid=100)
    sup = supervisor(tmp_path, spawner)
    sup.start()

    spawner.proc._alive = False  # the started mirror dies out-of-band
    spawner.proc = FakeProc(pid=101)  # the replacement it will spawn
    assert sup.ensure_running(now=1000.0) is True
    assert spawner.calls[1][0][0].endswith("wingman-mirror.exe")
    record = json.loads((tmp_path / "wingman_mirror.pid").read_text(encoding="utf-8"))
    assert record == {"pid": 101, "token": "TOKEN123"}


def test_ensure_running_gives_up_after_bounded_retries(tmp_path):
    spawner = FakeSpawner()
    sup = supervisor(tmp_path, spawner, restart_limit=2, restart_window_s=60.0)
    sup.start()

    # Two out-of-band deaths inside the window: both restarted (initial
    # start + limit), the third ask gives up and says so.
    for _ in range(2):
        spawner.proc._alive = False  # the current child dies
        spawner.proc = FakeProc(pid=spawner.proc.pid + 1)  # next spawn
        assert sup.ensure_running(now=1000.0) is True

    spawner.proc._alive = False
    assert sup.ensure_running(now=1001.0) is False
    assert sup.gave_up is True
    assert sup.last_error
    assert len(spawner.calls) == 3  # initial + 2 retries, no more


def test_restart_window_expiry_re_arms_the_budget(tmp_path):
    """Bounded retries are a burst guard, not a lifetime cap: deaths
    spread outside the window are independent failures."""
    spawner = FakeSpawner()
    sup = supervisor(tmp_path, spawner, restart_limit=1, restart_window_s=60.0)
    sup.start()

    spawner.proc = FakeProc(pid=200)
    spawner.proc._alive = False
    assert sup.ensure_running(now=1000.0) is True  # one retry in budget

    spawner.proc._alive = False
    assert sup.ensure_running(now=2000.0) is True  # window expired: re-armed


def test_status_states_are_driven_by_liveness(tmp_path):
    """The status file outlives the process that wrote it -- the engine's
    lesson -- so states derive from the child handle, never from the
    record on disk."""
    spawner = FakeSpawner()
    sup = supervisor(tmp_path, spawner)

    assert sup.status(enabled=False).state == "off"
    assert sup.status(enabled=True).state == "stopped"

    sup.start()
    assert sup.status(enabled=True).state == "running"

    spawner.proc._alive = False
    sup.ensure_running(now=1000.0)  # a death the budget already absorbed
    assert sup.status(enabled=True).state in ("running", "stopped")


def test_status_reports_given_up_when_the_budget_is_spent(tmp_path):
    spawner = FakeSpawner()
    sup = supervisor(tmp_path, spawner, restart_limit=0)
    sup.start()

    spawner.proc._alive = False
    sup.ensure_running(now=1000.0)

    status = sup.status(enabled=True)
    assert status.state == "given-up"
    assert status.last_error


def test_start_recovers_a_leftover_orphan_first(tmp_path, monkeypatch):
    """Engine rule, kept: the orphan record is resolved before a new
    spawn, even when the user has since turned the feature off -- a live
    mirror nobody can address is the failure the job object only partly
    covers."""
    (tmp_path / "wingman_mirror.pid").write_text(
        json.dumps({"pid": 999, "token": "TOKEN123"}), encoding="utf-8"
    )
    killed = []
    monkeypatch.setattr(
        mirrorsupervisor.procid,
        "describe",
        lambda pid: {
            "image": r"C:\app\bin\wingman-mirror.exe",
            "cmdline": r"wingman-mirror.exe --token TOKEN123",
        },
    )
    monkeypatch.setattr(
        mirrorsupervisor.procid,
        "terminate",
        lambda pid: killed.append(pid) or True,
    )
    spawner = FakeSpawner()
    sup = supervisor(tmp_path, spawner)

    assert sup.start() is True
    assert killed == [999]
    assert sup.is_running() is True
