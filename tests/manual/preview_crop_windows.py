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

import importlib.util
import logging
import os
import time
from pathlib import Path

from PIL import Image, ImageDraw

from wingman.preview import layered, win32
from wingman.preview.geometry import Rect
from wingman.preview.thumbnail import Thumbnail
from wingman.preview.window import CLICK_PX, coalesce_moves, drag_target, resize_result

# tests/manual/preview_crop_model.py is a sibling harness module, not a
# package member -- the same reason tests/test_preview_crop_model.py loads
# it via importlib rather than a normal import. This gets PrototypeCropPicker
# the same map_selection/fit_within its own tests already cross-check
# against, without inventing a second copy of that arithmetic here.
_model_spec = importlib.util.spec_from_file_location(
    "preview_crop_model", Path(__file__).parent / "preview_crop_model.py"
)
_crop_model = importlib.util.module_from_spec(_model_spec)
_model_spec.loader.exec_module(_crop_model)
map_selection = _crop_model.map_selection
fit_within = _crop_model.fit_within

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
            # Thumbnail.register() already logged the raw DWM failure; this
            # adds the context that only the crop knows -- which client and
            # that the window is being torn down as a result.
            logger.warning(
                "Thumbnail registration failed for crop %s; destroying window",
                client.stable_key,
            )
            _CROPS.pop(int(self.hwnd), None)
            libs.user32.DestroyWindow(self.hwnd)
            self.hwnd = None
            return None
        hr = self._thumb.update(Rect(0, 0, rect.w, rect.h), source_rect=source_rect)
        if hr:
            # Same reasoning: Thumbnail.update() already logged the hr and
            # the raw rects, so this adds only the crop-level context.
            logger.warning(
                "Initial thumbnail update failed for crop %s (hr=0x%08x); tearing down",
                client.stable_key,
                hr & 0xFFFFFFFF,
            )
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
            if self._mode is not None:
                # A second button arriving while a gesture is already
                # armed. The reduced grammar has no chord (unlike
                # PreviewWindow's resize-all): the primary preview's own
                # chord support is exactly the complexity being left out
                # here, per the design doc's first-version exclusions.
                # Ignored rather than reclassified -- accepting it would
                # silently overwrite an in-flight resize with a fresh
                # "pending_left", and the button that started the resize
                # would then release into a switch it never asked for.
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
            if self._mode == "pending_left" and msg == win32.WM_LBUTTONUP:
                # The click that never dragged. Gated on the matching
                # button: a right-release arriving on a still-pending left
                # click (the second button was ignored above, not
                # reclassified) must clear the gesture without activating.
                self._on_activate(self.client)
                self._mode = None
                return 0
            self._mode = None
            return 0

        if msg == win32.WM_DESTROY:
            if self._thumb is not None:
                self._thumb.close()
                self._thumb = None
            if self.hwnd is not None:
                # Registry and handle cleared here too -- not only in
                # close() -- in case WM_DESTROY reaches this instance
                # through some route other than our own close(), such as
                # the OS destroying an owner. DestroyWindow is deliberately
                # NOT called from here: this handler runs *because*
                # DestroyWindow already happened (or is happening), and
                # calling it again would be the double-destroy this guards
                # against.
                _CROPS.pop(int(self.hwnd), None)
                self.hwnd = None
            return 0
        return None


# --- Prototype crop picker ------------------------------------------------
#
# A dedicated, enlarged view of one client's WHOLE area, for choosing which
# rectangle of it a crop will later mirror. Two HWNDs, not one:
#
#   - the picker itself is the DWM destination: an ordinary topmost tool
#     popup that, unlike PrototypeCropWindow, is NOT WS_EX_NOACTIVATE --
#     Enter and Escape must reach its WndProc, which requires it to be the
#     foreground/focused window once the user has clicked it.
#   - an owned, layered, WS_EX_TRANSPARENT popup rides above it and carries
#     only the selection mask/border bitmap. Same owned-overlay z-order
#     technique window.py uses for the character-name pill (see
#     PreviewWindow._ensure_label_overlay): an owned window always
#     composites above its owner, so no z-order management is needed, and
#     WS_EX_TRANSPARENT keeps every mouse gesture reaching the picker
#     underneath rather than the overlay.
#
# Fixed-size in Phase 0 -- "Picker resize while selecting" is an explicit
# first-version exclusion in the design doc, so there is no resize gesture
# here at all.

WM_KEYDOWN = 0x0100
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B

