"""One preview window: an HWND, its chrome, and its thumbnail.

The gesture arithmetic at the top is pure and tested in CI. Everything
below it touches HWNDs and therefore may only run on the preview thread.
"""

import logging
import os
import time

from . import chrome, geometry, layered, win32
from .thumbnail import Thumbnail

logger = logging.getLogger(__name__)

# Opt-in drag diagnostics. Off by default and free when off: one bool
# check per mouse-move. Set WINGMAN_PREVIEW_PERF=1 to have each drag log
# how many moves it processed, how long the handler took, and -- the part
# that matters -- the largest gap BETWEEN events, which is what a stutter
# actually is.
# .strip(): in cmd.exe, `set VAR=1 && prog` assigns "1 " with a
# trailing space, so an exact match silently disables this for anyone
# who sets it the obvious way.
# .strip(): in cmd.exe, `set VAR=1 && prog` assigns "1 " with a
# trailing space, so an exact match silently disables this for anyone
# who sets it the obvious way.
PERF = os.environ.get("WINGMAN_PREVIEW_PERF", "").strip() == "1"

MIN_SIZE = (120, 90)
BORDER = 2
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
    return rect._replace(
        w=max(min_size[0], rect.w + dx), h=max(min_size[1], rect.h + dy)
    )


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
            if (
                tid
                and tid != our_tid
                and libs.user32.AttachThreadInput(our_tid, tid, True)
            ):
                attached.append(tid)
        libs.user32.SetForegroundWindow(hwnd)
    finally:
        for tid in attached:
            libs.user32.AttachThreadInput(our_tid, tid, False)

    ok = libs.user32.GetForegroundWindow() == hwnd
    if not ok:
        # INFO, not DEBUG: the root logger runs at INFO (__main__.py:64),
        # so a debug line here is invisible in the only log a user will
        # ever send us -- for the single most likely field complaint,
        # "clicking a preview does nothing". It cannot spam either: this
        # fires once per click, and only when the click failed.
        logger.info(
            "Activation of 0x%x did not take; foreground is 0x%x. "
            "Windows refuses a foreground change from a process "
            "that has not received recent user input.",
            hwnd,
            libs.user32.GetForegroundWindow() or 0,
        )
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
    win32._KEEPALIVE.append(proc)  # see win32._KEEPALIVE's comment
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


def drag_target(start_screen, cur_screen, start_rect):
    """Where the rect should be, from ABSOLUTE cursor positions.

    Both points are screen coordinates, and the anchor is the rect as it
    was at button-down. That combination is what makes this stable.

    The bug this replaces: WM_MOUSEMOVE's lParam is in CLIENT coordinates
    of the window's CURRENT position, and it was being converted to screen
    coordinates using the position at button-down. Once the window moved,
    the two disagreed by exactly the accumulated delta, so the target
    overshot, the window moved back, that generated another WM_MOUSEMOVE,
    and it oscillated -- visibly vibrating, and continuing to vibrate with
    the cursor completely still as long as the button was held.
    """
    return start_rect._replace(
        x=start_rect.x + (cur_screen[0] - start_screen[0]),
        y=start_rect.y + (cur_screen[1] - start_screen[1]),
    )


def coalesce_moves(peek, hwnd, lparam):
    """Return the newest queued mouse position, discarding the rest.

    A drag delivers WM_MOUSEMOVE far faster than a preview can be moved:
    measured at 320/s against a ~1.8ms handler, which is 58% of the thread
    for one window -- and a 1000Hz mouse would bury it. The cost is
    SetWindowPos blocking while DWM recomposites several topmost layered
    windows with live thumbnails.

    Processing every event just builds a backlog and makes the window lag
    the cursor, which is what the stutter is. Only the newest position can
    possibly be correct, so drop the intermediate ones: the window tracks
    the cursor and the thread stops saturating.

    *peek* is PeekMessageW, injected so this is testable off Windows.
    """
    from ctypes import byref
    from ctypes import wintypes as _wt

    msg = _wt.MSG()
    while peek(
        byref(msg), hwnd, win32.WM_MOUSEMOVE, win32.WM_MOUSEMOVE, win32.PM_REMOVE
    ):
        lparam = msg.lParam
    return lparam


def _cursor_pos(libs):
    """Absolute cursor position. Immune to the window moving under it."""
    import ctypes

    pt = win32.POINT()
    libs.user32.GetCursorPos(ctypes.byref(pt))
    return (pt.x, pt.y)


def _lparam_point(lparam):
    """Client coords packed into lParam. Signed: a drag above or left of
    the window gives negative values, and reading them unsigned makes the
    preview jump to the far edge of the desktop."""
    x = lparam & 0xFFFF
    y = (lparam >> 16) & 0xFFFF
    return (x - 0x10000 if x > 0x7FFF else x, y - 0x10000 if y > 0x7FFF else y)


