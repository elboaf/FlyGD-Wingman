"""Source-aware shared gamelog stream.

Owns folder discovery, per-character file selection, cursor tracking, partial-
line buffering, EOF baselining, rotation/relog handling, replay prevention, and
source lifecycle publication.  Every subscriber receives SourceLifecycle events
before any CombatFact for the corresponding generation; the serialised dispatch
order is the correctness contract.

Source-selection rules (age cutoff, dedup-before-cap, session-start + mtime
tie-break) are ported from alerts/tailer.py with their proven comments.  The
Tailer is NOT deleted or production-rewired here.

The synchronous ``scan_once(now_utc)`` method is the deterministic test seam:
it runs one complete rescan + poll cycle on the caller's thread with an injected
clock.  The threaded ``start`` / ``stop`` lifecycle wraps it with the existing
one-second-poll / five-second-rescan cadence.
"""

from __future__ import annotations

import contextlib
import datetime
import logging
import threading
from collections.abc import Callable
from pathlib import Path

from .. import combatlog
from . import parsing
from .model import CombatFact, SourceId, SourceLifecycle, StreamHealth

logger = logging.getLogger(__name__)

UTC = datetime.UTC

# Bounds the working set on a machine with months of logs.  Ported from
# alerts/tailer.py.
MAX_AGE = datetime.timedelta(hours=12)

# Matches combatlog.MAX_FILES.  Six clients that each relog once inside the
# cutoff is already twelve real logs before stubs, and combatlog.py:48-50
# records that character-less stubs are 47% of a real folder -- which is
# why the cap is applied AFTER header filtering, not before.
MAX_FILES = 64


class _Tracked:
    """Per-character file cursor and partial-line buffer."""

    __slots__ = ("character", "generation", "partial", "path", "position", "source_id")

    def __init__(
        self,
        character: str,
        path: Path,
        position: int,
        source_id: SourceId,
        generation: int,
    ):
        self.character = character
        self.path = path
        self.position = position
        self.source_id = source_id
        self.generation = generation
        self.partial = ""