# The enlarged mirror's cap and the minimum clearance kept from the host
# monitor's edges when centering it -- see _center_in_monitor.
PICKER_MAX = (1200, 800)
PICKER_MARGIN = 40
# The selection rect's border: amber, 2px, opaque.
PICKER_BORDER = (255, 180, 0, 255)
PICKER_BORDER_PX = 2
# Alpha of the mask drawn over everything OUTSIDE the selection -- dark
# enough to read as "not kept" without hiding the mirrored client under it.
PICKER_MASK_ALPHA = 140

PICKER_CLASS = "WingmanPreviewCropPickerProbe"
# hwnd -> PrototypeCropPicker. A separate registry from _CROPS above,
# because the picker answers a different WndProc with a different message
# grammar (keyboard confirm/cancel, not the crop's reduced click grammar).
_PICKERS = {}

_PICKER_CLASS_REGISTERED = False


def _ensure_picker_class(libs):
    """Register the picker's window class once per process. Byte-for-byte
    the same pattern as _ensure_class above and window.py's own copy --
    see _ensure_class's docstring for why the duplication is deliberate."""
    global _PICKER_CLASS_REGISTERED
    if _PICKER_CLASS_REGISTERED:
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

    proc = win32.wndproc_type()(_dispatch_picker)
    win32._KEEPALIVE.append(proc)  # see win32._KEEPALIVE's comment
    cls = WNDCLASSW()
    cls.lpfnWndProc = proc
    cls.hInstance = libs.kernel32.GetModuleHandleW(None)
    cls.lpszClassName = PICKER_CLASS
    cls.hCursor = libs.user32.LoadCursorW(None, ctypes.c_wchar_p(0x7F00))
    libs.user32.RegisterClassW(ctypes.byref(cls))
    _PICKER_CLASS_REGISTERED = True


def _dispatch_picker(hwnd, msg, wparam, lparam):
    libs = win32.bind()
    self = _PICKERS.get(int(hwnd))
    if self is not None:
        handled = self._on_message(msg, wparam, lparam)
        if handled is not None:
            return handled
    return libs.user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def _client_point(lparam):
    """Client coords packed into lParam, signed the same way
    window._lparam_point decodes them: a drag that has moved past the
    picker's own top-left edge (input keeps arriving while the button is
    captured) yields negative values here, and map_selection's own clamp
    to the destination rect is what makes keeping them safe rather than
    rejecting them at this layer."""
    x = lparam & 0xFFFF
    y = (lparam >> 16) & 0xFFFF
    return (x - 0x10000 if x > 0x7FFF else x, y - 0x10000 if y > 0x7FFF else y)


def _center_in_monitor(monitor, size, margin):
    """Center *size* inside *monitor*, keeping at least *margin* clear on
    each edge the monitor can afford it on. A picker that does not fit even
    without margin is pinned to the monitor's origin rather than left
    hanging partly off-screen -- the same tradeoff geometry.clamp_to_monitors
    makes for previews, scoped here to one already-chosen monitor rather
    than a search across several."""
    w, h = size
    x = monitor.x + (monitor.w - w) // 2
    min_x, max_x = monitor.x + margin, monitor.right - margin - w
    x = monitor.x if max_x < min_x else min(max(x, min_x), max_x)
    y = monitor.y + (monitor.h - h) // 2
    min_y, max_y = monitor.y + margin, monitor.bottom - margin - h
    y = monitor.y if max_y < min_y else min(max(y, min_y), max_y)
    return Rect(x, y, w, h)


def _render_selection_overlay(size, selection):
    """The overlay's bitmap: a translucent dark mask over the whole
    picker, punched fully transparent inside *selection* with a thin
    amber border traced around it. A missing or degenerate *selection*
    (nothing dragged yet) draws the mask alone -- there is nothing yet to
    mark as kept."""
    w, h = size
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w - 1, h - 1], fill=(0, 0, 0, PICKER_MASK_ALPHA))
    if selection is not None and selection.w > 0 and selection.h > 0:
        box = [selection.x, selection.y, selection.right - 1, selection.bottom - 1]
        d.rectangle(box, fill=(0, 0, 0, 0))
        d.rectangle(box, outline=PICKER_BORDER, width=PICKER_BORDER_PX)
    return img


