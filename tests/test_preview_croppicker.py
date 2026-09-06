"""Production picker, real mapping/DWM properties over injected native boundaries."""

import ctypes
from ctypes import wintypes
from types import SimpleNamespace

import pytest

from wingman.preview import win32
from wingman.preview.crops import map_selection
from wingman.preview.geometry import Rect
from wingman.telemetry.model import ClientSessionId, RosterClient

CLIENT = RosterClient(
    16, 101, "EVE - Alice", "Alice", ClientSessionId(16, 101, "Alice", 7)
)
MONITOR = Rect(-1920, -200, 1920, 1040)


def edges(rect):
    return rect.left, rect.top, rect.right, rect.bottom


def packed(x, y):
    return (x & 0xFFFF) | ((y & 0xFFFF) << 16)


class Native:
    """Every attempted allocation is recorded, even a failed registration."""

    def __init__(self, fail=None):
        self.fail = fail
        self.events = []
        self.windows = {}
        self.controls = {}
        self.source_size = (1280, 720)
        self.picker_size = (816, 600)
        self.origin = (-1800, -100)
        self.dpi = 96
        self.capture = None
        self.focus = None
        self.updates = []
        self.layers = []
        self.created = []
        self.fonts = set()
        self.thumbnails = set()
        self.timers = set()
        self.next_hwnd = 1000
        self.lib = SimpleNamespace(
            user32=self,
            dwmapi=self,
            gdi32=self,
            kernel32=SimpleNamespace(GetModuleHandleW=lambda _: 1),
        )

    def attempt(self, name, *args):
        self.events.append((name, *args))
        return self.fail != name

    def GetClientRect(self, hwnd, pointer):
        self.events.append(("read-size", hwnd))
        size = self.source_size if hwnd == CLIENT.hwnd else self.picker_size
        if not size or self.fail == "read-size":
            return False
        pointer._obj.left = pointer._obj.top = 0
        pointer._obj.right, pointer._obj.bottom = size
        return True

    def CreateWindowExW(
        self, ex, cls, text, style, x, y, w, h, parent, menu, instance, param
    ):
        name = (
            "picker"
            if parent is None
            else "overlay"
            if style & win32.WS_POPUP
            else text
        )
        self.created.append((ex, cls, text, style, Rect(x, y, w, h), parent, menu))
        if not self.attempt("create-" + name):
            return 0
        hwnd = self.next_hwnd
        self.next_hwnd += 1
        self.windows[hwnd] = name
        if name not in ("picker", "overlay"):
            self.controls[menu] = dict(hwnd=hwnd, text=text, enabled=True)
        return hwnd

    def DestroyWindow(self, hwnd):
        assert hwnd != CLIENT.hwnd
        self.attempt("destroy", hwnd)
        assert hwnd in self.windows, "double destroy"
        del self.windows[hwnd]
        return True

    def DwmRegisterThumbnail(self, dest, source, pointer):
        assert source == CLIENT.hwnd and dest in self.windows
        if not self.attempt("register", dest, source):
            return 0x80004005
        pointer._obj.value = 9000
        self.thumbnails.add(9000)
        return 0

    def DwmUpdateThumbnailProperties(self, handle, pointer):
        if not self.attempt("update"):
            return 0x80004005
        self.updates.append(
            win32.DWM_THUMBNAIL_PROPERTIES.from_buffer_copy(pointer._obj)
        )
        return 0

    def DwmUnregisterThumbnail(self, handle):
        self.attempt("unregister")
        self.thumbnails.remove(handle.value)
        return 0

    def ShowWindow(self, hwnd, mode):
        assert hwnd != CLIENT.hwnd
        self.attempt("show", hwnd, mode)
        return False  # previous visibility, NOT failure

    def SetWindowPos(self, hwnd, after, x, y, w, h, flags):
        assert hwnd != CLIENT.hwnd
        return self.attempt("position", hwnd, Rect(x, y, w, h), flags)

    def ClientToScreen(self, hwnd, pointer):
        if not self.attempt("client-to-screen", hwnd):
            return False
        pointer._obj.x += self.origin[0]
        pointer._obj.y += self.origin[1]
        return True

    def MonitorFromWindow(self, hwnd, flags):
        return 100 if self.attempt("monitor", hwnd, flags) else 0

    def GetMonitorInfoW(self, handle, pointer):
        if not self.attempt("monitor-info"):
            return False
        pointer._obj.rcWork = win32.RECT(-1920, -200, 0, 840)
        return True

    def GetDpiForWindow(self, hwnd):
        return self.dpi if self.attempt("dpi", hwnd) else 0

    def AdjustWindowRectExForDpi(self, pointer, style, menu, ex, dpi):
        if not self.attempt("adjust", dpi):
            return False
        pointer._obj.left -= 8
        pointer._obj.top -= 30
        pointer._obj.right += 8
        pointer._obj.bottom += 8
        return True

    def SetWindowTextW(self, hwnd, text):
        return self.attempt("text", hwnd, text)

    def EnableWindow(self, hwnd, enabled):
        for control in self.controls.values():
            if control["hwnd"] == hwnd:
                control["enabled"] = bool(enabled)
        self.attempt("enable", hwnd, bool(enabled))
        return False  # previous disabled state, NOT failure

    def SetForegroundWindow(self, hwnd):
        assert hwnd != CLIENT.hwnd
        return self.attempt("foreground", hwnd)

    def SetFocus(self, hwnd):
        assert hwnd != CLIENT.hwnd
        self.attempt("focus", hwnd)
        self.focus = None if self.fail == "focus" else hwnd
        # None is valid previous focus, not a failure indicator.

    def GetFocus(self):
        return self.focus

    def SetCapture(self, hwnd):
        self.capture = None if self.fail == "capture" else hwnd
        self.attempt("capture", hwnd)

    def GetCapture(self):
        return self.capture

    def ReleaseCapture(self):
        self.capture = None
        self.attempt("release")
        from wingman.preview import croppicker

        for picker in list(croppicker._PICKERS.values()):
            picker._on_message(win32.WM_CAPTURECHANGED, 0, 0)
        return True

    def SetTimer(self, hwnd, ident, ms, callback):
        if not self.attempt("timer", hwnd, ident):
            return 0
        self.timers.add((hwnd, ident))
        return ident

    def KillTimer(self, hwnd, ident):
        self.timers.discard((hwnd, ident))
        return self.attempt("kill-timer")

    def CreateFontW(self, *args):
        if not self.attempt("font", *args):
            return 0
        handle = 5000 + len(self.fonts)
        self.fonts.add(handle)
        return handle

    def DeleteObject(self, handle):
        self.attempt("delete-font", handle)
        self.fonts.remove(handle)
        return True

    def SendDlgItemMessageW(self, parent, ident, *args):
        assert self.windows[parent] == "picker"
        self.attempt("send", parent, ident, *args)
        return 0

    def IsDialogMessageW(self, hwnd, pointer):
        self.attempt("dialog", hwnd, pointer._obj.message)
        return True

    def PostMessageW(self, *args):
        return self.attempt("post", *args)

    def PeekMessageW(self, *args):
        return False

    def push(self, libs, hwnd, image, x, y):
        self.layers.append((hwnd, image, x, y))
        return self.attempt("layer")

    def assert_closed(self):
        assert not self.windows
        assert not self.thumbnails
        assert not self.fonts
        assert not self.timers
        assert self.capture is None


