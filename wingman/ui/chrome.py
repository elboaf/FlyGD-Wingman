"""Native window chrome: the resize border a frameless window does not get.

`ui/window.py` asks for `frameless=True`, which pywebview maps to
`FormBorderStyle.None` (6.2.1, platforms/winforms.py:269). That removes the
whole non-client frame, so Windows has nothing to hit-test and the window
cannot be resized. `resizable` is left at its `True` default throughout and
is not the cause.

This module gives the border back by answering WM_NCHITTEST from a
subclassed WndProc. Two facts from the spike shape everything here:

  * WM_NCHITTEST goes to the window UNDER THE CURSOR. pywebview docks the
    WebView2 control DockStyle.Fill and calls BringToFront
    (platforms/edgechromium.py:95-100), and frameless means the client area
    is the whole window -- so the Chromium child covers every border pixel
    and the parent sees NOTHING. Measured: zero hit-tests reached the form
    while a human dragged the edges. The control MUST be inset first; that
    is `window.py`'s job, and without it this module is decoration.
  * MinimumSize survives only if WM_GETMINMAXINFO chains to the original
    proc BEFORE the max fields are overridden. WinForms fills in
    ptMinTrackSize there. Reversed, min_size is silently discarded.

Why the Win32 types are built lazily rather than at module scope:
`ctypes.WINFUNCTYPE` and most of `ctypes.wintypes` do not exist off
Windows, and this module has to import cleanly on the Linux box that runs
the tests -- `hit_code` below is the only part of this feature CI can
cover, and it would get none if the import raised. `hit_code` therefore
depends on no ctypes type at all.

KNOWN LIMITATION: half-snap does not work. Verified on a real build --
Win+Up maximizes, Win+Left and Win+Right do nothing. Maximize needs
WS_MAXIMIZEBOX, which WinForms still sets; snapping needs WS_THICKFRAME,
which FormBorderStyle.None removes, so Windows does not consider the
window snappable however it hit-tests. Nothing here can recover it: it
would take WM_NCCALCSIZE to carve a real non-client frame, or giving up
`frameless` and taking the OS title bar back. Do not spend time trying to
fix it from this file.
"""

import ctypes
import logging
import sys
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Hit-test results. Values are Win32's, not ours.
HTLEFT, HTRIGHT = 10, 11
HTTOP, HTTOPLEFT, HTTOPRIGHT = 12, 13, 14
HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 15, 16, 17

WM_NCHITTEST = 0x0084
WM_GETMINMAXINFO = 0x0024
GWLP_WNDPROC = -4
MONITOR_DEFAULTTONEAREST = 2

# Grab thickness in LOGICAL pixels, scaled per window DPI at hit-test time.
# BORDER must never exceed INSET -- beyond the inset the WebView2 child owns
# the pixels and no hit-test arrives, so the extra reach would be dead.
# tests/test_chrome.py enforces that.
BORDER = 6
CORNER = 14

# How far the WebView2 is inset, in the same logical units as BORDER, and
# scaled by the same factor at attach time. Measured at 6: on a 4K/200%
# display this produces a 12-physical-pixel band, which is what hit_code
# then looks for.
INSET = 6

ALL_EDGES = frozenset({"left", "right", "top", "bottom"})
HORIZONTAL_EDGES = frozenset({"left", "right"})


@dataclass(frozen=True)
class ResizeInsets:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def horizontal(self) -> int:
        return self.left + self.right


