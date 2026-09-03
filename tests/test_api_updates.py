"""Atomic work claims and updater lifecycle orchestration."""

import threading
from pathlib import Path

import pytest

from tests import fakes
from wingman import settings as settings_mod
from wingman import updates as updates_mod
from wingman.ui import api as api_mod


def _upload_api(tmp_path):
    rows = fakes.FakeRows({"r1": fakes.info(tmp_path / "r1.mkv")})
    api, window = fakes.build_api(tmp_path, rows=rows)
    api._alert = fakes.Alerts()
    api._confirm = fakes.Answers()
    return api, window


def _join_upload(api):
    thread = api._upload_thread
    if thread is not None:
        thread.join(timeout=5)
        assert not thread.is_alive()


def _enable_retry(api):
    api._retry_state = api_mod.RetryState(
        job=api_mod.UploadJob(
            items=[],
            ids=[],
            title="Fight",
            description="",
            stitch=False,
            privacy="unlisted",
            category="20",
        ),
        resume_index=0,
        request=None,
    )


# ---- private work gate ----------------------------------------------------


def test_handoff_and_upload_claims_are_mutually_exclusive():
    gate = api_mod._WorkGate()
    assert gate.claim_upload()
    assert not gate.claim_handoff("handing_off")
    gate.release_upload()
    assert gate.claim_handoff("handing_off")
    assert not gate.claim_upload()


def test_quit_is_refused_during_each_handoff_phase():
    for phase in ("handing_off", "revalidating", "launching"):
        gate = api_mod._WorkGate()
        assert gate.claim_handoff(phase)
        assert gate.handoff_phase() == phase
        assert not gate.claim_quit(force_upload=False)


def test_failed_handoff_release_allows_upload_to_claim():
    gate = api_mod._WorkGate()
    assert gate.claim_handoff("revalidating")

    gate.release_handoff()

    assert gate.handoff_phase() == ""
    assert gate.claim_upload()


def test_update_shutdown_is_idempotent_for_the_handoff_owner():
    gate = api_mod._WorkGate()
    assert not gate.begin_update_shutdown()
    assert gate.claim_handoff("launching")

    assert gate.begin_update_shutdown()
    assert gate.begin_update_shutdown()
    assert gate.handoff_phase() == "launching"
    assert not gate.claim_upload()


def test_quitting_blocks_new_upload_and_handoff_claims():
    gate = api_mod._WorkGate()
    assert gate.claim_quit(force_upload=False)

    assert not gate.claim_upload()
    assert not gate.claim_handoff("handing_off")


def test_quit_requires_force_while_an_upload_is_claimed():
    gate = api_mod._WorkGate()
    assert gate.claim_upload()

    assert not gate.claim_quit(force_upload=False)
    assert gate.claim_quit(force_upload=True)


# ---- bridge-call races ----------------------------------------------------


def test_upload_and_handoff_race_has_exactly_one_winner(tmp_path):
    api, _window = _upload_api(tmp_path)
    bridge_calls = threading.Barrier(3)
    release_worker = threading.Event()
    results = {}
    api._confirm_then_upload = lambda _job: release_worker.wait(5)

    def upload_call():
        bridge_calls.wait(timeout=2)
        api.start_upload("Fight", "", False, ["r1"])

    def handoff_call():
        bridge_calls.wait(timeout=2)
        results["handoff"] = bool(api._work_gate.claim_handoff("handing_off"))

    upload_bridge = threading.Thread(target=upload_call)
    handoff_bridge = threading.Thread(target=handoff_call)
    upload_bridge.start()
    handoff_bridge.start()
    bridge_calls.wait(timeout=2)
    upload_bridge.join(timeout=2)
    handoff_bridge.join(timeout=2)
    assert not upload_bridge.is_alive()
    assert not handoff_bridge.is_alive()

    try:
        assert api._busy() is not results["handoff"]
    finally:
        release_worker.set()
        _join_upload(api)
        api._work_gate.release_handoff()


def test_retry_and_handoff_race_has_exactly_one_winner(tmp_path):
    api, _window = _upload_api(tmp_path)
    api._retry_state = api_mod.RetryState(
        job=api_mod.UploadJob(
            items=[],
            ids=[],
            title="Fight",
            description="",
            stitch=False,
            privacy="unlisted",
            category="20",
        ),
        resume_index=0,
        request=None,
    )
    bridge_calls = threading.Barrier(3)
    release_worker = threading.Event()
    results = {}
    api._retry_worker = lambda _state: release_worker.wait(5)

    def retry_call():
        bridge_calls.wait(timeout=2)
        api.retry()

    def handoff_call():
        bridge_calls.wait(timeout=2)
        results["handoff"] = bool(api._work_gate.claim_handoff("handing_off"))

    retry_bridge = threading.Thread(target=retry_call)
    handoff_bridge = threading.Thread(target=handoff_call)
    retry_bridge.start()
    handoff_bridge.start()
    bridge_calls.wait(timeout=2)
    retry_bridge.join(timeout=2)
    handoff_bridge.join(timeout=2)
    assert not retry_bridge.is_alive()
    assert not handoff_bridge.is_alive()

    try:
        assert api._busy() is not results["handoff"]
    finally:
        release_worker.set()
        _join_upload(api)
        api._work_gate.release_handoff()


