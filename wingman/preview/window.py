"""One preview window: an HWND, its chrome, and its thumbnail.

The gesture arithmetic at the top is pure and tested in CI. Everything
below it touches HWNDs and therefore may only run on the preview thread.
"""

import logging
import os
import time
from enum import Enum, auto

from ..alerts import state as alerts_state
from . import alertframes, chrome, geometry, layered, win32
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
PERF = os.environ.get("WINGMAN_PREVIEW_PERF", "").strip() == "1"

MIN_SIZE = (120, 90)
BORDER = 2
# How far the cursor must travel before a held left button stops being a
# click and becomes a drag. Pixels, in screen space, radius not components.
CLICK_PX = 4


def resize_result(start, current, rect, min_size=MIN_SIZE, aspect=None, chrome=(0, 0)):
    """New rect for a resize drag. Top-left is the anchor and never moves.

    With *aspect* set, the PICTURE keeps that shape and *chrome* says how
    many pixels of the window are not picture. With aspect None the result
    is what it has always been -- which is also the fallback when the
    client's rect cannot be read.
    """
    dx, dy = current[0] - start[0], current[1] - start[1]
    w, h = rect.w + dx, rect.h + dy
    if aspect:
        # The axis the pointer actually travelled furthest along is the one
        # believed; the other is derived from it. Deciding here rather than
        # in lock_to_aspect is not an arrangement of convenience -- this is
        # the only place the deltas exist at all. The rect alone cannot say
        # which way the user dragged, and guessing from it is what left the
        # handle dead for every inward drag.
        #
        # Known consequence, accepted: on a start rect that is ALREADY at
        # the locked ratio both branches agree at |dx| == |dy|, so the
        # gesture is smooth. On one that is not, crossing that point jumps
        # the window in a single WM_MOUSEMOVE -- measured at 145px wide
        # from a 700x300 rect with a 16:9 client. Three ways to be holding
        # such a rect: a deliberately mismatched `Size...` (the documented
        # escape hatch), a layout saved before the lock existed, and
        # unchecking lock_aspect, dragging freeform, then re-checking it.
        # The first locked drag corrects the rect, after which it cannot
        # recur for that preview. Left alone rather than smoothed because
        # every alternative either reintroduces an axis that ignores the
        # pointer or makes the handle's behaviour depend on drag history.
        drive = "w" if abs(dx) >= abs(dy) else "h"
        w, h = geometry.lock_to_aspect(w, h, aspect, chrome, min_size, drive)
        return rect._replace(w=w, h=h)
    return rect._replace(w=max(min_size[0], w), h=max(min_size[1], h))


class ActivationResult(Enum):
    ACTIVATED = auto()
    PENDING_RESTORE = auto()
    PENDING_FOREGROUND = auto()
    REFUSED = auto()


def activate_attached(libs, hwnd, source_hwnd) -> ActivationResult:
    """Try activation with the source and target input queues attached."""
    if libs.user32.IsIconic(hwnd):
        libs.user32.ShowWindowAsync(hwnd, win32.SW_RESTORE)
        return ActivationResult.PENDING_RESTORE
    our_tid = libs.kernel32.GetCurrentThreadId()
    source_tid = libs.user32.GetWindowThreadProcessId(source_hwnd, None)
    target_tid = libs.user32.GetWindowThreadProcessId(hwnd, None)

    attached = []
    try:
        # Source and target HWNDs can share an input queue; attaching the same
        # thread twice would require matching duplicate detach calls.
        for tid in dict.fromkeys((source_tid, target_tid)):
            if (
                tid
                and tid != our_tid
                and libs.user32.AttachThreadInput(our_tid, tid, True)
            ):
                attached.append(tid)
        libs.user32.SetForegroundWindow(hwnd)
        foreground = libs.user32.GetForegroundWindow() or 0
        if foreground == hwnd:
            # Direct activation deliberately has no SetFocus: keep this repair
            # in the fallback slot where the target queue is attached.
            libs.user32.SetFocus(hwnd)
    finally:
        # Every successful attachment must be detached exactly once in reverse
        # order, including when a foreground API raises.
        for tid in reversed(attached):
            libs.user32.AttachThreadInput(our_tid, tid, False)

    if foreground == hwnd:
        return ActivationResult.ACTIVATED

    # INFO, not DEBUG: the root logger runs at INFO, so this remains visible in
    # the log a user sends for the field complaint "clicking does nothing".
    logger.info(
        "Activation of 0x%x did not take; foreground is 0x%x. "
        "Windows refuses a foreground change from a process "
        "that has not received recent user input.",
        hwnd,
        foreground,
    )
    return ActivationResult.REFUSED


