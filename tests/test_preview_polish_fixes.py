"""Accepted primary storage, OS wake failure, and retained-owner regressions."""

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event
from types import SimpleNamespace

import pytest

from tests.test_api import make_api
from tests.test_preview_host import crop_pump as crop_pump
from tests.test_preview_runtime_review import parked
from tests.test_preview_runtime_review import runtime_pump as runtime_pump
from tests.test_preview_store import FakeTimer
from wingman import settings
from wingman.preview import geometry, layout, win32
from wingman.preview.store import LayoutStore


@pytest.fixture
def layout_api(runtime_pump, tmp_path):
    def make(**kwargs):
        r = runtime_pump(
            start=False,
            update_settings=lambda: settings.update(api._state.settings),
            **kwargs,
        )
        publish = r.runtime._callback
        api = make_api(tmp_path, preview_host=r.host, preview_runtime=r.runtime)
        r.runtime.set_state_callback(
            lambda state: (api._preview_runtime_changed(state), publish(state))
        )
        store = LayoutStore(
            lambda: settings.update(api._state.settings), timer=FakeTimer
        )
        r.store._flush_primary = store.flush
        r.host._flush_layouts = store.flush
        r.host._clear_layouts = store.clear
        r.host._replace_layout = store.replace
        r.host._on_layout_changed = lambda name, rect, locked: store.record(
            name, layout.Entry(rect, locked)
        )
        initial = layout.Entry(geometry.Rect(20, 30, 320, 210))
        assert store.replace("Alice", initial)
        r.host.sync_layout("Alice", initial)
        r.api, r.layouts, r.moved = api, store, []
        return r

    return make


def open_eve(r):
    assert r.api.set_preview_enabled(True)
    r.wait_state(lambda state: state.eve == "active")
    primary = SimpleNamespace(
        rect=geometry.Rect(20, 30, 320, 210),
        locked=False,
        _mode=None,
        move=lambda rect: r.moved.append(rect),
        set_hidden=lambda hidden: None,
        close=lambda: None,
    )
    r.call(
        lambda: (
            r.host._windows.update(Alice=primary),
            r.host._clients.update(Alice=None),
        )
    )


def refused(receipt):
    assert receipt["applied"] is False and receipt["persisted"] is False
    assert receipt["error"]


@pytest.mark.parametrize("command", ["reset", "resize", "resize-all"])
def test_failed_primary_wake_refuses_without_wedging_quit(
    layout_api, monkeypatch, command
):
    r = layout_api()
    open_eve(r)
    post = r.native.PostMessageW
    message = {
        "reset": win32.WM_APP_RESET_LAYOUTS,
        "resize": win32.WM_APP_RESIZE_ONE,
        "resize-all": win32.WM_APP_RESIZE_ALL,
    }[command]
    failed = Event()

    def fail_once(hwnd, msg, wp, lp):
        if msg == message and not failed.is_set():
            failed.set()
            return 0
        return post(hwnd, msg, wp, lp)

    monkeypatch.setattr(r.native, "PostMessageW", fail_once)
    submit = {
        "reset": r.api.reset_preview_layouts,
        "resize": lambda: r.api.set_preview_size("Alice", 500, 300),
        "resize-all": r.api.apply_preview_default_size,
    }[command]
    try:
        with parked(r):
            first = submit()
            assert failed.is_set()
            refused(first)
            assert submit()["applied"]
        assert r.runtime.shutdown(5)
        assert not r.host.is_running
    finally:
        # Make RED failures clean too: supply the lost signal to the original
        # implementation rather than leave its daemon poisoning later cases.
        if r.host._hwnd:
            post(r.host._hwnd, message, r.host._eve_epoch, 0)


