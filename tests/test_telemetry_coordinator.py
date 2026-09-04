"""Serialized telemetry coordinator -- tests.

Every test injects ``_noop_thread_factory`` so ``reconcile()`` sets up
subscriptions and service lifecycle without spawning a real dispatcher
thread, and drives ``dispatch_once(0)`` synchronously instead.  A zero
timeout is a genuine non-blocking ``Queue.get``, so the "one-second
dispatcher timeout" path is exercised without any test sleeping.

Only ``TestDispatcherThread`` inspects the real thread factory's arguments,
and it never starts a thread either.
"""

import datetime
import queue
import threading
import time

import pytest

from wingman.telemetry.coordinator import (
    PUBLISH_INTERVAL_S,
    TelemetryCoordinator,
    _FleetMode,
    _noop_thread_factory,
)
from wingman.telemetry.metrics import NO_LOG, FleetMetrics
from wingman.telemetry.model import (
    ClientSessionId,
    CombatFact,
    FleetRow,
    FleetSnapshot,
    RosterClient,
    RosterSnapshot,
    SourceId,
    SourceLifecycle,
    StreamHealth,
)

UTC = datetime.UTC
NOW = datetime.datetime(2026, 8, 25, 12, 0, 0, tzinfo=UTC)

STREAM_HEALTH = StreamHealth(state="active")


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------


def _session(character, *, hwnd=1, pid=100, generation=1):
    return ClientSessionId(
        hwnd=hwnd, pid=pid, character=character, first_seen_generation=generation
    )


def _roster(*sessions, generation=1):
    clients = tuple(
        RosterClient(
            hwnd=s.hwnd, pid=s.pid, title=s.character, character=s.character, session=s
        )
        for s in sessions
    )
    return RosterSnapshot(generation=generation, clients=clients)


def _source_id(path="C:/logs/alice.txt", session_start=NOW):
    return SourceId(normalized_path=path, session_start_utc=session_start)


def _lifecycle(character, *, generation=1, source_id=None, available=True, active=True):
    return SourceLifecycle(
        character=character,
        generation=generation,
        source_id=source_id if source_id is not None else _source_id(),
        available=available,
        active=active,
    )


def _fact(character, kind, *, amount=None, source="", occurred_at=NOW, generation=1):
    return CombatFact(
        character=character,
        source_generation=generation,
        source_id=_source_id(),
        occurred_at=occurred_at,
        kind=kind,
        amount=amount,
        source=source,
    )


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _AttemptSignallingLock:
    """Real lock that proves one watched thread reached acquire()."""

    def __init__(self):
        self._lock = threading.Lock()
        self._watched = None
        self.attempted = threading.Event()
        self.held = False

    def watch_current_thread(self):
        self._watched = threading.get_ident()

    def acquire(self, *args, **kwargs):
        if threading.get_ident() == self._watched:
            self.attempted.set()
        acquired = self._lock.acquire(*args, **kwargs)
        if acquired:
            self.held = True
        return acquired

    def release(self):
        self.held = False
        self._lock.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *_args):
        self.release()


class FakeDiscovery:
    """ClientDiscovery's coordinator-facing surface."""

    def __init__(self, *, start_results=None, stop_results=None):
        self.starts = 0
        self.stops = 0
        self.scans = 0
        self.subscribers = []
        self.start_results = list(start_results or [])
        self.stop_results = list(stop_results or [])
        self._latest = RosterSnapshot(generation=0, clients=())

    def subscribe(self, callback):
        self.subscribers.append(callback)

        def _unsub():
            if callback in self.subscribers:
                self.subscribers.remove(callback)

        return _unsub

    def start(self):
        self.starts += 1
        return self.start_results.pop(0) if self.start_results else True

    def stop(self, timeout=5.0):
        self.stops += 1
        return self.stop_results.pop(0) if self.stop_results else True

    def request_scan(self):
        self.scans += 1

    def snapshot(self):
        return self._latest

    def publish(self, snapshot):
        self._latest = snapshot
        for callback in list(self.subscribers):
            callback(snapshot)


class FakeStream:
    """GameLogStream's coordinator-facing surface.

    ``request_source`` publishes synchronously on the CALLER's thread, as
    the real stream does -- that is what makes the republished lifecycle
    land behind the roster envelope that asked for it.
    """

    def __init__(self, health=STREAM_HEALTH, *, start_results=None, stop_results=None):
        self.starts = []
        self.stops = 0
        self.requested = []
        self.subscribers = []
        self.sources = {}
        self._health = health
        self.start_results = list(start_results or [])
        self.stop_results = list(stop_results or [])

    def subscribe(self, callback):
        self.subscribers.append(callback)

        def _unsub():
            if callback in self.subscribers:
                self.subscribers.remove(callback)

        return _unsub

    def start(self, folder):
        self.starts.append(folder)
        return self.start_results.pop(0) if self.start_results else True

    def stop(self, timeout=3.0):
        self.stops += 1
        return self.stop_results.pop(0) if self.stop_results else True

    def request_source(self, character):
        self.requested.append(character)
        self.publish(
            self.sources.get(
                character,
                SourceLifecycle(
                    character=character,
                    generation=0,
                    source_id=None,
                    available=False,
                    active=False,
                ),
            )
        )

    def health(self):
        return self._health

    def publish(self, event):
        for callback in list(self.subscribers):
            callback(event)