def hit_code(rect, x, y, scale=1.0, *, edges=ALL_EDGES):
    """Which resize zone (x, y) falls in under *edges*, or None.

    *rect* is (left, top, right, bottom) in screen pixels, as GetWindowRect
    reports it. *x* and *y* are screen pixels. *scale* is the window's
    DPI scale, so the band stays the same apparent thickness at 150%.

    Returning None means "not mine": the caller must fall through to the
    original WndProc so the client area keeps behaving normally, or the
    page stops receiving the mouse entirely.

    Corners are checked first, and against a longer reach than the edges,
    so the diagonal grab is not a BORDER-sized square nobody can hit. If an
    edge is disabled, any corner that depends on it is disabled too -- on a
    horizontal-only window the top-left corner is still a LEFT resize, not
    a diagonal that would imply vertical movement.
    """
    left, top, right, bottom = rect
    border = max(1, int(BORDER * scale))
    corner = max(border, int(CORNER * scale))

    allow_left = "left" in edges
    allow_right = "right" in edges
    allow_top = "top" in edges
    allow_bottom = "bottom" in edges

    on_left = allow_left and x < left + border
    on_right = allow_right and x >= right - border
    on_top = allow_top and y < top + border
    on_bottom = allow_bottom and y >= bottom - border

    near_left = allow_left and x < left + corner
    near_right = allow_right and x >= right - corner
    near_top = allow_top and y < top + corner
    near_bottom = allow_bottom and y >= bottom - corner

    if allow_top and allow_left and ((on_top and near_left) or (on_left and near_top)):
        return HTTOPLEFT
    if (
        allow_top
        and allow_right
        and ((on_top and near_right) or (on_right and near_top))
    ):
        return HTTOPRIGHT
    if (
        allow_bottom
        and allow_left
        and ((on_bottom and near_left) or (on_left and near_bottom))
    ):
        return HTBOTTOMLEFT
    if (
        allow_bottom
        and allow_right
        and ((on_bottom and near_right) or (on_right and near_bottom))
    ):
        return HTBOTTOMRIGHT
    if on_left:
        return HTLEFT
    if on_right:
        return HTRIGHT
    if on_top:
        return HTTOP
    if on_bottom:
        return HTBOTTOM
    return None


# Every attached callback, kept alive forever. A ctypes callback collected
# while Windows still holds its address takes the process down at the next
# message, and the crash lands nowhere near this file. Never pruned: an
# entry costs a pointer, and the only window that attaches one lives for
# the life of the process.
_KEEPALIVE = []


def _win32():
    """Build the Win32 types and bind user32. Windows only; see the docstring.

    The argtypes/restype are load-bearing. SetWindowLongPtr returns a
    pointer-sized value, and leaving restype at its default c_int truncates
    the original WndProc address on 64-bit -- chaining to a truncated
    pointer is an immediate access violation.
    """
    from ctypes import wintypes

    LRESULT = ctypes.c_ssize_t
    WPARAM = ctypes.c_size_t
    LPARAM = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, WPARAM, LPARAM)

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    class MINMAXINFO(ctypes.Structure):
        _fields_ = [
            ("ptReserved", wintypes.POINT),
            ("ptMaxSize", wintypes.POINT),
            ("ptMaxPosition", wintypes.POINT),
            ("ptMinTrackSize", wintypes.POINT),
            ("ptMaxTrackSize", wintypes.POINT),
        ]

    user32 = ctypes.windll.user32
    set_ptr = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
    set_ptr.restype = ctypes.c_void_p
    set_ptr.argtypes = [wintypes.HWND, ctypes.c_int, WNDPROC]

    user32.CallWindowProcW.restype = LRESULT
    user32.CallWindowProcW.argtypes = [
        WNDPROC,
        wintypes.HWND,
        wintypes.UINT,
        WPARAM,
        LPARAM,
    ]
    # Declared for the same reason as CallWindowProcW: it is the fallback
    # inside the window proc, so a truncated default return type there
    # would corrupt the one path that exists to avoid a crash.
    user32.DefWindowProcW.restype = LRESULT
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]

    return user32, set_ptr, WNDPROC, MONITORINFO, MINMAXINFO, wintypes


def _scale_for(user32, hwnd):
    """Window DPI scale, matching the app's system-DPI-aware model.

    Under PROCESS_SYSTEM_DPI_AWARE -- what __main__.set_dpi_awareness()
    selects -- GetDpiForWindow reports the SYSTEM DPI, not the DPI of the
    monitor the window happens to be on. That is deliberately the same
    number pywebview's own _scale uses (winforms.py:317), including its
    known wrongness on a second monitor at another scale. Inheriting that
    tradeoff keeps this consistent with the rest of the window; improving
    on it here would just disagree with pywebview.
    """
    get_dpi = getattr(user32, "GetDpiForWindow", None)
    if get_dpi is None:
        return 1.0  # Predates Windows 10 1607.
    try:
        dpi = get_dpi(hwnd)
        return (dpi / 96.0) if dpi else 1.0
    except OSError:
        return 1.0


