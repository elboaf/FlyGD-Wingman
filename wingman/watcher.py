"""Poll a directory for finished recordings.

Polling rather than filesystem events: native change notifications are
unreliable on network and mapped drives, watchdog would be another
dependency, and polling one directory every few seconds costs nothing.

A file appearing is not a file finished. Size must hold steady across
several consecutive polls, AND the writer must have let go of the file,
before it is announced. The second half is not belt-and-braces: a steady
size alone is not evidence of anything, because OBS's muxer does not grow
the file smoothly. See file_is_closed below.
"""

import ctypes
import json
import logging
import sys
from ctypes import wintypes
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import library

logger = logging.getLogger(__name__)

# ERROR_SHARING_VIOLATION and ERROR_LOCK_VIOLATION: someone else holds a
# handle. Every other failure means the probe could not get an answer.
_WRITER_STILL_HOLDS_IT = frozenset({32, 33})


@lru_cache(maxsize=1)
def _kernel32():
    """The CreateFileW binding, built once.

    Cached for the reason dpapi.py:63-66 and preview/win32.py record: the
    DLL handle and its argtypes/restype are process-global mutations, so
    redoing them on every probe -- once per settled recording per poll,
    forever -- is wasted work rather than just noise.

    ctypes and ctypes.wintypes import fine on Linux; ctypes.WinDLL is what
    does not exist there, so the binding is built lazily in here and this
    module still imports for the suite. The layout preview/win32.py:1-9
    establishes.
    """
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # HANDLE CreateFileW(LPCWSTR, DWORD, DWORD, LPVOID, DWORD, DWORD, HANDLE)
    # Declared in full for the reason win32.py:10-16 records: undeclared,
    # ctypes marshals the returned HANDLE as a 32-bit int, so the
    # INVALID_HANDLE_VALUE comparison below misses on a 64-bit build -- a
    # locked file would read as opened, and this bug would come straight
    # back with nothing in the diff to explain it.
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


def _create_file_exclusive(path) -> tuple[bool, int]:
    """Open *path* denying all sharing. Returns (opened, last_error)."""
    kernel32 = _kernel32()
    handle = kernel32.CreateFileW(
        str(path),
        0x80000000,  # GENERIC_READ
        0,  # dwShareMode = 0: deny everything, which is the whole test
        None,
        3,  # OPEN_EXISTING
        0x80,  # FILE_ATTRIBUTE_NORMAL
        None,
    )
    if handle == wintypes.HANDLE(-1).value:  # INVALID_HANDLE_VALUE
        return False, ctypes.get_last_error()
    kernel32.CloseHandle(handle)
    return True, 0


def windows_file_is_closed(path, *, _create_file=_create_file_exclusive) -> bool:
    """Whether no other process holds *path* open.

    A share-mode-0 open is refused while any handle to the file exists, so
    this answers "has the recorder finished with it" directly rather than
    inferring it from the size. Our own handle lives for microseconds and
    is closed immediately.

    Fails OPEN. A probe that cannot get an answer -- permissions on a
    mapped drive, an antivirus filter, a path that vanished -- must not
    silently stop the app announcing recordings for the rest of the
    session. Guessing "closed" degrades to the behaviour this replaced,
    which is a repeated notification: annoying, and visible. That is the
    trade _save() makes with its swallowed OSError too.

    One consequence worth knowing: library.probe runs ffprobe over any
    recording whose duration is not already in the durations cache, and
    that holds a brief handle of its own. Overlapping with it reads as
    "still being written" and defers the announcement to the next poll,
    three seconds later.
    """
    opened, err = _create_file(path)
    if opened:
        return True
    return err not in _WRITER_STILL_HOLDS_IT


def file_is_closed(path) -> bool:
    """Platform default for the Watcher's probe.

    Off Windows there is no equivalent test -- POSIX advisory locks say
    nothing about ordinary writers -- and the app is Windows-only. Answering
    True there keeps the watcher's Linux behaviour exactly as it was.
    """
    if sys.platform != "win32":
        return True
    return windows_file_is_closed(path)


@dataclass
class SeenEntry:
    size: int
    mtime: float


def load_seen(path: Path) -> dict[str, SeenEntry]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, SeenEntry] = {}
    for key, value in raw.items():
        try:
            out[key] = SeenEntry(size=int(value["size"]), mtime=float(value["mtime"]))
        except (TypeError, KeyError, ValueError):
            continue
    return out


def save_seen(path: Path, seen: dict[str, SeenEntry]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: {"size": v.size, "mtime": v.mtime} for k, v in seen.items()}
    path.write_text(json.dumps(payload), encoding="utf-8")


