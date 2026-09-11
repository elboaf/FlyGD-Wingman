"""Real owners/conditions with manual monotonic time and explicit I/O barriers."""

import json
import queue
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from wingman.telemetry.model import ClientSessionId
from wingman.wanderer.client import Failure, Success, Unchanged
from wingman.wanderer.model import parse_snapshot

BODY = (Path(__file__).parent / "fixtures/wanderer/deployed-v1.json").read_bytes()
ETAG = 'W/"fixture-revision"'
FIRST = ClientSessionId(101, 201, "First Pilot", 1)
HIDDEN = ClientSessionId(102, 202, "Hidden Pilot", 1)


def success(receipt=100, *, rows=None, revision="fixture-revision"):
    data = json.loads(BODY)
    if rows is not None:
        data["data"] = rows
    data["revision"] = revision
    return Success(
        parse_snapshot(json.dumps(data).encode(), receipt), f'W/"{revision}"'
    )


class Clock:
    now = 100.0

    def __call__(self):
        return self.now


class ObservedCondition(threading.Condition):
    """Observe owner re-parking, not time passing, to prove negative assertions."""

    def __init__(self):
        super().__init__()
        self.observed = threading.Condition()
        self.waits = {}

    def wait(self, timeout=None):
        name = threading.current_thread().name
        if name.startswith("wanderer-"):
            with self.observed:
                self.waits[name] = self.waits.get(name, 0) + 1
                self.observed.notify_all()
        return super().wait(timeout)

    def counts(self):
        with self.observed:
            return dict(self.waits)

    def reparks(self, before, names):
        with self.observed:
            assert self.observed.wait_for(
                lambda: all(self.waits.get(n, 0) > before.get(n, 0) for n in names), 2
            ), (before, self.waits)


class Call:
    def __init__(self, args):
        self.args = args
        self.replies = queue.Queue()

    def reply(self, result):
        self.replies.put(result)


class Client:
    def __init__(self):
        self.calls = []
        self.cv = threading.Condition()
        self.active = 0
        self.maximum_active = 0

    def fetch(self, *args):
        with self.cv:
            call = Call(args)
            self.calls.append(call)
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
            self.cv.notify_all()
        try:
            result = call.replies.get(timeout=5)
            if isinstance(result, Exception):
                raise result
            return result
        finally:
            with self.cv:
                self.active -= 1
                self.cv.notify_all()

    def call(self, number):
        with self.cv:
            assert self.cv.wait_for(lambda: len(self.calls) >= number, 2)
            return self.calls[number - 1]


class Mailbox:
    def __init__(self):
        self.cv = threading.Condition()
        self.deliveries = []
        self.current = {}

    def publish(self, generation, updates):
        with self.cv:
            self.deliveries.append((generation, dict(updates)))
            self.current.update(updates)
            self.cv.notify_all()

    def expect(self, values):
        with self.cv:
            assert self.cv.wait_for(
                lambda: all(
                    k in self.current and self.current[k] == v
                    for k, v in values.items()
                ),
                2,
            ), self.deliveries


class Rig:
    def __init__(self, **kwargs):
        from wingman.wanderer.worker import WandererWorker, WorkerConfig

        self.clock = Clock()
        self.cv = ObservedCondition()
        self.client = Client()
        self.mailbox = Mailbox()
        self.worker = WandererWorker(
            self.client,
            kwargs.pop("publish", self.mailbox.publish),
            clock=self.clock,
            condition=self.cv,
            **kwargs,
        )
        self.config = WorkerConfig(
            enabled=True,
            previews_enabled=True,
            host_available=True,
            base_url="https://wanderer.example/prefix",
            map_identifier="map",
            token="private-token",
        )

    def configure(self, generation=1, **changes):
        self.config = replace(self.config, **changes)
        return self.worker.configure(self.config, generation=generation)

    def wait(self, predicate):
        with self.cv:
            assert self.cv.wait_for(lambda: predicate(self.worker.state()), 2), (
                self.worker.state()
            )
        return self.worker.state()

    def advance(self, now, *, owners=("wanderer-expiry",)):
        with self.cv:
            before = self.cv.counts()
            self.clock.now = now
            self.cv.notify_all()
        self.cv.reparks(before, owners)

    def close(self):
        self.worker.close_admission()
        with self.client.cv:
            for call in self.client.calls:
                call.reply(Failure("transport_error"))
        assert self.worker.stop(2)


