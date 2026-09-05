"""FleetSharingWorker -- non-blocking coordinator handoff and relay loop.

Two families of test here:

* ``iterate_once()``-driven tests (``_noop_thread_factory``, an injected
  monotonic clock) exercise every relay-facing behaviour deterministically:
  catalogue refresh cadence, coalescing, withdrawal, and every error class's
  status/backoff mapping. These never spawn a real thread.
* A small number of REAL-thread tests prove the two properties that cannot
  be shown any other way: ``submit()`` never blocks even while the worker's
  own thread is stuck inside a blocking relay call, and ``stop()`` is
  bounded rather than hanging forever on that same stuck call.
"""

from __future__ import annotations

import threading
import time

import pytest

from wingman.fleetsharing.client import FleetRelayError
from wingman.fleetsharing.model import CatalogueCharacter, FleetCatalogue, PublishRow
from wingman.fleetsharing.state import DeviceIdentity, SharingState
from wingman.fleetsharing.worker import (
    CATALOGUE_REFRESH_INTERVAL_S,
    FleetSharingWorker,
    SharingStatus,
    _noop_thread_factory,
)
from wingman.telemetry.model import FleetRow, FleetSnapshot, StreamHealth

STREAM_HEALTH = StreamHealth(state="active")

PAIRED_STATE = SharingState(
    identity=DeviceIdentity(
        protected_private_key_b64="protected", public_key_spki_b64="public"
    ),
    relay_origin="https://relay.test",
    session_id="session-1",
)

CATALOGUE = FleetCatalogue(
    revision=1,
    characters=(CatalogueCharacter(character_id=1, character_name="Alice"),),
)


def _snapshot(dps, *, character="Alice", ewar=()):
    return FleetSnapshot(
        rows=(FleetRow(character=character, dps=dps, ewar=ewar, log_status=None),),
        stream_health=STREAM_HEALTH,
    )


def _unwrap(_blob):
    return b"\x00" * 32


class FakeRelayClient:
    """A fully synchronous fake -- records calls, no real network."""

    def __init__(self, *, catalogue=CATALOGUE):
        self.catalogue = catalogue
        self.fetch_calls: list[int] = []
        self.publish_calls: list[tuple[int, tuple[PublishRow, ...]]] = []
        self.fetch_error: Exception | None = None
        self.publish_error: Exception | None = None

    def fetch_catalogue(self, *, session_id, private_key, revision):
        assert isinstance(private_key, bytes)
        self.fetch_calls.append(revision)
        if self.fetch_error is not None:
            raise self.fetch_error
        return self.catalogue

    def publish_snapshot(self, *, session_id, private_key, revision, rows):
        assert isinstance(private_key, bytes)
        self.publish_calls.append((revision, rows))
        if self.publish_error is not None:
            raise self.publish_error


class BlockingRelayClient:
    """Blocks the FIRST publish_snapshot call until ``release`` is set."""

    def __init__(self, catalogue=CATALOGUE):
        self.catalogue = catalogue
        self.publish_calls: list[tuple[PublishRow, ...]] = []
        self.entered = threading.Event()
        self.release = threading.Event()

    def fetch_catalogue(self, *, session_id, private_key, revision):
        return self.catalogue

    def publish_snapshot(self, *, session_id, private_key, revision, rows):
        self.publish_calls.append(rows)
        if not self.entered.is_set():
            self.entered.set()
            assert self.release.wait(5), "test fixture deadlocked"


def _worker(
    client, *, state=PAIRED_STATE, clock=None, thread_factory=_noop_thread_factory
):
    mono = clock or (lambda: 1000.0)
    return FleetSharingWorker(
        load_state=lambda: state,
        client_factory=lambda origin: client,
        unwrap_private_key=_unwrap,
        _thread_factory=thread_factory,
        _clock=mono,
        _jitter=lambda: 0.0,
    )


# ---------------------------------------------------------------------------
# Deterministic iterate_once() behaviour
# ---------------------------------------------------------------------------


class TestUnpaired:
    def test_unpaired_worker_never_touches_the_client_and_reports_stopped(self):
        client = FakeRelayClient()
        worker = _worker(client, state=SharingState())

        worker.iterate_once()

        assert client.fetch_calls == []
        assert client.publish_calls == []
        assert worker.status() == SharingStatus(state="stopped")

    def test_a_paired_worker_that_becomes_unpaired_resets_and_stops(self):
        client = FakeRelayClient()
        states = [PAIRED_STATE]
        worker = FleetSharingWorker(
            load_state=lambda: states[0],
            client_factory=lambda origin: client,
            unwrap_private_key=_unwrap,
            _thread_factory=_noop_thread_factory,
            _clock=lambda: 1000.0,
            _jitter=lambda: 0.0,
        )
        worker.submit(_snapshot(10))

        worker.iterate_once()
        assert worker.status().state == "active"

        states[0] = SharingState()
        worker.iterate_once()

        assert worker.status() == SharingStatus(state="stopped")


