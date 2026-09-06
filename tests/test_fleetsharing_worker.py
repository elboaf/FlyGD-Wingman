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
    BASE_BACKOFF_S,
    CATALOGUE_REFRESH_INTERVAL_S,
    HEARTBEAT_INTERVAL_S,
    INERT_POLL_S,
    MAX_SNAPSHOT_AGE_S,
    SESSION_RENEWAL_INTERVAL_S,
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
        self.renew_calls: list[int] = []
        self.fetch_error: Exception | None = None
        self.publish_error: Exception | None = None
        self.renew_error: Exception | None = None

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

    def renew_session(self, *, session_id, private_key, revision):
        assert isinstance(private_key, bytes)
        self.renew_calls.append(revision)
        if self.renew_error is not None:
            raise self.renew_error
        return "2026-01-01T00:30:00.000Z"


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

    def renew_session(self, *, session_id, private_key, revision):
        return "2026-01-01T00:30:00.000Z"


def _worker(
    client,
    *,
    state=PAIRED_STATE,
    clock=None,
    thread_factory=_noop_thread_factory,
    sharing_enabled=lambda: True,
    save_state=None,
):
    mono = clock or (lambda: 1000.0)
    kwargs = dict(
        load_state=lambda: state,
        client_factory=lambda origin: client,
        unwrap_private_key=_unwrap,
        sharing_enabled=sharing_enabled,
        _thread_factory=thread_factory,
        _clock=mono,
        _jitter=lambda: 0.0,
    )
    if save_state is not None:
        kwargs["save_state"] = save_state
    return FleetSharingWorker(**kwargs)


class _InMemoryStateStore:
    """A tiny stand-in for `wingman.fleetsharing.state.load`/`save` bound to
    one file: `load()`/`save(state)` round-trip through the SAME in-memory
    value, so two separate `FleetSharingWorker` instances sharing one store
    can simulate "the same device session, before and after a Wingman
    restart" without touching a real filesystem.
    """

    def __init__(self, state):
        self._state = state

    def load(self):
        return self._state

    def save(self, state):
        self._state = state


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


class TestSessionRenewal:
    def test_no_renewal_on_the_very_first_pass_of_a_freshly_observed_session(self):
        """Unlike the catalogue (which genuinely has no in-memory data at
        all until the first fetch), a freshly observed session's renewal
        baseline is set to "just observed" -- see `_begin_session`'s own
        comment -- so first contact must not cost an unconditional extra
        network call."""
        client = FakeRelayClient()
        worker = _worker(client)

        worker.iterate_once()

        assert client.renew_calls == []

    def test_session_is_renewed_on_its_own_cadence_independent_of_the_shorter_catalogue_refresh(
        self,
    ):
        client = FakeRelayClient()
        mono = [1000.0]
        worker = _worker(client, clock=lambda: mono[0])

        worker.iterate_once()  # session begins; catalogue fetched (rev 1)
        assert client.renew_calls == []

        # Short of the renewal interval, but past the (much shorter)
        # catalogue interval -- catalogue refreshes on its own cadence,
        # renewal must not fire early just because catalogue did.
        mono[0] += SESSION_RENEWAL_INTERVAL_S - 10
        worker.iterate_once()
        assert client.renew_calls == []
        assert client.fetch_calls == [1, 2]

        # Past the renewal interval (measured from session start, NOT from
        # catalogue's own, more-recently-reset timestamp) -- renewal fires
        # even though catalogue was JUST refreshed and is not yet due again.
        mono[0] += 11
        worker.iterate_once()

        assert client.renew_calls == [3]
        assert client.fetch_calls == [1, 2]  # unchanged: catalogue was not due

    def test_a_successful_renewal_counts_as_real_relay_contact_for_the_active_status(
        self,
    ):
        client = FakeRelayClient()
        mono = [1000.0]
        worker = _worker(client, clock=lambda: mono[0])
        worker.iterate_once()
        worker._set_status(SharingStatus(state="verifying"))

        mono[0] += SESSION_RENEWAL_INTERVAL_S
        worker.iterate_once()

        assert worker.status().state == "active"

    def test_a_failed_renewal_aborts_the_pass_before_catalogue_refresh_or_publish_are_attempted(
        self,
    ):
        """The concrete enforcement of "never two fleet-v1 signed requests
        for this device in flight at once" (docs/fleet-protocol.md, authGD
        repo): a failed renewal must not let this SAME pass go on to also
        attempt a catalogue refresh or a publish -- the next pass, one at
        a time, is the only thing allowed to try again."""
        client = FakeRelayClient()
        client.renew_error = FleetRelayError(500, "server_error", "boom")
        mono = [1000.0]
        worker = _worker(client, clock=lambda: mono[0])
        worker.iterate_once()  # session begins; catalogue fetched (rev 1)

        mono[0] += SESSION_RENEWAL_INTERVAL_S
        worker.submit(_snapshot(42))  # would otherwise also publish this pass
        worker.iterate_once()

        assert client.renew_calls == [2]
        assert client.fetch_calls == [1]  # unattempted: aborted before it
        assert client.publish_calls == []  # unattempted: aborted before it
        assert worker.status() == SharingStatus(state="error", detail="server_error")

    def test_renewal_consumes_a_revision_from_the_same_shared_sequence_as_catalogue_and_publish(
        self,
    ):
        client = FakeRelayClient()
        mono = [1000.0]
        worker = _worker(client, clock=lambda: mono[0])
        worker.iterate_once()  # rev 1: catalogue

        mono[0] += SESSION_RENEWAL_INTERVAL_S
        worker.submit(_snapshot(42))
        worker.iterate_once()

        # Renewal (checked first), then catalogue refresh (also due), then
        # publish -- three signed requests in one pass, one shared,
        # strictly increasing sequence across all of them.
        assert client.renew_calls == [2]
        assert client.fetch_calls == [1, 3]
        assert client.publish_calls[-1][0] == 4


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


