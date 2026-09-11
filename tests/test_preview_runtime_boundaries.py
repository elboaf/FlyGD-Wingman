"""Actual admission, OS acquisition and FIFO boundaries A-G from re-review."""

import inspect
import threading
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

import pytest

from tests.test_api import make_api
from tests.test_preview_cropcontroller import client
from tests.test_preview_host import crop_pump as crop_pump
from tests.test_preview_runtime_review import eve_on, parked
from tests.test_preview_runtime_review import runtime_pump as runtime_pump
from tests.test_preview_store import FakeTimer
from wingman.preview import geometry, layout, win32
from wingman.preview import host as host_mod
from wingman.preview.store import LayoutStore


def test_boundary_a_offline_tail_rechecks_cancellation_after_barrier_decision(
    runtime_pump, tmp_path, monkeypatch
):
    r = runtime_pump(start=False)
    entered, release, executor_release = Event(), Event(), Event()
    lock, run = r.host._lock, r.runtime._run

    class TailLock:
        def __enter__(self):
            lock.acquire()

        def __exit__(self, *args):
            frame = inspect.currentframe().f_back
            tail = (
                frame.f_code.co_name == "_drain_offline_crop_commands"
                and frame.f_locals.get("need_barrier") is False
            )
            lock.release()
            if tail and not entered.is_set():
                entered.set()
                assert release.wait(5)

    def held_executor():
        assert executor_release.wait(5)
        run()

    monkeypatch.setattr(r.host, "_lock", TailLock())
    monkeypatch.setattr(r.runtime, "_run", held_executor)
    api = make_api(tmp_path, preview_host=r.host, preview_runtime=r.runtime)
    with ThreadPoolExecutor(max_workers=1) as pool:
        operation = pool.submit(r.host.request_crop, "enabled", "Alice", False)
        assert entered.wait(5)
        try:
            assert api.set_preview_enabled(True)
            assert api.set_preview_enabled(False)
            assert r.host.is_stopping
            release.set()
            receipt = operation.result(5)
            r.store.drain().result(5)
            assert not r.host.is_stopping
            assert r.host.crop_state()["operations"][receipt["operation_id"]][
                "persisted"
            ]
            assert api.set_preview_enabled(True)
            executor_release.set()
            assert r.host._ready.wait(5)
        finally:
            release.set()
            executor_release.set()
            api.shutdown_previews()


def test_boundary_b_acquired_hotkey_remains_owned_after_revocation_and_failed_release(
    runtime_pump, monkeypatch
):
    r = runtime_pump()
    entered, registered_return, can_release = Event(), Event(), Event()
    native_ids = set()

    def register(hwnd, ident, *args):
        entered.set()
        assert registered_return.wait(5)
        native_ids.add(ident)
        return True

    def unregister(hwnd, ident):
        if not can_release.is_set():
            return False
        native_ids.discard(ident)
        return True

    monkeypatch.setattr(r.native, "RegisterHotKey", register, raising=False)
    monkeypatch.setattr(r.native, "UnregisterHotKey", unregister, raising=False)
    r.host.set_hotkeys({"characters": {"Alice": "Ctrl+F1"}})
    r.runtime.set_eve(True, 1)
    assert entered.wait(5)
    try:
        r.runtime.set_eve(False, 2)
        registered_return.set()
        r.call(lambda: None)
        r.store.drain().result(5)
        r.call(lambda: None)
        assert native_ids == {1}
        assert r.host.is_stopping and not r.host.runtime_enabled
        assert r.host._registered_text == {1: "Ctrl+F1"}
    finally:
        registered_return.set()
        can_release.set()
        r.host._post(0)
    r.wait_state(lambda state: state.eve == "stopped" and not r.host.is_stopping)
    assert not native_ids


