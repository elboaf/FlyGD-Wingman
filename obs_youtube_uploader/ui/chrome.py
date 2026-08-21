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
"""
import ctypes
import logging
import sys

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
#
# PENDING MEASUREMENT (plan step 1): these must not exceed the inset that
# window.py actually achieves, or part of the grab band lands on the
# WebView2 child and silently stops responding. The spike asked for a 6px
# inset and got 3, cause unresolved -- so treat both numbers below as
# provisional until that reads out.
BORDER = 6
CORNER = 14


def hit_code(rect, x, y, scale=1.0):
    """Which resize zone (x, y) falls in, or None for "not the border".

    *rect* is (left, top, right, bottom) in screen pixels, as GetWindowRect
    reports it. *x* and *y* are screen pixels. *scale* is the window's
    DPI scale, so the band stays the same apparent thickness at 150%.

    Returning None means "not mine": the caller must fall through to the
    original WndProc so the client area keeps behaving normally, or the
    page stops receiving the mouse entirely.

    Corners are checked first, and against a longer reach than the edges,
    so the diagonal grab is not a BORDER-sized square nobody can hit.
    """
    left, top, right, bottom = rect
    border = max(1, int(BORDER * scale))
    corner = max(border, int(CORNER * scale))

    on_left = x < left + border
    on_right = x >= right - border
    on_top = y < top + border
    on_bottom = y >= bottom - border

    near_left = x < left + corner
    near_right = x >= right - corner
    near_top = y < top + corner
    near_bottom = y >= bottom - corner

    if (on_top and near_left) or (on_left and near_top):
        return HTTOPLEFT
    if (on_top and near_right) or (on_right and near_top):
        return HTTOPRIGHT
    if (on_bottom and near_left) or (on_left and near_bottom):
        return HTBOTTOMLEFT
    if (on_bottom and near_right) or (on_right and near_bottom):
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
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                                 WPARAM, LPARAM)

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD),
                    ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD)]

    class MINMAXINFO(ctypes.Structure):
        _fields_ = [("ptReserved", wintypes.POINT),
                    ("ptMaxSize", wintypes.POINT),
                    ("ptMaxPosition", wintypes.POINT),
                    ("ptMinTrackSize", wintypes.POINT),
                    ("ptMaxTrackSize", wintypes.POINT)]

    user32 = ctypes.windll.user32
    set_ptr = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
    set_ptr.restype = ctypes.c_void_p
    set_ptr.argtypes = [wintypes.HWND, ctypes.c_int, WNDPROC]

    user32.CallWindowProcW.restype = LRESULT
    user32.CallWindowProcW.argtypes = [WNDPROC, wintypes.HWND, wintypes.UINT,
                                       WPARAM, LPARAM]
    user32.GetWindowRect.argtypes = [wintypes.HWND,
                                     ctypes.POINTER(wintypes.RECT)]
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE,
                                       ctypes.POINTER(MONITORINFO)]

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


def enable_resize(window) -> bool:
    """Give *window* a native resize border. True if it took.

    Never raises. A window that cannot be subclassed is the behaviour
    users have today -- a fixed-size window -- whereas an exception here
    would take the launch with it.
    """
    if sys.platform != "win32":
        return False

    native = getattr(window, "native", None)
    if native is None:
        logger.warning("No native window; resize border not attached.")
        return False

    try:
        hwnd = native.Handle.ToInt64()
    except Exception:
        logger.warning("Could not read the window handle.", exc_info=True)
        return False

    try:
        user32, set_ptr, WNDPROC, MONITORINFO, MINMAXINFO, wintypes = _win32()
    except Exception:
        logger.warning("Win32 setup failed; window stays fixed-size.",
                       exc_info=True)
        return False

    handle = wintypes.HWND(hwnd)
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
        # The coordinates are SIGNED 16-bit halves. A monitor left of the
        # primary gives a negative x, and masking without sign-extending
        # puts the cursor at x=65000 -- every hit-test there would miss.
        x = ctypes.c_short(lparam & 0xFFFF).value
        y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
        rect = wintypes.RECT()
        if not user32.GetWindowRect(handle, ctypes.byref(rect)):
            return None
        return hit_code((rect.left, rect.top, rect.right, rect.bottom),
                        x, y, _scale_for(user32, handle))

    def proc(hwnd_, msg, wparam, lparam):
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
                result = user32.CallWindowProcW(original, hwnd_, msg,
                                                wparam, lparam)
                _clamp(lparam)
                return result
        except Exception:
            # This unwinds through the native message pump if it escapes,
            # which is fatal. Log it and let the original proc answer.
            logger.debug("Window proc failed", exc_info=True)

        return user32.CallWindowProcW(original, hwnd_, msg, wparam, lparam)

    callback = WNDPROC(proc)
    _KEEPALIVE.append(callback)

    previous = set_ptr(handle, GWLP_WNDPROC, callback)
    if not previous:
        _KEEPALIVE.remove(callback)
        logger.warning("SetWindowLongPtr failed; window stays fixed-size.")
        return False

    chained.append(ctypes.cast(previous, WNDPROC))
    return True
