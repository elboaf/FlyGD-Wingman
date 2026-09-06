"""Temporary full-client DWM mirror and selection UI, on the preview pump only.

The non-layered picker owns a transparent layered selection overlay, not a
second thumbnail. Confirm closes that entire bundle before handing the exact
source facts to the coordinator, which may then spend the temporary slot on a
candidate. Discovery-session validity remains the coordinator's responsibility.
"""

import ctypes
import logging
from ctypes import wintypes

from PIL import Image, ImageDraw

from wingman.telemetry.model import RosterClient

from . import layered, win32
from .crops import MIN_SOURCE_SIZE, map_selection
from .geometry import Rect
from .thumbnail import Thumbnail
from .window import coalesce_moves

logger = logging.getLogger(__name__)
PICKER_CLASS = "WingmanPreviewCropPicker"
PICKER_MAX = (1200, 800)
_STYLE = (
    win32.WS_CAPTION | win32.WS_SYSMENU | win32.WS_THICKFRAME | win32.WS_CLIPCHILDREN
)
_EX_STYLE = win32.WS_EX_TOOLWINDOW | win32.WS_EX_TOPMOST
_USE, _CANCEL, _RESET, _STATUS = 1, 2, 100, 101
_TIMER = 1
_CLASS_REGISTERED = False
_PICKERS = {}
_HINT = "Drag across the mirror to select a region."
_MINIMUM = f"Select at least {MIN_SOURCE_SIZE[0]}x{MIN_SOURCE_SIZE[1]} source pixels."


def _ensure_class(libs):
    global _CLASS_REGISTERED
    if _CLASS_REGISTERED:
        return

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style", wintypes.UINT),
            ("lpfnWndProc", win32.wndproc_type()),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HANDLE),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
        ]

    proc = win32.wndproc_type()(_dispatch)
    cls = WNDCLASSW()
    cls.lpfnWndProc = proc
    cls.hInstance = libs.kernel32.GetModuleHandleW(None)
    cls.hCursor = libs.user32.LoadCursorW(None, ctypes.c_wchar_p(0x7F00))
    cls.hbrBackground = libs.gdi32.GetStockObject(4)  # BLACK_BRUSH, system-owned
    cls.lpszClassName = PICKER_CLASS
    _require(libs.user32.RegisterClassW(ctypes.byref(cls)), "RegisterClassW")
    # Failed registration retains neither a false success flag nor callbacks.
    win32._KEEPALIVE.append(proc)
    _CLASS_REGISTERED = True


def _dispatch(hwnd, msg, wparam, lparam):
    picker = _PICKERS.get(int(hwnd))
    if picker is not None:
        result = picker._on_message(msg, wparam, lparam)
        if result is not None:
            return result
    return win32.bind().user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def _require(result, operation):
    if not result:
        raise OSError(f"Crop picker {operation} failed")
    return result


def _client_size(libs, hwnd):
    rect = win32.RECT()
    _require(libs.user32.GetClientRect(hwnd, ctypes.byref(rect)), "GetClientRect")
    size = (rect.right - rect.left, rect.bottom - rect.top)
    _require(size[0] > 0 and size[1] > 0, "client area unavailable")
    return size


def _point(lparam):
    return ctypes.c_short(lparam & 0xFFFF).value, ctypes.c_short(
        (lparam >> 16) & 0xFFFF
    ).value


def _fit(size, maximum):
    scale = min(maximum[0] / size[0], maximum[1] / size[1])
    return max(1, int(size[0] * scale)), max(1, int(size[1] * scale))


def _in_work_area(rect, work):
    w, h = min(rect.w, work.w), min(rect.h, work.h)
    return Rect(
        min(max(rect.x, work.x), work.right - w),
        min(max(rect.y, work.y), work.bottom - h),
        w,
        h,
    )


def _render_overlay(size, selection, border):
    image = Image.new("RGBA", size, (0, 0, 0, 140))
    if selection is not None and selection.w > 0 and selection.h > 0:
        draw = ImageDraw.Draw(image)
        box = (selection.x, selection.y, selection.right - 1, selection.bottom - 1)
        draw.rectangle(box, fill=(0, 0, 0, 0))
        draw.rectangle(box, outline=(255, 180, 0, 255), width=border)
    return image


