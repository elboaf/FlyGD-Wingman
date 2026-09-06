"""Production crop controller exercised through recorded, injected native calls."""

import pytest

from tests.test_preview_crop_windows import FakeLibs
from wingman.preview import win32
from wingman.preview.geometry import Rect
from wingman.telemetry.model import ClientSessionId, RosterClient

CLIENT = RosterClient(
    16, 101, "EVE - Alice", "Alice", ClientSessionId(16, 101, "Alice", 1)
)
SOURCE = Rect(100, 50, 400, 200)
DEST = Rect(20, 30, 320, 160)


def create(monkeypatch, libs=None, **kwargs):
    from wingman.preview import cropwindow

    monkeypatch.setattr(cropwindow, "_ensure_class", lambda libs: None)
    libs = libs or FakeLibs()
    attach_capture(libs)
    options = dict(
        hidden=False,
        locked=False,
        on_activate=lambda client: None,
        on_rect_changed=lambda rect: None,
        on_disable=lambda: None,
        on_failure=lambda reason: None,
    )
    options.update(kwargs)
    window = cropwindow.CropWindow.create(libs, CLIENT, SOURCE, DEST, **options)
    return window, libs


def test_candidate_is_created_without_showing(monkeypatch):
    from wingman.preview import cropwindow

    libs = FakeLibs()
    monkeypatch.setattr(cropwindow, "_ensure_class", lambda libs: None)
    window = cropwindow.CropWindow.create(
        libs,
        CLIENT,
        Rect(0, 0, 320, 180),
        Rect(20, 20, 320, 180),
        hidden=True,
        locked=False,
        on_activate=lambda client: None,
        on_rect_changed=lambda rect: None,
        on_disable=lambda: None,
        on_failure=lambda reason: None,
    )
    assert window is not None
    try:
        assert libs.user32.shows == []
        assert len(libs.dwmapi.updates) == 1
        assert all(not props.fVisible for props in libs.dwmapi.updates)
        assert libs.user32.created[0]["style"] == win32.WS_POPUP
    finally:
        window.close()


@pytest.mark.parametrize("phase,unregisters", [("register", 0), ("update", 1)])
def test_initial_dwm_failure_cleans_once_without_retry(
    monkeypatch, caplog, phase, unregisters
):
    from wingman.preview import cropwindow

    libs = FakeLibs(**{f"{phase}_hr": 0x80004005})
    failures = []
    window, _ = create(monkeypatch, libs, on_failure=failures.append)
    assert window is None
    assert libs.events.count("register") == unregisters
    assert libs.events.count("update") == unregisters
    assert libs.events.count("unregister") == unregisters
    assert libs.events.count("destroy-window") == 1
    assert libs.teardown_order == [("unregister",)] * unregisters + [
        ("destroy-window", 1000)
    ]
    assert libs.user32.shows == []
    assert 1000 not in cropwindow._WINDOWS
    assert len(failures) == 1
    for detail in ("Alice", "0x10", "0x80004005", str(SOURCE), str(DEST)):
        assert detail in failures[0]
        assert detail in caplog.text


def attach_capture(libs):
    libs.user32.capture_owner = None
    original_set = libs.user32.SetCapture
    original_release = libs.user32.ReleaseCapture

    def capture(hwnd):
        libs.user32.capture_owner = hwnd
        return original_set(hwnd)

    def release():
        libs.user32.capture_owner = None
        return original_release()

    libs.user32.SetCapture = capture
    libs.user32.ReleaseCapture = release
    libs.user32.GetCapture = lambda: libs.user32.capture_owner


@pytest.fixture
def live(monkeypatch):
    windows = []

    def make(**kwargs):
        window, libs = create(monkeypatch, **kwargs)
        assert window is not None
        windows.append(window)
        return window, libs

    yield make
    for window in windows:
        window.close()


def edges(rect):
    return rect.left, rect.top, rect.right, rect.bottom


def press(window, libs, *, right=False, at=(100, 100)):
    libs.user32.cursor = at
    window._on_message(win32.WM_RBUTTONDOWN if right else win32.WM_LBUTTONDOWN, 0, 0)


def release(window, *, right=False):
    window._on_message(win32.WM_RBUTTONUP if right else win32.WM_LBUTTONUP, 0, 0)


