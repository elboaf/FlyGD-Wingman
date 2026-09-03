"""Shared EVE client discovery with stable per-session identity.

Owns nothing about *what* a window is -- ``preview.discovery`` remains the
sole raw Win32 enumerator, unchanged, so window-acceptance and identity
rules (title prefix, process image name, stable key) stay defined in
exactly one place.  This service consumes that module's failure-aware
``enumerate_clients()`` seam (see "Failure isolation" below), not its
plain-list ``list_clients()`` compatibility adapter.  This module adds the
thing multiple features need on top of that raw enumeration: one shared
scan cadence, fan-out to independent subscribers, and a *session* identity
that survives an ordinary unchanged scan but renews on disappearance,
HWND/PID change, or a generic-title transition.

Session identity
-----------------
A client is identified for session purposes by ``(hwnd, pid, character)``.
``first_seen_generation`` is the roster generation in which that tuple was
first observed and stays stable across every subsequent scan in which it
remains continuously present.  It is pruned the instant the tuple is
missing from a scan -- there is no grace window -- so a later reappearance
(the same character logging back in, a relaunch that reused HWND/PID, or a
generic character-selection title reverting to the same name) is treated as
a new session with a fresh ``first_seen_generation``.  A client whose
current title is not character-derived (``character is None``) is never
added to the session map: it still appears in the roster snapshot (Preview
identity and reconciliation need every window, named or not) but carries
``session is None``.

Failure isolation
------------------
``enumerate_clients()`` distinguishes a genuinely empty scan
(``success=True, clients=[]``) from a failed one (``success=False``): a
plain empty list cannot carry that distinction, and this service's
stable-session pruning must never treat "the enumerator raised" as
authoritative proof that every client vanished.  A failed scan therefore
records the error, publishes nothing, and leaves every tracked session key
and the last published snapshot untouched.  The next scan that genuinely
succeeds -- even an empty one -- resumes normal reconciliation and pruning.

This module deliberately never reads preview exclusion or any other
setting.  "Excluded from preview thumbnails" is a Preview-only concept
applied downstream; the shared roster is raw truth for every consumer.

Concurrency model
------------------
One owned worker context performs every scan; ``scan_once()`` is the
synchronous test seam used with ``_noop_thread_factory``, mirroring
``telemetry.gamelogs.GameLogStream``.  ``_scan_lock`` (non-reentrant)
serializes ``scan_once()`` itself, so a manual/test call and the worker's
own call can never run the enumerator concurrently -- one waits for the
other's whole cycle (enumerate, reconcile, and the state mutation) to
finish before starting its own.  ``_lock`` guards the session map,
generation counter, and latest snapshot; subscriber callbacks are always
invoked outside both locks, and one raising callback does not stop
delivery to the others.  ``_lifecycle_lock`` makes ``start``/``stop``
atomic, following the same idempotent, bounded-join, timeout-retains-worker
shape as ``GameLogStream``.

Injected seams for testing
---------------------------
``_thread_factory``, ``_wait_fn``, and ``_enumerate_clients``. The latter
defaults to ``preview.discovery.enumerate_clients`` and may return either
an ``EnumerationResult`` (honoring its ``success``/``clients`` split) or a
plain ``Client`` iterable -- the shape the task brief originally specified
-- which ``_normalize_scan_result`` treats as an always-successful scan,
including an authoritative empty one. Only ``EnumerationResult`` can
report ``success=False``; a bare list/iterable has no way to express
failure and is never pruning-suppressed.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable

from ..preview import discovery
from .model import ClientSessionId, RosterClient, RosterSnapshot

logger = logging.getLogger(__name__)

# Matches preview.host.SWEEP_MS: the shared service must not scan slower
# than Preview's existing cadence, since Preview becomes a consumer of it
# rather than reconciling windows itself.
SCAN_INTERVAL_S = 0.7

_SessionKey = tuple[int, int, str]

# The two shapes an injected `_enumerate_clients` collaborator may return:
# the failure-aware production seam, or a plain Client iterable (the task
# brief's original `Callable[[], list[Client]]` contract, still accepted
# for any existing list-returning fake).
ScanResult = discovery.EnumerationResult | Iterable[discovery.Client]


def _normalize_scan_result(result: ScanResult) -> tuple[bool, list]:
    """Narrow either accepted ``_enumerate_clients`` return shape to a
    plain ``(success, clients)`` pair.

    An explicit ``isinstance`` check, not exception-based duck typing:
    ``EnumerationResult`` alone can report failure; every other iterable
    (list, tuple, generator of ``Client``) has no way to express "the scan
    failed" and is therefore always a successful scan -- including a
    genuinely empty one, which stays authoritative for pruning exactly as
    it did for the production seam.
    """
    if isinstance(result, discovery.EnumerationResult):
        return result.success, list(result.clients) if result.success else []
    return True, list(result)


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


_EMPTY_SNAPSHOT = RosterSnapshot(generation=0, clients=())


class ClientDiscovery:
    """Shared client discovery.

    Public interface:
        subscribe(callback) -> unsubscribe callable
        start()
        request_scan()
        stop(timeout=5.0)
        snapshot() -> RosterSnapshot

    Inject ``_thread_factory=_noop_thread_factory`` and drive ``scan_once()``
    directly for deterministic tests.
    """

    def __init__(
        self,
        *,
        _thread_factory: Callable[..., threading.Thread] = _real_thread_factory,
        _wait_fn: Callable[[threading.Event, float], None] | None = None,
        _enumerate_clients: Callable[[], ScanResult] = discovery.enumerate_clients,
    ) -> None:
        self._thread_factory = _thread_factory
        self._wait_fn = _wait_fn or (lambda ev, t: ev.wait(t))
        self._enumerate_clients = _enumerate_clients

        self._subscribers: list[Callable[[RosterSnapshot], None]] = []
        # (hwnd, pid, character) -> the generation it was first seen in.
        # Pruned the instant a tuple is absent from a scan that genuinely
        # succeeded. A failed scan touches neither this map nor _latest.
        self._sessions: dict[_SessionKey, int] = {}
        self._next_generation = 1
        self._latest = _EMPTY_SNAPSHOT
        # Set on a failed scan, cleared on the next successful one. Private
        # state, not a health surface -- this task does not add one.
        self._last_error: str | None = None

        self._lock = threading.Lock()
        # Serializes scan_once() end to end (enumerate + reconcile), so a
        # manual/test caller and the worker thread can never run the
        # enumerator concurrently.
        self._scan_lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._started = False

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    def subscribe(
        self, callback: Callable[[RosterSnapshot], None]
    ) -> Callable[[], None]:
        """Register a callback; returns an unsubscribe callable."""
        with self._lock:
            self._subscribers.append(callback)

        def _unsub() -> None:
            with self._lock:
                if callback in self._subscribers:
                    self._subscribers.remove(callback)

        return _unsub

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Begin scanning.  Spawns a worker via the thread factory.

        Idempotent.  Refuses to launch while a timed-out worker is alive,
        the same guarantee ``GameLogStream.start`` makes.
        """
        with self._lifecycle_lock:
            with self._lock:
                if self._started:
                    return
                if self._worker is not None and self._worker.is_alive():
                    return
                self._started = True
                self._stop_event = threading.Event()
                self._wake_event = threading.Event()
                stop_ev = self._stop_event
                wake_ev = self._wake_event
            worker = self._thread_factory(
                target=self._run,
                args=(stop_ev, wake_ev),
                name="client-discovery",
                daemon=False,
            )
            with self._lock:
                self._worker = worker
            worker.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the worker and join with a bounded timeout.  Idempotent.

        On timeout the worker is retained and ``_started`` stays False so a
        later ``stop`` can retry joining, matching ``GameLogStream.stop``.
        """
        with self._lifecycle_lock:
            with self._lock:
                worker = self._worker
                stop_ev = self._stop_event
                wake_ev = self._wake_event
                self._started = False
            if worker is not None:
                stop_ev.set()
                wake_ev.set()  # unblock a pending wait immediately
                worker.join(timeout)
                with self._lock:
                    if not worker.is_alive():
                        self._worker = None

    def request_scan(self) -> None:
        """Wake the owned context for an immediate scan.

        Used by the Preview foreground hook so a just-activated window is
        reconciled without waiting out the ordinary cadence.  A no-op with
        respect to state if the worker is not currently waiting -- it will
        simply scan on its next iteration instead of blocking further.
        """
        with self._lock:
            wake_ev = self._wake_event
        wake_ev.set()

    def snapshot(self) -> RosterSnapshot:
        """The most recently published snapshot, or an empty generation-0
        snapshot if no scan has completed yet."""
        with self._lock:
            return self._latest

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    def _run(self, stop_event: threading.Event, wake_event: threading.Event) -> None:
        """Worker loop: immediate scan, then wait for the ordinary cadence
        or an early wake from ``request_scan()``."""
        while not stop_event.is_set():
            self.scan_once()
            if stop_event.is_set():
                return
            self._wait_fn(wake_event, SCAN_INTERVAL_S)
            wake_event.clear()

    # ------------------------------------------------------------------
    # Core: synchronous scan (deterministic test seam)
    # ------------------------------------------------------------------

    def scan_once(self) -> None:
        """One complete enumerate + reconcile + publish cycle, synchronous
        on the caller's thread.

        Serialized end to end by ``_scan_lock``: a concurrent caller (the
        worker thread or another manual/test call) waits for this whole
        cycle to finish rather than running its own enumerator call at the
        same time.

        A failed enumeration (``EnumerationResult(success=False, ...)`` or
        the callable raising directly) records the error and returns
        without touching session state or the latest snapshot, and without
        publishing anything -- an enumerator failure must never be read as
        proof that every client disappeared. A plain ``Client`` iterable
        (no ``EnumerationResult``) is always a successful scan, per
        ``_normalize_scan_result``.
        """
        with self._scan_lock:
            try:
                success, clients = _normalize_scan_result(self._enumerate_clients())
            except Exception:
                logger.exception("Could not enumerate EVE clients")
                success = False
                clients = []

            if not success:
                with self._lock:
                    self._last_error = "client enumeration failed"
                return

            with self._lock:
                self._last_error = None
                generation = self._next_generation
                self._next_generation += 1

                current_keys: set[_SessionKey] = set()
                roster_clients = []
                for client in clients:
                    session = None
                    if client.character is not None:
                        key = (client.hwnd, client.pid, client.character)
                        current_keys.add(key)
                        first_seen = self._sessions.get(key, generation)
                        self._sessions[key] = first_seen
                        session = ClientSessionId(
                            hwnd=client.hwnd,
                            pid=client.pid,
                            character=client.character,
                            first_seen_generation=first_seen,
                        )
                    roster_clients.append(
                        RosterClient(
                            hwnd=client.hwnd,
                            pid=client.pid,
                            title=client.title,
                            character=client.character,
                            session=session,
                        )
                    )

                # Prune tuples no longer present: a later reappearance must
                # be treated as a new session, never as continuity. Only
                # reached on a successful scan -- a failed one returned
                # above and left this map alone.
                for key in list(self._sessions):
                    if key not in current_keys:
                        del self._sessions[key]

                snapshot = RosterSnapshot(
                    generation=generation, clients=tuple(roster_clients)
                )
                self._latest = snapshot
                subs = list(self._subscribers)

        for callback in subs:
            try:
                callback(snapshot)
            except Exception:
                logger.exception("Subscriber raised during client discovery dispatch")