def _on_ui_thread(native, fn) -> None:
    """Run *fn* on the form's UI thread and wait for it to finish.

    Two callers need this for different reasons. Assigning Padding triggers
    a layout pass over the WebView2 control, and doing that cross-thread
    deadlocks the process into a window that cannot be closed. Installing
    the WndProc needs it so that publishing the callback and storing the
    original are ATOMIC with respect to message dispatch -- see
    enable_resize. pywebview guards its own equivalents the same way
    (winforms.py:546, :597).
    """
    from System import Action

    if native.InvokeRequired:
        native.Invoke(Action(fn))
    else:
        fn()


def _apply_inset(native, pad: int, *, edges=ALL_EDGES) -> None:
    """Inset the WebView2 so the form owns the enabled resize bands.

    *pad* is in PHYSICAL pixels, already scaled by the caller. WinForms
    resolves Padding against the form's own DeviceDpi, which is reported as
    96 even on a 200% display -- so an unscaled Padding(6) produces 6
    physical pixels there, while hit_code scales BORDER by
    GetDpiForWindow/96 and looks for 12. The inner half of the band would
    then sit over the WebView2 child, where no hit-test ever arrives, and
    the grab target would silently be half its intended thickness on
    exactly the high-DPI screens where it is hardest to hit. Measured on a
    4K/200% display; both must be scaled by the same factor.

    DockStyle.Fill measures against the parent's DisplayRectangle, which
    Padding shrinks -- so this insets pywebview's control without touching
    its Dock assignment (platforms/edgechromium.py:99). Horizontal-only
    resize leaves the top and bottom at 0 so the page keeps owning them.
    """
    from System.Windows.Forms import Padding

    left = pad if "left" in edges else 0
    top = pad if "top" in edges else 0
    right = pad if "right" in edges else 0
    bottom = pad if "bottom" in edges else 0
    _on_ui_thread(
        native, lambda: setattr(native, "Padding", Padding(left, top, right, bottom))
    )


def _requested_insets(pad: int, edges=ALL_EDGES) -> ResizeInsets:
    return ResizeInsets(
        left=pad if "left" in edges else 0,
        top=pad if "top" in edges else 0,
        right=pad if "right" in edges else 0,
        bottom=pad if "bottom" in edges else 0,
    )


def _logical_insets(native, scale: float, *, fallback: ResizeInsets) -> ResizeInsets:
    """Read back the inset in logical pixels, tolerating DPI rounding.

    The conversion boundary matters to later Fleet Bar width math: the
    returned numbers are the logical insets callers add to content width,
    while the Padding we just applied is in physical pixels. One physical
    pixel can round different ways either side of the form at fractional
    DPI, so each side is rounded independently rather than treated as exact.
    """
    factor = scale or 1.0
    try:
        client = native.ClientRectangle
        display = native.DisplayRectangle
        left = display.X
        top = display.Y
        right = client.Width - display.Width - display.X
        bottom = client.Height - display.Height - display.Y
        return ResizeInsets(
            left=max(0, round(left / factor)),
            top=max(0, round(top / factor)),
            right=max(0, round(right / factor)),
            bottom=max(0, round(bottom / factor)),
        )
    except Exception:
        logger.debug("Could not read back logical resize insets", exc_info=True)
        return fallback


def _remove_inset(native, *, edges=ALL_EDGES) -> None:
    try:
        _apply_inset(native, 0, edges=edges)
    except Exception:
        logger.debug(
            "Could not remove the resize inset after attach failure", exc_info=True
        )


def _bound_horizontal_track_width(
    lparam, MINMAXINFO, insets: ResizeInsets, min_content_width, max_content_width
) -> None:
    if min_content_width is None and max_content_width is None:
        return
    mmi = ctypes.cast(lparam, ctypes.POINTER(MINMAXINFO)).contents
    if min_content_width is not None:
        mmi.ptMinTrackSize.x = min_content_width + insets.horizontal
    if max_content_width is not None:
        mmi.ptMaxTrackSize.x = max_content_width + insets.horizontal


