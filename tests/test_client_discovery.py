"""Shared EVE client discovery -- tests.

Most tests use ``_noop_thread_factory`` so ``start()`` sets up state without
spawning a real thread, and ``scan_once()`` drives scans synchronously.  Only
``TestWorker`` uses real threads.
"""

import threading
import time

from wingman.preview.discovery import Client
from wingman.telemetry.clients import ClientDiscovery, _noop_thread_factory
from wingman.telemetry.model import RosterClient, RosterSnapshot

ALICE = Client(
    hwnd=0x100, title="EVE - Alice", pid=111, character="Alice", stable_key="Alice"
)
BOB = Client(hwnd=0x200, title="EVE - Bob", pid=222, character="Bob", stable_key="Bob")
GENERIC = Client(
    hwnd=0x100, title="EVE", pid=111, character=None, stable_key="hwnd:0x100"
)


def _discovery(**kw):
    """ClientDiscovery with a noop thread factory for synchronous tests."""
    kw.setdefault("_thread_factory", _noop_thread_factory)
    return ClientDiscovery(**kw)


def _seq_enumerator(*scans):
    """A callable returning each *scans* list in order, then repeating the
    last one forever -- so a scan_once() call past the injected sequence
    does not raise, matching a real enumerator that keeps returning its
    latest observation."""
    calls = {"n": 0}

    def _enumerate():
        i = min(calls["n"], len(scans) - 1)
        calls["n"] += 1
        return list(scans[i])

    return _enumerate


def _collect(discovery):
    received = []
    discovery.subscribe(lambda snapshot: received.append(snapshot))
    return received


def _sessions(snapshot: RosterSnapshot):
    return {c.character: c.session for c in snapshot.clients if c.character}


# ---------------------------------------------------------------------------
# Stable session identity
# ---------------------------------------------------------------------------


class TestStableSessions:
    def test_unchanged_tuple_keeps_first_seen_generation(self):
        disco = _discovery(
            _enumerate_clients=_seq_enumerator([ALICE], [ALICE], [ALICE])
        )
        received = _collect(disco)
        disco.scan_once()
        disco.scan_once()
        disco.scan_once()
        first_seen = [_sessions(s)["Alice"].first_seen_generation for s in received]
        assert first_seen[0] == first_seen[1] == first_seen[2]

    def test_disappearance_then_return_gets_new_session(self):
        disco = _discovery(_enumerate_clients=_seq_enumerator([ALICE], [], [ALICE]))
        received = _collect(disco)
        disco.scan_once()
        first = _sessions(received[0])["Alice"].first_seen_generation
        disco.scan_once()  # Alice absent
        disco.scan_once()  # Alice returns
        second = _sessions(received[2])["Alice"].first_seen_generation
        assert second != first
        assert second == received[2].generation

    def test_hwnd_change_gets_new_session(self):
        moved = ALICE._replace(hwnd=0x999)
        disco = _discovery(_enumerate_clients=_seq_enumerator([ALICE], [moved]))
        received = _collect(disco)
        disco.scan_once()
        first = _sessions(received[0])["Alice"].first_seen_generation
        disco.scan_once()
        second = _sessions(received[1])["Alice"].first_seen_generation
        assert second != first
        assert second == received[1].generation

    def test_pid_change_gets_new_session(self):
        relaunched = ALICE._replace(pid=999)
        disco = _discovery(_enumerate_clients=_seq_enumerator([ALICE], [relaunched]))
        received = _collect(disco)
        disco.scan_once()
        first = _sessions(received[0])["Alice"].first_seen_generation
        disco.scan_once()
        second = _sessions(received[1])["Alice"].first_seen_generation
        assert second != first

    def test_generic_title_transition_gets_new_session(self):
        # Same hwnd/pid throughout: character selection screen briefly shows
        # a generic title, then the same character logs back in.
        disco = _discovery(
            _enumerate_clients=_seq_enumerator([ALICE], [GENERIC], [ALICE])
        )
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
        disco = _discovery(_enumerate_clients=_seq_enumerator([GENERIC]))
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
        disco = _discovery(
            _enumerate_clients=_seq_enumerator([ALICE], [ALICE], [ALICE])
        )
        received = _collect(disco)
        disco.scan_once()
        disco.scan_once()
        disco.scan_once()
        gens = [s.generation for s in received]
        assert gens == sorted(gens)
        assert len(set(gens)) == 3

    def test_two_independent_clients_get_independent_sessions(self):
        disco = _discovery(_enumerate_clients=_seq_enumerator([ALICE, BOB]))
        received = _collect(disco)
        disco.scan_once()
        sessions = _sessions(received[0])
        assert sessions["Alice"] != sessions["Bob"]
        assert sessions["Alice"].character == "Alice"
        assert sessions["Bob"].character == "Bob"

    def test_no_clients_publishes_empty_snapshot(self):
        disco = _discovery(_enumerate_clients=_seq_enumerator([]))
        received = _collect(disco)
        disco.scan_once()
        assert received[0].clients == ()


