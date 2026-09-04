"""Shared EVE client discovery -- tests.

Most tests use ``_noop_thread_factory`` so ``start()`` sets up state without
spawning a real thread, and ``scan_once()`` drives scans synchronously.  Only
``TestWorker`` uses real threads.
"""

import threading
import time

from wingman.preview import discovery
from wingman.preview.discovery import Client, EnumerationResult
from wingman.telemetry.clients import ClientDiscovery, _noop_thread_factory
from wingman.telemetry.model import RosterClient, RosterSnapshot

ALICE = Client(
    hwnd=0x100, title="EVE - Alice", pid=111, character="Alice", stable_key="Alice"
)
BOB = Client(hwnd=0x200, title="EVE - Bob", pid=222, character="Bob", stable_key="Bob")
GENERIC = Client(
    hwnd=0x100, title="EVE", pid=111, character=None, stable_key="hwnd:0x100"
)

# Sentinel marking a scan that fails outright (the top-level enumerator
# raised), as opposed to a scan that succeeds with zero clients.
FAIL = object()


def _discovery(**kw):
    """ClientDiscovery with a noop thread factory for synchronous tests."""
    kw.setdefault("_thread_factory", _noop_thread_factory)
    return ClientDiscovery(**kw)


def _result_seq(*scans):
    """A callable returning an ``EnumerationResult`` per call, in order,
    then repeating the last entry forever -- so a ``scan_once()`` call past
    the injected sequence does not raise.  Pass ``FAIL`` for a scan whose
    enumerator failed; anything else is treated as the successful client
    list for that scan (including an empty list, a genuine empty scan)."""
    calls = {"n": 0}

    def _enumerate():
        i = min(calls["n"], len(scans) - 1)
        calls["n"] += 1
        entry = scans[i]
        if entry is FAIL:
            return EnumerationResult(False, [])
        return EnumerationResult(True, list(entry))

    return _enumerate


def _collect(disco):
    received = []
    disco.subscribe(lambda snapshot: received.append(snapshot))
    return received


def _sessions(snapshot: RosterSnapshot):
    return {c.character: c.session for c in snapshot.clients if c.character}


# ---------------------------------------------------------------------------
# Stable session identity
# ---------------------------------------------------------------------------


class TestStableSessions:
    def test_unchanged_tuple_keeps_first_seen_generation(self):
        disco = _discovery(_enumerate_clients=_result_seq([ALICE], [ALICE], [ALICE]))
        received = _collect(disco)
        disco.scan_once()
        disco.scan_once()
        disco.scan_once()
        first_seen = [_sessions(s)["Alice"].first_seen_generation for s in received]
        assert first_seen[0] == first_seen[1] == first_seen[2]

    def test_disappearance_then_return_gets_new_session(self):
        disco = _discovery(_enumerate_clients=_result_seq([ALICE], [], [ALICE]))
        received = _collect(disco)
        disco.scan_once()
        first = _sessions(received[0])["Alice"].first_seen_generation
        disco.scan_once()  # genuinely empty: Alice absent
        disco.scan_once()  # Alice returns
        second = _sessions(received[2])["Alice"].first_seen_generation
        assert second != first
        assert second == received[2].generation

    def test_hwnd_change_gets_new_session(self):
        moved = ALICE._replace(hwnd=0x999)
        disco = _discovery(_enumerate_clients=_result_seq([ALICE], [moved]))
        received = _collect(disco)
        disco.scan_once()
        first = _sessions(received[0])["Alice"].first_seen_generation
        disco.scan_once()
        second = _sessions(received[1])["Alice"].first_seen_generation
        assert second != first
        assert second == received[1].generation

    def test_pid_change_gets_new_session(self):
        relaunched = ALICE._replace(pid=999)
        disco = _discovery(_enumerate_clients=_result_seq([ALICE], [relaunched]))
        received = _collect(disco)
        disco.scan_once()
        first = _sessions(received[0])["Alice"].first_seen_generation
        disco.scan_once()
        second = _sessions(received[1])["Alice"].first_seen_generation
        assert second != first

    def test_generic_title_transition_gets_new_session(self):
        # Same hwnd/pid throughout: character selection screen briefly shows
        # a generic title, then the same character logs back in.
        disco = _discovery(_enumerate_clients=_result_seq([ALICE], [GENERIC], [ALICE]))
        received = _collect(disco)
        disco.scan_once()
        first = _sessions(received[0])["Alice"].first_seen_generation
        disco.scan_once()  # generic: no session for this hwnd
        assert _sessions(received[1]).get("Alice") is None
        disco.scan_once()  # same character name returns
        second = _sessions(received[2])["Alice"].first_seen_generation
        assert second != first
        assert second == received[2].generation

    def test_unnamed_client_present_without_session(self):
        disco = _discovery(_enumerate_clients=_result_seq([GENERIC]))
        received = _collect(disco)
        disco.scan_once()
        snapshot = received[0]
        assert len(snapshot.clients) == 1
        client = snapshot.clients[0]
        assert client.character is None
        assert client.session is None
        assert client.hwnd == GENERIC.hwnd
        assert client.pid == GENERIC.pid
        assert client.title == GENERIC.title

    def test_generation_monotonically_increases(self):
        disco = _discovery(_enumerate_clients=_result_seq([ALICE], [ALICE], [ALICE]))
        received = _collect(disco)
        disco.scan_once()
        disco.scan_once()
        disco.scan_once()
        gens = [s.generation for s in received]
        assert gens == sorted(gens)
        assert len(set(gens)) == 3

    def test_two_independent_clients_get_independent_sessions(self):
        disco = _discovery(_enumerate_clients=_result_seq([ALICE, BOB]))
        received = _collect(disco)
        disco.scan_once()
        sessions = _sessions(received[0])
        assert sessions["Alice"] != sessions["Bob"]
        assert sessions["Alice"].character == "Alice"
        assert sessions["Bob"].character == "Bob"

    def test_no_clients_publishes_empty_snapshot(self):
        disco = _discovery(_enumerate_clients=_result_seq([]))
        received = _collect(disco)
        disco.scan_once()
        assert received[0].clients == ()