class CropPicker:
    """Pump-only. Native controls keep their names and OS keyboard semantics.

    ``process_dialog_message`` must run before the pump's Translate/Dispatch;
    a True result means Windows already dispatched it. No nested message loop,
    source placement, or settings write is performed here.
    """

    def __init__(self, libs, client, on_confirm, on_cancel):
        self._libs = libs
        self.client = client
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel
        self.hwnd = None
        self._overlay_hwnd = None
        self._controls = {}
        self._thumb = None
        self._font = None
        self._timer = None
        self._dpi = 96
        self._source_size = None
        self._picker_size = None
        self._ready = False
        self._completed = False
        self._default_button = _USE
        self._pending_cancel = None
        self._start = None
        self.destination = None
        self.selection = None
        self.status = _HINT

    @classmethod
    def create(
        cls, libs, client: RosterClient, monitor: Rect, *, on_confirm, on_cancel
    ):
        """Return a live picker or None, cancelling once on any creation failure.

        ``monitor`` is one actual display rectangle, not the virtual bounding
        box. A hidden seed HWND lets Windows supply that display's DPI and work
        area before fitting the real window including its nonclient chrome.
        """
        self = cls(libs, client, on_confirm, on_cancel)
        try:
            self._source_size = _client_size(libs, client.hwnd)
            _ensure_class(libs)
            self.hwnd = _require(
                libs.user32.CreateWindowExW(
                    _EX_STYLE,
                    PICKER_CLASS,
                    f"FlyGD Wingman crop - {client.character}",
                    _STYLE,
                    monitor.x + monitor.w // 2,
                    monitor.y + monitor.h // 2,
                    1,
                    1,
                    None,
                    None,
                    libs.kernel32.GetModuleHandleW(None),
                    None,
                ),
                "CreateWindowExW picker",
            )
            _PICKERS[int(self.hwnd)] = self
            self._dpi = _require(
                libs.user32.GetDpiForWindow(self.hwnd), "GetDpiForWindow"
            )
            work = self._work_area()
            pad, toolbar = self._px(12), self._px(80)
            chrome = self._outer_size((0, 0))
            space = (
                min(PICKER_MAX[0], work.w - chrome[0] - 2 * pad - self._px(40)),
                min(PICKER_MAX[1], work.h - chrome[1] - toolbar - pad - self._px(40)),
            )
            _require(min(space) > 0, "monitor too small")
            mw, mh = _fit(self._source_size, space)
            w, h = self._outer_size(
                (max(self._px(400), mw + 2 * pad), mh + toolbar + pad)
            )
            rect = _in_work_area(
                Rect(work.x + (work.w - w) // 2, work.y + (work.h - h) // 2, w, h), work
            )
            self._position(self.hwnd, rect)
            for ident, text in (
                (_RESET, "&Reset"),
                (_USE, "&Use region"),
                (_CANCEL, "&Cancel"),
                (_STATUS, ""),
            ):
                style = win32.WS_CHILD | win32.WS_VISIBLE
                if ident != _STATUS:
                    style |= win32.WS_TABSTOP
                if ident == _USE:
                    style |= win32.BS_DEFPUSHBUTTON
                self._controls[ident] = _require(
                    libs.user32.CreateWindowExW(
                        0,
                        "STATIC" if ident == _STATUS else "BUTTON",
                        text,
                        style,
                        0,
                        0,
                        1,
                        1,
                        self.hwnd,
                        ident,
                        libs.kernel32.GetModuleHandleW(None),
                        None,
                    ),
                    f"CreateWindowExW {text or 'status'}",
                )
            self._overlay_hwnd = _require(
                libs.user32.CreateWindowExW(
                    win32.WS_EX_LAYERED
                    | win32.WS_EX_TRANSPARENT
                    | win32.WS_EX_TOOLWINDOW
                    | win32.WS_EX_NOACTIVATE,
                    "STATIC",
                    "",
                    win32.WS_POPUP,
                    0,
                    0,
                    1,
                    1,
                    self.hwnd,
                    None,
                    libs.kernel32.GetModuleHandleW(None),
                    None,
                ),
                "CreateWindowExW overlay",
            )
            self._thumb = _require(
                Thumbnail.register(libs, self.hwnd, client.hwnd), "DwmRegisterThumbnail"
            )
            self._set_font()
            self._layout()
            self._timer = _require(
                libs.user32.SetTimer(self.hwnd, _TIMER, 250, None), "SetTimer"
            )
            self._ready = True
            libs.user32.ShowWindow(self.hwnd, win32.SW_SHOWNOACTIVATE)
            # Showing/positioning our HWND synchronously dispatches native
            # messages; a failed layout may already have closed the bundle.
            if self._completed:
                return None
            libs.user32.ShowWindow(self._overlay_hwnd, win32.SW_SHOWNOACTIVATE)
            _require(libs.user32.SetForegroundWindow(self.hwnd), "SetForegroundWindow")
            if self._completed:
                return None
            libs.user32.SetFocus(self.hwnd)
            _require(libs.user32.GetFocus() == self.hwnd, "SetFocus")
        except OSError as exc:
            self._fail(exc)
            return None
        return self

    def _px(self, logical):
        return max(1, round(logical * self._dpi / 96))

    def _work_area(self):
        monitor = self._libs.user32.MonitorFromWindow(
            self.hwnd, win32.MONITOR_DEFAULTTONEAREST
        )
        info = win32.MONITORINFO()
        info.cbSize = ctypes.sizeof(info)
        _require(
            monitor and self._libs.user32.GetMonitorInfoW(monitor, ctypes.byref(info)),
            "GetMonitorInfoW",
        )
        r = info.rcWork
        return Rect(r.left, r.top, r.right - r.left, r.bottom - r.top)

    def _outer_size(self, size):
        rect = win32.RECT(0, 0, *size)
        _require(
            self._libs.user32.AdjustWindowRectExForDpi(
                ctypes.byref(rect), _STYLE, False, _EX_STYLE, self._dpi
            ),
            "AdjustWindowRectExForDpi",
        )
        return rect.right - rect.left, rect.bottom - rect.top

    def _position(self, hwnd, rect):
        _require(
            self._libs.user32.SetWindowPos(hwnd, None, *rect, 0x0010 | 0x0004),
            "SetWindowPos",
        )

    def _set_font(self):
        font = _require(
            self._libs.gdi32.CreateFontW(
                -self._px(13),
                0,
                0,
                0,
                400,
                0,
                0,
                0,
                1,
                0,
                0,
                0,
                0,
                "Segoe UI",
            ),
            "CreateFontW",
        )
        old, self._font = self._font, font
        for ident in self._controls:
            self._libs.user32.SendDlgItemMessageW(
                self.hwnd, ident, win32.WM_SETFONT, font, 1
            )
        if old:
            self._libs.gdi32.DeleteObject(old)

    def _set_status(self, message):
        self.status = message
        _require(
            self._libs.user32.SetWindowTextW(self._controls[_STATUS], message),
            "SetWindowTextW",
        )
        valid = (
            self.selection is not None
            and map_selection(self.selection, self.destination, self._source_size)
            is not None
        )
        use = self._controls[_USE]
        # Disabling the focused Use button must not strand keyboard focus.
        if not valid and self._libs.user32.GetFocus() == use:
            self._libs.user32.SetFocus(self._controls[_RESET])
        self._libs.user32.EnableWindow(use, valid)

    def _layout(self, message=None):
        size = _client_size(self._libs, self.hwnd)
        source = _client_size(self._libs, self.client.hwnd)
        if source != self._source_size:
            message = "Client size changed. Select the region again."
        elif size != self._picker_size and self._picker_size is not None:
            message = "Picker size changed. Select the region again."
        self._source_size, self._picker_size = source, size
        if message:
            self._end_drag()
            self.selection = None
        pad, toolbar = self._px(12), self._px(80)
        area = Rect(
            pad, toolbar, max(1, size[0] - 2 * pad), max(1, size[1] - toolbar - pad)
        )
        w, h = _fit(source, (area.w, area.h))
        self.destination = Rect(
            area.x + (area.w - w) // 2, area.y + (area.h - h) // 2, w, h
        )
        button_w, button_h, gap = self._px(112), self._px(28), self._px(8)
        for index, ident in enumerate((_RESET, _USE, _CANCEL)):
            self._position(
                self._controls[ident],
                Rect(pad + index * (button_w + gap), pad, button_w, button_h),
            )
        self._position(
            self._controls[_STATUS],
            Rect(pad, self._px(48), max(1, size[0] - 2 * pad), self._px(28)),
        )
        hr = self._thumb.update(self.destination, source_rect=Rect(0, 0, *source))
        if hr:
            raise OSError(
                f"Crop picker DwmUpdateThumbnailProperties hr=0x{hr & 0xFFFFFFFF:08x}"
            )
        self._set_status(message or self.status)
        self._draw_selection()

    def _draw_selection(self):
        d = self.destination
        local = (
            None
            if self.selection is None
            else Rect(
                self.selection.x - d.x,
                self.selection.y - d.y,
                self.selection.w,
                self.selection.h,
            )
        )
        origin = win32.POINT(d.x, d.y)
        _require(
            self._libs.user32.ClientToScreen(self.hwnd, ctypes.byref(origin)),
            "ClientToScreen",
        )
        image = _render_overlay((d.w, d.h), local, self._px(2))
        _require(
            layered.push(self._libs, self._overlay_hwnd, image, origin.x, origin.y),
            "UpdateLayeredWindow",
        )

    def _end_drag(self, *, release=True):
        dragging, self._start = self._start is not None, None
        # Our ReleaseCapture also sends WM_CAPTURECHANGED. Clear the gesture
        # first, and never release the capture now belonging to another HWND.
        if dragging and release and self._libs.user32.GetCapture() == self.hwnd:
            self._libs.user32.ReleaseCapture()

    def _update_selection(self, current):
        d = self.destination
        left = max(d.x, min(self._start[0], current[0]))
        top = max(d.y, min(self._start[1], current[1]))
        right = min(d.right, max(self._start[0], current[0]))
        bottom = min(d.bottom, max(self._start[1], current[1]))
        self.selection = Rect(left, top, max(0, right - left), max(0, bottom - top))
        pixels = map_selection(self.selection, d, self._source_size)
        self._set_status(
            _MINIMUM
            if pixels is None
            else f"Region: {pixels.w}x{pixels.h} source pixels. Use region to keep it."
        )
        self._draw_selection()

    def _confirm(self):
        current_size = _client_size(self._libs, self.client.hwnd)
        if current_size != self._source_size:
            self._layout("Client size changed. Select the region again.")
            return
        pixels = (
            None
            if self.selection is None
            else map_selection(self.selection, self.destination, current_size)
        )
        if pixels is None:
            self._set_status(_MINIMUM)
            return
        # Copy the proposal before releasing capture/destruction can re-enter.
        proposal = self.client, pixels, current_size
        self._completed = True
        self._close_resources()
        self._on_confirm(*proposal)

    def cancel(self, reason="cancelled"):
        """Dismiss once; the coordinator also uses this for missing/renewed sessions."""
        if self._completed:
            self._notify_pending_cancel()
            return
        self._completed = True
        self._close_resources()
        self._on_cancel(reason)

    def _fail(self, exc):
        logger.warning(
            "Crop picker %r src=0x%x: %s", self.client.character, self.client.hwnd, exc
        )
        self.cancel(str(exc))

    def _close_resources(self, *, destroy_picker=True):
        self._ready = False
        self._end_drag()
        if self._timer is not None:
            timer, self._timer = self._timer, None
            self._libs.user32.KillTimer(self.hwnd, timer)
        if self._overlay_hwnd is not None:
            hwnd, self._overlay_hwnd = self._overlay_hwnd, None
            self._libs.user32.DestroyWindow(hwnd)
        controls, self._controls = self._controls, {}
        for hwnd in controls.values():
            self._libs.user32.DestroyWindow(hwnd)
        if self._font is not None:
            font, self._font = self._font, None
            self._libs.gdi32.DeleteObject(font)
        if self._thumb is not None:
            thumb, self._thumb = self._thumb, None
            thumb.close()
        if self.hwnd is not None and destroy_picker:
            hwnd, self.hwnd = self.hwnd, None
            _PICKERS.pop(int(hwnd), None)
            self._libs.user32.DestroyWindow(hwnd)

    def _notify_pending_cancel(self):
        if self._pending_cancel is not None:
            reason, self._pending_cancel = self._pending_cancel, None
            self._on_cancel(reason)

    def process_dialog_message(self, message: wintypes.MSG) -> bool:
        """Offer EVERY pump message until the terminal callback, even without HWND.

        True means consumed: skip normal Translate/Dispatch. An unsolicited
        native destruction defers its callback here so even DestroyWindow's
        final WndProc has returned before a candidate can reuse the slot.
        """
        self._notify_pending_cancel()
        return bool(
            self._ready
            and not self._completed
            and self._libs.user32.IsDialogMessageW(self.hwnd, ctypes.byref(message))
        )

    def _on_message(self, msg, wparam, lparam):
        if msg == win32.WM_NCDESTROY and self.hwnd is not None:
            _PICKERS.pop(int(self.hwnd), None)
            self.hwnd = None
            self._pending_cancel = "picker-destroyed"
            # Null HWND posts to THIS thread's queue, never another pump.
            if not self._libs.user32.PostMessageW(None, 0, 0, 0):
                logger.warning(
                    "Could not wake picker cancellation; awaiting next pump message"
                )
            return None  # DefWindowProc still frees its nonclient allocations.
        if not self._ready or self._completed:
            return None
        try:
            return self._handle_message(msg, wparam, lparam)
        except OSError as exc:
            self._fail(exc)
            return None

    def _handle_message(self, msg, wparam, lparam):
        if msg == win32.WM_DESTROY:
            self._completed = True
            self._close_resources(destroy_picker=False)
            return 0
        if msg == win32.DM_GETDEFID:
            return self._default_button | (0x534B << 16)  # DC_HASDEFID
        if msg == win32.DM_SETDEFID:
            if wparam in (_USE, _RESET, _CANCEL) and wparam != self._default_button:
                for ident, style in (
                    (self._default_button, 0),
                    (wparam, win32.BS_DEFPUSHBUTTON),
                ):
                    self._libs.user32.SendDlgItemMessageW(
                        self.hwnd, ident, win32.BM_SETSTYLE, style, 1
                    )
                self._default_button = wparam
            return 1
        if msg == win32.WM_CLOSE:
            self.cancel()
            return 0
        if msg == win32.WM_KEYDOWN:
            if wparam == win32.VK_ESCAPE:
                self.cancel()
                return 0
            if wparam == win32.VK_RETURN:
                return self._handle_message(win32.WM_COMMAND, self._default_button, 0)
        if msg == win32.WM_COMMAND and (wparam >> 16) == 0:
            ident = wparam & 0xFFFF
            if ident == _USE:
                self._confirm()
            elif ident == _CANCEL:
                self.cancel()
            elif ident == _RESET:
                self._end_drag()
                self.selection = None
                self._set_status(_HINT)
                self._draw_selection()
            else:
                return None
            return 0
        if msg in (win32.WM_CAPTURECHANGED, win32.WM_CANCELMODE):
            if self._start is not None:
                self._end_drag(release=msg != win32.WM_CAPTURECHANGED)
                self.selection = None
                self._set_status("Selection interrupted. Select the region again.")
                self._draw_selection()
            # DefWindowProc still owns native menu/capture cancellation.
            return None if msg == win32.WM_CANCELMODE else 0
        if msg == win32.WM_TIMER and wparam == _TIMER:
            if _client_size(self._libs, self.client.hwnd) != self._source_size:
                self._layout("Client size changed. Select the region again.")
            return 0
        if msg in (win32.WM_SIZE, win32.WM_MOVE):
            self._layout()
            return None
        if msg == win32.WM_DPICHANGED:
            self._dpi = wparam & 0xFFFF
            suggested = ctypes.cast(lparam, ctypes.POINTER(win32.RECT)).contents
            rect = Rect(
                suggested.left,
                suggested.top,
                suggested.right - suggested.left,
                suggested.bottom - suggested.top,
            )
            self._position(self.hwnd, _in_work_area(rect, self._work_area()))
            if self._completed:
                return 0
            self._set_font()
            self._layout("Picker size changed. Select the region again.")
            return 0
        if msg == win32.WM_GETMINMAXINFO:
            info = ctypes.cast(lparam, ctypes.POINTER(win32.MINMAXINFO)).contents
            work = self._work_area()
            w, h = self._outer_size((self._px(400), self._px(240)))
            info.ptMinTrackSize = win32.POINT(min(work.w, w), min(work.h, h))
            return 0
        if msg == win32.WM_LBUTTONDOWN:
            d = self.destination
            point = _point(lparam)
            if (
                self._start is None
                and d.x <= point[0] < d.right
                and d.y <= point[1] < d.bottom
            ):
                self._start = point
                self.selection = None
                self._set_status(_HINT)
                self._libs.user32.SetFocus(self.hwnd)
                self._libs.user32.SetCapture(self.hwnd)
                _require(self._libs.user32.GetCapture() == self.hwnd, "SetCapture")
                self._update_selection(point)
            return 0
        if msg == win32.WM_MOUSEMOVE and self._start is not None:
            lparam = coalesce_moves(self._libs.user32.PeekMessageW, self.hwnd, lparam)
            self._update_selection(_point(lparam))
            return 0
        if msg == win32.WM_LBUTTONUP and self._start is not None:
            self._update_selection(_point(lparam))
            self._end_drag()
            return 0
        return None
