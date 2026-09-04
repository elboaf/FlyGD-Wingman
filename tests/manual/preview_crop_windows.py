"""Prototype crop window: an ephemeral, DWM-only mirror of one rectangle of
a client's area, positioned and resized independently of the primary
preview.

This is a Phase 0 engineering probe (see
docs/preview-evolution-crops-design.md), not production code: it is not
imported by wingman/__main__.py, ui/api.py, or any shipped module, and it
persists nothing. It is loaded directly by tests/test_preview_crop_windows.py
via importlib, the same way tests/manual/preview_crop_model.py is loaded by
tests/test_preview_crop_model.py.

Deliberately reuses only the PURE helpers from wingman/preview/window.py --
CLICK_PX, resize_result, drag_target, coalesce_moves -- and never its
activation functions: the host decides whether and how to bring a client
forward, this controller only ever asks via on_activate(client).

Design-doc first-version exclusions carried through here: no label overlay,
no alert ring, no independent hotkey, no crop-specific opacity or
click-through control, no direct settings writes, no client discovery.
That is also why the window is WS_POPUP with no WS_EX_LAYERED: unlike the
primary preview, this prototype owns no layered chrome bitmap at all --
DWM's thumbnail is the only thing ever painted onto it.

Same Linux-import constraint as wingman/preview/win32.py: ctypes.WINFUNCTYPE,
ctypes.WinDLL and ctypes.windll do not exist off Windows, so every native
call lives inside create() or a method invoked with injected libs, never at
module scope.
"""

import logging
import os
import time

from wingman.preview import win32
from wingman.preview.geometry import Rect
from wingman.preview.thumbnail import Thumbnail
from wingman.preview.window import CLICK_PX, coalesce_moves, drag_target, resize_result

logger = logging.getLogger(__name__)

# Same opt-in and the same .strip() rationale as wingman/preview/window.py:
# `set VAR=1 && prog` in cmd.exe assigns "1 " with a trailing space.
PERF = os.environ.get("WINGMAN_PREVIEW_PERF", "").strip() == "1"

# Smaller than the primary preview's MIN_SIZE: there is no chrome to fit
# inside, and central_source()/map_selection() already floor a source
# selection at 16x16 (see tests/manual/preview_crop_model.py).
MIN_SIZE = (16, 16)

CROP_CLASS = "WingmanPreviewCropProbe"
# hwnd -> PrototypeCropWindow, mirroring window.py's _WINDOWS registry so
# the class-level WndProc can find its instance.
_CROPS = {}

_CLASS_REGISTERED = False


def _ensure_class(libs):
    """Register the crop window class once per process.

    Byte-for-byte the same pattern as window.py's _ensure_class -- a
    distinct class name and a distinct keepalive entry, because Windows
    requires one registered class per distinct WndProc/name pair, not
    because this WndProc differs in any interesting way.
    """
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
    cls.lpszClassName = CROP_CLASS
    cls.hCursor = libs.user32.LoadCursorW(None, ctypes.c_wchar_p(0x7F00))
    libs.user32.RegisterClassW(ctypes.byref(cls))
    _CLASS_REGISTERED = True


def _dispatch(hwnd, msg, wparam, lparam):
    libs = win32.bind()
    self = _CROPS.get(int(hwnd))
    if self is not None:
        handled = self._on_message(msg, wparam, lparam)
        if handled is not None:
            return handled
    return libs.user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def _cursor_pos(libs):
    """Absolute cursor position -- see window.py's _cursor_pos for why this
    must be the source of truth rather than lParam while a drag is live."""
    import ctypes

    pt = win32.POINT()
    libs.user32.GetCursorPos(ctypes.byref(pt))
    return (pt.x, pt.y)


