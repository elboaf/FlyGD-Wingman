"""Actual owner + signed snapshot client + JSON journal; only relay I/O is fake."""

import pytest
from test_fleetsharing_client import FakeTransport, _headers_of
from test_fleetsharing_publication import OBSERVED as PARSER_ROW
from test_fleetsharing_publication import Response
from test_fleetsharing_worker import (
    DEVICE,
    NOW,
    PAIRED_STATE,
    FakeRelayClient,
    _worker,
    drive,
)

from wingman.fleetsharing import protocol as p
from wingman.fleetsharing import state as s
from wingman.fleetsharing.client import FleetRelayClient

PUBLICATION = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
OBSERVED = {**PARSER_ROW, "publication_id": PUBLICATION}


class SnapshotClient(FakeRelayClient):
    def __init__(self, path):
        super().__init__(device=DEVICE)
        self.path = path
        self.mode = "fresh"
        self.wire = []
        self.responses = []
        self.saved_response = None
        self.relay = FleetRelayClient("https://relay.test", transport=self.transport)

    def transport(self, request, timeout=None):
        headers = _headers_of(request)
        # An attempted revision is durable BEFORE even entering HTTP transport.
        assert s.load(self.path).last_revision == int(headers["x-fleet-revision"])
        assert s.load(self.path).session_id == headers["x-fleet-session"]
        self.wire.append(headers)
        canned = FakeTransport({"protocol": 1, "rows": [OBSERVED]}, publication=True)
        admitted = canned(request, timeout)
        if self.saved_response is None:
            self.saved_response = admitted.headers
        headers = self.saved_response if self.mode == "replay" else admitted.headers
        payload = {"protocol": 1, "rows": [OBSERVED]}
        if self.mode == "stripped":
            del headers["x-fleet-snapshot-format"]
        elif self.mode == "malformed":
            payload["rows"][0] = {**OBSERVED, "publication_id": None}
        elif self.mode == "lost":
            self.mode = "fresh"
            raise OSError("synthetic lost reply")
        response = Response(payload, headers)
        self.responses.append(response)
        return response

    def read_snapshot(self, **args):
        return self._call(
            "read_snapshot", args, lambda: self.relay.read_snapshot(**args)
        )


def setup(tmp_path):
    path = tmp_path / "sharing.json"
    s.save(path, PAIRED_STATE)
    client = SnapshotClient(path)
    mono = [1000.0]

    def owner():
        worker = _worker(client, clock=lambda: mono[0], utc_clock=lambda: NOW)
        worker._load_state = lambda: s.load(path)
        worker._save_state = lambda state: s.save(path, state)
        return worker

    return path, client, mono, owner


def test_frozen_wall_clock_attempt_journal_survives_lost_snapshot_and_restart(tmp_path):
    path, client, mono, owner = setup(tmp_path)
    worker = owner()
    events = []
    worker.subscribe_remote(events.append)
    drive(worker, mono, 14)
    replaced = [e for e in events if e.kind == "replace"]
    assert replaced and replaced[-1].rows == (
        p.ObservedRemoteRow(42, "Alice", 0, (), "live", 0, PUBLICATION),
    )
    client.mode = "lost"
    before = len(client.wire)
    for _ in range(20):
        drive(worker, mono, 1)
        if len(client.wire) > before:
            break
    assert len(client.wire) == before + 1
    lost_revision = int(client.wire[-1]["x-fleet-revision"])
    assert s.load(path).last_revision == lost_revision
    assert [e for e in events if e.kind == "replace"][-1] is replaced[-1]
    assert worker.stop()
    replacement = owner()
    try:
        client.mode = "replay"
        events = []
        replacement.subscribe_remote(events.append)
        drive(replacement, mono, 16)
        assert len(client.wire) > before + 1
        assert int(client.wire[before + 1]["x-fleet-revision"]) > lost_revision
        assert not [e for e in events if e.kind == "replace"]
        # No implicit recovery/key change/browser flow for correlation failures.
        assert not client.recoveries and not client.pair_keys
        assert s.load(path).identity == PAIRED_STATE.identity
        assert all(
            h["x-fleet-issued-at"] == "2026-09-07T12:00:00.000Z" for h in client.wire
        )
        assert (
            "publication_id" not in path.read_text()
            and PUBLICATION not in path.read_text()
        )
        assert all(response.closed for response in client.responses)
    finally:
        assert replacement.stop()


@pytest.mark.parametrize("mode", ["stripped", "malformed", "replay"])
def test_untrusted_snapshot_never_emits_replace_or_refreshes_receipt(mode, tmp_path):
    _, client, mono, owner = setup(tmp_path)
    worker = owner()
    events = []
    worker.subscribe_remote(events.append)
    try:
        drive(worker, mono, 14)
        baseline = [e for e in events if e.kind == "replace"][-1]
        client.mode = mode
        before = len(client.wire)
        drive(worker, mono, 20)
        assert len(client.wire) > before
        assert [e for e in events if e.kind == "replace"][-1] is baseline
        assert client.recoveries == 0 and client.pair_keys == []
        assert all(response.closed for response in client.responses)
    finally:
        assert worker.stop()


def test_failed_attempt_persistence_sends_no_signed_snapshot(tmp_path):
    path, client, mono, owner = setup(tmp_path)
    worker = owner()
    try:
        drive(worker, mono, 14)
        revision = s.load(path).last_revision
        before = len(client.wire)

        def fail_revision(state):
            if state.last_revision > revision:
                raise OSError("synthetic journal failure")
            s.save(path, state)

        worker._save_state = fail_revision
        drive(worker, mono, 20)
        assert len(client.wire) == before
        assert s.load(path).last_revision == revision
    finally:
        assert worker.stop()


def test_recovery_new_session_rejects_former_whole_response_and_renewal_retains_counter(
    tmp_path,
):
    path, client, mono, owner = setup(tmp_path)
    worker = owner()
    events = []
    worker.subscribe_remote(events.append)
    try:
        drive(worker, mono, 14)
        previous = s.load(path)
        # Force the supported renewal lifecycle, not a manually-reset journal.
        mono[0] += 1740
        drive(worker, mono, 8)
        assert client.renew_calls
        assert s.load(path).last_revision > previous.last_revision
        assert s.load(path).session_id == previous.session_id
        client.valid_sessions.clear()
        drive(worker, mono, 18)
        assert client.recoveries == 1
        assert s.load(path).session_id != previous.session_id
        assert s.load(path).identity == previous.identity
        before = len(client.wire)
        baseline = [e for e in events if e.kind == "replace"][-1]
        client.mode = "replay"
        drive(worker, mono, 16)
        assert len(client.wire) > before
        assert client.wire[-1]["x-fleet-session"] != client.wire[0]["x-fleet-session"]
        assert [e for e in events if e.kind == "replace"][-1] is baseline
        assert not client.pair_keys
    finally:
        assert worker.stop()