class GameLogStream:
    """Shared, source-aware gamelog stream.

    Public interface:
        subscribe(callback) -> unsubscribe callable
        start(folder)
        request_source(character)
        scan_once(now_utc)   -- deterministic test seam
        stop(timeout=3.0)
        health() -> StreamHealth
    """

    def __init__(self) -> None:
        self._folder: Path | None = None
        self._tracked: dict[str, _Tracked] = {}
        self._subscribers: list[Callable] = []
        self._next_generation = 1
        self._seen_first_scan = False
        # Tracks identities of sources that have been retired in this
        # folder generation.  Prevents replay when a folder disappears
        # and returns with the same files still on disk.
        self._retired_source_ids: set[SourceId] = set()
        # Whether the current folder has been baselined (first scan completed).
        self._folder_baselined = False
        self._started = False
        self._last_error: str | None = None
        self._lock = threading.Lock()
        # Worker thread support
        self._worker: threading.Thread | None = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    def subscribe(self, callback: Callable) -> Callable[[], None]:
        """Register a callback; returns an unsubscribe callable."""
        self._subscribers.append(callback)

        def _unsub():
            with contextlib.suppress(ValueError):
                self._subscribers.remove(callback)

        return _unsub

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, folder: Path) -> None:
        self._folder = Path(folder)
        self._started = True
        self._last_error = None

    def stop(self, timeout: float = 3.0) -> None:
        if self._worker is not None:
            self._stop_event.set()
            self._worker.join(timeout)
            self._worker = None
        self._started = False

    def request_source(self, character: str) -> None:
        """Re-publish lifecycle for a character, or unavailable if unknown."""
        tracked = self._tracked.get(character)
        if tracked is not None:
            self._dispatch(
                SourceLifecycle(
                    character=character,
                    generation=tracked.generation,
                    source_id=tracked.source_id,
                    available=True,
                    active=True,
                )
            )
        else:
            self._dispatch(
                SourceLifecycle(
                    character=character,
                    generation=0,
                    source_id=None,
                    available=False,
                    active=False,
                )
            )

    def health(self) -> StreamHealth:
        if not self._started:
            return StreamHealth(state="stopped")
        if self._folder is not None and not self._folder.exists():
            return StreamHealth(state="missing_folder", detail=str(self._folder))
        if self._last_error:
            return StreamHealth(state="error", detail=self._last_error)
        if self._tracked:
            return StreamHealth(
                state="active", detail=f"{len(self._tracked)} character(s)"
            )
        return StreamHealth(state="running")

    # ------------------------------------------------------------------
    # Core: synchronous scan + poll (deterministic test seam)
    # ------------------------------------------------------------------

    def scan_once(self, now_utc: datetime.datetime) -> None:
        """One complete rescan + poll cycle.  Thread-safe via _lock."""
        self._rescan(now_utc)
        self._poll()

    def _rescan(self, now_utc: datetime.datetime) -> None:
        """Discover logs and reconcile tracked sources."""
        if self._folder is None:
            return

        try:
            entries = list(self._folder.glob("*.txt"))
        except OSError:
            logger.debug("Gamelogs folder unreadable: %s", self._folder)
            self._last_error = f"Folder unreadable: {self._folder}"
            # Retire all sources on folder loss
            self._retire_all_sources()
            return

        if not entries and not self._folder.exists():
            self._last_error = None  # Not an error, just missing
            self._retire_all_sources()
            return

        # Clear folder-level error on successful glob
        self._last_error = None

        cutoff = now_utc - MAX_AGE
        candidates = []
        for path in entries:
            try:
                mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            except OSError:
                continue
            if mtime < cutoff:
                continue
            header = combatlog.parse_header(path)
            if header is None or header.listener.strip().upper() == "EVE":
                continue
            candidates.append((header, path, mtime))

        # Dedup to one log per character FIRST, then cap: capping before
        # dedup lets one character with more than MAX_FILES sessions
        # inside the window (a client that relogged repeatedly) consume
        # the whole budget on its own, silently starving every other
        # character -- no error, no log line, they just stop alerting.
        #
        # session_start alone is not a total order: two logs for the same
        # character can carry an identical "Session Started" header (the
        # same relog, or a client that copies its header verbatim), and
        # list.sort() is stable, so a tie falls through to glob()'s
        # enumeration order -- which is filesystem-dependent and differs
        # between platforms. mtime as the tie-break makes the newest write
        # win everywhere: the more recently written file is the live one.
        candidates.sort(key=lambda c: (c[0].session_start, c[2]), reverse=True)
        best: dict[str, tuple] = {}
        for header, path, mtime in candidates:
            best.setdefault(header.listener, (header, path, mtime))
        # `best`'s insertion order already tracks each character's most
        # recent session: candidates is sorted newest-first and setdefault
        # only records a character's first (i.e. newest) occurrence, so
        # slicing here keeps the MAX_FILES most recently active
        # characters rather than the first MAX_FILES sessions of however
        # few characters produced them.
        best = dict(list(best.items())[:MAX_FILES])

        # Retire characters no longer in best
        for character in list(self._tracked):
            if character not in best:
                tracked = self._tracked.pop(character)
                self._retired_source_ids.add(tracked.source_id)
                self._dispatch(
                    SourceLifecycle(
                        character=character,
                        generation=tracked.generation,
                        source_id=tracked.source_id,
                        available=False,
                        active=False,
                    )
                )

        # Activate or replace sources
        for character, (header, path, mtime) in best.items():
            source_id = SourceId(
                normalized_path=str(path.resolve()),
                session_start_utc=header.session_start,
            )
            existing = self._tracked.get(character)

            if existing is not None and existing.source_id == source_id:
                # Same file, no change
                continue

            # Retire the old source if replaced
            if existing is not None:
                self._retired_source_ids.add(existing.source_id)
                self._dispatch(
                    SourceLifecycle(
                        character=character,
                        generation=existing.generation,
                        source_id=existing.source_id,
                        available=False,
                        active=False,
                    )
                )

            # Determine initial read position.
            # A file already on disk at the first scan OR one whose identity
            # we've seen and retired: baseline at EOF (no replay).
            # A genuinely new file appearing after the first scan: read from
            # zero.
            start = 0
            is_recovered = source_id in self._retired_source_ids
            if not self._seen_first_scan or is_recovered:
                try:
                    start = path.stat().st_size
                except OSError:
                    start = 0

            gen = self._next_generation
            self._next_generation += 1

            self._tracked[character] = _Tracked(
                character=character,
                path=path,
                position=start,
                source_id=source_id,
                generation=gen,
            )

            self._dispatch(
                SourceLifecycle(
                    character=character,
                    generation=gen,
                    source_id=source_id,
                    available=True,
                    active=True,
                )
            )

        self._seen_first_scan = True

    def _retire_all_sources(self) -> None:
        """Retire every tracked source (folder loss)."""
        for character, tracked in list(self._tracked.items()):
            self._retired_source_ids.add(tracked.source_id)
            self._dispatch(
                SourceLifecycle(
                    character=character,
                    generation=tracked.generation,
                    source_id=tracked.source_id,
                    available=False,
                    active=False,
                )
            )
        self._tracked.clear()
        self._seen_first_scan = False

    def _poll(self) -> None:
        """Read appended data from all tracked files and dispatch facts."""
        for character, tracked in list(self._tracked.items()):
            self._read_source(character, tracked)

    def _read_source(self, character: str, tracked: _Tracked) -> None:
        """Read new data from one tracked file and dispatch parsed facts."""
        try:
            size = tracked.path.stat().st_size
        except OSError:
            return
        if size < tracked.position:
            # File shrank — rotation.  Reset position and partial buffer.
            tracked.position = 0
            tracked.partial = ""
        if size == tracked.position:
            return
        try:
            with open(tracked.path, "rb") as fh:
                fh.seek(tracked.position)
                chunk = fh.read(size - tracked.position)
                tracked.position = fh.tell()
        except OSError:
            return

        text = tracked.partial + chunk.decode("utf-8", errors="replace")
        lines = text.split("\n")
        # Last element is whatever follows the final newline: either empty,
        # or half a line still being written.
        tracked.partial = lines.pop()

        for line in lines:
            if not line.strip():
                continue
            parsed = parsing.parse_line(line, character)
            for fact in parsed.facts:
                self._dispatch(
                    CombatFact(
                        character=character,
                        source_generation=tracked.generation,
                        source_id=tracked.source_id,
                        occurred_at=parsed.occurred_at,
                        kind=fact.kind,
                        amount=fact.amount,
                        source=fact.source,
                    )
                )

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, event: SourceLifecycle | CombatFact) -> None:
        """Deliver to every subscriber with callback isolation."""
        for callback in list(self._subscribers):
            try:
                callback(event)
            except Exception:
                logger.exception("Subscriber raised during dispatch")
