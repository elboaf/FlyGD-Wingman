"""Enumerate running EVE client windows by title.

Windows-only at runtime; imports and tests cleanly on Linux, following the
ui/chrome.py precedent. ctypes is imported lazily inside the enumerator so
the module itself has no platform dependency at import time.
"""
import logging
import sys

logger = logging.getLogger(__name__)

# The engine matches ^EVE -  (111unified.ahk:248). Offering the user a
# window the engine will never match would give them a checkbox that
# silently does nothing, so the two must agree exactly.
TITLE_PREFIX = "EVE - "


def _enumerate_titles() -> list:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    titles = []

    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length:
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            titles.append(buffer.value)
        return True

    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(proto(callback), 0)
    return titles


def list_eve_windows(enumerator=None) -> list:
    """Sorted, de-duplicated EVE window titles. Empty off Windows."""
    if sys.platform != "win32":
        return []
    try:
        titles = (enumerator or _enumerate_titles)()
    except Exception:
        logger.exception("Could not enumerate windows")
        return []
    return sorted({t for t in titles if t.startswith(TITLE_PREFIX)})
