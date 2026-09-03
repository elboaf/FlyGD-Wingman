"""Tray Quit while an upload is in flight.

The upload runs on a daemon thread (`Api.start_upload`), so tray Quit ends
the process and the upload dies mid-chunk with nothing on screen. These
cover the guard that turns that silent discard into a decision.

Driven at the Api seam rather than through `__main__.on_quit`, which is a
closure inside main() that no test can reach. That is the point of putting
the decision on Api: on_quit is left as glue thin enough to read.
"""

import threading

import pytest

from tests.test_api import FakeWindow, make_api
from wingman.ui import api as api_mod

# Released by the autouse fixture below. The stand-in upload holds the same
# claim as a real worker so Quit exercises the production synchronization
# contract rather than relying on a thread handle's liveness.
stop = threading.Event()


@pytest.fixture(autouse=True)
def _release_workers():
    stop.clear()
    yield
    stop.set()


def busy_api(tmp_path, window=None, **kw):
    """An Api that reports an upload in flight, without running one."""
    api = make_api(tmp_path, window if window is not None else FakeWindow(), **kw)
    assert api._work_gate.claim_upload()

    def hold_claim():
        try:
            stop.wait(5)
        finally:
            api._work_gate.release_upload()

    api._upload_thread = threading.Thread(target=hold_claim)
    api._upload_thread.start()
    return api


def test_quitting_while_idle_asks_nothing_and_does_not_raise_the_window(tmp_path):
    """The guard must be invisible in the ordinary case.

    Quit is the only way out of a tray app; a confirm on every exit would
    be the padding PRODUCT.md's tone rule rules out.
    """
    window = FakeWindow()
    api = make_api(tmp_path, window)

    assert api._confirm_quit_if_busy() is True
    assert window.shown == 0
    assert window.evaluated == [], "an idle quit must push no dialog"
    assert not api._work_gate.claim_upload(), "Quit did not atomically close the gate"


def test_a_busy_quit_raises_the_window_before_asking(tmp_path):
    """REGRESSION GUARD for the trap that makes this more than one predicate.

    This is a tray app and the window is normally hidden -- `--hidden` is
    how it boots at login. A dialog pushed into a hidden window is one the
    user can neither see nor answer, and the ask blocks, so Quit would
    become a control that silently does nothing until the timeout.
    """
    window = FakeWindow()
    api = busy_api(tmp_path, window, id_factory=lambda: "q-1")

    worker = threading.Thread(target=api._confirm_quit_if_busy)
    worker.start()
    for _ in range(500):
        if window.evaluated:
            break
        worker.join(0.01)

    assert window.shown == 1, "the dialog was pushed into a window nobody can see"
    api.dialog_response("q-1", True)
    worker.join(5)


def test_confirming_a_busy_quit_returns_true(tmp_path):
    api = busy_api(tmp_path, id_factory=lambda: "q-2")
    result = {}

    worker = threading.Thread(
        target=lambda: result.update(ok=api._confirm_quit_if_busy())
    )
    worker.start()
    for _ in range(500):
        api.dialog_response("q-2", True)
        worker.join(0.01)
        if not worker.is_alive():
            break
    assert result == {"ok": True}
    stop.set()
    api._upload_thread.join(timeout=5)
    assert not api._work_gate.claim_upload(), "confirmed Quit did not close the gate"


def test_declining_a_busy_quit_returns_false(tmp_path):
    api = busy_api(tmp_path, id_factory=lambda: "q-3")
    result = {}

    worker = threading.Thread(
        target=lambda: result.update(ok=api._confirm_quit_if_busy())
    )
    worker.start()
    for _ in range(500):
        api.dialog_response("q-3", False)
        worker.join(0.01)
        if not worker.is_alive():
            break
    assert result == {"ok": False}


def test_an_unanswered_quit_is_read_as_do_not_quit(tmp_path, monkeypatch):
    """The conservative default, and the reason the ask is bounded at all.

    A page that never answers -- crashed, mid-reload -- must not park the
    pystray thread forever. Reading silence as "stay running" costs the
    user a second click; reading it as "quit" costs them the upload.
    """
    monkeypatch.setattr(api_mod, "QUIT_CONFIRM_TIMEOUT_S", 0.05)
    api = busy_api(tmp_path)

    assert api._confirm_quit_if_busy() is False