def test_upload_refusal_keeps_handoff_reason_if_state_changes_before_alert(
    tmp_path,
):
    api, _window = _upload_api(tmp_path)
    assert api._work_gate.claim_handoff("handing_off")
    after_claim = threading.Barrier(2)
    real_claim = api._work_gate.claim_upload

    def paused_claim():
        result = real_claim()
        after_claim.wait(timeout=2)
        after_claim.wait(timeout=2)
        return result

    api._work_gate.claim_upload = paused_claim
    bridge = threading.Thread(
        target=lambda: api.start_upload("Fight", "", False, ["r1"])
    )
    bridge.start()
    after_claim.wait(timeout=2)
    api._work_gate.release_handoff()
    after_claim.wait(timeout=2)
    bridge.join(timeout=2)

    assert not bridge.is_alive()
    assert api._alert.raised == [
        ("info", "Update", "Update installation is being prepared.")
    ]


def test_upload_refused_while_quitting_explains_update_shutdown(tmp_path):
    api, _window = _upload_api(tmp_path)
    assert api._work_gate.claim_quit(force_upload=False)

    api.start_upload("Fight", "", False, ["r1"])

    assert api._upload_thread is None
    assert api._alert.raised == [
        ("info", "Update", "Update installation is being prepared.")
    ]


def test_retry_refused_during_handoff_is_disabled_and_explained(tmp_path):
    api, _window = _upload_api(tmp_path)
    _enable_retry(api)
    assert api._work_gate.claim_handoff("handing_off")
    sent = fakes.record_pushes(api)

    api.retry()

    assert api._upload_thread is None
    assert fakes.payloads(sent, "onRetryAvailable") == [{"available": False}]
    assert api._alert.raised == [
        ("info", "Update", "Update installation is being prepared.")
    ]


def test_retry_refused_while_quitting_is_disabled_and_explained(tmp_path):
    api, _window = _upload_api(tmp_path)
    _enable_retry(api)
    assert api._work_gate.claim_quit(force_upload=False)
    sent = fakes.record_pushes(api)

    api.retry()

    assert api._upload_thread is None
    assert fakes.payloads(sent, "onRetryAvailable") == [{"available": False}]
    assert api._alert.raised == [
        ("info", "Update", "Update installation is being prepared.")
    ]


def test_retry_refused_by_an_upload_is_disabled_and_names_the_upload(tmp_path):
    api, _window = _upload_api(tmp_path)
    _enable_retry(api)
    assert api._work_gate.claim_upload()
    sent = fakes.record_pushes(api)

    try:
        api.retry()
    finally:
        api._work_gate.release_upload()

    assert api._upload_thread is None
    assert fakes.payloads(sent, "onRetryAvailable") == [{"available": False}]
    assert api._alert.raised == [
        ("warning", "Busy", "An upload is already in progress.")
    ]


