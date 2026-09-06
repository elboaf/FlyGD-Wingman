"""One independent crop HWND and DWM relationship, owned by the preview pump.

Only callbacks cross into host policy: activation, destination persistence,
transactional disable, and runtime failure. No primary-preview state or probe
runtime is shared; only its narrow geometry/queue helpers are reused.
"""

import ctypes
import logging
from ctypes import wintypes

from wingman.telemetry.model import RosterClient

from . import win32
from .crops import MIN_SOURCE_SIZE, source_from_pixels
from .geometry import Rect
from .thumbnail import Thumbnail
from .window import CLICK_PX, coalesce_moves, drag_target, resize_result

logger = logging.getLogger(__name__)
CROP_CLASS = "WingmanPreviewCrop"
_DISABLE_CROP = 1
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
    win32._KEEPALIVE.append(proc)
    cls = WNDCLASSW()
    cls.lpfnWndProc = proc
    cls.hInstance = libs.kernel32.GetModuleHandleW(None)
    cls.lpszClassName = CROP_CLASS
    cls.hCursor = libs.user32.LoadCursorW(None, ctypes.c_wchar_p(0x7F00))
    if not libs.user32.RegisterClassW(ctypes.byref(cls)):
        raise OSError("RegisterClassW failed for crop window")
    _CLASS_REGISTERED = True


def _dispatch(hwnd, msg, wparam, lparam):
    window = _WINDOWS.get(int(hwnd))
    if window is not None:
        handled = window._on_message(msg, wparam, lparam)
        if handled is not None:
            return handled
    return win32.bind().user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def _cursor_pos(libs):
    # Absolute coordinates cannot feed back as the destination moves under
    # the pointer; lParam is relative to the window's *current* position.
    point = win32.POINT()
    if not libs.user32.GetCursorPos(ctypes.byref(point)):
        return None
    return point.x, point.y


