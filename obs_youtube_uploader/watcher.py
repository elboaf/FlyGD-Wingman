"""Poll a directory for finished recordings.

Polling rather than filesystem events: native change notifications are
unreliable on network and mapped drives, watchdog would be another
dependency, and polling one directory every few seconds costs nothing.

A file appearing is not a file finished. Size must hold steady across
several consecutive polls before the file is announced.
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from . import library

logger = logging.getLogger(__name__)


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
    def __init__(self, directory, seen_path, *, stable_polls: int = 3):
        self.directory = Path(directory)
        self.seen_path = Path(seen_path)
        self.stable_polls = stable_polls
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
            logger.warning("Could not persist seen-set to %s", self.seen_path, exc_info=True)

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
            if entry is not None and entry.size == stat.st_size and entry.mtime == stat.st_mtime:
                continue  # Unchanged since we last recorded it.
            previous = self._pending.get(key)
            if previous is not None and previous[0] == stat.st_size:
                count = previous[1] + 1
            else:
                count = 1
            if count >= self.stable_polls:
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

    def prune(self) -> int:
        """Drop entries whose files no longer exist. Returns the count."""
        gone = [k for k in self.seen if not Path(k).exists()]
        for key in gone:
            del self.seen[key]
        if gone:
            self._save()
        return len(gone)