class RecordingMetrics:
    """FleetMetrics' interface, recording call ORDER as well as payloads."""

    def __init__(self, rows=()):
        self.calls = []
        self.rows = rows
        self.raise_on_consume = False
        self.resets = 0

    @property
    def envelopes(self):
        return [payload for kind, payload in self.calls if kind == "consume"]

    @property
    def sequences(self):
        return [env.sequence for env in self.envelopes]

    def reset(self):
        self.resets += 1
        self.calls.append(("reset", None))

    def consume(self, envelope):
        self.calls.append(("consume", envelope))
        if self.raise_on_consume:
            raise RuntimeError("metrics exploded")

    def snapshot(self, sequence, health):
        self.calls.append(("snapshot", sequence))
        return FleetSnapshot(rows=self.rows, stream_health=health)


class FakePreviewHost:
    def __init__(self, *, raises=False):
        self.rosters = []
        self.raises = raises

    def apply_roster(self, snapshot):
        self.rosters.append(snapshot)
        if self.raises:
            raise RuntimeError("preview exploded")


class FakePolicy:
    def __init__(self, *, raises=False):
        self.calls = []
        self.raises = raises
        self.resets = 0

    def reset(self):
        self.resets += 1

    def handle(self, events, now):
        self.calls.append((list(events), now))
        if self.raises:
            raise RuntimeError("policy exploded")
        return []


class _Harness:
    """A coordinator plus every fake it was built from."""

    def __init__(self, tmp_path, **kw):
        self.flags = {
            "preview": kw.pop("preview", False),
            "fleet": kw.pop("fleet", True),
            "alerts": kw.pop("alerts", False),
        }
        self.folder = kw.pop("folder", tmp_path)
        self.discovery = kw.pop("discovery", None) or FakeDiscovery()
        self.stream = kw.pop("stream", None) or FakeStream()
        self.metrics = kw.pop("metrics", None) or RecordingMetrics()
        self.preview = kw.pop("preview_host", None)
        self.policy = kw.pop("alert_policy", None)
        self.mono = [1000.0]
        self.snapshots = []
        self.coordinator = TelemetryCoordinator(
            preview_enabled=lambda: self.flags["preview"],
            fleet_enabled=lambda: self.flags["fleet"],
            alerts_enabled=lambda: self.flags["alerts"],
            gamelogs_folder=lambda: self.folder,
            discovery=self.discovery,
            stream=self.stream,
            metrics=self.metrics,
            preview_host=self.preview,
            alert_policy=self.policy,
            _thread_factory=_noop_thread_factory,
            _clock=lambda: self.mono[0],
            **kw,
        )

    def subscribe(self):
        return self.coordinator.subscribe_fleet(self.snapshots.append)

    def pump(self):
        """One synchronous dispatcher iteration, never blocking."""
        self.coordinator.dispatch_once(0)


def _harness(tmp_path, **kw):
    return _Harness(tmp_path, **kw)


# ---------------------------------------------------------------------------
# Step 1: runtime predicates
# ---------------------------------------------------------------------------


class TestRuntimePredicates:
    @pytest.mark.parametrize(
        "preview,fleet,alerts,want_discovery,want_stream,want_policy",
        [
            (False, False, False, False, False, False),
            (False, True, False, True, True, False),
            (False, False, True, False, False, False),
            (True, False, False, True, False, False),
            (True, False, True, True, True, True),
        ],
    )
    def test_runtime_predicates(
        self, tmp_path, preview, fleet, alerts, want_discovery, want_stream, want_policy
    ):
        policy = FakePolicy()
        h = _harness(
            tmp_path,
            preview=preview,
            fleet=fleet,
            alerts=alerts,
            alert_policy=policy,
            preview_host=FakePreviewHost(),
        )
        h.coordinator.reconcile()

        assert (h.discovery.starts == 1) is want_discovery
        assert (len(h.stream.starts) == 1) is want_stream

        # Alert eligibility is only observable through delivery, and a fact
        # can only arrive at all while the stream is running -- the two
        # rows where want_stream is False assert the trivially-true half of
        # that on purpose: no stream, no alert, whatever alerts_enabled says.
        if want_stream:
            h.stream.publish(_fact("Alice", "incoming_damage", source="Rat"))
            h.pump()
        assert (len(policy.calls) == 1) is want_policy

    def test_alert_policy_resets_across_disable_and_reenable(self, tmp_path):
        policy = FakePolicy()
        h = _harness(
            tmp_path,
            preview=True,
            fleet=True,
            alerts=True,
            preview_host=FakePreviewHost(),
            alert_policy=policy,
        )
        h.coordinator.reconcile()
        h.pump()
        initial = policy.resets

        h.flags["alerts"] = False
        h.coordinator.reconcile()
        h.pump()
        h.flags["alerts"] = True
        h.coordinator.reconcile()
        h.pump()

        assert policy.resets == initial + 2

    def test_stream_needs_a_resolvable_folder(self, tmp_path):
        h = _harness(tmp_path, fleet=True, folder=tmp_path / "gone")
        h.coordinator.reconcile()

        assert h.discovery.starts == 1
        assert h.stream.starts == []

    def test_stream_stops_when_the_folder_disappears(self, tmp_path):
        folder = tmp_path / "logs"
        folder.mkdir()
        h = _harness(tmp_path, fleet=True, folder=folder)
        h.coordinator.reconcile()
        assert len(h.stream.starts) == 1
        h.discovery.publish(_roster(_session("Alice")))
        h.pump()
        initial_resets = h.metrics.resets

        folder.rmdir()
        h.coordinator.reconcile()
        h.pump()

        assert h.stream.stops == 1
        assert h.stream.subscribers == []
        assert h.metrics.resets == initial_resets + 1
        assert h.coordinator.snapshot().stream_health.state == "missing_folder"

    def test_settings_are_read_live_not_captured(self, tmp_path):
        h = _harness(tmp_path, preview=False, fleet=False, alerts=False)
        h.coordinator.reconcile()
        assert h.discovery.starts == 0

        h.flags["fleet"] = True
        h.coordinator.reconcile()

        assert h.discovery.starts == 1
        assert len(h.stream.starts) == 1

    def test_all_off_reconcile_does_not_start_a_dispatcher_for_no_fleet_consumers(
        self, tmp_path
    ):
        """Generation bookkeeping must not pay a create-and-stop startup cost."""
        h = _harness(tmp_path, preview=False, fleet=False, alerts=False)
        made = []

        def record_factory(**kwargs):
            made.append(kwargs)
            return _noop_thread_factory(**kwargs)

        h.coordinator._thread_factory = record_factory
        h.coordinator.reconcile()

        assert made == []
        assert h.coordinator._worker is None
        assert h.coordinator._running is False
        assert h.coordinator.requested_fleet_generation() == 0

    def test_reconcile_reads_predicates_while_holding_its_pass_lock(self, tmp_path):
        h = _harness(tmp_path, preview=False, fleet=False, alerts=False)
        gate = _AttemptSignallingLock()
        reads_under_lock = []
        h.coordinator._reconcile_lock = gate
        h.coordinator._fleet_enabled = lambda: (
            reads_under_lock.append(gate.held) or True
        )

        h.coordinator.reconcile()

        assert reads_under_lock
        assert all(reads_under_lock)


