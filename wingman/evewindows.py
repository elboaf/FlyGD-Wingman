"""Enumerate running EVE client windows by title.

Windows-only at runtime; imports and tests cleanly on Linux, following the
ui/chrome.py precedent. ctypes is imported lazily inside the enumerator so
the module itself has no platform dependency at import time.

`_enumerate` declares argtypes/restype on every Win32 call, matching
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


class WindowEnumerationError(OSError):
    """A strict enumeration could not read every window.

    Carries the individual failures on `.errors` so the caller can report
    WHY it is refusing rather than only that it did.
    """

    def __init__(self, message: str, errors=()) -> None:
        super().__init__(message)
        self.errors = tuple(errors)


def _enumerate(errors) -> list:
    """One sweep of the desktop, shared by both enumeration contracts.

    `errors` is None for the best-effort caller and a list for the strict
    one. It is deliberately a collector rather than a "raise now" flag: an
    exception cannot leave the callback (see below), and returning early
    would truncate the very sweep whose completeness is in question.
    """
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
        # everything and skip the offending window instead. A strict caller
        # gets it back on `errors`, raised once the sweep has finished.
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                titles.append((hwnd, buffer.value))
        except Exception as error:
            logger.exception("Skipped a window during enumeration.")
            if errors is not None:
                errors.append(error)
        return True

    if not user32.EnumWindows(wndenumproc(callback), 0) and errors is not None:
        # EnumWindows returns FALSE when the callback stopped it or the call
        # itself failed. This callback always returns TRUE, so a falsy result
        # means the list is short for a reason nobody saw. No error code is
        # quoted: ctypes.windll does not preserve GetLastError across the
        # call, and a stale code reads as fact. Only the strict caller is
        # told -- logging it best-effort would write a line per preview
        # sweep, several times a second.
        errors.append(OSError("EnumWindows reported an incomplete enumeration."))
    return titles


def _enumerate_windows() -> list:
    """Best effort: an unreadable window is skipped, the rest are returned.

    What previews and the bookmarks checkbox want -- one locked-down window
    must not cost the user every client on the list.
    """
    return _enumerate(None)


def _enumerate_windows_strict() -> list:
    """The same sweep, but an unreadable window is a failure, not a skip.

    For `preview.discovery.probe_eve_client_state`, which asks "is any EVE
    client running" before a whole-profile write. A skipped window is
    indistinguishable from an absent one in the returned list, so the
    best-effort sweep can answer CLOSED on the strength of the single
    window nobody managed to read -- and CLOSED is the answer that lets the
    destructive write proceed. Raising here is what turns that into UNKNOWN.
    """
    errors: list[BaseException] = []
    windows = _enumerate(errors)
    if errors:
        raise WindowEnumerationError(
            f"Could not read {len(errors)} window(s) during enumeration.", errors
        )
    return windows


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