def menu_fake(libs, *, result=1, create_ok=True, append_ok=True):
    calls = []
    libs.user32.CreatePopupMenu = lambda: 0x123456789 if create_ok else None
    libs.user32.AppendMenuW = lambda *args: calls.append(("append", args)) or append_ok
    libs.user32.TrackPopupMenuEx = lambda *args: calls.append(("track", args)) or result
    libs.user32.DestroyMenu = lambda handle: calls.append(("destroy", handle)) or True
    return calls


def test_live_creation_keeps_full_session_and_nonactivating_styles(live):
    activated, changed = [], []
    window, libs = live(on_activate=activated.append, on_rect_changed=changed.append)
    assert window.client is CLIENT
    assert window.client.session == ClientSessionId(16, 101, "Alice", 1)
    assert libs.user32.created[0]["class_name"] == "WingmanPreviewCrop"
    assert libs.user32.created[0]["ex_style"] == (
        win32.WS_EX_TOPMOST | win32.WS_EX_TOOLWINDOW | win32.WS_EX_NOACTIVATE
    )
    assert libs.events == ["create-window", "register", "update", "show"]
    props = libs.dwmapi.updates[0]
    assert edges(props.rcSource) == (100, 50, 500, 250)
    assert edges(props.rcDestination) == (0, 0, 320, 160)
    assert props.fVisible and props.fSourceClientAreaOnly
    assert props.opacity == 255
    assert activated == changed == []


def test_move_and_resize_emit_current_destination_without_changing_source(live):
    changed = []
    window, libs = live(on_rect_changed=changed.append)
    window.move(Rect(-20, 0, 320, 160))
    assert len(libs.dwmapi.updates) == 1
    window.move(Rect(-20, 0, 640, 320))
    window.move(Rect(-20, 0, 640, 320))
    assert changed == [Rect(-20, 0, 320, 160), Rect(-20, 0, 640, 320)]
    assert libs.user32.positions == [(-20, 0, 320, 160), (-20, 0, 640, 320)]
    assert len(libs.dwmapi.updates) == 2
    assert edges(libs.dwmapi.updates[-1].rcSource) == (100, 50, 500, 250)
    assert edges(libs.dwmapi.updates[-1].rcDestination) == (0, 0, 640, 320)


def test_source_update_validates_current_client_bounds_and_updates_only_dwm(live):
    changed = []
    window, libs = live(on_rect_changed=changed.append)
    libs.user32.client_rect = (0, 0, 1600, 900)
    window.set_source_rect(Rect(50, 40, 800, 400))
    window.set_source_rect(Rect(50, 40, 800, 400))
    assert window.source_rect == Rect(50, 40, 800, 400)
    assert len(libs.dwmapi.updates) == 2
    assert edges(libs.dwmapi.updates[-1].rcSource) == (50, 40, 850, 440)
    assert libs.user32.positions == changed == []


@pytest.mark.parametrize(
    "source", [Rect(-1, 0, 20, 20), Rect(0, 0, 15, 20), Rect(1270, 0, 20, 20)]
)
def test_initial_invalid_source_never_allocates(monkeypatch, source):
    from wingman.preview import cropwindow

    libs = FakeLibs()
    failures = []
    monkeypatch.setattr(cropwindow, "_ensure_class", lambda libs: None)
    window = cropwindow.CropWindow.create(
        libs,
        CLIENT,
        source,
        DEST,
        hidden=True,
        locked=False,
        on_activate=lambda c: None,
        on_rect_changed=lambda r: None,
        on_disable=lambda: None,
        on_failure=failures.append,
    )
    assert window is None
    assert libs.events == []
    assert len(failures) == 1
    assert "Alice" in failures[0]


@pytest.mark.parametrize("bounds", [None, (0, 0, 0, 0), (0, 0, 100, 100)])
def test_source_update_after_client_loss_or_shrink_closes_without_bad_dwm(live, bounds):
    failures = []
    window, libs = live(on_failure=failures.append)
    libs.user32.client_rect = bounds
    window.set_source_rect(SOURCE)
    assert window.hwnd is None
    assert len(libs.dwmapi.updates) == 1
    assert len(failures) == 1
    assert libs.teardown_order == [("unregister",), ("destroy-window", 1000)]