@pytest.fixture
def rig():
    value = Rig()
    try:
        yield value
    finally:
        value.close()


def start_snapshot(rig):
    rig.worker.set_sessions((FIRST, HIDDEN))
    assert rig.configure()
    call = rig.client.call(1)
    assert call.args == (
        "https://wanderer.example/prefix",
        "map",
        "private-token",
        None,
    )
    call.reply(success())
    rig.mailbox.expect({FIRST: "HOME", HIDDEN: "Amarr"})
    rig.wait(lambda s: s.status == "connected" and not s.in_flight)


def test_200_replaces_instead_of_merging_and_304_preserves_exact_deadlines(rig):
    start_snapshot(rig)
    rig.advance(102)
    call = rig.client.call(2)
    assert call.args[3] == ETAG
    call.reply(Unchanged(ETAG))
    state = rig.wait(lambda s: s.last_success_monotonic == 102)
    assert (state.previewed, state.matched, state.available) == (2, 2, 2)
    rig.advance(104)
    call = rig.client.call(3)
    row = json.loads(BODY)["data"][0]
    row["display_name"] = "NEW"
    call.reply(success(104, rows=[row], revision="new"))
    rig.mailbox.expect({FIRST: "NEW", HIDDEN: None})
    rig.wait(lambda s: s.matched == 1)


def test_expiry_runs_while_next_http_request_is_blocked(rig):
    start_snapshot(rig)
    rig.advance(102)
    call = rig.client.call(2)
    rig.advance(113.999)
    assert rig.mailbox.current[FIRST] == "HOME"
    rig.advance(114)
    rig.mailbox.expect({FIRST: None, HIDDEN: None})
    state = rig.worker.state()
    assert state.in_flight and state.status == "stale"
    assert state.stale == 2 and state.available == 0
    call.reply(Unchanged(ETAG))
    rig.wait(lambda s: s.last_success_monotonic == 114)
    assert rig.mailbox.current[FIRST] is None


@pytest.mark.parametrize(
    "error", [Failure("transport_error"), Failure("rate_limited", 429, 60)]
)
def test_expiry_is_independent_of_backoff_and_retry_after(rig, error):
    start_snapshot(rig)
    rig.advance(102)
    rig.client.call(2).reply(error)
    rig.wait(lambda s: s.error_code == error.code and not s.in_flight)
    rig.advance(114)
    rig.mailbox.expect({FIRST: None, HIDDEN: None})
    if error.retry_after:
        assert len(rig.client.calls) == 2
        assert rig.worker.state().next_request_monotonic == 162


@pytest.mark.parametrize(
    "status,code", [(401, "invalid_token"), (403, "wrong_map"), (403, "disabled")]
)
def test_auth_clears_immediately_pauses_and_test_explicitly_recovers(rig, status, code):
    start_snapshot(rig)
    rig.advance(102)
    rig.client.call(2).reply(Failure(code, status))
    rig.wait(lambda s: s.paused and s.error_code == code)
    rig.mailbox.expect({FIRST: None, HIDDEN: None})
    assert rig.clock.now == 102  # Not the original 114 deadline.
    rig.advance(200, owners=("wanderer-expiry", "wanderer-http"))
    assert len(rig.client.calls) == 2
    assert rig.worker.test_connection()
    call = rig.client.call(3)
    assert call.args[3] is None
    call.reply(success(200))
    rig.wait(lambda s: not s.paused and s.test_result == "success")
    rig.mailbox.expect({FIRST: "HOME", HIDDEN: "Amarr"})


