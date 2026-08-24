"""Win32 edge for EVE client window placement.

Thin by construction: no policy, no iteration, no settings. Each function
is one or two calls plus a struct fill, so everything worth testing lives
in placement.py and clientlayout.py instead.

`libs` is a parameter on every function so the whole module runs under a
double on ubuntu-latest -- win32.py keeps structs and constants at module
scope and touches a DLL only inside bind() (win32.py:1-14), which is what
makes that possible.
"""
import contextlib
import ctypes
import logging

from . import win32
from .geometry import Rect
from .placement import Placement, to_screen, to_workspace

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def dpi_context(libs=None):
    """Per-Monitor V2 for the duration of one batch. Yields whether the
    override was accepted.

    A SCOPE, not initialisation, for two independent reasons:

      * threading.Timer starts a fresh thread per tick
        (ui/scheduler.py:52-65) and DPI awareness is thread-local, so a
        context set once at startup is gone by the first watcher tick.
      * Virtualization follows the CALLING thread, not the window. A save
        and a restore in different contexts disagree by the scale factor
        on any monitor not at system DPI -- and agree exactly on a
        single-monitor machine, so local testing cannot find it.

    Thread-local, so the process keeps the PROCESS_SYSTEM_DPI_AWARE
    contract __main__.py:99-114 chose and ui/chrome.py:177-186 depends on.
    This is the same move the preview thread makes (host.py), already
    verified against a 192-DPI monitor.
    """
    libs = libs or win32.bind()
    previous = libs.user32.SetThreadDpiAwarenessContext(
        ctypes.c_void_p(win32.DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2))
    try:
        yield bool(previous)
    finally:
        # Restored exactly, not guessed: the setter returns the context it
        # replaced. A falsy return means nothing was changed, so there is
        # nothing to put back.
        if previous:
            libs.user32.SetThreadDpiAwarenessContext(previous)


def work_area_origin(libs=None) -> tuple:
    """The workspace -> screen offset: the primary monitor's work-area
    origin. (0, 0) for a taskbar docked bottom or right, non-zero for one
    docked top or left.
    """
    libs = libs or win32.bind()
    rect = win32.RECT()
    if not libs.user32.SystemParametersInfoW(win32.SPI_GETWORKAREA, 0,
                                             ctypes.byref(rect), 0):
        # Zero is the right guess rather than an abort: it is correct for
        # every bottom or right taskbar, which is the common case.
        logger.warning("SPI_GETWORKAREA failed; assuming a zero offset")
        return (0, 0)
    return (int(rect.left), int(rect.top))


def read_placement(hwnd, origin, libs=None):
    """The client's restore rect in screen coordinates, or None.

    rcNormalPosition rather than GetWindowRect deliberately: the latter
    returns the MAXIMIZED bounds of a maximized window, while this is the
    rect it will un-maximize to -- the thing worth persisting.
    """
    libs = libs or win32.bind()
    wp = win32.WINDOWPLACEMENT()
    wp.length = ctypes.sizeof(win32.WINDOWPLACEMENT)
    if not libs.user32.GetWindowPlacement(hwnd, ctypes.byref(wp)):
        return None
    r = wp.rcNormalPosition
    rect = Rect(int(r.left), int(r.top),
                int(r.right) - int(r.left), int(r.bottom) - int(r.top))
    if rect.w <= 0 or rect.h <= 0:
        return None
    return Placement(to_screen(rect, origin),
                     wp.showCmd == win32.SW_SHOWMAXIMIZED)


def apply_placement(hwnd, placement, origin, libs=None) -> bool:
    """Move *hwnd* to *placement*. Never minimizes.

    Placement carries no minimized state, so SW_SHOWMINIMIZED is
    unreachable from here by construction -- restoring a client into a
    minimized window would make it vanish with no indication why.
    """
    libs = libs or win32.bind()
    rect = to_workspace(placement.rect, origin)
    wp = win32.WINDOWPLACEMENT()
    wp.length = ctypes.sizeof(win32.WINDOWPLACEMENT)
    # Posts rather than sends: a loading or hung client would otherwise
    # stall this thread for as long as it stays wedged.
    wp.flags = win32.WPF_ASYNCWINDOWPLACEMENT
    wp.showCmd = (win32.SW_SHOWMAXIMIZED if placement.maximized
                  else win32.SW_SHOWNORMAL)
    wp.rcNormalPosition = win32.RECT(rect.x, rect.y, rect.right, rect.bottom)
    return bool(libs.user32.SetWindowPlacement(hwnd, ctypes.byref(wp)))