@pytest.fixture
def make(monkeypatch):
    from wingman.preview import croppicker

    pickers = []
    monkeypatch.setattr(croppicker, "_ensure_class", lambda libs: None)

    def factory(native=None, **options):
        native = native or Native()
        monkeypatch.setattr(croppicker.layered, "push", native.push)
        defaults = dict(on_confirm=lambda *args: None, on_cancel=lambda reason: None)
        defaults.update(options)
        picker = croppicker.CropPicker.create(native.lib, CLIENT, MONITOR, **defaults)
        if picker:
            pickers.append(picker)
        return picker, native

    yield factory
    for picker in pickers:
        picker.cancel("test-finished")
    assert not croppicker._PICKERS


def drag(picker, start=None, end=None):
    d = picker.destination
    start = start or (d.x, d.y)
    end = end or (d.x + d.w // 2, d.y + d.h // 2)
    picker._on_message(win32.WM_LBUTTONDOWN, 0, packed(*start))
    picker._on_message(win32.WM_MOUSEMOVE, 0, packed(*end))
    picker._on_message(win32.WM_LBUTTONUP, 0, packed(*end))


def test_toolbar_offset_is_removed_before_mapping():
    assert map_selection(
        Rect(20, 60, 320, 180), Rect(20, 60, 640, 360), (1280, 720)
    ) == Rect(0, 0, 640, 360)


@pytest.mark.parametrize(
    "selection,want",
    [
        (Rect(21, 61, 318, 178), Rect(2, 2, 636, 356)),
        (Rect(339, 239, -318, -178), Rect(2, 2, 636, 356)),
        (Rect(-100, -100, 1000, 1000), Rect(0, 0, 1280, 720)),
    ],
)
def test_actual_mapping_covers_all_edges(selection, want):
    assert map_selection(selection, Rect(20, 60, 640, 360), (1280, 720)) == want


def test_creation_uses_full_client_mirror_controls_and_focus_before_click(make):
    picker, native = make()
    assert picker.client is CLIENT
    ex, cls, title, style, rect, owner, _ = native.created[0]
    assert cls == "WingmanPreviewCropPicker" and owner is None
    assert "Alice" in title and "Wingman" in title
    assert style & 0x00040000  # WS_THICKFRAME
    assert not style & (0x00020000 | 0x00010000)  # min/max boxes
    assert not ex & (win32.WS_EX_LAYERED | win32.WS_EX_NOACTIVATE)
    assert MONITOR.x <= rect.x and rect.right <= MONITOR.right
    assert MONITOR.y <= rect.y and rect.bottom <= MONITOR.bottom
    assert picker.destination == Rect(12, 111, 792, 445)
    props = native.updates[-1]
    assert edges(props.rcSource) == (0, 0, 1280, 720)
    assert edges(props.rcDestination) == (12, 111, 804, 556)
    assert props.fSourceClientAreaOnly and props.fVisible
    assert native.controls[1]["text"] == "&Use region"
    assert not native.controls[1]["enabled"]
    assert native.controls[2]["text"] == "&Cancel"
    assert native.controls[100]["text"] == "&Reset"
    assert native.focus == picker.hwnd
    assert ("foreground", picker.hwnd) in native.events
    overlay, image, x, y = native.layers[-1]
    assert native.windows[overlay] == "overlay"
    assert image.size == (792, 445)
    assert (x, y) == (-1788, 11)


def test_confirm_tears_down_entire_slot_before_callback_and_preserves_size(make):
    confirmed = []
    native = Native()

    def confirm(*args):
        native.assert_closed()
        confirmed.append(args)
        picker.cancel("reentrant")

    picker, _ = make(native, on_confirm=confirm)
    drag(picker)
    assert native.controls[1]["enabled"]
    picker._on_message(win32.WM_COMMAND, 1, 0)
    picker.cancel("late")
    assert confirmed == [(CLIENT, Rect(0, 0, 640, 360), (1280, 720))]
    names = [e[0] for e in native.events]
    assert names.count("register") == names.count("unregister") == 1
    assert max(
        i for i, e in enumerate(native.events) if e[0] == "destroy" and e[1] != 1000
    ) < names.index("unregister")
    assert native.events[names.index("unregister") + 1] == ("destroy", 1000)


@pytest.mark.parametrize("msg,key", [(0x0100, 0x1B), (0x0010, 0), (0x0111, 2)])
def test_cancel_paths_cleanup_once_before_callback(make, msg, key):
    cancelled = []
    native = Native()

    def cancel(reason):
        native.assert_closed()
        cancelled.append(reason)

    picker, _ = make(native, on_cancel=cancel)
    picker._on_message(win32.WM_LBUTTONDOWN, 0, packed(20, 120))
    picker._on_message(msg, key, 0)
    picker.cancel("again")
    assert len(cancelled) == 1
    assert [e[0] for e in native.events].count("release") == 1


def test_reset_small_selection_and_enter_without_region_stay_open(make):
    confirmed = []
    picker, native = make(on_confirm=lambda *args: confirmed.append(args))
    picker._on_message(win32.WM_KEYDOWN, win32.VK_RETURN, 0)
    drag(picker, (30, 120), (31, 121))
    assert not native.controls[1]["enabled"]
    assert "16x16" in picker.status
    picker._on_message(win32.WM_KEYDOWN, win32.VK_RETURN, 0)
    assert not confirmed and picker.hwnd
    drag(picker)
    picker._on_message(win32.WM_COMMAND, 100, 0)
    assert picker.selection is None
    assert not native.controls[1]["enabled"]
    drag(picker)
    picker._on_message(win32.WM_KEYDOWN, win32.VK_RETURN, 0)
    assert len(confirmed) == 1


@pytest.mark.parametrize("point", [(30, 10), (30, 100), (810, 300)])
def test_press_in_toolbar_or_letterbox_never_starts_selection(make, point):
    picker, native = make()
    picker._on_message(win32.WM_LBUTTONDOWN, 0, packed(*point))
    assert native.capture is None
    assert picker.selection is None


def test_reverse_drag_past_negative_client_origin_clamps_and_overlay_has_hole(make):
    picker, native = make()
    drag(picker, (408, 333), (-10, -10))
    assert picker.selection == Rect(12, 111, 396, 222)
    image = native.layers[-1][1]
    assert image.getpixel((10, 10))[3] == 0
    assert image.getpixel((790, 440))[3] > 0


@pytest.mark.parametrize("message", [0x0215, 0x001F])
def test_capture_loss_discards_partial_drag_and_keeps_os_default(make, message):
    picker, native = make()
    picker._on_message(win32.WM_LBUTTONDOWN, 0, packed(20, 120))
    picker._on_message(win32.WM_MOUSEMOVE, 0, packed(300, 300))
    native.capture = 9999
    result = picker._on_message(message, 0, 9999)
    assert result == (None if message == 0x001F else 0)
    assert native.capture == 9999
    assert not native.controls[1]["enabled"]
    assert picker.selection is None
    native.capture = None


@pytest.mark.parametrize("trigger", ["timer", "confirm", "move"])
def test_source_resize_clears_selection_and_refreshes_source_authority(make, trigger):
    confirmed = []
    picker, native = make(on_confirm=lambda *args: confirmed.append(args))
    drag(picker)
    native.source_size = (1000, 1000)
    if trigger == "timer":
        picker._on_message(win32.WM_TIMER, 1, 0)
    elif trigger == "confirm":
        picker._on_message(win32.WM_COMMAND, 1, 0)
    else:
        picker._on_message(win32.WM_MOVE, 0, 0)
    assert picker.hwnd and not confirmed
    assert picker.selection is None and not native.controls[1]["enabled"]
    assert picker.status == "Client size changed. Select the region again."
    assert edges(native.updates[-1].rcSource) == (0, 0, 1000, 1000)
    assert picker.destination == Rect(154, 80, 508, 508)
    drag(picker, (154, 80), (408, 334))
    picker._on_message(win32.WM_COMMAND, 1, 0)
    assert confirmed == [(CLIENT, Rect(0, 0, 500, 500), (1000, 1000))]


def test_picker_resize_and_dpi_change_clear_selection_and_move_only_owned_hwnds(make):
    picker, native = make()
    drag(picker)
    native.picker_size = (1000, 700)
    picker._on_message(win32.WM_SIZE, 0, 0)
    assert picker.selection is None and "Picker size changed" in picker.status
    assert picker.destination == Rect(12, 109, 976, 549)
    drag(picker)
    native.dpi = 192
    native.origin = (-1850, -150)
    suggested = win32.RECT(-2000, -300, -500, 700)
    picker._on_message(
        win32.WM_DPICHANGED, 192 | (192 << 16), ctypes.addressof(suggested)
    )
    assert picker.selection is None
    positions = [e for e in native.events if e[0] == "position" and e[1] == picker.hwnd]
    assert positions[-1][2] == Rect(-1920, -200, 1500, 1000)
    assert len(native.fonts) == 1  # old DPI font released
    assert all(
        e[1] != CLIENT.hwnd
        for e in native.events
        if e[0] in ("position", "focus", "show", "foreground")
    )


def test_dialog_message_seam_delegates_translation_once_and_is_inert_after_close(make):
    picker, native = make()
    msg = wintypes.MSG()
    msg.hWnd = picker.hwnd
    msg.message = win32.WM_KEYDOWN
    msg.wParam = 9
    assert picker.process_dialog_message(msg)
    assert ("dialog", picker.hwnd, win32.WM_KEYDOWN) in native.events
    assert picker._on_message(win32.DM_GETDEFID, 0, 0) == 1 | (0x534B << 16)
    picker.cancel("closed")
    assert not picker.process_dialog_message(msg)


@pytest.mark.parametrize(
    "phase",
    [
        "read-size",
        "create-picker",
        "create-&Reset",
        "create-&Use region",
        "create-&Cancel",
        "create-",
        "create-overlay",
        "register",
        "update",
        "position",
        "client-to-screen",
        "font",
        "timer",
        "adjust",
        "monitor-info",
        "monitor",
        "dpi",
        "text",
        "layer",
        "foreground",
        "focus",
    ],
)
def test_every_partial_creation_failure_cleans_once_without_registration_retry(
    make, phase
):
    native = Native(fail=phase)
    cancelled = []
    picker, _ = make(native, on_cancel=cancelled.append)
    assert picker is None
    native.assert_closed()
    assert len(cancelled) == 1
    attempts = [e for e in native.events if e[0] == "register"]
    assert len(attempts) <= 1
    if phase == "register":
        assert len(attempts) == 1  # a failed call still counts
    assert [e[0] for e in native.events].count("unregister") <= 1


@pytest.mark.parametrize("size", [None, (0, 720), (1280, 0)])
def test_source_unavailable_at_confirmation_cancels_without_proposal(make, size):
    confirmed, cancelled = [], []
    picker, native = make(
        on_confirm=lambda *a: confirmed.append(a), on_cancel=cancelled.append
    )
    drag(picker)
    native.source_size = size
    picker._on_message(win32.WM_COMMAND, 1, 0)
    native.assert_closed()
    assert confirmed == [] and len(cancelled) == 1


def test_fractional_mapping_confirms_floor_left_top_and_ceil_right_bottom(make):
    confirmed = []
    picker, _ = make(on_confirm=lambda *args: confirmed.append(args))
    drag(picker, (13, 112), (331, 290))
    picker._on_message(win32.WM_COMMAND, 1, 0)
    assert confirmed == [(CLIENT, Rect(1, 1, 515, 289), (1280, 720))]


def test_minimum_tracking_size_includes_chrome_without_overwriting_os_maximum(make):
    picker, _ = make()
    info = win32.MINMAXINFO()
    info.ptMaxTrackSize = win32.POINT(8000, 4000)
    picker._on_message(win32.WM_GETMINMAXINFO, 0, ctypes.addressof(info))
    assert (info.ptMinTrackSize.x, info.ptMinTrackSize.y) == (416, 278)
    assert (info.ptMaxTrackSize.x, info.ptMaxTrackSize.y) == (8000, 4000)


def test_dialog_default_button_changes_keep_native_style_and_enter_contract(make):
    picker, native = make()
    assert picker._on_message(0x0401, 100, 0) == 1  # DM_SETDEFID
    assert picker._on_message(win32.DM_GETDEFID, 0, 0) == 100 | (0x534B << 16)
    sends = [e for e in native.events if e[0] == "send" and e[3] == 0x00F4]
    assert sends[-2:] == [
        ("send", picker.hwnd, 1, 0x00F4, 0, 1),
        ("send", picker.hwnd, 100, 0x00F4, 1, 1),
    ]


@pytest.mark.parametrize(
    "phase", ["update", "position", "client-to-screen", "layer", "font"]
)
def test_runtime_native_failure_closes_all_resources_and_cancels_once(make, phase):
    cancelled = []
    picker, native = make(on_cancel=cancelled.append)
    native.fail = phase
    if phase == "font":
        suggested = win32.RECT(-1800, -100, -800, 600)
        picker._on_message(win32.WM_DPICHANGED, 144, ctypes.addressof(suggested))
    else:
        native.picker_size = (1000, 700)
        picker._on_message(win32.WM_SIZE, 0, 0)
    native.assert_closed()
    assert len(cancelled) == 1
    picker.cancel("again")
    assert len(cancelled) == 1


def test_external_destroy_releases_children_then_defers_cancel_until_pump_resumes(make):
    cancelled = []
    native = Native()

    def cancel(reason):
        native.assert_closed()
        cancelled.append(reason)

    picker, _ = make(native, on_cancel=cancel)
    hwnd = picker.hwnd
    picker._on_message(win32.WM_DESTROY, 0, 0)
    assert native.windows == {hwnd: "picker"}
    assert not native.thumbnails and not native.fonts
    assert cancelled == []
    picker._on_message(win32.WM_NCDESTROY, 0, 0)
    del native.windows[hwnd]  # DestroyWindow returns to the pump after WM_NCDESTROY.
    assert cancelled == []
    assert not picker.process_dialog_message(wintypes.MSG())
    assert cancelled == ["picker-destroyed"]
    picker.cancel("again")
    assert len(cancelled) == 1
    assert ("destroy", hwnd) not in native.events  # no recursive parent destruction


def test_confirm_during_capture_releases_before_closing_and_notifies_once(make):
    confirmed = []
    picker, native = make(on_confirm=lambda *args: confirmed.append(args))
    picker._on_message(win32.WM_LBUTTONDOWN, 0, packed(12, 111))
    picker._on_message(win32.WM_MOUSEMOVE, 0, packed(408, 333))
    picker._on_message(win32.WM_COMMAND, 1, 0)
    native.assert_closed()
    assert confirmed == [(CLIENT, Rect(0, 0, 640, 360), (1280, 720))]
    names = [e[0] for e in native.events]
    assert names.index("release") < names.index("destroy") < names.index("unregister")


def test_dispatch_preserves_default_processing_for_cancelmode(make, monkeypatch):
    from wingman.preview import croppicker

    picker, native = make()
    defaults = []
    native.DefWindowProcW = lambda *args: defaults.append(args) or 123
    monkeypatch.setattr(win32, "bind", lambda: native.lib)
    assert croppicker._dispatch(picker.hwnd, win32.WM_CANCELMODE, 0, 0) == 123
    assert defaults == [(picker.hwnd, win32.WM_CANCELMODE, 0, 0)]


def test_failed_capture_does_not_leave_an_unguarded_selection_drag(make):
    cancelled = []
    picker, native = make(on_cancel=cancelled.append)
    native.fail = "capture"
    picker._on_message(win32.WM_LBUTTONDOWN, 0, packed(20, 120))
    native.assert_closed()
    assert len(cancelled) == 1


def test_dpi_position_reentry_cannot_allocate_after_resize_failure_closes_picker(make):
    cancelled = []
    picker, native = make(on_cancel=cancelled.append)
    original = native.SetWindowPos

    def position(hwnd, *args):
        result = original(hwnd, *args)
        if hwnd == picker.hwnd:
            native.fail = "update"
            picker._on_message(win32.WM_SIZE, 0, 0)
        return result

    native.SetWindowPos = position
    suggested = win32.RECT(-1800, -100, -800, 600)
    picker._on_message(win32.WM_DPICHANGED, 144, ctypes.addressof(suggested))
    native.assert_closed()
    assert len(cancelled) == 1


def test_initial_show_reentry_failure_returns_none_without_touching_closed_handles(
    make,
):
    from wingman.preview import croppicker

    native = Native()
    original = native.ShowWindow
    cancelled = []

    def show(hwnd, mode):
        assert hwnd in native.windows
        result = original(hwnd, mode)
        if native.windows[hwnd] == "picker":
            native.fail = "update"
            croppicker._PICKERS[hwnd]._on_message(win32.WM_SIZE, 0, 0)
        return result

    native.ShowWindow = show
    picker, _ = make(native, on_cancel=cancelled.append)
    assert picker is None
    native.assert_closed()
    assert len(cancelled) == 1


@pytest.mark.parametrize("size", [None, (0, 720), (1280, 0)])
def test_initial_bad_client_size_allocates_nothing_and_notifies_once(make, size):
    native = Native()
    native.source_size = size
    cancelled = []
    picker, _ = make(native, on_cancel=cancelled.append)
    assert picker is None and len(cancelled) == 1
    assert native.created == []
    native.assert_closed()


def test_class_failure_is_cancelled_by_factory_before_native_allocation(
    make, monkeypatch
):
    from wingman.preview import croppicker

    def fail(libs):
        raise OSError("RegisterClassW failed")

    monkeypatch.setattr(croppicker, "_ensure_class", fail)
    cancelled = []
    picker, native = make(on_cancel=cancelled.append)
    assert picker is None and len(cancelled) == 1
    assert native.created == []
    native.assert_closed()


def test_class_registration_failure_is_retryable_without_accumulating_callbacks(
    monkeypatch,
):
    from wingman.preview import croppicker

    calls = []
    callback = ctypes.CFUNCTYPE(
        win32.LRESULT, wintypes.HWND, wintypes.UINT, win32.WPARAM, win32.LPARAM
    )
    monkeypatch.setattr(win32, "wndproc_type", lambda: callback)
    monkeypatch.setattr(croppicker, "_CLASS_REGISTERED", False)
    monkeypatch.setattr(win32, "_KEEPALIVE", [])
    outcomes = iter([0, 1])

    def register(pointer):
        calls.append(pointer._obj)
        return next(outcomes)

    libs = SimpleNamespace(
        user32=SimpleNamespace(
            RegisterClassW=register,
            LoadCursorW=lambda *a: 1,
            GetStockObject=lambda *a: 4,
        ),
        kernel32=SimpleNamespace(GetModuleHandleW=lambda _: 1),
        gdi32=SimpleNamespace(GetStockObject=lambda *a: 4),
    )
    with pytest.raises(OSError, match="RegisterClassW"):
        croppicker._ensure_class(libs)
    assert not croppicker._CLASS_REGISTERED
    assert not win32._KEEPALIVE
    croppicker._ensure_class(libs)
    croppicker._ensure_class(libs)
    assert len(calls) == 2 and len(win32._KEEPALIVE) == 1