def test_hide_and_show_update_thumbnail_visibility_idempotently(live):
    window, libs = live(hidden=True)
    window.move(Rect(10, 10, 400, 200))
    assert len(libs.dwmapi.updates) == 2
    assert all(not p.fVisible for p in libs.dwmapi.updates)
    assert libs.user32.shows == []
    window.set_hidden(False)
    window.set_hidden(False)
    assert libs.user32.shows == [(window.hwnd, win32.SW_SHOWNOACTIVATE)]
    assert libs.dwmapi.updates[-1].fVisible
    window.set_hidden(True)
    window.set_hidden(True)
    assert libs.user32.shows[-1] == (window.hwnd, win32.SW_HIDE)
    assert len(libs.dwmapi.updates) == 4
    assert not libs.dwmapi.updates[-1].fVisible


def test_locked_click_activates_once_on_down_without_capture(live):
    activated = []
    window, libs = live(locked=True, on_activate=activated.append)
    press(window, libs)
    release(window)
    assert activated == [CLIENT]
    assert libs.user32.captures == []


@pytest.mark.parametrize(
    "offset,expected,activations",
    [
        ((2, 2), DEST, 1),
        ((4, 0), Rect(24, 30, 320, 160), 0),
        ((30, 10), Rect(50, 40, 320, 160), 0),
    ],
)
def test_left_click_or_drag_uses_screen_radius(live, offset, expected, activations):
    activated = []
    window, libs = live(on_activate=activated.append)
    press(window, libs)
    libs.user32.cursor = (100 + offset[0], 100 + offset[1])
    window._on_message(win32.WM_MOUSEMOVE, 0, 0)
    release(window)
    assert window.rect == expected
    assert activated == [CLIENT] * activations


def test_release_position_cannot_turn_a_missed_mousemove_into_a_click(live):
    activated = []
    window, libs = live(on_activate=activated.append)
    press(window, libs)
    libs.user32.cursor = (130, 110)
    release(window)
    assert activated == []
    assert window.rect == Rect(50, 40, 320, 160)


def test_drag_coalesces_queued_moves_and_uses_latest_absolute_cursor(live):
    window, libs = live()
    press(window, libs)
    queued = [(120, 110), (140, 120)]

    def peek(ptr, hwnd, low, high, flags):
        assert hwnd == window.hwnd
        if not queued:
            return False
        libs.user32.cursor = queued.pop(0)
        ptr._obj.lParam = 0
        return True

    libs.user32.PeekMessageW = peek
    window._on_message(win32.WM_MOUSEMOVE, 0, 0)
    assert queued == []
    assert libs.user32.positions == [(60, 50, 320, 160)]


@pytest.mark.parametrize("locked", [False, True])
def test_stationary_right_click_opens_disable_menu_not_activation_or_deletion(
    live, locked
):
    disabled, activated = [], []
    window, libs = live(
        locked=locked,
        on_disable=lambda: disabled.append(True),
        on_activate=activated.append,
    )
    calls = menu_fake(libs)
    press(window, libs, right=True, at=(-100, 500))
    assert calls == []
    release(window, right=True)
    assert disabled == [True]
    assert activated == []
    assert window.hwnd == 1000
    assert libs.teardown_order == []
    assert calls == [
        ("append", (0x123456789, win32.MF_STRING, 1, "Disable crop")),
        (
            "track",
            (
                0x123456789,
                win32.TPM_RETURNCMD | win32.TPM_NONOTIFY,
                -100,
                500,
                1000,
                None,
            ),
        ),
        ("destroy", 0x123456789),
    ]
    assert libs.user32.capture_owner is None


@pytest.mark.parametrize("locked", [False, True])
def test_right_drag_does_not_open_menu_and_respects_lock(live, locked):
    window, libs = live(locked=locked)
    calls = menu_fake(libs)
    press(window, libs, right=True)
    libs.user32.cursor = (200, 120)
    window._on_message(win32.WM_MOUSEMOVE, 0, 0)
    release(window, right=True)
    assert window.rect == (DEST if locked else Rect(20, 30, 420, 210))
    assert calls == []


