"""Event-controlled regressions for the twelve Phase 1 review findings."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from threading import Condition, Event
from types import SimpleNamespace

import pytest

from tests.test_api import FakeWindow, make_api
from tests.test_preview_cropcontroller import DEFINITION, client
from tests.test_preview_host import crop_pump as crop_pump
from tests.test_preview_runtime import RecordingHost
from tests.test_preview_store import FakeTimer
from wingman.preview import geometry, layout
from wingman.preview.runtime import PreviewRuntime
from wingman.preview.store import LayoutStore
from wingman.telemetry.model import RosterSnapshot


@pytest.fixture
def runtime_pump(crop_pump):
    opened = []

    def make(*, start=True, **kwargs):
        r = crop_pump(**kwargs)
        runtime = PreviewRuntime(r.host)
        changed = Condition()
        states = []

        def publish(state):
            with changed:
                states.append(state)
                changed.notify_all()

        def wait(predicate):
            with changed:
                assert changed.wait_for(lambda: predicate(runtime.snapshot()), 5), (
                    states
                )

        runtime.set_state_callback(publish)
        r.runtime, r.states, r.wait_state = runtime, states, wait
        opened.append(r)
        if start:
            runtime.set_companions(True, 1)
            wait(lambda state: state.companions == "active")
        return r

    yield make
    results = [r.runtime.shutdown(5) for r in opened]
    assert all(results), "Preview runtime cleanup did not finish"


@contextmanager
def parked(r):
    entered, release = Event(), Event()

    def hold():
        entered.set()
        assert release.wait(5)

    with ThreadPoolExecutor(max_workers=1) as pool:
        call = pool.submit(r.call, hold)
        assert entered.wait(5)
        try:
            yield
        finally:
            release.set()
            call.result(5)


def eve_on(r, revision=1):
    r.runtime.set_eve(True, revision)
    r.wait_state(lambda state: state.eve == "active")


def test_review_01_canceled_unstarted_admission_does_not_wedge_eve(
    runtime_pump, tmp_path, monkeypatch
):
    r = runtime_pump(start=False)
    entered, release = Event(), Event()
    run = r.runtime._run

    def held_executor():
        entered.set()
        assert release.wait(5)
        run()

    monkeypatch.setattr(r.runtime, "_run", held_executor)
    api = make_api(tmp_path, preview_host=r.host, preview_runtime=r.runtime)
    try:
        assert api.set_preview_enabled(True)
        assert entered.wait(5)
        assert api.set_preview_enabled(False)
        assert not r.host.is_stopping
        assert api.set_preview_enabled(True)
        release.set()
        assert r.host._ready.wait(5) and r.host.runtime_enabled
    finally:
        release.set()
        api.shutdown_previews()


def test_review_01_canceled_unstarted_waits_for_admitted_offline_submission(
    runtime_pump, monkeypatch
):
    r = runtime_pump(start=False)
    executor_release, submission_entered, submission_release = Event(), Event(), Event()
    run, submit = r.runtime._run, r.store.set_enabled

    def held_executor():
        assert executor_release.wait(5)
        run()

    def held_submission(*args):
        submission_entered.set()
        assert submission_release.wait(5)
        return submit(*args)

    monkeypatch.setattr(r.runtime, "_run", held_executor)
    monkeypatch.setattr(r.store, "set_enabled", held_submission)
    with ThreadPoolExecutor(max_workers=1) as pool:
        operation = pool.submit(r.host.request_crop, "enabled", "Alice", False)
        assert submission_entered.wait(5)
        try:
            r.runtime.set_eve(True, 1)
            r.runtime.set_eve(False, 2)
            assert r.host.is_stopping
            submission_release.set()
            receipt = operation.result(5)
            r.store.drain().result(5)
            # No pump ever started; the accepted storage barrier must settle
            # the canceled family without requiring a later start/stop caller.
            assert not r.host.is_stopping
            assert r.host.crop_state()["operations"][receipt["operation_id"]][
                "persisted"
            ]
        finally:
            submission_release.set()
            executor_release.set()


def test_review_02_canceled_prepared_crop_epoch_is_not_reused(runtime_pump):
    entered, release = Event(), Event()

    def before_window():
        entered.set()
        assert release.wait(5)

    r = runtime_pump(
        start=False,
        before_window=before_window,
        initial={"Alice": replace(DEFINITION, enabled=False)},
    )
    r.runtime.set_eve(True, 1)
    assert entered.wait(5)
    old_epoch = r.host._crop_epoch
    try:
        r.runtime.set_companions(True, 1)
        r.runtime.set_eve(False, 2)
    finally:
        release.set()
    r.wait_state(lambda state: state.companions == "active" and state.eve == "stopped")
    eve_on(r, 3)
    r.host.apply_roster(RosterSnapshot(1, (client(),)))
    receipt = r.host.request_crop("enabled", "Alice", True)
    r.call(lambda: None)
    r.store.drain().result(5)
    r.call(lambda: None)
    assert r.host._crop_epoch > old_epoch
    assert r.host.crop_state()["operations"][receipt["operation_id"]]["persisted"]


def test_review_03_companion_off_on_keeps_cleanup_edge_and_lease(runtime_pump):
    r = runtime_pump()
    lease = r.runtime.acquire_selection(12)
    old = r.runtime.snapshot().companion_epoch
    acknowledgments = []
    callback = r.host._lifecycle_callback
    r.host._lifecycle_callback = lambda ack: (
        acknowledgments.append(ack),
        callback(ack),
    )
    with parked(r):
        r.runtime.set_companions(False, 2)
        r.runtime.set_companions(True, 3)
    r.wait_state(
        lambda state: state.companions == "active" and state.companion_epoch > old
    )
    assert r.runtime.snapshot().selection_pending
    assert any(
        ack.outcome == "companions-stopped" and ack.companion_epoch == old + 1
        for ack in acknowledgments
    )
    r.runtime.release_selection(lease)


@pytest.mark.parametrize("boundary", ["older-family-wake", "early-close"])
def test_review_04_05_accepted_primary_fifo_precedes_cleanup(runtime_pump, boundary):
    r = runtime_pump()
    eve_on(r)
    h = r.host
    store = LayoutStore(r.transaction.update, timer=FakeTimer)
    h._clear_layouts = store.clear
    h._on_layout_changed = lambda name, rect, locked: store.record(
        name, layout.Entry(rect, locked)
    )
    r.store._flush_primary = store.flush
    moved = []
    primary = SimpleNamespace(
        rect=geometry.Rect(20, 30, 320, 210),
        locked=False,
        _mode=None,
        move=lambda rect: moved.append(rect),
        set_hidden=lambda hidden: None,
        close=lambda: None,
    )
    r.call(lambda: h._windows.update(Alice=primary))
    with parked(r):
        h.set_families(h._families)  # Old coalesced wake is ahead of accepted settings.
        assert h.reset_layouts()
        assert h.resize_preview("Alice", (500, 300))
        if boundary == "early-close":
            r.runtime.close_admission()
        else:
            r.runtime.set_eve(False, 2)
    if boundary == "early-close":
        r.call(lambda: None)  # Delivery occurs BEFORE the later final stop.
        assert r.runtime.shutdown(5)
    else:
        r.wait_state(lambda state: state.eve == "stopped")
    saved = r.transaction.document["preview"]["layouts"]
    assert saved["Alice"]["w"] == 500 and saved["Alice"]["h"] == 300
    assert not moved  # Revoked native movement is not needed to persist the receipt.


def test_review_06_failed_hwnd_creation_retires_storage_and_can_retry(
    runtime_pump, monkeypatch
):
    r = runtime_pump(start=False)
    create = r.host._create_host_window
    attempts = []

    def fail_once(libs):
        attempts.append(True)
        return None if len(attempts) == 1 else create(libs)

    monkeypatch.setattr(r.host, "_create_host_window", fail_once)
    r.runtime.set_eve(True, 1)
    r.wait_state(lambda state: state.pump == "failed" and not r.host.is_stopping)
    eve_on(r, 1)
    assert len(attempts) == 2
    assert r.runtime.shutdown(5)
    with pytest.raises(RuntimeError, match="closed"):
        r.store.begin("Alice", epoch=0, session=None)


@pytest.mark.parametrize("failed_resource", ["hotkey", "hook"])
def test_review_07_failed_unregister_retains_owner_until_existing_pump_boundary(
    runtime_pump, monkeypatch, failed_resource
):
    r = runtime_pump()
    eve_on(r)
    h = r.host
    release, attempted = Event(), Event()

    def unregister(*args):
        attempted.set()
        return release.is_set()

    monkeypatch.setattr(
        r.native,
        "UnregisterHotKey",
        unregister if failed_resource == "hotkey" else lambda *args: True,
        raising=False,
    )
    monkeypatch.setattr(
        r.native,
        "UnhookWinEvent",
        unregister if failed_resource == "hook" else lambda *args: True,
        raising=False,
    )
    r.call(
        lambda: (
            h._registered.update({1: ("focus", ("Alice",))}),
            h._registered_text.update({1: "Ctrl+F1"}),
            setattr(h, "_hook", 99),
        )
    )
    old_epoch = h._eve_epoch
    try:
        r.runtime.set_eve(False, 2)
        assert attempted.wait(5)
        r.store.drain().result(5)
        r.call(lambda: None)
        assert h.is_stopping and h._hwnd == 42
        assert 1 in h._registered if failed_resource == "hotkey" else h._hook == 99
        r.runtime.set_eve(True, 3)
        r.call(lambda: None)
        assert not h.runtime_enabled and h._eve_epoch == old_epoch + 1
    finally:
        release.set()
        h._post(0)
    r.wait_state(
        lambda state: state.eve == "active" and state.eve_epoch > old_epoch + 1
    )


def test_review_08_offline_final_storage_completion_wakes_retained_executor(
    runtime_pump, monkeypatch
):
    entered, release = Event(), Event()

    def flush():
        entered.set()
        assert release.wait(10)

    r = runtime_pump(start=False, primary_flush=flush)
    stopped = Event()
    original_stop = r.host.stop

    def short_stop(timeout=5, *, final=False):
        result = original_stop(timeout=0, final=final)
        if not result:
            stopped.set()
        return result

    monkeypatch.setattr(r.host, "stop", short_stop)
    r.host.request_crop("enabled", "Alice", False)
    try:
        assert not r.runtime.shutdown(0)
        assert entered.wait(5) and stopped.wait(5)
        worker = r.runtime._worker
        assert not r.runtime.shutdown(0)
    finally:
        release.set()
    assert r.runtime.shutdown(5)
    assert r.runtime._worker is worker and r.host._thread is None


def test_review_09_raised_start_requires_retirement_before_explicit_retry():
    h = RecordingHost()
    runtime = PreviewRuntime(h)
    attempts = []

    def start():
        h.record("start")
        attempts.append(True)
        if len(attempts) == 1:
            raise OSError("launch refused")
        h.is_running = True

    h.start = start
    h.stop_gate.clear()
    try:
        runtime.set_eve(True, 1)
        h.wait("stop")
        runtime.set_eve(True, 1)
        assert len(attempts) == 1 and runtime.snapshot().pump_epoch == 1
        h.stop_gate.set()
        h.wait("start", 2)
        assert runtime.snapshot().pump_epoch == 2
    finally:
        h.stop_gate.set()
        assert runtime.shutdown(5)


@pytest.mark.parametrize("adapter", ["crops", "hotkeys", "bind"])
@pytest.mark.parametrize("boundary", ["serialization", "mirror"])
def test_review_10_preview_publication_rechecks_actual_delivery(
    tmp_path, monkeypatch, adapter, boundary
):
    from wingman.ui import api as api_mod

    api = make_api(tmp_path)
    api._sigbar_window = FakeWindow()
    entered, release = Event(), Event()
    payload = api_mod._page_payload
    main = api._window.evaluate_js

    def held_payload(value):
        entered.set()
        assert release.wait(5)
        return payload(value)

    def held_main(script):
        main(script)  # This delivery began before close and is allowed.
        entered.set()
        assert release.wait(5)

    if boundary == "serialization":
        monkeypatch.setattr(api_mod, "_page_payload", held_payload)
    else:
        monkeypatch.setattr(api._window, "evaluate_js", held_main)
    push = {
        "crops": lambda: api.push_preview_crops({"revision": 1}),
        "hotkeys": api.push_preview_hotkeys,
        "bind": lambda: api.push_bind_captured("Ctrl+F1"),
    }[adapter]
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(push)
        assert entered.wait(5)
        try:
            api._close_eve_runtime()
        finally:
            release.set()
        pending.result(5)
    assert len(api._window.evaluated) == (boundary == "mirror")
    assert not api._sigbar_window.evaluated


def test_review_11_completed_failure_cleanup_off_on_accepts_next_real_epoch(
    runtime_pump,
):
    r = runtime_pump()

    def fail(*args, **kwargs):
        raise OSError("EVE native creation refused")

    r.host._crop_controller_factory = fail
    r.runtime.set_eve(True, 1)
    r.wait_state(lambda state: state.eve == "failed" and not r.host.is_stopping)
    r.host._crop_controller_factory = None
    r.runtime.set_eve(False, 2)
    eve_on(r, 3)
    assert r.runtime.snapshot().eve_epoch == 3


@pytest.mark.parametrize("inflight", ["off", "unchanged-on"])
def test_review_12_runtime_admission_preserves_off_before_latest_on(
    runtime_pump, monkeypatch, inflight
):
    r = runtime_pump()
    eve_on(r)
    h, runtime = r.host, r.runtime
    original = h.set_families
    entered, release = Event(), Event()
    delivered = []

    def held(demand):
        if not entered.is_set():
            entered.set()
            assert release.wait(5)
        delivered.append(demand)
        return original(demand)

    monkeypatch.setattr(h, "set_families", held)
    old_epoch = h._eve_epoch
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(runtime.set_eve, inflight != "off", 2)
        assert entered.wait(5)
        try:
            if inflight == "unchanged-on":
                runtime.set_eve(False, 3)
            runtime.set_eve(True, 4)
            if inflight == "unchanged-on":
                # Both producers may replace desired state while admission is
                # held. Off edges stay bounded by family, not request count.
                for revision in range(5, 45):
                    runtime.set_companions(revision % 2 == 0, revision)
                    runtime.set_eve(revision % 2 == 0, revision)
                    assert len(runtime._pending_off) <= 2
            assert runtime.snapshot().pump_epoch == 1
        finally:
            release.set()
        first.result(5)
    r.wait_state(lambda state: state.eve == "active" and state.eve_epoch > old_epoch)
    assert any(not demand.eve for demand in delivered)
    assert delivered[-1].eve
    assert [d.revision for d in delivered] == sorted(d.revision for d in delivered)
