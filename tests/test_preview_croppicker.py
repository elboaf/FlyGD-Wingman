"""Production picker, real mapping/DWM properties over injected native boundaries."""

import ctypes
import re
from ctypes import wintypes
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

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
        self.held_fonts = set()
        self.thumbnails = set()
        self.timers = set()
        self.next_hwnd = 1000
        self.next_font = 5000
        self.dc = {}
        self.dc_stack = []
        self.canvas = Image.new("RGB", (816, 600), "white")
        self.hit_test = 1
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

    def ScreenToClient(self, hwnd, pointer):
        if not self.attempt("screen-to-client", hwnd):
            return False
        pointer._obj.x -= self.origin[0]
        pointer._obj.y -= self.origin[1]
        return True

    def DefWindowProcW(self, hwnd, msg, wp, lp):
        self.attempt("default", hwnd, msg, wp, lp)
        return self.hit_test

    def InvalidateRect(self, hwnd, rect, erase):
        assert hwnd in self.windows
        return self.attempt("invalidate", hwnd, bool(erase))

    def GetStockObject(self, ident):
        assert ident == 18  # DC_BRUSH, system-owned and never deleted.
        return 6000 if self.attempt("stock-brush") else 0

    def SaveDC(self, hdc):
        if not self.attempt("save-dc", hdc):
            return 0
        self.dc_stack.append(self.dc.copy())
        return len(self.dc_stack)

    def RestoreDC(self, hdc, level):
        if not self.attempt("restore-dc", hdc, level):
            return False
        self.dc = self.dc_stack.pop()
        return True

    def SelectObject(self, hdc, handle):
        old = self.dc.get("font", 1)
        self.dc["font"] = handle
        return old

    def SetDCBrushColor(self, hdc, color):
        self.dc["brush"] = color
        return 0 if self.attempt("brush-color", hdc, color) else 0xFFFFFFFF

    def SetTextColor(self, hdc, color):
        self.dc["text"] = color
        return 0 if self.attempt("text-color", hdc, color) else 0xFFFFFFFF

    def SetBkColor(self, hdc, color):
        self.dc["background"] = color
        return 0 if self.attempt("background-color", hdc, color) else 0xFFFFFFFF

    def SetBkMode(self, hdc, mode):
        self.dc["mode"] = mode
        return 2 if self.attempt("background-mode", hdc, mode) else 0

    def FillRect(self, hdc, pointer, brush):
        assert brush == 6000
        r = pointer._obj
        color = self.dc["brush"]
        ImageDraw.Draw(self.canvas).rectangle(
            (r.left, r.top, r.right - 1, r.bottom - 1),
            fill=(color & 255, color >> 8 & 255, color >> 16 & 255),
        )
        return self.attempt("fill", hdc, edges(r), color)

    def DrawTextW(self, hdc, text, length, pointer, flags):
        return self.attempt("draw-text", hdc, text, flags, self.dc.copy())

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
        pointer._obj.top -= 30 if style & win32.WS_CAPTION else 8
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
        handle = self.next_font
        self.next_font += 1
        self.fonts.add(handle)
        return handle

    def DeleteObject(self, handle):
        self.attempt("delete-font", handle)
        if handle in self.held_fonts or any(
            dc.get("font") == handle for dc in [self.dc, *self.dc_stack]
        ):
            return False  # GDI cannot delete an object still selected in a DC.
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
    assert picker.destination == Rect(12, 127, 792, 445)
    props = native.updates[-1]
    assert edges(props.rcSource) == (0, 0, 1280, 720)
    assert edges(props.rcDestination) == (12, 127, 804, 572)
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
    assert (x, y) == (-1788, 27)