@pytest.mark.parametrize("companions", [False, True])
@pytest.mark.parametrize("command", ["reset", "resize"])
def test_offline_edit_refuses_older_retained_storage_then_succeeds(
    layout_api, companions, command
):
    r = layout_api()
    if companions:
        r.runtime.set_companions(True, 1)
        r.wait_state(lambda state: state.companions == "active")
    open_eve(r)
    edit = (
        r.api.reset_preview_layouts
        if command == "reset"
        else lambda: r.api.set_preview_size("Alice", 640, 400)
    )
    with parked(r):
        assert r.api.set_preview_size("Alice", 500, 300)["applied"]
        assert r.api.set_preview_enabled(False)
        assert not r.host.runtime_enabled and r.host.is_running
        refused(edit())
    r.wait_state(
        lambda state: (
            state.eve == "stopped"
            and (
                state.companions == "active" if companions else state.pump == "stopped"
            )
        )
    )
    assert not r.moved
    saved = r.api._state.settings["preview"]["layouts"]
    assert (saved["Alice"]["w"], saved["Alice"]["h"]) == (500, 300)
    assert edit()["persisted"]
    r.layouts.flush()
    saved = r.api._state.settings["preview"]["layouts"]
    if command == "reset":
        assert saved == {} and r.host.layout_entries() == {}
    else:
        assert (saved["Alice"]["w"], saved["Alice"]["h"]) == (640, 400)
        assert r.host.layout_entries()["Alice"].rect == geometry.Rect(20, 30, 640, 400)
    assert not r.host.runtime_enabled and not r.moved
    assert r.host.is_running is companions


def test_hwnd_gap_primary_fifo_survives_revocation_and_later_failed_post(
    layout_api, monkeypatch
):
    entered, release = Event(), Event()
    hwnd_created, initialized = Event(), Event()

    def before_window():
        entered.set()
        assert release.wait(5)

    r = layout_api(before_window=before_window)
    initialize = r.host._init_companion_family
    post = r.native.PostMessageW

    def hold_initialization(libs):
        hwnd_created.set()
        assert initialized.wait(5)
        initialize(libs)

    monkeypatch.setattr(r.host, "_init_companion_family", hold_initialization)
    monkeypatch.setattr(
        r.native,
        "PostMessageW",
        lambda hwnd, msg, wp, lp: (
            0 if msg == win32.WM_APP_RESIZE_ALL else post(hwnd, msg, wp, lp)
        ),
    )
    r.runtime.set_companions(True, 1)
    assert entered.wait(5)
    try:
        assert r.api.set_preview_enabled(True)
        # The command was accepted without an HWND, so it cannot be rolled
        # back later just because a subsequent native wake fails.
        assert r.api.reset_preview_layouts()["applied"]
        release.set()
        assert hwnd_created.wait(5)
        refused(r.api.apply_preview_default_size())
        assert r.api.set_preview_enabled(False)
        initialized.set()
        r.wait_state(
            lambda state: state.companions == "active" and state.eve == "stopped"
        )
        assert r.api._state.settings["preview"]["layouts"] == {}
        assert r.runtime.shutdown(5)
    finally:
        release.set()
        initialized.set()
        if r.host._hwnd:
            post(r.host._hwnd, win32.WM_APP_RESIZE_ALL, r.host._eve_epoch, 0)


def test_hwnd_arriving_during_primary_admission_does_not_lose_accepted_reset(
    layout_api, monkeypatch
):
    entered, release, hwnd_created = Event(), Event(), Event()

    def before_window():
        entered.set()
        assert release.wait(5)

    r = layout_api(before_window=before_window)
    initialize = r.host._init_companion_family

    def note_hwnd(libs):
        hwnd_created.set()
        initialize(libs)

    class HeldAppend(deque):
        def append(self, value):
            # Payload insertion is inside the admission lock, but HWND creation
            # is not. Force that transition before admission can finish.
            release.set()
            assert hwnd_created.wait(5)
            super().append(value)

    monkeypatch.setattr(r.host, "_init_companion_family", note_hwnd)
    monkeypatch.setattr(r.host, "_primary_intents", HeldAppend())
    r.runtime.set_companions(True, 1)
    assert entered.wait(5)
    try:
        assert r.api.set_preview_enabled(True)
        assert r.api.reset_preview_layouts()["applied"]
        assert r.host._ready.wait(5)
        r.call(lambda: None)
        assert r.api._state.settings["preview"]["layouts"] == {}
        assert r.runtime.shutdown(5)
    finally:
        release.set()
        if r.host._hwnd:
            r.native.PostMessageW(
                r.host._hwnd, win32.WM_APP_RESET_LAYOUTS, r.host._eve_epoch, 0
            )