# ---------------------------------------------------------------------------
# Failure isolation: an enumerator failure must not look like an empty roster
# ---------------------------------------------------------------------------


class TestFailureIsolation:
    def test_failed_scan_publishes_nothing(self):
        disco = _discovery(_enumerate_clients=_result_seq([ALICE], FAIL))
        received = _collect(disco)
        disco.scan_once()
        disco.scan_once()  # fails
        assert len(received) == 1  # the failed scan published no snapshot

    def test_continuously_present_client_keeps_session_across_a_failed_scan(self):
        """RULING: a failed scan must not prune continuity. Alice stays
        present the whole time; a scan in between fails outright (not a
        genuine empty scan) and must not reset her session."""
        disco = _discovery(_enumerate_clients=_result_seq([ALICE], FAIL, [ALICE]))
        received = _collect(disco)
        disco.scan_once()
        first = _sessions(received[0])["Alice"].first_seen_generation
        disco.scan_once()  # fails: publishes nothing, prunes nothing
        disco.scan_once()  # succeeds again: Alice was never pruned
        assert len(received) == 2  # only the two successful scans published
        second = _sessions(received[1])["Alice"].first_seen_generation
        assert second == first

    def test_genuine_empty_scan_between_still_mints_a_new_session(self):
        """Contrast case for the ruling: a *successful* empty scan (as
        opposed to a failed one) is authoritative and does prune -- Alice's
        later return must mint a fresh session."""
        disco = _discovery(_enumerate_clients=_result_seq([ALICE], [], [ALICE]))
        received = _collect(disco)
        disco.scan_once()
        first = _sessions(received[0])["Alice"].first_seen_generation
        disco.scan_once()  # genuinely empty: prunes Alice
        disco.scan_once()  # Alice returns: new session
        assert len(received) == 3  # every scan here succeeded and published
        second = _sessions(received[2])["Alice"].first_seen_generation
        assert second != first
        assert second == received[2].generation

    def test_failed_scan_leaves_the_last_published_snapshot_untouched(self):
        disco = _discovery(_enumerate_clients=_result_seq([ALICE], FAIL))
        disco.scan_once()
        before = disco.snapshot()
        disco.scan_once()  # fails
        assert disco.snapshot() is before

    def test_failed_scan_records_the_error_and_success_clears_it(self):
        disco = _discovery(_enumerate_clients=_result_seq([ALICE], FAIL, [ALICE]))
        disco.scan_once()
        assert disco._last_error is None
        disco.scan_once()  # fails
        assert disco._last_error is not None
        disco.scan_once()  # succeeds again
        assert disco._last_error is None

    def test_enumerator_raising_directly_is_also_a_failed_scan(self):
        """Defense in depth: even if a caller's injected callable raises
        instead of returning EnumerationResult(False, ...), that must be
        treated exactly like a reported failure, not an empty roster."""
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                return EnumerationResult(True, [ALICE])
            raise RuntimeError("enumerator exploded")

        disco = _discovery(_enumerate_clients=flaky)
        received = _collect(disco)
        disco.scan_once()
        first = _sessions(received[0])["Alice"].first_seen_generation
        disco.scan_once()  # raises internally
        assert len(received) == 1  # nothing published for the failed scan
        assert disco._last_error is not None
        calls["n"] = 0  # let the next call succeed again with Alice present

        def recovered():
            return EnumerationResult(True, [ALICE])

        disco._enumerate_clients = recovered
        disco.scan_once()
        second = _sessions(received[1])["Alice"].first_seen_generation
        assert second == first  # never pruned by the failed scan