def test_confirm_tears_down_entire_slot_before_callback_and_preserves_size(make):
    confirmed, cancelled = [], []
    native = Native()

    def confirm(*args):
        native.assert_closed()
        confirmed.append(args)
        picker.cancel("reentrant")

    picker, _ = make(native, on_confirm=confirm, on_cancel=cancelled.append)
    drag(picker)
    assert native.controls[1]["enabled"]
    picker._on_message(win32.WM_COMMAND, 1, 0)
    picker.cancel("late")
    assert confirmed == [(CLIENT, Rect(0, 0, 640, 360), (1280, 720))]
    assert cancelled == []
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
    picker._on_message(win32.WM_LBUTTONDOWN, 0, packed(20, 150))
    picker._on_message(msg, key, 0)
    picker.cancel("again")
    assert len(cancelled) == 1
    assert [e[0] for e in native.events].count("release") == 1


def test_reset_small_selection_and_enter_without_region_stay_open(make):
    confirmed = []
    picker, native = make(on_confirm=lambda *args: confirmed.append(args))
    picker._on_message(win32.WM_KEYDOWN, win32.VK_RETURN, 0)
    drag(picker, (30, 150), (31, 151))
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
    drag(picker, (408, 349), (-10, -10))
    assert picker.selection == Rect(12, 127, 396, 222)
    image = native.layers[-1][1]
    assert image.getpixel((10, 10))[3] == 0
    assert image.getpixel((790, 440))[3] > 0


@pytest.mark.parametrize("message", [0x0215, 0x001F])
def test_capture_loss_discards_partial_drag_and_keeps_os_default(make, message):
    picker, native = make()
    picker._on_message(win32.WM_LBUTTONDOWN, 0, packed(20, 150))
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
    assert picker.destination == Rect(170, 112, 476, 476)
    drag(picker, (170, 112), (408, 350))
    picker._on_message(win32.WM_COMMAND, 1, 0)
    assert confirmed == [(CLIENT, Rect(0, 0, 500, 500), (1000, 1000))]


def test_picker_resize_and_dpi_change_clear_selection_and_move_only_owned_hwnds(make):
    picker, native = make()
    drag(picker)
    native.picker_size = (1000, 700)
    picker._on_message(win32.WM_SIZE, 0, 0)
    assert picker.selection is None and "Picker size changed" in picker.status
    assert picker.destination == Rect(12, 125, 976, 549)
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
        "create-FlyGD Wingman crop - Alice",
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
    drag(picker, (13, 128), (331, 306))
    picker._on_message(win32.WM_COMMAND, 1, 0)
    assert confirmed == [(CLIENT, Rect(1, 1, 515, 289), (1280, 720))]


def test_minimum_tracking_size_includes_chrome_without_overwriting_os_maximum(make):
    picker, _ = make()
    info = win32.MINMAXINFO()
    info.ptMaxTrackSize = win32.POINT(8000, 4000)
    picker._on_message(win32.WM_GETMINMAXINFO, 0, ctypes.addressof(info))
    assert (info.ptMinTrackSize.x, info.ptMinTrackSize.y) == (416, 288)
    assert (info.ptMaxTrackSize.x, info.ptMaxTrackSize.y) == (8000, 4000)


def test_dialog_default_button_changes_keep_owner_draw_style_and_enter_contract(make):
    picker, native = make()
    assert picker._on_message(0x0401, 100, 0) == 1  # DM_SETDEFID
    assert picker._on_message(win32.DM_GETDEFID, 0, 0) == 100 | (0x534B << 16)
    # BM_SETSTYLE would turn BS_OWNERDRAW back into a light stock button.
    assert not [e for e in native.events if e[0] == "send" and e[3] == 0x00F4]
    assert [e for e in native.events if e[0] == "invalidate"][-2:] == [
        ("invalidate", native.controls[1]["hwnd"], True),
        ("invalidate", native.controls[100]["hwnd"], True),
    ]
    drag(picker)
    picker._on_message(win32.WM_KEYDOWN, win32.VK_RETURN, 0)
    assert picker.selection is None  # Enter invokes Reset, the new default.


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
    picker._on_message(win32.WM_LBUTTONDOWN, 0, packed(12, 127))
    picker._on_message(win32.WM_MOUSEMOVE, 0, packed(408, 349))
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
    picker._on_message(win32.WM_LBUTTONDOWN, 0, packed(20, 150))
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