def activate(libs, hwnd) -> ActivationResult:
    """Request foreground directly, using attachment only after refusal."""
    if libs.user32.IsIconic(hwnd):
        # ShowWindowAsync only requests restoration. Let the host retry after
        # IsIconic clears rather than racing foreground work with restoration.
        libs.user32.ShowWindowAsync(hwnd, win32.SW_RESTORE)
        return ActivationResult.PENDING_RESTORE

    source = libs.user32.GetForegroundWindow() or 0
    if source == hwnd:
        return ActivationResult.ACTIVATED

    libs.user32.SetForegroundWindow(hwnd)
    foreground = libs.user32.GetForegroundWindow() or 0
    if foreground == hwnd:
        return ActivationResult.ACTIVATED
    if foreground == 0:
        return ActivationResult.PENDING_FOREGROUND
    return activate_attached(libs, hwnd, source)


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

    # Class-level so a preview created before the first restyle still has
    # it. Pushed live by PreviewHost._restyle, like show_labels and locked.
    snap = True
    lock_aspect = True
    # The selection ring's colour, #rrggbb. Class-level for the same
    # reason; the default is the cyan this module hardcoded until the
    # setting existed, so a preview created before the first restyle draws
    # exactly what it always drew.
    selection_color = "#00c8dc"

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
        snap=True,
        lock_aspect=True,
        selection_color="#00c8dc",
        on_resize_all=None,
    ):
        self._libs = libs
        self.client = client
        self.rect = rect
        # Restored from the saved layout, not assumed False: a preview the
        # user locked must still be locked after a restart, and reporting
        # locked=False on the next drag would erase the flag.
        self.locked = locked
        # Set once from the host at creation; the live restyle path lets this
        # change on an already-open window.
        self.show_labels = show_labels
        # A DWM thumbnail property, not a bitmap one -- see the note on
        # _chrome_key() below. Set once at creation; the live restyle path lets
        # this change on an already-open window.
        self.opacity = opacity
        # Set once from the host at creation; PreviewHost._restyle pushes
        # live updates, like show_labels and locked.
        self.snap = snap
        # Whether the resize handle holds the client's shape. Read once per
        # drag rather than per mouse-move, at the same point _start_aspect
        # is sampled -- flipping the setting mid-drag must not change the
        # gesture already in flight under the user's hand.
        self.lock_aspect = lock_aspect
        # A string, not a tuple: it is the settings representation
        # verbatim, parsed per redraw (once per repaint, not per
        # mouse-move) so no second parsed copy can drift from it.
        self.selection_color = selection_color
        self.selected = False
        # Whether hide-on-lost-focus currently has this window off screen.
        # Not a saved setting and not per character: the host recomputes it
        # for every preview on every sweep, and a new window is always
        # created visible -- _apply_visibility hides it on the same sweep
        # if the foreground says so.
        self.hidden = False
        # Whether the client owns the foreground right now, as opposed to
        # `selected` above, which is the sticky ring. Only the alerts read
        # it; see set_focused.
        self.focused = False
        self._perf = None
        # Last key rendered; None forces the first draw.
        self._chrome_cache_key = None
        self._on_activate = on_activate
        self._on_rect_changed = on_rect_changed
        # Supplied by the host: called with this window's rect on every
        # coalesced move of a resize-all chord, so the host can mirror the
        # size onto every OTHER preview. Runs on the preview thread (this
        # wndproc's thread), the only thread allowed to touch those
        # windows -- see the class docstring.
        self._on_resize_all = on_resize_all
        # Supplied by the host, which is the only thing that knows about
        # sibling previews. Without it snap() sees screen edges only and
        # preview-to-preview snapping silently does nothing.
        self._neighbours = neighbours
        # Supplied, not computed here: the host re-reads it each sweep so
        # a monitor added or rearranged mid-session is picked up.
        self._screen = screen
        self.hwnd = None
        self._thumb = None
        # The character-name overlay window's HWND, or None. See
        # _ensure_label_overlay for why the name is a window at all.
        self._label_hwnd = None
        self._label_img = None
        self._label_key = None
        # The thumbnail's inset from the window edge. Normally BORDER, but
        # an armed alert widens it to ALERT_BORDER for the duration: the
        # thumbnail overpaints the ring everywhere it covers, so a 6px ring
        # inside a 2px inset renders as corner brackets (measured; see
        # docs/preview-roadmap.md). Stored rather than passed, so the two
        # existing thumbnail_rect call sites cannot drift from it.
        self._inset = BORDER
        self._alert = None
        self._frames = None
        self._frames_dirty = False
        self._mode = None
        self._start = None
        self._start_rect = None
        self._start_aspect = None
        self._start_chrome = (0, 0)

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
        snap=True,
        lock_aspect=True,
        selection_color="#00c8dc",
        on_resize_all=None,
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
            snap,
            lock_aspect,
            selection_color,
            on_resize_all,
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
                geometry.thumbnail_rect(self.rect, self._inset),
                self.opacity,
            )
        # After the preview itself exists: the overlay is owned by it.
        self._ensure_label_overlay()
        return self

    # -- rendering -------------------------------------------------------
    def _source_aspect(self):
        """The client area's width/height, or None if it cannot be read.

        None is routine rather than exceptional: a client sitting at character
        select, or one that quit mid-drag, has a degenerate rect. The handle
        falls back to a freeform resize rather than freezing.
        """
        import ctypes

        rect = win32.RECT()
        if not self._libs.user32.GetClientRect(self.client.hwnd, ctypes.byref(rect)):
            return None
        w, h = rect.right - rect.left, rect.bottom - rect.top
        if w <= 0 or h <= 0:
            return None
        return w / h

    def _chrome_key(self):
        # opacity deliberately does NOT belong here. It is a DWM thumbnail
        # property (Thumbnail.update's DWM_TNP_OPACITY), never a pixel in
        # this bitmap, so including it would force a ~67k-pixel re-render
        # on every opacity change for no visual reason -- the exact cost
        # redraw()'s short-circuit exists to avoid.
        return (
            self.rect.w,
            self.rect.h,
            self.selected,
            # For the same reason as below: without the colour here, a
            # recolour is a no-op on every already-open preview.
            self.selection_color,
        )

    def _border_color(self):
        """The selection ring's RGBA, parsed from the #rrggbb setting.

        Called once per redraw, never per mouse-move. Falls back to the
        shipped cyan rather than raising: the value arrives from
        settings, which validated_preview has already screened, so an
        unparsable string here means a settings file edited by hand --
        and a ring in the wrong colour beats a preview subsystem that
        died mid-drag.
        """
        try:
            return (
                int(self.selection_color[1:3], 16),
                int(self.selection_color[3:5], 16),
                int(self.selection_color[5:7], 16),
                255,
            )
        except (TypeError, ValueError):
            return (0, 200, 220, 255)

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
        img = chrome.render(
            (self.rect.w, self.rect.h),
            border_color=self._border_color(),
            border=BORDER,
            selected=self.selected,
        )
        layered.push(self._libs, self.hwnd, img, self.rect.x, self.rect.y)
        self._chrome_cache_key = key

    # -- the character-name overlay --------------------------------------
    #
    # The name CANNOT be drawn into the chrome bitmap: the DWM thumbnail
    # composites OVER it, so anything drawn where the video goes is
    # invisible. The band this replaces had to reserve space at the top
    # and shrink the picture to make room -- which also bent the locked
    # aspect, because 30px of chrome is a different fraction of every
    # height. EVE-O Preview instead overlays the name, and so do we: a
    # tiny WS_EX_LAYERED|WS_EX_TRANSPARENT window, OWNED by the preview
    # (an owned window always composites above its owner, so no z-order
    # work), click-through by style so every mouse gesture reaches the
    # preview underneath, carrying one small pill bitmap.
    def _label_text(self) -> str:
        return self.client.character or self.client.title

    def set_labels(self, shown: bool) -> None:
        """Show or hide the name overlay. Idempotent, like every setter
        the host calls per restyle."""
        self.show_labels = bool(shown)
        if shown:
            self._ensure_label_overlay()
        else:
            self._destroy_label_overlay()

    def _ensure_label_overlay(self) -> None:
        if not self.show_labels or self.hwnd is None:
            return
        if self._label_hwnd is None:
            self._label_hwnd = self._libs.user32.CreateWindowExW(
                win32.WS_EX_LAYERED
                | win32.WS_EX_TRANSPARENT
                | win32.WS_EX_TOOLWINDOW
                | win32.WS_EX_NOACTIVATE,
                "STATIC",
                "",
                win32.WS_POPUP,
                0,
                0,
                0,
                0,
                # The OWNER, not a parent: this is how the overlay stays
                # above the preview without ever holding the foreground
                # or fighting it for z-order.
                self.hwnd,
                None,
                self._libs.kernel32.GetModuleHandleW(None),
                None,
            )
            if not self._label_hwnd:
                logger.warning("Label overlay window failed for %s", self._label_text())
                return
            # WS_POPUP alone creates the window HIDDEN, and the bitmap
            # push below maps to UpdateLayeredWindow, which does NOT
            # change visibility -- the chrome window shows itself the same
            # explicit way. This call is why the pill exists on screen at
            # all; without it the overlay is a perfectly rendered bitmap
            # on a window that is never mapped.
            self._libs.user32.ShowWindow(self._label_hwnd, win32.SW_SHOWNOACTIVATE)
        self._sync_label()

    def _sync_label(self) -> None:
        """(Re)render, paint and position the overlay. No-op without one.

        Called on every move: the push is an UpdateLayeredWindow on a
        pill-sized bitmap (a few thousand pixels, against chrome's
        ~67k), and the render is cache-keyed on the pill's OWN size --
        measured per move with label_size(), no pixels drawn -- so a
        drag re-renders only when the width crosses the ellipsize
        threshold.
        """
        if self._label_hwnd is None:
            return
        label = self._label_text()
        max_w = self.rect.w - self._inset * 2
        size = chrome.label_size(label, max_w)
        if size != self._label_key:
            self._label_img = chrome.render_label(label, max_w)
            self._label_key = size
        if self._label_img is None:
            self._libs.user32.ShowWindow(self._label_hwnd, win32.SW_HIDE)
            return
        layered.push(
            self._libs,
            self._label_hwnd,
            self._label_img,
            self.rect.x + self._inset,
            self.rect.y + self._inset,
        )

    def _destroy_label_overlay(self) -> None:
        if self._label_hwnd is None:
            return
        self._libs.user32.DestroyWindow(self._label_hwnd)
        self._label_hwnd = None

    def set_hidden(self, hidden: bool) -> None:
        """Take this preview off the screen, or put it back.

        ShowWindow rather than a destroy: hide-on-lost-focus fires on every
        alt-tab, and closing the window would re-run rect resolution and
        DwmRegisterThumbnail several times a minute. The window keeps its
        position, its thumbnail and its layered bitmap while hidden, so
        coming back is one ShowWindow.

        SW_SHOWNOACTIVATE on the way back, matching create(): these windows
        are WS_EX_NOACTIVATE precisely so they never take the foreground
        from the client being flown, and a plain SW_SHOW would hand it to
        them on every return.

        TriffView parks its overlay at Opacity 0 instead
        (TriffViewSubsystem.cs:4222). That is not available here: it has
        one overlay window and we have one per client, and
        SetLayeredWindowAttributes is unusable on these windows -- it dims
        the chrome and the thumbnail together and then fails every
        subsequent UpdateLayeredWindow (alertframes.py:14-18).

        Idempotent, like set_selected/set_focused and for the same reason:
        the host applies this to every window on every sweep.
        """
        if hidden == self.hidden:
            return
        self.hidden = hidden
        # NOT for a failed CreateWindowExW: create() returns None there
        # (window.py's `if not self.hwnd`) and the host only stores a
        # window that is not None, so that one never reaches this method.
        # This guards the other direction -- close() nulls hwnd after
        # DestroyWindow -- and the tests, which construct windows directly
        # without ever creating a real one.
        if self.hwnd is None:
            return
        self._libs.user32.ShowWindow(
            self.hwnd, win32.SW_HIDE if hidden else win32.SW_SHOWNOACTIVATE
        )
        # The overlay with it: an owned window does not follow the owner
        # into hiding, so a hidden preview would leave its name floating
        # over whatever moved into that space.
        if self._label_hwnd is not None:
            self._libs.user32.ShowWindow(
                self._label_hwnd,
                win32.SW_HIDE if hidden else win32.SW_SHOWNOACTIVATE,
            )

    def set_selected(self, selected: bool) -> None:
        """Draw or drop the ring. Cosmetic only -- see set_focused for the
        half of this that used to live here."""
        if selected == self.selected:
            return
        self.selected = selected
        # Already part of _chrome_key() above, so this repaints.
        self.redraw()

    def set_focused(self, focused: bool) -> None:
        """Record whether this client actually owns the foreground.

        Nothing about this is visible: the ring follows `selected`, which
        is sticky and stays on the last client used. What hangs off this
        flag is the alerts, and both directions matter.

        Taking the foreground is what acknowledges a persistent alert, and
        this is the ONLY place that catches every route to a client:
        clicking the preview, a cycle keybind, and plain alt-tab all end up
        here through the foreground hook. Acknowledging in the click
        handler alone would leave a ring pulsing forever for anyone who
        switched clients any other way.

        Losing it matters just as much. This flag is what arm_alert reads
        as "you are already looking at this client, so the alert need not
        persist" -- so it has to go false the moment you tab out to a
        browser, or an alert on the client you last used would count as
        seen and expire while you were reading something else. The ring
        was that signal until it went sticky; splitting the two is what
        let it.
        """
        if focused == self.focused:
            return
        self.focused = focused
        if focused:
            self.acknowledge_alert()

    # -- alerts ----------------------------------------------------------
    def _set_inset(self, px: int) -> None:
        """Move the thumbnail's edge. Two calls per alert -- arm and clear
        -- never one per tick."""
        if px == self._inset:
            return
        self._inset = px
        if self._thumb is not None:
            self._thumb.update(geometry.thumbnail_rect(self.rect, px), self.opacity)
        # The pill rides the inset's inner corner, so an armed alert's
        # wider ring nudges it in by the same pixels.
        self._sync_label()

    def _rebuild_frames(self) -> None:
        """Drop any cached frames and render the current alert's."""
        if self._frames is not None:
            self._frames.close(self._libs)
            self._frames = None
        self._frames_dirty = False
        if self._alert is None:
            return
        self._frames = alertframes.FrameCache.build(
            self._libs,
            (self.rect.w, self.rect.h),
            self._alert.color,
        )

    def _invalidate_frames(self) -> None:
        """Free the frames and ask the next tick to rebuild them.

        Distinct from `_frames is None` meaning "build failed": that must
        NOT be retried every 80ms, since the way it fails is GDI handle
        exhaustion and the retry is six Pillow renders. This flag is the
        only thing that asks for a rebuild.
        """
        if self._frames is not None:
            self._frames.close(self._libs)
            self._frames = None
        self._frames_dirty = True

    def arm_alert(self, event: str, spec: dict, now: float) -> None:
        pulses = spec.get("pulses", 3)
        self._alert = alerts_state.arm(
            self._alert,
            event,
            spec.get("color", "#ff4d4d"),
            now,
            # DERIVED here, and only here. The spec carries how many
            # flashes the event gets and how fast each one is; the
            # duration is their product. Both paths that raise an alert --
            # the poll thread through PreviewHost._apply_alerts, and
            # api.test_alert -- arrive at this method, so deriving at this
            # one site is what keeps the stored pair the only source of
            # truth for how long a ring pulses.
            duration_ms=alerts_state.duration_for(spec.get("flash_rate"), pulses),
            pulses=pulses,
            # Global, not per-event: persist_until_selected lives beside
            # `events` in the alerts section, and AlertService merges it
            # into the spec it dispatches so this stays one dict.
            persist=bool(spec.get("persist_until_selected")),
            # `focused`, NOT `selected`: the ring is sticky and survives a
            # trip to a browser, and passing it here would make every alert
            # on the client you last used non-persistent -- expiring in its
            # 1200ms while you are looking at something else. The setting is
            # still named persist_until_selected in settings and on the
            # Alerts card; "selected" there means "you switched to it",
            # which is this flag.
            target_is_selected=self.focused,
        )
        # Size and colour: the frames ARE a bitmap, keyed the same way
        # chrome's is. (The label no longer is one of their inputs -- a
        # frame carries no name, and the overlay rides above the pulses
        # unchanged.) `arm` can also return the EXISTING alert unchanged
        # (a lower-severity event extends the expiry without repainting),
        # in which case nothing has changed and the cache stands.
        stale = self._frames is None or (
            self._frames.colour != self._alert.color
            or self._frames.size != (self.rect.w, self.rect.h)
        )
        if stale:
            self._rebuild_frames()
        # Outside the `if`: the inset must widen on every arm, not only on
        # the arms that happen to rebuild. The two were coupled by
        # coincidence (frames are None exactly when the inset is BORDER)
        # with nothing asserting the coupling.
        self._set_inset(alertframes.ALERT_BORDER)

    def tick_alert(self, now: float) -> bool:
        """Push the current phase. Returns False when the alert is done."""
        self._alert = alerts_state.clear_expired(self._alert, now)
        if self._alert is None:
            self.clear_alert()
            return False
        if self._frames_dirty:
            self._rebuild_frames()
        if self._frames is None:
            # Frames failed to build (GDI exhaustion). Nothing can be
            # drawn, so stop claiming to be armed rather than spinning the
            # 80ms timer forever on a window that will never flash. Not
            # retried: the retry is six Pillow renders against the
            # resource that just ran out.
            logger.warning(
                "Alert frames unavailable for %s; clearing the alert",
                self.client.stable_key,
            )
            self.clear_alert()
            return False
        self._frames.push(
            self._libs, self.hwnd, self.rect, alerts_state.frame_index(self._alert, now)
        )
        return True

    def _free_frames(self) -> None:
        """Release the DIBs without repainting. Split out for close(),
        which is about to destroy the window: a redraw and a thumbnail
        update there would be work on a surface nobody will see again."""
        if self._frames is not None:
            self._frames.close(self._libs)
            self._frames = None
        self._frames_dirty = False
        self._alert = None

    def clear_alert(self) -> None:
        if self._alert is None and self._frames is None:
            return
        self._free_frames()
        self._set_inset(BORDER)
        # force=True: pushing alert frames does not change _chrome_key, so
        # redraw() would early-return and the last alert frame would stay
        # on screen for the life of the preview.
        self.redraw(force=True)

    def alert_is_armed(self) -> bool:
        return self._alert is not None

    def acknowledge_alert(self) -> bool:
        """Clear a PERSISTENT alert. A timed one is left to expire, so
        selecting a client does not cut short a ring that just appeared."""
        if self._alert is None:
            return False
        if alerts_state.acknowledge(self._alert) is None:
            self.clear_alert()
            return True
        return False

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
        # The overlay is a separate HWND in SCREEN coordinates, so unlike
        # the thumbnail it must be re-placed on a pure move too.
        self._sync_label()
        if resized:
            # The bitmap is sized to the window, so a resize must re-push
            # it or the surface stays at the old dimensions.
            self.redraw()
            if self._thumb is not None:
                self._thumb.update(
                    geometry.thumbnail_rect(rect, self._inset),
                    self.opacity,
                )
            # The cached alert frames are sized to the OLD rect, and
            # UpdateLayeredWindow takes its size from the image -- so a
            # stale frame does not merely look wrong, it snaps the window
            # back to the armed size, fighting the drag at 12Hz.
            #
            # Invalidated, NOT rebuilt here: this runs once per
            # WM_MOUSEMOVE, and a rebuild is up to six Pillow renders --
            # "the cost that made dragging stutter" all over again. The
            # next tick rebuilds once, so a drag costs one rebuild per
            # 80ms instead of one per mouse event.
            if self._alert is not None:
                self._invalidate_frames()

    # -- input -----------------------------------------------------------
    def _on_message(self, msg, wparam, lparam):
        # The button grammar, when previews are NOT locked in place:
        #
        #   left click            -> switch to the client (selected ring)
        #   left drag             -> move this preview
        #   right drag            -> resize this preview
        #   left+right drag       -> resize EVERY preview at once
        #   corner-handle drag    -> resize this preview (kept: it is the
        #                             one visibly discoverable affordance)
        #
        # LOCKED, the grammar collapses to what a lock promises -- nothing
        # about WHERE a preview sits or HOW BIG it is may change by mouse:
        # no move, no resize, no chord. The payoff is performance: with
        # every drag gesture refused outright, a locked left press IS a
        # click from the first instant, so the switch fires on the way
        # down (#123's original shape) and no click pays the 60-120ms
        # classification delay the unlocked grammar needs.
        if msg in (win32.WM_LBUTTONDOWN, win32.WM_RBUTTONDOWN):
            if self.locked:
                # A locked left press is a switch and nothing else. A
                # locked right press is nothing at all.
                if msg == win32.WM_LBUTTONDOWN:
                    # Acknowledged BEFORE the handoff, and regardless of
                    # whether the switch that follows succeeds: Windows
                    # refuses a foreground change from a process without
                    # recent input, so acknowledging only on a successful
                    # swap would leave the ring pulsing forever with
                    # clicking it doing nothing.
                    self.acknowledge_alert()
                    self._on_activate(self.client)
                return 0
            pt = _lparam_point(lparam)
            if self._mode is not None:
                # The SECOND button of the chord. Whichever gesture the
                # first button armed, both-buttons now means resize-all.
                # Re-anchoring to the CURRENT rect and cursor is what
                # keeps the window from jumping: the original anchors
                # describe a press that happened before this button, and
                # a resize computed against them teleports the window to
                # wherever that drag would by now have gone.
                self._start_rect = self.rect
                self._start = _cursor_pos(self._libs)
                self._mode = "resize_all"
                return 0
            resizing = msg == win32.WM_LBUTTONDOWN and geometry.hit_resize_handle(
                geometry.Rect(0, 0, self.rect.w, self.rect.h), *pt
            )
            if msg == win32.WM_LBUTTONDOWN:
                self._mode = "resize" if resizing else "pending_left"
            else:
                # Right is resize now, not move: left took over movement
                # because a move is the gesture you want near the preview
                # you are looking at, and a resize is the one you want a
                # deliberate second button for.
                self._mode = "resize"
            # Client coords are only safe HERE: the window has not moved
            # yet, so they still describe the point that was clicked.
            self._start_rect = self.rect
            self._start = _cursor_pos(self._libs)
            # Sampled once per drag, never per WM_MOUSEMOVE: that handler
            # has a documented stutter history and a WINGMAN_PREVIEW_PERF
            # harness built to measure it, and a syscall per mouse move is
            # the cost that harness exists to catch.
            # None is already the freeform path -- it is what a client at
            # character select or one gone mid-drag produces -- so the
            # unlock reuses it rather than adding a second branch to
            # resize_result. The syscall is skipped entirely when unlocked.
            self._start_aspect = self._source_aspect() if self.lock_aspect else None
            # Borders only, never a label term: the name is an overlay
            # now, so the window's chrome is the same with labels on or
            # off and a locked resize holds the client's shape exactly.
            self._start_chrome = (BORDER * 2, BORDER * 2)
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
            # GetCursorPos, not lParam: lParam is client-relative and the
            # window is moving under the cursor, which is what made this
            # oscillate. Absolute coordinates cannot feed back.
            cur = _cursor_pos(self._libs)
            if self._mode == "pending_left":
                dx, dy = cur[0] - self._start[0], cur[1] - self._start[1]
                if dx * dx + dy * dy < CLICK_PX * CLICK_PX:
                    return 0
                # A drag, not a click -- and the switch that a click would
                # have earned is now cancelled, deliberately: dragging a
                # preview around is not a request to bring its client
                # forward. (A locked preview never reaches this branch at
                # all: its press switched on the way down.)
                self._mode = "move"
            if self._mode in ("resize", "resize_all"):
                self.move(
                    resize_result(
                        self._start,
                        cur,
                        self._start_rect,
                        aspect=self._start_aspect,
                        chrome=self._start_chrome,
                    )
                )
                if self._mode == "resize_all" and self._on_resize_all is not None:
                    # The host mirrors the finished size onto every OTHER
                    # preview; this window has already moved above. Called
                    # per coalesced move, the same budget dragging spends.
                    self._on_resize_all(self.rect)
            else:
                moved = drag_target(self._start, cur, self._start_rect)
                if self.snap:
                    moved = geometry.snap(moved, self._neighbours(), self._screen())
                self.move(moved)
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
            if self._mode == "pending_left":
                # The click that never dragged. Acknowledged BEFORE the
                # handoff, and regardless of whether the switch that
                # follows succeeds: Windows refuses a foreground change
                # from a process without recent input, so acknowledging
                # only on a successful swap would leave the ring pulsing
                # forever with clicking it doing nothing.
                self.acknowledge_alert()
                # Classify, then hand off: the window does NOT call
                # activate() itself. The host owns the switch because it
                # is the only thing that knows the previous foreground,
                # the roster and the settings -- and it has to know them
                # BEFORE the foreground moves.
                self._on_activate(self.client)
                self._mode = None
                return 0
            self._mode = None
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
        unregistering after DestroyWindow leaves DWM holding a dead HWND.
        The overlay last: it is owned by this window and Windows destroys
        owned windows with their owner, but doing it explicitly keeps the
        HWND bookkeeping honest and the destruction order legible."""
        # Before anything is destroyed: a client that quits mid-alert
        # otherwise leaks one DC and up to six DIBs for the life of the
        # process, and a fleet-wide aggression arms every preview at once.
        self._free_frames()
        self._release_thumb()
        if self.hwnd:
            _WINDOWS.pop(int(self.hwnd), None)
            self._libs.user32.DestroyWindow(self.hwnd)
            self.hwnd = None
        self._destroy_label_overlay()