@pytest.mark.parametrize("first", ["reset", "resize"])
@pytest.mark.parametrize("second", ["reset", "resize", "enable"])
def test_offline_layout_transaction_reserves_against_concurrent_edit_or_enable(
    layout_api, monkeypatch, first, second
):
    r = layout_api()
    r.runtime.set_companions(True, 1)
    r.wait_state(lambda state: state.companions == "active")
    entered, release = Event(), Event()
    update = settings.update

    @contextmanager
    def held(document):
        with update(document) as doc:
            yield doc
            entered.set()
            assert release.wait(5)

    monkeypatch.setattr(settings, "update", held)
    commands = {
        "reset": r.api.reset_preview_layouts,
        "resize": lambda: r.api.set_preview_size("Alice", 640, 400),
        "enable": lambda: r.api.set_preview_enabled(True),
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(commands[first])
        assert entered.wait(5)
        try:
            two = pool.submit(commands[second])
            result = two.result(1)
            if second == "enable":
                assert result is False
            else:
                refused(result)
        finally:
            release.set()
        assert one.result(5)["persisted"]
    assert not r.host.runtime_enabled
    assert r.runtime.snapshot().companions == "active"
    saved = r.api._state.settings["preview"]["layouts"]
    if first == "reset":
        assert saved == {}
    else:
        assert saved["Alice"]["w"] == 640


def test_offline_character_size_cannot_overtake_accepted_live_reset(layout_api):
    r = layout_api()
    open_eve(r)
    # Alice has a saved placement but no discovered/open primary preview.
    r.call(lambda: (r.host._clients.clear(), r.host._windows.clear()))
    with parked(r):
        assert r.api.reset_preview_layouts()["applied"]
        refused(r.api.set_preview_size("Alice", 640, 400))
    r.call(lambda: None)
    r.layouts.flush()
    assert r.api._state.settings["preview"]["layouts"] == {}


def test_failed_middle_post_preserves_accepted_fifo_and_storage_on_quit(
    layout_api, monkeypatch
):
    r = layout_api()
    open_eve(r)
    post = r.native.PostMessageW
    failed = Event()

    def fail_once(hwnd, msg, wp, lp):
        if msg == win32.WM_APP_RESET_LAYOUTS and not failed.is_set():
            failed.set()
            return 0
        return post(hwnd, msg, wp, lp)

    monkeypatch.setattr(r.native, "PostMessageW", fail_once)
    try:
        with parked(r):
            assert r.api.set_preview_size("Alice", 500, 300)["applied"]
            refused(r.api.reset_preview_layouts())
            # The failed reset is not an accepted delimiter. Only these
            # admitted commands participate in the resize/reset/resize FIFO.
            assert r.api.set_preview_size("Alice", 640, 400)["applied"]
            assert r.api.reset_preview_layouts()["applied"]
            assert r.api.set_preview_size("Alice", 700, 450)["applied"]
            r.runtime.close_admission()
        assert r.runtime.shutdown(5)
        assert not r.moved and not r.host.is_running
        saved = r.api._state.settings["preview"]["layouts"]
        assert (saved["Alice"]["w"], saved["Alice"]["h"]) == (700, 450)
    finally:
        if r.host._hwnd:
            post(r.host._hwnd, win32.WM_APP_RESET_LAYOUTS, r.host._eve_epoch, 0)