class PrototypeCropWindow:
    """One ephemeral crop: an HWND, its DWM thumbnail (source-rect mirror of
    a client's area), and the reduced click/move/resize gesture grammar.

    Every method here runs on the preview thread, same thread-affinity
    contract as PreviewWindow -- see that class's docstring.
    """

    def __init__(self, libs, client, source_rect, rect, on_activate, locked=False):
        self._libs = libs
        self.client = client
        # The client-area rectangle DWM mirrors from. Fixed for the life of
        # this controller: the design reselects by creating a new crop
        # rather than mutating the source of a live one.
        self.source_rect = source_rect
        self.rect = rect
        self.locked = locked
        self.hidden = False
        self._on_activate = on_activate
        self.hwnd = None
        self._thumb = None
        self._mode = None
        self._start = None
        self._start_rect = None
        self._perf = None

    @classmethod
    def create(cls, libs, client, source_rect, rect, on_activate, locked=False):
        """Creation order: HWND, then the HWND registry, then the DWM
        thumbnail, then its first update. A non-zero HRESULT from that
        first update tears down in DWM-before-HWND order -- unregistering
        after DestroyWindow would leave DWM holding a dead handle -- and a
        failed registration itself skips straight to destroying the HWND,
        since there is no DWM relationship yet to unwind."""
        self = cls(libs, client, source_rect, rect, on_activate, locked)
        _ensure_class(libs)
        ex_style = win32.WS_EX_TOOLWINDOW | win32.WS_EX_NOACTIVATE | win32.WS_EX_TOPMOST
        self.hwnd = libs.user32.CreateWindowExW(
            ex_style,
            CROP_CLASS,
            "wingman-crop",
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
            logger.warning("CreateWindowExW failed for crop %s", client.stable_key)
            return None
        _CROPS[int(self.hwnd)] = self
        self._thumb = Thumbnail.register(libs, self.hwnd, client.hwnd)
        if self._thumb is None:
            # Nothing DWM-side exists yet: destroy the HWND directly.
            _CROPS.pop(int(self.hwnd), None)
            libs.user32.DestroyWindow(self.hwnd)
            self.hwnd = None
            return None
        hr = self._thumb.update(Rect(0, 0, rect.w, rect.h), source_rect=source_rect)
        if hr:
            self._thumb.close()  # DWM first
            self._thumb = None
            _CROPS.pop(int(self.hwnd), None)
            libs.user32.DestroyWindow(self.hwnd)  # HWND second
            self.hwnd = None
            return None
        libs.user32.ShowWindow(self.hwnd, win32.SW_SHOWNOACTIVATE)
        return self

    def _source_aspect(self):
        """The selected source region's own shape, or None for a
        degenerate rect. None routes resize_result to its freeform
        fallback rather than raising."""
        if self.source_rect.w <= 0 or self.source_rect.h <= 0:
            return None
        return self.source_rect.w / self.source_rect.h

    # -- geometry ----------------------------------------------------------
    def move(self, rect) -> None:
        """Reposition and, only on a resize, push a fresh DWM update.

        The destination the thumbnail is told about is always (0, 0, w, h)
        in the crop's own client coordinates -- there is no chrome inset to
        account for, unlike the primary preview's BORDER. The source
        rectangle passed to DWM never changes on a resize: the crop resizes
        its DESTINATION, not what it mirrors.
        """
        resized = (rect.w, rect.h) != (self.rect.w, self.rect.h)
        self.rect = rect
        # SWP_NOACTIVATE | SWP_NOZORDER, same flags and the same reason as
        # window.py's move(): repositioning a crop must not steal focus
        # from the client the user is about to click into.
        self._libs.user32.SetWindowPos(
            self.hwnd, None, rect.x, rect.y, rect.w, rect.h, 0x0010 | 0x0004
        )
        if resized and self._thumb is not None:
            self._thumb.update(Rect(0, 0, rect.w, rect.h), source_rect=self.source_rect)

    def set_hidden(self, hidden: bool) -> None:
        """Take this crop off screen, or put it back. Idempotent, like
        PreviewWindow.set_hidden and for the same reason -- the host applies
        this every sweep and every foreground change."""
        if hidden == self.hidden:
            return
        self.hidden = hidden
        if self.hwnd is None:
            return
        self._libs.user32.ShowWindow(
            self.hwnd, win32.SW_HIDE if hidden else win32.SW_SHOWNOACTIVATE
        )

    def set_locked(self, locked: bool) -> None:
        """Apply a live lock. A lock in flight cancels whatever gesture is
        currently armed rather than letting a drag that started unlocked
        keep moving the crop after the flag flips -- the same "nothing may
        change by mouse while locked" guarantee PreviewWindow's message
        handler enforces up front on every press."""
        locked = bool(locked)
        if locked and self._mode is not None:
            self._libs.user32.ReleaseCapture()
            self._mode = None
        self.locked = locked

    # -- teardown ------------------------------------------------------
    def close(self) -> None:
        """DWM first, HWND second -- the same order as create()'s cleanup
        and PreviewWindow.close(): unregistering after DestroyWindow would
        leave DWM holding a dead handle. Idempotent: a second call finds
        both already cleared and does nothing."""
        if self._thumb is not None:
            self._thumb.close()
            self._thumb = None
        if self.hwnd:
            _CROPS.pop(int(self.hwnd), None)
            self._libs.user32.DestroyWindow(self.hwnd)
            self.hwnd = None

    # -- input -----------------------------------------------------------
    def _on_message(self, msg, wparam, lparam):
        # The reduced grammar: no resize-all chord, no snapping, no corner
        # handle -- a crop has no neighbours to snap to and its aspect is
        # always the selected source's, never a per-crop toggle.
        #
        #   locked left press  -> activate immediately, nothing else
        #   unlocked left      -> click (release inside CLICK_PX) or drag-move
        #   unlocked right     -> drag-resize, source aspect preserved
        if msg in (win32.WM_LBUTTONDOWN, win32.WM_RBUTTONDOWN):
            if self.locked:
                if msg == win32.WM_LBUTTONDOWN:
                    self._on_activate(self.client)
                return 0
            self._mode = "pending_left" if msg == win32.WM_LBUTTONDOWN else "resize"
            self._start_rect = self.rect
            self._start = _cursor_pos(self._libs)
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
            if PERF:
                t0 = time.perf_counter()
                p = self._perf
                p["gap"] = max(p["gap"], t0 - p["last"])
                p["n"] += 1
            coalesce_moves(self._libs.user32.PeekMessageW, self.hwnd, lparam)
            cur = _cursor_pos(self._libs)
            if self._mode == "pending_left":
                dx, dy = cur[0] - self._start[0], cur[1] - self._start[1]
                if dx * dx + dy * dy < CLICK_PX * CLICK_PX:
                    return 0
                self._mode = "move"
            if self._mode == "resize":
                self.move(
                    resize_result(
                        self._start,
                        cur,
                        self._start_rect,
                        min_size=MIN_SIZE,
                        aspect=self._source_aspect(),
                        chrome=(0, 0),
                    )
                )
            else:
                self.move(drag_target(self._start, cur, self._start_rect))
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
                    "crop drag perf: %d moves in %.0fms (%.0f/s) | handler "
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
            if self._mode == "pending_left":
                # The click that never dragged.
                self._on_activate(self.client)
                self._mode = None
                return 0
            self._mode = None
            return 0

        if msg == win32.WM_DESTROY:
            if self._thumb is not None:
                self._thumb.close()
                self._thumb = None
            return 0
        return None