class TestCatalogueRefresh:
    def test_catalogue_is_fetched_once_and_reused_before_the_interval_elapses(self):
        client = FakeRelayClient()
        mono = [1000.0]
        worker = _worker(client, clock=lambda: mono[0])

        worker.iterate_once()
        mono[0] += CATALOGUE_REFRESH_INTERVAL_S - 1
        worker.submit(_snapshot(10))
        worker.iterate_once()

        assert client.fetch_calls == [1]

    def test_catalogue_is_refetched_once_the_refresh_interval_elapses(self):
        client = FakeRelayClient()
        mono = [1000.0]
        worker = _worker(client, clock=lambda: mono[0])

        worker.iterate_once()
        mono[0] += CATALOGUE_REFRESH_INTERVAL_S
        worker.iterate_once()

        assert client.fetch_calls == [1, 2]

    def test_first_contact_this_session_reports_connecting_later_reports_verifying(
        self,
    ):
        mono = [1000.0]
        statuses = []
        holder: dict = {}

        class _Recording(FakeRelayClient):
            def fetch_catalogue(self, **kwargs):
                statuses.append(holder["worker"].status().state)
                return super().fetch_catalogue(**kwargs)

        client = _Recording()
        worker = _worker(client, clock=lambda: mono[0])
        holder["worker"] = worker

        worker.iterate_once()
        mono[0] += CATALOGUE_REFRESH_INTERVAL_S
        worker.iterate_once()

        assert statuses == ["connecting", "verifying"]


class TestProjectionAndPublication:
    def test_no_snapshot_yet_never_publishes(self):
        client = FakeRelayClient()
        worker = _worker(client)

        worker.iterate_once()

        assert client.publish_calls == []
        assert worker.status().state == "active"

    def test_a_matching_row_publishes_with_an_advancing_revision(self):
        client = FakeRelayClient()
        worker = _worker(client)
        worker.submit(_snapshot(42))

        worker.iterate_once()

        assert len(client.publish_calls) == 1
        revision, rows = client.publish_calls[0]
        assert rows == (PublishRow(character_id=1, dps=42, ewar=()),)
        # revision 1 was consumed by fetch_catalogue; publish gets a new one.
        assert revision == 2

    def test_unmatched_local_name_publishes_nothing_but_no_error(self):
        client = FakeRelayClient()
        worker = _worker(client)
        worker.submit(_snapshot(42, character="Nobody"))

        worker.iterate_once()

        assert client.publish_calls == []
        assert worker.status().state == "active"

    def test_a_row_that_stops_matching_withdraws_the_previous_publication(self):
        client = FakeRelayClient()
        worker = _worker(client)
        worker.submit(_snapshot(42))
        worker.iterate_once()
        assert client.publish_calls[-1][1] != ()

        worker.submit(_snapshot(42, character="Nobody"))
        worker.iterate_once()

        assert client.publish_calls[-1][1] == ()

    def test_identical_projection_is_not_republished(self):
        client = FakeRelayClient()
        worker = _worker(client)
        worker.submit(_snapshot(42))
        worker.iterate_once()
        assert len(client.publish_calls) == 1

        worker.submit(_snapshot(42))
        worker.iterate_once()

        assert len(client.publish_calls) == 1

    def test_changed_projection_publishes_immediately(self):
        client = FakeRelayClient()
        worker = _worker(client)
        worker.submit(_snapshot(42))
        worker.iterate_once()

        worker.submit(_snapshot(43))
        worker.iterate_once()

        assert len(client.publish_calls) == 2
        assert client.publish_calls[-1][1] == (PublishRow(1, 43, ()),)

    def test_revision_advances_across_a_failed_then_retried_publish(self):
        """A failure must not let a later attempt replay the same revision."""
        client = FakeRelayClient()
        worker = _worker(client)
        worker.submit(_snapshot(42))
        client.publish_error = FleetRelayError(500, "server_error", "boom")
        worker.iterate_once()
        assert client.publish_calls[-1][0] == 2  # fetch=1, publish attempt=2

        client.publish_error = None
        worker.submit(_snapshot(42))  # same content: forces a resend attempt
        worker.iterate_once()

        assert [rev for rev, _ in client.publish_calls] == [2, 3]