def test_upload_claim_lives_until_worker_finally(tmp_path):
    api, _window = _upload_api(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    def block(_job):
        entered.set()
        release.wait(5)

    api._confirm_then_upload = block
    api.start_upload("Fight", "", False, ["r1"])

    assert entered.wait(1)
    assert api._busy()
    release.set()
    _join_upload(api)
    assert not api._busy()


def test_upload_claim_is_released_when_the_worker_target_raises(tmp_path):
    api, _window = _upload_api(tmp_path)
    assert api._work_gate.claim_upload()

    def explode():
        raise RuntimeError("worker exploded")

    with pytest.raises(RuntimeError, match="worker exploded"):
        api._run_claimed_upload(explode)

    assert not api._busy()


def test_upload_is_claimed_before_thread_start(tmp_path, monkeypatch):
    api, _window = _upload_api(tmp_path)
    api._confirm_then_upload = lambda _job: None
    observed = []
    real_start = threading.Thread.start

    def start(thread):
        observed.append(api._busy())
        real_start(thread)

    monkeypatch.setattr(api_mod.threading.Thread, "start", start)
    api.start_upload("Fight", "", False, ["r1"])
    monkeypatch.undo()
    _join_upload(api)

    assert observed == [True]


def test_retry_is_claimed_before_thread_start(tmp_path, monkeypatch):
    api, _window = _upload_api(tmp_path)
    api._retry_state = api_mod.RetryState(
        job=api_mod.UploadJob(
            items=[],
            ids=[],
            title="Fight",
            description="",
            stitch=False,
            privacy="unlisted",
            category="20",
        ),
        resume_index=0,
        request=None,
    )
    api._retry_worker = lambda _state: None
    observed = []
    real_start = threading.Thread.start

    def start(thread):
        observed.append(api._busy())
        real_start(thread)

    monkeypatch.setattr(api_mod.threading.Thread, "start", start)
    api.retry()
    monkeypatch.undo()
    _join_upload(api)

    assert observed == [True]


class _StartFailureThread:
    def __init__(self, *, target, args, daemon):
        self.target = target
        self.args = args
        self.daemon = daemon

    def start(self):
        raise RuntimeError("cannot start worker")


def test_upload_start_failure_clears_thread_and_claim(tmp_path, monkeypatch):
    api, _window = _upload_api(tmp_path)
    monkeypatch.setattr(api_mod.threading, "Thread", _StartFailureThread)

    with pytest.raises(RuntimeError, match="cannot start worker"):
        api.start_upload("Fight", "", False, ["r1"])

    assert api._upload_thread is None
    assert not api._busy()


def test_retry_start_failure_clears_thread_and_claim(tmp_path, monkeypatch):
    api, _window = _upload_api(tmp_path)
    api._retry_state = api_mod.RetryState(
        job=api_mod.UploadJob(
            items=[],
            ids=[],
            title="Fight",
            description="",
            stitch=False,
            privacy="unlisted",
            category="20",
        ),
        resume_index=0,
        request=None,
    )
    monkeypatch.setattr(api_mod.threading, "Thread", _StartFailureThread)

    with pytest.raises(RuntimeError, match="cannot start worker"):
        api.retry()

    assert api._upload_thread is None
    assert not api._busy()


# ---- update-check runtime -------------------------------------------------


def _release_info(version: str) -> updates_mod.ReleaseInfo:
    tagged = f"v{version}"
    return updates_mod.ReleaseInfo(
        version=updates_mod.parse_version(tagged, tagged=True),
        tag=tagged,
        asset_name=f"FlyGD-Wingman-Setup-{version}.exe",
        url=(
            "https://github.com/elboaf/FlyGD-Wingman/releases/download/"
            f"{tagged}/FlyGD-Wingman-Setup-{version}.exe"
        ),
        size=123,
        sha256="ab" * 32,
        content_type="application/octet-stream",
    )


class FakeUpdates:
    def __init__(
        self,
        *,
        release=None,
        failure=None,
        block=False,
        staged=None,
        download_failure=None,
        verify_failure=None,
        launch_failure=None,
        marker_failure=None,
        close_failure=None,
        block_download=False,
        block_launch=False,
        process_handle=42,
    ):
        self._release = release
        self._failure = failure
        self._staged = Path(staged) if staged is not None else None
        self._download_failure = download_failure
        self._verify_failure = verify_failure
        self._launch_failure = launch_failure
        self._marker_failure = marker_failure
        self._close_failure = close_failure
        self._process_handle = process_handle
        self.check_calls = 0
        self.download_calls = 0
        self.verify_calls = 0
        self.launch_calls = 0
        self.cleanup_calls = []
        self.events = []
        self.progress_callback = None
        self.download_entered = threading.Event()
        self.launch_entered = threading.Event()
        self._gate = threading.Event()
        self._download_gate = threading.Event()
        self._launch_gate = threading.Event()
        if not block:
            self._gate.set()
        if not block_download:
            self._download_gate.set()
        if not block_launch:
            self._launch_gate.set()

    def latest_release(self, current_version=updates_mod.__version__):
        del current_version
        self.check_calls += 1
        assert self._gate.wait(5), "update check never released"
        if self._failure == "network":
            raise updates_mod.UpdateFailure("check", "network", "offline")
        if self._failure == "metadata":
            raise updates_mod.UpdateFailure("check", "metadata", "bad payload")
        if isinstance(self._failure, BaseException):
            raise self._failure
        return self._release

    def release(self):
        self._gate.set()

    def download_release(self, release, staging_root, *, on_progress):
        del release
        self.download_calls += 1
        self.progress_callback = on_progress
        self.events.append("download")
        self.download_entered.set()
        assert self._download_gate.wait(5), "update download never released"
        if self._download_failure is not None:
            raise self._download_failure
        path = self._staged or Path(staging_root) / "update-fake.ready.exe"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(b"verified")
        self._staged = path
        return path

    def progress(self, done, total):
        assert self.progress_callback is not None
        self.progress_callback(done, total)

    def release_download(self):
        self._download_gate.set()

    def verify_after_attachment(self, release, path):
        del release, path
        self.verify_calls += 1
        self.events.append("verify")
        if self._verify_failure is not None:
            raise self._verify_failure

    def launch_verified(self, release, path, *, before_launch):
        del release, path
        self.launch_calls += 1
        self.events.append("launch_verified")
        self.launch_entered.set()
        assert self._launch_gate.wait(5), "update launch never released"
        before_launch()
        self.events.append("shell")
        if self._launch_failure is not None:
            raise self._launch_failure
        return self._process_handle

    def release_launch(self):
        self._launch_gate.set()

    def write_handoff_marker(self, path, release):
        del release
        self.events.append("marker")
        if self._marker_failure is not None:
            raise self._marker_failure
        marker = path.with_name(path.name + ".handoff.json")
        marker.write_text("handed-off", encoding="utf-8")
        return marker

    def remove_handoff_marker(self, marker):
        self.events.append("remove-marker")
        marker.unlink(missing_ok=True)

    def close_process_handle(self, handle):
        assert handle == self._process_handle
        self.events.append("close-handle")
        if self._close_failure is not None:
            raise self._close_failure

    def cleanup_staging(self, staging_root):
        self.cleanup_calls.append(Path(staging_root))


class _BrokenUpdateWindow:
    def evaluate_js(self, _script):
        raise RuntimeError("window is gone")


class _UpdateStartFailureThread:
    def __init__(self, *, target, args, daemon, name=None):
        self.target = target
        self.args = args
        self.daemon = daemon
        self.name = name

    def start(self):
        raise RuntimeError("cannot start update worker")


def _broken_update_spawn(*, target, args=(), daemon=False, name=None):
    del target, args, daemon, name
    raise RuntimeError("cannot construct update worker")


def _update_api(
    tmp_path,
    service,
    *,
    update_spawn=threading.Thread,
    is_frozen=lambda: False,
    window=None,
    rows=None,
):
    cfg = settings_mod._normalize(
        {
            "privacy": "unlisted",
            "category": "20",
            "notify_mode": "toast",
            "recording_dir": str(tmp_path),
            "discord_webhook": "",
            "gamelogs_dir": None,
            "channel_id": "",
            "channel_title": "",
        }
    )
    state = api_mod.AppState(
        recording_dir=Path(tmp_path),
        settings=cfg,
        ffmpeg_bin="/usr/bin/ffmpeg",
        ffprobe_bin=None,
    )
    api = api_mod.Api(
        state,
        rows=rows if rows is not None else fakes.FakeRows(),
        update_service=service,
        update_spawn=update_spawn,
        is_frozen=is_frozen,
    )
    api._window = window if window is not None else fakes.FakeWindow()
    return api, api._window


def _join_update(api, worker=None):
    if worker is None:
        with api._update_lock:
            worker = api._update.worker
    if worker is not None:
        worker.join(timeout=5)
        assert not worker.is_alive()


def _available_api(tmp_path, service, *, frozen=True, update_spawn=threading.Thread):
    rows = fakes.FakeRows({"r1": fakes.info(tmp_path / "r1.mkv")})
    api, window = _update_api(
        tmp_path,
        service,
        update_spawn=update_spawn,
        is_frozen=lambda: frozen,
        rows=rows,
    )
    with api._update_lock:
        api._update.state = "available"
        api._update.release = service._release or _release_info("4.9.0")
    api._alert = fakes.Alerts()
    return api, window


def _ready_api(tmp_path, service, *, frozen=True, update_spawn=threading.Thread):
    path = service._staged or tmp_path / "update-fake.ready.exe"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"verified")
    service._staged = path
    api, window = _available_api(
        tmp_path, service, frozen=frozen, update_spawn=update_spawn
    )
    with api._update_lock:
        api._update.state = "ready"
        api._update.staged = path
        api._update.downloaded_bytes = path.stat().st_size
        api._update.total_bytes = path.stat().st_size
    return api, window