@pytest.mark.parametrize(
    "kwargs,call_names",
    [
        ({"result": 0}, ["append", "track", "destroy"]),
        ({"create_ok": False}, []),
        ({"append_ok": False}, ["append", "destroy"]),
    ],
)
def test_cancelled_or_failed_menu_keeps_crop_enabled_and_releases_menu(
    live, kwargs, call_names
):
    disabled = []
    window, libs = live(on_disable=lambda: disabled.append(True))
    calls = menu_fake(libs, **kwargs)
    press(window, libs, right=True)
    release(window, right=True)
    assert [call[0] for call in calls] == call_names
    assert disabled == []
    assert window.hwnd == 1000


def test_close_message_requests_disable_only_until_host_closes(live):
    disabled = []
    window, libs = live(on_disable=lambda: disabled.append(True))
    assert window._on_message(win32.WM_CLOSE, 0, 0) == 0
    assert disabled == [True]
    assert window.hwnd == 1000
    assert libs.teardown_order == []
    window.close()
    window.close()
    assert libs.teardown_order == [("unregister",), ("destroy-window", 1000)]


@pytest.mark.parametrize("action", ["lock", "hide", "cancel", "close"])
def test_cancellation_resets_before_synchronous_capture_changed(live, action):
    activated = []
    window, libs = live(on_activate=activated.append)
    press(window, libs)
    released = []

    def synchronous_release():
        released.append(True)
        assert window._mode is window._start is window._start_rect is None
        libs.user32.capture_owner = None
        window._on_message(win32.WM_CAPTURECHANGED, 0, 999)
        return True

    libs.user32.ReleaseCapture = synchronous_release
    if action == "lock":
        window.set_locked(True)
    elif action == "hide":
        window.set_hidden(True)
    elif action == "cancel":
        window._on_message(win32.WM_CANCELMODE, 0, 0)
    else:
        window.close()
    release(window)
    assert released == [True]
    assert activated == []


@pytest.mark.parametrize("notify", [True, False])
def test_capture_loss_never_releases_new_owners_capture(live, notify):
    activated = []
    window, libs = live(on_activate=activated.append)
    press(window, libs)
    libs.user32.capture_owner = 999
    if notify:
        window._on_message(win32.WM_CAPTURECHANGED, 0, 999)
    window.set_locked(True)
    release(window)
    assert libs.user32.capture_owner == 999
    assert libs.user32.captures == [("set", 1000)]
    assert activated == []


def test_second_button_does_not_reclassify_and_wrong_release_cancels(live):
    activated = []
    window, libs = live(on_activate=activated.append)
    press(window, libs, right=True)
    libs.user32.cursor = (130, 110)
    window._on_message(win32.WM_MOUSEMOVE, 0, 0)
    press(window, libs)
    assert window._mode == "resize"
    release(window, right=True)
    assert activated == []
    press(window, libs)
    release(window, right=True)
    assert window._mode is None
    assert activated == []


def test_hidden_and_closed_controllers_ignore_input_and_native_mutations(live):
    activated, disabled = [], []
    window, libs = live(
        hidden=True,
        on_activate=activated.append,
        on_disable=lambda: disabled.append(True),
    )
    press(window, libs)
    release(window)
    assert libs.user32.captures == []
    assert activated == []
    window.close()
    before = list(libs.events)
    window.move(Rect(0, 0, 900, 500))
    window.set_source_rect(Rect(0, 0, 100, 100))
    window.set_hidden(False)
    window.set_locked(True)
    window._on_message(win32.WM_CLOSE, 0, 0)
    press(window, libs)
    assert libs.events == before
    assert activated == disabled == []


def test_unexpected_destroy_unregisters_without_destroying_again(live):
    from wingman.preview import cropwindow

    window, libs = live()
    window._on_message(win32.WM_DESTROY, 0, 0)
    window.close()
    assert window.hwnd is None
    assert 1000 not in cropwindow._WINDOWS
    assert libs.teardown_order == [("unregister",)]


