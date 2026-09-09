"""Task 9b: projection permissions and ordered, immutable presentation handoffs."""

import threading
from dataclasses import replace

import pytest

from tests.test_fleetsharing_worker import _snapshot, drive, rig
from wingman.fleetsharing.model import CatalogueCharacter, FleetCatalogue, PublishRow
from wingman.telemetry.model import FleetRow, FleetSnapshot, StreamHealth


def test_eligible_zero_dps_local_tackle_publishes_without_outside_damage():
    worker, client, _store, mono = rig()
    client.catalogue = FleetCatalogue(
        9,
        (
            CatalogueCharacter(1, "Eligible"),
            CatalogueCharacter(2, "Outside"),
        ),
    )
    snapshot = FleetSnapshot(
        (FleetRow("Eligible", 0, ("SCRAM", "POINT")), FleetRow("Outside", 1000)),
        StreamHealth("active"),
    )
    drive(worker, mono, 20, snapshot)
    assert client.publish_calls
    assert all(
        rows == (PublishRow(1, 0, ("SCRAM/POINT",)),)
        for _, rows in client.publish_calls
    )


def test_reentrant_off_captures_clear_before_newer_on_read():
    worker, _client, _store, mono = rig()
    drive(worker, mono, 14)
    events = []
    worker.subscribe_remote(events.append)

    def on_status(status):
        if status.participation == "queued" and not reentered[0]:
            reentered[0] = True
            worker.request_participation(True)
            drive(worker, mono, 20)

    reentered = [False]
    worker.subscribe_status(on_status)
    worker.request_participation(False)
    assert events and events[-1].kind == "replace"


def test_catalogue_hash_decrease_is_a_new_observation_and_reset_invalidates():
    worker, client, _store, mono = rig()
    events = []
    assert hasattr(worker, "subscribe_catalogue"), (
        "catalogue identity never reaches display"
    )
    worker.subscribe_catalogue(events.append)
    client.catalogue = FleetCatalogue(4000000000, (CatalogueCharacter(1, "Alice"),))
    drive(worker, mono, 14)
    client.catalogue = FleetCatalogue(1, (CatalogueCharacter(1, "Renamed"),))
    mono[0] += 60
    drive(worker, mono, 14)
    accepted = [e for e in events if e.catalogue is not None]
    assert [e.catalogue.revision for e in accepted] == [4000000000, 1]
    assert accepted[0].binding == accepted[1].binding
    assert accepted[0].order < accepted[1].order
    worker._reset_session()
    assert events[-1].catalogue is None
    assert events[-1].order > accepted[-1].order


def test_remote_receipt_and_full_request_elapsed_are_captured_once():
    worker, client, _store, mono = rig()
    drive(worker, mono, 14)
    events = []
    worker.subscribe_remote(events.append)
    client.latency = lambda: mono.__setitem__(0, mono[0] + 2.5)
    drive(worker, mono, 12)
    observed = [e for e in events if e.kind == "replace"]
    assert observed
    assert all(e.request_elapsed == 2.5 for e in observed)
    assert all(e.binding for e in observed)
    assert [e.order for e in observed] == sorted({e.order for e in observed})


def test_catalogue_result_cannot_be_relabelled_after_identity_transition(monkeypatch):
    worker, _client, _store, mono = rig()
    events = []
    worker.subscribe_catalogue(events.append)
    original = worker._accept
    transitioned = []

    def accept(work, *args):
        if work.operation == "fetch_catalogue" and not transitioned:
            transitioned.append(True)
            worker.request_pairing(mode="upgrade")
        return original(work, *args)

    monkeypatch.setattr(worker, "_accept", accept)
    drive(worker, mono, 3)
    assert transitioned
    assert not [e for e in events if e.catalogue is not None]


def test_refused_whole_publication_refetches_both_and_rebuilds_latest(monkeypatch):
    from wingman.fleetsharing.client import FleetRelayError

    worker, client, _store, mono = rig()
    drive(worker, mono, 14)
    calls = []
    original = client.publish_snapshot

    def publish(**args):
        calls.append(args["rows"])
        if len(calls) == 1:
            worker.submit(_snapshot(99))
            raise FleetRelayError(403, "forbidden", "ownership changed")
        return original(**args)

    monkeypatch.setattr(client, "publish_snapshot", publish)
    before = len(client.calls)
    worker.submit(_snapshot(10))
    drive(worker, mono, 9)
    assert calls[:2] == [(PublishRow(1, 10, ()),), (PublishRow(1, 99, ()),)]
    operations = [op for op, _, _ in client.calls[before:]]
    assert operations.index("fetch_catalogue") < operations.index("publish_snapshot")
    assert operations.index("fetch_eligibility") < operations.index("publish_snapshot")


@pytest.mark.parametrize(
    "condition",
    ["missing", "not_ready", "wrong_generation", "expired", "no_participation"],
)
def test_no_current_eligibility_never_falls_back_to_all_owned_ids(condition):
    worker, _client, _store, mono = rig()
    drive(worker, mono, 14)
    worker.submit(_snapshot(100))
    if condition == "missing":
        worker._eligibility = None
    elif condition == "not_ready":
        worker._eligibility = replace(
            worker._eligibility, state="not_verified", characters=()
        )
    elif condition == "wrong_generation":
        worker._eligibility = replace(worker._eligibility, participation_generation=99)
    elif condition == "expired":
        mono[0] += 20
        worker.submit(_snapshot(100))
    else:
        worker._state = replace(worker._state, observed_participation=None)
    assert not worker._publication()


@pytest.mark.parametrize("stream", ["remote", "catalogue"])
def test_callback_barrier_cannot_deliver_retired_clear_or_catalogue(stream):
    worker, _client, _store, mono = rig()
    drive(worker, mono, 14)
    entered, release = threading.Event(), threading.Event()
    seen = []

    def block(event):
        if not entered.is_set():
            entered.set()
            assert release.wait(5)

    subscribe = (
        worker.subscribe_remote if stream == "remote" else worker.subscribe_catalogue
    )
    subscribe(block)
    subscribe(seen.append)
    action = (
        worker._clear_remote
        if stream == "remote"
        else lambda: worker._set_catalogue(None)
    )
    thread = threading.Thread(target=action)
    thread.start()
    try:
        assert entered.wait(5)
        worker.request_pairing(mode="upgrade")
        release.set()
        thread.join(5)
        assert not thread.is_alive()
        assert all(e.identity_epoch == worker._identity_epoch for e in seen)
    finally:
        release.set()
        thread.join(5)