def test_automatic_check_is_single_flight_and_caches_available_release(tmp_path):
    service = FakeUpdates(release=_release_info("4.9.0"), block=True)
    api, _window = _update_api(tmp_path, service)

    api._start_update_check(automatic=True)
    api._start_update_check(automatic=True)

    assert service.check_calls == 1
    service.release()
    _join_update(api)
    assert api.update_status()["state"] == "available"
    assert api.update_status()["available_version"] == "4.9.0"
    assert api.update_status()["update_available"] is True


def test_automatic_failure_is_quiet_but_manual_failure_has_copy(tmp_path):
    api, _window = _update_api(tmp_path, FakeUpdates(failure="network"))

    api._start_update_check(automatic=True)
    _join_update(api)
    assert api.update_status()["state"] == "unavailable"
    assert api.update_status()["error"] == ""

    api.check_for_updates()
    _join_update(api)
    assert "Could not check for updates" in api.update_status()["error"]


def test_manual_check_reports_current_when_the_latest_release_is_not_newer(tmp_path):
    api, _window = _update_api(tmp_path, FakeUpdates(release=None))

    status = api.check_for_updates()

    assert status["state"] == "checking"
    _join_update(api)
    current = api.update_status()
    assert current["state"] == "current"
    assert current["available_version"] == ""
    assert current["update_available"] is False
    assert current["error"] == ""


def test_malformed_release_metadata_uses_verification_copy(tmp_path):
    api, _window = _update_api(tmp_path, FakeUpdates(failure="metadata"))

    api.check_for_updates()
    _join_update(api)

    status = api.update_status()
    assert status["state"] == "check_failed"
    assert "Could not check for updates" in status["error"]
    assert "verified" in status["error"]


