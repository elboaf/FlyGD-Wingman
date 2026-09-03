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
clock, without starting a worker.  The threaded ``start`` / ``stop`` lifecycle
wraps it with the one-second-poll / five-second-rescan cadence the spec requires.
"""

from __future__ import annotations

import contextlib
import datetime
import logging
import threading
import time
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

# Worker cadence.
_POLL_INTERVAL_S = 1.0
_RESCAN_INTERVAL_S = 5.0


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
        scan_once(now_utc)   -- deterministic test seam (no thread)
        stop(timeout=3.0)
        health() -> StreamHealth
    """

    def __init__(self) -> None:
        self._folder: Path | None = None
        self._tracked: dict[str, _Tracked] = {}
        self._subscribers: list[Callable] = []
        self._next_generation = 1
        self._seen_first_scan = False
        # Every normalized path ever observed during any scan (whether
        # selected, failed, or cap-evicted).  A file known to have been
        # present on disk during a prior scan is ALWAYS baselined at EOF
        # when first selected — never read from zero — so transient stat
        # failure, header failure, or cap eviction followed by recovery
        # cannot replay history.
        self._known_paths: set[str] = set()
        # Tracks identities of sources that have been retired in this
        # folder generation.  Prevents replay when a folder disappears
        # and returns with the same files still on disk.
        self._retired_source_ids: set[SourceId] = set()
        self._started = False
        # Health tracking.  Errors are set during rescan/poll and cleared
        # only after a fully successful complete operation.
        self._last_error: str | None = None
        self._scan_errors: list[str] = []
        self._poll_errors: dict[str, str] = {}
        self._last_successful_rescan: float | None = None
        self._last_successful_poll: float | None = None
        # Lock protects ALL mutable state above.  _dispatch is called
        # OUTSIDE the lock with captured snapshots.
        self._lock = threading.Lock()
        # Worker thread support: a fresh stop event per start() generation.
        self._worker: threading.Thread | None = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    def subscribe(self, callback: Callable) -> Callable[[], None]:
        """Register a callback; returns an unsubscribe callable."""
        with self._lock:
            self._subscribers.append(callback)

        def _unsub():
            with self._lock, contextlib.suppress(ValueError):
                self._subscribers.remove(callback)

        return _unsub

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, folder: Path) -> None:
        """Begin streaming.  Spawns a non-daemon worker with a fresh stop event.

        Idempotent: calling start() while already running is a no-op.
        """
        with self._lock:
            if self._started:
                return
            self._folder = Path(folder)
            self._started = True
            self._last_error = None
            self._scan_errors = []
            self._poll_errors = {}
            # Fresh stop event per start generation so a leftover set()
            # from a previous stop cannot immediately kill the new worker.
            self._stop_event = threading.Event()
            stop_ev = self._stop_event
            folder_path = self._folder

        # Non-daemon: the app must call stop() explicitly, matching the
        # spec's "shared workers stop and join after their consumers
        # detach, preserving the existing non-daemon shutdown guarantees".
        worker = threading.Thread(
            target=self._run,
            args=(folder_path, stop_ev),
            name="gamelog-stream",
            daemon=False,
        )
        with self._lock:
            self._worker = worker
        worker.start()

    def stop(self, timeout: float = 3.0) -> None:
        """Signal the worker and join with a bounded timeout.  Idempotent."""
        with self._lock:
            worker = self._worker
            stop_ev = self._stop_event
            self._started = False
        if worker is not None:
            stop_ev.set()
            worker.join(timeout)
            with self._lock:
                if self._worker is worker:
                    self._worker = None

    def _run(self, folder: Path, stop_event: threading.Event) -> None:
        """Worker loop: 1-second poll, 5-second rescan."""
        last_rescan = 0.0
        while not stop_event.is_set():
            now_mono = time.monotonic()
            now_utc = datetime.datetime.now(tz=UTC)
            do_rescan = (now_mono - last_rescan) >= _RESCAN_INTERVAL_S
            if do_rescan:
                self._rescan(now_utc)
                last_rescan = now_mono
            self._poll()
            stop_event.wait(_POLL_INTERVAL_S)

    def request_source(self, character: str) -> None:
        """Re-publish lifecycle for a character, or unavailable if unknown."""
        with self._lock:
            tracked = self._tracked.get(character)
            if tracked is not None:
                event = SourceLifecycle(
                    character=character,
                    generation=tracked.generation,
                    source_id=tracked.source_id,
                    available=True,
                    active=True,
                )
            else:
                event = SourceLifecycle(
                    character=character,
                    generation=0,
                    source_id=None,
                    available=False,
                    active=False,
                )
            subs = list(self._subscribers)
        _dispatch(event, subs)

    def health(self) -> StreamHealth:
        with self._lock:
            if not self._started:
                return StreamHealth(state="stopped")
            if self._folder is not None and not self._folder.exists():
                return StreamHealth(state="missing_folder", detail=str(self._folder))
            if self._last_error:
                return StreamHealth(state="error", detail=self._last_error)
            if self._scan_errors:
                return StreamHealth(
                    state="error",
                    detail=f"{len(self._scan_errors)} scan error(s)",
                )
            if self._poll_errors:
                return StreamHealth(
                    state="error",
                    detail=f"{len(self._poll_errors)} source error(s)",
                )
            if self._tracked:
                return StreamHealth(
                    state="active", detail=f"{len(self._tracked)} character(s)"
                )
            return StreamHealth(state="running")

    # ------------------------------------------------------------------
    # Core: synchronous scan + poll (deterministic test seam)
    # ------------------------------------------------------------------

    def scan_once(self, now_utc: datetime.datetime) -> None:
        """One complete rescan + poll cycle on the caller's thread.

        This is the deterministic test seam: no worker, no real clock.
        Production code uses start()/stop() which run the worker.
        """
        self._rescan(now_utc)
        self._poll()

    def _rescan(self, now_utc: datetime.datetime) -> None:
        """Discover logs and reconcile tracked sources.

        Acquires _lock for state reads/writes, releases before dispatch.
        """
        with self._lock:
            folder = self._folder
        if folder is None:
            return

        # -- Enumerate outside the lock (I/O) ---
        try:
            entries = list(folder.glob("*.txt"))
        except OSError:
            logger.debug("Gamelogs folder unreadable: %s", folder)
            # Retire all under lock, dispatch outside
            events = self._retire_all_sources_locked(
                error=f"Folder unreadable: {folder}"
            )
            with self._lock:
                subs = list(self._subscribers)
            for ev in events:
                _dispatch(ev, subs)
            return

        if not entries and not folder.exists():
            events = self._retire_all_sources_locked(error=None)
            with self._lock:
                subs = list(self._subscribers)
            for ev in events:
                _dispatch(ev, subs)
            return

        # -- Build candidate list outside the lock (I/O-heavy) ---
        cutoff = now_utc - MAX_AGE
        candidates = []
        scan_errors: list[str] = []
        # Collect paths seen this scan into a local set.  They are
        # committed to _known_paths only AFTER selection decisions, so a
        # file appearing for the first time in this scan is not mistaken
        # for a previously-known file that should baseline at EOF.
        # We track the UNRESOLVED absolute path (not resolve()) because a
        # broken symlink's resolve() target differs from the real file's
        # resolve(), and we need the tombstone to match when the real
        # file reappears at the same directory entry.
        paths_this_scan: set[str] = set()
        for path in entries:
            normalized = str(path.absolute())
            paths_this_scan.add(normalized)
            try:
                mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            except OSError as exc:
                scan_errors.append(f"stat {path.name}: {exc}")
                continue
            if mtime < cutoff:
                continue
            header = combatlog.parse_header(path)
            if header is None:
                # Unparseable header — not an error for health (could be a
                # character-less stub).  The path is still tombstoned
                # via paths_this_scan, committed below.
                continue
            if header.listener.strip().upper() == "EVE":
                continue
            candidates.append((header, path, mtime))

        # -- Dedup to one log per character FIRST, then cap ---
        # Capping before dedup lets one character with more than MAX_FILES
        # sessions inside the window (a client that relogged repeatedly)
        # consume the whole budget on its own, silently starving every
        # other character — no error, no log line, they just stop alerting.
        #
        # session_start alone is not a total order: two logs for the same
        # character can carry an identical "Session Started" header (the
        # same relog, or a client that copies its header verbatim), and
        # list.sort() is stable, so a tie falls through to glob()'s
        # enumeration order — which is filesystem-dependent and differs
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

        # -- Reconcile under lock, collect events ---
        events: list[SourceLifecycle] = []
        with self._lock:
            # Retire characters no longer in best
            for character in list(self._tracked):
                if character not in best:
                    tracked = self._tracked.pop(character)
                    self._retired_source_ids.add(tracked.source_id)
                    events.append(
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
                    events.append(
                        SourceLifecycle(
                            character=character,
                            generation=existing.generation,
                            source_id=existing.source_id,
                            available=False,
                            active=False,
                        )
                    )

                # Determine initial read position.
                # A file already on disk at the first scan, one whose
                # identity we've retired, or one whose path we've seen
                # in a PREVIOUS scan (even if stat/header failed):
                # baseline at EOF.  A genuinely new file appearing after
                # the first scan whose path was NEVER seen before: read
                # from zero.
                #
                # Baseline stat failure: try to read EOF. If stat fails,
                # baseline at position MAX (will wait for the file to
                # become readable and catch up via the size < position
                # rotation path, which creates a new generation).  Never
                # fall back to zero for a known path.
                start = 0
                path_key = str(path.absolute())
                is_known = (
                    not self._seen_first_scan
                    or source_id in self._retired_source_ids
                    or path_key in self._known_paths
                )
                if is_known:
                    try:
                        start = path.stat().st_size
                    except OSError:
                        # Cannot determine EOF — do NOT fall back to zero.
                        # Use a sentinel that will trigger the truncation
                        # path (size < position → rotation with new
                        # generation) once the file becomes readable.
                        start = 2**63

                gen = self._next_generation
                self._next_generation += 1

                self._tracked[character] = _Tracked(
                    character=character,
                    path=path,
                    position=start,
                    source_id=source_id,
                    generation=gen,
                )

                events.append(
                    SourceLifecycle(
                        character=character,
                        generation=gen,
                        source_id=source_id,
                        available=True,
                        active=True,
                    )
                )

            self._seen_first_scan = True

            # Commit this scan's paths to _known_paths AFTER selection
            # decisions.  A file appearing for the first time in this scan
            # was correctly treated as new (read from zero) or historical
            # (first scan, baselined at EOF).  On FUTURE scans, it will
            # be treated as known and baselined at EOF if re-selected
            # after eviction or stat failure.
            self._known_paths.update(paths_this_scan)

            # Health: record scan errors, clear only when zero errors.
            self._scan_errors = scan_errors
            if not scan_errors:
                self._last_successful_rescan = time.monotonic()
                # Clear folder-level error only after a fully clean rescan.
                self._last_error = None

            subs = list(self._subscribers)

        # -- Dispatch outside the lock ---
        for ev in events:
            _dispatch(ev, subs)

    def _retire_all_sources_locked(self, *, error: str | None) -> list[SourceLifecycle]:
        """Retire every tracked source (folder loss).  Caller holds NO lock.

        Returns the lifecycle events to dispatch outside the lock.
        """
        events: list[SourceLifecycle] = []
        with self._lock:
            for character, tracked in list(self._tracked.items()):
                self._retired_source_ids.add(tracked.source_id)
                events.append(
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
            self._last_error = error
        return events

    def _poll(self) -> None:
        """Read appended data from all tracked files and dispatch facts.

        Per-source errors are recorded without suppressing other sources.
        Errors clear only after a fully successful complete poll.
        """
        # Snapshot tracked under lock
        with self._lock:
            snapshot = list(self._tracked.items())
            subs = list(self._subscribers)

        all_events: list[SourceLifecycle | CombatFact] = []
        poll_errors: dict[str, str] = {}

        for character, tracked in snapshot:
            events, err = self._read_source(character, tracked)
            all_events.extend(events)
            if err:
                poll_errors[character] = err

        # Update health under lock
        with self._lock:
            self._poll_errors = poll_errors
            if not poll_errors:
                self._last_successful_poll = time.monotonic()

        # Dispatch outside lock
        for ev in all_events:
            _dispatch(ev, subs)

    def _read_source(
        self, character: str, tracked: _Tracked
    ) -> tuple[list[SourceLifecycle | CombatFact], str | None]:
        """Read new data from one tracked file and return parsed events.

        On truncation (size < position), the source is retired and
        reactivated with a new generation — lifecycle events are emitted
        before any facts from the new content.

        Returns (events, error_string_or_None).
        """
        events: list[SourceLifecycle | CombatFact] = []
        try:
            size = tracked.path.stat().st_size
        except OSError as exc:
            return [], f"stat: {exc}"

        if size < tracked.position:
            # File shrank — treat as rotation.  Retire the old generation
            # and create a new one so downstream consumers see a clean
            # lifecycle boundary.
            old_gen = tracked.generation
            old_sid = tracked.source_id
            with self._lock:
                new_gen = self._next_generation
                self._next_generation += 1
                tracked.generation = new_gen
            tracked.position = 0
            tracked.partial = ""
            events.append(
                SourceLifecycle(
                    character=character,
                    generation=old_gen,
                    source_id=old_sid,
                    available=False,
                    active=False,
                )
            )
            events.append(
                SourceLifecycle(
                    character=character,
                    generation=new_gen,
                    source_id=tracked.source_id,
                    available=True,
                    active=True,
                )
            )

        if size == tracked.position:
            return events, None

        try:
            with open(tracked.path, "rb") as fh:
                fh.seek(tracked.position)
                chunk = fh.read(size - tracked.position)
                tracked.position = fh.tell()
        except OSError as exc:
            return events, f"read: {exc}"

        text = tracked.partial + chunk.decode("utf-8", errors="replace")
        lines = text.split("\n")
        # Last element is whatever follows the final newline: either empty,
        # or half a line still being written.
        tracked.partial = lines.pop()

        # Capture generation under lock to verify currency before dispatch.
        with self._lock:
            current_gen = tracked.generation
            current_sid = tracked.source_id

        for line in lines:
            if not line.strip():
                continue
            parsed = parsing.parse_line(line, character)
            for fact in parsed.facts:
                # Verify the generation is still current — a concurrent
                # rescan could have retired this source while we were
                # reading.  Drop facts from stale generations.
                with self._lock:
                    if tracked.generation != current_gen:
                        return events, None
                events.append(
                    CombatFact(
                        character=character,
                        source_generation=current_gen,
                        source_id=current_sid,
                        occurred_at=parsed.occurred_at,
                        kind=fact.kind,
                        amount=fact.amount,
                        source=fact.source,
                    )
                )

        return events, None


# ------------------------------------------------------------------
# Module-level dispatch — never called under the state lock.
# ------------------------------------------------------------------


def _dispatch(event: SourceLifecycle | CombatFact, subscribers: list[Callable]) -> None:
    """Deliver to every subscriber with callback isolation."""
    for callback in subscribers:
        try:
            callback(event)
        except Exception:
            logger.exception("Subscriber raised during dispatch")