def _attach_resize(
    window,
    *,
    pad: int = INSET,
    edges=ALL_EDGES,
    min_content_width=None,
    max_content_width=None,
) -> ResizeInsets | None:
    """Attach resize chrome and return the logical inset it produced.

    The inset and the subclass are done together on purpose. WM_NCHITTEST
    goes to the window under the cursor, so without the inset the WebView2
    child answers every one of them and the subclass is inert -- measured
    as zero hit-tests reaching the form. Two callers, one of which forgot
    the inset, would produce a feature that silently does nothing.

    Never raises. A window that cannot be subclassed is the behaviour users
    have today -- a fixed-size window -- whereas an exception here would
    take the launch with it.
    """
    if sys.platform != "win32":
        return None

    native = getattr(window, "native", None)
    if native is None:
        logger.warning("No native window; resize border not attached.")
        return None

    try:
        hwnd = native.Handle.ToInt64()
    except Exception:
        logger.warning("Could not read the window handle.", exc_info=True)
        return None

    try:
        user32, set_ptr, WNDPROC, MONITORINFO, MINMAXINFO, wintypes = _win32()
    except Exception:
        logger.warning("Win32 setup failed; window stays fixed-size.", exc_info=True)
        return None

    handle = wintypes.HWND(hwnd)

    # One scale, used for both the inset and the hit band. They must agree:
    # see _apply_inset.
    scale = _scale_for(user32, handle)
    requested = _requested_insets(pad, edges)

    try:
        _apply_inset(native, max(1, int(pad * scale)), edges=edges)
    except Exception:
        # Without the band the subclass cannot receive anything, so there
        # is nothing to gain by continuing to attach it.
        logger.warning(
            "Could not inset the web view; window stays fixed-size.", exc_info=True
        )
        return None

    insets = _logical_insets(native, scale, fallback=requested)
    chained = []

    def _clamp(lparam):
        """Keep a borderless maximize off the taskbar.

        Done here rather than via Form.MaximumSize because MaximumSize is a
        single global cap: it would also stop the window growing on a
        larger second monitor. WM_GETMINMAXINFO is per-monitor and is
        evaluated at the moment of maximizing.
        """
        monitor = user32.MonitorFromWindow(handle, MONITOR_DEFAULTTONEAREST)
        if not monitor:
            return
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return
        work, full = info.rcWork, info.rcMonitor
        mmi = ctypes.cast(lparam, ctypes.POINTER(MINMAXINFO)).contents
        mmi.ptMaxSize.x = work.right - work.left
        mmi.ptMaxSize.y = work.bottom - work.top
        # ptMaxPosition is relative to the monitor, not the desktop.
        mmi.ptMaxPosition.x = work.left - full.left
        mmi.ptMaxPosition.y = work.top - full.top

    def _hit(lparam):
        # The captured `scale`, not a fresh GetDpiForWindow: the inset was
        # applied once at this scale, and the band must keep matching it.
        # Re-reading per message would also mean a syscall on every mouse
        # move, and under system-DPI-awareness the answer cannot change.
        #
        # The coordinates are SIGNED 16-bit halves. A monitor left of the
        # primary gives a negative x, and masking without sign-extending
        # puts the cursor at x=65000 -- every hit-test there would miss.
        x = ctypes.c_short(lparam & 0xFFFF).value
        y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
        rect = wintypes.RECT()
        if not user32.GetWindowRect(handle, ctypes.byref(rect)):
            return None
        return hit_code(
            (rect.left, rect.top, rect.right, rect.bottom),
            x,
            y,
            scale=scale,
            edges=edges,
        )

    def proc(hwnd_, msg, wparam, lparam):
        if not chained:
            # Unreachable by construction -- the install below publishes
            # this callback and stores the original in one UI-thread step,
            # and messages are dispatched on that same thread. Guarded
            # anyway because the alternative is an IndexError unwinding
            # into the native message pump, which kills the process.
            return user32.DefWindowProcW(hwnd_, msg, wparam, lparam)

        original = chained[0]
        try:
            if msg == WM_NCHITTEST:
                code = _hit(lparam)
                if code is not None:
                    return code
                # Fall through: the client area must keep behaving normally.
            elif msg == WM_GETMINMAXINFO:
                # Chain FIRST so WinForms fills ptMinTrackSize in from
                # MinimumSize, THEN override only the max fields. The other
                # order throws min_size away entirely.
                result = user32.CallWindowProcW(original, hwnd_, msg, wparam, lparam)
                _clamp(lparam)
                _bound_horizontal_track_width(
                    lparam, MINMAXINFO, insets, min_content_width, max_content_width
                )
                return result
        except Exception:
            # This unwinds through the native message pump if it escapes,
            # which is fatal. Log it and let the original proc answer.
            logger.debug("Window proc failed", exc_info=True)

        return user32.CallWindowProcW(original, hwnd_, msg, wparam, lparam)

    callback = WNDPROC(proc)
    _KEEPALIVE.append(callback)

    # Publishing the callback and storing the original MUST be atomic with
    # respect to message dispatch. SetWindowLongPtr makes `proc` live the
    # instant it returns, and Windows dispatches this window's messages on
    # the UI thread -- so with the two steps split across threads, a single
    # mouse move in between enters `proc` with `chained` still empty. Doing
    # both inside one UI-thread call closes that window: the thread that
    # would deliver the message is the thread running this code.
    installed = {}

    def _install():
        previous = set_ptr(handle, GWLP_WNDPROC, callback)
        if previous:
            chained.append(ctypes.cast(previous, WNDPROC))
        installed["previous"] = previous

    try:
        _on_ui_thread(native, _install)
    except Exception:
        _KEEPALIVE.remove(callback)
        _remove_inset(native, edges=edges)
        logger.warning(
            "Could not install the window proc; window stays fixed-size.", exc_info=True
        )
        return None

    if not installed.get("previous"):
        _KEEPALIVE.remove(callback)
        _remove_inset(native, edges=edges)
        logger.warning("SetWindowLongPtr failed; window stays fixed-size.")
        return None

    _log_geometry(native, pad, scale)
    return insets