@pytest.mark.parametrize(
    "interrupt",
    ["capture", "cancelmode", "resize", "source-resize", "cancel", "new-drag"],
)
def test_coalescing_does_not_update_an_interrupted_or_replaced_drag(make, interrupt):
    picker, native = make()
    point = packed(20, 150)
    picker._on_message(win32.WM_LBUTTONDOWN, 0, point)
    after_interrupt = []

    def peek(*args):
        # PeekMessage dispatches nonqueued messages even with a mouse filter.
        if interrupt == "capture":
            native.capture = None
            picker._on_message(win32.WM_CAPTURECHANGED, 0, 9999)
        elif interrupt == "cancelmode":
            picker._on_message(win32.WM_CANCELMODE, 0, 0)
        elif interrupt == "resize":
            native.picker_size = (1000, 700)
            picker._on_message(win32.WM_SIZE, 0, 0)
        elif interrupt == "source-resize":
            native.source_size = (1000, 1000)
            picker._on_message(win32.WM_TIMER, 1, 0)
        elif interrupt == "cancel":
            picker.cancel("nested-cancel")
        else:
            picker._on_message(win32.WM_CANCELMODE, 0, 0)
            # Same coordinates, different gesture: equality is not identity.
            picker._on_message(win32.WM_LBUTTONDOWN, 0, point)
        after_interrupt.append(
            (picker.selection, len(native.layers), len(native.events))
        )
        return False

    native.PeekMessageW = peek
    picker._on_message(win32.WM_MOUSEMOVE, 0, packed(300, 300))
    assert (
        picker.selection,
        len(native.layers),
        len(native.events),
    ) == after_interrupt[0]
    assert not native.controls[1]["enabled"] or interrupt == "cancel"


@pytest.mark.parametrize(
    "phase", ["picker-show", "overlay-show", "foreground", "focus"]
)
def test_initial_native_destruction_drains_cancel_after_native_return(make, phase):
    from wingman.preview import croppicker

    native = Native()
    cancelled, destroyed = [], []
    inside_native = False

    def destroy_picker():
        picker = next(iter(croppicker._PICKERS.values()))
        hwnd = picker.hwnd
        picker._on_message(win32.WM_DESTROY, 0, 0)
        picker._on_message(win32.WM_NCDESTROY, 0, 0)
        assert cancelled == []
        del native.windows[hwnd]  # Native parent destruction completes here.
        destroyed.append(picker)

    def wrap(name, target):
        original = getattr(native, name)

        def call(hwnd, *args):
            nonlocal inside_native
            assert hwnd in native.windows, "creation touched a destroyed handle"
            inside_native = True
            result = original(hwnd, *args)
            if target == phase or (
                name == "ShowWindow" and phase == native.windows[hwnd] + "-show"
            ):
                destroy_picker()
            inside_native = False
            return result

        setattr(native, name, call)

    wrap("ShowWindow", "show")
    wrap("SetForegroundWindow", "foreground")
    wrap("SetFocus", "focus")

    def cancel(reason):
        assert not inside_native
        native.assert_closed()
        cancelled.append(reason)

    picker, _ = make(native, on_cancel=cancel)
    assert picker is None
    assert cancelled == ["picker-destroyed"]
    assert len(destroyed) == 1
    destroyed[0].cancel("again")
    assert cancelled == ["picker-destroyed"]


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


def draw_button(picker, native, ident, state):
    item = win32.DRAWITEMSTRUCT()
    item.CtlType, item.CtlID = 4, ident  # ODT_BUTTON
    item.hwndItem = native.controls[ident]["hwnd"]
    item.hDC = 7000
    item.rcItem = win32.RECT(0, 0, 112, 28)
    item.itemState = state
    return picker._on_message(0x002B, ident, ctypes.addressof(item))


