"""Struct declarations, checked on every platform.

test_preview_win32.py is skipped off Windows because it calls bind().
These assertions need no DLL -- win32.py keeps structs and constants at
module scope precisely so they import anywhere (win32.py:1-14).
"""
import ctypes

from obs_youtube_uploader.preview import win32


def test_windowplacement_struct_is_usable_off_windows():
    """clientwin32's tests build one of these on Linux. length is what
    GetWindowPlacement validates, so sizeof must be real."""
    wp = win32.WINDOWPLACEMENT()
    wp.length = ctypes.sizeof(win32.WINDOWPLACEMENT)
    assert wp.length > 0
    assert hasattr(wp, "showCmd") and hasattr(wp, "rcNormalPosition")


def test_placement_show_constants_match_win32():
    assert (win32.SW_SHOWNORMAL, win32.SW_SHOWMINIMIZED,
            win32.SW_SHOWMAXIMIZED) == (1, 2, 3)
    assert win32.WPF_ASYNCWINDOWPLACEMENT == 0x0004
    assert win32.SPI_GETWORKAREA == 0x0030