class TestSharingEnabledGating:
    """fleet_sharing.enabled gates real work; unpaired gets the same slow,
    non-interruptible poll for the same reason -- see INERT_POLL_S."""

    def test_disabled_worker_never_calls_load_state(self):
        load_calls = []

        def load_state():
            load_calls.append(1)
            return PAIRED_STATE

        worker = FleetSharingWorker(
            load_state=load_state,
            client_factory=lambda origin: FakeRelayClient(),
            unwrap_private_key=_unwrap,
            sharing_enabled=lambda: False,
            _thread_factory=_noop_thread_factory,
            _clock=lambda: 1000.0,
            _jitter=lambda: 0.0,
        )

        worker.iterate_once()

        assert load_calls == []
        assert worker.status() == SharingStatus(state="stopped")

    def test_disabled_worker_reports_the_slow_non_interruptible_inert_poll(self):
        worker = _worker(FakeRelayClient(), sharing_enabled=lambda: False)

        wait_s, interruptible = worker._iterate()

        assert wait_s == INERT_POLL_S
        assert interruptible is False

    def test_unpaired_worker_reports_the_same_slow_inert_poll(self):
        worker = _worker(FakeRelayClient(), state=SharingState())

        wait_s, interruptible = worker._iterate()

        assert wait_s == INERT_POLL_S
        assert interruptible is False

    def test_a_raising_sharing_enabled_predicate_fails_closed_to_stopped(self):
        def broken():
            raise RuntimeError("settings unavailable")

        worker = _worker(FakeRelayClient(), sharing_enabled=broken)

        worker.iterate_once()

        assert worker.status() == SharingStatus(state="stopped")


class TestSnapshotStaleness:
    def test_a_snapshot_older_than_the_max_age_is_dropped_not_published(self):
        client = FakeRelayClient()
        mono = [1000.0]
        worker = _worker(client, clock=lambda: mono[0])
        worker.submit(_snapshot(42))

        mono[0] += MAX_SNAPSHOT_AGE_S + 0.01
        worker.iterate_once()

        assert client.publish_calls == []

    def test_a_snapshot_within_the_max_age_still_publishes(self):
        client = FakeRelayClient()
        mono = [1000.0]
        worker = _worker(client, clock=lambda: mono[0])
        worker.submit(_snapshot(42))

        mono[0] += MAX_SNAPSHOT_AGE_S - 0.01
        worker.iterate_once()

        assert len(client.publish_calls) == 1

    def test_a_dropped_stale_snapshot_does_not_force_a_withdrawal(self):
        client = FakeRelayClient()
        mono = [1000.0]
        worker = _worker(client, clock=lambda: mono[0])
        worker.submit(_snapshot(42))
        worker.iterate_once()
        assert client.publish_calls[-1][1] != ()
        published_so_far = len(client.publish_calls)

        mono[0] += MAX_SNAPSHOT_AGE_S + 0.01
        worker.iterate_once()

        # Neither a stale re-publish NOR a forced empty withdrawal happens.
        assert len(client.publish_calls) == published_so_far


