"""Discover running EVE clients, with a stable identity per client.

Separate from `evewindows.list_eve_windows` on purpose: that function's
string-list return type is consumed by ui/api.py and is frozen. Both share
`_enumerate_windows` so the argtypes discipline lives in one place.
"""

import logging
import sys
from typing import NamedTuple

from .. import evewindows

logger = logging.getLogger(__name__)

TITLE_PREFIX = "EVE - "
CLIENT_IMAGE = "exefile.exe"

# NOT bookmarks.is_engine_window_title: that predicate also rejects "=",
# because the AHK engine's INI format cannot carry it (bookmarks.py:308).
# That is a storage constraint of a different feature. A client whose
# character name contains "=" is still perfectly previewable.


class Client(NamedTuple):
    hwnd: int
    title: str
    pid: int
    character: str
    stable_key: str


class EnumerationResult(NamedTuple):
    """A raw scan's outcome, distinguishing a genuinely empty roster from
    a failed one.

    A plain `list` cannot carry that distinction, and callers that prune
    state on absence (ClientDiscovery's stable-session pruning) must never
    treat a failed scan as authoritative proof that nothing is running.
    `success=False` always carries an empty `clients` list -- the shape
    `list_clients()`'s existing callers already tolerate on failure.
    """

    success: bool
    clients: list


def _character(title: str):
    if title.startswith(TITLE_PREFIX):
        name = title[len(TITLE_PREFIX) :].strip()
        return name or None
    return None


def enumerate_clients(
    *, enumerator=None, pids=None, image_name=None, strict=False
) -> EnumerationResult:
    """Every visible EVE client window, with a flag distinguishing a
    genuinely empty scan from one where the top-level enumerator call
    itself failed.

    Collaborators are injected for testing, following evewindows.py's
    pattern. `image_name` returns None when the process cannot be opened,
    which is routine for processes owned by another user -- treated as
    "not a client", never as an error. A per-window inspection failure
    (`pids`/`image_name` raising) only drops that one window -- it is not
    an enumeration failure, since the top-level window list was obtained
    successfully.
    """
    if sys.platform != "win32" and enumerator is None:
        return EnumerationResult(True, [])
    enumerator = enumerator or evewindows._enumerate_windows
    pids = pids or _pid_for_window
    image_name = image_name or _image_name_for_pid
    try:
        windows = enumerator()
    except Exception:
        if strict:
            raise
        logger.exception("Could not enumerate windows")
        return EnumerationResult(False, [])

    out = []
    for hwnd, title in windows:
        if not title.startswith("EVE"):
            continue
        try:
            pid = pids(hwnd)
            if not pid or image_name(pid) != CLIENT_IMAGE:
                continue
        except Exception:
            if strict:
                raise
            logger.exception("Skipped window 0x%x during discovery", hwnd)
            continue
        character = _character(title)
        out.append(Client(hwnd, title, pid, character, character or f"hwnd:0x{hwnd:x}"))
    return EnumerationResult(True, out)


def list_clients(*, enumerator=None, pids=None, image_name=None, strict=False) -> list:
    """Every visible EVE client window, as Client records.

    Compatibility adapter over `enumerate_clients()`: existing callers
    (Preview reconciliation, Alerts) have never needed to distinguish "no
    clients" from "enumeration failed" and this preserves that -- both
    collapse to an empty list here, exactly as before this function grew
    a failure-aware sibling.
    """
    return enumerate_clients(
        enumerator=enumerator, pids=pids, image_name=image_name, strict=strict
    ).clients


_IMAGE_CACHE = {}
_CACHE_SWEEPS = 0
_CACHE_FLUSH_EVERY = 512  # TriffViewSubsystem.cs:4732 uses the same bound


def _pid_for_window(hwnd: int) -> int:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
    return int(pid.value)


def _image_name_for_pid(pid: int):
    """Executable basename for *pid*, or None if it cannot be opened.

    QueryFullProcessImageNameW under PROCESS_QUERY_LIMITED_INFORMATION --
    the limited right exists precisely so this works without elevation.

    Deliberately NOT procid.describe(): that spawns PowerShell per PID with
    a ten-second timeout (procid.py:21-37) and its docstring justifies the
    cost as "one call on one code path". This runs every 700ms across every
    client.
    """
    if pid in _IMAGE_CACHE:
        return _IMAGE_CACHE[pid]
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.windll.kernel32
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [wintypes.HANDLE]

    handle = k32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
    if not handle:
        _IMAGE_CACHE[pid] = None
        return None
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if not k32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            _IMAGE_CACHE[pid] = None
            return None
        name = buf.value.rsplit("\\", 1)[-1].lower()
    finally:
        k32.CloseHandle(handle)
    _IMAGE_CACHE[pid] = name
    return name


def flush_image_cache_periodically() -> None:
    """PIDs are reused. Called once per sweep by the host."""
    global _CACHE_SWEEPS
    _CACHE_SWEEPS += 1
    if _CACHE_SWEEPS >= _CACHE_FLUSH_EVERY:
        _CACHE_SWEEPS = 0
        _IMAGE_CACHE.clear()