class PreviewWindow:
    """One client's preview. Every method here runs on the preview thread.

    Touching any of this from another thread is a thread-affinity
    violation: Win32 window ownership is per-thread, and the failure mode
    is a hang, not an exception.
    """

    def __init__(
        self,
        libs,
        client,
        rect,
        on_activate,
        on_rect_changed,
        neighbours,
        screen,
        locked=False,
        show_labels=True,
        opacity: int = 255,
    ):
        self._libs = libs
        self.client = client
        self.rect = rect
        # Restored from the saved layout, not assumed False: a preview the
        # user locked must still be locked after a restart, and reporting
        # locked=False on the next drag would erase the flag.
        self.locked = locked
        # Set once from the host at creation; Task 4 wires the live-update
        # path that lets this change on an already-open window.
        self.show_labels = show_labels
        # A DWM thumbnail property, not a bitmap one -- see the note on
        # _chrome_key() below. Set once at creation; Task 4 wires the
        # live-update path that lets this change on an already-open window.
        self.opacity = opacity
        self.selected = False
        self._perf = None
        # Last key rendered; None forces the first draw.
        self._chrome_cache_key = None
        self._on_activate = on_activate
        self._on_rect_changed = on_rect_changed
        # Supplied by the host, which is the only thing that knows about
        # sibling previews. Without it snap() sees screen edges only and
        # preview-to-preview snapping silently does nothing.
        self._neighbours = neighbours
        # Supplied, not computed here: the host re-reads it each sweep so
        # a monitor added or rearranged mid-session is picked up.
        self._screen = screen
        self.hwnd = None
        self._thumb = None
        self._mode = None
        self._start = None
        self._start_rect = None

    @classmethod
    def create(
        cls,
        libs,
        client,
        rect,
        on_activate,
        on_rect_changed,
        neighbours,
        screen,
        locked=False,
        show_labels=True,
        opacity: int = 255,
    ):
        self = cls(
            libs,
            client,
            rect,
            on_activate,
            on_rect_changed,
            neighbours,
            screen,
            locked,
            show_labels,
            opacity,
        )
        _ensure_class(libs)
        self.hwnd = libs.user32.CreateWindowExW(
            win32.WS_EX_LAYERED
            | win32.WS_EX_TOOLWINDOW
            | win32.WS_EX_NOACTIVATE
            | win32.WS_EX_TOPMOST,
            CLASS_NAME,
            "wingman-preview",
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
        if not self.hwnd:
            logger.warning("CreateWindowExW failed for %s", client.stable_key)
            return None
        _WINDOWS[int(self.hwnd)] = self
        self.redraw()
        libs.user32.ShowWindow(self.hwnd, win32.SW_SHOWNOACTIVATE)
        self._thumb = Thumbnail.register(libs, self.hwnd, client.hwnd)
        if self._thumb is not None:
            self._thumb.update(
                geometry.thumbnail_rect(self.rect, BORDER, self._label_h()),
                self.opacity,
            )
        return self

    # -- rendering -------------------------------------------------------
    def _label_h(self) -> int:
        """LABEL_H when labels are on, 0 when off.

        chrome.py needs no change for the off case: its band guard
        (`band_bottom > border`) is already false when label_h=0, so a
        bandless tile with no text falls out of the existing render path.
        """
        return LABEL_H if self.show_labels else 0

    def _chrome_key(self):
        # opacity deliberately does NOT belong here. It is a DWM thumbnail
        # property (Thumbnail.update's DWM_TNP_OPACITY), never a pixel in
        # this bitmap, so including it would force a ~67k-pixel re-render
        # on every opacity change for no visual reason -- the exact cost
        # redraw()'s short-circuit exists to avoid.
        return (
            self.rect.w,
            self.rect.h,
            self.client.character or self.client.title,
            self.selected,
            # Without this, flipping show_labels on an already-open preview
            # is a no-op: redraw() short-circuits on an unchanged key and
            # the bitmap never repaints.
            self.show_labels,
        )

    def redraw(self, force: bool = False) -> None:
        """Re-render the chrome bitmap and push it to the layered surface.

        Skipped when nothing that affects the bitmap has changed. Rendering
        is a fresh Pillow image plus a ~67k-pixel DIB push, and a drag
        emits a mouse-move at well over 100Hz -- doing this per move is
        what made dragging stutter.
        """
        key = self._chrome_key()
        if not force and key == self._chrome_cache_key:
            return
        label = self.client.character or self.client.title
        img = chrome.render(
            (self.rect.w, self.rect.h),
            label,
            border_color=(0, 200, 220, 255),
            border=BORDER,
            label_h=self._label_h(),
            selected=self.selected,
        )
        layered.push(self._libs, self.hwnd, img, self.rect.x, self.rect.y)
        self._chrome_cache_key = key

    def set_selected(self, selected: bool) -> None:
        if selected == self.selected:
            return
        self.selected = selected
        # Already part of _chrome_key() above, so this repaints.
        self.redraw()

    def move(self, rect) -> None:
        """Reposition and, only if the size changed, re-render.

        A pure move needs SetWindowPos alone. The layered surface survives
        a move, and the thumbnail's destination is in CLIENT coordinates,
        so neither has to be touched when only x/y change.
        """
        resized = (rect.w, rect.h) != (self.rect.w, self.rect.h)
        self.rect = rect
        # SWP_NOACTIVATE | SWP_NOZORDER: moving a preview must not steal
        # focus from the client the user is about to click into.
        self._libs.user32.SetWindowPos(
            self.hwnd, None, rect.x, rect.y, rect.w, rect.h, 0x0010 | 0x0004
        )
        if resized:
            # The bitmap is sized to the window, so a resize must re-push
            # it or the surface stays at the old dimensions.
            self.redraw()
            if self._thumb is not None:
                self._thumb.update(
                    geometry.thumbnail_rect(rect, BORDER, self._label_h()),
                    self.opacity,
                )

    # -- input -----------------------------------------------------------
    def _on_message(self, msg, wparam, lparam):
        if msg in (win32.WM_LBUTTONDOWN, win32.WM_RBUTTONDOWN):
            pt = _lparam_point(lparam)
            # Client coords are only safe HERE: the window has not moved
            # yet, so they still describe the point that was clicked.
            self._start_rect = self.rect
            self._start = _cursor_pos(self._libs)
            if msg == win32.WM_LBUTTONDOWN and geometry.hit_resize_handle(
                geometry.Rect(0, 0, self.rect.w, self.rect.h), *pt
            ):
                self._mode = "resize"
            elif msg == win32.WM_RBUTTONDOWN:
                # Tracked separately from a left drag: right-drag is the
                # override that moves a LOCKED preview. Collapsing both
                # into one "drag" mode made the lock suppress it too, so
                # the override documented alongside it did nothing.
                self._mode = "right_drag"
            else:
                self._mode = "drag"
            self._libs.user32.SetCapture(self.hwnd)
            if PERF:
                self._perf = {
                    "n": 0,
                    "handler": 0.0,
                    "gap": 0.0,
                    "last": time.perf_counter(),
                    "start": time.perf_counter(),
                }
            return 0

        if msg == win32.WM_MOUSEMOVE and self._mode:
            if self.locked and self._mode == "drag":
                # Left drag only. A lock stops accidental movement; the
                # right-drag override is how a locked preview is moved
                # deliberately.
                return 0
            if PERF:
                t0 = time.perf_counter()
                p = self._perf
                p["gap"] = max(p["gap"], t0 - p["last"])
                p["n"] += 1
            coalesce_moves(self._libs.user32.PeekMessageW, self.hwnd, lparam)
            # GetCursorPos, not lParam: lParam is client-relative and the
            # window is moving under the cursor, which is what made this
            # oscillate. Absolute coordinates cannot feed back.
            cur = _cursor_pos(self._libs)
            if self._mode == "resize":
                self.move(resize_result(self._start, cur, self._start_rect))
            else:
                moved = drag_target(self._start, cur, self._start_rect)
                self.move(geometry.snap(moved, self._neighbours(), self._screen()))
            if PERF:
                now = time.perf_counter()
                self._perf["handler"] += now - t0
                self._perf["last"] = now
            return 0

        if msg in (win32.WM_LBUTTONUP, win32.WM_RBUTTONUP) and self._mode:
            self._libs.user32.ReleaseCapture()
            if PERF and getattr(self, "_perf", None):
                p = self._perf
                wall = time.perf_counter() - p["start"]
                n = max(1, p["n"])
                logger.info(
                    "drag perf: %d moves in %.0fms (%.0f/s) | handler "
                    "%.3fms avg, %.1f%% of wall | worst gap between events "
                    "%.1fms",
                    p["n"],
                    wall * 1000,
                    n / max(wall, 1e-6),
                    p["handler"] * 1000 / n,
                    100 * p["handler"] / max(wall, 1e-6),
                    p["gap"] * 1000,
                )
                self._perf = None
            mode, self._mode = self._mode, None
            if mode == "drag" and msg == win32.WM_LBUTTONUP:
                # Only a left click activates. A right-drag release falls
                # through to reporting the new rect.
                action, _ = drag_result(
                    self._start, _cursor_pos(self._libs), self._start_rect, self.locked
                )
                if action == "activate":
                    # Classify, then hand off: the window does NOT call
                    # activate() itself. The host owns the switch because
                    # it is the only thing that knows the previous
                    # foreground, the roster and the settings -- and it
                    # has to know them BEFORE the foreground moves. When
                    # both owned it, the host learned of a click only
                    # after the switch was already over.
                    self._on_activate(self.client)
                    return 0
            self._on_rect_changed(self.client.stable_key, self.rect, self.locked)
            return 0

        if msg == win32.WM_DESTROY:
            self._release_thumb()
            return 0
        return None

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