def enable_resize(window, pad: int = INSET) -> bool:
    """Give *window* a native resize border. True if it took."""
    return _attach_resize(window, pad=pad, edges=ALL_EDGES) is not None


def enable_horizontal_resize(
    window, *, pad: int = INSET, min_content_width: int, max_content_width: int
) -> ResizeInsets | None:
    """Attach left/right-only resize chrome and return its logical inset."""
    return _attach_resize(
        window,
        pad=pad,
        edges=HORIZONTAL_EDGES,
        min_content_width=min_content_width,
        max_content_width=max_content_width,
    )


def _log_geometry(native, pad: int, scale: float) -> None:
    """Record what the inset actually produced. Never fatal.

    INFO, not DEBUG, because configure_logging() pins the root logger at
    INFO (__main__.py:64) -- a DEBUG line here would be written nowhere and
    the diagnostic would silently not exist. It is one line per launch.

    Kept rather than run once and deleted: the band depends on a DPI factor
    that WinForms and Win32 report differently (see _apply_inset), so the
    only way to know what a given machine did is to read it back. Without
    it, a wrong band arrives as "resizing feels wrong on that laptop" with
    nothing to go on.

    DisplayRectangle is the authoritative number -- it is what DockStyle.Fill
    measures the WebView2 against -- so the inset is the gap between it and
    ClientRectangle, and the child's own bounds add nothing.
    """
    try:
        client = native.ClientRectangle
        display = native.DisplayRectangle
        logger.info(
            "resize band: asked %spx at scale %s, got %dpx left / %dpx top "
            "(client %dx%d, display %dx%d, padding %s, dpi %s)",
            pad,
            scale,
            display.X,
            display.Y,
            client.Width,
            client.Height,
            display.Width,
            display.Height,
            native.Padding,
            native.DeviceDpi,
        )
    except Exception:
        logger.debug("Could not read back the inset geometry", exc_info=True)
