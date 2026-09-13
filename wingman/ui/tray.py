"""Windows notification-area menu integration."""

import ctypes
import logging
from contextlib import contextmanager
from ctypes import wintypes

logger = logging.getLogger(__name__)


@contextmanager
def _menu_dpi_context():
    """Interpret physical menu coordinates without changing any existing HWND."""
    previous = None
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        set_context = user32.SetThreadDpiAwarenessContext
        set_context.argtypes = [ctypes.c_void_p]
        set_context.restype = ctypes.c_void_p
        previous = set_context(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
    except (AttributeError, OSError):
        logger.warning(
            "Tray menu DPI override unavailable; placement may be scaled",
            exc_info=True,
        )
    else:
        if not previous:
            logger.warning(
                "Tray menu DPI override rejected (error %s); placement may be scaled",
                getattr(ctypes, "get_last_error", lambda: 0)(),
            )
    try:
        yield
    finally:
        if previous and not set_context(previous):
            logger.error(
                "Tray menu DPI context restoration failed (error %s)",
                getattr(ctypes, "get_last_error", lambda: 0)(),
            )


def physical_cursor_position(*, user32=None) -> tuple[int, int]:
    """Return the cursor in physical screen coordinates.

    Pair this with ``_menu_dpi_context``: after WinForms startup, even
    physical coordinates can be scaled again by a system-aware menu call.
    """
    if user32 is None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetPhysicalCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.GetPhysicalCursorPos.restype = wintypes.BOOL

    point = wintypes.POINT()
    if not user32.GetPhysicalCursorPos(ctypes.byref(point)):
        error_code = getattr(ctypes, "get_last_error", lambda: 0)()
        raise OSError(error_code, "GetPhysicalCursorPos failed")
    return point.x, point.y


def show_windows_menu(icon, *, win32, physical_cursor):
    """Display *icon*'s menu, preferring physical screen coordinates."""
    win32.SetForegroundWindow(icon._hwnd)

    # WinForms startup changes the native menu's scaling behavior. A bare
    # pystray probe misses this: physical coordinates alone still land at
    # half scale in the app. Scope the override to menu work, not the HWNDs
    # or Open/Quit callbacks, which retain their original DPI context.
    with _menu_dpi_context():
        try:
            x, y = physical_cursor()
        except (AttributeError, OSError):
            point = wintypes.POINT()
            win32.GetCursorPos(ctypes.byref(point))
            x, y = point.x, point.y

        menu, descriptors = icon._menu_handle
        index = win32.TrackPopupMenuEx(
            menu,
            win32.TPM_RIGHTALIGN | win32.TPM_BOTTOMALIGN | win32.TPM_RETURNCMD,
            x,
            y,
            icon._menu_hwnd,
            None,
        )
    if index > 0:
        descriptors[index - 1](icon)


def windows_icon_class(base_icon, win32):
    """Return a pystray Icon variant with DPI-isolated popup placement."""

    class WingmanWindowsIcon(base_icon):
        def _on_notify(self, wparam, lparam):
            if self._menu_handle and lparam == win32.WM_RBUTTONUP:
                return show_windows_menu(
                    self,
                    win32=win32,
                    physical_cursor=physical_cursor_position,
                )
            return super()._on_notify(wparam, lparam)

    return WingmanWindowsIcon