class TestRelayErrors:
    def test_forbidden_response_marks_refused_and_forces_a_catalogue_refresh(self):
        client = FakeRelayClient()
        worker = _worker(client)
        worker.submit(_snapshot(42))
        worker.iterate_once()
        assert client.fetch_calls == [1]

        client.publish_error = FleetRelayError(403, "forbidden", "no")
        worker.submit(_snapshot(43))  # a real change, so a publish is attempted
        worker.iterate_once()

        assert worker.status() == SharingStatus(state="refused", detail="forbidden")
        assert worker._catalogue is None  # forced stale by the 403

        # The next pass must refresh the catalogue again before retrying --
        # no fetch happened above because the cached catalogue was still
        # fresh at that point.
        worker.iterate_once()
        assert client.fetch_calls == [1, 4]

    def test_unauthorized_response_is_also_refused(self):
        client = FakeRelayClient()
        client.publish_error = FleetRelayError(401, "unauthorized", "no")
        worker = _worker(client)
        worker.submit(_snapshot(42))

        worker.iterate_once()

        assert worker.status() == SharingStatus(state="refused", detail="unauthorized")

    def test_rate_limited_response_backs_off_and_a_later_success_recovers(self):
        client = FakeRelayClient()
        client.publish_error = FleetRelayError(429, "rate_limited", "slow down")
        worker = _worker(client)
        worker.submit(_snapshot(42))

        worker.iterate_once()
        assert worker.status() == SharingStatus(state="error", detail="rate_limited")
        assert worker._backoff == pytest.approx(1.0)

        worker.iterate_once()  # still failing: backoff should grow
        assert worker._backoff == pytest.approx(2.0)

        client.publish_error = None
        worker.iterate_once()
        assert worker.status().state == "active"
        assert worker._backoff == 0.0

    def test_network_failure_backs_off_the_same_way_as_a_rate_limit(self):
        client = FakeRelayClient()
        client.publish_error = FleetRelayError(None, "transport_error", "down")
        worker = _worker(client)
        worker.submit(_snapshot(42))

        worker.iterate_once()

        assert worker.status() == SharingStatus(state="error", detail="transport_error")
        assert worker._backoff == pytest.approx(1.0)

    def test_protocol_mismatch_is_reported_as_an_error_not_refused(self):
        client = FakeRelayClient()
        client.fetch_error = FleetRelayError(None, "protocol_mismatch", "nope")
        worker = _worker(client)

        worker.iterate_once()

        assert worker.status() == SharingStatus(
            state="error", detail="protocol_mismatch"
        )

    def test_backoff_is_capped(self):
        client = FakeRelayClient()
        client.publish_error = FleetRelayError(500, "server_error", "boom")
        worker = _worker(client)
        worker.submit(_snapshot(42))

        for _ in range(10):
            worker.iterate_once()

        assert worker._backoff <= 30.0


class TestIterateOnceLifecycleGuard:
    def test_iterate_once_refuses_to_run_beside_a_live_worker(self):
        class AliveWorker:
            def is_alive(self):
                return True

        worker = _worker(FakeRelayClient())
        worker._worker = AliveWorker()

        with pytest.raises(RuntimeError, match="sharing worker"):
            worker.iterate_once()

    def test_status_defaults_to_stopped_before_any_iteration(self):
        worker = _worker(FakeRelayClient())
        assert worker.status() == SharingStatus(state="stopped")


class TestBasicLifecycle:
    def test_start_is_idempotent(self):
        worker = _worker(FakeRelayClient())
        assert worker.start() is True
        assert worker.start() is True

    def test_stop_without_start_is_a_noop(self):
        worker = _worker(FakeRelayClient())
        assert worker.stop() is True

    def test_worker_thread_is_non_daemon_and_named(self):
        made = []

        def factory(*, target, args, name, daemon):
            made.append({"name": name, "daemon": daemon})
            return _noop_thread_factory(
                target=target, args=args, name=name, daemon=daemon
            )

        worker = _worker(FakeRelayClient(), thread_factory=factory)
        worker.start()

        assert made == [{"name": "fleet-sharing-worker", "daemon": False}]


# ---------------------------------------------------------------------------
# Real-thread concurrency proofs
# ---------------------------------------------------------------------------