class TestFleetGeneration:
    def test_fleet_generation_is_reserved_even_when_dispatcher_cannot_start(
        self, tmp_path
    ):
        h = _harness(tmp_path, fleet=True)
        h.coordinator._start_dispatcher = lambda: False

        generation = h.coordinator.reconcile()

        assert generation == 1
        assert h.coordinator.requested_fleet_generation() == 1
        assert h.coordinator._fleet_requested is True

    def test_idempotent_reconcile_reuses_requested_fleet_generation(self, tmp_path):
        h = _harness(tmp_path, fleet=True)

        first = h.coordinator.reconcile()
        second = h.coordinator.reconcile()

        assert first == second == 1

    def test_each_fleet_mode_transition_reserves_a_new_generation(self, tmp_path):
        h = _harness(tmp_path, fleet=True)
        first = h.coordinator.reconcile()
        h.flags["fleet"] = False
        second = h.coordinator.reconcile()
        h.flags["fleet"] = True
        third = h.coordinator.reconcile()

        assert (first, second, third) == (1, 2, 3)

    def test_failed_start_keeps_the_reserved_generation_for_a_later_reconcile(
        self, tmp_path
    ):
        h = _harness(tmp_path, fleet=True)
        h.coordinator._start_dispatcher = lambda: False

        first = h.coordinator.reconcile()
        h.coordinator._start_dispatcher = (
            TelemetryCoordinator._start_dispatcher.__get__(h.coordinator)
        )
        h.flags["preview"] = True
        second = h.coordinator.reconcile()
        h.coordinator.dispatch_once(0)
        h.discovery.publish(_roster(_session("Alice")))
        h.coordinator.dispatch_once(0)

        assert (first, second) == (1, 1)
        assert h.coordinator.requested_fleet_generation() == 1
        assert h.coordinator.snapshot().activation_generation == 1

    def test_late_dead_dispatcher_preserves_the_reserved_fleet_generation(
        self, tmp_path
    ):
        class DeadWorker:
            def is_alive(self):
                return False

        class FailingWorker:
            def start(self):
                raise RuntimeError("thread unavailable")

            def is_alive(self):
                return False

        h = _harness(tmp_path, fleet=True)
        h.coordinator._worker = DeadWorker()
        h.coordinator._running = False
        h.coordinator._fleet_active = True
        h.coordinator._fleet_requested = True
        h.coordinator._fleet_active_generation = 1
        h.coordinator._fleet_requested_generation = 1
        h.coordinator._queue.put(_FleetMode(True, 1))
        h.subscribe()
        h.coordinator._thread_factory = lambda **_kwargs: FailingWorker()

        first = h.coordinator.reconcile()

        h.coordinator._thread_factory = _noop_thread_factory
        second = h.coordinator.reconcile()
        h.discovery.publish(_roster(_session("Alice")))
        h.pump()
        h.pump()

        assert (first, second) == (1, 1)
        assert h.coordinator.requested_fleet_generation() == 1
        assert h.snapshots
        assert h.snapshots[-1].activation_generation == 1

    def test_empty_and_disabled_snapshots_keep_generation_zero(self, tmp_path):
        h = _harness(tmp_path, fleet=True)

        assert h.coordinator.snapshot().activation_generation == 0

        h.coordinator.reconcile()
        assert h.coordinator.snapshot().activation_generation == 0

        h.flags["fleet"] = False
        h.coordinator.reconcile()
        assert h.coordinator.snapshot().activation_generation == 0

    def test_initial_fleet_activation_keeps_synthetic_snapshot_until_roster_consumed(
        self, tmp_path
    ):
        """Remembered names stay unknown until this activation has a roster."""
        h = _harness(tmp_path, fleet=True)
        h.subscribe()

        h.coordinator.reconcile()
        h.pump()

        assert h.snapshots == []
        assert h.coordinator.snapshot().activation_generation == 0

        h.discovery.publish(_roster(_session("Alice")))
        h.pump()

        assert [snapshot.activation_generation for snapshot in h.snapshots] == [1]

    def test_published_snapshot_carries_the_activated_generation(self, tmp_path):
        h = _harness(tmp_path, fleet=True)
        h.subscribe()
        h.coordinator.reconcile()

        h.discovery.publish(_roster(_session("Alice")))
        h.pump()

        assert h.snapshots[-1].activation_generation == 1


# ---------------------------------------------------------------------------
# Step 2: sequencing and source republication
# ---------------------------------------------------------------------------


