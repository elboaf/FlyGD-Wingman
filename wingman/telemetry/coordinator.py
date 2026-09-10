"""The one serialized telemetry coordinator.

Everything shared between Previews, Alerts and the fleet bar meets here:
``ClientDiscovery`` publishes rosters on its scan thread. ``GameLogStream``
publishes polled events on its worker and requested source restatements on
the requesting thread. This module turns those producer orders into ONE
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
discovery:    preview.enabled || fleet_bar.enabled || fleet_sharing.enabled
stream:       (fleet_bar.enabled || fleet_sharing.enabled
               || (preview.enabled && preview.alerts.enabled))
              && a Gamelogs folder that resolves to a real directory
alert policy: preview.enabled && preview.alerts.enabled
metrics:      fleet_bar.enabled || fleet_sharing.enabled
```

An enabled-but-inert Alerts preference therefore starts nothing while
Previews is off, and fleet-only mode starts discovery and the stream but
never attaches Alert policy or posts a roster to Preview. Fleet sharing
is the same shape again: it can start discovery/the stream and feed Fleet
Metrics (so a subscriber -- the sharing worker -- receives snapshots) with
neither the Fleet Bar window, Preview, nor Alerts ever attaching. Sharing
never changes what `snapshot()` reports to the Fleet Bar page itself --
that remains gated on `fleet_bar.enabled` alone, unaffected by sharing.

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

import dataclasses
import logging
import queue
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from ..alerts.custom import MAX_CUSTOM_RULES, AlertRuntimeSnapshot, rule_is_current
from .gamelogs import MAX_FILES
from .model import (
    CombatFact,
    CustomMatch,
    FleetSnapshot,
    RosterSnapshot,
    SourceLifecycle,
    StreamBatch,
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
    "incoming_scram": "warp_scramble",
    "incoming_point": "warp_scramble",
    "decloak": "decloak",
}

# Wakes a dispatcher blocked on an empty queue so stop() does not have to
# wait out a whole publication interval.
_WAKE = object()
_FLEET_REFRESH = object()
_ALERT_RESET = object()
_CUSTOM_DRAIN = object()
_CUSTOM_SOURCE_RESET = object()
CUSTOM_PENDING_MAX = MAX_FILES * MAX_CUSTOM_RULES


class _FleetMode(NamedTuple):
    """Internal queue control, ordered with producer payloads."""

    enabled: bool
    generation: int


class AlertEvent(NamedTuple):
    """Minimal event shape consumed by the thread-free AlertPolicy."""

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
        reconcile() -> int
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
        sharing_enabled: Callable[[], bool] = lambda: False,
        custom_snapshot: Callable[[], AlertRuntimeSnapshot] | None = None,
        _thread_factory: Callable[..., threading.Thread] = _real_thread_factory,
        _queue_factory: Callable[[], queue.Queue] = queue.Queue,
        _clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._preview_enabled = preview_enabled
        self._fleet_enabled = fleet_enabled
        self._alerts_enabled = alerts_enabled
        self._sharing_enabled = sharing_enabled
        self._gamelogs_folder = gamelogs_folder
        self._discovery = discovery
        self._stream = stream
        self._metrics = metrics
        self._preview_host = preview_host
        self._alert_policy = alert_policy
        self._thread_factory = _thread_factory
        self._clock = _clock

        self._queue: queue.Queue = _queue_factory()
        # Only custom pressure is bounded. Ingress seals a stream batch against
        # the dispatcher's final empty observation, never against consumption.
        self._ingress_lock = threading.Lock()
        self._custom_snapshot = custom_snapshot
        self._custom_pending: dict[tuple[str, str, int], CustomMatch] = {}
        self._custom_drain_queued = False
        self._stream_delivery_epoch = 0
        self._custom_alert_epoch = 0
        self._custom_admission_open = False
        self._custom_closed = False
        self._subscribers: list[Callable[[FleetSnapshot], None]] = []

        # Dispatcher-thread-only state.  Nothing else may touch these: the
        # sequence in particular is the one thing whose ordering guarantee
        # would be destroyed by a second writer.
        self._sequence = 0
        self._custom_sources: dict[str, SourceLifecycle] = {}
        self._custom_batch_epoch = (0, 0)
        self._sessions: dict[str, object] = {}
        self._fleet_active = False
        self._fleet_roster_generation: int | None = None
        # No current-generation publication is truthful until a complete
        # discovery roster has reached Fleet Metrics for this activation.
        self._fleet_has_complete_roster = False
        self._fleet_active_generation = 0

        self._lock = threading.Lock()
        self._latest: FleetSnapshot | None = None
        self._fleet_requested = False
        self._fleet_requested_generation = 0
        self._alerts_requested = False
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
        self._dispatcher_finalized_dead = False
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
        return (
            self._flag(self._preview_enabled)
            or self._flag(self._fleet_enabled)
            or self._flag(self._sharing_enabled)
        )

    def _wants_alert_policy(self) -> bool:
        return self._flag(self._preview_enabled) and self._flag(self._alerts_enabled)

    def _wants_stream_consumer(self) -> bool:
        """The consumer half of the stream predicate, folder aside.

        Separate from ``_resolved_folder`` so health can distinguish "no
        consumer needs the stream" from "a consumer needs it and the
        configured folder does not resolve", which the design requires be
        visibly different states.
        """
        return (
            self._flag(self._fleet_enabled)
            or self._flag(self._sharing_enabled)
            or self._wants_alert_policy()
        )

    def _wants_metrics(self) -> bool:
        """Whether Fleet Metrics must run at all -- the Fleet Bar window or
        fleet sharing, read live rather than passed a captured value, for
        the same reason ``_wants_alert_policy`` re-reads instead of taking
        a parameter: this is called from places (``_queue_stream_refreshes``
        via ``stop()``) that do not share ``reconcile()``'s local scope.
        """
        return self._flag(self._fleet_enabled) or self._flag(self._sharing_enabled)

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

    def reconcile(self) -> int:
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
            sharing_enabled = self._flag(self._sharing_enabled)
            want_discovery = preview_enabled or fleet_enabled or sharing_enabled
            want_stream = (
                fleet_enabled or sharing_enabled or (preview_enabled and alerts_enabled)
            )
            folder = self._resolved_folder() if want_stream else None
            # Fleet Metrics must run -- and publish to every fleet
            # subscriber, including a sharing worker -- whenever EITHER the
            # Fleet Bar window or fleet sharing wants a completed snapshot,
            # even with no Fleet Bar window open at all. It is computed once,
            # up front, so the dead-dispatcher restore below reserves the
            # same combined predicate the generation was minted for.
            want_metrics = fleet_enabled or sharing_enabled
            fleet_generation = self._request_fleet_mode(want_metrics)
            needs_dispatcher = want_discovery or folder is not None

            # Producers must never run without the sole consumer of their
            # queue. A retained timed-out dispatcher can refuse a restart;
            # leave producers stopped and retry next reconcile. Do not create
            # one just to observe the all-off Fleet generation reservation.
            if needs_dispatcher:
                self._dispatcher_finalized_dead = False
                started = self._start_dispatcher()
                if want_metrics and self._dispatcher_finalized_dead:
                    with self._lock:
                        needs_restore = not self._fleet_requested
                        if needs_restore:
                            self._fleet_requested = True
                    if needs_restore:
                        # A dead dispatcher can drain the queued activation while
                        # finalizing; restore the same generation so this reconcile
                        # still publishes the reservation it already handed out.
                        self._queue.put(_FleetMode(want_metrics, fleet_generation))
                if not started:
                    return fleet_generation

            self._reconcile_discovery(want_discovery)
            self._reconcile_stream(folder)
            self._request_alert_mode(preview_enabled and alerts_enabled)

            if not needs_dispatcher:
                # Nothing left to serialize. Stopping an existing dispatcher
                # here releases the last consumer without creating one on an
                # all-off startup solely to stop it again.
                self._stop_dispatcher()
            return fleet_generation

    @staticmethod
    def _completed(result) -> bool:
        """Treat legacy ``None`` lifecycle results as successful.

        The shared services now return booleans so timeout refusal is
        observable. Test doubles and transitional adapters that still
        return None preserve their former successful meaning.
        """
        return result is not False

    def _remaining_timeout(self, deadline: float) -> float:
        return max(0.0, deadline - self._clock())

    def _reconcile_discovery(self, wanted: bool, deadline: float | None = None) -> None:
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
            result = (
                self._discovery.stop()
                if deadline is None
                else self._discovery.stop(timeout=self._remaining_timeout(deadline))
            )
            if not self._completed(result):
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

    def _reconcile_stream(
        self, folder: Path | None, deadline: float | None = None
    ) -> None:
        with self._lock:
            current = self._stream_folder
            unsub = self._stream_unsub
        refresh_consumers = False

        # A missing subscription denotes a timed-out detached generation.
        # A folder move uses the same stop-before-start path.
        if current is not None and (folder != current or unsub is None):
            if unsub is not None:
                self._advance_custom_delivery(open_admission=False)
                unsub()
                with self._lock:
                    self._stream_unsub = None
            result = (
                self._stream.stop()
                if deadline is None
                else self._stream.stop(timeout=self._remaining_timeout(deadline))
            )
            if not self._completed(result):
                return
            with self._lock:
                self._stream_folder = None
            current = None
            refresh_consumers = True

        if folder is not None and current is None:
            epoch = self._advance_custom_delivery(open_admission=True)
            unsub = self._stream.subscribe_batches(
                lambda batch: self._on_stream_batch(batch, epoch)
            )
            if not self._completed(self._stream.start(folder)):
                self._advance_custom_delivery(open_admission=False)
                unsub()
                if refresh_consumers:
                    self._queue_stream_refreshes()
                return
            with self._lock:
                self._stream_folder = folder
                self._stream_unsub = unsub

        if refresh_consumers:
            self._queue_stream_refreshes()

    def _queue_stream_refreshes(self) -> None:
        """Order consumer resets behind the old stream generation."""
        if self._wants_metrics():
            self._queue.put(_FLEET_REFRESH)
        if self._wants_alert_policy():
            self._queue_alert_reset()

    def _request_fleet_mode(self, enabled: bool) -> int:
        """Order a Fleet consumer transition with producer payloads."""
        with self._lock:
            if enabled == self._fleet_requested:
                return self._fleet_requested_generation
            self._fleet_requested = enabled
            self._fleet_requested_generation += 1
            generation = self._fleet_requested_generation
        self._queue.put(_FleetMode(enabled, generation))
        return generation

    def requested_fleet_generation(self) -> int:
        with self._lock:
            return self._fleet_requested_generation

    def _request_alert_mode(self, enabled: bool) -> None:
        with self._lock:
            if enabled == self._alerts_requested:
                return
            self._alerts_requested = enabled
        self._queue_alert_reset()

    def _queue_alert_reset(self) -> None:
        with self._ingress_lock:
            self._custom_alert_epoch += 1
            self._custom_pending.clear()
            self._queue.put(_ALERT_RESET)

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

    def _on_stream_batch(self, batch: StreamBatch, delivery_epoch: int) -> None:
        """Admit semantic siblings atomically with their bounded custom work."""
        with self._ingress_lock:
            for event in batch.events:
                self._queue.put(event)
            # A detached callback still owns its semantic delivery. Only its
            # custom siblings are subject to this epoch and admission gate.
            if (
                not batch.custom_matches
                or not self._custom_admission_open
                or delivery_epoch != self._stream_delivery_epoch
            ):
                return
            snapshot = self._read_custom_snapshot()
            if snapshot is None:
                return
            # Prune before checking capacity: an edit must not leave old tokens
            # occupying every slot and refuse its own replacement generation.
            self._custom_pending = {
                key: match
                for key, match in self._custom_pending.items()
                if rule_is_current(
                    snapshot, match.rule_id, match.generation, match.activation_epoch
                )
            }
            for match in batch.custom_matches:
                if rule_is_current(
                    snapshot, match.rule_id, match.generation, match.activation_epoch
                ):
                    self._stage_custom(match)
            if self._custom_pending and not self._custom_drain_queued:
                self._custom_drain_queued = True
                self._queue.put(_CUSTOM_DRAIN)

    def _stage_custom(self, match: CustomMatch) -> bool:
        """Caller owns ingress; source lifecycles are checked only at delivery."""
        key = (match.character, match.rule_id, match.generation)
        if (
            key not in self._custom_pending
            and len(self._custom_pending) >= CUSTOM_PENDING_MAX
        ):
            return False
        self._custom_pending[key] = match
        return True

    def _read_custom_snapshot(self) -> AlertRuntimeSnapshot | None:
        if self._custom_snapshot is None:
            return None
        try:
            return self._custom_snapshot()
        except Exception:  # noqa: BLE001 — isolate custom failure without logging private text.
            logger.warning("Could not read custom alert authority.")
            return None

    def _advance_custom_delivery(self, *, open_admission: bool) -> int:
        with self._ingress_lock:
            if not open_admission and not self._custom_admission_open:
                # Repeated stops have already fenced this owner. In particular,
                # don't enqueue orphaned controls after its dispatcher exited.
                return self._stream_delivery_epoch
            self._stream_delivery_epoch += 1
            self._custom_admission_open = open_admission and not self._custom_closed
            self._custom_pending.clear()
            # Source authority remains dispatcher-owned and resets in semantic
            # order, even when the old worker cannot finish its bounded join.
            self._queue.put(_CUSTOM_SOURCE_RESET)
            return self._stream_delivery_epoch

    def close_custom_admission(self) -> None:
        """One-way final shutdown gate; no consumer calls or joins."""
        with self._ingress_lock:
            self._custom_closed = True
            self._custom_admission_open = False
            self._stream_delivery_epoch += 1
            self._custom_pending.clear()
            # Keep sentinel ownership until cutoff; it may still be queued.

    # ------------------------------------------------------------------
    # Dispatcher
    # ------------------------------------------------------------------

    def _start_dispatcher(self) -> bool:
        with self._lifecycle_lock:
            if self._running:
                return True
            if self._worker is not None:
                if self._worker.is_alive():
                    # A worker a previous stop() failed to join is still
                    # draining this queue; a second one would deliver the
                    # same batch twice.
                    return False
                # It died after the prior bounded join returned. Finalize
                # that generation before a replacement can consume its
                # queued payloads or publish its cached rows.
                self._dispatcher_finalized_dead = True
                self._finalize_dead_dispatcher()
            self._running = True
            self._stop_event = threading.Event()
            stop_ev = self._stop_event
            try:
                worker = self._thread_factory(
                    target=self._run,
                    args=(stop_ev,),
                    name="telemetry-dispatch",
                    daemon=False,
                )
                self._worker = worker
                worker.start()
            except Exception:
                logger.exception("Could not start telemetry dispatcher")
                self._running = False
                self._worker = None
                return False
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
                self._finalize_dead_dispatcher()

    def _finalize_dead_dispatcher(self) -> None:
        """Clear one confirmed-dead generation; caller owns lifecycle lock."""
        self._worker = None
        self._custom_sources.clear()
        self._sessions = {}
        self._fleet_active = False
        self._fleet_active_generation = 0
        self._fleet_roster_generation = None
        self._fleet_has_complete_roster = False
        self._metrics.reset()
        with self._lock:
            self._fleet_requested = False
            self._alerts_requested = False
            self._latest = None
        # Payloads nobody consumed describe the ended generation. Stamping
        # them after restart would present stale sessions as current.
        self._drain_queue()
        self._reset_alert_policy()

    def _drain_queue(self) -> None:
        with self._ingress_lock:
            self._custom_pending.clear()
            self._custom_drain_queued = False
            while True:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    return

    def _run(self, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            with self._dispatch_lock:
                self._dispatch_iteration(PUBLISH_INTERVAL_S, stop_event)

    def stop(self, timeout: float = 5.0) -> bool:
        """Detach consumers, stop workers, and report bounded completion.

        A timed-out producer remains authoritative by design. Shutdown gets
        one retry before the dispatcher is stopped, sharing one timeout budget
        across both attempts and the dispatcher join. If blocking external I/O
        still prevents exit, ``False`` and the error log make that state
        observable rather than pretending teardown completed.
        """
        deadline = self._clock() + max(0.0, timeout)
        with self._reconcile_lock:
            self._advance_custom_delivery(open_admission=False)
            services_stopped = False
            for _ in range(2):
                self._reconcile_discovery(False, deadline=deadline)
                self._reconcile_stream(None, deadline=deadline)
                with self._lock:
                    services_stopped = (
                        not self._discovery_started and self._stream_folder is None
                    )
                if services_stopped:
                    break
            self._stop_dispatcher(self._remaining_timeout(deadline))
            with self._lifecycle_lock:
                dispatcher_stopped = self._worker is None or not self._worker.is_alive()
            completed = services_stopped and dispatcher_stopped
            if not completed:
                logger.error("EVE telemetry workers did not stop cleanly")
            return completed

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
            stop_event = self._stop_event
        if worker_alive:
            raise RuntimeError("dispatch_once cannot run beside dispatcher worker")
        with self._dispatch_lock:
            self._dispatch_iteration(timeout, stop_event)

    def _dispatch_iteration(self, timeout: float, stop_event: threading.Event) -> None:
        """Consume one batch and publish; caller owns ``_dispatch_lock``.

        ``stop_event`` is the generation's own, handed in rather than read
        from ``self``: it is checked at every point where this iteration
        would otherwise hand work to a consumer. ``_run`` only tests it
        between iterations, and a stop that lands mid-batch used to be
        discarded here -- the ``_WAKE`` sentinel ``_stop_dispatcher`` puts
        on the queue was skipped by the coalescing loop like any other
        wake, so the whole batch still reached ``_dispatch_alerts`` and
        ``_publish``. A sound played and a preview ring lit AFTER
        ``stop()`` had returned, against previews already torn down.
        """
        try:
            item = self._queue.get(timeout=timeout)
        except queue.Empty:
            if not stop_event.is_set():
                self._publish()
            return
        if item is _WAKE or stop_event.is_set():
            return

        alerts: list[AlertEvent] = []
        self._process(item, alerts)
        # Coalesce whatever else is already waiting into this same batch:
        # one snapshot publication and one Alert policy call per batch,
        # rather than per event.  Alert policy reads the foreground client
        # once per call (a cross-thread read into the preview pump), which
        # is exactly the cost the Tailer's per-poll batching avoided.
        while True:
            with self._ingress_lock:
                try:
                    item = self._queue.get_nowait()
                except queue.Empty:
                    # Take custom work ONCE, not at each sentinel encountered
                    # during a prolonged semantic batch. The next producer
                    # owns a new mailbox and cannot split this sealed batch.
                    custom_matches = tuple(self._custom_pending.values())
                    self._custom_pending.clear()
                    self._custom_drain_queued = False
                    self._custom_batch_epoch = (
                        self._stream_delivery_epoch,
                        self._custom_alert_epoch,
                    )
                    break
            if stop_event.is_set():
                return
            if item is _WAKE:
                # A wake is only ever put by a reconcile or a stop; when it
                # is the stop's, everything behind it belongs to a
                # generation that is over. Payloads left on the queue are
                # drained by _finalize_dead_dispatcher.
                if stop_event.is_set():
                    return
                continue
            self._process(item, alerts)

        if stop_event.is_set():
            return
        self._dispatch_alerts(alerts, custom_matches)
        self._publish()

    def _process(self, payload, alerts: list[AlertEvent]) -> None:
        """Stamp one payload and fan it out.  Dispatcher thread only."""
        if isinstance(payload, _FleetMode):
            self._apply_fleet_mode(payload)
            return
        if payload is _FLEET_REFRESH:
            if self._fleet_active:
                self._reset_fleet_state(prime=True)
            return
        if payload is _ALERT_RESET:
            alerts.clear()
            self._reset_alert_policy()
            return
        if payload is _CUSTOM_DRAIN:
            return
        if payload is _CUSTOM_SOURCE_RESET:
            self._custom_sources.clear()
            return

        self._sequence += 1
        envelope = TelemetryEnvelope(sequence=self._sequence, payload=payload)

        if isinstance(payload, RosterSnapshot):
            self._apply_preview(payload)
            # Enabling Fleet primes discovery.snapshot() synchronously. The
            # callback for that same completed scan may already be queued;
            # consume one roster generation only once or every enable race
            # looks like a second session publication to Fleet Metrics.
            is_new_fleet_roster = (
                self._fleet_active
                and payload.generation != 0
                and (
                    self._fleet_roster_generation is None
                    or payload.generation > self._fleet_roster_generation
                )
            )
            if is_new_fleet_roster and self._consume_metrics(envelope):
                self._fleet_roster_generation = payload.generation
                self._fleet_has_complete_roster = True
                self._republish_sources(payload)
            return

        if isinstance(payload, SourceLifecycle) and self._custom_snapshot is not None:
            if payload.active and payload.available and payload.source_id is not None:
                self._custom_sources[payload.character] = payload
            else:
                self._custom_sources.pop(payload.character, None)

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

    def _reset_alert_policy(self) -> None:
        if self._alert_policy is None:
            return
        try:
            self._alert_policy.reset()
        except Exception:
            logger.exception("Alert policy raised while resetting cooldowns")

    def _apply_fleet_mode(self, mode: _FleetMode) -> None:
        """Reset Fleet state and prime a newly enabled current roster."""
        if mode.enabled == self._fleet_active:
            if mode.enabled:
                self._fleet_active_generation = mode.generation
            return
        self._fleet_active = mode.enabled
        self._fleet_active_generation = mode.generation if mode.enabled else 0
        self._reset_fleet_state(prime=mode.enabled)

    def _reset_fleet_state(self, *, prime: bool) -> None:
        """Clear old bindings; optionally seed from current discovery."""
        self._metrics.reset()
        self._sessions = {}
        self._fleet_roster_generation = None
        self._fleet_has_complete_roster = False
        with self._lock:
            self._latest = None
        if not prime:
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
            self._fleet_has_complete_roster = True
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

    def _dispatch_alerts(
        self, alerts: list[AlertEvent], custom_matches: tuple[CustomMatch, ...] = ()
    ) -> None:
        if not alerts and not custom_matches:
            return
        policy = self._alert_policy
        if policy is None or not self._wants_alert_policy():
            # Alerts are inert while Previews is off.  Checked at delivery,
            # not at subscription: the preference can change between two
            # reconciles, and the honest answer is the one that holds when
            # the event is actually dispatched.
            return
        if custom_matches:
            with self._ingress_lock:
                snapshot = self._read_custom_snapshot()
                if (
                    not self._custom_admission_open
                    or self._custom_batch_epoch
                    != (self._stream_delivery_epoch, self._custom_alert_epoch)
                    or snapshot is None
                ):
                    custom_matches = ()
                else:
                    custom_matches = tuple(
                        match
                        for match in custom_matches
                        if (source := self._custom_sources.get(match.character))
                        is not None
                        and source.generation == match.source_generation
                        and source.source_id == match.source_id
                        and rule_is_current(
                            snapshot,
                            match.rule_id,
                            match.generation,
                            match.activation_epoch,
                        )
                    )
        if not alerts and not custom_matches:
            return
        try:
            if custom_matches:
                policy.handle(alerts, self._clock(), custom_matches=custom_matches)
            else:
                # Built-in-only delivery preserves the legacy policy contract.
                policy.handle(alerts, self._clock())
        except Exception:
            logger.exception("Alert policy raised while handling telemetry facts")

    def _publish(self) -> None:
        """Build one complete fleet snapshot and deliver it when enabled.

        Fleet Metrics has already consumed this batch: the snapshot a
        subscriber sees is never behind the envelopes that produced it.
        """
        if not self._fleet_active or not self._fleet_has_complete_roster:
            return
        health = self._health()
        try:
            snapshot = dataclasses.replace(
                self._metrics.snapshot(self._sequence, health),
                activation_generation=self._fleet_active_generation,
            )
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