def test_manual_click_during_an_automatic_check_reuses_the_worker_and_makes_failure_specific(
    tmp_path,
):
    service = FakeUpdates(failure="network", block=True)
    api, _window = _update_api(tmp_path, service)

    api._start_update_check(automatic=True)
    api.check_for_updates()

    assert service.check_calls == 1
    service.release()
    _join_update(api)
    assert api.update_status()["state"] == "check_failed"
    assert "Could not check for updates" in api.update_status()["error"]


def test_update_status_repairs_a_missed_push_with_the_complete_snapshot(tmp_path):
    service = FakeUpdates(release=_release_info("4.9.0"))
    api, _window = _update_api(tmp_path, service, window=_BrokenUpdateWindow())

    api.check_for_updates()
    _join_update(api)

    assert api.update_status() == {
        "state": "available",
        "installed_version": updates_mod.__version__,
        "available_version": "4.9.0",
        "update_available": True,
        "downloaded_bytes": 0,
        "total_bytes": 0,
        "can_check": True,
        "can_download": True,
        "can_install": False,
        "error": "",
    }


@pytest.mark.parametrize(
    ("state", "expected_download", "expected_install"),
    [
        ("available", True, False),
        ("download_failed", True, False),
        ("ready", False, True),
    ],
)
def test_cached_newer_release_keeps_update_available_through_later_states(
    tmp_path, state, expected_download, expected_install
):
    api, _window = _update_api(
        tmp_path,
        FakeUpdates(),
        is_frozen=lambda: True,
    )

    with api._update_lock:
        api._update.state = state
        api._update.release = _release_info("4.9.0")
        api._update.total_bytes = 123
        api._update.downloaded_bytes = 77

    status = api.update_status()
    assert status["update_available"] is True
    assert status["available_version"] == "4.9.0"
    assert status["can_download"] is expected_download
    assert status["can_install"] is expected_install


@pytest.mark.parametrize(
    "update_spawn",
    [_broken_update_spawn, _UpdateStartFailureThread],
)
def test_update_check_worker_construction_and_start_failures_roll_back_state(
    tmp_path, update_spawn
):
    api, _window = _update_api(tmp_path, FakeUpdates(), update_spawn=update_spawn)

    status = api.check_for_updates()

    assert status["state"] == "idle"
    assert status["can_check"] is True
    assert status["error"] == "Could not start checking for updates. Try again."


def test_update_status_returns_a_fresh_dict(tmp_path):
    api, _window = _update_api(tmp_path, FakeUpdates())

    first = api.update_status()
    first["state"] = "broken"

    assert api.update_status()["state"] == "idle"


def test_ready_state_cannot_start_another_check(tmp_path):
    service = FakeUpdates(release=_release_info("4.9.0"))
    api, _window = _update_api(tmp_path, service, is_frozen=lambda: True)
    with api._update_lock:
        api._update.state = "ready"
        api._update.release = _release_info("4.9.0")

    status = api.check_for_updates()

    assert service.check_calls == 0
    assert status["state"] == "ready"
    assert status["can_check"] is False
    assert status["can_install"] is True


def test_update_check_releases_the_lock_before_spawn_and_push(tmp_path):
    events = []
    api, _window = _update_api(tmp_path, FakeUpdates(release=_release_info("4.9.0")))
    real_push = api._push

    def lock_is_free(where):
        assert api._update_lock.acquire(blocking=False), where
        api._update_lock.release()
        events.append(where)

    class CheckingSpawn:
        def __init__(self, *, target, args, daemon):
            lock_is_free("construct")
            self._thread = threading.Thread(target=target, args=args, daemon=daemon)

        def start(self):
            lock_is_free("start")
            self._thread.start()

        def join(self, timeout=None):
            self._thread.join(timeout=timeout)

        def is_alive(self):
            return self._thread.is_alive()

    api._update_spawn = CheckingSpawn

    def spy(handler, payload):
        lock_is_free(handler)
        real_push(handler, payload)

    api._push = spy

    api.check_for_updates()
    _join_update(api)

    assert events == ["construct", "onUpdateStatus", "start", "onUpdateStatus"]


def test_get_settings_does_not_call_the_update_service(tmp_path):
    service = FakeUpdates(release=_release_info("4.9.0"))
    api, _window = _update_api(tmp_path, service)

    api.get_settings()

    assert service.check_calls == 0


def test_update_runtime_attributes_are_private(tmp_path):
    api, _window = _update_api(tmp_path, FakeUpdates())

    assert callable(api.update_status)
    assert callable(api.check_for_updates)
    assert not hasattr(api, "update_service")
    assert not hasattr(api, "update_spawn")
    assert not hasattr(api, "is_frozen")
    assert not hasattr(api, "update_lock")
    assert not hasattr(api, "update")


# ---- download and install orchestration -----------------------------------