def test_auth_pause_survives_readiness_toggles_until_credential_change(rig):
    start_snapshot(rig)
    rig.advance(102)
    rig.client.call(2).reply(Failure("invalid_token", 401))
    rig.wait(lambda s: s.paused)
    assert rig.configure(2, host_available=False)
    assert rig.configure(3, host_available=True)
    rig.advance(200, owners=("wanderer-expiry", "wanderer-http"))
    assert rig.worker.state().paused
    assert len(rig.client.calls) == 2
    assert rig.configure(4, token="replacement-token")
    rig.client.call(3).reply(success(200))
    rig.mailbox.expect({FIRST: "HOME"})
    assert not rig.worker.state().paused


def test_304_without_prior_snapshot_is_rejected_and_not_successful(rig):
    assert rig.configure()
    rig.client.call(1).reply(Unchanged(ETAG))
    state = rig.wait(lambda s: s.error_code == "invalid_response")
    assert state.last_success_monotonic is None
    assert state.available == 0


def test_wrong_304_etag_is_rejected_without_renewal(rig):
    start_snapshot(rig)
    rig.advance(102)
    rig.client.call(2).reply(Unchanged('W/"different"'))
    rig.wait(lambda s: s.error_code == "invalid_response")
    assert rig.worker.state().last_success_monotonic == 100
    rig.advance(114)
    rig.mailbox.expect({FIRST: None, HIDDEN: None})


def test_off_test_is_one_shot_not_enable_and_shares_cadence(rig):
    rig.worker.set_sessions((FIRST,))
    assert rig.configure(enabled=False)
    assert not rig.client.calls
    assert rig.worker.test_connection()
    assert not rig.worker.test_connection()  # At most one explicit ticket.
    rig.client.call(1).reply(success())
    state = rig.wait(lambda s: s.test_result == "success" and not s.in_flight)
    assert not state.enabled and not state.automatic_ready
    assert rig.mailbox.current.get(FIRST) is None
    rig.advance(200, owners=("wanderer-expiry", "wanderer-http"))
    assert len(rig.client.calls) == 1
    assert rig.worker.test_connection()
    rig.client.call(2).reply(Failure("rate_limited", 429, 60))
    rig.wait(lambda s: s.test_result == "rate_limited" and not s.in_flight)
    assert rig.worker.test_connection()
    rig.advance(259, owners=("wanderer-expiry", "wanderer-http"))
    assert len(rig.client.calls) == 2
    rig.advance(260)
    rig.client.call(3).reply(success(260))
    rig.wait(lambda s: s.test_result == "success" and not s.in_flight)
    assert rig.client.maximum_active == 1


def test_test_queues_behind_poll_on_same_lane_and_cannot_bypass_rate_limit(rig):
    start_snapshot(rig)
    rig.advance(102)
    call = rig.client.call(2)
    assert rig.worker.test_connection()
    assert not rig.worker.test_connection()
    assert len(rig.client.calls) == 2
    call.reply(Failure("rate_limited", 429, 60))
    rig.wait(lambda s: not s.in_flight and s.test_pending)
    rig.advance(161.999, owners=("wanderer-expiry", "wanderer-http"))
    assert len(rig.client.calls) == 2
    rig.advance(162)
    rig.client.call(3).reply(success(162))
    rig.wait(lambda s: s.test_result == "success")
    assert rig.client.maximum_active == 1


@pytest.mark.parametrize("late", [success(), Failure("invalid_token", 401)])
def test_configuration_fences_inflight_success_and_auth_and_cancels_old_test(rig, late):
    start_snapshot(rig)
    rig.advance(102)
    call = rig.client.call(2)
    assert rig.worker.test_connection()
    assert rig.configure(2, map_identifier="new-map", token="new-private-token")
    assert rig.worker.state().generation == 2
    rig.mailbox.expect({FIRST: None, HIDDEN: None})
    call.reply(late)
    rig.wait(lambda s: not s.in_flight)
    assert rig.worker.state().test_result is None
    assert not rig.worker.state().paused
    assert rig.worker.state().available == 0
    rig.advance(104)
    call = rig.client.call(3)
    assert call.args == (
        "https://wanderer.example/prefix",
        "new-map",
        "new-private-token",
        None,
    )
    call.reply(success(104))
    rig.mailbox.expect({FIRST: "HOME"})
    assert rig.mailbox.deliveries[-1][0] == 2
    assert not rig.worker.configure(rig.config, generation=1)
    assert "private-token" not in repr(rig.config) + repr(rig.worker.state())


