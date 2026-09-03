"""Discover running EVE clients, with a stable identity per client.

Separate from `evewindows.list_eve_windows` on purpose: that function's
string-list return type is consumed by ui/api.py and is frozen. Both views
of the desktop come from `evewindows._enumerate`, so the argtypes discipline
lives in one place -- `list_clients` through its best-effort wrapper and
`probe_eve_client_state` through its strict one.
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


def probe_eve_client_state(
    enumerator=None, pids=None, image_name=None
) -> EveClientProbe:
    """Tri-state probe for whole-profile writes: CLOSED, RUNNING, or UNKNOWN.

    Considers every window whose title starts with "EVE" -- the same wide net
    list_clients casts, not TITLE_PREFIX's narrower "EVE - ". A client whose
    title has not yet gained its character suffix (the launcher hand-off
    window, a client still loading) is exactly the one this probe must not
    miss, and TITLE_PREFIX would skip it silently.

    Deliberately NOT routed through list_clients(): that function's whole
    contract is to SKIP a window it cannot resolve, which is right for
    drawing previews and wrong here. Every unresolvable candidate is
    collected as an error instead, and any error at all makes the answer
    UNKNOWN -- fail-closed, because the caller is about to rewrite a whole
    profile and "probably closed" is a guess in the dangerous direction.
    RUNNING needs one candidate verified as CLIENT_IMAGE; CLOSED is what is
    left when nothing errored and nothing verified.

    The default enumerator is the STRICT one for the same reason: the
    best-effort sweep list_clients uses drops a window it could not read,
    and a dropped window is indistinguishable from an absent one here --
    an EVE client nobody managed to look at would read as CLOSED and clear
    the write.
    """
    if sys.platform != "win32" and enumerator is None:
        return EveClientProbe(state=EveClientState.CLOSED)

    enumerator = enumerator or evewindows._enumerate_windows_strict
    pids = pids or _pid_for_window
    image_name = image_name or _image_name_for_pid

    errors: list[BaseException] = []
    found_running = False

    try:
        windows = enumerator()
    except Exception as error:  # noqa: BLE001 - collected, not swallowed: it is returned on EveClientProbe.errors and forces UNKNOWN
        errors.append(error)
        return EveClientProbe(state=EveClientState.UNKNOWN, errors=tuple(errors))

    for hwnd, title in windows:
        if not title.startswith("EVE"):
            continue

        try:
            pid = pids(hwnd)
        except Exception as error:  # noqa: BLE001 - collected, not swallowed: see the enumerator handler above
            errors.append(error)
            continue

        # A zero PID is a failed lookup, not an absent client. Synthesised as
        # an error so it reaches UNKNOWN rather than reading as "not a client".
        if not pid:
            errors.append(OSError(f"Zero PID for window 0x{hwnd:x}"))
            continue

        try:
            resolved_image = image_name(pid)
        except Exception as error:  # noqa: BLE001 - collected, not swallowed: see the enumerator handler above
            errors.append(error)
            continue

        # None means the process could not be opened. list_clients reads that
        # as "owned by another user, not a client"; here it is unresolved, and
        # an unresolved EVE-titled window is precisely the doubt this probe
        # exists to report.
        if resolved_image is None:
            errors.append(
                OSError(f"Cannot resolve image for PID {pid} (window 0x{hwnd:x})")
            )
            continue

        if resolved_image == CLIENT_IMAGE:
            found_running = True

    if errors:
        return EveClientProbe(state=EveClientState.UNKNOWN, errors=tuple(errors))
    if found_running:
        return EveClientProbe(state=EveClientState.RUNNING)
    return EveClientProbe(state=EveClientState.CLOSED)
