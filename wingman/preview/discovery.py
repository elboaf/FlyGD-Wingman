"""Discover running EVE clients, with a stable identity per client.

Separate from `evewindows.list_eve_windows` on purpose: that function's
string-list return type is consumed by ui/api.py and is frozen. Both share
`_enumerate_windows` so the argtypes discipline lives in one place.
"""

import enum
import logging
import sys
from dataclasses import dataclass
from typing import NamedTuple

from .. import evewindows

logger = logging.getLogger(__name__)

TITLE_PREFIX = "EVE - "
CLIENT_IMAGE = "exefile.exe"

# NOT bookmarks.is_engine_window_title: that predicate also rejects "=",
# because the AHK engine's INI format cannot carry it (bookmarks.py:308).
# That is a storage constraint of a different feature. A client whose
# character name contains "=" is still perfectly previewable.


class EveClientState(enum.Enum):
    """Tri-state probe result for whole-profile writes.
    
    CLOSED: No EVE clients or all candidates failed to resolve as clients.
    RUNNING: At least one EVE client window verified as exefile.exe.
    UNKNOWN: Errors occurred during probe; state cannot be determined.
    """
    CLOSED = "closed"
    RUNNING = "running"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class EveClientProbe:
    """Result of a whole-profile write probe.
    
    state: The tri-state result.
    errors: Exceptions caught during probing (enumeration, PID lookup, image lookup).
    """
    state: EveClientState
    errors: tuple[BaseException, ...] = ()


class Client(NamedTuple):
    hwnd: int
    title: str
    pid: int
    character: str
    stable_key: str


def _character(title: str):
    if title.startswith(TITLE_PREFIX):
        name = title[len(TITLE_PREFIX) :].strip()
        return name or None
    return None


def list_clients(*, enumerator=None, pids=None, image_name=None, strict=False) -> list:
    """Every visible EVE client window, as Client records.

    Collaborators are injected for testing, following evewindows.py's
    pattern. `image_name` returns None when the process cannot be opened,
    which is routine for processes owned by another user -- treated as
    "not a client", never as an error.
    """
    if sys.platform != "win32" and enumerator is None:
        return []
    enumerator = enumerator or evewindows._enumerate_windows
    pids = pids or _pid_for_window
    image_name = image_name or _image_name_for_pid
    try:
        windows = enumerator()
    except Exception:
        if strict:
            raise
        logger.exception("Could not enumerate windows")
        return []

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
    return out


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


def probe_eve_client_state(enumerator=None, pids=None, image_name=None) -> EveClientProbe:
    """Tri-state probe for whole-profile writes: CLOSED, RUNNING, or UNKNOWN.
    
    Examines all windows beginning with TITLE_PREFIX ("EVE - "), collecting
    errors for zero PIDs, None images, and caught exceptions. Returns:
    - UNKNOWN if any errors occur (fail-closed for safety)
    - RUNNING if at least one candidate verifies as CLIENT_IMAGE (exefile.exe)
    - CLOSED otherwise (no EVE clients found)
    
    Does NOT route through list_clients().
    """
    if sys.platform != "win32" and enumerator is None:
        return EveClientProbe(state=EveClientState.CLOSED)
    
    enumerator = enumerator or evewindows._enumerate_windows
    pids = pids or _pid_for_window
    image_name = image_name or _image_name_for_pid
    
    errors: list[BaseException] = []
    found_running = False
    
    try:
        windows = enumerator()
    except Exception as e:
        errors.append(e)
        return EveClientProbe(state=EveClientState.UNKNOWN, errors=tuple(errors))
    
    # Examine every window starting with "EVE"
    for hwnd, title in windows:
        if not title.startswith("EVE"):
            continue
        
        # Try to resolve PID
        try:
            pid = pids(hwnd)
        except Exception as e:
            errors.append(e)
            continue
        
        # Fail-closed: zero PID is an error condition
        if not pid:
            errors.append(OSError(f"Zero PID for window 0x{hwnd:x}"))
            continue
        
        # Try to resolve image name
        try:
            resolved_image = image_name(pid)
        except Exception as e:
            errors.append(e)
            continue
        
        # Fail-closed: None image (access denied) is an error condition
        if resolved_image is None:
            errors.append(OSError(f"Cannot resolve image for PID {pid} (window 0x{hwnd:x})"))
            continue
        
        # Check if it's a real EVE client
        if resolved_image == CLIENT_IMAGE:
            found_running = True
    
    # Tri-state logic: UNKNOWN dominates, then RUNNING, then CLOSED
    if errors:
        return EveClientProbe(state=EveClientState.UNKNOWN, errors=tuple(errors))
    if found_running:
        return EveClientProbe(state=EveClientState.RUNNING)
    return EveClientProbe(state=EveClientState.CLOSED)