# ---------------------------------------------------------------------------
# Backward-compatible plain-list enumerator (the brief's original shape)
# ---------------------------------------------------------------------------


class TestPlainListEnumeratorShape:
    """``_enumerate_clients`` must still accept the task brief's original
    ``Callable[[], list[Client]]`` shape -- a bare iterable with no way to
    express failure -- alongside the newer failure-aware
    ``EnumerationResult``. Every such call is treated as successful."""

    def test_list_returning_enumerator_is_a_successful_scan(self):
        def enumerate_clients():
            return [ALICE]

        disco = _discovery(_enumerate_clients=enumerate_clients)
        received = _collect(disco)
        disco.scan_once()
        assert received[0].clients[0].character == "Alice"
        assert _sessions(received[0])["Alice"].first_seen_generation == 1

    def test_tuple_returning_enumerator_is_also_accepted(self):
        def enumerate_clients():
            return (ALICE, BOB)

        disco = _discovery(_enumerate_clients=enumerate_clients)
        received = _collect(disco)
        disco.scan_once()
        assert {c.character for c in received[0].clients} == {"Alice", "Bob"}

    def test_empty_list_from_a_list_returning_enumerator_is_authoritative(self):
        """Unlike EnumerationResult(False, ...), a bare empty list has no
        way to signal failure -- it is a genuine empty scan and prunes
        exactly as the production seam's own empty success does."""
        calls = {"n": 0}

        def enumerate_clients():
            calls["n"] += 1
            return [ALICE] if calls["n"] in (1, 3) else []

        disco = _discovery(_enumerate_clients=enumerate_clients)
        received = _collect(disco)
        disco.scan_once()  # [ALICE]
        first = _sessions(received[0])["Alice"].first_seen_generation
        disco.scan_once()  # [] -- authoritative, prunes Alice
        assert _sessions(received[1]) == {}
        disco.scan_once()  # [ALICE] again -- must be a new session
        second = _sessions(received[2])["Alice"].first_seen_generation
        assert second != first
        assert second == received[2].generation

    def test_list_returning_enumerator_still_prunes_on_ordinary_disappearance(self):
        disco = _discovery(_enumerate_clients=lambda: [ALICE, BOB])
        received = _collect(disco)
        disco.scan_once()
        disco._enumerate_clients = lambda: [ALICE]
        disco.scan_once()
        assert _sessions(received[1]).get("Bob") is None
        assert all(c.character != "Bob" for c in received[1].clients)


# ---------------------------------------------------------------------------
# Fan-out, request_scan, isolation, and settings independence
# ---------------------------------------------------------------------------


class TestFanOutAndIsolation:
    def test_one_scan_reaches_multiple_subscribers(self):
        disco = _discovery(_enumerate_clients=_result_seq([ALICE]))
        first = []
        second = []
        disco.subscribe(lambda s: first.append(s))
        disco.subscribe(lambda s: second.append(s))
        disco.scan_once()
        assert len(first) == 1 and len(second) == 1
        assert first[0] is second[0]

    def test_failing_subscriber_does_not_block_another(self):
        disco = _discovery(_enumerate_clients=_result_seq([ALICE]))
        good = []

        def boom(_snapshot):
            raise RuntimeError("boom")

        disco.subscribe(boom)
        disco.subscribe(lambda s: good.append(s))
        disco.scan_once()
        assert len(good) == 1

    def test_unsubscribe_stops_delivery(self):
        disco = _discovery(_enumerate_clients=_result_seq([ALICE], [ALICE]))
        received = []
        unsub = disco.subscribe(lambda s: received.append(s))
        disco.scan_once()
        unsub()
        disco.scan_once()
        assert len(received) == 1

    def test_enumerator_is_the_only_collaborator(self):
        """The service consults nothing but the injected enumerator: no
        preview exclusion settings are read to build the roster."""
        calls = []

        def spying_enumerate():
            calls.append(True)
            return EnumerationResult(True, [ALICE])

        disco = _discovery(_enumerate_clients=spying_enumerate)
        received = _collect(disco)
        disco.scan_once()
        assert calls == [True]
        # The excluded-from-preview character still appears untouched.
        assert received[0].clients[0].character == "Alice"

    def test_snapshot_returns_latest(self):
        disco = _discovery(_enumerate_clients=_result_seq([ALICE]))
        assert disco.snapshot().clients == ()
        disco.scan_once()
        assert disco.snapshot().clients[0].character == "Alice"

    def test_snapshot_before_any_scan_is_empty_generation_zero(self):
        disco = _discovery(_enumerate_clients=_result_seq([]))
        snap = disco.snapshot()
        assert snap.generation == 0
        assert snap.clients == ()