def test_caption_replaces_light_stock_chrome_but_keeps_native_controls(make):
    picker, native = make()
    style = native.created[0][3]
    assert not style & win32.WS_CAPTION
    assert style & win32.WS_THICKFRAME
    assert not style & (win32.WS_SYSMENU | 0x00020000 | 0x00010000)
    assert native.controls[102]["text"] == native.created[0][2]
    for _, cls, text, style, _, _, ident in native.created[1:]:
        if ident in (1, 2, 100):
            assert cls == "BUTTON" and text.startswith("&")
            assert style & win32.WS_TABSTOP
            assert style & 0xF == 0xB  # BS_OWNERDRAW alone, not DEFPUSHBUTTON
        elif ident in (101, 102):
            assert cls == "STATIC" and not style & win32.WS_TABSTOP
            assert style & 0x80  # SS_NOPREFIX: character names can contain '&'.
    picker._on_message(win32.WM_LBUTTONDOWN, 0, packed(20, 20))
    assert picker.selection is None and native.capture is None


@pytest.mark.parametrize("native_hit", [1, 10, 11, 12, 13, 14, 15, 16, 17])
def test_caption_hit_test_preserves_native_resize_edges_at_negative_origin(
    make, native_hit
):
    picker, native = make()
    native.hit_test = native_hit
    location = packed(native.origin[0] + 20, native.origin[1] + 20)
    assert picker._on_message(0x0084, 0, location) == (
        2 if native_hit == 1 else native_hit
    )
    native.hit_test = 1
    below_caption = packed(native.origin[0] + 20, native.origin[1] + 44)
    assert picker._on_message(0x0084, 0, below_caption) == 1
    # A caption double click must not create an unadvertised maximize path.
    assert picker._on_message(0x00A3, 2, location) == 0


def test_native_erase_and_static_messages_paint_token_surfaces(make):
    picker, native = make()
    assert picker._on_message(0x0014, 7000, 0) == 1  # WM_ERASEBKGND
    assert native.canvas.getpixel((0, 40)) == (12, 13, 16)  # --bg
    assert native.canvas.getpixel((0, 10)) == (18, 16, 22)  # --titlebar-bottom
    for ident, background, text in (
        (101, 0x100D0C, 0xB1A29A),
        (102, 0x161012, 0xEDEAE8),
    ):
        assert picker._on_message(0x0138, 7000, native.controls[ident]["hwnd"]) == 6000
        assert native.dc["background"] == native.dc["brush"] == background
        assert native.dc["text"] == text


@pytest.mark.parametrize(
    "ident,state,fill,text",
    [
        (100, 0, (33, 29, 40), 0xD6CDC8),
        (100, 1, (42, 38, 52), 0xD6CDC8),  # ODS_SELECTED
        (1, 0, (132, 48, 217), 0xFFFFFF),
        (1, 1, (122, 31, 200), 0xFFFFFF),
        (1, 4, (12, 13, 16), 0x92847D),  # ODS_DISABLED
    ],
)
def test_native_button_paint_covers_stock_surface_and_restores_dc(
    make, ident, state, fill, text
):
    picker, native = make()
    before = native.dc.copy()
    assert draw_button(picker, native, ident, state) == 1
    assert native.canvas.getpixel((56, 14)) == fill
    drawn = [e for e in native.events if e[0] == "draw-text"][-1]
    assert drawn[2] == native.controls[ident]["text"]
    assert drawn[4]["text"] == text and drawn[4]["font"] in native.fonts
    assert native.dc == before and not native.dc_stack


@pytest.mark.parametrize(
    "state,focused,hide_accel", [(0x10, True, False), (0x310, False, True)]
)
def test_owner_draw_honors_native_keyboard_focus_and_mnemonic_cues(
    make, state, focused, hide_accel
):
    picker, native = make()
    assert draw_button(picker, native, 100, state) == 1
    assert (native.canvas.getpixel((1, 1)) == (201, 156, 255)) == focused
    drawn = [e for e in native.events if e[0] == "draw-text"][-1]
    assert bool(drawn[3] & 0x00100000) == hide_accel  # DT_HIDEPREFIX