class Watcher:
    def __init__(self, directory, seen_path, *, stable_polls: int = 3, is_closed=None):
        self.directory = Path(directory)
        self.seen_path = Path(seen_path)
        self.stable_polls = stable_polls
        # Injected seam rather than a platform branch inside poll_once: the
        # whole suite runs on Linux, where the real probe cannot exist.
        self.is_closed = file_is_closed if is_closed is None else is_closed
        self.seen = load_seen(self.seen_path)
        self._pending: dict[str, tuple[int, int]] = {}  # key -> (size, stable_count)

    def _save(self) -> None:
        """Persist the seen-set, degrading sanely if the disk can't take it.

        A write failure here (disk full, permissions, read-only mapped
        drive) must not raise: poll_once() is called from a Tk timer
        wrapped in a broad except, so an uncaught error here would make
        the watcher silently stop reporting recordings with nothing in
        the logs. Losing this save only means the in-memory seen-set is
        ahead of disk; at worst, files already announced this session get
        re-announced after a restart that happens to land on a still-full
        disk -- annoying, never silent data loss or a crash loop.
        """
        try:
            save_seen(self.seen_path, self.seen)
        except OSError:
            logger.warning(
                "Could not persist seen-set to %s", self.seen_path, exc_info=True
            )

    def baseline(self) -> None:
        """Establish the starting point without announcing anything.

        First ever run (no seen file): record every current file silently,
        so launching the app does not announce the user's whole back
        catalogue.

        Any later run (seen file exists): only prune. Files on disk but
        absent from the persisted set are genuinely new — recorded while
        the app was closed — and poll_once() announces them.
        """
        first_run = not self.seen_path.exists()
        if first_run:
            for path in library.discover(self.directory):
                try:
                    stat = path.stat()
                except OSError:
                    continue
                self.seen[str(path)] = SeenEntry(size=stat.st_size, mtime=stat.st_mtime)
        else:
            self.prune()
        self._save()

    def poll_once(self) -> list[Path]:
        """Return files that have just become stable and are new or changed."""
        ready: list[Path] = []
        for path in library.discover(self.directory):
            key = str(path)
            try:
                stat = path.stat()
            except OSError:
                continue
            entry = self.seen.get(key)
            if (
                entry is not None
                and entry.size == stat.st_size
                and entry.mtime == stat.st_mtime
            ):
                continue  # Unchanged since we last recorded it.
            previous = self._pending.get(key)
            if previous is not None and previous[0] == stat.st_size:
                count = previous[1] + 1
            else:
                count = 1
            if count >= self.stable_polls:
                # Steady size is the cheap filter; the handle probe is the
                # actual verdict, and it runs only once a file has settled
                # so a folder of old recordings is not opened every poll.
                #
                # A file still held open stays in _pending at its current
                # count. It is re-probed each poll from here on -- one
                # CreateFile every three seconds for one file -- and is
                # announced on the first poll after the writer lets go,
                # rather than waiting out another settle.
                if not self.is_closed(path):
                    self._pending[key] = (stat.st_size, count)
                    continue
                self._pending.pop(key, None)
                self.seen[key] = SeenEntry(size=stat.st_size, mtime=stat.st_mtime)
                ready.append(path)
            else:
                self._pending[key] = (stat.st_size, count)
        if ready:
            self._save()
        return ready

    def rebind(self, directory) -> None:
        """Point at a new directory and silently baseline its contents.

        Used when the user changes the recording folder in Settings. Without
        this the watcher keeps polling the old folder until restart, and
        without the silent baseline the new folder's whole back catalogue
        would be announced at once.
        """
        self.directory = Path(directory)
        self._pending.clear()
        for path in library.discover(self.directory):
            try:
                stat = path.stat()
            except OSError:
                continue
            self.seen[str(path)] = SeenEntry(size=stat.st_size, mtime=stat.st_mtime)
        self._save()

    def forget(self, path) -> None:
        """Drop an entry, e.g. after the user deletes the file."""
        key = str(path)
        self.seen.pop(key, None)
        self._pending.pop(key, None)
        self._save()

    def rename(self, old_path, new_path) -> None:
        """Follow a renamed recording, so it is not announced a second time.

        The seen-set is keyed by path, and a rename produces a path this
        watcher has never seen. Without this, the next poll finds a
        settled, closed, unknown file and announces it as a finished
        recording -- preselected, ready to upload, for the second time.
        The user renamed a file and Wingman reported a new one, which reads
        as a bug about OBS rather than about the rename.

        NOT ``forget(old)`` plus a poll: forget is precisely what makes the
        file look new. The entry has to arrive at the new key intact, and
        it is still accurate there -- a rename changes neither size nor
        mtime.

        The pending entry moves too. A file part-way through its stability
        count would otherwise start its settle again, deferring a genuine
        announcement by up to ``stable_polls`` polls for no reason.

        A path with no entry is a no-op in both maps. Renaming a recording
        the watcher has never seen must not invent one, or the announcement
        of a genuinely new file is suppressed.
        """
        old_key, new_key = str(old_path), str(new_path)
        entry = self.seen.pop(old_key, None)
        if entry is not None:
            self.seen[new_key] = entry
        pending = self._pending.pop(old_key, None)
        if pending is not None:
            self._pending[new_key] = pending
        if entry is not None:
            self._save()

    def prune(self) -> int:
        """Drop entries whose files no longer exist. Returns the count."""
        gone = [k for k in self.seen if not Path(k).exists()]
        for key in gone:
            del self.seen[key]
        if gone:
            self._save()
        return len(gone)