class TestClientConstructionGuard:
    def test_a_client_factory_that_raises_reports_error_without_crashing(self):
        def bad_factory(origin):
            raise ValueError("not a bare https origin")

        worker = _worker(FakeRelayClient(), thread_factory=_noop_thread_factory)
        worker._client_factory = bad_factory

        worker.iterate_once()  # must not raise

        assert worker.status() == SharingStatus(
            state="error", detail="invalid relay origin"
        )

    def test_the_worker_recovers_once_the_client_factory_stops_raising(self):
        good_client = FakeRelayClient()
        calls = {"n": 0}

        def flaky_factory(origin):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ValueError("not a bare https origin")
            return good_client

        worker = _worker(good_client, thread_factory=_noop_thread_factory)
        worker._client_factory = flaky_factory

        worker.iterate_once()
        assert worker.status().state == "error"

        worker.iterate_once()
        assert worker.status().state == "active"
        assert good_client.fetch_calls == [1]

    def test_an_unexpected_exception_anywhere_in_a_pass_is_caught_not_fatal(self):
        """A general safety net beyond the specific client-construction
        guard above: ANY unexpected exception during a pass -- here, a
        persisted identity object missing the attribute this worker
        reads -- must report `error` and back off, never kill the worker's
        own thread."""

        class _BrokenIdentity:
            pass  # deliberately has no protected_private_key_b64 attribute

        broken_state = SharingState(
            identity=_BrokenIdentity(),  # type: ignore[arg-type]
            relay_origin="https://relay.test",
            session_id="session-1",
        )
        worker = _worker(FakeRelayClient(), state=broken_state)

        worker.iterate_once()  # must not raise AttributeError

        assert worker.status().state == "error"


class TestHeartbeat:
    def test_an_unchanged_nonempty_projection_is_republished_as_a_heartbeat(self):
        client = FakeRelayClient()
        mono = [1000.0]
        worker = _worker(client, clock=lambda: mono[0])
        worker.submit(_snapshot(42))
        worker.iterate_once()
        assert len(client.publish_calls) == 1

        mono[0] += HEARTBEAT_INTERVAL_S
        worker.submit(_snapshot(42))  # unchanged content, a fresh submission
        worker.iterate_once()

        assert len(client.publish_calls) == 2
        assert client.publish_calls[-1][1] == (PublishRow(1, 42, ()),)

    def test_an_unchanged_projection_is_not_republished_before_the_interval(self):
        client = FakeRelayClient()
        mono = [1000.0]
        worker = _worker(client, clock=lambda: mono[0])
        worker.submit(_snapshot(42))
        worker.iterate_once()
        assert len(client.publish_calls) == 1

        mono[0] += HEARTBEAT_INTERVAL_S - 0.5
        worker.submit(_snapshot(42))
        worker.iterate_once()

        assert len(client.publish_calls) == 1

    def test_an_empty_projection_never_needs_a_heartbeat(self):
        client = FakeRelayClient()
        mono = [1000.0]
        worker = _worker(client, clock=lambda: mono[0])
        worker.submit(_snapshot(42, character="Nobody"))  # never matches
        worker.iterate_once()
        assert client.publish_calls == []

        mono[0] += HEARTBEAT_INTERVAL_S * 5
        worker.submit(_snapshot(42, character="Nobody"))
        worker.iterate_once()

        assert client.publish_calls == []


class TestRevisionPersistence:
    def test_revision_resumes_from_the_persisted_value_across_a_restart(self):
        store = _InMemoryStateStore(PAIRED_STATE)
        client_a = FakeRelayClient()
        worker_a = FleetSharingWorker(
            load_state=store.load,
            save_state=store.save,
            client_factory=lambda origin: client_a,
            unwrap_private_key=_unwrap,
            _thread_factory=_noop_thread_factory,
            _clock=lambda: 1000.0,
            _jitter=lambda: 0.0,
        )
        worker_a.submit(_snapshot(42))
        worker_a.iterate_once()  # revision 1: fetch_catalogue; 2: publish
        assert store.load().last_revision == 2

        # A fresh worker instance, same session id, same persisted store --
        # simulating a Wingman restart with a still-valid device session.
        client_b = FakeRelayClient()
        worker_b = FleetSharingWorker(
            load_state=store.load,
            save_state=store.save,
            client_factory=lambda origin: client_b,
            unwrap_private_key=_unwrap,
            _thread_factory=_noop_thread_factory,
            _clock=lambda: 1000.0,
            _jitter=lambda: 0.0,
        )
        worker_b.submit(_snapshot(42))
        worker_b.iterate_once()

        # Must NOT restart at revision 1/2 -- authGD already saw those.
        assert client_b.fetch_calls == [3]
        assert client_b.publish_calls[0][0] == 4
        assert store.load().last_revision == 4

    def test_revision_restarts_at_zero_when_the_session_id_genuinely_changes(self):
        store = _InMemoryStateStore(PAIRED_STATE)
        client = FakeRelayClient()
        worker = FleetSharingWorker(
            load_state=store.load,
            save_state=store.save,
            client_factory=lambda origin: client,
            unwrap_private_key=_unwrap,
            _thread_factory=_noop_thread_factory,
            _clock=lambda: 1000.0,
            _jitter=lambda: 0.0,
        )
        worker.submit(_snapshot(42))
        worker.iterate_once()
        assert client.fetch_calls == [1]

        # A genuinely new pairing while THIS worker instance keeps running --
        # a different session id must start its own revision sequence.
        current = store.load()
        store.save(
            SharingState(
                identity=current.identity,
                relay_origin=current.relay_origin,
                session_id="session-2",
                last_revision=current.last_revision,
            )
        )
        client.fetch_calls.clear()
        worker.submit(_snapshot(42))
        worker.iterate_once()

        assert client.fetch_calls == [1]  # revision 1 again, not 3

    def test_a_failing_save_state_aborts_the_pass_without_crashing(self):
        def raising_save(_state):
            raise OSError("disk full")

        client = FakeRelayClient()
        worker = _worker(client, save_state=raising_save)

        worker.iterate_once()

        assert client.fetch_calls == []
        assert worker.status().state == "error"


