"""Completion, not successful posting, owns primary-layout admission."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from tests.test_preview_host import crop_pump as crop_pump
from tests.test_preview_polish_fixes import layout_api as layout_api
from tests.test_preview_polish_fixes import open_eve
from tests.test_preview_runtime_review import parked
from tests.test_preview_runtime_review import runtime_pump as runtime_pump
from wingman.preview import win32
from wingman.preview.runtime import FamilyDemand


def test_exclusive_waits_for_ordinary_completion():
    from wingman.preview.layoutadmission import PrimaryLayoutAdmission

    gate = PrimaryLayoutAdmission()
    ordinary = gate.try_begin(exclusive=False)
    assert ordinary is not None
    assert gate.try_begin(exclusive=True) is None
    gate.finish(ordinary)
    batch = gate.try_begin(exclusive=True)
    assert batch is not None
    assert gate.try_begin(exclusive=False) is None
    gate.close()
    assert not gate.wait_idle(timeout=0)
    gate.finish(batch)
    assert gate.wait_idle(timeout=0)
    assert gate.try_begin(exclusive=True) is None


def test_shared_leases_finish_independently_and_ids_do_not_reuse():
    from wingman.preview.layoutadmission import PrimaryLayoutAdmission

    gate = PrimaryLayoutAdmission()
    first = gate.try_begin(exclusive=False)
    second = gate.try_begin(exclusive=False)
    assert gate.snapshot().shared_count == 2
    gate.finish(first)
    gate.finish(first)
    assert not gate.owns(first) and gate.owns(second)
    assert gate.snapshot().shared_count == 1
    gate.finish(second)
    third = gate.try_begin(exclusive=True)
    assert third.operation_id > second.operation_id > first.operation_id
    assert gate.snapshot().exclusive
    gate.finish(third)


def test_timed_out_wait_retains_closed_owner_until_real_completion():
    from wingman.preview.layoutadmission import PrimaryLayoutAdmission

    gate = PrimaryLayoutAdmission()
    lease = gate.try_begin(exclusive=False)
    entered, release = Event(), Event()

    def work():
        entered.set()
        assert release.wait(5)
        gate.finish(lease)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(work)
        assert entered.wait(5)
        try:
            gate.close()
            assert gate.snapshot().closed
            assert not gate.wait_idle(timeout=0.01)
            assert gate.owns(lease)
            assert gate.try_begin(exclusive=False) is None
        finally:
            release.set()
        assert gate.wait_idle(timeout=5)
        future.result(5)


def test_foreign_lease_cannot_retire_an_owner_with_the_same_id():
    from wingman.preview.layoutadmission import PrimaryLayoutAdmission

    gate, other = PrimaryLayoutAdmission(), PrimaryLayoutAdmission()
    owned = gate.try_begin(exclusive=False)
    foreign = other.try_begin(exclusive=False)
    assert owned.operation_id == foreign.operation_id
    assert not gate.owns(foreign)
    gate.finish(foreign)
    assert gate.owns(owned)
    gate.finish(owned)
    other.finish(foreign)


@pytest.mark.parametrize(
    "operation", ["default", "size", "copy", "reset", "visibility", "on"]
)
def test_bridge_and_host_share_exclusive_refusal(layout_api, operation):
    r = layout_api()
    open_eve(r)
    gate = r.host._layout_admission
    lease = gate.try_begin(exclusive=True)
    commands = {
        "default": lambda: r.api.set_preview_default_size(500, 300),
        "size": lambda: r.api.set_preview_size("Alice", 500, 300),
        "copy": lambda: r.api.copy_preview_layout("Alice", "Bob"),
        "reset": r.api.reset_preview_layouts,
        "visibility": lambda: r.api.set_preview_excluded("Alice", True),
        "on": lambda: r.api.set_preview_enabled(True),
    }
    try:
        result = commands[operation]()
        assert result is False if operation == "on" else not result["applied"]
        assert r.api.set_preview_enabled(
            False
        )  # Revocation never waits for layout idle.
        assert not r.host.runtime_enabled
    finally:
        r.host.release_primary_layout(lease)


def test_visibility_promise_waits_for_reconcile_and_rebind(layout_api, monkeypatch):
    r = layout_api()
    open_eve(r)
    from tests.test_preview_cropcontroller import client
    from wingman.preview.host import _preview_client
    from wingman.telemetry.model import RosterSnapshot

    r.call(lambda: r.host._clients.update(Alice=_preview_client(client())))
    r.host.apply_roster(RosterSnapshot(2, (client(),)))
    r.call(lambda: None)
    observed = []
    monkeypatch.setattr(
        r.host, "_reconcile_roster", lambda *args: observed.append("roster")
    )
    rebind = r.host._apply_hotkeys

    def observed_rebind(*args):
        observed.append("rebind")
        return rebind(*args)

    monkeypatch.setattr(r.host, "_apply_hotkeys", observed_rebind)
    entered = Event()
    pending = []
    refresh = r.host.refresh_primary_visibility

    def admitted(lease):
        future = refresh(lease)
        pending.append(future)
        entered.set()
        return future

    monkeypatch.setattr(r.host, "refresh_primary_visibility", admitted)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with parked(r):
            future = pool.submit(r.api.set_preview_excluded, "Alice", True)
            assert entered.wait(5)
            assert not future.done() and not pending[0].done()
            assert not r.host._layout_admission.wait_idle(0)
        assert future.result(5)["persisted"]
        assert pending[0].result(5).live == "applied"
    assert "roster" in observed and observed[-1] == "rebind"
    assert r.host._layout_admission.wait_idle(5)


def test_copy_coalescing_keeps_every_lease_until_native_retirement(layout_api):
    from wingman.preview.geometry import Rect
    from wingman.preview.layout import Entry

    r = layout_api()
    open_eve(r)
    r.host.sync_layout("Bob", Entry(Rect(60, 70, 450, 250)))
    r.host.sync_layout("Carol", Entry(Rect(90, 100, 550, 350)))
    with parked(r):
        assert r.host.copy_layout("Alice", "Bob") == "ok"
        assert r.host.copy_layout("Alice", "Carol") == "ok"
        assert r.host._layout_admission.snapshot().shared_count == 2
        assert not r.moved
    assert r.host._layout_admission.wait_idle(5)
    assert r.moved == [Rect(90, 100, 550, 350)]
    assert r.api._state.settings["preview"]["layouts"]["Alice"]["w"] == 550


def test_mid_resize_all_revocation_fences_each_native_target(layout_api, monkeypatch):
    from tests.test_preview_cropcontroller import client
    from wingman.preview.geometry import Rect
    from wingman.preview.host import _preview_client
    from wingman.preview.window import PreviewWindow

    r = layout_api()
    open_eve(r)
    epoch = r.host._eve_epoch
    entered, release = Event(), Event()
    moved, windows = [], {}
    cursor = [0, 0]

    def get_cursor(ptr):
        ptr._obj.x, ptr._obj.y = cursor
        return True

    def position(hwnd, after, x, y, w, h, flags):
        assert r.host._lock.acquire(blocking=False)
        r.host._lock.release()
        moved.append((hwnd, r.host._eve_valid(epoch)))
        if hwnd == 52:  # Bob crossed native admission; Carol has not.
            entered.set()
            assert release.wait(5)
        return True

    monkeypatch.setattr(r.native, "GetCursorPos", get_cursor, raising=False)
    monkeypatch.setattr(r.native, "SetWindowPos", position)

    def install():
        for hwnd, name in enumerate(("Alice", "Bob", "Carol"), 51):
            win = PreviewWindow(
                r.native.lib,
                _preview_client(client(name, hwnd=hwnd + 100)),
                Rect(20, 30, 320, 210),
                lambda client: None,
                lambda *args, owner=name: r.host._primary_rect_changed(
                    epoch, owner, *args
                ),
                list,
                r.host._screen,
                show_labels=False,
                lock_aspect=False,
                is_authorized=lambda: r.host._eve_valid(epoch),
                on_gesture_begin=lambda owner=name: r.host._begin_primary_gesture(
                    epoch, owner
                ),
                on_gesture_end=r.host.release_primary_layout,
                on_resize_all=lambda rect, owner=name: (
                    r.host._mirror_resize(owner, rect)
                    if r.host._eve_valid(epoch)
                    else None
                ),
            )
            win.hwnd = hwnd
            win.redraw = lambda force=False: None
            r.native.windows[hwnd] = "primary"
            windows[name] = win
        r.host._windows = windows.copy()
        driver = windows["Alice"]
        driver._on_message(win32.WM_RBUTTONDOWN, 0, 0)
        driver._on_message(win32.WM_LBUTTONDOWN, 0, 0)

    r.call(install)
    cursor[:] = [80, 50]
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            r.call, lambda: windows["Alice"]._on_message(win32.WM_MOUSEMOVE, 0, 0)
        )
        if not entered.wait(5):
            future.result(5)
            pytest.fail("resize-all did not reach Bob's native movement")
        try:
            assert r.api.set_preview_enabled(False)
            assert not r.host._layout_admission.wait_idle(0)
        finally:
            release.set()
        future.result(5)
    r.wait_state(lambda state: state.eve == "stopped")
    assert moved == [(51, True), (52, True)]
    assert windows["Carol"].rect == Rect(20, 30, 320, 210)
    assert r.host.layout_entries()["Alice"].rect == Rect(20, 30, 400, 260)
    assert r.host.layout_entries()["Bob"].rect == Rect(20, 30, 400, 260)
    assert r.host._layout_admission.wait_idle(5)


@pytest.mark.parametrize("operation", ["size", "size-all"])
def test_revoked_native_size_keeps_the_admitted_storage_choice(
    layout_api, monkeypatch, operation
):
    from tests.test_preview_cropcontroller import client
    from wingman.preview.geometry import Rect
    from wingman.preview.host import _preview_client
    from wingman.preview.window import PreviewWindow

    r = layout_api()
    open_eve(r)
    epoch = r.host._eve_epoch
    entered, release = Event(), Event()
    moved = []

    def authorized():
        entered.set()
        assert release.wait(5)
        return r.host._eve_valid(epoch)

    def install():
        win = PreviewWindow(
            r.native.lib,
            _preview_client(client()),
            Rect(20, 30, 320, 210),
            lambda client: None,
            r.host._layout_changed,
            list,
            r.host._screen,
            show_labels=False,
            is_authorized=authorized,
        )
        win.hwnd = 51
        r.native.windows[51] = "primary"
        r.host._windows["Alice"] = win

    monkeypatch.setattr(
        r.native, "SetWindowPos", lambda *args: moved.append(args) or True
    )
    r.call(install)
    assert (
        r.host.resize_preview("Alice", (500, 300))
        if operation == "size"
        else r.host.resize_all((500, 300))
    )
    assert entered.wait(5)
    try:
        assert r.api.set_preview_enabled(False)
        assert not r.host._layout_admission.wait_idle(0)
    finally:
        release.set()
    assert r.host._layout_admission.wait_idle(5)
    r.wait_state(lambda state: state.eve == "stopped")
    assert not moved
    assert r.host.layout_entries()["Alice"].rect == Rect(20, 30, 500, 300)
    saved = r.api._state.settings["preview"]["layouts"]["Alice"]
    assert (saved["w"], saved["h"]) == (500, 300)


def test_stop_freezes_gesture_before_waiting_for_queued_reset(layout_api, monkeypatch):
    from tests.test_preview_cropcontroller import client
    from wingman.preview.geometry import Rect
    from wingman.preview.host import _preview_client
    from wingman.preview.window import PreviewWindow

    r = layout_api()
    open_eve(r)

    monkeypatch.setattr(r.native, "GetCursorPos", lambda ptr: True, raising=False)

    def install():
        win = PreviewWindow(
            r.native.lib,
            _preview_client(client()),
            Rect(60, 70, 450, 250),
            lambda client: None,
            r.host._layout_changed,
            list,
            r.host._screen,
            show_labels=False,
            lock_aspect=False,
            on_gesture_begin=lambda: r.host._begin_primary_gesture(
                r.host._eve_epoch, "Alice"
            ),
            on_gesture_end=r.host.release_primary_layout,
        )
        win.hwnd = 51
        r.native.windows[51] = "primary"
        r.host._windows["Alice"] = win
        win._on_message(win32.WM_RBUTTONDOWN, 0, 0)

    r.call(install)
    assert r.native.capture == 51
    entered, release = Event(), Event()
    clear = r.host._clear_layouts

    def held_clear():
        entered.set()
        assert release.wait(5)
        return clear()

    monkeypatch.setattr(r.host, "_clear_layouts", held_clear)
    try:
        assert r.host.reset_layouts()
        assert entered.wait(5)
        r.call(lambda: None)
        # Reset supersedes the earlier drag before its asynchronous clear;
        # freezing it later during Off would resurrect the erased geometry.
        assert r.host._layout_admission.snapshot().shared_count == 1
        assert r.native.capture is None
        r.call(lambda: r.host._windows["Alice"]._on_message(win32.WM_RBUTTONUP, 0, 0))
        assert r.native.capture is None
        assert r.api.set_preview_enabled(False)
    finally:
        release.set()
    assert r.host._layout_admission.wait_idle(5)
    r.wait_state(lambda state: state.eve == "stopped")
    assert r.api._state.settings["preview"]["layouts"] == {}


def test_eve_stop_does_not_release_foreign_mouse_capture(layout_api):
    r = layout_api()
    r.runtime.set_companions(True, 1)
    r.wait_state(lambda state: state.companions == "active")
    open_eve(r)
    r.call(lambda: r.native.SetCapture(99))
    assert r.api.set_preview_enabled(False)
    r.wait_state(lambda state: state.eve == "stopped" and state.companions == "active")
    try:
        assert r.call(r.native.GetCapture) == 99
    finally:
        r.call(r.native.ReleaseCapture)


def test_offline_copy_io_blocks_on_and_final_storage_close(layout_api, monkeypatch):
    from wingman.preview.geometry import Rect
    from wingman.preview.layout import Entry

    r = layout_api()
    r.host.sync_layout("Bob", Entry(Rect(60, 70, 450, 250)))
    entered, release = Event(), Event()
    replace = r.host._replace_layout

    def held(*args):
        entered.set()
        assert release.wait(5)
        return replace(*args)

    monkeypatch.setattr(r.host, "_replace_layout", held)
    with ThreadPoolExecutor(max_workers=1) as pool:
        copy = pool.submit(r.host.copy_layout, "Alice", "Bob")
        assert entered.wait(5)
        try:
            assert not r.api.set_preview_enabled(True)
            assert not r.runtime.shutdown(0)
            assert r.store._close_future is None
        finally:
            release.set()
        assert copy.result(5) == "ok"
    assert r.runtime.shutdown(5)
    assert r.host.layout_entries()["Alice"].rect.w == 450


def test_replacement_family_admission_waits_for_detached_owner(layout_api):
    r = layout_api()
    lease = r.host._layout_admission.try_begin(exclusive=False)
    try:
        assert r.host.set_families(FamilyDemand(1, True, False))
        assert not r.host._eve_valid()
    finally:
        r.host.release_primary_layout(lease)
    assert r.host._eve_valid()


def test_native_preparation_failure_retires_lease_without_killing_pump(
    layout_api, monkeypatch
):
    r = layout_api()
    open_eve(r)

    def fail(_pending):
        raise OSError("native size preparation failed")

    monkeypatch.setattr(r.host, "_apply_resizes", fail)
    assert r.host.resize_preview("Alice", (500, 300))
    assert r.host._layout_admission.wait_idle(5)
    r.call(lambda: None)
    assert r.host.runtime_enabled and not r.host.layout_commands_pending


def test_copy_mailbox_prevents_offline_size_overtaking_it(layout_api):
    from wingman.preview.geometry import Rect
    from wingman.preview.layout import Entry

    r = layout_api()
    open_eve(r)
    r.host.sync_layout("Bob", Entry(Rect(60, 70, 450, 250)))
    r.call(lambda: r.host._clients.clear())
    with parked(r):
        assert r.host.copy_layout("Alice", "Bob") == "ok"
        assert r.host.layout_commands_pending
        assert not r.api.set_preview_size("Alice", 500, 300)["applied"]
    assert r.host._layout_admission.wait_idle(5)


def test_shared_resources_survive_platform_host_unavailability(tmp_path, monkeypatch):
    from tests.test_api import make_state
    from tests.test_preview_store import FakeTimer
    from wingman import __main__ as main_mod
    from wingman import settings
    from wingman.preview.geometry import Rect
    from wingman.preview.layout import Entry
    from wingman.preview.layoutadmission import PrimaryLayoutAdmission
    from wingman.preview.store import LayoutStore
    from wingman.ui.api import Api

    state = make_state(tmp_path)
    store = LayoutStore(lambda: settings.update(state.settings), timer=FakeTimer)
    gate = PrimaryLayoutAdmission()
    monkeypatch.setattr(main_mod.sys, "platform", "linux")
    host = main_mod.build_preview_host(
        state, {}, layout_store=store, layout_admission=gate
    )
    assert host is None
    api = Api(state, preview_host=host, layout_store=store, layout_admission=gate)
    assert store.replace("Alice", Entry(Rect(20, 30, 320, 210)))
    store.record("Alice", Entry(Rect(20, 30, 450, 250)))
    lease = gate.try_begin(exclusive=True)
    try:
        assert not api.set_preview_size("Alice", 500, 300)["applied"]
    finally:
        gate.finish(lease)
    assert api.set_preview_size("Alice", 500, 300)["persisted"]
    store.flush()
    assert settings.load()["preview"]["layouts"]["Alice"]["w"] == 500
    api._close_eve_runtime()
    assert gate.snapshot().closed
    assert not api.reset_preview_layouts()["applied"]


@pytest.mark.parametrize("failure", ["reset", "size"])
def test_host_worker_start_failure_retires_admitted_primary(
    layout_api, monkeypatch, failure
):
    r = layout_api()
    open_eve(r)

    def fail():
        raise RuntimeError("primary worker cannot start")

    monkeypatch.setattr(r.store, "_executor_factory", fail)
    assert (
        r.host.reset_layouts()
        if failure == "reset"
        else r.host.resize_preview("Alice", (500, 300))
    )
    assert r.host._layout_admission.wait_idle(5)
    assert not r.host.layout_commands_pending
    r.call(lambda: None)
    assert r.host.runtime_enabled


def test_visibility_failure_retains_persisted_choice_and_warns(layout_api, monkeypatch):
    r = layout_api()
    open_eve(r)

    def fail(*args):
        raise OSError("hotkey rebind failed")

    monkeypatch.setattr(r.host, "_apply_hotkeys", fail)
    result = r.api.set_preview_excluded("Alice", True)
    assert result["persisted"] and "hotkey rebind failed" in result["warning"]
    assert "Alice" in r.api._state.settings["preview"]["excluded"]
    assert r.host._layout_admission.wait_idle(5)


@pytest.mark.parametrize("failure", ["unregister", "register"])
def test_visibility_false_native_rebind_preserves_choices_and_reports_incomplete(
    layout_api, monkeypatch, failure
):
    from tests.test_preview_host import _FakeUser32
    from wingman import settings

    r = layout_api()
    native = _FakeUser32()
    monkeypatch.setattr(
        r.native, "RegisterHotKey", native.RegisterHotKey, raising=False
    )
    monkeypatch.setattr(
        r.native, "UnregisterHotKey", native.UnregisterHotKey, raising=False
    )
    monkeypatch.setattr(
        r.host, "_excluded", lambda: r.api._state.settings["preview"]["excluded"]
    )
    open_eve(r)
    table = {"characters": {"Alice": "Ctrl+F1", "Bob": "Ctrl+F2", "Carol": "Ctrl+F3"}}
    r.host.set_hotkeys(table)
    registered = r.call(lambda: dict(r.host._registered_text))
    alice_id = next(ident for ident, text in registered.items() if text == "Ctrl+F1")
    bob_id = next(ident for ident, text in registered.items() if text == "Ctrl+F2")
    pending = []
    refresh = r.host.refresh_primary_visibility

    def remember(lease):
        future = refresh(lease)
        pending.append(future)
        return future

    monkeypatch.setattr(r.host, "refresh_primary_visibility", remember)
    if failure == "unregister":
        monkeypatch.setattr(
            r.native,
            "UnregisterHotKey",
            lambda hwnd, ident: (
                False if ident == alice_id else native.UnregisterHotKey(hwnd, ident)
            ),
        )
    else:
        native._refuse.add(native.registered[bob_id])
    try:
        result = r.api.set_preview_excluded("Alice", True)
        assert result["applied"] and result["persisted"] and not result["error"]
        assert settings.load()["preview"]["excluded"] == ["Alice"]
        assert r.host._desired_hotkeys == table
        assert r.host._layout_admission.wait_idle(5)
        assert pending[-1].result(5).live == "incomplete"
        warning = result["warning"]
        if failure == "unregister":
            assert "release" in warning.lower() and "Ctrl+F1" in warning
            assert r.call(lambda: dict(r.host._registered_text)) == {
                alice_id: "Ctrl+F1"
            }
            assert alice_id in native.registered
            assert (
                r.call(lambda: dict(r.host._registered)) == {}
            )  # Held, not authorized.
        else:
            assert "register" in warning.lower() and "Ctrl+F2" in warning
            assert list(r.call(lambda: dict(r.host._registered_text)).values()) == [
                "Ctrl+F3"
            ]
            assert len(native.registered) == 1
    finally:
        native._refuse.clear()
        monkeypatch.setattr(r.native, "UnregisterHotKey", native.UnregisterHotKey)
    retry = r.api.set_preview_excluded("Alice", True)
    assert retry["persisted"] and not retry.get("warning")
    assert pending[-1].result(5).live == "applied"
    assert set(r.call(lambda: dict(r.host._registered_text)).values()) == {
        "Ctrl+F2",
        "Ctrl+F3",
    }


def test_off_does_not_complete_an_executing_visibility_phase_early(
    layout_api, monkeypatch
):
    r = layout_api()
    open_eve(r)
    entered, release = Event(), Event()
    rebind = r.host._apply_hotkeys

    def held(*args):
        entered.set()
        assert release.wait(5)
        return rebind(*args)

    monkeypatch.setattr(r.host, "_apply_hotkeys", held)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(r.api.set_preview_excluded, "Alice", True)
        assert entered.wait(5)
        try:
            assert r.api.set_preview_enabled(False)
            assert not r.host.runtime_enabled
            assert not future.done() and not r.host._layout_admission.wait_idle(0)
        finally:
            release.set()
        assert future.result(5)["persisted"]
    assert r.host._layout_admission.wait_idle(5)


def test_offline_crop_submission_cannot_close_ahead_of_admitted_reset(
    layout_api, monkeypatch
):
    r = layout_api()
    crop_entered, crop_release = Event(), Event()
    reset_entered, reset_release = Event(), Event()
    submit, clear = r.store.set_enabled, r.host.clear_layouts_offline

    def held_crop(*args):
        crop_entered.set()
        assert crop_release.wait(5)
        return submit(*args)

    def held_reset():
        reset_entered.set()
        assert reset_release.wait(5)
        return clear()

    monkeypatch.setattr(r.store, "set_enabled", held_crop)
    monkeypatch.setattr(r.host, "clear_layouts_offline", held_reset)
    with ThreadPoolExecutor(max_workers=2) as pool:
        crop = pool.submit(r.host.request_crop, "enabled", "Alice", False)
        assert crop_entered.wait(5)
        reset = pool.submit(r.api.reset_preview_layouts)
        assert reset_entered.wait(5)
        try:
            r.runtime.close_admission()
            assert not r.host.stop(timeout=0, final=True)
            crop_release.set()
            crop.result(5)
            assert r.store._close_future is None
        finally:
            crop_release.set()
            reset_release.set()
        assert reset.result(5)["persisted"]
    assert r.runtime.shutdown(5)
    assert r.api._state.settings["preview"]["layouts"] == {}


def test_off_accepts_only_the_admitted_gestures_final_geometry(layout_api):
    from wingman.preview.geometry import Rect

    r = layout_api()
    open_eve(r)
    epoch = r.host._eve_epoch
    with parked(r):
        lease = r.host._begin_primary_gesture(epoch, "Alice")
        assert lease is not None
        try:
            assert r.api.set_preview_enabled(False)
            r.host._primary_rect_changed(
                epoch, "Alice", "Alice", Rect(60, 70, 450, 250), False
            )
        finally:
            r.host.release_primary_layout(lease)
        r.host._primary_rect_changed(
            epoch, "Alice", "Alice", Rect(90, 100, 550, 350), False
        )
    r.wait_state(lambda state: state.eve == "stopped")
    assert r.host.layout_entries()["Alice"].rect == Rect(60, 70, 450, 250)
    assert r.api._state.settings["preview"]["layouts"]["Alice"]["w"] == 450


def test_stop_retains_crop_mailbox_while_primary_completion_is_pending(
    layout_api, monkeypatch
):
    r = layout_api()
    open_eve(r)
    entered, release = Event(), Event()
    clear = r.host._clear_layouts

    def held_clear():
        entered.set()
        assert release.wait(5)
        return clear()

    monkeypatch.setattr(r.host, "_clear_layouts", held_clear)
    try:
        with parked(r):
            assert r.host.reset_layouts()
            crop = r.host.request_crop("enabled", "Alice", False)
            assert crop["pending"]
            assert r.api.set_preview_enabled(False)
        assert entered.wait(5)
        r.call(lambda: None)
        assert r.host._crop_commands  # Not detached into a returned stop frame.
    finally:
        release.set()
    assert r.host._layout_admission.wait_idle(5)
    r.wait_state(lambda state: state.eve == "stopped")
    assert r.host.crop_state()["operations"][crop["operation_id"]]["persisted"]
    assert not r.api._state.settings["preview"]["crops"]["Alice"]["enabled"]


def test_consumed_resize_wake_waits_for_reset_storage_and_retains_leases(
    layout_api, monkeypatch
):
    r = layout_api()
    open_eve(r)
    entered, release = Event(), Event()
    clear = r.host._clear_layouts

    def held_clear():
        entered.set()
        assert release.wait(5)
        clear()

    monkeypatch.setattr(r.host, "_clear_layouts", held_clear)
    try:
        assert r.api.reset_preview_layouts()["applied"]
        assert entered.wait(5)
        assert r.api.set_preview_size("Alice", 500, 300)["applied"]
        r.call(lambda: None)  # Consume Size's OS wake while Reset still owns I/O.
        assert r.host._layout_admission.try_begin(exclusive=True) is None
        assert r.host.layout_commands_pending
        assert not r.moved
    finally:
        release.set()
    assert r.host._layout_admission.wait_idle(5)
    r.call(lambda: None)
    assert not r.host.layout_commands_pending
    assert r.api._state.settings["preview"]["layouts"]["Alice"]["w"] == 500
    assert r.moved[-1].w == 500


def test_live_failed_completion_post_retains_native_phase_until_existing_turn(
    layout_api, monkeypatch
):
    r = layout_api()
    open_eve(r)
    entered, release, failed = Event(), Event(), Event()
    clear, post = r.host._clear_layouts, r.native.PostMessageW

    def held_clear():
        entered.set()
        assert release.wait(5)
        clear()

    def fail_completion(hwnd, msg, wp, lp):
        if msg == win32.WM_APP_PRIMARY_COMPLETE:
            failed.set()
            return 0
        return post(hwnd, msg, wp, lp)

    # Evaluate before installing the seam so a missing production constant
    # fails without breaking unrelated teardown posts in the RED run.
    assert win32.WM_APP_PRIMARY_COMPLETE
    monkeypatch.setattr(r.host, "_clear_layouts", held_clear)
    monkeypatch.setattr(r.native, "PostMessageW", fail_completion)
    try:
        assert r.host.reset_layouts()
        assert entered.wait(5)
        release.set()
        assert failed.wait(5)
        assert r.host.layout_commands_pending and not r.moved
        assert not r.host._layout_admission.wait_idle(0)
        r.call(lambda: None)  # No new owner/timer/retry thread, just the next turn.
        assert r.host._layout_admission.wait_idle(5)
        assert r.moved and not r.host.layout_commands_pending
    finally:
        release.set()


@pytest.mark.parametrize("native", [False, True])
def test_final_barrier_waits_for_reset_and_admitted_resize_completion(
    layout_api, monkeypatch, native
):
    entered, release = Event(), Event()
    r = layout_api()
    if native:
        open_eve(r)
    else:
        r.host.set_families(FamilyDemand(1, True, False))
    clear = r.host._clear_layouts

    def held_clear():
        entered.set()
        assert release.wait(5)
        clear()

    monkeypatch.setattr(r.host, "_clear_layouts", held_clear)
    try:
        assert r.host.reset_layouts()
        assert r.host.resize_preview("Alice", (500, 300))
        if not native:
            r.host.close_admission()
            assert not r.host.stop(timeout=0, final=True)
        else:
            assert entered.wait(5)
            r.call(lambda: None)
            r.runtime.close_admission()
            assert not r.runtime.shutdown(0)
        assert entered.wait(5)
        assert r.store._close_future is None
        assert r.host.layout_commands_pending
    finally:
        release.set()
    assert r.host._layout_admission.wait_idle(5)
    assert r.runtime.shutdown(5)
    assert not r.host.layout_commands_pending
    assert r.api._state.settings["preview"]["layouts"]["Alice"]["w"] == 500