@pytest.mark.parametrize("hidden", [False, True])
def test_later_update_recovers_once_and_each_success_ends_the_episode(live, hidden):
    failures = []
    window, libs = live(hidden=hidden, on_failure=failures.append)
    original = libs.dwmapi.DwmUpdateThumbnailProperties
    outcomes = iter([0x80004005, 0, 0x80004005, 0])

    def update(handle, props):
        libs.dwmapi.update_hr = next(outcomes)
        return original(handle, props)

    libs.dwmapi.DwmUpdateThumbnailProperties = update
    window.move(Rect(20, 30, 400, 200))
    window.move(Rect(20, 30, 500, 250))
    assert window.hwnd == 1000
    assert failures == []
    assert libs.events.count("register") == 3
    assert libs.events.count("unregister") == 2
    assert len(libs.dwmapi.updates) == 5
    assert all(bool(p.fVisible) is not hidden for p in libs.dwmapi.updates)
    window.close()
    assert libs.events.count("unregister") == 3
    assert libs.events.count("destroy-window") == 1


@pytest.mark.parametrize(
    "phase,updates,unregisters", [("register", 2, 1), ("update", 3, 2)]
)
def test_failed_recovery_closes_before_contextual_callback_once(
    live, phase, updates, unregisters
):
    failures, changes = [], []
    window, libs = live(on_failure=failures.append, on_rect_changed=changes.append)
    libs.dwmapi.update_hr = 0x80004005
    if phase == "register":
        libs.dwmapi.register_hr = 0x80070006
    window.move(Rect(20, 30, 400, 200))
    assert window.hwnd is None
    window.move(Rect(20, 30, 500, 250))
    window.close()
    assert len(failures) == 1
    for detail in (
        "Alice",
        "0x10",
        str(SOURCE),
        "Rect(x=20, y=30, w=400, h=200)",
        "0x80004005",
    ):
        assert detail in failures[0]
    if phase == "register":
        assert "0x80070006" in failures[0]
    assert changes == []
    assert libs.events.count("update") == updates
    assert libs.events.count("unregister") == unregisters
    assert libs.events.count("destroy-window") == 1
    assert libs.teardown_order[-1] == ("destroy-window", 1000)


def test_failed_reveal_never_shows_a_candidate(live):
    window, libs = live(hidden=True)
    libs.dwmapi.update_hr = 0x80004005
    window.set_hidden(False)
    assert window.hwnd is None
    assert libs.user32.shows == []


@pytest.mark.parametrize("action", ["hide", "close"])
def test_menu_pump_cannot_disable_a_stale_window(live, action):
    disabled = []
    window, libs = live(on_disable=lambda: disabled.append(True))
    calls = menu_fake(libs)

    def track(*args):
        if action == "hide":
            window.set_hidden(True)
        else:
            window.close()
        return 1

    libs.user32.TrackPopupMenuEx = track
    press(window, libs, right=True)
    release(window, right=True)
    assert disabled == []
    assert calls[-1] == ("destroy", 0x123456789)


def test_activation_callback_can_close_after_gesture_reset(live):
    activated = []

    def activate(client):
        assert window._mode is window._start is window._start_rect is None
        assert libs.user32.capture_owner is None
        activated.append(client)
        window.close()

    window, libs = live(on_activate=activate)
    press(window, libs)
    release(window)
    assert activated == [CLIENT]
    assert libs.teardown_order == [("unregister",), ("destroy-window", 1000)]


def test_disable_callback_runs_after_menu_handle_is_released(live):
    disabled = []

    def disable():
        assert calls[-1] == ("destroy", 0x123456789)
        disabled.append(True)
        window.close()

    window, libs = live(on_disable=disable)
    calls = menu_fake(libs)
    press(window, libs, right=True)
    release(window, right=True)
    assert disabled == [True]
    assert libs.teardown_order == [("unregister",), ("destroy-window", 1000)]


def test_failure_callback_observes_resources_already_closed_and_can_reenter(live):
    failures = []

    def fail(reason):
        assert window.hwnd is None
        assert libs.teardown_order == [
            ("unregister",),
            ("unregister",),
            ("destroy-window", 1000),
        ]
        failures.append(reason)
        window.close()
        window.set_hidden(False)

    window, libs = live(on_failure=fail)
    libs.dwmapi.update_hr = 0x80004005
    window.move(Rect(20, 30, 400, 200))
    assert len(failures) == 1


def test_failed_native_move_does_not_publish_geometry(live):
    changes, failures = [], []
    window, libs = live(on_rect_changed=changes.append, on_failure=failures.append)
    libs.user32.SetWindowPos = lambda *args: False
    window.move(Rect(50, 50, 320, 160))
    assert changes == []
    assert len(failures) == 1
    assert window.hwnd is None