def test_boundary_c_removed_chord_loses_dispatch_not_cleanup_ownership(
    runtime_pump, monkeypatch
):
    r = runtime_pump()
    can_release = Event()
    monkeypatch.setattr(r.native, "RegisterHotKey", lambda *args: True, raising=False)
    monkeypatch.setattr(
        r.native, "UnregisterHotKey", lambda *args: can_release.is_set(), raising=False
    )
    monkeypatch.setattr(r.native, "GetForegroundWindow", lambda: 0, raising=False)
    activated = []
    monkeypatch.setattr(
        r.host,
        "_activate_client",
        lambda libs, source: activated.append(source.stable_key),
    )
    r.host.set_hotkeys({"characters": {"Alice": "Ctrl+F1", "Bob": "Ctrl+F2"}})
    eve_on(r)
    r.call(
        lambda: r.host._clients.update(
            {name: host_mod._preview_client(client(name)) for name in ("Alice", "Bob")}
        )
    )
    try:
        r.host.set_hotkeys({"characters": {"Bob": "Ctrl+F2"}})
        r.call(lambda: None)
        r.call(lambda: r.host._host_proc(42, win32.WM_HOTKEY, 1, 0))
        r.call(lambda: r.host._host_proc(42, win32.WM_HOTKEY, 2, 0))
        assert activated == ["Bob"]
        assert r.host.hotkey_status() == {"Ctrl+F2": True}
        assert r.host._registered_text == {1: "Ctrl+F1", 2: "Ctrl+F2"}
    finally:
        can_release.set()
        r.host.request_rebind()
        r.call(lambda: None)


def test_boundary_d_resize_payloads_do_not_coalesce_across_reset(runtime_pump):
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
        assert h.resize_preview("Alice", (400, 250))
        assert h.reset_layouts()
        assert h.resize_preview("Alice", (600, 350))
        r.runtime.set_eve(False, 2)
    r.wait_state(lambda state: state.eve == "stopped")
    saved = r.transaction.document["preview"]["layouts"]
    assert saved["Alice"]["w"] == 600 and saved["Alice"]["h"] == 350
    assert not moved


def test_boundary_e_coalesced_unadmitted_on_does_not_reserve_epoch(
    runtime_pump, monkeypatch
):
    r = runtime_pump()
    entered, release = Event(), Event()
    admission = r.host.set_families

    def held(demand):
        if not entered.is_set():
            entered.set()
            assert release.wait(5)
        return admission(demand)

    monkeypatch.setattr(r.host, "set_families", held)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(r.runtime.set_companions, True, 2)
        assert entered.wait(5)
        try:
            r.runtime.set_eve(True, 1)
            r.runtime.set_eve(False, 2)
            r.runtime.set_eve(True, 3)
        finally:
            release.set()
        pending.result(5)
    r.wait_state(lambda state: state.eve == "active")
    assert r.runtime.snapshot().eve_epoch == r.host._eve_epoch == 1


def test_boundary_f_held_active_ack_cannot_revive_revoked_admission(runtime_pump):
    r = runtime_pump()
    eve_on(r)
    r.runtime.set_eve(False, 2)
    r.wait_state(lambda state: state.eve == "stopped" and not r.host.is_stopping)
    entered, release, delivered, unwind = Event(), Event(), Event(), Event()
    callback = r.host._lifecycle_callback

    def held(ack):
        if ack.outcome == "eve-active" and ack.eve_epoch == 3:
            entered.set()
            assert release.wait(5)
            callback(ack)
            delivered.set()
            assert unwind.wait(5)
        else:
            callback(ack)

    r.host._lifecycle_callback = held
    r.runtime.set_eve(True, 3)
    assert entered.wait(5)
    try:
        r.runtime.set_eve(False, 4)
        r.runtime.set_eve(True, 5)
        assert not r.host.runtime_enabled and r.host._eve_epoch == 4
        release.set()
        assert delivered.wait(5)
        assert r.runtime.snapshot().eve != "active"
    finally:
        release.set()
        unwind.set()
    r.wait_state(lambda state: state.eve == "active" and state.eve_epoch == 5)


@pytest.mark.parametrize("started", [False, True])
def test_boundary_g_actual_thread_start_failure_retires_storage_before_retry(
    runtime_pump, monkeypatch, started
):
    entered, release = Event(), Event()

    def flush():
        entered.set()
        assert release.wait(5)

    r = runtime_pump(start=False, primary_flush=flush)
    attempts = []

    class NativeThread(threading.Thread):
        def start(self):
            attempts.append(self)
            if len(attempts) == 1:
                if started:
                    super().start()
                raise RuntimeError("native thread launch refused")
            return super().start()

    monkeypatch.setattr(host_mod, "threading", SimpleNamespace(Thread=NativeThread))
    r.runtime.set_eve(True, 1)
    try:
        assert entered.wait(5)
        r.runtime.set_eve(True, 1)
        assert len(attempts) == 1 and attempts[0].is_alive() == started
    finally:
        release.set()
    r.wait_state(lambda state: state.eve == "active")
    assert len(attempts) == 2 and r.host._thread is attempts[1]
    assert r.runtime.shutdown(5)


