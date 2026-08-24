"""One preview window: an HWND, its chrome, and its thumbnail.

The gesture arithmetic at the top is pure and tested in CI. Everything
below it touches HWNDs and therefore may only run on the preview thread.
"""
import logging

from . import chrome, geometry, layered, win32
from .thumbnail import Thumbnail

logger = logging.getLogger(__name__)

MIN_SIZE = (120, 90)
BORDER = 5
LABEL_H = 30
DRAG_MIN = 4


def drag_result(start, current, rect, locked: bool, drag_min: int = DRAG_MIN):
    """Classify a completed pointer gesture.

    Returns ("activate", unchanged_rect) or ("move", new_rect). A locked
    preview always reports "activate": the lock stops movement, not focus
    switching.
    """
    dx, dy = current[0] - start[0], current[1] - start[1]
    if locked or (abs(dx) <= drag_min and abs(dy) <= drag_min):
        return "activate", rect
    return "move", rect._replace(x=rect.x + dx, y=rect.y + dy)


def resize_result(start, current, rect, min_size=MIN_SIZE):
    """New rect for a resize drag. Top-left is the anchor and never moves.

    Floored at *min_size*: a rect dragged through zero would invert, and
    DwmUpdateThumbnailProperties rejects an inverted destination -- the
    preview just goes blank, with nothing logged.
    """
    dx, dy = current[0] - start[0], current[1] - start[1]
    return rect._replace(w=max(min_size[0], rect.w + dx),
                         h=max(min_size[1], rect.h + dy))


def activate(libs, hwnd) -> bool:
    """Bring *hwnd* to the foreground. Returns whether it actually worked.

    SetForegroundWindow alone does not work: Windows refuses it from a
    process that does not own the foreground. The two-stage
    AttachThreadInput dance is what makes it succeed.

    The verdict is read from GetForegroundWindow, never from
    SetForegroundWindow's return value -- that reports the request was
    accepted, not that the window came forward.

    Every attach MUST be balanced by a detach, including on the failure
    path: a leaked attachment welds two threads' input queues together for
    the life of the process, and the symptom is EVE's keyboard input
    arriving in the wrong client.
    """
    if libs.user32.IsIconic(hwnd):
        libs.user32.ShowWindowAsync(hwnd, win32.SW_RESTORE)

    current = libs.user32.GetForegroundWindow()
    if current == hwnd:
        return True

    our_tid = libs.kernel32.GetCurrentThreadId()
    fg_tid = libs.user32.GetWindowThreadProcessId(current, None)
    target_tid = libs.user32.GetWindowThreadProcessId(hwnd, None)

    attached = []
    try:
        for tid in (fg_tid, target_tid):
            if tid and tid != our_tid and libs.user32.AttachThreadInput(
                    our_tid, tid, True):
                attached.append(tid)
        libs.user32.SetForegroundWindow(hwnd)
    finally:
        for tid in attached:
            libs.user32.AttachThreadInput(our_tid, tid, False)

    ok = libs.user32.GetForegroundWindow() == hwnd
    if not ok:
        # The most likely field complaint is "clicking a preview does
        # nothing". Without this line there is nothing to go on.
        logger.debug("Activation of 0x%x did not take; foreground is 0x%x",
                     hwnd, libs.user32.GetForegroundWindow() or 0)
    return ok


_CLASS_REGISTERED = False
CLASS_NAME = "WingmanPreviewWindow"


def _ensure_class(libs):
    """Register the window class once per process."""
    global _CLASS_REGISTERED
    if _CLASS_REGISTERED:
        return
    import ctypes
    from ctypes import wintypes

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", wintypes.UINT),
                    ("lpfnWndProc", win32.wndproc_type()),
                    ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wintypes.HINSTANCE),
                    ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
                    ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR),
                    ("lpszClassName", wintypes.LPCWSTR)]

    proc = win32.wndproc_type()(_dispatch)
    win32._KEEPALIVE.append(proc)   # see win32._KEEPALIVE's comment
    cls = WNDCLASSW()
    cls.lpfnWndProc = proc
    cls.hInstance = libs.kernel32.GetModuleHandleW(None)
    cls.lpszClassName = CLASS_NAME
    cls.hCursor = libs.user32.LoadCursorW(None, ctypes.c_wchar_p(0x7F00))
    libs.user32.RegisterClassW(ctypes.byref(cls))
    _CLASS_REGISTERED = True


# hwnd -> PreviewWindow, so the class-level WndProc can find its instance.
_WINDOWS = {}


def _dispatch(hwnd, msg, wparam, lparam):
    libs = win32.bind()
    self = _WINDOWS.get(int(hwnd))
    if self is not None:
        handled = self._on_message(msg, wparam, lparam)
        if handled is not None:
            return handled
    return libs.user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def _lparam_point(lparam):
    """Client coords packed into lParam. Signed: a drag above or left of
    the window gives negative values, and reading them unsigned makes the
    preview jump to the far edge of the desktop."""
    x = lparam & 0xFFFF
    y = (lparam >> 16) & 0xFFFF
    return (x - 0x10000 if x > 0x7FFF else x,
            y - 0x10000 if y > 0x7FFF else y)