# ---------------------------------------------------------------------------
# scan_once() serialization: at most one in-flight enumeration
# ---------------------------------------------------------------------------


class _AttemptSignallingLock:
    """Test-only wrapper around a lock that reports a watched thread's
    arrival at ``acquire`` *before* it blocks.

    A contention test cannot infer "the other thread is blocked" from a
    sleep plus a not-yet-finished flag: that only proves it has not
    finished, which is also true if it never started. Wrapping the lock
    makes the attempt itself observable, so the test can wait on
    ``attempted`` and know the watched thread is parked on a lock the other
    thread holds. Ported from ``test_telemetry_gamelogs.py``.
    """

    def __init__(self, real):
        self._real = real
        self._watch_ident = None
        self.attempted = threading.Event()

    def watch(self, ident):
        self._watch_ident = ident

    def acquire(self, *args, **kwargs):
        if threading.get_ident() == self._watch_ident:
            self.attempted.set()
        return self._real.acquire(*args, **kwargs)

    def release(self):
        self._real.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc_info):
        self.release()
        return False


class TestScanOnceSerialization:
    def test_manual_and_worker_calls_never_run_the_enumerator_concurrently(self):
        """A slow enumerator records how many calls are simultaneously
        in-flight. A second, independently-started ``scan_once()`` must
        block on ``_scan_lock`` until the first one's whole cycle (not just
        its enumerator call) completes, so at most one call is ever
        in-flight -- proven by an explicit blocked-thread signal, not a
        timing coincidence."""
        entered = threading.Event()
        release = threading.Event()
        in_flight = {"n": 0}
        observed_concurrency = []
        guard = threading.Lock()

        def slow_enumerate():
            with guard:
                in_flight["n"] += 1
                observed_concurrency.append(in_flight["n"])
            entered.set()
            release.wait(timeout=5)
            with guard:
                in_flight["n"] -= 1
            return EnumerationResult(True, [ALICE])

        disco = ClientDiscovery(
            _thread_factory=_noop_thread_factory, _enumerate_clients=slow_enumerate
        )
        gate = _AttemptSignallingLock(disco._scan_lock)
        disco._scan_lock = gate

        t1 = threading.Thread(target=disco.scan_once)
        t1.start()
        assert entered.wait(timeout=5)  # t1 is inside the enumerator

        def call_from_second_thread():
            gate.watch(threading.get_ident())
            disco.scan_once()

        t2 = threading.Thread(target=call_from_second_thread)
        t2.start()
        # t2 has reached the operation lock t1 still holds -- the only path
        # forward from here runs through that acquire, so it is parked.
        assert gate.attempted.wait(timeout=5)
        assert t2.is_alive()
        assert observed_concurrency == [1]  # t2 never entered the enumerator

        release.set()
        t1.join(timeout=5)
        t2.join(timeout=5)
        assert not t1.is_alive() and not t2.is_alive()
        # Both calls ran the enumerator, but strictly one at a time.
        assert observed_concurrency == [1, 1]

    def test_callbacks_run_outside_the_scan_and_state_locks(self):
        """A subscriber that calls scan_once() reentrantly must not
        deadlock -- proving callbacks run outside both _scan_lock and
        _lock."""
        disco = _discovery(_enumerate_clients=_result_seq([ALICE], [ALICE]))
        reentered = []

        def reentrant_sub(snapshot):
            if not reentered:
                reentered.append(True)
                disco.scan_once()

        disco.subscribe(reentrant_sub)
        received = _collect(disco)
        disco.scan_once()
        assert reentered
        assert len(received) == 2


# ---------------------------------------------------------------------------
# Worker lifecycle (real threads)
# ---------------------------------------------------------------------------