class TestSequencing:
    def test_service_callbacks_only_enqueue(self, tmp_path):
        """A discovery/stream callback must return without touching a
        consumer: the real GameLogStream preserves total order, but a
        blocking subscriber stalls its producer."""
        preview = FakePreviewHost()
        h = _harness(tmp_path, preview=True, fleet=True, preview_host=preview)
        h.coordinator.reconcile()
        h.subscribe()

        h.discovery.publish(_roster(_session("Alice")))
        h.stream.publish(_lifecycle("Alice"))

        assert h.metrics.calls == []
        assert preview.rosters == []
        assert h.snapshots == []

        h.pump()

        assert h.metrics.envelopes != []
        assert preview.rosters != []
        assert h.snapshots != []

    def test_sequences_strictly_increase_across_interleaved_inputs(self, tmp_path):
        h = _harness(tmp_path, fleet=True)
        h.coordinator.reconcile()

        h.discovery.publish(_roster(_session("Alice")))
        h.pump()
        h.stream.publish(_lifecycle("Alice", generation=7))
        h.pump()
        h.discovery.publish(_roster(_session("Alice"), generation=2))
        h.pump()
        h.stream.publish(_fact("Alice", "outgoing_damage", amount=100, generation=7))
        h.pump()

        seqs = h.metrics.sequences
        assert seqs == sorted(set(seqs))
        kinds = [type(env.payload).__name__ for env in h.metrics.envelopes]
        assert kinds == [
            "RosterSnapshot",
            "SourceLifecycle",  # the republication for the new session
            "SourceLifecycle",
            "RosterSnapshot",
            "CombatFact",
        ]

    def test_new_session_republishes_its_source_after_the_roster(self, tmp_path):
        h = _harness(tmp_path, fleet=True)
        h.stream.sources["Alice"] = _lifecycle("Alice", generation=3)
        h.coordinator.reconcile()

        h.discovery.publish(_roster(_session("Alice")))
        h.pump()

        assert h.stream.requested == ["Alice"]
        first, second = h.metrics.envelopes
        assert isinstance(first.payload, RosterSnapshot)
        assert second.payload == _lifecycle("Alice", generation=3)
        assert second.sequence > first.sequence

    def test_initial_source_before_roster_is_republished_after_roster(self, tmp_path):
        """An early source event must not leave the first Fleet row at NO LOG."""
        metrics = FleetMetrics(_clock=lambda: 1000.0, _utc_now=lambda: NOW)
        h = _harness(tmp_path, fleet=True, metrics=metrics)
        h.stream.sources["Alice"] = _lifecycle("Alice", generation=3)

        h.coordinator.reconcile()
        h.stream.publish(_lifecycle("Alice", generation=3))
        h.pump()  # mode then source: no roster session exists yet

        h.discovery.publish(_roster(_session("Alice")))
        h.pump()  # roster requests the source again after its session exists

        assert h.stream.requested == ["Alice"]
        assert [
            (row.character, row.log_status) for row in h.coordinator.snapshot().rows
        ] == [("Alice", None)]

    def test_unchanged_session_does_not_republish(self, tmp_path):
        h = _harness(tmp_path, fleet=True)
        h.coordinator.reconcile()

        h.discovery.publish(_roster(_session("Alice")))
        h.pump()
        h.discovery.publish(_roster(_session("Alice"), generation=2))
        h.pump()

        assert h.stream.requested == ["Alice"]

    def test_changed_session_republishes_again(self, tmp_path):
        h = _harness(tmp_path, fleet=True)
        h.coordinator.reconcile()

        h.discovery.publish(_roster(_session("Alice")))
        h.pump()
        # A relog: same name, new first_seen_generation.
        h.discovery.publish(_roster(_session("Alice", generation=9), generation=2))
        h.pump()

        assert h.stream.requested == ["Alice", "Alice"]

    def test_departed_character_is_forgotten_and_rerequested(self, tmp_path):
        h = _harness(tmp_path, fleet=True)
        h.coordinator.reconcile()

        h.discovery.publish(_roster(_session("Alice")))
        h.pump()
        h.discovery.publish(_roster(generation=2))
        h.pump()
        h.discovery.publish(_roster(_session("Alice"), generation=3))
        h.pump()

        assert h.stream.requested == ["Alice", "Alice"]

    def test_unnamed_client_is_never_republished(self, tmp_path):
        h = _harness(tmp_path, fleet=True)
        h.coordinator.reconcile()

        snapshot = RosterSnapshot(
            generation=1,
            clients=(
                RosterClient(hwnd=1, pid=2, title="EVE", character=None, session=None),
            ),
        )
        h.discovery.publish(snapshot)
        h.pump()

        assert h.stream.requested == []

    def test_no_republication_while_the_stream_is_stopped(self, tmp_path):
        h = _harness(tmp_path, preview=True, fleet=False, alerts=False)
        h.coordinator.reconcile()
        assert h.stream.starts == []

        h.discovery.publish(_roster(_session("Alice")))
        h.pump()

        assert h.stream.requested == []

    def test_degraded_stream_health_keeps_last_good_rows_and_recovers(self, tmp_path):
        rows = (FleetRow(character="Alice", dps=24),)
        h = _harness(tmp_path, fleet=True, metrics=RecordingMetrics(rows))
        h.subscribe()
        h.coordinator.reconcile()
        h.discovery.publish(_roster(_session("Alice")))
        h.pump()

        h.stream._health = StreamHealth(state="stale", detail="3.2s since poll")
        h.pump()
        assert h.snapshots[-1].rows == rows
        assert h.snapshots[-1].stream_health.state == "stale"

        h.stream._health = StreamHealth(state="error", detail="read failed")
        h.pump()
        assert h.snapshots[-1].rows == rows
        assert h.snapshots[-1].stream_health.state == "error"

        h.stream._health = StreamHealth(state="active")
        h.pump()
        assert h.snapshots[-1].rows == rows
        assert h.snapshots[-1].stream_health == StreamHealth(state="active")

    def test_metrics_are_fed_before_the_snapshot_is_published(self, tmp_path):
        h = _harness(tmp_path, fleet=True)
        h.coordinator.reconcile()
        h.subscribe()

        h.discovery.publish(_roster(_session("Alice")))
        h.pump()

        kinds = [kind for kind, _ in h.metrics.calls]
        assert kinds[-1] == "snapshot"
        assert kinds[:-1] == ["reset", "consume", "consume"]
        assert len(h.snapshots) == 1

    def test_alert_facts_reach_policy_once_per_batch_in_order(self, tmp_path):
        policy = FakePolicy()
        h = _harness(
            tmp_path,
            preview=True,
            alerts=True,
            fleet=False,
            alert_policy=policy,
            preview_host=FakePreviewHost(),
        )
        h.mono[0] = 1234.5
        h.coordinator.reconcile()

        h.stream.publish(_fact("Alice", "incoming_damage", source="Rat"))
        h.stream.publish(_fact("Alice", "incoming_tackle", source="Bob"))
        h.stream.publish(_fact("Alice", "incoming_miss", source="Rat"))
        h.stream.publish(_fact("Alice", "decloak"))
        h.stream.publish(_fact("Alice", "outgoing_damage", amount=10))
        h.pump()

        assert len(policy.calls) == 1
        events, now = policy.calls[0]
        assert now == 1234.5
        assert [(e.character, e.event, e.source) for e in events] == [
            ("Alice", "combat", "Rat"),
            ("Alice", "warp_scramble", "Bob"),
            ("Alice", "combat", "Rat"),
            ("Alice", "decloak", ""),
        ]

    def test_preview_receives_rosters_only_while_preview_is_enabled(self, tmp_path):
        preview = FakePreviewHost()
        h = _harness(tmp_path, preview=False, fleet=True, preview_host=preview)
        h.coordinator.reconcile()

        h.discovery.publish(_roster(_session("Alice")))
        h.pump()
        assert preview.rosters == []

        h.flags["preview"] = True
        h.coordinator.reconcile()
        h.discovery.publish(_roster(_session("Alice"), generation=2))
        h.pump()

        assert [s.generation for s in preview.rosters] == [2]

    def test_preview_only_mode_never_touches_fleet_metrics_or_subscribers(
        self, tmp_path
    ):
        preview = FakePreviewHost()
        policy = FakePolicy()
        h = _harness(
            tmp_path,
            preview=True,
            fleet=False,
            alerts=True,
            preview_host=preview,
            alert_policy=policy,
        )
        h.subscribe()
        h.coordinator.reconcile()

        h.discovery.publish(_roster(_session("Alice")))
        h.stream.publish(_fact("Alice", "incoming_damage", source="Rat"))
        h.pump()

        assert preview.rosters
        assert policy.calls
        assert h.metrics.envelopes == []
        assert h.snapshots == []

    def test_disabling_fleet_resets_state_and_silences_subscribers(self, tmp_path):
        h = _harness(tmp_path, preview=True, fleet=True, preview_host=FakePreviewHost())
        h.subscribe()
        h.coordinator.reconcile()
        h.discovery.publish(_roster(_session("Alice")))
        h.pump()
        published = len(h.snapshots)

        h.flags["fleet"] = False
        h.coordinator.reconcile()
        h.pump()

        assert h.metrics.resets >= 1
        assert len(h.snapshots) == published
        assert h.coordinator.snapshot().rows == ()
        assert h.coordinator.snapshot().stream_health == StreamHealth(state="disabled")

    def test_reenabling_fleet_primes_current_roster_and_republishes_source(
        self, tmp_path
    ):
        h = _harness(
            tmp_path,
            preview=True,
            fleet=False,
            alerts=False,
            preview_host=FakePreviewHost(),
        )
        current = _roster(_session("Alice"), generation=7)
        h.discovery.publish(current)
        h.coordinator.reconcile()
        h.pump()
        assert h.metrics.envelopes == []

        h.flags["fleet"] = True
        h.coordinator.reconcile()
        h.pump()

        roster_envelopes = [
            env
            for env in h.metrics.envelopes
            if isinstance(env.payload, RosterSnapshot)
        ]
        assert [env.payload for env in roster_envelopes] == [current]
        assert h.stream.requested == ["Alice"]


