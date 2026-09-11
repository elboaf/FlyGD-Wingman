"""An independent auxiliary mirror, never an EVE-preview mode.

All placement/show/capture calls target our registered destination. The source
HWND is used only for DWM registration; source activation belongs to the family,
which revalidates its complete immutable identity immediately before the click.
"""

import ctypes
import logging
from ctypes import wintypes

from . import win32
from .layout import Rect
from .thumbnail import Thumbnail
from .window import CLICK_PX, coalesce_moves, drag_target, resize_result

logger = logging.getLogger(__name__)
COMPANION_CLASS = "WingmanCompanionPreview"
_WINDOWS = {}
_CLASS_REGISTERED = False


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
    cls.lpszClassName = COMPANION_CLASS
    if not libs.user32.RegisterClassW(ctypes.byref(cls)):
        raise OSError("Companion window registration failed")
    win32._KEEPALIVE.append(proc)
    _CLASS_REGISTERED = True


def _dispatch(hwnd, msg, wparam, lparam):
    window = _WINDOWS.get(int(hwnd))
    if window is not None:
        result = window._on_message(msg, wparam, lparam)
        if result is not None:
            return result
    return win32.bind().user32.DefWindowProcW(hwnd, msg, wparam, lparam)


class CompanionWindow:
    def __init__(self, libs, binding, rect, source_rect, on_activate, on_geometry):
        self._libs = libs
        self.binding = binding
        self.rect = rect
        self.source_rect = source_rect
        self._on_activate = on_activate
        self._on_geometry = on_geometry
        self.hwnd = None
        self._thumb = None
        self.hidden = True
        self.failed = None
        self._mode = self._start = self._start_rect = None

    @classmethod
    def create(cls, libs, binding, rect, source_rect, *, on_activate, on_geometry):
        self = cls(libs, binding, rect, source_rect, on_activate, on_geometry)
        try:
            _ensure_class(libs)
            self.hwnd = (
                libs.user32.CreateWindowExW(
                    win32.WS_EX_TOOLWINDOW
                    | win32.WS_EX_NOACTIVATE
                    | win32.WS_EX_TOPMOST,
                    COMPANION_CLASS,
                    "FlyGD Wingman companion",
                    win32.WS_POPUP,
                    *rect,
                    None,
                    None,
                    libs.kernel32.GetModuleHandleW(None),
                    None,
                )
                or None
            )
            if self.hwnd is None:
                raise OSError("Companion destination unavailable")
            _WINDOWS[int(self.hwnd)] = self
            self._thumb = Thumbnail.register(libs, self.hwnd, binding.hwnd)
            if self._thumb is None or not self._thumb._handle.value:
                raise OSError("Source could not be captured")
            if not self._update():
                raise OSError("Source capture update failed")
        except OSError as exc:
            self.failed = str(exc)
            # A failed native release is still a real owner, not a None result.
            return None if self.close() else self
        return self

    def _update(self):
        if self._thumb is None:
            return False
        hr = self._thumb.update(
            Rect(0, 0, self.rect.w, self.rect.h),
            visible=not self.hidden,
            source_rect=self.source_rect,
        )
        if hr != 0:
            self.failed = "Source capture update failed"
            return False
        return True

    def move(self, rect: Rect, *, notify=False) -> None:
        if self.hwnd is None or self.failed or self.rect == rect:
            return
        if not self._libs.user32.SetWindowPos(self.hwnd, None, *rect, 0x0010 | 0x0004):
            self.failed = "Companion position could not be updated"
            return
        self.rect = rect
        if self._update() and notify:
            self._on_geometry(rect)

    def set_source_rect(self, rect: Rect | None) -> None:
        if rect != self.source_rect and self.hwnd is not None:
            self.source_rect = rect
            self._update()

    def set_hidden(self, hidden: bool, *, authorized=None) -> None:
        if self.hwnd is None or self.failed or hidden == self.hidden:
            return
        self.hidden = hidden
        if hidden:
            self._cancel_gesture()
            self._libs.user32.ShowWindow(self.hwnd, win32.SW_HIDE)
        if self._update() and not hidden:
            if authorized is not None and not authorized():
                self.hidden = True
                self._update()
                return
            self._libs.user32.ShowWindow(self.hwnd, win32.SW_SHOWNOACTIVATE)

    def close(self) -> bool:
        self._cancel_gesture()
        if self.hwnd is not None and not self.hidden:
            self.hidden = True
            self._libs.user32.ShowWindow(self.hwnd, win32.SW_HIDE)
        if self._thumb is not None:
            if self._libs.dwmapi.DwmUnregisterThumbnail(self._thumb._handle) != 0:
                return False
            self._thumb._handle = None
            self._thumb = None
        if self.hwnd is not None:
            hwnd = self.hwnd
            if not self._libs.user32.DestroyWindow(hwnd) and self._libs.user32.IsWindow(
                hwnd
            ):
                return False
            _WINDOWS.pop(int(hwnd), None)
            self.hwnd = None
        return True

    def _cancel_gesture(self, *, release=True):
        captured = self._mode is not None
        self._mode = self._start = self._start_rect = None
        if captured and release and self._libs.user32.GetCapture() == self.hwnd:
            self._libs.user32.ReleaseCapture()

    def _cursor(self):
        point = win32.POINT()
        return (
            (point.x, point.y)
            if self._libs.user32.GetCursorPos(ctypes.byref(point))
            else None
        )

    def _drag(self, point):
        if self._mode in ("left", "right"):
            dx, dy = point[0] - self._start[0], point[1] - self._start[1]
            if dx * dx + dy * dy < CLICK_PX * CLICK_PX:
                return
            self._mode = "move" if self._mode == "left" else "resize"
        if self._mode == "move":
            rect = drag_target(self._start, point, self._start_rect)
        else:
            source = self.source_rect or Rect(0, 0, *self.binding.client_size)
            rect = resize_result(
                self._start,
                point,
                self._start_rect,
                min_size=(32, 32),
                aspect=source.w / source.h,
                chrome=(0, 0),
            )
        self.move(rect, notify=True)

    def _on_message(self, msg, wparam, lparam):
        if msg in (win32.WM_CAPTURECHANGED, win32.WM_CANCELMODE):
            self._cancel_gesture(release=msg != win32.WM_CAPTURECHANGED)
            return 0
        if msg == win32.WM_CLOSE:
            return 0  # Only persisted disable/remove may retire a committed row.
        if msg == win32.WM_NCDESTROY:
            if self.hwnd is not None:
                _WINDOWS.pop(int(self.hwnd), None)
                self.hwnd = None
                self.failed = "Companion destination closed"
            return None
        if self.hidden or self.failed or self.hwnd is None:
            return None
        if msg in (win32.WM_LBUTTONDOWN, win32.WM_RBUTTONDOWN):
            if self._mode is None and (point := self._cursor()) is not None:
                self._mode = "left" if msg == win32.WM_LBUTTONDOWN else "right"
                self._start, self._start_rect = point, self.rect
                self._libs.user32.SetCapture(self.hwnd)
                if self._libs.user32.GetCapture() != self.hwnd:
                    self._cancel_gesture(release=False)
            return 0
        if msg == win32.WM_MOUSEMOVE and self._mode is not None:
            coalesce_moves(self._libs.user32.PeekMessageW, self.hwnd, lparam)
            if self._mode is not None and (point := self._cursor()) is not None:
                self._drag(point)
            return 0
        if msg in (win32.WM_LBUTTONUP, win32.WM_RBUTTONUP) and self._mode is not None:
            right = self._mode in ("right", "resize")
            point = self._cursor()
            if point is None or right != (msg == win32.WM_RBUTTONUP):
                self._cancel_gesture()
                return 0
            self._drag(point)
            click = self._mode == "left"
            self._cancel_gesture()
            if click:
                self._on_activate()
            return 0
        return None