@pytest.mark.parametrize("ident", [1, 2, 100])
def test_dialog_default_query_and_enter_follow_focused_owner_draw_button(make, ident):
    confirmed, cancelled = [], []
    picker, native = make(
        on_confirm=lambda *a: confirmed.append(a), on_cancel=cancelled.append
    )
    drag(picker)
    native.SetFocus(native.controls[ident]["hwnd"])
    # Owner-draw and DEFPUSHBUTTON are mutually exclusive. Dialog Enter must
    # resolve the focused native button without requiring a style conversion.
    assert picker._on_message(win32.DM_GETDEFID, 0, 0) == ident | (0x534B << 16)
    picker._on_message(win32.WM_KEYDOWN, win32.VK_RETURN, 0)
    if ident == 1:
        assert len(confirmed) == 1 and not cancelled
    elif ident == 2:
        assert cancelled == ["cancelled"] and not confirmed
    else:
        assert picker.hwnd and picker.selection is None
        assert not confirmed and not cancelled


@pytest.mark.parametrize(
    "phase",
    [
        "save-dc",
        "restore-dc",
        "stock-brush",
        "brush-color",
        "fill",
        "text-color",
        "background-mode",
        "draw-text",
    ],
)
def test_paint_failure_cancels_and_attempts_dc_restoration(make, phase):
    cancelled = []
    picker, native = make(on_cancel=cancelled.append)
    native.fail = phase
    draw_button(picker, native, 100, 0)
    native.assert_closed()
    assert len(cancelled) == 1
    restores = [event for event in native.events if event[0] == "restore-dc"]
    assert len(restores) == (0 if phase == "save-dc" else 1)
    # A failed RestoreDC cannot prove restoration of the Windows-owned DC.
    if phase != "restore-dc":
        assert not native.dc_stack


def test_selected_font_delete_failure_waits_for_native_paint_unwind(make):
    cancelled = []
    native = Native()

    def cancel(reason):
        native.assert_closed()
        cancelled.append(reason)

    picker, _ = make(native, on_cancel=cancel)
    font = picker._font
    native.held_fonts.add(font)  # An enclosing native control still owns its DC.
    native.fail = "restore-dc"
    draw_button(picker, native, 100, 0)
    assert cancelled == []
    assert picker._fonts == native.fonts == {font}
    assert not native.windows and not native.thumbnails and not native.timers
    # The next pump turn follows EndPaint/ReleaseDC in the native caller.
    native.held_fonts.clear()
    native.dc.clear()
    native.dc_stack.clear()
    picker.process_dialog_message(wintypes.MSG())
    native.assert_closed()
    assert len(cancelled) == 1
    picker.cancel("again")
    picker.process_dialog_message(wintypes.MSG())
    assert len(cancelled) == 1


@pytest.mark.parametrize("entry", ["creation", "dpi", "stop"])
def test_font_cleanup_after_enclosing_native_call_preserves_callback_once(make, entry):
    from wingman.preview import croppicker

    native = Native()
    cancelled = []
    retained = []

    def cancel(reason):
        native.assert_closed()
        cancelled.append(reason)

    def paint_then_return(*args):
        picker = next(iter(croppicker._PICKERS.values()))
        retained.append(picker)
        native.held_fonts.update(native.fonts)
        if entry == "stop":
            picker.cancel("stopping")
        else:
            native.fail = "restore-dc"
            draw_button(picker, native, 100, 0)
        assert not cancelled
        assert picker._fonts == native.fonts and native.fonts
        native.held_fonts.clear()
        native.dc.clear()
        native.dc_stack.clear()
        return True

    if entry == "creation":
        native.SetForegroundWindow = paint_then_return
        picker, _ = make(native, on_cancel=cancel)
        assert picker is None
    else:
        picker, _ = make(native, on_cancel=cancel)
        native.SendDlgItemMessageW = paint_then_return
        picker._set_font()
        picker.cancel("stopping")
    native.assert_closed()
    assert len(cancelled) == 1
    retained[0].cancel("again")
    assert len(cancelled) == 1


