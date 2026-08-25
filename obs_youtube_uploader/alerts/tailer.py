"""Follow the EVE Gamelogs folder and turn new lines into events.

Polled, not watched: there is no FileSystemWatcher in the standard
library and watchdog would be a new runtime dependency. TriffView polls
at 1s anyway underneath its watcher, so this is its mechanism without
its optimisation, and one second of latency on "you are being shot" does
not change the decision the alert exists to prompt.

rescan() and poll() are separate and take no locks, so the thread in
service.py drives them on its own cadence and the tests drive them
directly.
"""

import datetime
import logging
from pathlib import Path
from typing import NamedTuple

from .. import combatlog
from . import patterns

logger = logging.getLogger(__name__)

UTC = datetime.UTC

# Bounds the working set on a machine with months of logs.
MAX_AGE = datetime.timedelta(hours=12)
# Matches combatlog.MAX_FILES. Six clients that each relog once inside the
# cutoff is already twelve real logs before stubs, and combatlog.py:48-50
# records that character-less stubs are 47% of a real folder -- which is
# why the cap is applied AFTER header filtering, not before.
MAX_FILES = 64


class Event(NamedTuple):
    character: str
    event: str
    source: str


class _Tracked:
    __slots__ = ("partial", "path", "position")

    def __init__(self, path: Path, position: int):
        self.path = path
        self.position = position
        self.partial = ""


class Tailer:
    def __init__(self, folder: Path):
        self._folder = Path(folder)
        # character -> _Tracked. One log per character: a relog leaves the
        # old file on disk and reading both would alert twice.
        self._tracked: dict[str, _Tracked] = {}
        self._seen_first_scan = False

    def characters(self) -> list[str]:
        return sorted(self._tracked)

    def rescan(self, now_utc: datetime.datetime) -> None:
        """Discover logs and attribute them to characters."""
        candidates = []
        try:
            entries = list(self._folder.glob("*.txt"))
        except OSError:
            logger.debug("Gamelogs folder unreadable: %s", self._folder)
            return
        cutoff = now_utc - MAX_AGE
        for path in entries:
            try:
                mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            except OSError:
                continue
            if mtime < cutoff:
                continue
            header = combatlog.parse_header(path)
            if header is None or header.listener.strip().upper() == "EVE":
                # No pilot logged in. Excluding these here keeps them from
                # consuming the cap.
                continue
            candidates.append((header, path, mtime))

        # Newest first, then capped: an unordered cap drops live logs.
        candidates.sort(key=lambda c: c[0].session_start, reverse=True)
        best: dict[str, tuple] = {}
        for header, path, mtime in candidates[:MAX_FILES]:
            best.setdefault(header.listener, (path, mtime))

        for character, (path, _mtime) in best.items():
            existing = self._tracked.get(character)
            if existing is not None and existing.path == path:
                continue
            # A file already on disk at the first scan is history; one that
            # appears later is live. Without this, enabling alerts replays
            # the morning's fight as a burst.
            start = 0
            if not self._seen_first_scan:
                try:
                    start = path.stat().st_size
                except OSError:
                    start = 0
            self._tracked[character] = _Tracked(path, start)

        for character in list(self._tracked):
            if character not in best:
                del self._tracked[character]

        self._seen_first_scan = True

    def poll(self) -> list[Event]:
        """Read whatever has been appended since the last call."""
        events: list[Event] = []
        for character, tracked in self._tracked.items():
            events.extend(self._read(character, tracked))
        return events

    def _read(self, character: str, tracked: _Tracked) -> list[Event]:
        try:
            size = tracked.path.stat().st_size
        except OSError:
            return []
        if size < tracked.position:
            # Smaller than where we were: the file rotated.
            tracked.position = 0
            tracked.partial = ""
        if size == tracked.position:
            return []
        try:
            with open(tracked.path, "rb") as fh:
                fh.seek(tracked.position)
                chunk = fh.read(size - tracked.position)
                tracked.position = fh.tell()
        except OSError:
            return []

        text = tracked.partial + chunk.decode("utf-8", errors="replace")
        lines = text.split("\n")
        # The last element is whatever follows the final newline: either
        # empty, or half a line that is still being written.
        tracked.partial = lines.pop()

        events = []
        for line in lines:
            match = patterns.match_line(line)
            if match is not None:
                events.append(Event(character, match.event, match.source))
        return events