def test_boundary_c_removed_chord_cannot_regain_authority_on_late_register_return(
    runtime_pump, monkeypatch
):
    r = runtime_pump()
    entered, release, can_release = Event(), Event(), Event()
    activated = []

    def register(*args):
        entered.set()  # OS acquisition succeeded; only its FFI return is held.
        assert release.wait(5)
        return True

    monkeypatch.setattr(r.native, "RegisterHotKey", register, raising=False)
    monkeypatch.setattr(
        r.native, "UnregisterHotKey", lambda *args: can_release.is_set(), raising=False
    )
    monkeypatch.setattr(r.native, "GetForegroundWindow", lambda: 0, raising=False)
    monkeypatch.setattr(
        r.host,
        "_activate_client",
        lambda libs, source: activated.append(source.stable_key),
    )
    r.host._clients["Alice"] = host_mod._preview_client(client())
    r.host.set_hotkeys({"characters": {"Alice": "Ctrl+F1"}})
    r.runtime.set_eve(True, 1)
    assert entered.wait(5)
    try:
        r.native.PostMessageW(42, win32.WM_HOTKEY, 1, 0)
        r.host.set_hotkeys({"characters": {}})  # REBIND is behind the OS hotkey.
        release.set()
        r.call(lambda: None)
        assert not activated
        assert r.host.hotkey_status() == {}
    finally:
        release.set()
        can_release.set()
        r.host.request_rebind()
        r.call(lambda: None)


def test_admission_snapshot_does_not_retire_prospective_selection(
    runtime_pump, monkeypatch
):
    r = runtime_pump(start=False)
    release = Event()
    run = r.runtime._run
    query = r.host._admission_epochs
    seen = []

    def held_executor():
        assert release.wait(5)
        run()

    def checked_query():
        assert not r.runtime._condition._is_owned()
        epochs = query()
        assert isinstance(epochs, tuple)
        seen.append(epochs)
        return epochs

    monkeypatch.setattr(r.runtime, "_run", held_executor)
    monkeypatch.setattr(r.host, "_admission_epochs", checked_query)
    lease = r.runtime.acquire_selection(91)
    try:
        r.runtime.set_companions(False, 1)
        assert seen == [(0, 0, 0)]
        assert r.runtime.snapshot().selection_pending and lease.pump_epoch == 1
    finally:
        release.set()
    r.wait_state(lambda state: state.pump == "active")
    assert r.runtime.snapshot().selection_pending
    r.runtime.release_selection(lease)


def test_active_ack_deferral_is_bounded_while_stop_ack_reaches_cleanup(
    runtime_pump, monkeypatch
):
    r = runtime_pump()
    eve_on(r)
    r.runtime.set_eve(False, 2)
    r.wait_state(lambda state: state.eve == "stopped" and not r.host.is_stopping)
    active, release_active, delivered = Event(), Event(), Event()
    queried, release_query = Event(), Event()
    callback, query = r.host._lifecycle_callback, r.host._admission_epochs

    def held_active(ack):
        if ack.outcome == "eve-active" and ack.eve_epoch == 3:
            active.set()
            assert release_active.wait(5)
            callback(ack)
            delivered.set()
        else:
            callback(ack)

    def held_query():
        assert not r.runtime._condition._is_owned()
        epochs = query()
        if epochs[1] == 4 and not queried.is_set():
            queried.set()
            assert release_query.wait(5)
        return epochs

    r.host._lifecycle_callback = held_active
    r.runtime.set_eve(True, 3)
    assert active.wait(5)
    monkeypatch.setattr(r.host, "_admission_epochs", held_query)
    with ThreadPoolExecutor(max_workers=1) as pool:
        off = pool.submit(r.runtime.set_eve, False, 4)
        assert queried.wait(5)
        try:
            r.runtime.set_eve(True, 5)
            release_active.set()
            assert delivered.wait(5)
            assert r.runtime.snapshot().eve != "active"
            assert len(r.runtime._deferred_active) == 1
            # The real pump can finish epoch-four cleanup while its admission
            # query is held. Stopped is never deferred with the stale active ack.
            r.wait_state(lambda state: state.eve_epoch == 4)
        finally:
            release_active.set()
            release_query.set()
        off.result(5)
    r.wait_state(lambda state: state.eve == "active" and state.eve_epoch == 5)
    assert not r.runtime._deferred_active