# ---------------------------------------------------------------------------
# Fan-out, request_scan, isolation, and settings independence
# ---------------------------------------------------------------------------


class TestFanOutAndIsolation:
    def test_one_scan_reaches_multiple_subscribers(self):
        disco = _discovery(_enumerate_clients=_seq_enumerator([ALICE]))
        first = []
        second = []
        disco.subscribe(lambda s: first.append(s))
        disco.subscribe(lambda s: second.append(s))
        disco.scan_once()
        assert len(first) == 1 and len(second) == 1
        assert first[0] is second[0]

    def test_failing_subscriber_does_not_block_another(self):
        disco = _discovery(_enumerate_clients=_seq_enumerator([ALICE]))
        good = []

        def boom(_snapshot):
            raise RuntimeError("boom")

        disco.subscribe(boom)
        disco.subscribe(lambda s: good.append(s))
        disco.scan_once()
        assert len(good) == 1

    def test_unsubscribe_stops_delivery(self):
        disco = _discovery(_enumerate_clients=_seq_enumerator([ALICE], [ALICE]))
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
            return [ALICE]

        disco = _discovery(_enumerate_clients=spying_enumerate)
        received = _collect(disco)
        disco.scan_once()
        assert calls == [True]
        # The excluded-from-preview character still appears untouched.
        assert received[0].clients[0].character == "Alice"

    def test_enumerator_exception_publishes_empty_snapshot(self):
        def exploding():
            raise RuntimeError("enum failed")

        disco = _discovery(_enumerate_clients=exploding)
        received = _collect(disco)
        disco.scan_once()
        assert received[0].clients == ()

    def test_snapshot_returns_latest(self):
        disco = _discovery(_enumerate_clients=_seq_enumerator([ALICE]))
        assert disco.snapshot().clients == ()
        disco.scan_once()
        assert disco.snapshot().clients[0].character == "Alice"

    def test_snapshot_before_any_scan_is_empty_generation_zero(self):
        disco = _discovery(_enumerate_clients=_seq_enumerator([]))
        snap = disco.snapshot()
        assert snap.generation == 0
        assert snap.clients == ()


# ---------------------------------------------------------------------------
# Worker lifecycle (real threads)
# ---------------------------------------------------------------------------


class TestWorker:
    def test_request_scan_wakes_immediately(self):
        calls = {"n": 0}
        gate = threading.Event()

        def enumerate_clients():
            calls["n"] += 1
            if calls["n"] == 1:
                gate.set()
            return [ALICE]

        disco = ClientDiscovery(_enumerate_clients=enumerate_clients)
        received = _collect(disco)
        disco.start()
        assert gate.wait(timeout=5)
        received.clear()
        before = calls["n"]
        disco.request_scan()
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if calls["n"] > before:
                break
            time.sleep(0.01)
        disco.stop()
        assert calls["n"] > before
        # Woken well inside the ordinary ~700ms cadence.
        assert len(received) >= 1

    def test_non_daemon(self):
        disco = ClientDiscovery(_enumerate_clients=_seq_enumerator([]))
        disco.start()
        assert disco._worker is not None and not disco._worker.daemon
        disco.stop()

    def test_stop_joins(self):
        disco = ClientDiscovery(_enumerate_clients=_seq_enumerator([]))
        disco.start()
        worker = disco._worker
        disco.stop(timeout=3.0)
        assert not worker.is_alive()

    def test_start_idempotent(self):
        disco = ClientDiscovery(_enumerate_clients=_seq_enumerator([]))
        disco.start()
        worker = disco._worker
        disco.start()
        assert disco._worker is worker
        disco.stop()

    def test_stop_idempotent(self):
        disco = ClientDiscovery(_enumerate_clients=_seq_enumerator([]))
        disco.start()
        disco.stop()
        disco.stop()

    def test_worker_publishes(self):
        disco = ClientDiscovery(_enumerate_clients=_seq_enumerator([ALICE]))
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
        disco = _discovery(_enumerate_clients=_seq_enumerator([ALICE]))
        received = _collect(disco)
        disco.scan_once()
        client: RosterClient = received[0].clients[0]
        assert client.session.hwnd == ALICE.hwnd
        assert client.session.pid == ALICE.pid
        assert client.session.character == "Alice"