class TestActiveStatusRequiresContact:
    def test_a_pass_with_nothing_due_does_not_reassign_status(self):
        client = FakeRelayClient()
        mono = [1000.0]
        worker = _worker(client, clock=lambda: mono[0])

        worker.iterate_once()  # mandatory first catalogue fetch: real contact
        assert worker.status().state == "active"

        # Simulate an externally observed non-active status -- proves the
        # NEXT no-op pass (catalogue still fresh, nothing submitted) does
        # not blindly reassert "active" over it.
        worker._set_status(SharingStatus(state="verifying"))

        worker.iterate_once()

        assert worker.status() == SharingStatus(state="verifying")

    def test_active_is_reasserted_only_immediately_after_real_contact(self):
        client = FakeRelayClient()
        mono = [1000.0]
        worker = _worker(client, clock=lambda: mono[0])
        worker.iterate_once()
        assert worker.status().state == "active"

        worker._set_status(SharingStatus(state="verifying"))
        worker.submit(_snapshot(42))  # forces a real publish this pass
        worker.iterate_once()

        assert worker.status().state == "active"


# ---------------------------------------------------------------------------
# Real-thread concurrency proofs
# ---------------------------------------------------------------------------


class TestDeadlineBasedBackoff:
    """Real threads, real time.monotonic -- proves a steady flood of
    submit() calls during backoff cannot collapse the backoff wait to
    zero, only a genuinely elapsed deadline (or stop()) ends it."""

    def test_a_steady_stream_of_submits_does_not_shorten_the_backoff_wait(self):
        class FailOnceRelayClient:
            def __init__(self, catalogue=CATALOGUE):
                self.catalogue = catalogue
                self.publish_calls: list[float] = []

            def fetch_catalogue(self, *, session_id, private_key, revision):
                return self.catalogue

            def publish_snapshot(self, *, session_id, private_key, revision, rows):
                self.publish_calls.append(time.monotonic())
                if len(self.publish_calls) == 1:
                    raise FleetRelayError(500, "server_error", "boom")

        client = FailOnceRelayClient()
        worker = FleetSharingWorker(
            load_state=lambda: PAIRED_STATE,
            client_factory=lambda origin: client,
            unwrap_private_key=_unwrap,
        )
        assert worker.start()
        try:
            worker.submit(_snapshot(10))
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and len(client.publish_calls) < 1:
                time.sleep(0.01)
            assert len(client.publish_calls) == 1, "first (failing) attempt never ran"
            first_attempt = client.publish_calls[0]

            # Flood submit() well inside the backoff window (BASE_BACKOFF_S
            # is 1.0s): an interruptible wait would let these wake the loop
            # and retry almost immediately.
            flood_until = time.monotonic() + 0.5
            while time.monotonic() < flood_until:
                worker.submit(_snapshot(11))
                time.sleep(0.01)

            assert len(client.publish_calls) == 1, (
                "backoff was not honoured -- a flood of submit() calls "
                "triggered an early retry"
            )

            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and len(client.publish_calls) < 2:
                time.sleep(0.01)
            assert len(client.publish_calls) == 2
            assert client.publish_calls[1] - first_attempt >= BASE_BACKOFF_S * 0.9
        finally:
            worker.stop(timeout=5)


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
        from wingman.telemetry.model import RosterSnapshot

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

            def snapshot(self):
                # Enabling Fleet primes from this synchronously (see
                # coordinator._reset_fleet_state). A non-zero generation is
                # what tells the coordinator a real scan has already
                # completed, which is what unblocks _publish() from
                # withholding snapshots as a pre-roster synthetic state.
                return RosterSnapshot(generation=1, clients=())

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