def test_quit_refusal_keeps_handoff_reason_if_state_changes_before_alert(tmp_path):
    window = FakeWindow()
    api = make_api(tmp_path, window)
    alerts = []
    api._alert = lambda *args: alerts.append(args)
    assert api._work_gate.claim_handoff("handing_off")
    after_claim = threading.Barrier(2)
    real_claim = api._work_gate.claim_quit

    def paused_claim(*, force_upload):
        result = real_claim(force_upload=force_upload)
        after_claim.wait(timeout=2)
        after_claim.wait(timeout=2)
        return result

    api._work_gate.claim_quit = paused_claim
    result = {}
    worker = threading.Thread(target=lambda: result.update(ok=api._claim_quit()))
    worker.start()
    after_claim.wait(timeout=2)
    api._work_gate.release_handoff()
    after_claim.wait(timeout=2)
    worker.join(timeout=2)

    assert result == {"ok": False}
    assert window.shown == 1
    assert alerts == [("info", "Update", "Update installation is being prepared.")]


def test_quit_refused_while_quitting_explains_update_shutdown(tmp_path):
    window = FakeWindow()
    api = make_api(tmp_path, window)
    alerts = []
    api._alert = lambda *args: alerts.append(args)
    assert api._work_gate.claim_quit(force_upload=False)

    assert api._claim_quit() is False

    assert window.shown == 1
    assert alerts == [("info", "Update", "Update installation is being prepared.")]


def test_quit_is_refused_with_information_during_each_handoff_phase(tmp_path):
    for phase in ("handing_off", "revalidating", "launching"):
        window = FakeWindow()
        api = make_api(tmp_path, window)
        alerts = []
        api._alert = lambda *args: alerts.append(args)
        assert api._work_gate.claim_handoff(phase)

        assert api._claim_quit() is False

        assert window.shown == 1
        assert alerts == [("info", "Update", "Update installation is being prepared.")]


def test_forced_quit_refusal_keeps_handoff_reason_if_handoff_then_releases(tmp_path):
    window = FakeWindow()
    api = busy_api(tmp_path, window)
    alerts = []
    api._alert = lambda *args: alerts.append(args)
    after_claim = threading.Barrier(2)
    real_claim = api._work_gate.claim_quit

    def approve_then_handoff(*args, **kwargs):
        stop.set()
        api._upload_thread.join(timeout=5)
        assert api._work_gate.claim_handoff("handing_off")
        return True

    def paused_claim(*, force_upload):
        result = real_claim(force_upload=force_upload)
        if force_upload and not result:
            after_claim.wait(timeout=2)
            after_claim.wait(timeout=2)
        return result

    api._ask = approve_then_handoff
    api._work_gate.claim_quit = paused_claim
    result = {}
    worker = threading.Thread(target=lambda: result.update(ok=api._claim_quit()))
    worker.start()
    after_claim.wait(timeout=2)
    api._work_gate.release_handoff()
    after_claim.wait(timeout=2)
    worker.join(timeout=2)

    assert result == {"ok": False}
    assert window.shown == 2
    assert alerts == [("info", "Update", "Update installation is being prepared.")]


def test_handoff_winning_during_upload_confirmation_refuses_quit(tmp_path):
    window = FakeWindow()
    api = busy_api(tmp_path, window, id_factory=lambda: "q-4")
    alerts = []
    api._alert = lambda *args: alerts.append(args)
    result = {}
    worker = threading.Thread(target=lambda: result.update(ok=api._claim_quit()))
    worker.start()
    for _ in range(500):
        if window.evaluated:
            break
        worker.join(0.01)

    stop.set()
    api._upload_thread.join(timeout=5)
    assert api._work_gate.claim_handoff("handing_off")
    api.dialog_response("q-4", True)
    worker.join(timeout=5)

    assert result == {"ok": False}
    assert window.shown == 2
    assert alerts == [("info", "Update", "Update installation is being prepared.")]


def test_the_dialog_cannot_carry_the_previous_uploads_percentage(tmp_path, monkeypatch):
    """Anything derived must be derived, not left over.

    `_last_pct` is only ever written by a progress callback, so without a
    reset a job that quits before its first chunk reports the LAST job's
    number -- in a dialog whose whole job is stating the real cost. The
    same staleness reaches on_retry's bar, which is why the reset lives in
    the worker rather than in the quit path.
    """
    monkeypatch.setattr(
        api_mod.uploader,
        "load_credentials",
        lambda p: (_ for _ in ()).throw(RuntimeError("no token")),
    )
    api = make_api(tmp_path)
    api._alert = lambda *a: None
    api._last_pct = 90.0

    # The reset is before the try; the worker then fails on credentials and
    # reports it, which is the path an interrupted job takes for real.
    api._upload_worker(
        api_mod.UploadJob(
            items=[],
            ids=[],
            title="t",
            description="d",
            stitch=False,
            privacy="unlisted",
            category="20",
            logs=False,
        )
    )

    assert api._last_pct == 0.0