def test_download_reports_progress_then_ready(tmp_path):
    service = FakeUpdates(
        release=_release_info("4.9.0"),
        staged=tmp_path / "update.ready.exe",
        block_download=True,
    )
    api, _window = _available_api(tmp_path, service)
    sent = fakes.record_pushes(api)

    status = api.download_update()
    assert status["state"] == "downloading"
    assert service.download_entered.wait(1)
    with api._update_lock:
        worker = api._update.worker
    assert worker.name == "wingman-update-download"

    service.progress(10, 20)
    assert api.update_status()["downloaded_bytes"] == 10
    service.release_download()
    _join_update(api, worker)

    states = [payload["state"] for payload in fakes.payloads(sent, "onUpdateStatus")]
    assert "downloading" in states
    assert states[-1] == "ready"
    assert api.update_status()["can_install"] is True
    assert service.verify_calls == 1
    assert service.events == ["download", "verify"]
    assert service.cleanup_calls == [], "partial cleanup belongs to download_release"


def test_only_one_download_can_run_at_a_time(tmp_path):
    service = FakeUpdates(release=_release_info("4.9.0"), block_download=True)
    api, _window = _available_api(tmp_path, service)

    api.download_update()
    assert service.download_entered.wait(1)
    second = api.download_update()

    assert second["state"] == "downloading"
    assert service.download_calls == 1
    service.release_download()
    _join_update(api)


@pytest.mark.parametrize(
    ("failure", "from_verify", "expected"),
    [
        (
            updates_mod.UpdateFailure("download", "network", "connection reset"),
            False,
            "Could not download the update. Check your internet connection and try again.",
        ),
        (
            updates_mod.UpdateFailure("download", "checksum", "wrong digest"),
            False,
            "The download did not match the release checksum. It was not installed.",
        ),
        (
            updates_mod.UpdateFailure("download", "filesystem", "disk full"),
            False,
            "Could not save the update. Check available disk space and try again.",
        ),
        (
            updates_mod.UpdateFailure("verify", "attachment", "policy failed"),
            True,
            (
                "Windows could not mark the installer as an internet download. "
                "It was not installed."
            ),
        ),
    ],
)
def test_download_failures_keep_exact_stage_specific_copy(
    tmp_path, failure, from_verify, expected
):
    service = FakeUpdates(
        release=_release_info("4.9.0"),
        download_failure=None if from_verify else failure,
        verify_failure=failure if from_verify else None,
    )
    api, _window = _available_api(tmp_path, service)

    api.download_update()
    _join_update(api)

    status = api.update_status()
    assert status["state"] == "download_failed"
    assert status["can_download"] is True
    assert status["error"] == expected
    assert status["can_install"] is False


@pytest.mark.parametrize(
    "update_spawn", [_broken_update_spawn, _UpdateStartFailureThread]
)
def test_download_worker_construction_and_start_failures_are_retryable(
    tmp_path, update_spawn
):
    service = FakeUpdates(release=_release_info("4.9.0"))
    api, _window = _available_api(tmp_path, service, update_spawn=update_spawn)

    status = api.download_update()

    assert status["state"] == "download_failed"
    assert status["can_download"] is True
    assert status["error"] == "Could not start downloading the update. Try again."
    with api._update_lock:
        assert api._update.worker is None
    assert service.download_calls == 0


def test_source_checkout_can_check_and_download_but_cannot_install(tmp_path):
    service = FakeUpdates(release=_release_info("4.9.0"))
    api, _window = _available_api(tmp_path, service, frozen=False)

    assert api.update_status()["can_download"] is True
    api.download_update()
    _join_update(api)

    assert api.update_status()["state"] == "ready"
    assert api.update_status()["can_install"] is False
    assert api.install_update()["state"] == "ready"
    assert service.launch_calls == 0
    assert api._work_gate.handoff_phase() == ""


def test_install_claim_excludes_upload_before_revalidation(tmp_path):
    service = FakeUpdates(release=_release_info("4.9.0"), block_launch=True)
    api, _window = _ready_api(tmp_path, service)

    api.install_update()
    assert service.launch_entered.wait(1)
    assert api._work_gate.handoff_phase() == "revalidating"
    api.start_upload("Fight", "", False, ["r1"])

    assert api._alert.raised[-1] == (
        "info",
        "Update",
        "Update installation is being prepared.",
    )
    assert api._upload_thread is None
    service.release_launch()
    _join_update(api)


def test_update_runtime_prevents_a_second_installer(tmp_path):
    service = FakeUpdates(release=_release_info("4.9.0"), block_launch=True)
    api, _window = _ready_api(tmp_path, service)

    api.install_update()
    assert service.launch_entered.wait(1)
    second = api.install_update()

    assert second["state"] == "revalidating"
    assert service.launch_calls == 1
    service.release_launch()
    _join_update(api)


def test_install_claim_excludes_retry_before_revalidation(tmp_path):
    service = FakeUpdates(release=_release_info("4.9.0"), block_launch=True)
    api, _window = _ready_api(tmp_path, service)
    _enable_retry(api)
    sent = fakes.record_pushes(api)

    api.install_update()
    assert service.launch_entered.wait(1)
    api.retry()

    assert fakes.payloads(sent, "onRetryAvailable")[-1] == {"available": False}
    assert api._alert.raised[-1][2] == "Update installation is being prepared."
    assert api._upload_thread is None
    service.release_launch()
    _join_update(api)


