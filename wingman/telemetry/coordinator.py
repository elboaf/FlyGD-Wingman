"""The one serialized telemetry coordinator.

Everything shared between Previews, Alerts and the fleet bar meets here:
``ClientDiscovery`` publishes rosters on its own scan thread,
``GameLogStream`` publishes source lifecycles and combat facts on its own
poll thread, and this module turns those two independent orders into ONE
stamped, totally-ordered stream that every consumer sees identically.

Why a queue and a thread of its own
------------------------------------
The callbacks this module hands to discovery and the stream do exactly one
thing: put the payload on a queue.  ``GameLogStream`` preserves total order
by delivering batches from whichever thread owns its drain, so a subscriber
that does real work there stalls the producer -- a poll that cannot finish
is a poll that cannot read the next lines, and the whole point of the
shared stream is that one consumer's slowness is not another's.  So the
callbacks enqueue and return, and all consumption -- Fleet Metrics, the
Preview roster hand-off, Alert policy, fleet subscribers -- happens on this
module's own dispatcher thread.

That thread is also the ONLY place a telemetry sequence is stamped.  A
sequence taken on a producer thread would order two producers by who won a
lock rather than by the order the coordinator actually consumed them, and
Fleet Metrics' whole roster/source join is defined against that consumption
order (``metrics.py``: a lifecycle binds only when its sequence follows the
session's first roster envelope).

Source republication
---------------------
When a roster snapshot introduces a client session this coordinator has not
seen before, it asks the stream to republish that character's current
source lifecycle -- including an "unavailable" one when no log exists.  The
stream publishes that synchronously on the caller's thread, which is this
dispatcher thread, so the republished lifecycle lands on the queue behind
the roster envelope that asked for it and is therefore stamped after it.
That is the entire mechanism by which the two independent generations
(roster and stream) acquire a defined order, without treating every 700ms
roster scan as a new session.

Runtime predicates (exact, per the design)
-------------------------------------------
```text
discovery:    preview.enabled || fleet_bar.enabled
stream:       (fleet_bar.enabled || (preview.enabled && preview.alerts.enabled))
              && a Gamelogs folder that resolves to a real directory
alert policy: preview.enabled && preview.alerts.enabled
```

An enabled-but-inert Alerts preference therefore starts nothing while
Previews is off, and fleet-only mode starts discovery and the stream but
never attaches Alert policy or posts a roster to Preview.

Settings arrive through CALLABLES, never captured dicts.
``settings._normalize`` reassigns ``data["preview"]`` wholesale on every
load and save, so a subtree captured at construction is orphaned after the
first write -- the same rule ``alerts/service.py`` documents, and the
reason every predicate here re-reads its callable at the moment it is
needed rather than caching a snapshot of the configuration.

Failure isolation
------------------
Every consumer is called inside its own guard: a raising Preview host, a
raising Alert policy, a raising Fleet Metrics and a raising fleet
subscriber each cost only their own delivery.  A consumer exception must
never unwind the dispatcher loop, because that loop is what keeps the
one-second decay cadence alive for everyone else.

Injected seams for testing
---------------------------
``_thread_factory``, ``_queue_factory`` and ``_clock``.  ``dispatch_once``
is the deterministic seam: call it with a zero timeout to drive one
iteration synchronously (a zero timeout is a genuinely non-blocking
``Queue.get``), mirroring ``ClientDiscovery.scan_once`` and
``GameLogStream.scan_once``.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from .model import (
    CombatFact,
    FleetSnapshot,
    RosterSnapshot,
    StreamHealth,
    TelemetryEnvelope,
)

logger = logging.getLogger(__name__)

# Fleet snapshots are published on every dispatched batch AND on every
# idle timeout, which is what makes a DPS window decay to zero with no new
# lines arriving.  One second is the design's stated cadence.
PUBLISH_INTERVAL_S = 1.0

# Fact kind -> the alert event name policy already knows.  The same mapping
# alerts/patterns.match_line applies to a parsed line; Alert policy is
# unchanged by this feature, so the shared stream's facts have to arrive
# wearing their existing names.  outgoing_damage is deliberately absent: it
# is a Fleet Metrics input only and has no alert.
_ALERT_EVENTS = {
    "incoming_damage": "combat",
    "incoming_miss": "combat",
    "incoming_tackle": "warp_scramble",
    "decloak": "decloak",
}

# Wakes a dispatcher blocked on an empty queue so stop() does not have to
# wait out a whole publication interval.
_WAKE = object()


class _FleetMode(NamedTuple):
    """Internal queue control, ordered with producer payloads."""

    enabled: bool


class AlertEvent(NamedTuple):
    """What AlertPolicy.handle() reads off each event.

    Structurally identical to ``alerts.tailer.Event`` and deliberately not
    imported from it: the Tailer is the module this feature replaces, and
    nothing new should acquire a dependency on it.
    """

    character: str
    event: str
    source: str


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


_EMPTY_ROWS: tuple = ()


class TelemetryCoordinator:
    """Shared telemetry ownership: predicates, sequence, dispatch, cadence.

    Public interface:
        reconcile()
        request_discovery()
        snapshot() -> FleetSnapshot
        subscribe_fleet(callback) -> unsubscribe callable
        stop(timeout=5.0)
        dispatch_once(timeout=PUBLISH_INTERVAL_S)  -- deterministic seam
    """

    def __init__(
        self,
        *,
        preview_enabled: Callable[[], bool],
        fleet_enabled: Callable[[], bool],
        alerts_enabled: Callable[[], bool],
        gamelogs_folder: Callable[[], Path | str | None],
        discovery,
        stream,
        metrics,
        preview_host=None,
        alert_policy=None,
        _thread_factory: Callable[..., threading.Thread] = _real_thread_factory,
        _queue_factory: Callable[[], queue.Queue] = queue.Queue,
        _clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._preview_enabled = preview_enabled
        self._fleet_enabled = fleet_enabled
        self._alerts_enabled = alerts_enabled
        self._gamelogs_folder = gamelogs_folder
        self._discovery = discovery
        self._stream = stream
        self._metrics = metrics
        self._preview_host = preview_host
        self._alert_policy = alert_policy
        self._thread_factory = _thread_factory
        self._clock = _clock

        self._queue: queue.Queue = _queue_factory()
        self._subscribers: list[Callable[[FleetSnapshot], None]] = []

        # Dispatcher-thread-only state.  Nothing else may touch these: the
        # sequence in particular is the one thing whose ordering guarantee
        # would be destroyed by a second writer.
        self._sequence = 0
        self._sessions: dict[str, object] = {}
        self._fleet_active = False
        self._fleet_roster_generation: int | None = None

        self._lock = threading.Lock()
        self._latest: FleetSnapshot | None = None
        self._fleet_requested = False
        self._discovery_started = False
        self._discovery_unsub: Callable[[], None] | None = None
        self._stream_folder: Path | None = None
        self._stream_unsub: Callable[[], None] | None = None

        # Serialises whole reconcile()/stop() passes against each other.
        # Without it, a tray-thread stop() and a UI-thread reconcile() can
        # interleave their start and stop halves and leave a service
        # running with nobody subscribed to it.  Never held while the
        # dispatcher is consuming, so a consumer cannot deadlock on it.
        self._reconcile_lock = threading.Lock()

        self._lifecycle_lock = threading.Lock()
        # Serializes the complete dequeue -> sequence -> consumer -> publish
        # iteration. The real worker is the ordinary owner; dispatch_once()
        # uses the same lock only when no worker is alive, for deterministic
        # tests. Without one lock, two manual callers could stamp and deliver
        # envelopes in a different order from Queue.get().
        self._dispatch_lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._running = False
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Settings predicates
    # ------------------------------------------------------------------

    def _flag(self, read: Callable[[], bool]) -> bool:
        """One settings callable's answer, or False if it could not answer.

        Guarded because these run on the dispatcher thread as well as the
        caller's: a settings read that raises mid-shutdown would otherwise
        take the dispatcher down with it, and "off" is the safe reading of
        a preference nobody can produce.
        """
        try:
            return bool(read())
        except Exception:
            logger.exception("Could not read a telemetry runtime preference")
            return False

    def _wants_discovery(self) -> bool:
        return self._flag(self._preview_enabled) or self._flag(self._fleet_enabled)

    def _wants_alert_policy(self) -> bool:
        return self._flag(self._preview_enabled) and self._flag(self._alerts_enabled)

    def _wants_stream_consumer(self) -> bool:
        """The consumer half of the stream predicate, folder aside.

        Separate from ``_resolved_folder`` so health can distinguish "no
        consumer needs the stream" from "a consumer needs it and the
        configured folder does not resolve", which the design requires be
        visibly different states.
        """
        return self._flag(self._fleet_enabled) or self._wants_alert_policy()

    def _resolved_folder(self) -> Path | None:
        """The configured Gamelogs folder, or None if it does not resolve.

        ``is_dir()`` every time, not once at construction: a folder that
        was valid and stopped being one (an unmounted drive, an unlinked
        OneDrive folder, a settings.json carried from another machine)
        must stop the stream rather than keep it looking healthy -- glob on
        a missing directory yields nothing and raises nothing.
        """
        try:
            configured = self._gamelogs_folder()
        except Exception:
            logger.exception("Could not read the configured Gamelogs folder")
            return None
        if not configured:
            return None
        path = Path(configured)
        try:
            return path if path.is_dir() else None
        except OSError:
            logger.debug("Gamelogs folder unreachable: %s", path, exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Reconciliation
    # ------------------------------------------------------------------

    def reconcile(self) -> None:
        """Start or stop shared infrastructure to match the predicates.

        Idempotent: a service already in its wanted state is left alone, so
        the first consumer starts it exactly once and the last one stops it
        exactly once, however often this is called in between.
        """
        with self._reconcile_lock:
            # Read every live setting inside the same pass lock as the state
            # changes it decides. Reading before the lock lets stop() finish
            # between those two phases, after which this pass could restart
            # services from a stale pre-stop preference snapshot.
            preview_enabled = self._flag(self._preview_enabled)
            fleet_enabled = self._flag(self._fleet_enabled)
            alerts_enabled = self._flag(self._alerts_enabled)
            want_discovery = preview_enabled or fleet_enabled
            want_stream = fleet_enabled or (preview_enabled and alerts_enabled)
            folder = self._resolved_folder() if want_stream else None

            # Producers must never run without the sole consumer of their
            # queue. A retained timed-out dispatcher can refuse a restart;
            # leave producers stopped and retry next reconcile.
            if (want_discovery or folder is not None) and not self._start_dispatcher():
                return

            self._reconcile_discovery(want_discovery)
            self._reconcile_stream(folder)
            self._request_fleet_mode(fleet_enabled)

            if not want_discovery and folder is None:
                # Nothing left to serialize.  Stopping the dispatcher here
                # is what makes "the last consumer detaching" release the
                # thread too, rather than leaving one publishing empty
                # snapshots at one hertz for the rest of the session.
                self._stop_dispatcher()

    @staticmethod
    def _completed(result) -> bool:
        """Treat legacy ``None`` lifecycle results as successful.

        The shared services now return booleans so timeout refusal is
        observable. Test doubles and transitional adapters that still
        return None preserve their former successful meaning.
        """
        return result is not False

    def _reconcile_discovery(self, wanted: bool) -> None:
        with self._lock:
            started = self._discovery_started
            unsub = self._discovery_unsub

        # ``started`` with no subscription means the previous stop timed
        # out: its worker remains authoritative but detached. Retry that
        # stop before either accepting off or starting a fresh generation.
        if started and (not wanted or unsub is None):
            if unsub is not None:
                unsub()
                with self._lock:
                    self._discovery_unsub = None
            if not self._completed(self._discovery.stop()):
                return
            with self._lock:
                self._discovery_started = False
            started = False

        if wanted and not started:
            # Subscribe BEFORE start: the first scan is immediate. Publish
            # the marker only after start accepts this generation.
            unsub = self._discovery.subscribe(self._on_roster)
            if not self._completed(self._discovery.start()):
                unsub()
                return
            with self._lock:
                self._discovery_started = True
                self._discovery_unsub = unsub

    def _reconcile_stream(self, folder: Path | None) -> None:
        with self._lock:
            current = self._stream_folder
            unsub = self._stream_unsub

        # A missing subscription denotes a timed-out detached generation.
        # A folder move uses the same stop-before-start path.
        if current is not None and (folder != current or unsub is None):
            if unsub is not None:
                unsub()
                with self._lock:
                    self._stream_unsub = None
            if not self._completed(self._stream.stop()):
                return
            with self._lock:
                self._stream_folder = None
            current = None

        if folder is not None and current is None:
            unsub = self._stream.subscribe(self._on_stream_event)
            if not self._completed(self._stream.start(folder)):
                unsub()
                return
            with self._lock:
                self._stream_folder = folder
                self._stream_unsub = unsub

    def _request_fleet_mode(self, enabled: bool) -> None:
        """Order a Fleet consumer transition with producer payloads."""
        with self._lock:
            if enabled == self._fleet_requested:
                return
            self._fleet_requested = enabled
        self._queue.put(_FleetMode(enabled))

    def request_discovery(self) -> None:
        """Ask for an immediate roster scan.  Safe from any thread.

        A no-op while discovery is not running: the Preview foreground hook
        calls this, and previews being off is exactly when there is nothing
        to scan for.
        """
        with self._lock:
            started = self._discovery_started
        if started:
            self._discovery.request_scan()

    # ------------------------------------------------------------------
    # Subscription and snapshots
    # ------------------------------------------------------------------

    def subscribe_fleet(
        self, callback: Callable[[FleetSnapshot], None]
    ) -> Callable[[], None]:
        """Register a fleet-snapshot callback; returns an unsubscribe.

        Delivered on the dispatcher thread, one complete immutable snapshot
        at a time.
        """
        with self._lock:
            self._subscribers.append(callback)

        def _unsub() -> None:
            with self._lock:
                if callback in self._subscribers:
                    self._subscribers.remove(callback)

        return _unsub

    def stream_health(self) -> StreamHealth:
        """Current shared reader health for the existing Alerts card."""
        return self._health()

    def stream_characters(self) -> tuple[str, ...]:
        """Characters with active log sources, or none if unavailable."""
        try:
            return self._stream.characters()
        except Exception:
            logger.exception("Could not read gamelog stream characters")
            return ()

    def snapshot(self) -> FleetSnapshot:
        """The most recently published snapshot, or an empty one.

        Deliberately NOT a fresh ``metrics.snapshot()`` call: Fleet Metrics
        is thread-free by design and only the dispatcher thread may touch
        it, so answering a page's readiness request by computing here would
        race the dispatcher through that module's mutable state.  The last
        published value is at most one publication interval old.
        """
        if not self._flag(self._fleet_enabled):
            return FleetSnapshot(
                rows=_EMPTY_ROWS, stream_health=StreamHealth(state="disabled")
            )
        with self._lock:
            latest = self._latest
        if latest is not None:
            return latest
        return FleetSnapshot(rows=_EMPTY_ROWS, stream_health=self._health())

    def _health(self) -> StreamHealth:
        """Stream health as the fleet page needs to distinguish it."""
        with self._lock:
            folder = self._stream_folder
        if folder is not None:
            try:
                return self._stream.health()
            except Exception:
                logger.exception("Could not read gamelog stream health")
                return StreamHealth(state="error", detail="health unavailable")
        if not self._wants_stream_consumer():
            return StreamHealth(state="disabled")
        try:
            configured = self._gamelogs_folder()
        except Exception:
            logger.exception("Could not read the configured Gamelogs folder")
            configured = None
        return StreamHealth(
            state="missing_folder",
            detail=str(configured) if configured else None,
        )

    # ------------------------------------------------------------------
    # Producer callbacks -- ENQUEUE ONLY
    # ------------------------------------------------------------------

    def _on_roster(self, snapshot: RosterSnapshot) -> None:
        """Discovery's scan thread.  Must not do work; see module docstring."""
        self._queue.put(snapshot)

    def _on_stream_event(self, event) -> None:
        """The stream's poll thread.  Must not do work; see module docstring."""
        self._queue.put(event)

    # ------------------------------------------------------------------
    # Dispatcher
    # ------------------------------------------------------------------

    def _start_dispatcher(self) -> bool:
        with self._lifecycle_lock:
            if self._running:
                return True
            if self._worker is not None and self._worker.is_alive():
                # A worker a previous stop() failed to join is still
                # draining this queue; a second one would deliver the same
                # batch twice.  Same refusal ClientDiscovery.start makes.
                return False
            self._running = True
            self._stop_event = threading.Event()
            stop_ev = self._stop_event
            worker = self._thread_factory(
                target=self._run,
                args=(stop_ev,),
                name="telemetry-dispatch",
                daemon=False,
            )
            self._worker = worker
            worker.start()
            return True

    def _stop_dispatcher(self, timeout: float = 5.0) -> None:
        with self._lifecycle_lock:
            worker = self._worker
            stop_ev = self._stop_event
            self._running = False
        if worker is None:
            return
        stop_ev.set()
        # The dispatcher spends most of its life blocked on an empty queue;
        # the sentinel is what makes stop() prompt instead of costing a
        # whole publication interval.
        self._queue.put(_WAKE)
        worker.join(timeout)
        with self._lifecycle_lock:
            # Retained on timeout so a later stop() can retry the join and
            # _start_dispatcher can refuse to run two dispatchers at once.
            if not worker.is_alive():
                self._worker = None
                # Dispatcher-thread-only state, safe to touch exactly here:
                # the thread that owned it is confirmed dead.  Cleared so a
                # later restart re-asks the stream about every session it
                # sees rather than trusting a map built before the gap.
                self._sessions = {}
                self._fleet_active = False
                self._fleet_roster_generation = None
                self._metrics.reset()
                with self._lock:
                    self._fleet_requested = False
                    self._latest = None
                # And whatever the producers queued but nobody consumed:
                # those payloads describe the session that just ended, and
                # stamping them with fresh sequences after a restart would
                # present them to Fleet Metrics as current.
                self._drain_queue()

    def _drain_queue(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return

    def _run(self, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            with self._dispatch_lock:
                self._dispatch_iteration(PUBLISH_INTERVAL_S)

    def stop(self, timeout: float = 5.0) -> None:
        """Detach every consumer and stop shared infrastructure.

        Idempotent, and ordered: consumers detach before the workers they
        feed are joined, so no producer thread is still delivering into a
        dispatcher that is being shut down.
        """
        with self._reconcile_lock:
            self._reconcile_discovery(False)
            self._reconcile_stream(None)
            self._stop_dispatcher(timeout)

    def dispatch_once(self, timeout: float = PUBLISH_INTERVAL_S) -> None:
        """Drive one iteration synchronously when no worker is alive.

        This is a deterministic test seam, not a second dispatcher. A live
        worker owns the queue and sequence; allowing an external caller to
        consume beside it would make dequeue order and delivery order race.
        Concurrent manual callers are serialized by the same lock the real
        worker uses.
        """
        with self._lifecycle_lock:
            worker_alive = self._worker is not None and self._worker.is_alive()
        if worker_alive:
            raise RuntimeError("dispatch_once cannot run beside dispatcher worker")
        with self._dispatch_lock:
            self._dispatch_iteration(timeout)

    def _dispatch_iteration(self, timeout: float) -> None:
        """Consume one batch and publish; caller owns ``_dispatch_lock``."""
        try:
            item = self._queue.get(timeout=timeout)
        except queue.Empty:
            self._publish()
            return
        if item is _WAKE:
            return

        alerts: list[AlertEvent] = []
        self._process(item, alerts)
        # Coalesce whatever else is already waiting into this same batch:
        # one snapshot publication and one Alert policy call per batch,
        # rather than per event.  Alert policy reads the foreground client
        # once per call (a cross-thread read into the preview pump), which
        # is exactly the cost the Tailer's per-poll batching avoided.
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item is _WAKE:
                continue
            self._process(item, alerts)

        self._dispatch_alerts(alerts)
        self._publish()

    def _process(self, payload, alerts: list[AlertEvent]) -> None:
        """Stamp one payload and fan it out.  Dispatcher thread only."""
        if isinstance(payload, _FleetMode):
            self._apply_fleet_mode(payload.enabled)
            return

        self._sequence += 1
        envelope = TelemetryEnvelope(sequence=self._sequence, payload=payload)

        if isinstance(payload, RosterSnapshot):
            self._apply_preview(payload)
            # Enabling Fleet primes discovery.snapshot() synchronously. The
            # callback for that same completed scan may already be queued;
            # consume one roster generation only once or every enable race
            # looks like a second session publication to Fleet Metrics.
            is_new_fleet_roster = self._fleet_active and (
                self._fleet_roster_generation is None
                or payload.generation > self._fleet_roster_generation
            )
            if is_new_fleet_roster and self._consume_metrics(envelope):
                self._fleet_roster_generation = payload.generation
                self._republish_sources(payload)
            return

        if self._fleet_active:
            self._consume_metrics(envelope)

        if isinstance(payload, CombatFact):
            name = _ALERT_EVENTS.get(payload.kind)
            if name is not None:
                alerts.append(
                    AlertEvent(
                        character=payload.character,
                        event=name,
                        source=payload.source,
                    )
                )

    def _consume_metrics(self, envelope: TelemetryEnvelope) -> bool:
        try:
            self._metrics.consume(envelope)
            return True
        except Exception:
            # Fleet Metrics is pure, so this should not happen -- and if it
            # does, cadence, Preview and Alerts must survive it.
            logger.exception("Fleet Metrics raised while consuming telemetry")
            return False

    def _apply_fleet_mode(self, enabled: bool) -> None:
        """Reset Fleet state and prime a newly enabled current roster."""
        if enabled == self._fleet_active:
            return
        self._fleet_active = enabled
        self._metrics.reset()
        self._sessions = {}
        self._fleet_roster_generation = None
        with self._lock:
            self._latest = None
        if not enabled:
            return
        try:
            snapshot = self._discovery.snapshot()
        except Exception:
            logger.exception("Could not read current roster while enabling Fleet")
            return
        if snapshot.generation == 0:
            return  # Discovery has not completed its first scan yet.
        self._sequence += 1
        envelope = TelemetryEnvelope(sequence=self._sequence, payload=snapshot)
        if self._consume_metrics(envelope):
            self._fleet_roster_generation = snapshot.generation
            self._republish_sources(snapshot)

    def _apply_preview(self, snapshot: RosterSnapshot) -> None:
        if self._preview_host is None or not self._flag(self._preview_enabled):
            return
        try:
            self._preview_host.apply_roster(snapshot)
        except Exception:
            logger.exception("Preview host raised while applying a roster")

    def _republish_sources(self, snapshot: RosterSnapshot) -> None:
        """Ask the stream to restate the source of every NEW session.

        Only while the stream is running: with no stream there is nothing
        to answer, and Fleet Metrics would keep the row at ``NO LOG``
        anyway.  Called on the dispatcher thread, so the stream's
        synchronous republication lands on this queue behind the roster
        envelope that triggered it -- the ordering the whole join depends
        on.
        """
        with self._lock:
            running = self._stream_folder is not None
        current: dict[str, object] = {}
        new: list[str] = []
        for client in snapshot.clients:
            if client.character is None or client.session is None:
                # A generic character-selection title: real enough for
                # Preview, but it carries no session to join a log to.
                continue
            current[client.character] = client.session
            if self._sessions.get(client.character) != client.session:
                new.append(client.character)
        # Replaced wholesale: a character absent from this snapshot is
        # gone, and its return must count as a new session even if the
        # identity happens to match.
        self._sessions = current
        if not running:
            return
        for character in new:
            try:
                self._stream.request_source(character)
            except Exception:
                logger.exception("Could not request the log source for %s", character)

    def _dispatch_alerts(self, alerts: list[AlertEvent]) -> None:
        if not alerts:
            return
        policy = self._alert_policy
        if policy is None or not self._wants_alert_policy():
            # Alerts are inert while Previews is off.  Checked at delivery,
            # not at subscription: the preference can change between two
            # reconciles, and the honest answer is the one that holds when
            # the event is actually dispatched.
            return
        try:
            policy.handle(alerts, self._clock())
        except Exception:
            logger.exception("Alert policy raised while handling telemetry facts")

    def _publish(self) -> None:
        """Build one complete fleet snapshot and deliver it when enabled.

        Fleet Metrics has already consumed this batch: the snapshot a
        subscriber sees is never behind the envelopes that produced it.
        """
        if not self._fleet_active:
            return
        health = self._health()
        try:
            snapshot = self._metrics.snapshot(self._sequence, health)
        except Exception:
            logger.exception("Fleet Metrics raised while building a snapshot")
            return

        with self._lock:
            self._latest = snapshot
            subs = list(self._subscribers)

        for callback in subs:
            try:
                callback(snapshot)
            except Exception:
                logger.exception("Subscriber raised during fleet snapshot dispatch")


__all__ = [
    "PUBLISH_INTERVAL_S",
    "AlertEvent",
    "TelemetryCoordinator",
]
