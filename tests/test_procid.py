"""terminate() feeds HotkeyEngine.recover_orphan, which relies on a False
return to keep the PID record for another try. A taskkill that exits
non-zero without raising must not be reported as a successful kill."""

from types import SimpleNamespace

from obs_youtube_uploader import procid


def fake_runner(returncode, stderr=""):
    return lambda argv, **kwargs: SimpleNamespace(
        returncode=returncode, stdout="", stderr=stderr
    )


def test_terminate_reports_success_on_zero_returncode(monkeypatch):
    monkeypatch.setattr(procid.sys, "platform", "win32")
    assert procid.terminate(123, runner=fake_runner(0)) is True


def test_terminate_reports_failure_when_taskkill_exits_nonzero(monkeypatch):
    """taskkill exits non-zero for "process not found" and "access denied"
    alike, without raising -- a bare exception guard would treat both as a
    successful kill."""
    monkeypatch.setattr(procid.sys, "platform", "win32")
    assert procid.terminate(123, runner=fake_runner(1, "Access is denied.")) is False


def test_terminate_reports_failure_when_runner_raises(monkeypatch):
    monkeypatch.setattr(procid.sys, "platform", "win32")

    def boom(argv, **kwargs):
        raise OSError("no such command")

    assert procid.terminate(123, runner=boom) is False


def test_terminate_is_a_noop_off_windows(monkeypatch):
    monkeypatch.setattr(procid.sys, "platform", "linux")
    assert procid.terminate(123, runner=fake_runner(0)) is False
