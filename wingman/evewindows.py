"""Enumerate running EVE client windows by title.

Windows-only at runtime; imports and tests cleanly on Linux, following the
ui/chrome.py precedent. ctypes is imported lazily inside the enumerator so
the module itself has no platform dependency at import time.

`_enumerate_titles` declares argtypes/restype on every Win32 call, matching
ui/chrome.py:127-128. This is deliberate, not decoration: EnumWindows hands
the callback an hwnd as a plain Python int, and passing that int to an
*undeclared* function makes ctypes marshal it as a 32-bit C int, truncating
a 64-bit handle on 64-bit Windows. IsWindowVisible/GetWindowTextW would then
read a window that doesn't exist, and the list would come back silently
wrong -- with no test able to catch it, since this code path never runs off
Windows. Do not trim these as noise.
"""

import logging
import sys

from . import bookmarks

logger = logging.getLogger(__name__)

# The engine has no prefix check of its own -- it binds to whatever exact
# titles the INI lists. is_engine_window_title is the layer that actually
# enforces which titles count as EVE client windows (bookmarks.py:242-250),
# and generate_ini uses that same predicate when writing the INI. Re-deriving
# the rule here (a bare prefix check) would drift from it silently: a title
# containing "=" would be offered here, the user could enable it, and
# generate_ini would then drop it -- a checkbox that does nothing. Read from
# the single source instead.
TITLE_PREFIX = bookmarks.ENGINE_TITLE_PREFIX


def _enumerate_windows() -> list:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32

    # The argtypes/restype are load-bearing, for the reason ui/chrome.py:127
    # records: hwnd reaches the callback as a Python int, and passing it to an
    # undeclared function marshals it as a 32-bit C int, truncating a 64-bit
    # handle. IsWindowVisible and GetWindowTextW would then be reading a
    # window that does not exist, and the list would come back silently wrong.
    wndenumproc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [wndenumproc, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int

    titles = []

    def callback(hwnd, _lparam):
        # An exception raised here does NOT reach the caller: ctypes reports
        # it via sys.unraisablehook and returns a falsy value, which Windows
        # reads as "stop enumerating" -- silently truncating the list. Catch
        # everything and skip the offending window instead.
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                titles.append((hwnd, buffer.value))
        except Exception:
            logger.exception("Skipped a window during enumeration.")
        return True

    user32.EnumWindows(wndenumproc(callback), 0)
    return titles


def _enumerate_titles() -> list:
    """Titles only, for list_eve_windows's frozen string-list contract.

    Both views come from one enumeration so the preview subsystem and the
    bookmarks checkbox can never disagree about which windows exist.
    """
    return [title for _hwnd, title in _enumerate_windows()]


def list_eve_windows(enumerator=None) -> list:
    """Sorted, de-duplicated EVE window titles. Empty off Windows."""
    if sys.platform != "win32":
        return []
    try:
        titles = (enumerator or _enumerate_titles)()
    except Exception:
        logger.exception("Could not enumerate windows")
        return []
    return sorted({t for t in titles if bookmarks.is_engine_window_title(t)})