@pytest.mark.parametrize(
    "changes",
    [
        {"enabled": False},
        {"previews_enabled": False},
        {"host_available": False},
        {"token": None},
        {"base_url": ""},
        {"map_identifier": ""},
    ],
)
def test_readiness_gates_auto_and_disable_clears_cached_metadata(rig, changes):
    start_snapshot(rig)
    assert rig.configure(2, **changes)
    rig.mailbox.expect({FIRST: None, HIDDEN: None})
    assert not rig.worker.state().automatic_ready
    rig.advance(200, owners=("wanderer-expiry", "wanderer-http"))
    assert len(rig.client.calls) == 1
    if any(k in changes for k in ("token", "base_url", "map_identifier")):
        assert not rig.worker.test_connection()


def test_current_session_projection_has_no_recent_name_cap_and_no_departed_keys(rig):
    start_snapshot(rig)
    replacement = ClientSessionId(FIRST.hwnd, FIRST.pid, FIRST.character, 2)
    sessions = [replacement] + [
        ClientSessionId(1000 + n, 2000 + n, "Hidden Pilot", n) for n in range(90)
    ]
    baseline = len(rig.mailbox.deliveries)
    rig.worker.set_sessions(sessions)
    sessions.clear()  # Input ownership is detached before the callback returns.
    rig.mailbox.expect({replacement: "HOME"})
    rig.wait(lambda s: s.previewed == 91 and s.available == 91)
    deliveries = rig.mailbox.deliveries[baseline:]
    assert all(
        FIRST not in updates and HIDDEN not in updates for _, updates in deliveries
    )
    assert len(deliveries[-1][1]) == 91
    rig.worker.set_sessions(())
    rig.wait(lambda s: s.previewed == 0)
    rig.advance(114)
    assert rig.worker.state().matched == 0


def test_backoff_is_bounded_and_success_resets_failure_sequence(rig):
    assert rig.configure()
    now = 100
    for number, delay in enumerate((4, 8, 16, 32, 60, 60), 1):
        rig.client.call(number).reply(Failure("transport_error"))
        state = rig.wait(
            lambda s: not s.in_flight and s.next_request_monotonic == now + delay
        )
        assert state.error_code == "transport_error"
        rig.advance(now + delay - 0.001, owners=("wanderer-expiry", "wanderer-http"))
        assert len(rig.client.calls) == number
        now += delay
        rig.advance(now)
    rig.client.call(7).reply(success(now))
    rig.wait(lambda s: not s.in_flight and s.next_request_monotonic == now + 2)
    rig.advance(now + 2)
    rig.client.call(8).reply(Failure("transport_error"))
    rig.wait(lambda s: not s.in_flight and s.next_request_monotonic == now + 6)


def test_shutdown_closes_admission_retains_http_owner_and_never_replaces_it(rig):
    start_snapshot(rig)
    rig.advance(102)
    call = rig.client.call(2)
    http_owner = rig.worker._request_thread
    expiry_owner = rig.worker._scheduler_thread
    rig.worker.close_admission()
    assert not rig.worker.stop(0)
    assert rig.worker._request_thread is http_owner
    assert rig.worker._scheduler_thread is expiry_owner
    assert not rig.configure(2)
    assert not rig.worker.test_connection()
    rig.worker.set_sessions((FIRST,))
    assert rig.worker.state().status == "stopped"
    baseline = len(rig.mailbox.deliveries)
    call.reply(success(102))
    assert rig.worker.stop(2)
    assert len(rig.mailbox.deliveries) == baseline
    assert rig.worker.state().previewed == 0


def test_shutdown_does_not_join_stalled_publication_under_state_lock():
    entered, release = threading.Event(), threading.Event()

    def mailbox(_generation, _updates):
        entered.set()
        assert release.wait(3)

    rig = Rig(publish=mailbox)
    try:
        rig.worker.set_sessions((FIRST,))
        assert rig.configure()
        assert entered.wait(2)
        request_owner = rig.worker._request_thread
        scheduler_owner = rig.worker._scheduler_thread
        rig.worker.close_admission()  # Must not acquire a lock held by publication.
        assert not rig.worker.stop(0)
        assert not rig.configure(2)
        assert rig.worker._request_thread is request_owner
        assert rig.worker._scheduler_thread is scheduler_owner
        assert rig.worker.state().status == "stopped"
    finally:
        release.set()
        rig.close()