class TestRealThreadConcurrency:
    def test_submit_never_blocks_and_the_worker_publishes_only_the_latest_snapshot(
        self,
    ):
        client = BlockingRelayClient()
        worker = FleetSharingWorker(
            load_state=lambda: PAIRED_STATE,
            client_factory=lambda origin: client,
            unwrap_private_key=_unwrap,
        )
        assert worker.start()
        try:
            worker.submit(_snapshot(10))  # A: will block inside publish_snapshot
            assert client.entered.wait(5), "worker never reached the blocking call"

            started = time.monotonic()
            worker.submit(_snapshot(20))  # B: overwritten before it is ever read
            worker.submit(_snapshot(30))  # C: the only one that must survive
            elapsed = time.monotonic() - started
            assert elapsed < 0.5, "submit() must never block on the stuck worker"
            assert len(client.publish_calls) == 1  # only A has been sent so far

            client.release.set()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and len(client.publish_calls) < 2:
                time.sleep(0.01)
        finally:
            client.release.set()
            worker.stop(timeout=5)

        assert len(client.publish_calls) == 2
        assert client.publish_calls[0][0].dps == 10
        assert client.publish_calls[1][0].dps == 30

    def test_stop_is_bounded_while_a_request_is_blocked_then_completes_after_release(
        self,
    ):
        client = BlockingRelayClient()
        worker = FleetSharingWorker(
            load_state=lambda: PAIRED_STATE,
            client_factory=lambda origin: client,
            unwrap_private_key=_unwrap,
        )
        worker.start()
        worker.submit(_snapshot(10))
        assert client.entered.wait(5)

        started = time.monotonic()
        assert worker.stop(timeout=0.2) is False
        assert time.monotonic() - started < 2.0

        client.release.set()
        assert worker.stop(timeout=5) is True


class TestCoordinatorIntegration:
    def test_coordinator_cadence_and_local_metrics_continue_while_sharing_is_blocked(
        self, tmp_path
    ):
        """A sharing worker stuck in a blocking relay call must never stall
        the coordinator's own dispatcher, its cadence, or any other
        subscriber -- the whole reason submit() only ever swaps a
        reference and signals."""
        from wingman.telemetry.coordinator import TelemetryCoordinator
        from wingman.telemetry.model import FleetSnapshot as TelemetryFleetSnapshot

        class _FakeDiscovery:
            def __init__(self):
                self.subscribers = []

            def subscribe(self, callback):
                self.subscribers.append(callback)
                return lambda: None

            def start(self):
                return True

            def stop(self, timeout=5.0):
                return True

            def request_scan(self):
                pass

        class _FakeStream:
            def subscribe(self, callback):
                return lambda: None

            def start(self, folder):
                return True

            def stop(self, timeout=3.0):
                return True

            def health(self):
                return STREAM_HEALTH

        class _FakeMetrics:
            """Always produces one non-empty row -- real FleetMetrics/roster/
            source-lifecycle wiring is exercised elsewhere; this test only
            needs the coordinator's own one-second cadence and a row the
            sharing worker's catalogue can match."""

            def reset(self):
                pass

            def consume(self, envelope):
                pass

            def snapshot(self, sequence, health):
                return TelemetryFleetSnapshot(
                    rows=(
                        FleetRow(character="Alice", dps=24, ewar=(), log_status=None),
                    ),
                    stream_health=health,
                )

        client = BlockingRelayClient()
        worker = FleetSharingWorker(
            load_state=lambda: PAIRED_STATE,
            client_factory=lambda origin: client,
            unwrap_private_key=_unwrap,
        )
        coordinator = TelemetryCoordinator(
            preview_enabled=lambda: False,
            fleet_enabled=lambda: False,
            alerts_enabled=lambda: False,
            sharing_enabled=lambda: True,
            gamelogs_folder=lambda: tmp_path,
            discovery=_FakeDiscovery(),
            stream=_FakeStream(),
            metrics=_FakeMetrics(),
        )
        local_snapshots = []
        coordinator.subscribe_fleet(local_snapshots.append)
        coordinator.subscribe_fleet(worker.submit)

        assert worker.start()
        try:
            coordinator.reconcile()

            assert client.entered.wait(5), "sharing worker never reached the relay call"

            # The coordinator must keep publishing (its one-second cadence)
            # to every OTHER subscriber the whole time the sharing worker
            # remains stuck.
            before = len(local_snapshots)
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and len(local_snapshots) <= before:
                time.sleep(0.05)
            assert len(local_snapshots) > before
        finally:
            client.release.set()
            worker.stop(timeout=5)
            coordinator.stop(timeout=5)