class TestConsumerFailureIsolation:
    def test_preview_failure_stops_neither_alerts_nor_fleet(self, tmp_path):
        preview = FakePreviewHost(raises=True)
        policy = FakePolicy()
        h = _harness(
            tmp_path,
            preview=True,
            fleet=True,
            alerts=True,
            preview_host=preview,
            alert_policy=policy,
        )
        h.coordinator.reconcile()
        h.subscribe()

        h.discovery.publish(_roster(_session("Alice")))
        h.stream.publish(_fact("Alice", "incoming_damage", source="Rat"))
        h.pump()

        assert preview.rosters != []
        assert len(policy.calls) == 1
        assert len(h.snapshots) == 1

    def test_alert_failure_stops_neither_preview_nor_fleet(self, tmp_path):
        preview = FakePreviewHost()
        policy = FakePolicy(raises=True)
        h = _harness(
            tmp_path,
            preview=True,
            fleet=True,
            alerts=True,
            preview_host=preview,
            alert_policy=policy,
        )
        h.coordinator.reconcile()
        h.subscribe()

        h.discovery.publish(_roster(_session("Alice")))
        h.stream.publish(_fact("Alice", "incoming_damage", source="Rat"))
        h.pump()

        assert preview.rosters != []
        assert len(h.snapshots) == 1

    def test_one_failing_fleet_subscriber_cannot_starve_the_others(self, tmp_path):
        h = _harness(tmp_path, fleet=True)
        h.coordinator.reconcile()

        def _boom(_snapshot):
            raise RuntimeError("subscriber exploded")

        h.coordinator.subscribe_fleet(_boom)
        h.subscribe()

        h.discovery.publish(_roster(_session("Alice")))
        h.pump()

        assert len(h.snapshots) == 1

    def test_metrics_failure_does_not_kill_the_dispatcher(self, tmp_path):
        h = _harness(tmp_path, fleet=True)
        h.coordinator.reconcile()
        h.subscribe()
        h.discovery.publish(_roster(_session("Alice")))
        h.pump()

        h.metrics.raise_on_consume = True
        h.stream.publish(_lifecycle("Alice", generation=2))
        h.pump()
        assert len(h.snapshots) == 2

        h.metrics.raise_on_consume = False
        h.stream.publish(_lifecycle("Alice", generation=3))
        h.pump()

        assert len(h.snapshots) == 3

    def test_unsubscribed_fleet_callback_stops_receiving(self, tmp_path):
        h = _harness(tmp_path, fleet=True)
        h.coordinator.reconcile()
        unsub = h.subscribe()

        h.discovery.publish(_roster(_session("Alice")))
        h.pump()
        assert len(h.snapshots) == 1

        unsub()
        h.pump()

        assert len(h.snapshots) == 1


