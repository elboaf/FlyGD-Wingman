"""Task 9b: projection permissions and ordered, immutable presentation handoffs."""

import threading
from dataclasses import replace
from datetime import timedelta
from fractions import Fraction

import pytest

from tests.fleetsharing_timing_helpers import FakePublicationSource
from tests.test_fleetsharing_source_admission import publication_rig, ticket
from tests.test_fleetsharing_worker import NOW, _date, _snapshot, _source, drive, rig
from wingman.fleetsharing.model import CatalogueCharacter, FleetCatalogue
from wingman.telemetry.model import (
    EffectObservation,
    FleetSnapshot,
    StreamHealth,
)


def test_eligible_zero_dps_local_tackle_publishes_without_outside_damage(tmp_path):
    def configure(worker, client, mono):
        client.catalogue = FleetCatalogue(
            9,
            (CatalogueCharacter(1, "Eligible"), CatalogueCharacter(2, "Outside")),
        )

    worker, client, mono = publication_rig(tmp_path, configure=configure)
    now = mono[0]
    eligible = _source(0, now, character="Eligible").snapshot.rows[0]
    activity = replace(
        eligible.combat,
        observations=tuple(
            EffectObservation(kind, now + 30, eligible.combat.observation_id)
            for kind in ("SCRAM", "POINT")
        ),
    )
    source = FakePublicationSource(
        FleetSnapshot(
            (
                replace(eligible, combat=activity),
                _source(1000, now, character="Outside").snapshot.rows[0],
            ),
            StreamHealth("active"),
            sampled_at_mono=now,
        )
    )
    drive(worker, mono, 6, source)
    assert client.puts
    assert all(
        body["rows"]
        == [
            {
                "character_id": 1,
                "outgoing_dps": 0,
                "incoming_dps": 0,
                "activity_age_ms": 0,
                "effects": [
                    {"kind": kind, "observations": [{"name": None, "age_ms": 0}]}
                    for kind in ("SCRAM", "POINT")
                ],
            }
        ]
        for body in client.puts
    )


def test_reentrant_off_captures_clear_before_newer_on_read():
    worker, _client, _store, mono = rig()
    drive(worker, mono, 14)
    events = []
    worker.subscribe_remote(events.append)

    def on_status(status):
        if status.participation == "queued" and not reentered[0]:
            reentered[0] = True
            actions.append(
                worker.request_participation(
                    True,
                    expected_generation=status.observed_participation.generation,
                    binding=status.metadata.binding,
                )
            )
            drive(worker, mono, 20)

    reentered = [False]
    actions = []
    worker.subscribe_status(on_status)
    worker.request_participation(False)
    assert reentered == [True] and len(actions) == 1 and actions[0]
    assert (
        worker.status().pending_participation is None
        and not worker.status().local_inhibited
    )
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
    context = worker._timing_context
    before = len(context._state.exchanges)
    client.latency = lambda: mono.__setitem__(0, mono[0] + 2.5)
    drive(worker, mono, 12)
    observed = [e for e in events if e.kind == "replace"]
    assert observed
    admitted = context._state.exchanges[before:]
    assert len(admitted) == len(observed)
    assert all(e.received_at - e.started_at == Fraction(5, 2) for e in admitted)
    assert all(e.payload is not None for e in observed)
    assert observed[-1].payload is context._state.receiver.payload
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


def test_refused_whole_publication_refetches_both_and_rebuilds_latest(
    monkeypatch, tmp_path
):
    worker, client, mono = publication_rig(tmp_path)
    transport = client.relay._transport

    def publish(request, timeout=None):
        first = not client.puts
        client.put_error = (403, "forbidden") if first else None
        result = transport(request, timeout)
        if first:
            mono[0] += 0.125  # Genuinely later measurement, not conflicting same-m DPS.
            worker.submit(ticket(mono[0], outgoing=99))
        return result

    monkeypatch.setattr(client.relay, "_transport", publish)
    before = len(client.calls)
    worker.submit(ticket(mono[0], outgoing=10))
    drive(worker, mono, 9)
    assert [body["rows"][0]["outgoing_dps"] for body in client.puts[:2]] == [10, 99]
    operations = [op for op, _, _ in client.calls[before:]]
    attempts = [i for i, op in enumerate(operations) if op == "publish_snapshot"]
    assert len(attempts) >= 2
    for operation in ("fetch_catalogue", "fetch_eligibility"):
        assert attempts[0] < operations.index(operation) < attempts[1]


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


