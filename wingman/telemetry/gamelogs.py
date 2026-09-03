"""Source-aware shared gamelog stream.

Owns folder discovery, per-character file selection, cursor tracking, partial-
line buffering, EOF baselining, rotation/relog handling, replay prevention, and
source lifecycle publication.  Every subscriber receives SourceLifecycle events
before any CombatFact for the corresponding generation; the serialised dispatch
order is the correctness contract.

Source-selection rules (age cutoff, dedup-before-cap, session-start + mtime
tie-break) are ported from alerts/tailer.py with their proven comments.  The
Tailer is NOT deleted or production-rewired here.

Concurrency model
-----------------
``_lock`` (Lock) guards all mutable state.  Subscribers are NEVER called
under ``_lock``.

Each operation (``scan_once``, ``request_source``, worker iteration) builds
an ordered event batch under ``_lock``, then appends it to ``_dispatch_queue``
(a list guarded by ``_dispatch_lock``).  A single ``_drain_queue`` call
delivers the batches in FIFO order on the caller's thread.  Because rescan
and poll run inside one ``scan_once`` call, rescan's activation lifecycle
is guaranteed to be enqueued — and therefore delivered — before poll's facts.
A reentrant callback that triggers ``request_source`` appends its batch
*behind* the current batch; the drainer delivers it in order after the
current batch completes, so no interleaving is possible.

``_lifecycle_lock`` (Lock) makes ``start`` / ``stop`` atomic.  ``start``
refuses to launch a second worker while a timed-out worker is still alive.
``stop`` retains the worker reference on timeout so a later ``stop`` can
retry joining.  Only once the worker is confirmed dead may ``start`` create
a fresh generation.

``scan_once(now_utc)`` is the deterministic test seam.  Tests inject
``_noop_thread_factory`` so ``start()`` sets up folder/state without
spawning a real thread.

Injected seams for testing
--------------------------
``_thread_factory``, ``_clock`` (monotonic), ``_utc_now``, ``_wait_fn``,
``_read_header`` (wraps ``combatlog.parse_header`` with readable-open guard),
``_get_file_size`` (wraps ``path.stat().st_size``).
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

# Matches combatlog.MAX_FILES.
MAX_FILES = 64

# Worker cadence.
POLL_INTERVAL_S = 1.0
RESCAN_INTERVAL_S = 5.0
# Health: stale after this many consecutive poll intervals without a
# successful complete poll.
_STALE_POLLS = 3


def _noop_thread_factory(
    *, target: Callable, args: tuple, name: str, daemon: bool
) -> threading.Thread:
    """Test seam: return a Thread-shaped object that never starts."""

    class _NoopThread:
        def __init__(self) -> None:
            self.daemon = daemon

        def start(self) -> None:
            pass

        def is_alive(self) -> bool:
            return False

        def join(self, timeout: float | None = None) -> None:
            pass

    return _NoopThread()  # type: ignore[return-value]


def _real_thread_factory(
    *, target: Callable, args: tuple, name: str, daemon: bool
) -> threading.Thread:
    return threading.Thread(target=target, args=args, name=name, daemon=daemon)


def _default_read_header(path: Path) -> combatlog.LogHeader | None:
    """Production header reader: readable-open guard before parse_header.

    Distinguishes inaccessible files (raises OSError) from valid
    characterless stubs (returns None without error).
    """
    # Guard: can we open the file at all?  parse_header catches its own
    # OSError internally and returns None, so a permission error would be
    # silently conflated with a characterless stub.  The explicit open
    # surfaces I/O failures as exceptions for the caller to record.
    with open(path, "rb") as fh:
        fh.read(1)
    return combatlog.parse_header(path)


def _default_get_file_size(path: Path) -> int:
    return path.stat().st_size


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

    Inject ``_thread_factory=_noop_thread_factory`` for synchronous tests.
    """

    def __init__(
        self,
        *,
        _thread_factory: Callable[..., threading.Thread] = _real_thread_factory,
        _clock: Callable[[], float] = time.monotonic,
        _utc_now: Callable[[], datetime.datetime] | None = None,
        _wait_fn: Callable[[threading.Event, float], None] | None = None,
        _read_header: Callable[
            [Path], combatlog.LogHeader | None
        ] = _default_read_header,
        _get_file_size: Callable[[Path], int] = _default_get_file_size,
    ) -> None:
        self._thread_factory = _thread_factory
        self._clock = _clock
        self._utc_now = _utc_now or (lambda: datetime.datetime.now(tz=UTC))
        self._wait_fn = _wait_fn or (lambda ev, t: ev.wait(t))
        self._read_header = _read_header
        self._get_file_size = _get_file_size

        self._folder: Path | None = None
        self._tracked: dict[str, _Tracked] = {}
        self._subscribers: list[Callable] = []
        self._next_generation = 1
        self._seen_first_scan = False
        self._known_paths: set[str] = set()
        self._retired_source_ids: set[SourceId] = set()
        self._started = False
        self._started_mono: float | None = None

        # Health tracking.
        self._last_error: str | None = None
        self._scan_errors: list[str] = []
        self._poll_errors: dict[str, str] = {}
        self._last_successful_poll_mono: float | None = None
        self._last_successful_rescan_mono: float | None = None

        # _lock: guards ALL mutable state.  Never call subscribers under it.
        self._lock = threading.Lock()
        # _dispatch_queue + _dispatch_lock: serialized event delivery.
        # Each operation appends an ordered batch; _drain_queue delivers
        # them in FIFO order outside _lock.
        self._dispatch_queue: list[list[SourceLifecycle | CombatFact]] = []
        self._dispatch_lock = threading.Lock()
        # _lifecycle_lock: makes start/stop atomic.
        self._lifecycle_lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    def subscribe(self, callback: Callable) -> Callable[[], None]:
        """Register a callback; returns an unsubscribe callable."""
        with self._lock:
            self._subscribers.append(callback)

        def _unsub() -> None:
            with self._lock, contextlib.suppress(ValueError):
                self._subscribers.remove(callback)

        return _unsub

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self, folder: Path) -> None:
        """Begin streaming.  Spawns a worker via the thread factory.

        Idempotent.  Refuses to launch while a timed-out worker is alive.
        """
        with self._lifecycle_lock:
            with self._lock:
                # Refuse if already running OR a timed-out worker is alive.
                if self._started:
                    return
                if self._worker is not None and self._worker.is_alive():
                    return
                self._folder = Path(folder)
                self._started = True
                self._started_mono = self._clock()
                self._last_error = None
                self._scan_errors = []
                self._poll_errors = {}
                self._last_successful_poll_mono = None
                self._last_successful_rescan_mono = None
                self._stop_event = threading.Event()
                stop_ev = self._stop_event
            worker = self._thread_factory(
                target=self._run,
                args=(stop_ev,),
                name="gamelog-stream",
                daemon=False,
            )
            with self._lock:
                self._worker = worker
            worker.start()

    def stop(self, timeout: float = 3.0) -> None:
        """Signal the worker and join with a bounded timeout.  Idempotent.

        On timeout the worker is RETAINED and ``_started`` stays False so
        a later ``stop`` can retry joining.  ``start`` checks
        ``is_alive()`` and refuses to launch a second worker.
        """
        with self._lifecycle_lock:
            with self._lock:
                worker = self._worker
                stop_ev = self._stop_event
                self._started = False
            if worker is not None:
                stop_ev.set()
                worker.join(timeout)
                with self._lock:
                    if not worker.is_alive():
                        self._worker = None

    def _run(self, stop_event: threading.Event) -> None:
        """Worker loop: immediate rescan, then 1-second poll / 5-second rescan."""
        last_rescan = self._clock() - RESCAN_INTERVAL_S
        while not stop_event.is_set():
            now_mono = self._clock()
            now_utc = self._utc_now()
            do_rescan = (now_mono - last_rescan) >= RESCAN_INTERVAL_S
            if do_rescan:
                self._rescan(now_utc)
                last_rescan = self._clock()
            self._poll()
            self._drain_queue()
            self._wait_fn(stop_event, POLL_INTERVAL_S)

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
        self._enqueue([event])
        self._drain_queue()

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
            # Stale: check against last successful poll or start time.
            ref = self._last_successful_poll_mono
            if ref is None:
                ref = self._started_mono
            if ref is not None:
                age = self._clock() - ref
                if age > _STALE_POLLS * POLL_INTERVAL_S:
                    return StreamHealth(state="stale", detail=f"{age:.1f}s since poll")
            if self._tracked:
                return StreamHealth(
                    state="active", detail=f"{len(self._tracked)} character(s)"
                )
            return StreamHealth(state="running")

    # ------------------------------------------------------------------
    # Dispatch queue
    # ------------------------------------------------------------------

    def _enqueue(self, batch: list[SourceLifecycle | CombatFact]) -> None:
        if batch:
            with self._dispatch_lock:
                self._dispatch_queue.append(batch)

    def _drain_queue(self) -> None:
        """Deliver all queued batches in FIFO order.

        Called outside ``_lock``.  A reentrant callback that calls
        ``request_source`` appends behind the current batch; the loop
        picks it up on the next iteration.
        """
        while True:
            with self._dispatch_lock:
                if not self._dispatch_queue:
                    return
                batch = self._dispatch_queue.pop(0)
            with self._lock:
                subs = list(self._subscribers)
            for event in batch:
                for callback in subs:
                    try:
                        callback(event)
                    except Exception:
                        logger.exception("Subscriber raised during dispatch")

    # ------------------------------------------------------------------
    # Core: synchronous scan + poll (deterministic test seam)
    # ------------------------------------------------------------------

    def scan_once(self, now_utc: datetime.datetime) -> None:
        """One complete rescan + poll cycle on the caller's thread.

        Rescan enqueues lifecycle events, poll enqueues fact events, then
        ``_drain_queue`` delivers them all in order.
        """
        self._rescan(now_utc)
        self._poll()
        self._drain_queue()

    def _rescan(self, now_utc: datetime.datetime) -> None:
        """Discover logs and reconcile tracked sources.

        Acquires ``_lock`` for state.  Enqueues lifecycle events.
        """
        with self._lock:
            folder = self._folder
        if folder is None:
            return

        try:
            entries = list(folder.glob("*.txt"))
        except OSError:
            logger.debug("Gamelogs folder unreadable: %s", folder)
            events = self._retire_all_sources(error=f"Folder unreadable: {folder}")
            self._enqueue(events)
            return

        if not entries and not folder.exists():
            events = self._retire_all_sources(error=None)
            self._enqueue(events)
            return

        cutoff = now_utc - MAX_AGE
        candidates = []
        scan_errors: list[str] = []
        paths_this_scan: set[str] = set()

        for path in entries:
            paths_this_scan.add(str(path.absolute()))
            try:
                mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            except OSError as exc:
                scan_errors.append(f"stat {path.name}: {exc}")
                continue
            if mtime < cutoff:
                continue
            try:
                header = self._read_header(path)
            except OSError as exc:
                scan_errors.append(f"header {path.name}: {exc}")
                continue
            if header is None:
                continue
            if header.listener.strip().upper() == "EVE":
                continue
            candidates.append((header, path, mtime))

        # -- Dedup to one log per character FIRST, then cap ---
        candidates.sort(key=lambda c: (c[0].session_start, c[2]), reverse=True)
        best: dict[str, tuple] = {}
        for header, path, mtime in candidates:
            best.setdefault(header.listener, (header, path, mtime))
        best = dict(list(best.items())[:MAX_FILES])

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
                    continue

                # Determine initial read position BEFORE retiring old.
                path_key = str(path.absolute())
                is_known = (
                    not self._seen_first_scan
                    or source_id in self._retired_source_ids
                    or path_key in self._known_paths
                )
                if is_known:
                    try:
                        start = self._get_file_size(path)
                    except OSError as exc:
                        # Cannot baseline — do NOT activate, do NOT retire
                        # the old source.  Record an error and retry next
                        # scan.
                        scan_errors.append(f"baseline {path.name}: {exc}")
                        continue
                else:
                    start = 0

                # Only now retire the old source (new baseline succeeded).
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
            self._known_paths.update(paths_this_scan)
            self._scan_errors = scan_errors
            if not scan_errors:
                self._last_successful_rescan_mono = self._clock()
                self._last_error = None

        self._enqueue(events)

    def _retire_all_sources(self, *, error: str | None) -> list[SourceLifecycle]:
        """Retire every tracked source (folder loss)."""
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
        """Read appended data from all tracked files.  Enqueues fact events."""
        with self._lock:
            snapshot = list(self._tracked.items())

        all_events: list[SourceLifecycle | CombatFact] = []
        poll_errors: dict[str, str] = {}

        for character, tracked in snapshot:
            evts, err = self._read_source(character, tracked)
            all_events.extend(evts)
            if err:
                poll_errors[character] = err

        with self._lock:
            self._poll_errors = poll_errors
            if not poll_errors:
                self._last_successful_poll_mono = self._clock()

        self._enqueue(all_events)

    def _read_source(
        self, character: str, tracked: _Tracked
    ) -> tuple[list[SourceLifecycle | CombatFact], str | None]:
        """Read new data from one tracked file."""
        events: list[SourceLifecycle | CombatFact] = []
        try:
            size = tracked.path.stat().st_size
        except OSError as exc:
            return [], f"stat: {exc}"

        if size < tracked.position:
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
        tracked.partial = lines.pop()

        for line in lines:
            if not line.strip():
                continue
            # Verify tracked object is still current before emitting.
            with self._lock:
                current = self._tracked.get(character)
                if current is not tracked:
                    return events, None
                gen = tracked.generation
                sid = tracked.source_id
            parsed = parsing.parse_line(line, character)
            for fact in parsed.facts:
                events.append(
                    CombatFact(
                        character=character,
                        source_generation=gen,
                        source_id=sid,
                        occurred_at=parsed.occurred_at,
                        kind=fact.kind,
                        amount=fact.amount,
                        source=fact.source,
                    )
                )

        return events, None