@pytest.mark.parametrize(
    "entry", ["layout", "status", "font", "drag-status", "drag-focus"]
)
def test_nested_owner_draw_failure_cannot_continue_using_closed_controls(make, entry):
    cancelled = []
    native = Native()

    def cancel(reason):
        native.assert_closed()  # Including both fonts during a DPI replacement.
        cancelled.append(reason)

    picker, _ = make(native, on_cancel=cancel)
    call_name = {
        "layout": "SetWindowPos",
        "status": "SetWindowTextW",
        "font": "SendDlgItemMessageW",
        "drag-status": "SetWindowTextW",
        "drag-focus": "SetFocus",
    }[entry]
    original = getattr(native, call_name)

    def paint(*args):
        result = original(*args)
        native.fail = "draw-text"
        draw_button(picker, native, 100, 0)
        return result

    setattr(native, call_name, paint)
    if entry.startswith("drag-"):
        picker._on_message(win32.WM_LBUTTONDOWN, 0, packed(20, 150))
    elif entry == "font":
        suggested = win32.RECT(-1800, -100, -800, 600)
        picker._on_message(win32.WM_DPICHANGED, 144, ctypes.addressof(suggested))
    else:
        picker._on_message(win32.WM_SIZE, 0, 0)
    native.assert_closed()
    assert len(cancelled) == 1


@pytest.mark.parametrize("state,gap", [(0, 1), (0x10, 2)])
def test_accent_button_ring_has_dark_gap_for_focus_contrast(make, state, gap):
    picker, native = make()
    assert draw_button(picker, native, 1, state) == 1
    # --focus-ring against --brand is only 2.84:1. A --bg gap makes both
    # adjacent sides of the ring 8.96:1 without inventing a brighter colour.
    assert native.canvas.getpixel((0, 0)) == (201, 156, 255)
    assert native.canvas.getpixel((gap, gap)) == (12, 13, 16)
    assert native.canvas.getpixel((gap + 1, gap + 1)) == (132, 48, 217)


@pytest.mark.parametrize(
    "foreground,background,minimum",
    [
        ("text", "titlebar-bottom", 4.5),
        ("text-dim", "bg", 4.5),
        ("text-btn", "control", 4.5),
        ("text-btn", "control-hover", 4.5),
        ("text-faint", "bg", 4.5),
        ("on-accent", "brand", 4.5),
        ("on-accent", "acc-bottom", 4.5),
        ("focus-ring", "bg", 3),
    ],
)
def test_picker_text_and_focus_token_pairs_meet_contrast_floor(
    foreground, background, minimum
):
    from wingman.preview import croppicker

    def luminance(rgb):
        channels = [v / 255 for v in rgb]
        linear = [
            v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
            for v in channels
        ]
        return sum(v * weight for v, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    low, high = sorted(
        luminance(croppicker._RGB[token]) for token in (foreground, background)
    )
    assert (high + 0.05) / (low + 0.05) >= minimum


def test_native_picker_tokens_are_asserted_against_authoritative_css():
    from wingman.preview import croppicker

    css = (Path(__file__).parents[1] / "wingman/web/style.css").read_text()
    root = css.split(":root {", 1)[1].split("}", 1)[0]
    tokens = dict(re.findall(r"--([\w-]+):\s*(#[a-fA-F0-9]+);", root))
    for token, color in croppicker._THEME.items():
        assert color == tokens[token], token


def test_selection_overlay_uses_the_existing_focus_token():
    from wingman.preview import croppicker

    image = croppicker._render_overlay((100, 100), Rect(10, 10, 50, 50), 2)
    assert image.getpixel((10, 10)) == (201, 156, 255, 255)


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