@pytest.mark.parametrize("phase", ["press", "move", "release"])
def test_cursor_read_failure_does_not_activate_or_jump(live, phase):
    activated = []
    window, libs = live(on_activate=activated.append)
    if phase != "press":
        press(window, libs)
    libs.user32.GetCursorPos = lambda ptr: False
    if phase == "press":
        press(window, libs)
    elif phase == "move":
        window._on_message(win32.WM_MOUSEMOVE, 0, 0)
    release(window)
    assert activated == []
    assert window.rect == DEST
    assert window._mode is None


@pytest.mark.parametrize("phase", ["class", "hwnd", "source"])
def test_initial_native_failure_creates_no_live_resources(monkeypatch, phase):
    from wingman.preview import cropwindow

    libs = FakeLibs()
    failures = []
    if phase == "hwnd":
        libs.user32.CreateWindowExW = lambda *args: None
    if phase == "source":
        libs.user32.client_rect = None

    def ensure(libs):
        raise OSError("Class unavailable")

    # create()'s test helper normally bypasses registration; call directly
    # here so the injected failure really exercises the class error path.
    monkeypatch.setattr(
        cropwindow, "_ensure_class", ensure if phase == "class" else lambda libs: None
    )
    window = cropwindow.CropWindow.create(
        libs,
        CLIENT,
        SOURCE,
        DEST,
        hidden=True,
        locked=False,
        on_activate=lambda c: None,
        on_rect_changed=lambda r: None,
        on_disable=lambda: None,
        on_failure=failures.append,
    )
    assert window is None
    assert libs.events == []
    assert len(failures) == 1


def test_registration_is_routable_before_dwm_and_unknown_messages_use_default(
    monkeypatch,
):
    from wingman.preview import cropwindow

    libs = FakeLibs(crops=cropwindow._WINDOWS)
    disabled = []
    window, _ = create(monkeypatch, libs, on_disable=lambda: disabled.append(True))
    try:
        assert libs.dwmapi.registry_present_at_register is True
        defaults = []
        libs.user32.DefWindowProcW = lambda *args: defaults.append(args) or 123
        monkeypatch.setattr(win32, "bind", lambda: libs)
        assert cropwindow._dispatch(window.hwnd, win32.WM_CLOSE, 0, 0) == 0
        assert disabled == [True]
        assert cropwindow._dispatch(window.hwnd, 0x4321, 12, 34) == 123
        assert cropwindow._dispatch(999, 0x4321, 56, 78) == 123
        assert defaults == [(1000, 0x4321, 12, 34), (999, 0x4321, 56, 78)]
    finally:
        window.close()


def test_only_destination_hwnd_is_moved_or_shown(live):
    window, libs = live()
    positions = []
    libs.user32.SetWindowPos = lambda *args: positions.append(args) or True
    window.move(Rect(-200, 40, 400, 200))
    window.set_hidden(True)
    window.set_hidden(False)
    assert positions == [(1000, None, -200, 40, 400, 200, 0x0014)]
    assert len(libs.user32.shows) == 3
    assert all(hwnd == 1000 and hwnd != CLIENT.hwnd for hwnd, cmd in libs.user32.shows)


def test_crop_client_geometry_safety_surface():
    """Extend the placement guard to every crop call, including future paths."""
    import ast
    import inspect

    from wingman.preview import cropwindow

    tree = ast.parse(inspect.getsource(cropwindow))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    dangerous = {
        "MoveWindow",
        "SetWindowPlacement",
        "ShowWindowAsync",
        "SetForegroundWindow",
        "SetFocus",
        "SendInput",
        "keybd_event",
        "mouse_event",
    }
    assert not dangerous.intersection(node.func.attr for node in calls)
    geometry_calls = [
        node for node in calls if node.func.attr in {"SetWindowPos", "ShowWindow"}
    ]
    assert geometry_calls
    assert all(ast.unparse(node.args[0]) == "self.hwnd" for node in geometry_calls)
    assert "tests.manual" not in inspect.getsource(cropwindow)
    assert cropwindow.CropWindow.__bases__ == (object,)