class TestWorker:
    def test_request_scan_interrupts_wait_before_ordinary_timeout(self):
        """The injected wait_fn ignores the real ~700ms cadence value it is
        called with and blocks on a much longer ceiling instead. If the
        wait returns True (woken) well before that ceiling elapses, the
        only possible cause is an explicit ``Event.set()`` from
        ``request_scan()`` -- a real timeout could not have produced that
        result, so this is not a timing race against the ordinary cadence."""
        LONG_CEILING_S = 10.0
        wait_started = threading.Event()
        wait_results = []
        call_count = {"n": 0}

        def enumerate_clients():
            call_count["n"] += 1
            return EnumerationResult(True, [])

        def wait_fn(event, _ordinary_timeout):
            wait_started.set()
            started = time.monotonic()
            woke = event.wait(timeout=LONG_CEILING_S)
            wait_results.append((woke, time.monotonic() - started))
            return woke

        disco = ClientDiscovery(_enumerate_clients=enumerate_clients, _wait_fn=wait_fn)
        disco.start()
        assert wait_started.wait(timeout=5), "worker never reached its wait"
        before = call_count["n"]

        disco.request_scan()

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and call_count["n"] <= before:
            time.sleep(0.005)
        disco.stop()

        assert call_count["n"] > before
        assert wait_results, "wait_fn was never invoked"
        woke, elapsed = wait_results[0]
        assert woke is True
        # Nowhere near the artificial ceiling: only an explicit set() could
        # have produced this, since the real cadence was substituted away.
        assert elapsed < LONG_CEILING_S / 2

    def test_non_daemon(self):
        disco = ClientDiscovery(_enumerate_clients=_result_seq([]))
        disco.start()
        assert disco._worker is not None and not disco._worker.daemon
        disco.stop()

    def test_stop_joins(self):
        disco = ClientDiscovery(_enumerate_clients=_result_seq([]))
        disco.start()
        worker = disco._worker
        disco.stop(timeout=3.0)
        assert not worker.is_alive()

    def test_start_idempotent(self):
        disco = ClientDiscovery(_enumerate_clients=_result_seq([]))
        disco.start()
        worker = disco._worker
        disco.start()
        assert disco._worker is worker
        disco.stop()

    def test_lifecycle_reports_completion(self):
        disco = ClientDiscovery(_enumerate_clients=_result_seq([]))
        assert disco.start() is True
        assert disco.start() is True
        assert disco.stop() is True
        assert disco.stop() is True

    def test_timeout_reports_false_and_blocks_restart(self):
        gate = threading.Event()
        created = []

        def blocking(*, target, args, name, daemon):
            def wrapper():
                gate.wait(timeout=10)
                target(*args)

            worker = threading.Thread(target=wrapper, name=name, daemon=daemon)
            created.append(worker)
            return worker

        disco = ClientDiscovery(
            _enumerate_clients=_result_seq([]), _thread_factory=blocking
        )
        assert disco.start() is True
        assert disco.stop(timeout=0.01) is False
        assert disco.start() is False
        assert len(created) == 1
        gate.set()
        assert disco.stop(timeout=5) is True
        assert disco.start() is True
        assert len(created) == 2
        assert disco.stop(timeout=5) is True

    def test_stop_idempotent(self):
        disco = ClientDiscovery(_enumerate_clients=_result_seq([]))
        disco.start()
        disco.stop()
        disco.stop()

    def test_worker_publishes(self):
        disco = ClientDiscovery(_enumerate_clients=_result_seq([ALICE]))
        received = _collect(disco)
        disco.start()
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if received:
                break
            time.sleep(0.01)
        disco.stop()
        assert received and received[0].clients[0].character == "Alice"


# ---------------------------------------------------------------------------
# Interface types
# ---------------------------------------------------------------------------


class TestRosterClientShape:
    def test_named_client_carries_matching_session_identity(self):
        disco = _discovery(_enumerate_clients=_result_seq([ALICE]))
        received = _collect(disco)
        disco.scan_once()
        client: RosterClient = received[0].clients[0]
        assert client.session.hwnd == ALICE.hwnd
        assert client.session.pid == ALICE.pid
        assert client.session.character == "Alice"


class TestDiscoveryModuleUnchanged:
    def test_raw_enumeration_still_goes_through_preview_discovery(self):
        """Regression guard for the ruling: ClientDiscovery's default
        collaborator really is preview.discovery.enumerate_clients, not a
        copy of its logic."""
        assert (
            ClientDiscovery.__init__.__kwdefaults__["_enumerate_clients"]
            is discovery.enumerate_clients
        )