def test_retry_and_install_race_has_exactly_one_owner(tmp_path):
    service = FakeUpdates(release=_release_info("4.9.0"), block_launch=True)
    api, _window = _ready_api(tmp_path, service)
    _enable_retry(api)
    release_retry = threading.Event()
    api._retry_worker = lambda _state: release_retry.wait(5)
    bridge_calls = threading.Barrier(3)

    def retry_call():
        bridge_calls.wait(timeout=2)
        api.retry()

    def install_call():
        bridge_calls.wait(timeout=2)
        api.install_update()

    retry_bridge = threading.Thread(target=retry_call)
    install_bridge = threading.Thread(target=install_call)
    retry_bridge.start()
    install_bridge.start()
    bridge_calls.wait(timeout=2)
    retry_bridge.join(timeout=2)
    install_bridge.join(timeout=2)
    assert not retry_bridge.is_alive()
    assert not install_bridge.is_alive()

    handoff = bool(api._work_gate.handoff_phase())
    uploading = api._busy()
    try:
        assert uploading is not handoff
    finally:
        release_retry.set()
        service.release_launch()
        _join_upload(api)
        _join_update(api)


def test_active_upload_refuses_install_without_reserving_handoff(tmp_path):
    service = FakeUpdates(release=_release_info("4.9.0"))
    api, _window = _ready_api(tmp_path, service)
    assert api._work_gate.claim_upload()

    try:
        status = api.install_update()
    finally:
        api._work_gate.release_upload()

    assert status["state"] == "ready"
    assert status["error"] == "Finish the active upload before installing the update."
    assert service.launch_calls == 0
    assert api._work_gate.handoff_phase() == ""


@pytest.mark.parametrize("mutation", ["delete", "replace", "truncate"])
def test_final_file_mutation_returns_install_to_download_failed(tmp_path, mutation):
    class MutationCheckingUpdates(FakeUpdates):
        def launch_verified(self, release, path, *, before_launch):
            del release, before_launch
            self.launch_calls += 1
            if not path.exists() or path.read_bytes() != b"verified":
                raise updates_mod.UpdateFailure(
                    "verify", "checksum", "installer changed"
                )
            raise AssertionError("mutated installer unexpectedly verified")

    service = MutationCheckingUpdates(release=_release_info("4.9.0"))
    api, _window = _ready_api(tmp_path, service)
    path = service._staged
    if mutation == "delete":
        path.unlink()
    elif mutation == "replace":
        replacement = tmp_path / "replacement.exe"
        replacement.write_bytes(b"replacement")
        replacement.replace(path)
    else:
        path.write_bytes(b"")

    api.install_update()
    _join_update(api)

    status = api.update_status()
    assert status["state"] == "download_failed"
    assert status["error"] == (
        "The downloaded installer changed or is no longer available. Download it again."
    )
    assert api._work_gate.handoff_phase() == ""


def test_marker_failure_prevents_shell_launch_and_requires_a_new_download(tmp_path):
    service = FakeUpdates(
        release=_release_info("4.9.0"),
        marker_failure=updates_mod.UpdateFailure(
            "cleanup", "filesystem", "marker write failed"
        ),
    )
    api, _window = _ready_api(tmp_path, service)

    api.install_update()
    _join_update(api)

    assert service.events == ["launch_verified", "marker"]
    assert api.update_status()["state"] == "download_failed"
    assert api._work_gate.handoff_phase() == ""


@pytest.mark.parametrize("detail", ["shell failed", "null process handle"])
def test_shell_failure_removes_marker_and_recovers_ready_state(tmp_path, detail):
    service = FakeUpdates(
        release=_release_info("4.9.0"),
        launch_failure=updates_mod.UpdateFailure("launch", "shell", detail),
    )
    api, _window = _ready_api(tmp_path, service)
    original_path = service._staged

    api.install_update()
    _join_update(api)

    assert service.events == [
        "launch_verified",
        "marker",
        "shell",
        "remove-marker",
    ]
    assert original_path.exists(), "a launch failure must not rename the installer"
    assert not original_path.with_name(original_path.name + ".handoff.json").exists()
    status = api.update_status()
    assert status["state"] == "ready"
    assert status["error"] == "Could not open the installer. Try again."
    assert api._work_gate.handoff_phase() == ""


def test_null_process_result_is_treated_as_shell_failure(tmp_path):
    service = FakeUpdates(
        release=_release_info("4.9.0"),
        process_handle=None,
    )
    api, _window = _ready_api(tmp_path, service)

    api.install_update()
    _join_update(api)

    assert service.events == [
        "launch_verified",
        "marker",
        "shell",
        "remove-marker",
    ]
    assert api.update_status()["state"] == "ready"
    assert api.update_status()["error"] == "Could not open the installer. Try again."
    assert api._work_gate.handoff_phase() == ""