# ---------------------------------------------------------------------------
# Step 3: lifecycle and cadence
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_first_consumer_starts_each_service_exactly_once(self, tmp_path):
        h = _harness(tmp_path, preview=True, fleet=True, alerts=True)

        h.coordinator.reconcile()
        h.coordinator.reconcile()
        h.coordinator.reconcile()

        assert h.discovery.starts == 1
        assert h.stream.starts == [tmp_path]
        assert len(h.discovery.subscribers) == 1
        assert len(h.stream.subscribers) == 1

    def test_last_consumer_stops_each_service_exactly_once(self, tmp_path):
        h = _harness(tmp_path, preview=True, fleet=True, alerts=True)
        h.coordinator.reconcile()

        h.flags.update(preview=False, fleet=False, alerts=False)
        h.coordinator.reconcile()
        h.coordinator.reconcile()

        assert h.discovery.stops == 1
        assert h.stream.stops == 1
        assert h.discovery.subscribers == []
        assert h.stream.subscribers == []

    def test_dropping_only_the_fleet_keeps_discovery_for_preview(self, tmp_path):
        h = _harness(tmp_path, preview=True, fleet=True, alerts=False)
        h.coordinator.reconcile()

        h.flags["fleet"] = False
        h.coordinator.reconcile()

        assert h.discovery.stops == 0
        assert h.discovery.starts == 1
        assert h.stream.stops == 1

    def test_stop_retries_timed_out_services_and_reports_completion(self, tmp_path):
        discovery = FakeDiscovery(stop_results=[False, True])
        stream = FakeStream(stop_results=[False, True])
        h = _harness(tmp_path, fleet=True, discovery=discovery, stream=stream)
        h.coordinator.reconcile()

        assert h.coordinator.stop() is True
        assert discovery.stops == 2
        assert stream.stops == 2

    def test_stop_reports_an_authoritative_worker_that_remains_stuck(self, tmp_path):
        discovery = FakeDiscovery(stop_results=[False, False])
        h = _harness(tmp_path, fleet=True, discovery=discovery)
        h.coordinator.reconcile()

        assert h.coordinator.stop() is False
        assert discovery.stops == 2

    def test_stop_stops_every_service_and_is_idempotent(self, tmp_path):
        h = _harness(tmp_path, preview=True, fleet=True, alerts=True)
        h.coordinator.reconcile()

        h.coordinator.stop()
        h.coordinator.stop()

        assert h.discovery.stops == 1
        assert h.stream.stops == 1
        assert h.discovery.subscribers == []
        assert h.stream.subscribers == []

    def test_reconcile_after_stop_restarts(self, tmp_path):
        h = _harness(tmp_path, fleet=True)
        h.coordinator.reconcile()
        h.coordinator.stop()

        h.coordinator.reconcile()

        assert h.discovery.starts == 2
        assert len(h.stream.starts) == 2
        assert len(h.discovery.subscribers) == 1

    def test_stop_discards_telemetry_nobody_consumed(self, tmp_path):
        h = _harness(tmp_path, fleet=True)
        h.coordinator.reconcile()

        h.discovery.publish(_roster(_session("Alice")))
        h.coordinator.stop()

        # The queued callback payload described the dispatcher generation
        # that ended. Stop drains it without stamping; a later reconcile may
        # legitimately prime discovery's current snapshot as fresh state.
        assert h.metrics.envelopes == []
        assert h.coordinator._queue.empty()

    def test_restart_reasks_the_stream_about_a_surviving_session(self, tmp_path):
        h = _harness(tmp_path, fleet=True)
        h.coordinator.reconcile()
        h.discovery.publish(_roster(_session("Alice")))
        h.pump()
        assert h.stream.requested == ["Alice"]

        h.coordinator.stop()
        h.coordinator.reconcile()
        # ClientDiscovery keeps session identity across its own restart, so
        # the very same session is republished -- and the binding it had is
        # gone, so it must be asked for again.
        h.discovery.publish(_roster(_session("Alice")))
        h.pump()

        assert h.stream.requested == ["Alice", "Alice"]

    def test_a_changed_folder_restarts_and_rebinds_fleet_sources(self, tmp_path):
        second = tmp_path / "other"
        second.mkdir()
        h = _harness(tmp_path, fleet=True)
        h.coordinator.reconcile()
        h.discovery.publish(_roster(_session("Alice")))
        h.pump()
        assert h.stream.requested == ["Alice"]
        initial_resets = h.metrics.resets

        h.folder = second
        h.coordinator.reconcile()
        h.pump()

        assert h.stream.stops == 1
        assert h.stream.starts == [tmp_path, second]
        assert h.metrics.resets == initial_resets + 1
        assert h.stream.requested == ["Alice", "Alice"]

    def test_request_discovery_forwards_only_while_running(self, tmp_path):
        h = _harness(tmp_path, preview=False, fleet=False)
        h.coordinator.reconcile()

        h.coordinator.request_discovery()
        assert h.discovery.scans == 0

        h.flags["fleet"] = True
        h.coordinator.reconcile()
        h.coordinator.request_discovery()

        assert h.discovery.scans == 1

    def test_refused_service_starts_are_not_recorded_and_retry(self, tmp_path):
        discovery = FakeDiscovery(start_results=[False, True])
        stream = FakeStream(start_results=[False, True])
        h = _harness(tmp_path, fleet=True, discovery=discovery, stream=stream)

        h.coordinator.reconcile()
        assert discovery.starts == 1
        assert stream.starts == [tmp_path]
        assert discovery.subscribers == []
        assert stream.subscribers == []

        h.coordinator.reconcile()
        assert discovery.starts == 2
        assert stream.starts == [tmp_path, tmp_path]
        assert len(discovery.subscribers) == 1
        assert len(stream.subscribers) == 1

    def test_timed_out_service_stops_are_retried_before_restart(self, tmp_path):
        discovery = FakeDiscovery(stop_results=[False, True])
        stream = FakeStream(stop_results=[False, True])
        h = _harness(tmp_path, fleet=True, discovery=discovery, stream=stream)
        h.coordinator.reconcile()

        h.flags["fleet"] = False
        h.coordinator.reconcile()
        assert discovery.stops == 1
        assert stream.stops == 1
        assert discovery.subscribers == []
        assert stream.subscribers == []

        h.flags["fleet"] = True
        h.coordinator.reconcile()
        assert discovery.stops == 2
        assert stream.stops == 2
        assert discovery.starts == 2
        assert stream.starts == [tmp_path, tmp_path]
        assert len(discovery.subscribers) == 1
        assert len(stream.subscribers) == 1