class PreviewWindow:
    """One client's preview. Every method here runs on the preview thread.

    Touching any of this from another thread is a thread-affinity
    violation: Win32 window ownership is per-thread, and the failure mode
    is a hang, not an exception.
    """

    def __init__(self, libs, client, rect, on_activate, on_rect_changed,
                 neighbours):
        self._libs = libs
        self.client = client
        self.rect = rect
        self.locked = False
        self._on_activate = on_activate
        self._on_rect_changed = on_rect_changed
        # Supplied by the host, which is the only thing that knows about
        # sibling previews. Without it snap() sees screen edges only and
        # preview-to-preview snapping silently does nothing.
        self._neighbours = neighbours
        self.hwnd = None
        self._thumb = None
        self._mode = None
        self._start = None
        self._start_rect = None

    @classmethod
    def create(cls, libs, client, rect, on_activate, on_rect_changed,
               neighbours):
        self = cls(libs, client, rect, on_activate, on_rect_changed,
                   neighbours)
        _ensure_class(libs)
        self.hwnd = libs.user32.CreateWindowExW(
            win32.WS_EX_LAYERED | win32.WS_EX_TOOLWINDOW
            | win32.WS_EX_NOACTIVATE | win32.WS_EX_TOPMOST,
            CLASS_NAME, "wingman-preview", win32.WS_POPUP,
            rect.x, rect.y, rect.w, rect.h,
            None, None, libs.kernel32.GetModuleHandleW(None), None)
        if not self.hwnd:
            logger.warning("CreateWindowExW failed for %s", client.stable_key)
            return None
        _WINDOWS[int(self.hwnd)] = self
        self.redraw()
        libs.user32.ShowWindow(self.hwnd, win32.SW_SHOWNOACTIVATE)
        self._thumb = Thumbnail.register(libs, self.hwnd, client.hwnd)
        if self._thumb is not None:
            self._thumb.update(geometry.thumbnail_rect(self.rect, BORDER,
                                                       LABEL_H))
        return self

    # -- rendering -------------------------------------------------------
    def redraw(self) -> None:
        label = self.client.character or self.client.title
        img = chrome.render((self.rect.w, self.rect.h), label,
                            border_color=(0, 200, 220, 255),
                            border=BORDER, label_h=LABEL_H)
        layered.push(self._libs, self.hwnd, img, self.rect.x, self.rect.y)

    def move(self, rect) -> None:
        self.rect = rect
        # SWP_NOACTIVATE | SWP_NOZORDER: moving a preview must not steal
        # focus from the client the user is about to click into.
        self._libs.user32.SetWindowPos(self.hwnd, None, rect.x, rect.y,
                                       rect.w, rect.h, 0x0010 | 0x0004)
        self.redraw()
        if self._thumb is not None:
            self._thumb.update(geometry.thumbnail_rect(rect, BORDER, LABEL_H))

    # -- input -----------------------------------------------------------
    def _on_message(self, msg, wparam, lparam):
        if msg in (win32.WM_LBUTTONDOWN, win32.WM_RBUTTONDOWN):
            pt = _lparam_point(lparam)
            self._start, self._start_rect = pt, self.rect
            self._mode = ("resize"
                          if (msg == win32.WM_LBUTTONDOWN
                              and geometry.hit_resize_handle(
                                  geometry.Rect(0, 0, self.rect.w,
                                                self.rect.h), *pt))
                          else "drag")
            self._libs.user32.SetCapture(self.hwnd)
            return 0

        if msg == win32.WM_MOUSEMOVE and self._mode:
            if self.locked and self._mode == "drag":
                return 0
            pt = _lparam_point(lparam)
            # Client coords move with the window, so compare against the
            # rect captured at button-down rather than the live one.
            cur = (self._start_rect.x + pt[0], self._start_rect.y + pt[1])
            start = (self._start_rect.x + self._start[0],
                     self._start_rect.y + self._start[1])
            if self._mode == "resize":
                self.move(resize_result(start, cur, self._start_rect))
            else:
                moved = self._start_rect._replace(
                    x=self._start_rect.x + (cur[0] - start[0]),
                    y=self._start_rect.y + (cur[1] - start[1]))
                self.move(geometry.snap(moved, self._neighbours(),
                                        self._screen()))
            return 0

        if msg in (win32.WM_LBUTTONUP, win32.WM_RBUTTONUP) and self._mode:
            self._libs.user32.ReleaseCapture()
            mode, self._mode = self._mode, None
            pt = _lparam_point(lparam)
            if mode == "drag" and msg == win32.WM_LBUTTONUP:
                action, _ = drag_result(self._start, pt, self._start_rect,
                                        self.locked)
                if action == "activate":
                    activate(self._libs, self.client.hwnd)
                    self._on_activate(self.client)
                    return 0
            self._on_rect_changed(self.client.stable_key, self.rect,
                                  self.locked)
            return 0

        if msg == win32.WM_DESTROY:
            self._release_thumb()
            return 0
        return None

    def _screen(self):
        # Single-monitor virtual desktop is enough for snapping; the host
        # supplies real bounds once multi-monitor layout lands.
        return geometry.Rect(0, 0, 1920, 1080)

    # -- teardown --------------------------------------------------------
    def _release_thumb(self):
        if self._thumb is not None:
            self._thumb.close()
            self._thumb = None

    def close(self) -> None:
        """Thumbnail first: its destination is this window, and
        unregistering after DestroyWindow leaves DWM holding a dead HWND."""
        self._release_thumb()
        if self.hwnd:
            _WINDOWS.pop(int(self.hwnd), None)
            self._libs.user32.DestroyWindow(self.hwnd)
            self.hwnd = None