class CropWindow:
    """Pump-only controller. ``close`` releases resources, never saved state."""

    def __init__(
        self,
        libs,
        client,
        source_rect,
        rect,
        *,
        hidden,
        locked,
        on_activate,
        on_rect_changed,
        on_disable,
        on_failure,
    ):
        self._libs = libs
        self.client = client
        self.source_rect = source_rect
        self.rect = rect
        self.hidden = hidden
        self.locked = locked
        self._on_activate = on_activate
        self._on_rect_changed = on_rect_changed
        self._on_disable = on_disable
        self._on_failure = on_failure
        self.hwnd = None
        self._thumb = None
        self._failed = False
        self._mode = None
        self._start = None
        self._start_rect = None

    @classmethod
    def create(
        cls,
        libs,
        client: RosterClient,
        source_rect: Rect,
        rect: Rect,
        *,
        hidden: bool,
        locked: bool,
        on_activate,
        on_rect_changed,
        on_disable,
        on_failure,
    ):
        """Return a live controller or None; a candidate is hidden from birth."""
        self = cls(
            libs,
            client,
            source_rect,
            rect,
            hidden=hidden,
            locked=locked,
            on_activate=on_activate,
            on_rect_changed=on_rect_changed,
            on_disable=on_disable,
            on_failure=on_failure,
        )
        if not self._validate_source(source_rect):
            return None
        try:
            _ensure_class(libs)
        except OSError as exc:
            self._fail(str(exc))
            return None
        self.hwnd = (
            libs.user32.CreateWindowExW(
                win32.WS_EX_TOOLWINDOW | win32.WS_EX_NOACTIVATE | win32.WS_EX_TOPMOST,
                CROP_CLASS,
                f"FlyGD Wingman crop - {client.character}",
                win32.WS_POPUP,
                rect.x,
                rect.y,
                rect.w,
                rect.h,
                None,
                None,
                libs.kernel32.GetModuleHandleW(None),
                None,
            )
            or None
        )
        if self.hwnd is None:
            self._fail("CreateWindowExW failed")
            return None
        _WINDOWS[int(self.hwnd)] = self
        hr = self._register_thumbnail()
        if hr:
            self._fail("Initial DwmRegisterThumbnail", hr)
            return None
        hr = self._update_thumbnail()
        if hr:
            self._fail("Initial DwmUpdateThumbnailProperties", hr)
            return None
        if not hidden:
            libs.user32.ShowWindow(self.hwnd, win32.SW_SHOWNOACTIVATE)
        return self

    def _validate_source(self, source_rect):
        bounds = win32.RECT()
        if not self._libs.user32.GetClientRect(self.client.hwnd, ctypes.byref(bounds)):
            self._fail("Source client area unavailable")
            return False
        try:
            source_from_pixels(source_rect, (bounds.right, bounds.bottom))
        except ValueError as exc:
            self._fail(f"Invalid source {source_rect}: {exc}")
            return False
        return True

    def _register_thumbnail(self):
        # Thumbnail.register intentionally returns only None on failure. Keep
        # the raw registration HRESULT here so crop diagnostics include it
        # alongside the character and rectangles, without changing its API.
        handle = wintypes.HANDLE()
        hr = self._libs.dwmapi.DwmRegisterThumbnail(
            self.hwnd, self.client.hwnd, ctypes.byref(handle)
        )
        if hr == 0:
            self._thumb = Thumbnail(self._libs, handle, self.hwnd, self.client.hwnd)
        return int(hr)

    def _update_thumbnail(self):
        return self._thumb.update(
            Rect(0, 0, self.rect.w, self.rect.h),
            source_rect=self.source_rect,
            visible=not self.hidden,
        )

    def _refresh(self):
        """One recovery per failing update, never a retry loop on the pump."""
        hr = self._update_thumbnail()
        if not hr:
            return True
        reason = f"DwmUpdateThumbnailProperties hr=0x{hr & 0xFFFFFFFF:08x}"
        logger.warning(self._diagnostic(f"{reason}; attempting one recovery"))
        thumb, self._thumb = self._thumb, None
        thumb.close()
        recovery_hr = self._register_thumbnail()
        if recovery_hr:
            self._fail(f"{reason}; recovery DwmRegisterThumbnail failed", recovery_hr)
            return False
        recovery_hr = self._update_thumbnail()
        if recovery_hr:
            self._fail(f"{reason}; recovery update failed", recovery_hr)
            return False
        return True

    def move(self, rect: Rect) -> None:
        """Move only our destination; resizing never changes the source region."""
        if self.hwnd is None or rect == self.rect:
            return
        resized = (rect.w, rect.h) != (self.rect.w, self.rect.h)
        self.rect = rect
        # SWP_NOACTIVATE | SWP_NOZORDER: no foreground or Z-order side effect.
        if not self._libs.user32.SetWindowPos(
            self.hwnd, None, rect.x, rect.y, rect.w, rect.h, 0x0010 | 0x0004
        ):
            self._fail("SetWindowPos failed")
            return
        if resized and not self._refresh():
            return
        self._on_rect_changed(self.rect)

    def set_source_rect(self, rect: Rect) -> None:
        """Revalidate even an unchanged rectangle: the client may have shrunk."""
        if self.hwnd is None or not self._validate_source(rect):
            return
        if rect != self.source_rect:
            self.source_rect = rect
            self._refresh()

    def set_hidden(self, hidden: bool) -> None:
        if self.hwnd is None or hidden == self.hidden:
            return
        self.hidden = hidden
        if hidden:
            self._cancel_gesture()
            self._libs.user32.ShowWindow(self.hwnd, win32.SW_HIDE)
        # A hidden candidate's first visible update must succeed BEFORE
        # showing its HWND. Hiding does the inverse to take it off-screen now.
        if self._refresh() and not hidden:
            self._libs.user32.ShowWindow(self.hwnd, win32.SW_SHOWNOACTIVATE)

    def set_locked(self, locked: bool) -> None:
        if locked == self.locked:
            return
        self.locked = locked
        if locked:
            self._cancel_gesture()

    def _cancel_gesture(self, *, release=True):
        had_capture = self._mode is not None
        self._mode = self._start = self._start_rect = None
        # ReleaseCapture synchronously sends WM_CAPTURECHANGED, including
        # on our own release. Never release a different window's capture.
        if had_capture and release and self._libs.user32.GetCapture() == self.hwnd:
            self._libs.user32.ReleaseCapture()

    def _diagnostic(self, reason, hr=None):
        error = "" if hr is None else f" hr=0x{hr & 0xFFFFFFFF:08x}"
        return (
            f"Crop {self.client.character!r} src=0x{self.client.hwnd:x} "
            f"source={self.source_rect} destination={self.rect}: {reason}{error}"
        )

    def _fail(self, reason, hr=None):
        if self._failed:
            return
        self._failed = True
        message = self._diagnostic(reason, hr)
        logger.warning(message)
        self.close()
        self._on_failure(message)

    def close(self):
        """Unregister before destroying the destination; safe to repeat/re-enter."""
        self._cancel_gesture()
        if self._thumb is not None:
            thumb, self._thumb = self._thumb, None
            thumb.close()
        if self.hwnd is not None:
            hwnd, self.hwnd = self.hwnd, None
            _WINDOWS.pop(int(hwnd), None)
            self._libs.user32.DestroyWindow(hwnd)

    def _show_menu(self, point):
        menu = self._libs.user32.CreatePopupMenu()
        if not menu:
            logger.warning(self._diagnostic("CreatePopupMenu failed"))
            return
        command = 0
        try:
            if not self._libs.user32.AppendMenuW(
                menu, win32.MF_STRING, _DISABLE_CROP, "Disable crop"
            ):
                logger.warning(self._diagnostic("AppendMenuW failed"))
                return
            command = self._libs.user32.TrackPopupMenuEx(
                menu,
                win32.TPM_RETURNCMD | win32.TPM_NONOTIFY,
                point[0],
                point[1],
                self.hwnd,
                None,
            )
        finally:
            self._libs.user32.DestroyMenu(menu)
        # Tracking pumps messages: the host may close/hide us while the menu
        # is open. A stale menu result must not mutate committed state.
        if command == _DISABLE_CROP and self.hwnd is not None and not self.hidden:
            self._on_disable()

    def _drag_to(self, current):
        if self._mode in ("pending_left", "pending_right"):
            dx, dy = current[0] - self._start[0], current[1] - self._start[1]
            if dx * dx + dy * dy < CLICK_PX * CLICK_PX:
                return
            self._mode = "move" if self._mode == "pending_left" else "resize"
        if self.locked:
            return  # A moved right press is not a stationary menu request.
        if self._mode == "resize":
            self.move(
                resize_result(
                    self._start,
                    current,
                    self._start_rect,
                    min_size=MIN_SOURCE_SIZE,
                    aspect=self.source_rect.w / self.source_rect.h,
                    chrome=(0, 0),
                )
            )
        elif self._mode == "move":
            self.move(drag_target(self._start, current, self._start_rect))

    def _on_message(self, msg, wparam, lparam):
        if self.hwnd is None:
            return None
        if msg == win32.WM_CAPTURECHANGED:
            self._cancel_gesture(release=False)
            return 0
        if msg == win32.WM_CANCELMODE:
            self._cancel_gesture()
            # DefWindowProc must also cancel native menu tracking, which
            # outlives our custom gesture while TrackPopupMenuEx is running.
            return None
        if msg == win32.WM_CLOSE:
            self._cancel_gesture()
            self._on_disable()
            return 0
        if msg == win32.WM_DESTROY:
            # Defensive OS teardown; never recursively DestroyWindow here.
            self._cancel_gesture()
            if self._thumb is not None:
                thumb, self._thumb = self._thumb, None
                thumb.close()
            _WINDOWS.pop(int(self.hwnd), None)
            self.hwnd = None
            return 0
        if self.hidden:
            return None
        if msg in (win32.WM_LBUTTONDOWN, win32.WM_RBUTTONDOWN):
            if self._mode is not None:
                return 0  # No second-button/chord grammar on crops.
            if self.locked and msg == win32.WM_LBUTTONDOWN:
                self._on_activate(self.client)
                return 0
            point = _cursor_pos(self._libs)
            if point is None:
                return 0
            self._mode = (
                "pending_left" if msg == win32.WM_LBUTTONDOWN else "pending_right"
            )
            self._start, self._start_rect = point, self.rect
            self._libs.user32.SetCapture(self.hwnd)
            return 0
        if msg == win32.WM_MOUSEMOVE and self._mode is not None:
            coalesce_moves(self._libs.user32.PeekMessageW, self.hwnd, lparam)
            point = _cursor_pos(self._libs)
            if point is None:
                self._cancel_gesture()
            else:
                self._drag_to(point)
            return 0
        if msg in (win32.WM_LBUTTONUP, win32.WM_RBUTTONUP) and self._mode is not None:
            right = self._mode in ("pending_right", "resize")
            if right != (msg == win32.WM_RBUTTONUP):
                self._cancel_gesture()
                return 0
            point = _cursor_pos(self._libs)
            if point is None:
                self._cancel_gesture()
                return 0
            # Mouse-up may be the first position outside the click radius.
            self._drag_to(point)
            mode = self._mode
            self._cancel_gesture()
            if mode == "pending_left":
                self._on_activate(self.client)
            elif mode == "pending_right":
                self._show_menu(point)
            return 0
        return None