class PrototypeCropPicker:
    """A temporary, enlarged mirror of one client's whole area, for
    choosing the source rectangle a crop will later mirror.

    `source_size` is captured once, from GetClientRect at creation, and is
    never re-derived from it afterwards -- only re-READ, on confirmation,
    to check it still matches. A client that has changed shape in between
    is a cancellation (`client-resized`), not a guessed remap: Phase 0 has
    no basis for translating a selection drawn against one source shape
    onto a different one.

    Every method here runs on the preview thread, same thread-affinity
    contract as PrototypeCropWindow and PreviewWindow -- see their
    docstrings.
    """

    def __init__(self, libs, client, on_confirm, on_cancel):
        self._libs = libs
        self.client = client
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel
        self.hwnd = None
        self._overlay_hwnd = None
        self._thumb = None
        self._source_size = None
        self.rect = None
        self.selection = None
        self._dragging = False
        self._start = None
        self._completed = False

    @classmethod
    def create(cls, libs, client, monitor, on_confirm, on_cancel):
        """Creation order: read the source facts FIRST -- a failed or
        degenerate GetClientRect returns None before any HWND exists, so
        there is nothing to leak -- then the picker HWND, then its
        registry entry, then the overlay HWND, then DWM registration, then
        its first update. Any failure from the overlay onward tears down
        in overlay-then-DWM-then-HWND order, the same order close()
        (_close_resources) uses.
        """
        import ctypes

        self = cls(libs, client, on_confirm, on_cancel)
        client_rect = win32.RECT()
        if not libs.user32.GetClientRect(client.hwnd, ctypes.byref(client_rect)):
            return None
        w = client_rect.right - client_rect.left
        h = client_rect.bottom - client_rect.top
        if w <= 0 or h <= 0:
            return None
        self._source_size = (w, h)

        picker_size = fit_within(self._source_size, PICKER_MAX)
        self.rect = _center_in_monitor(monitor, picker_size, PICKER_MARGIN)

        _ensure_picker_class(libs)
        self.hwnd = libs.user32.CreateWindowExW(
            win32.WS_EX_TOOLWINDOW | win32.WS_EX_TOPMOST,
            PICKER_CLASS,
            "wingman-crop-picker",
            win32.WS_POPUP,
            self.rect.x,
            self.rect.y,
            self.rect.w,
            self.rect.h,
            None,
            None,
            libs.kernel32.GetModuleHandleW(None),
            None,
        )
        if not self.hwnd:
            logger.warning(
                "CreateWindowExW failed for crop picker %s", client.stable_key
            )
            return None
        _PICKERS[int(self.hwnd)] = self

        self._overlay_hwnd = libs.user32.CreateWindowExW(
            win32.WS_EX_LAYERED
            | win32.WS_EX_TRANSPARENT
            | win32.WS_EX_TOOLWINDOW
            | win32.WS_EX_NOACTIVATE,
            "STATIC",
            "",
            win32.WS_POPUP,
            self.rect.x,
            self.rect.y,
            self.rect.w,
            self.rect.h,
            self.hwnd,  # OWNER, not parent -- see the class docstring above
            None,
            libs.kernel32.GetModuleHandleW(None),
            None,
        )
        if not self._overlay_hwnd:
            logger.warning(
                "Overlay window failed for crop picker %s; destroying picker",
                client.stable_key,
            )
            _PICKERS.pop(int(self.hwnd), None)
            libs.user32.DestroyWindow(self.hwnd)
            self.hwnd = None
            return None
        # Same reasoning as PreviewWindow._ensure_label_overlay: WS_POPUP
        # alone creates the window hidden, and layered.push (mapped to
        # UpdateLayeredWindow) never changes visibility on its own.
        libs.user32.ShowWindow(self._overlay_hwnd, win32.SW_SHOWNOACTIVATE)

        self._thumb = Thumbnail.register(libs, self.hwnd, client.hwnd)
        if self._thumb is None:
            logger.warning(
                "Thumbnail registration failed for crop picker %s; destroying window",
                client.stable_key,
            )
            libs.user32.DestroyWindow(self._overlay_hwnd)
            self._overlay_hwnd = None
            _PICKERS.pop(int(self.hwnd), None)
            libs.user32.DestroyWindow(self.hwnd)
            self.hwnd = None
            return None
        # The picker mirrors the client's WHOLE area at its own enlarged
        # size -- the user selects a sub-region of THAT, so the DWM source
        # is the full client rect, not any particular crop's source_rect.
        hr = self._thumb.update(
            Rect(0, 0, self.rect.w, self.rect.h),
            source_rect=Rect(0, 0, w, h),
        )
        if hr:
            logger.warning(
                "Initial thumbnail update failed for crop picker %s "
                "(hr=0x%08x); tearing down",
                client.stable_key,
                hr & 0xFFFFFFFF,
            )
            self._thumb.close()
            self._thumb = None
            libs.user32.DestroyWindow(self._overlay_hwnd)
            self._overlay_hwnd = None
            _PICKERS.pop(int(self.hwnd), None)
            libs.user32.DestroyWindow(self.hwnd)
            self.hwnd = None
            return None

        libs.user32.ShowWindow(self.hwnd, win32.SW_SHOWNOACTIVATE)
        return self

    # -- selection -----------------------------------------------------
    def _update_selection(self, current):
        left, right = sorted((self._start[0], current[0]))
        top, bottom = sorted((self._start[1], current[1]))
        self.selection = Rect(left, top, right - left, bottom - top)
        img = _render_selection_overlay((self.rect.w, self.rect.h), self.selection)
        layered.push(self._libs, self._overlay_hwnd, img, self.rect.x, self.rect.y)

    # -- confirmation ----------------------------------------------------
    def _confirm(self):
        if self._completed or self.selection is None:
            return
        import ctypes

        client_rect = win32.RECT()
        if not self._libs.user32.GetClientRect(
            self.client.hwnd, ctypes.byref(client_rect)
        ):
            self._finish_cancel("client-unavailable")
            return
        w = client_rect.right - client_rect.left
        h = client_rect.bottom - client_rect.top
        if w <= 0 or h <= 0:
            self._finish_cancel("client-unavailable")
            return
        if (w, h) != self._source_size:
            # Phase 0 does not guess a remap against a client that has
            # changed shape since the picker opened -- see the class
            # docstring above and the design doc's exclusions.
            self._finish_cancel("client-resized")
            return
        source_rect = map_selection(
            self.selection, Rect(0, 0, self.rect.w, self.rect.h), self._source_size
        )
        if source_rect is None:
            return  # empty or below the minimum after clamping; keep open
        self._completed = True
        self._close_resources()
        self._on_confirm(self.client, source_rect)

    def _finish_cancel(self, reason):
        if self._completed:
            return
        self._completed = True
        self._close_resources()
        self._on_cancel(reason)

    # -- teardown --------------------------------------------------------
    def _close_resources(self):
        """Overlay, then DWM, then the picker HWND -- the order the brief
        specifies, and the reverse of create()'s success-path ordering
        above."""
        if self._overlay_hwnd is not None:
            self._libs.user32.DestroyWindow(self._overlay_hwnd)
            self._overlay_hwnd = None
        if self._thumb is not None:
            self._thumb.close()
            self._thumb = None
        if self.hwnd is not None:
            _PICKERS.pop(int(self.hwnd), None)
            self._libs.user32.DestroyWindow(self.hwnd)
            self.hwnd = None

    # -- input -----------------------------------------------------------
    def _on_message(self, msg, wparam, lparam):
        # The fixed grammar: left drag selects, Enter confirms, Escape or
        # WM_CLOSE cancels. No move, no resize -- the picker's own rect
        # never changes after create() (Phase 0 excludes picker resize).
        if msg == win32.WM_LBUTTONDOWN:
            self._start = _client_point(lparam)
            self._dragging = True
            self._libs.user32.SetCapture(self.hwnd)
            return 0
        if msg == win32.WM_MOUSEMOVE and self._dragging:
            self._update_selection(_client_point(lparam))
            return 0
        if msg == win32.WM_LBUTTONUP and self._dragging:
            self._update_selection(_client_point(lparam))
            self._dragging = False
            self._libs.user32.ReleaseCapture()
            return 0
        if msg == WM_KEYDOWN:
            if wparam == VK_RETURN:
                self._confirm()
            elif wparam == VK_ESCAPE:
                self._finish_cancel("cancelled")
            return 0
        if msg == win32.WM_CLOSE:
            self._finish_cancel("cancelled")
            return 0
        if msg == win32.WM_DESTROY:
            # Defensive, like PrototypeCropWindow's own WM_DESTROY handler:
            # this only clears bookkeeping for a destruction that reached
            # this instance through some route other than
            # _close_resources(), which already pops the registry, closes
            # the thumbnail and clears both HWND fields -- so a destruction
            # THIS class started never reaches here with anything left to
            # clear. DestroyWindow is deliberately not called again from
            # here for the same reason PrototypeCropWindow's handler
            # does not: that would be the double-destroy being guarded
            # against.
            if self._thumb is not None:
                self._thumb.close()
                self._thumb = None
            self._overlay_hwnd = None
            if self.hwnd is not None:
                _PICKERS.pop(int(self.hwnd), None)
                self.hwnd = None
            return 0
        return None