def _publication_case(tmp_path, expired_ids=(), amounts=(10, 20)):
    def configure(worker, client, mono):
        client.catalogue = FleetCatalogue(
            9, (CatalogueCharacter(1, "Alice"), CatalogueCharacter(2, "Bob"))
        )
        fetch = client.fetch_eligibility

        def proof(**args):
            result = fetch(**args)
            return replace(
                result,
                characters=tuple(
                    replace(
                        result.characters[0],
                        character_id=cid,
                        expires_at=_date(
                            NOW + timedelta(seconds=0 if cid in expired_ids else 60)
                        ),
                    )
                    for cid in (1, 2)
                ),
            )

        client.fetch_eligibility = proof

    worker, client, mono = publication_rig(tmp_path, configure=configure)
    rows = tuple(
        _source(dps, mono[0], character=name).snapshot.rows[0]
        for name, dps in zip(("Alice", "Bob"), amounts, strict=True)
    )
    worker.submit(
        FakePublicationSource(
            FleetSnapshot(
                rows,
                StreamHealth("active"),
                sampled_at_mono=mono[0],
            )
        )
    )
    return worker, client, mono


@pytest.mark.parametrize("expired_ids", [(1,), (1, 2)])
def test_expired_active_permission_suspends_whole_replacement(expired_ids, tmp_path):
    worker, client, mono = _publication_case(tmp_path, expired_ids)
    drive(worker, mono, 3)
    assert client.puts == []
    assert worker._publication() is None


def test_expired_quiet_member_does_not_block_fresh_active_member(tmp_path):
    # Retained node: legacy zero-as-quiet premise was wrong. Zero with live
    # combat is a submitted member, and its expired proof refuses the WHOLE batch.
    worker, client, mono = _publication_case(tmp_path, (1,), amounts=(0, 20))
    assert worker._publication() is None
    drive(worker, mono, 3)
    assert client.puts == []


def test_real_inactivity_remains_an_empty_replacement(tmp_path):
    worker, client, mono = _publication_case(tmp_path, amounts=(0, 0))
    drive(worker, mono, 3)
    assert client.puts and len(client.puts[0]["rows"]) == 2
    rows = tuple(
        _source(0, mono[0], character=name, inactive=True).snapshot.rows[0]
        for name in ("Alice", "Bob")
    )
    worker.submit(
        FakePublicationSource(
            FleetSnapshot(rows, StreamHealth("active"), sampled_at_mono=mono[0])
        )
    )
    drive(worker, mono, 3)
    assert client.puts[-1] == {"protocol": 2, "sampled_at_ms": 0, "rows": []}


def test_authoritative_not_verified_remains_an_empty_replacement(tmp_path):
    worker, client, mono = _publication_case(tmp_path)
    drive(worker, mono, 3)
    assert client.puts and len(client.puts[0]["rows"]) == 2
    fetch = client.fetch_eligibility

    def lost(**args):
        return replace(fetch(**args), state="not_verified", characters=())

    client.fetch_eligibility = lost
    worker.submit(None)
    drive(worker, mono, 8)
    assert client.puts[-1] == {"protocol": 2, "sampled_at_ms": 0, "rows": []}
    assert sum(not body["rows"] for body in client.puts) == 1


@pytest.mark.parametrize("stream", ["remote", "catalogue"])
def test_callback_barrier_cannot_deliver_retired_clear_or_catalogue(stream):
    worker, _client, _store, mono = rig()
    drive(worker, mono, 14)
    entered, release = threading.Event(), threading.Event()
    seen, waited = [], []

    def block(event):
        if not entered.is_set():
            entered.set()
            waited.append(release.wait(5))

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
        assert not thread.is_alive() and waited == [True]
        assert all(e.identity_epoch == worker._identity_epoch for e in seen)
    finally:
        release.set()
        thread.join(5)
