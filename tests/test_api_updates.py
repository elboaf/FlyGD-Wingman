"""Atomic work claims shared by uploads, updater handoff, and Quit."""

import threading

import pytest

from tests import fakes
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
        results["handoff"] = api._work_gate.claim_handoff("handing_off")

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
        results["handoff"] = api._work_gate.claim_handoff("handing_off")

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