class TestDispatcherThread:
    def test_dispatcher_thread_is_non_daemon_and_single(self, tmp_path):
        made = []

        def _factory(*, target, args, name, daemon):
            made.append({"name": name, "daemon": daemon})
            return _noop_thread_factory(
                target=target, args=args, name=name, daemon=daemon
            )

        coordinator = TelemetryCoordinator(
            preview_enabled=lambda: True,
            fleet_enabled=lambda: True,
            alerts_enabled=lambda: False,
            gamelogs_folder=lambda: tmp_path,
            discovery=FakeDiscovery(),
            stream=FakeStream(),
            metrics=RecordingMetrics(),
            _thread_factory=_factory,
        )
        coordinator.reconcile()
        coordinator.reconcile()

        assert made == [{"name": "telemetry-dispatch", "daemon": False}]

    def test_real_dispatcher_thread_publishes_and_joins(self, tmp_path):
        discovery = FakeDiscovery()
        stream = FakeStream()
        metrics = FleetMetrics(_clock=lambda: 1000.0, _utc_now=lambda: NOW)
        coordinator = TelemetryCoordinator(
            preview_enabled=lambda: False,
            fleet_enabled=lambda: True,
            alerts_enabled=lambda: False,
            gamelogs_folder=lambda: tmp_path,
            discovery=discovery,
            stream=stream,
            metrics=metrics,
        )
        seen = queue.Queue()
        coordinator.subscribe_fleet(seen.put)
        coordinator.reconcile()
        try:
            discovery.publish(_roster(_session("Alice")))
            deadline = time.monotonic() + 5
            snapshot = None
            while time.monotonic() < deadline:
                candidate = seen.get(timeout=max(0.01, deadline - time.monotonic()))
                if candidate.rows:
                    snapshot = candidate
                    break
            assert snapshot is not None
            assert [row.character for row in snapshot.rows] == ["Alice"]
        finally:
            coordinator.stop(timeout=5)

        assert discovery.stops == 1
        assert stream.stops == 1

    def test_manual_dispatch_is_rejected_while_worker_is_alive(self, tmp_path):
        coordinator = TelemetryCoordinator(
            preview_enabled=lambda: True,
            fleet_enabled=lambda: False,
            alerts_enabled=lambda: False,
            gamelogs_folder=lambda: tmp_path,
            discovery=FakeDiscovery(),
            stream=FakeStream(),
            metrics=RecordingMetrics(),
        )
        coordinator.reconcile()
        try:
            with pytest.raises(RuntimeError, match="dispatcher worker"):
                coordinator.dispatch_once(0)
        finally:
            coordinator.stop(timeout=5)

    def test_failed_dispatcher_start_rolls_back_and_starts_no_producers(self, tmp_path):
        class FailingWorker:
            def start(self):
                raise RuntimeError("thread unavailable")

            def is_alive(self):
                return False

        discovery = FakeDiscovery()
        stream = FakeStream()
        coordinator = TelemetryCoordinator(
            preview_enabled=lambda: False,
            fleet_enabled=lambda: True,
            alerts_enabled=lambda: False,
            gamelogs_folder=lambda: tmp_path,
            discovery=discovery,
            stream=stream,
            metrics=RecordingMetrics(),
            _thread_factory=lambda **_kwargs: FailingWorker(),
        )

        coordinator.reconcile()

        assert coordinator._running is False
        assert coordinator._worker is None
        assert discovery.starts == 0
        assert stream.starts == []

    def test_refused_dispatcher_restart_does_not_start_producers(self, tmp_path):
        class AliveWorker:
            def is_alive(self):
                return True

        discovery = FakeDiscovery()
        stream = FakeStream()
        h = _harness(tmp_path, fleet=True, discovery=discovery, stream=stream)
        h.coordinator._worker = AliveWorker()
        h.coordinator._running = False

        h.coordinator.reconcile()

        assert discovery.starts == 0
        assert stream.starts == []

    def test_late_dead_dispatcher_is_finalized_before_restart(self, tmp_path):
        class DeadWorker:
            def is_alive(self):
                return False

        h = _harness(tmp_path, fleet=True)
        h.coordinator._worker = DeadWorker()
        h.coordinator._running = False
        h.coordinator._fleet_active = True
        h.coordinator._fleet_requested = True
        h.coordinator._sessions = {"Old Session": object()}
        h.coordinator._latest = FleetSnapshot(
            rows=(FleetRow("Old Session", 99),),
            stream_health=StreamHealth(state="active"),
        )
        h.coordinator._queue.put(_roster(_session("Old Session")))

        h.coordinator.reconcile()
        h.pump()

        assert h.coordinator._sessions == {}
        assert h.coordinator.snapshot().rows == ()
        assert not [
            envelope
            for envelope in h.metrics.envelopes
            if isinstance(envelope.payload, RosterSnapshot) and envelope.payload.clients
        ]

    def test_manual_dispatch_calls_have_one_owner(self, tmp_path):
        class BlockingMetrics(RecordingMetrics):
            def __init__(self):
                super().__init__()
                self.entered = threading.Event()
                self.release = threading.Event()

            def consume(self, envelope):
                super().consume(envelope)
                if not self.entered.is_set():
                    self.entered.set()
                    assert self.release.wait(5)

        metrics = BlockingMetrics()
        h = _harness(tmp_path, fleet=True, metrics=metrics)
        gate = _AttemptSignallingLock()
        h.coordinator._dispatch_lock = gate
        h.coordinator.reconcile()
        h.discovery.publish(_roster(_session("Alice")))

        first = threading.Thread(target=lambda: h.coordinator.dispatch_once(0))
        first.start()
        assert metrics.entered.wait(5)

        h.stream.publish(_lifecycle("Alice"))
        second_done = threading.Event()

        def second_dispatch():
            gate.watch_current_thread()
            h.coordinator.dispatch_once(0)
            second_done.set()

        second = threading.Thread(target=second_dispatch)
        second.start()
        assert gate.attempted.wait(5)
        assert not second_done.is_set()

        metrics.release.set()
        first.join(5)
        second.join(5)
        assert not first.is_alive()
        assert not second.is_alive()
        assert metrics.sequences == sorted(set(metrics.sequences))