def test_nearest_deadline_clears_only_due_sessions_while_http_stalls(rig):
    rig.worker.set_sessions((FIRST, HIDDEN))
    assert rig.configure()
    data = json.loads(BODY)
    data["data"][1]["location_observed_at"] = "2026-09-10T19:59:57Z"
    rig.client.call(1).reply(
        Success(parse_snapshot(json.dumps(data).encode(), 100), ETAG)
    )
    rig.mailbox.expect({FIRST: "HOME", HIDDEN: "Amarr"})
    rig.advance(102)
    rig.client.call(2)
    rig.advance(111)
    rig.mailbox.expect({FIRST: "HOME", HIDDEN: None})
    assert rig.worker.state().available == rig.worker.state().stale == 1
    rig.advance(114)
    rig.mailbox.expect({FIRST: None, HIDDEN: None})


def test_successful_empty_snapshot_clears_all_without_reporting_transport_failure(rig):
    start_snapshot(rig)
    rig.advance(102)
    rig.client.call(2).reply(success(102, rows=[], revision="empty"))
    rig.mailbox.expect({FIRST: None, HIDDEN: None})
    state = rig.worker.state()
    assert state.status == "connected"
    assert state.matched == state.available == state.stale == 0
    assert state.error_code is None


def test_same_generation_repetition_is_noop_but_changed_config_is_rejected(rig):
    start_snapshot(rig)
    assert rig.worker.configure(rig.config, generation=1)
    assert not rig.worker.configure(
        replace(rig.config, map_identifier="other"), generation=1
    )
    rig.advance(101, owners=("wanderer-expiry", "wanderer-http"))
    assert rig.mailbox.current[FIRST] == "HOME"
    assert len(rig.client.calls) == 1
    rig.advance(102)
    rig.client.call(2).reply(Unchanged(ETAG))
    rig.wait(lambda s: s.last_success_monotonic == 102)
    rig.advance(103, owners=("wanderer-expiry", "wanderer-http"))
    assert (
        sum(
            FIRST in updates and updates[FIRST] == "HOME"
            for _, updates in rig.mailbox.deliveries
        )
        == 1
    )


def test_partial_thread_start_failure_is_safe_retained_and_not_retried(caplog):
    created = []

    class Thread(threading.Thread):
        def start(self):
            if self.name == "wanderer-http":
                raise RuntimeError("private-token")
            super().start()

    def factory(**kwargs):
        owner = Thread(**kwargs)
        created.append(owner)
        return owner

    rig = Rig(thread_factory=factory)
    try:
        assert not rig.configure()
        assert rig.worker.state().status == "worker_failed"
        assert not rig.configure(2)
        assert not rig.worker.test_connection()
        assert len(created) == 2
        assert rig.worker._scheduler_thread is created[0]
        assert rig.worker._request_thread is created[1]
        assert "private-token" not in repr(rig.worker.state()) + caplog.text
    finally:
        rig.close()


def test_mailbox_failure_closes_admission_without_raw_exception_leak(caplog):
    def failed(_generation, _updates):
        raise RuntimeError("private-token")

    rig = Rig(publish=failed)
    try:
        rig.worker.set_sessions((FIRST,))
        assert rig.configure()
        rig.wait(lambda s: s.status == "worker_failed")
        assert not rig.worker.test_connection()
        assert "private-token" not in repr(rig.worker.state()) + caplog.text
    finally:
        rig.close()


def test_unexpected_transport_exception_is_safe_and_does_not_kill_expiry(rig, caplog):
    start_snapshot(rig)
    rig.advance(102)
    rig.client.call(2).reply(RuntimeError("private-token"))
    rig.wait(lambda s: s.error_code == "transport_error")
    rig.advance(114)
    rig.mailbox.expect({FIRST: None})
    assert "private-token" not in repr(rig.worker.state()) + caplog.text
