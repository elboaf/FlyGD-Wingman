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
``_op_lock`` (RLock) serializes every operation that reads tracked state AND
publishes events: ``scan_once``, ``request_source``, and every worker
iteration.  Within one operation, ``_lock`` (Lock) guards brief state
reads/writes; subscribers are NEVER called under ``_lock``.  Because
``_op_lock`` is held across both rescan and poll in ``scan_once``, an
activation lifecycle is guaranteed to publish before any facts for that
generation.

``_lifecycle_lock`` (Lock) makes ``start`` / ``stop`` atomic so a concurrent
``stop`` cannot return before the worker has been created and started.

``scan_once(now_utc)`` is the deterministic test seam.  It acquires
``_op_lock`` and runs one rescan + poll on the caller's thread.  Tests inject
a no-op thread factory so ``start()`` sets up folder/state without spawning a
real thread.
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
            self._alive = False

        def start(self) -> None:
            pass

        def is_alive(self) -> bool:
            return self._alive

        def join(self, timeout: float | None = None) -> None:
            pass

    return _NoopThread()  # type: ignore[return-value]


def _real_thread_factory(
    *, target: Callable, args: tuple, name: str, daemon: bool
) -> threading.Thread:
    return threading.Thread(target=target, args=args, name=name, daemon=daemon)


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
    Inject ``_clock`` (monotonic) and ``_utc_now`` for cadence tests.
    """

    def __init__(
        self,
        *,
        _thread_factory: Callable[..., threading.Thread] = _real_thread_factory,
        _clock: Callable[[], float] = time.monotonic,
        _utc_now: Callable[[], datetime.datetime] | None = None,
        _wait_fn: Callable[[threading.Event, float], None] | None = None,
    ) -> None:
        self._thread_factory = _thread_factory
        self._clock = _clock
        self._utc_now = _utc_now or (lambda: datetime.datetime.now(tz=UTC))
        self._wait_fn = _wait_fn or (lambda ev, t: ev.wait(t))
        self._folder: Path | None = None
        self._tracked: dict[str, _Tracked] = {}
        self._subscribers: list[Callable] = []
        self._next_generation = 1
        self._seen_first_scan = False
        # Every absolute path ever observed during any scan (whether
        # selected, failed, or cap-evicted).  Paths are committed AFTER
        # selection decisions each scan so a file first appearing in the
        # current scan is not mistakenly treated as previously known.
        self._known_paths: set[str] = set()
        # Tracks identities of sources that have been retired.  Prevents
        # replay when a folder disappears and returns.
        self._retired_source_ids: set[SourceId] = set()
        self._started = False

        # Health tracking.  Errors clear only after a fully successful
        # complete operation.
        self._last_error: str | None = None
        self._scan_errors: list[str] = []
        self._poll_errors: dict[str, str] = {}
        self._last_successful_poll_mono: float | None = None
        self._last_successful_rescan_mono: float | None = None

        # _lock: brief state reads/writes.  Never call subscribers under it.
        self._lock = threading.Lock()
        # _op_lock: serializes operations that read state AND publish events.
        self._op_lock = threading.RLock()
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

        Idempotent: calling start() while already running is a no-op.
        The lifecycle lock makes start/stop atomic — a concurrent stop()
        cannot return before the worker has been created and started.
        """
        with self._lifecycle_lock:
            with self._lock:
                if self._started:
                    return
                self._folder = Path(folder)
                self._started = True
                self._last_error = None
                self._scan_errors = []
                self._poll_errors = {}
                self._last_successful_poll_mono = None
                self._last_successful_rescan_mono = None
                # Fresh stop event per start generation.
                self._stop_event = threading.Event()
                stop_ev = self._stop_event
            # Worker created and started inside lifecycle_lock so stop()
            # cannot see _started=True without a live worker.
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

        On timeout the worker reference is RETAINED for later join/reconcile
        — never forgotten.
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
                    # Clear only if it terminated; on timeout retain for
                    # later reconcile.
                    if not worker.is_alive():
                        self._worker = None

    def _run(self, stop_event: threading.Event) -> None:
        """Worker loop: immediate rescan, then 1-second poll / 5-second rescan."""
        # Force an immediate rescan on the first iteration.
        last_rescan = self._clock() - RESCAN_INTERVAL_S
        while not stop_event.is_set():
            now_mono = self._clock()
            now_utc = self._utc_now()
            do_rescan = (now_mono - last_rescan) >= RESCAN_INTERVAL_S
            with self._op_lock:
                if do_rescan:
                    self._rescan(now_utc)
                    last_rescan = self._clock()
                self._poll()
            self._wait_fn(stop_event, POLL_INTERVAL_S)

    def request_source(self, character: str) -> None:
        """Re-publish lifecycle for a character, or unavailable if unknown."""
        with self._op_lock:
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
            # Stale: had a successful poll once but none recently.
            if self._last_successful_poll_mono is not None:
                age = self._clock() - self._last_successful_poll_mono
                if age > _STALE_POLLS * POLL_INTERVAL_S:
                    return StreamHealth(state="stale", detail=f"{age:.1f}s since poll")
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

        Acquires ``_op_lock`` so rescan's activation lifecycle is
        guaranteed to publish before poll's facts.  Production code uses
        ``start()`` / ``stop()`` which run the worker.
        """
        with self._op_lock:
            self._rescan(now_utc)
            self._poll()

    def _rescan(self, now_utc: datetime.datetime) -> None:
        """Discover logs and reconcile tracked sources.

        Caller holds ``_op_lock``.  ``_lock`` acquired briefly for state.
        Subscribers called outside ``_lock`` but inside ``_op_lock``.
        """
        with self._lock:
            folder = self._folder
        if folder is None:
            return

        # -- Enumerate (I/O, outside _lock) ---
        try:
            entries = list(folder.glob("*.txt"))
        except OSError:
            logger.debug("Gamelogs folder unreadable: %s", folder)
            events = self._retire_all_sources(error=f"Folder unreadable: {folder}")
            with self._lock:
                subs = list(self._subscribers)
            for ev in events:
                _dispatch(ev, subs)
            return

        if not entries and not folder.exists():
            events = self._retire_all_sources(error=None)
            with self._lock:
                subs = list(self._subscribers)
            for ev in events:
                _dispatch(ev, subs)
            return

        # -- Build candidate list (I/O-heavy, outside _lock) ---
        cutoff = now_utc - MAX_AGE
        candidates = []
        scan_errors: list[str] = []
        # Paths seen this scan — committed to _known_paths AFTER selection
        # decisions so a new file in this scan is not misidentified as
        # previously known.  Uses absolute() (not resolve()) because a
        # broken symlink's resolve() differs from the real file.
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
            header = combatlog.parse_header(path)
            if header is None:
                # Unparseable header or character-less stub.  parse_header
                # returns None for both; the path is tombstoned via
                # paths_this_scan regardless.
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
        # recent session.  Slicing keeps the MAX_FILES most recently
        # active characters.
        best = dict(list(best.items())[:MAX_FILES])

        # -- Reconcile under _lock, collect events ---
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
                    continue  # Same file, no change

                # Retire the old source if being replaced
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
                        # Cannot determine EOF.  Do NOT fall back to zero
                        # and do NOT activate.  The path stays in
                        # _known_paths so the next scan that CAN stat it
                        # will baseline at EOF.
                        continue
                else:
                    # Genuinely new file, read from zero.
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

            # Health: clear only when zero errors.
            self._scan_errors = scan_errors
            if not scan_errors:
                self._last_successful_rescan_mono = self._clock()
                self._last_error = None

            subs = list(self._subscribers)

        # -- Dispatch outside _lock, inside _op_lock ---
        for ev in events:
            _dispatch(ev, subs)

    def _retire_all_sources(self, *, error: str | None) -> list[SourceLifecycle]:
        """Retire every tracked source (folder loss).

        Acquires ``_lock`` internally.  Returns events to dispatch.
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

        Caller holds ``_op_lock``.  Per-source errors are recorded without
        suppressing other sources.  Errors clear only after a fully
        successful complete poll.
        """
        with self._lock:
            snapshot = list(self._tracked.items())
            subs = list(self._subscribers)

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

        for ev in all_events:
            _dispatch(ev, subs)

    def _read_source(
        self, character: str, tracked: _Tracked
    ) -> tuple[list[SourceLifecycle | CombatFact], str | None]:
        """Read new data from one tracked file.

        On truncation (size < position), retire old generation and activate
        a new one.  Before emitting each fact, verify the tracked object is
        still current by looking it up in ``_tracked`` by character.
        """
        events: list[SourceLifecycle | CombatFact] = []
        try:
            size = tracked.path.stat().st_size
        except OSError as exc:
            return [], f"stat: {exc}"

        if size < tracked.position:
            # File shrank — treat as rotation.
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
            # Before emitting, verify the tracked object is still the
            # current one for this character.  A concurrent rescan (when
            # running under the real worker) could have retired this
            # source.  The _op_lock serializes scan_once iterations so
            # this cannot happen in the synchronous test path, but it is
            # the safety net for the threaded path.
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


# ------------------------------------------------------------------
# Module-level dispatch — never called under _lock.
# ------------------------------------------------------------------


def _dispatch(event: SourceLifecycle | CombatFact, subscribers: list[Callable]) -> None:
    """Deliver to every subscriber with callback isolation."""
    for callback in subscribers:
        try:
            callback(event)
        except Exception:
            logger.exception("Subscriber raised during dispatch")