def test_successful_launch_classifies_closes_handle_then_requests_shutdown(tmp_path):
    service = FakeUpdates(release=_release_info("4.9.0"), process_handle=73)
    api, _window = _ready_api(tmp_path, service)
    observations = []
    original_close = service.close_process_handle

    def close_process_handle(handle):
        marker = service._staged.with_name(service._staged.name + ".handoff.json")
        observations.append(
            (
                "close",
                marker.exists(),
                api.update_status()["state"],
                api._work_gate.handoff_phase(),
            )
        )
        original_close(handle)

    def request_shutdown():
        observations.append(
            ("shutdown", api.update_status()["state"], api._work_gate.handoff_phase())
        )

    service.close_process_handle = close_process_handle
    api._request_shutdown = request_shutdown

    status = api.install_update()
    assert status["state"] == "handing_off"
    with api._update_lock:
        worker = api._update.worker
    assert worker.name == "wingman-update-install"
    _join_update(api, worker)

    assert service.events == [
        "launch_verified",
        "marker",
        "shell",
        "close-handle",
    ]
    assert observations == [
        ("close", True, "launching", "launching"),
        ("shutdown", "launching", "launching"),
    ]
    assert not api._work_gate.claim_upload()


def test_process_handle_close_failure_does_not_abandon_a_launched_installer(tmp_path):
    service = FakeUpdates(
        release=_release_info("4.9.0"),
        close_failure=updates_mod.UpdateFailure(
            "launch", "close-handle", "CloseHandle failed"
        ),
    )
    api, _window = _ready_api(tmp_path, service)
    shutdown = []
    api._request_shutdown = lambda: shutdown.append(True)

    api.install_update()
    _join_update(api)

    assert "close-handle" in service.events
    assert shutdown == [True]
    assert api.update_status()["state"] == "launching"


@pytest.mark.parametrize(
    "update_spawn", [_broken_update_spawn, _UpdateStartFailureThread]
)
def test_install_worker_construction_and_start_failures_release_handoff(
    tmp_path, update_spawn
):
    service = FakeUpdates(release=_release_info("4.9.0"))
    api, _window = _ready_api(tmp_path, service, update_spawn=update_spawn)

    status = api.install_update()

    assert status["state"] == "ready"
    assert status["error"] == "Could not start installing the update. Try again."
    assert api._work_gate.handoff_phase() == ""
    assert service.launch_calls == 0


def test_updater_shutdown_is_idempotent_and_removes_an_unhanded_ready_file(tmp_path):
    service = FakeUpdates(release=_release_info("4.9.0"))
    api, _window = _ready_api(tmp_path, service)
    path = service._staged

    api.shutdown_updates()
    api.shutdown_updates()

    assert api.update_status()["state"] == "closed"
    assert not path.exists()
    assert len(service.cleanup_calls) == 1


def test_updater_shutdown_preserves_a_durably_handed_off_installer(tmp_path):
    service = FakeUpdates(release=_release_info("4.9.0"))
    api, _window = _ready_api(tmp_path, service)
    marker = service.write_handoff_marker(service._staged, service._release)
    with api._update_lock:
        api._update.state = "launching"
    assert marker.exists()

    api.shutdown_updates()

    assert service._staged.exists()
    assert marker.exists()
    assert api.update_status()["state"] == "closed"


def test_install_worker_cannot_mutate_handoff_or_push_after_shutdown_begins(
    tmp_path,
):
    service = FakeUpdates(
        release=_release_info("4.9.0"),
        launch_failure=updates_mod.UpdateFailure(
            "verify", "checksum", "installer changed"
        ),
        block_launch=True,
    )
    api, _window = _ready_api(tmp_path, service)
    sent = fakes.record_pushes(api)

    api.install_update()
    assert service.launch_entered.wait(1)
    with api._update_lock:
        worker = api._update.worker
    handoff_at_shutdown = api._work_gate.handoff_phase()
    api.shutdown_updates()
    pushed_at_shutdown = len(sent)
    service.release_launch()
    _join_update(api, worker)

    assert api.update_status()["state"] == "closed"
    assert api._work_gate.handoff_phase() == handoff_at_shutdown
    assert len(sent) == pushed_at_shutdown


def test_download_worker_cannot_verify_mutate_or_push_after_shutdown_begins(tmp_path):
    service = FakeUpdates(
        release=_release_info("4.9.0"),
        staged=tmp_path / "late.ready.exe",
        block_download=True,
    )
    api, _window = _available_api(tmp_path, service)
    sent = fakes.record_pushes(api)

    api.download_update()
    assert service.download_entered.wait(1)
    with api._update_lock:
        worker = api._update.worker
    api.shutdown_updates()
    pushed_at_shutdown = len(sent)
    service.release_download()
    _join_update(api, worker)

    assert api.update_status()["state"] == "closed"
    assert service.verify_calls == 0
    assert len(sent) == pushed_at_shutdown
    assert not service._staged.exists()
