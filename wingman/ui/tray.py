"""Windows notification-area menu integration."""

import ctypes
from ctypes import wintypes


def physical_cursor_position(*, user32=None) -> tuple[int, int]:
    """Return the cursor in physical screen coordinates.

    ``GetCursorPos`` is DPI-virtualized for Wingman's system-aware tray
    thread. ``TrackPopupMenuEx`` consumes physical screen coordinates, so a
    200% primary display otherwise halves both coordinates and puts the menu
    near the middle of the screen.
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
    """Return a pystray Icon variant with physical popup coordinates."""

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