class TestCadence:
    def _fleet_harness(self, tmp_path):
        """A harness wired to the REAL FleetMetrics on injected clocks."""
        wall = [NOW]
        mono = [1000.0]
        metrics = FleetMetrics(_clock=lambda: mono[0], _utc_now=lambda: wall[0])
        h = _harness(tmp_path, fleet=True, metrics=metrics)
        return h, wall, mono

    def test_timeout_publishes_a_freshly_decayed_snapshot(self, tmp_path):
        h, wall, mono = self._fleet_harness(tmp_path)
        h.stream.sources["Alice"] = _lifecycle("Alice", generation=3)
        h.coordinator.reconcile()
        h.subscribe()

        h.discovery.publish(_roster(_session("Alice")))
        h.pump()  # roster, then the republished lifecycle that binds it

        h.stream.publish(_fact("Alice", "outgoing_damage", amount=100, generation=3))
        h.pump()
        assert h.snapshots[-1].rows[0].dps == 10

        # No new fact: only the clocks move, and only the one-second
        # dispatcher timeout publishes.
        wall[0] = NOW + datetime.timedelta(seconds=1)
        mono[0] += 1.0
        h.pump()
        assert h.snapshots[-1].rows[0].dps == 10

        wall[0] = NOW + datetime.timedelta(seconds=11)
        mono[0] += 10.0
        h.pump()

        assert h.snapshots[-1].rows[0].dps == 0
        assert len(h.snapshots) == 4

    def test_published_snapshot_carries_stream_health(self, tmp_path):
        h = _harness(
            tmp_path, fleet=True, stream=FakeStream(health=StreamHealth(state="stale"))
        )
        h.coordinator.reconcile()
        h.subscribe()
        h.discovery.publish(_roster(_session("Alice")))
        h.pump()

        assert h.snapshots[-1].stream_health == StreamHealth(state="stale")

    def test_snapshot_returns_the_last_published_value(self, tmp_path):
        h, _wall, _mono = self._fleet_harness(tmp_path)
        h.coordinator.reconcile()

        assert h.coordinator.snapshot().rows == ()

        h.discovery.publish(_roster(_session("Alice")))
        h.pump()

        rows = h.coordinator.snapshot().rows
        assert [(r.character, r.log_status) for r in rows] == [("Alice", NO_LOG)]

    def test_health_says_disabled_when_no_consumer_wants_the_stream(self, tmp_path):
        h = _harness(tmp_path, preview=True, fleet=False, alerts=False)
        h.coordinator.reconcile()

        assert h.coordinator.snapshot().stream_health == StreamHealth(state="disabled")

    def test_health_says_missing_folder_when_a_consumer_wants_the_stream(
        self, tmp_path
    ):
        h = _harness(tmp_path, fleet=True, folder=tmp_path / "gone")
        h.coordinator.reconcile()

        health = h.coordinator.snapshot().stream_health
        assert health.state == "missing_folder"
        assert health.detail == str(tmp_path / "gone")

    def test_publish_interval_is_one_second(self):
        assert PUBLISH_INTERVAL_S == 1.0
