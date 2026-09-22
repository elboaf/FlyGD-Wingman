"""D consumer only: original test ticket, real signed client and durable journal."""

import json
import threading
import time
import urllib.request
from dataclasses import asdict, replace
from datetime import timedelta
from itertools import count
from math import inf, nextafter

import pytest

from tests.fleetsharing_timing_helpers import FakePublicationSource
from tests.test_fleetsharing_client import FakeTransport, _headers_of
from tests.test_fleetsharing_timing_publisher import LIFETIME
from tests.test_fleetsharing_worker import (
    DEVICE,
    NOW,
    PAIRED_STATE,
    UUID,
    FakeRelayClient,
    _worker,
    drive,
)
from wingman.fleetsharing import crypto
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing import state as s
from wingman.fleetsharing.client import FleetRelayClient, FleetRelayError
from wingman.fleetsharing.worker import _Obsolete
from wingman.telemetry.model import (
    CombatActivity,
    EffectObservation,
    FleetRow,
    FleetSnapshot,
    StreamHealth,
)

COMBAT_CAPS = (p.SHARED_CAPABILITY, p.COMBAT_CAPABILITY)
_ROW_EVENTS = count(100)


def selected_publication(worker, mono, source):
    worker.submit(source)
    for _ in range(8):
        fence = worker._fence()
        selected = worker._scheduler.choose(worker._work(True), mono[0])
        if selected is not None and selected.operation == "publish_snapshot":
            assert selected.payload.source is source
            assert selected.payload.snapshot is source.snapshot
            return selected, fence
        drive(worker, mono, 1)
    pytest.fail("real scheduler never selected publication")


class PublicationClient(FakeRelayClient):
    def __init__(self, path, device):
        super().__init__(device=device)
        self.acks = []
        self.path = path
        self.puts = []
        self.put_error = None
        self.source_requests = []
        self._source_args = None
        self.relay = FleetRelayClient("https://relay.test", transport=self.transport)

    def transport(self, request, timeout=None):
        headers = _headers_of(request)
        assert s.load(self.path).last_revision == int(headers["x-fleet-revision"])
        if request.full_url.endswith("/sources"):
            assert request.method == "PUT"
            command = p.parse_source_command(json.loads(request.data))
            assert command == self._source_args["command"]
            self.source_requests.append(command)
            try:
                result = FakeRelayClient.control_source(
                    self, **{**self._source_args, "before_send": None}
                )
            except FleetRelayError as exc:
                return FakeTransport(
                    {"protocol": 2, "error": exc.code}, exc.status or 500
                )(request, timeout)
            return FakeTransport({"protocol": 2, **asdict(result)})(request, timeout)
        assert request.method == "PUT" and request.full_url.endswith("/snapshot")
        self.puts.append(json.loads(request.data))
        if self.put_error is not None:
            status, code = self.put_error
            return FakeTransport({"protocol": 2, "error": code}, status)(
                request, timeout
            )
        return FakeTransport({"protocol": 2})(request, timeout)

    def control_source(self, **args):
        self._source_args = args
        try:
            return self.relay.control_source(**args)
        finally:
            self._source_args = None

    def acknowledge_capabilities(self, **args):
        def apply():
            capabilities = args["capabilities"]
            assert set(capabilities) <= set(self.device.approved_capabilities)
            assert set(capabilities) <= set(self.device.session_approved_capabilities)
            self.acks.append(capabilities)
            return self._update_session(args, acknowledged_capabilities=capabilities)

        return self._call("acknowledge_capabilities", args, apply)

    def publish_snapshot(self, **args):
        return self._call(
            "publish_snapshot",
            {**args, "before_send": None},
            lambda: self.relay.publish_snapshot(**args),
        )


def publication_rig(tmp_path, *, configure=None, **rights):
    path = tmp_path / "sharing.json"
    s.save(path, PAIRED_STATE)
    mono = [1000.0]
    approved = dict(
        approved_capabilities=COMBAT_CAPS,
        session_approved_capabilities=COMBAT_CAPS,
        acknowledged_capabilities=COMBAT_CAPS,
    )
    approved.update(rights)
    client = PublicationClient(path, replace(DEVICE, **approved))
    worker = _worker(
        client,
        clock=lambda: mono[0],
        utc_clock=lambda: NOW + timedelta(seconds=mono[0] - 1000),
    )
    worker._load_state = lambda: s.load(path)
    worker._save_state = lambda state: s.save(path, state)
    if configure is not None:
        configure(worker, client, mono)
    drive(worker, mono, 12)
    assert worker._catalogue is not None and worker._eligibility is not None
    assert worker._timing_context._state.anchor is not None
    return worker, client, mono


def ticket(m, *, outgoing=0, incoming=0, effects=()):
    return FakePublicationSource(
        FleetSnapshot(
            (
                FleetRow(
                    "Alice",
                    outgoing,
                    incoming_dps=incoming,
                    combat=CombatActivity(
                        m + 29, (LIFETIME, next(_ROW_EVENTS)), effects
                    ),
                ),
            ),
            StreamHealth("active"),
            sampled_at_mono=m,
        )
    )


@pytest.mark.parametrize("outgoing,incoming", [(0, 0), (None, 0), (7, None)])
def test_original_source_reaches_real_signed_combat_put(tmp_path, outgoing, incoming):
    worker, client, mono = publication_rig(tmp_path)
    m = mono[0]
    source = ticket(
        m,
        outgoing=outgoing,
        incoming=incoming,
        effects=(
            EffectObservation("SCRAM", m + 29, (LIFETIME, 2), "Alice's hunter"),
            EffectObservation("POINT", m + 28, (LIFETIME, 1)),
            EffectObservation("NEUT", m + 28, (LIFETIME, 1)),
        ),
    )
    worker.submit(source)
    drive(worker, mono, 3)
    assert client.puts, worker.status()
    assert client.puts[0] == {
        "protocol": 2,
        "sampled_at_ms": 1788782405800,
        "rows": [
            {
                "character_id": 1,
                "outgoing_dps": outgoing,
                "incoming_dps": incoming,
                "activity_age_ms": 1000,
                "effects": [
                    {
                        "kind": "SCRAM",
                        "observations": [{"name": "Alice's hunter", "age_ms": 1000}],
                    },
                    {"kind": "POINT", "observations": [{"name": None, "age_ms": 2000}]},
                    {"kind": "NEUT", "observations": [{"name": None, "age_ms": 2000}]},
                ],
            }
        ],
    }


@pytest.mark.parametrize("barrier", ["signing", "after_start"])
def test_source_invalidation_before_or_after_real_hook(tmp_path, monkeypatch, barrier):
    worker, client, mono = publication_rig(tmp_path)
    source = ticket(mono[0])
    work, fence = selected_publication(worker, mono, source)
    revision = s.load(client.path).last_revision
    if barrier == "signing":
        sign = crypto.sign_request

        def invalidate(*args, **kwargs):
            result = sign(*args, **kwargs)
            source.revoke()
            return result

        monkeypatch.setattr(crypto, "sign_request", invalidate)
    else:
        transport = client.relay._transport

        def invalidate(*args, **kwargs):
            source.revoke()
            return transport(*args, **kwargs)

        monkeypatch.setattr(client.relay, "_transport", invalidate)
    with pytest.raises(_Obsolete):
        worker._execute(work, fence)
    assert len(client.puts) == (barrier == "after_start")
    assert not worker._last_published
    assert s.load(client.path).last_revision == revision + 1
    assert "publication" not in worker._scheduler.failures
    assert worker._timing_context._publisher.associations
    assert worker._timing_context._next_stage_at is not None, (
        "staging slot was refunded"
    )
    assert (
        worker._timing_context._next_stage_at >= source.snapshot.sampled_at_mono + 0.5
    )
    if barrier == "after_start":
        assert worker._scheduler.deadlines["publication"] == mono[0] + 0.5


def test_leaf_wait_crossing_original_sample_expiry_sends_nothing(tmp_path):
    worker, client, mono = publication_rig(tmp_path)
    source = ticket(mono[0])
    work, fence = selected_publication(worker, mono, source)
    signing = threading.Event()
    reached_leaf = threading.Event()
    errors = []
    original = source.admit_start

    def admitted(validate):
        reached_leaf.set()
        return original(validate)

    source.admit_start = admitted
    real_publish = client.publish_snapshot

    def publish(**args):
        signing.set()
        return real_publish(**args)

    client.publish_snapshot = publish

    def execute():
        try:
            worker._execute(work, fence)
        except BaseException as exc:  # noqa: BLE001 — forward thread failures, including pytest outcomes, to the asserting owner.
            errors.append(exc)

    # Acquire only after staging/unwrap/save: the next source operation is the
    # actual real-client final gate, not its advisory staging check.
    entered = threading.Event()
    proceed = threading.Event()
    unwrap = worker._unwrap_private_key

    def held_unwrap(blob):
        entered.set()
        assert proceed.wait(5)
        return unwrap(blob)

    worker._unwrap_private_key = held_unwrap
    thread = threading.Thread(target=execute)
    thread.start()
    try:
        assert entered.wait(5)
        with source._lock:
            proceed.set()
            assert signing.wait(5)
            assert reached_leaf.wait(2), "real before_send never entered source leaf"
            mono[0] = source.snapshot.sampled_at_mono + 5
    finally:
        proceed.set()
        thread.join(5)
    assert not thread.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], _Obsolete)
    assert client.puts == []
    assert worker.status().detail != "local_failure"


def test_new_mailbox_does_not_replace_selected_current_ticket(tmp_path):
    worker, client, mono = publication_rig(tmp_path)
    original = ticket(mono[0], outgoing=7)
    work, fence = selected_publication(worker, mono, original)
    mono[0] += 0.25
    newer = ticket(mono[0], outgoing=99)
    worker.submit(newer)
    worker._execute(work, fence)
    assert worker._latest is newer
    assert client.puts[0]["rows"][0]["outgoing_dps"] == 7
    assert client.puts[0]["sampled_at_ms"] == 1788782405800


@pytest.mark.parametrize(
    "missing", ["approved_capabilities", "session_approved_capabilities"]
)
def test_missing_combat_disclosure_never_puts_but_shared_read_works(tmp_path, missing):
    worker, client, mono = publication_rig(
        tmp_path, **{missing: (p.SHARED_CAPABILITY,)}
    )
    before = sum(op == "read_snapshot" for op, _, _ in client.calls)
    worker.submit(ticket(mono[0]))
    drive(worker, mono, 6)
    assert client.puts == []
    assert sum(op == "read_snapshot" for op, _, _ in client.calls) > before
    assert client.acks == []


@pytest.mark.parametrize(
    "device_caps,session_caps,want",
    [
        (COMBAT_CAPS, COMBAT_CAPS, COMBAT_CAPS),
        (COMBAT_CAPS, (p.SHARED_CAPABILITY,), (p.SHARED_CAPABILITY,)),
        ((p.SHARED_CAPABILITY,), COMBAT_CAPS, (p.SHARED_CAPABILITY,)),
    ],
)
def test_ack_uses_only_canonical_approved_intersection(
    tmp_path, device_caps, session_caps, want
):
    worker, client, mono = publication_rig(
        tmp_path,
        approved_capabilities=device_caps,
        session_approved_capabilities=session_caps,
        acknowledged_capabilities=(),
    )
    assert client.acks == [want]
    worker.submit(ticket(mono[0]))
    drive(worker, mono, 3)
    assert bool(client.puts) == (want == COMBAT_CAPS)


def test_shared_ack_already_present_does_not_skip_approved_combat_ack(tmp_path):
    worker, client, mono = publication_rig(
        tmp_path, acknowledged_capabilities=(p.SHARED_CAPABILITY,)
    )
    assert client.acks == [COMBAT_CAPS]
    worker.submit(ticket(mono[0]))
    drive(worker, mono, 3)
    assert client.puts


@pytest.mark.parametrize("boundary", ["signing", "after_start"])
def test_source_control_generation_fences_selected_and_completed_put(
    tmp_path, monkeypatch, boundary
):
    worker, client, mono = publication_rig(tmp_path)
    work, fence = selected_publication(worker, mono, ticket(mono[0]))
    if boundary == "signing":
        owner, method = crypto, "sign_request"
    else:
        owner, method = client.relay, "_transport"
    original = getattr(owner, method)
    crossed = []

    def queued(*args, **kwargs):
        result = original(*args, **kwargs)
        crossed.append(worker.request_source_start(1, UUID))
        return result

    monkeypatch.setattr(owner, method, queued)
    with pytest.raises(_Obsolete):
        worker._execute(work, fence)
    assert crossed and all(crossed)
    assert len(client.puts) == (boundary == "after_start")
    assert not worker._last_published


@pytest.mark.parametrize("rollback", [False, True])
def test_cached_permission_deadline_expires_after_signing_without_utc_renewal(
    tmp_path, monkeypatch, rollback
):
    def configure(worker, client, mono):
        fetch = client.fetch_eligibility

        def short_proof(**args):
            proof = fetch(**args)
            return replace(
                proof,
                characters=tuple(
                    replace(entry, expires_at="2026-09-07T12:00:08.000Z")
                    for entry in proof.characters
                ),
            )

        client.fetch_eligibility = short_proof

    worker, client, mono = publication_rig(tmp_path, configure=configure)
    if rollback:
        worker._utc_clock = lambda: NOW - timedelta(days=1)
    work, fence = selected_publication(worker, mono, ticket(mono[0]))
    sign = crypto.sign_request

    def expired(*args, **kwargs):
        result = sign(*args, **kwargs)
        mono[0] = 1008.0
        return result

    monkeypatch.setattr(crypto, "sign_request", expired)
    with pytest.raises(_Obsolete):
        worker._execute(work, fence)
    assert client.puts == []
    assert not worker._last_published


def test_final_leaf_performs_no_utc_settings_or_source_reentry(tmp_path, monkeypatch):
    worker, client, mono = publication_rig(tmp_path)
    source = ticket(mono[0])
    work, fence = selected_publication(worker, mono, source)
    in_leaf = [False]
    original = source.admit_start
    current = source.is_current

    def admit(validate):
        def guarded():
            assert worker._lock.locked() and source._lock.locked()
            in_leaf[0] = True
            try:
                validate()
            finally:
                in_leaf[0] = False

        return original(guarded)

    def not_in_leaf(callback):
        def checked(*args, **kwargs):
            assert not in_leaf[0], "callback reentered under source leaf"
            return callback(*args, **kwargs)

        return checked

    source.admit_start = admit
    source.is_current = not_in_leaf(current)
    monkeypatch.setattr(worker, "_utc_clock", not_in_leaf(worker._utc_clock))
    monkeypatch.setattr(
        worker, "_sharing_enabled", not_in_leaf(worker._sharing_enabled)
    )
    worker._execute(work, fence)
    assert client.puts


@pytest.mark.parametrize(
    "kind,want_empty",
    [
        ("empty", True),
        ("inactive", True),
        ("zero_live", False),
        ("unavailable", False),
        ("legacy", False),
        ("stale", False),
        ("revoked", False),
        ("invalid_m", False),
    ],
)
def test_only_proven_source_inactivity_withdraws_without_anchor(
    tmp_path, kind, want_empty
):
    worker, client, mono = publication_rig(tmp_path)
    work, fence = selected_publication(worker, mono, ticket(mono[0], outgoing=7))
    worker._execute(work, fence)
    assert len(client.puts) == 1
    mono[0] += 0.5
    source = ticket(mono[0])
    snapshot = source.snapshot
    row = snapshot.rows[0]
    if kind == "empty":
        snapshot = replace(snapshot, rows=())
    elif kind == "inactive":
        snapshot = replace(snapshot, rows=(replace(row, combat=CombatActivity()),))
    elif kind == "unavailable":
        snapshot = replace(snapshot, rows=(replace(row, dps=None, incoming_dps=None),))
    elif kind == "legacy":
        snapshot = replace(snapshot, rows=(replace(row, combat=None),))
    elif kind == "stale":
        snapshot = replace(snapshot, sampled_at_mono=mono[0] - 5)
    elif kind == "invalid_m":
        snapshot = replace(snapshot, sampled_at_mono=None)
    source = FakePublicationSource(snapshot)
    if kind == "revoked":
        source.revoke()
    worker._timing_context._state = replace(worker._timing_context._state, anchor=None)
    # Stop legitimate anchor-producing reads from changing this boundary case.
    for due in worker._due:
        worker._due[due] = mono[0] + 60
    worker.submit(source)
    drive(worker, mono, 4)
    assert client.puts[1:] == (
        [{"protocol": 2, "sampled_at_ms": 0, "rows": []}] if want_empty else []
    )
    assert bool(worker._last_published) is not want_empty


@pytest.mark.parametrize(
    "conflict", ["row_deadline", "effect_deadline", "same_m_empty", "same_m_inactive"]
)
def test_retained_evidence_conflict_cannot_become_source_withdrawal(tmp_path, conflict):
    worker, client, mono = publication_rig(tmp_path)
    source = ticket(
        mono[0],
        outgoing=7,
        effects=(EffectObservation("POINT", mono[0] + 28, (LIFETIME, 77), "Hunter"),),
    )
    work, fence = selected_publication(worker, mono, source)
    worker._execute(work, fence)
    assert len(client.puts) == 1 and client.puts[0]["rows"]
    previous = worker._last_published
    pins = worker._timing_context._publisher
    floor = worker._timing_context._next_stage_at
    row = source.snapshot.rows[0]
    mono[0] += 0.5
    if conflict == "same_m_empty":
        snapshot = replace(source.snapshot, rows=())
    elif conflict == "same_m_inactive":
        snapshot = replace(
            source.snapshot, rows=(replace(row, combat=CombatActivity()),)
        )
    else:
        # Projection prunes the whole expired row. Either its old live row ID or
        # an old live named-effect ID must still conflict against retained pins.
        activity = replace(
            row.combat,
            expires_at_mono=mono[0] - 1,
            observations=(
                replace(row.combat.observations[0], expires_at_mono=mono[0] - 2),
            ),
        )
        if conflict == "effect_deadline":
            activity = replace(activity, observation_id=(LIFETIME, next(_ROW_EVENTS)))
        snapshot = replace(
            source.snapshot,
            rows=(replace(row, combat=activity),),
            sampled_at_mono=mono[0],
        )
    worker.submit(FakePublicationSource(snapshot))
    for key in worker._due:
        worker._due[key] = mono[0] + 60
    drive(worker, mono, 2)
    assert len(client.puts) == 1, (
        "retained evidence conflict sent destructive empty PUT"
    )
    assert worker._last_published is previous
    assert worker._timing_context._publisher is pins
    assert worker._timing_context._next_stage_at == floor


@pytest.mark.parametrize("eligible_bob", [True, False])
def test_conflicting_member_beside_inactive_is_not_hidden_by_permission(
    tmp_path, eligible_bob
):
    from tests.test_fleetsharing_remote_worker import _publication_case

    worker, client, mono = _publication_case(tmp_path)
    original = worker._latest.snapshot
    drive(worker, mono, 3)
    assert client.puts and len(client.puts[0]["rows"]) == 2
    previous, pins = worker._last_published, worker._timing_context._publisher
    before = len(client.puts)
    if not eligible_bob:
        fetch = client.fetch_eligibility

        def alice_only(**args):
            result = fetch(**args)
            return replace(
                result,
                characters=tuple(e for e in result.characters if e.character_id == 1),
            )

        client.fetch_eligibility = alice_only
        worker.submit(None)
        for key in worker._due:
            worker._due[key] = 0 if key == "eligibility" else mono[0] + 60
        worker.iterate_once()
        assert [e.character_id for e in worker._eligibility.characters] == [1]
    alice, bob = original.rows
    worker.submit(
        FakePublicationSource(
            replace(
                original,
                sampled_at_mono=mono[0],
                rows=(
                    replace(alice, dps=0, combat=CombatActivity()),
                    replace(
                        bob, combat=replace(bob.combat, expires_at_mono=mono[0] - 1)
                    ),
                ),
            )
        )
    )
    drive(worker, mono, 3)
    assert len(client.puts) == before, (
        "permission filtering hid retained member conflict"
    )
    assert worker._last_published is previous
    assert worker._timing_context._publisher is pins


def test_authoritative_eligibility_loss_withdraws_without_local_ticket(tmp_path):
    worker, client, mono = publication_rig(tmp_path)
    work, fence = selected_publication(worker, mono, ticket(mono[0]))
    worker._execute(work, fence)
    worker.submit(None)
    fetch = client.fetch_eligibility

    def lost(**args):
        result = fetch(**args)
        return replace(result, state="not_verified", characters=())

    client.fetch_eligibility = lost
    drive(worker, mono, 10)
    assert client.puts[1:] == [{"protocol": 2, "sampled_at_ms": 0, "rows": []}]


def test_explicit_off_withdraws_when_source_and_timing_are_closed(tmp_path):
    worker, client, mono = publication_rig(tmp_path)
    source = ticket(mono[0])
    work, fence = selected_publication(worker, mono, source)
    worker._execute(work, fence)
    source.revoke()
    worker.submit(None)
    worker.fence_timing("db_continuity_lost")
    assert worker.request_participation(
        False, expected_generation=1, binding=worker.status().metadata.binding
    )
    drive(worker, mono, 12)
    assert client.puts[1:] == [{"protocol": 2, "sampled_at_ms": 0, "rows": []}]
    assert not client.device.participation.enabled


def selected_off(worker, mono):
    assert worker.request_participation(
        False, expected_generation=1, binding=worker.status().metadata.binding
    )
    worker._ingest()
    for _ in range(20):
        fence = worker._fence()
        work = worker._scheduler.choose(worker._work(False), mono[0])
        if work is not None and work.key == "withdraw":
            return work, fence
        wait, _ = worker._iterate()
        mono[0] += wait
    pytest.fail("authorized Off withdrawal never selected")


@pytest.mark.parametrize(
    "http_error,authority",
    [
        (False, "deadline_equal"),
        (True, "deadline_over"),
        (False, "deadline_extended"),
        (False, "approved_capabilities"),
        (False, "session_approved_capabilities"),
        (False, "acknowledged_capabilities"),
        (False, "auth"),
        (False, "new_intent"),
        (False, "new_session"),
    ],
)
def test_off_completion_retains_original_applicable_authority(
    tmp_path, monkeypatch, http_error, authority
):
    worker, client, mono = publication_rig(tmp_path)
    source = ticket(mono[0])
    work, fence = selected_publication(worker, mono, source)
    worker._execute(work, fence)
    assert len(client.puts) == 1 and client.puts[0]["rows"]
    # Off must not gain a source/timing prerequisite as part of this correction.
    source.revoke()
    worker.submit(None)
    worker.fence_timing("db_continuity_lost")
    work, fence = selected_off(worker, mono)
    original_deadline = worker._expires_at
    previous, last_at = worker._last_published, worker._last_publish_at
    status, catalogue = worker.status(), worker._catalogue
    revision = s.load(client.path).last_revision
    assert worker._withdraw_needed and mono[0] < original_deadline
    if http_error:
        client.put_error = (403, "forbidden")
    entered, release = threading.Event(), threading.Event()
    errors = []
    transport = client.relay._transport

    def held(*args, **kwargs):
        result = transport(*args, **kwargs)
        entered.set()
        assert release.wait(5), "Off HTTP response not released"
        return result

    monkeypatch.setattr(client.relay, "_transport", held)

    def execute():
        try:
            with worker._iteration_lock:
                worker._execute(work, fence)
        except BaseException as exc:  # noqa: BLE001 — forward thread/pytest failures to the asserting owner.
            errors.append(exc)

    thread = threading.Thread(target=execute)
    thread.start()
    try:
        assert entered.wait(5), "actual signed Off HTTP not reached"
        assert client.puts[-1] == {"protocol": 2, "sampled_at_ms": 0, "rows": []}
        assert s.load(client.path).last_revision == revision + 1
        if authority.startswith("deadline"):
            mono[0] = float(original_deadline)
            assert mono[0] == original_deadline  # Actual original deadline equality.
            if authority == "deadline_over":
                mono[0] = nextafter(mono[0], inf)
            elif authority == "deadline_extended":
                worker._expires_at += 60  # Later cache cannot renew this old reply.
        elif authority == "auth":
            worker._control_auth = None
        elif authority == "new_intent":
            assert worker.request_participation(
                True, expected_generation=1, binding=worker.status().metadata.binding
            )
            status = worker.status()  # Compare against effects of the new intent.
        elif authority == "new_session":
            worker._state = replace(worker._state, session_id="B" * 42 + "A")
        else:
            worker._state = replace(worker._state, **{authority: ()})
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], _Obsolete), (
        "obsolete Off reply installed current effects"
    )
    assert worker._last_published is previous and worker._last_publish_at == last_at
    assert worker._withdraw_needed
    assert worker.status() == status and worker._catalogue is catalogue
    assert s.load(client.path).last_revision == revision + 1
    assert worker._scheduler.deadlines["publication"] == mono[0] + 0.5
    if http_error:
        assert worker._scheduler.retry_at["withdraw"] == mono[0] + 1


def error_install_case(tmp_path, kind):
    worker, client, mono = publication_rig(tmp_path)
    source = ticket(mono[0], outgoing=7)
    work, fence = selected_publication(worker, mono, source)
    worker._execute(work, fence)
    assert len(client.puts) == 1 and client.puts[0]["rows"]
    mono[0] += 0.5
    if kind == "off":
        source.revoke()
        worker.submit(None)
        worker.fence_timing("db_continuity_lost")
        worker._apply_timing_loss()
        work, fence = selected_off(worker, mono)
    else:
        work, fence = selected_publication(worker, mono, ticket(mono[0], outgoing=9))
    return worker, client, mono, work, fence


@pytest.mark.parametrize(
    "kind,error,invalidate",
    [
        ("publication", (403, "forbidden"), "new_intent"),
        ("off", (403, "forbidden"), "lifecycle"),
        ("publication", (401, "unauthorized"), "auth"),
        ("off", (401, "unauthorized"), "shared_rights"),
        ("publication", (503, "service_unavailable"), "lifecycle"),
        ("off", (503, "service_unavailable"), "new_intent"),
    ],
)
def test_publication_error_install_rechecks_original_authority_atomically(
    tmp_path, monkeypatch, kind, error, invalidate
):
    # Removing the protected error-install validation must expose obsolete error
    # state, even though HTTP and the preliminary completion check both finished.
    worker, client, mono, work, fence = error_install_case(tmp_path, kind)
    client.put_error = error
    previous, last_at = worker._last_published, worker._last_publish_at
    revision = s.load(client.path).last_revision
    original_session = worker._state.session_id
    catalogue, eligibility = worker._catalogue, worker._eligibility
    proof, needs_device = worker._eligibility_proof, worker._needs_device
    due, withdraw = dict(worker._due), worker._withdraw_needed
    responses, checks, errors, statuses, catalogues = [], [], [], [], []
    transport = client.relay._transport
    completion = worker._check_publication_completion
    relay_error = worker._relay_error
    entered, release = threading.Event(), threading.Event()
    installing = [None]
    worker_lock = worker._lock

    class InstallLock:
        def __enter__(self):
            if installing[0] == threading.get_ident():
                installing[0] = None
                entered.set()
                assert release.wait(5), "error installation not released"
            worker_lock.acquire()
            return self

        def __exit__(self, *args):
            worker_lock.release()

    monkeypatch.setattr(worker, "_lock", InstallLock())

    def closed_error(*args, **kwargs):
        response = transport(*args, **kwargs)
        responses.append(response)
        mono[0] += 0.125  # HTTP completion, not later error presentation, owns r.
        return response

    def prechecked(*args, **kwargs):
        result = completion(*args, **kwargs)
        checks.append(mono[0])
        return result

    def held_install(*args, **kwargs):
        assert checks and responses[-1].closed
        # Hold the actual install lock acquisition, not merely method entry. A
        # mutant that checks again outside that lock must still lose this race.
        installing[0] = threading.get_ident()
        return relay_error(*args, **kwargs)

    monkeypatch.setattr(client.relay, "_transport", closed_error)
    monkeypatch.setattr(worker, "_check_publication_completion", prechecked)
    monkeypatch.setattr(worker, "_relay_error", held_install)
    worker.subscribe_status(statuses.append)
    worker.subscribe_catalogue(catalogues.append)

    def execute():
        try:
            with worker._iteration_lock:
                worker._execute(work, fence)
        except BaseException as exc:  # noqa: BLE001 — forward thread/pytest failures to the asserting owner.
            errors.append(exc)

    thread = threading.Thread(target=execute)
    thread.start()
    try:
        assert entered.wait(5), "closed signed HTTP did not reach post-precheck install"
        receipt = mono[0]
        assert checks == [receipt]
        assert s.load(client.path).last_revision == revision + 1
        assert len(client.puts) == 2
        if kind == "off":
            assert client.puts[-1] == {"protocol": 2, "sampled_at_ms": 0, "rows": []}
        else:
            assert client.puts[-1]["rows"][0]["outgoing_dps"] == 9
        pins = worker._timing_context._publisher
        floor = worker._timing_context._next_stage_at
        if invalidate == "new_intent":
            assert worker.request_participation(
                True, expected_generation=1, binding=worker.status().metadata.binding
            )
        elif invalidate == "lifecycle":
            assert worker.stop()
        else:
            with worker._lock:
                if invalidate == "auth":
                    worker._control_auth = None
                else:
                    worker._state = replace(worker._state, acknowledged_capabilities=())
        status = worker.status()
        statuses.clear()
        catalogues.clear()
        mono[0] += 0.25  # Presentation delay cannot shift the HTTP completion floor.
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()
    assert worker.status() == status, "obsolete publication error installed status"
    assert worker._catalogue is catalogue and worker._eligibility is eligibility
    assert worker._eligibility_proof is proof and worker._needs_device == needs_device
    assert worker._due == due
    assert not statuses and not catalogues
    assert len(errors) == 1 and isinstance(errors[0], _Obsolete)
    assert worker._last_published is previous and worker._last_publish_at == last_at
    assert worker._withdraw_needed == withdraw
    assert worker._state.session_id == original_session
    assert s.load(client.path).last_revision == revision + 1
    assert worker._scheduler.deadlines["publication"] == receipt + 0.5
    assert worker._scheduler.retry_at[work.key] == receipt + 1
    assert worker._scheduler.failures[work.key] == 1
    assert worker._timing_context._publisher is pins
    assert worker._timing_context._next_stage_at == floor


@pytest.mark.parametrize("kind", ["publication", "off"])
@pytest.mark.parametrize(
    "error", [(403, "forbidden"), (401, "unauthorized"), (503, "service_unavailable")]
)
def test_current_publication_error_captures_effects_before_unlocked_notifications(
    tmp_path, monkeypatch, kind, error
):
    worker, client, mono, work, fence = error_install_case(tmp_path, kind)
    client.put_error = error
    previous, last_at = worker._last_published, worker._last_publish_at
    catalogue, eligibility = worker._catalogue, worker._eligibility
    revision = s.load(client.path).last_revision
    notices, saves = [], []
    notify, save = worker._notify, worker._save_state

    def observe_notice(event_kind, value):
        locks = [worker._lock, worker._status_lock]
        if kind == "publication":
            locks.append(work.payload.source._lock)
        free = []
        for lock in locks:
            acquired = lock.acquire(blocking=False)
            free.append(acquired)
            if acquired:
                lock.release()
        notices.append(
            (event_kind, value, free, worker._catalogue, worker._eligibility)
        )
        return notify(event_kind, value)

    def observe_save(candidate):
        acquired = worker._lock.acquire(blocking=False)
        if acquired:
            worker._lock.release()
        saves.append((candidate, acquired))
        return save(candidate)

    monkeypatch.setattr(worker, "_notify", observe_notice)
    monkeypatch.setattr(worker, "_save_state", observe_save)
    worker._execute(work, fence)
    receipt = mono[0]
    assert worker.status().state == "error" and worker.status().detail == error[1]
    assert len(client.puts) == 2
    assert all(all(row[2]) for row in notices), "notification delivered under a lock"
    assert saves[0][0].last_revision == revision + 1
    assert all(unlocked for _, unlocked in saves), "durable save under worker lock"
    status_notice = next(
        row for row in notices if row[0] == "status" and row[1].state == "error"
    )
    if error[0] == 403:
        assert status_notice[3:] == (None, None), (
            "status escaped before forbidden effects installed"
        )
        assert worker._catalogue is None and worker._eligibility is None
        assert (
            worker._needs_device
            and worker._due["catalogue"] == worker._due["eligibility"] == 0
        )
    elif error[0] == 401:
        assert s.load(client.path).session_id is None
        assert worker._catalogue is None and worker._eligibility is None
        assert not worker._last_published
        assert any(row[0] == "remote" for row in notices)
    else:
        assert worker._catalogue is catalogue and worker._eligibility is eligibility
    if error[0] != 401:
        assert worker._last_published is previous
        assert s.load(client.path).last_revision == revision + 1
    assert worker._last_publish_at == last_at
    assert worker._withdraw_needed == (kind == "off")
    assert worker._scheduler.deadlines["publication"] == receipt + 0.5
    assert worker._scheduler.retry_at[work.key] == receipt + 1


@pytest.mark.parametrize(
    "kind,boundary,invalidate",
    [
        ("publication", "during_save", "new_intent"),
        ("off", "during_save", "lifecycle"),
        ("publication", "after_save", "lifecycle"),
        ("off", "after_save", "new_intent"),
    ],
)
def test_publication_401_durable_loss_cannot_reset_after_replacement(
    tmp_path, monkeypatch, kind, invalidate, boundary
):
    worker, client, mono, work, fence = error_install_case(tmp_path, kind)
    client.put_error = (401, "unauthorized")
    previous, last_at = worker._last_published, worker._last_publish_at
    catalogue, eligibility = worker._catalogue, worker._eligibility
    auth, needs_device = worker._control_auth, worker._needs_device
    due, withdraw = dict(worker._due), worker._withdraw_needed
    revision = s.load(client.path).last_revision
    entered, release = threading.Event(), threading.Event()
    errors, saves, catalogues, unlocked = [], [], [], []
    save, persist = worker._save_state, worker._persist

    def hold():
        acquired = worker._lock.acquire(blocking=False)
        unlocked.append(acquired)
        if acquired:
            worker._lock.release()
        entered.set()
        assert release.wait(5), "durable session-loss boundary not released"

    def held_save(candidate):
        saves.append(candidate)
        save(candidate)
        if candidate.session_id is None and boundary == "during_save":
            hold()

    def held_persist(candidate, *args, **kwargs):
        result = persist(candidate, *args, **kwargs)
        if candidate.session_id is None and boundary == "after_save":
            hold()
        return result

    monkeypatch.setattr(worker, "_save_state", held_save)
    monkeypatch.setattr(worker, "_persist", held_persist)
    worker.subscribe_catalogue(catalogues.append)

    def execute():
        try:
            with worker._iteration_lock:
                worker._execute(work, fence)
        except BaseException as exc:  # noqa: BLE001 — forward thread/pytest failures to the asserting owner.
            errors.append(exc)

    thread = threading.Thread(target=execute)
    thread.start()
    try:
        assert entered.wait(5), "real 401 did not reach durable session-loss boundary"
        assert unlocked == [True], "session-loss persistence moved under worker lock"
        assert len(client.puts) == 2
        assert saves[0].last_revision == revision + 1
        assert s.load(client.path).session_id is None
        if invalidate == "new_intent":
            assert worker.request_participation(True)
        else:
            assert worker.stop()
        status = worker.status()
        catalogues.clear()
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()
    assert worker._catalogue is catalogue, "obsolete 401 completion reset catalogue"
    assert worker._eligibility is eligibility and worker._control_auth == auth
    assert worker._needs_device == needs_device and worker._due == due
    assert not catalogues
    assert worker._last_published is previous and worker._last_publish_at == last_at
    assert worker._withdraw_needed == withdraw
    assert len(errors) == 1 and isinstance(errors[0], _Obsolete)
    # Successfully saved session loss is retained even if submission fenced the
    # following completion. Its metadata projection is not a publication ACK.
    assert worker._state == s.load(client.path) and worker._state.session_id is None
    current = worker.status()
    assert (
        current.state,
        current.detail,
        current.participation,
        current.participation_intent_id,
    ) == (
        status.state,
        status.detail,
        status.participation,
        status.participation_intent_id,
    )
    assert not current.metadata.has_session
    assert worker._scheduler.deadlines["publication"] == mono[0] + 0.5
    assert worker._scheduler.retry_at[work.key] == mono[0] + 1


class CompletionInstallBarrier:
    """Pause the executing thread immediately before an actual lock acquisition."""

    def __init__(self, monkeypatch, worker):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.owner = None
        self.hits = []
        self.lock = worker._lock
        monkeypatch.setattr(worker, "_lock", self)

    def arm(self):
        self.owner = threading.get_ident()

    def __enter__(self):
        if self.owner == threading.get_ident():
            self.owner = None
            self.hits.append(threading.get_ident())
            self.entered.set()
            assert self.release.wait(5), "completion installation not released"
        self.lock.acquire()
        return self

    def __exit__(self, *args):
        self.lock.release()


def completion_thread(worker, work, fence):
    errors = []

    def execute():
        try:
            with worker._iteration_lock:
                worker._execute(work, fence)
        except BaseException as exc:  # noqa: BLE001 — thread/pytest failures belong to the asserting owner, not a swallowed subscriber callback.
            errors.append(exc)

    thread = threading.Thread(target=execute)
    thread.start()
    return thread, errors


def source_completion_case(tmp_path, kind):
    worker, client, mono, work, fence = error_install_case(tmp_path, "publication")
    if kind == "inactive":
        source = FakePublicationSource(
            FleetSnapshot((), StreamHealth("active"), sampled_at_mono=mono[0])
        )
        work, fence = selected_publication(worker, mono, source)
        assert work.payload.withdrawal_reason == "inactive"
    return worker, client, mono, work, fence


@pytest.mark.parametrize(
    "kind,error,revoke",
    [
        (kind, error, True)
        for kind in ("publication", "inactive")
        for error in (None, (403, "forbidden"), (503, "service_unavailable"))
    ]
    + [("publication", None, False)],
)
def test_original_source_guards_actual_completion_install(
    tmp_path, monkeypatch, kind, error, revoke
):
    # Advisory-only validation or guarding the newer mailbox permits obsolete
    # ACK/error effects after the original source has independently revoked.
    worker, client, mono, work, fence = source_completion_case(tmp_path, kind)
    source = work.payload.source
    worker._update_status(state="error", detail="server_error")
    client.put_error = error
    previous, last_at = worker._last_published, worker._last_publish_at
    catalogue, eligibility = worker._catalogue, worker._eligibility
    proof, needs_device = worker._eligibility_proof, worker._needs_device
    due, withdraw = dict(worker._due), worker._withdraw_needed
    revision = s.load(client.path).last_revision
    statuses, catalogues, checks, responses = [], [], [], []
    completion, transport = (
        worker._check_publication_completion,
        client.relay._transport,
    )
    barrier = CompletionInstallBarrier(monkeypatch, worker)

    def prechecked(*args, **kwargs):
        result = completion(*args, **kwargs)
        checks.append(mono[0])
        barrier.arm()
        return result

    def closed(*args, **kwargs):
        response = transport(*args, **kwargs)
        responses.append(response)
        mono[0] += 0.125
        return response

    monkeypatch.setattr(worker, "_check_publication_completion", prechecked)
    monkeypatch.setattr(client.relay, "_transport", closed)
    worker.subscribe_status(statuses.append)
    worker.subscribe_catalogue(catalogues.append)
    thread, errors = completion_thread(worker, work, fence)
    try:
        assert barrier.entered.wait(5), "post-precheck installation never acquired"
        receipt = mono[0]
        assert checks == [receipt] and responses[-1].closed
        assert len(client.puts) == 2
        assert bool(client.puts[-1]["rows"]) == (kind == "publication")
        assert s.load(client.path).last_revision == revision + 1
        pins, floor = (
            worker._timing_context._publisher,
            worker._timing_context._next_stage_at,
        )
        status, current_fence = worker.status(), worker._fence()
        # Mailbox delivery alone changes no authority of the retained selection.
        fresh = ticket(mono[0], outgoing=99)
        worker.submit(fresh)
        if revoke:
            source.revoke()
        assert worker._fence() == current_fence == fence
        statuses.clear()
        catalogues.clear()
        mono[0] += 0.25
    finally:
        barrier.release.set()
        thread.join(5)
    assert not thread.is_alive() and barrier.hits == [thread.ident]
    if revoke:
        assert (
            worker._last_published is previous and worker._last_publish_at == last_at
        ), "obsolete source acknowledged publication"
        assert worker.status() == status, "obsolete source installed error/status"
        assert worker._catalogue is catalogue and worker._eligibility is eligibility
        assert (
            worker._eligibility_proof is proof and worker._needs_device == needs_device
        )
        assert worker._due == due and not statuses and not catalogues
        assert len(errors) == 1 and isinstance(errors[0], _Obsolete), errors
    else:
        assert errors == []
        if error is None:
            assert worker._last_published == (
                () if kind == "inactive" else work.payload.semantic
            )
            assert worker._last_publish_at == receipt
            assert worker.status().state == "active" and worker.status().detail is None
            assert statuses[-1] == worker.status(), (
                "current success lost its error-clear notification"
            )
        else:
            assert (
                worker._last_published is previous
                and worker._last_publish_at == last_at
            )
            assert (
                worker.status().state == "error" and worker.status().detail == error[1]
            )
            assert statuses[-1] == worker.status()
            if error[0] == 403:
                assert worker._catalogue is None and worker._eligibility is None
                assert catalogues[-1].catalogue is None
                assert worker._needs_device
                assert worker._due["catalogue"] == worker._due["eligibility"] == 0
            else:
                assert (
                    worker._catalogue is catalogue
                    and worker._eligibility is eligibility
                )
    assert worker._withdraw_needed == withdraw
    assert worker._latest is fresh and len(client.puts) == 2
    assert s.load(client.path).last_revision == revision + 1
    assert worker._scheduler.deadlines["publication"] == receipt + 0.5
    if error is not None:
        assert worker._scheduler.retry_at[work.key] == receipt + 1
        assert worker._scheduler.failures[work.key] == 1
    else:
        assert work.key not in worker._scheduler.failures
    assert worker._timing_context._publisher is pins
    assert worker._timing_context._next_stage_at == floor


@pytest.mark.parametrize(
    "kind,replace_intent",
    [
        ("publication", True),
        ("off", True),
        ("off_refused", True),
        ("publication", False),
    ],
)
def test_publication_success_status_install_keeps_original_intent(
    tmp_path, monkeypatch, kind, replace_intent
):
    worker, client, mono, work, fence = error_install_case(
        tmp_path, "off" if kind == "off_refused" else kind
    )
    # Off is already source-less/timing-closed. Clear its presentation only so
    # the old generic active tail is distinguishable; timing stays unavailable.
    if kind == "off":
        worker._timing_context._timing_loss = None
        worker._timing_context._inconsistent = True
    worker._update_status(state="error", detail="server_error")
    revision = s.load(client.path).last_revision
    barrier = CompletionInstallBarrier(monkeypatch, worker)
    checks, statuses = [], []
    completion = worker._check_publication_completion

    def prechecked(*args, **kwargs):
        result = completion(*args, **kwargs)
        checks.append(mono[0])
        return result

    # Baseline's actual status-install worker acquisition is in _update_status;
    # the corrected combined ACK/status path acquires in _accept_publication.
    # Both observe AFTER preliminary completion and before the mutation lock.
    update = worker._update_status

    def status_install(**changes):
        if checks and changes.get("state") in ("active", "refused"):
            barrier.arm()
        return update(**changes)

    monkeypatch.setattr(worker, "_update_status", status_install)
    if hasattr(worker, "_accept_publication"):
        accept = worker._accept_publication

        def combined_install(*args, **kwargs):
            if checks:
                barrier.arm()
            return accept(*args, **kwargs)

        monkeypatch.setattr(worker, "_accept_publication", combined_install)
    monkeypatch.setattr(worker, "_check_publication_completion", prechecked)
    worker.subscribe_status(statuses.append)
    thread, errors = completion_thread(worker, work, fence)
    try:
        assert barrier.entered.wait(5), "actual success-status installation not reached"
        assert checks == [mono[0]] and len(client.puts) == 2
        if replace_intent:
            assert worker.request_participation(
                True, expected_generation=1, binding=worker.status().metadata.binding
            )
        status = worker.status()
        statuses.clear()
    finally:
        barrier.release.set()
        thread.join(5)
    assert not thread.is_alive() and barrier.hits == [thread.ident]
    if replace_intent:
        assert worker.status() == status, (
            "old success overwrote replacement intent status"
        )
        assert not statuses, "obsolete success notification escaped"
        assert len(errors) == 1 and isinstance(errors[0], _Obsolete), errors
    else:
        assert errors == []
        assert worker.status().state == (
            "refused" if kind == "off_refused" else "active"
        )
        assert worker.status().detail == (
            "db_continuity_lost" if kind == "off_refused" else None
        )
        assert statuses[-1] == worker.status()
        assert worker._last_publish_at == mono[0]
        assert worker._last_published == (
            () if kind != "publication" else work.payload.semantic
        )
        assert not worker._withdraw_needed
    assert s.load(client.path).last_revision == revision + 1
    assert worker._scheduler.deadlines["publication"] == mono[0] + 0.5


@pytest.mark.parametrize(
    "kind,boundary,revoke",
    [
        ("publication", "during_save", True),
        ("inactive", "during_save", True),
        ("publication", "reset_acquisition", True),
        ("inactive", "reset_acquisition", True),
        ("publication", "reset_acquisition", False),
    ],
)
def test_original_source_guards_post_save_401_reset(
    tmp_path, monkeypatch, kind, boundary, revoke
):
    worker, client, mono, work, fence = source_completion_case(tmp_path, kind)
    source = work.payload.source
    client.put_error = (401, "unauthorized")
    previous, last_at = worker._last_published, worker._last_publish_at
    catalogue, eligibility = worker._catalogue, worker._eligibility
    auth, needs_device = worker._control_auth, worker._needs_device
    due, withdraw = dict(worker._due), worker._withdraw_needed
    revision = s.load(client.path).last_revision
    barrier = CompletionInstallBarrier(monkeypatch, worker)
    save, persist = worker._save_state, worker._persist
    saves, statuses, catalogues, persisted = [], [], [], []

    def saved(candidate):
        save(candidate)
        saves.append(candidate)
        if candidate.session_id is None and boundary == "during_save":
            barrier.entered.set()
            assert barrier.release.wait(5), "durable save not released"

    def after_persist(candidate, *args, **kwargs):
        result = persist(candidate, *args, **kwargs)
        if candidate.session_id is None:
            persisted.append(candidate)
            if boundary == "reset_acquisition":
                barrier.arm()
        return result

    monkeypatch.setattr(worker, "_save_state", saved)
    monkeypatch.setattr(worker, "_persist", after_persist)
    worker.subscribe_status(statuses.append)
    worker.subscribe_catalogue(catalogues.append)
    thread, errors = completion_thread(worker, work, fence)
    try:
        assert barrier.entered.wait(5), "real 401 did not reach post-save boundary"
        assert len(client.puts) == 2 and saves[0].last_revision == revision + 1
        assert s.load(client.path) == saves[-1] and saves[-1].session_id is None
        assert saves[-1].last_revision == 0  # Existing replace_session semantics.
        current_fence, status = worker._fence(), worker.status()
        if boundary == "reset_acquisition":
            assert persisted == [saves[-1]]
        if revoke:
            source.revoke()
        assert worker._fence() == current_fence
        pins, floor = (
            worker._timing_context._publisher,
            worker._timing_context._next_stage_at,
        )
        statuses.clear()
        catalogues.clear()
    finally:
        barrier.release.set()
        thread.join(5)
    assert not thread.is_alive()
    if boundary == "reset_acquisition":
        assert barrier.hits == [thread.ident]
    if revoke:
        assert worker._catalogue is catalogue, (
            "obsolete source reset catalogue after durable 401 save"
        )
        assert worker._eligibility is eligibility and worker._control_auth == auth
        assert worker._needs_device == needs_device and worker._due == due
        assert worker._last_published is previous and not catalogues
        assert len(errors) == 1 and isinstance(errors[0], _Obsolete), errors
        # The during-save projection legitimately publishes has_session=False;
        # no later cache/status reset or rollback of that saved candidate is allowed.
        assert all(not event.metadata.has_session for event in statuses)
        assert worker.status().eligibility == status.eligibility
    else:
        assert errors == []
        assert worker._catalogue is None and worker._eligibility is None
        assert worker._control_auth is None and worker._needs_device
        assert not worker._last_published and catalogues[-1].catalogue is None
    assert worker._state == s.load(client.path) == saves[-1]
    assert not worker.status().metadata.has_session
    assert worker._last_publish_at == last_at and worker._withdraw_needed == withdraw
    assert worker._scheduler.deadlines["publication"] == mono[0] + 0.5
    assert worker._scheduler.retry_at[work.key] == mono[0] + 1
    assert worker._timing_context._publisher is pins
    assert worker._timing_context._next_stage_at == floor


@pytest.mark.parametrize(
    "kind,error",
    [
        ("publication", None),
        ("off", None),
        ("publication", (403, "forbidden")),
        ("inactive", (401, "unauthorized")),
        ("off", (401, "unauthorized")),
        ("off", (503, "service_unavailable")),
    ],
)
def test_completion_leaf_lock_order_and_nonconsuming_costs(
    tmp_path, monkeypatch, kind, error
):
    if kind == "off":
        worker, client, mono, work, fence = error_install_case(tmp_path, kind)
    else:
        worker, client, mono, work, fence = source_completion_case(tmp_path, kind)
    client.put_error = error
    worker._update_status(state="error", detail="server_error")
    source = None if kind == "off" else work.payload.source
    in_leaf = [False]
    leaf_locks, reentries, external, stages, starts, completed = [], [], [], [], [], []

    class WitnessLock:
        def __init__(self, lock, name):
            self.lock, self.name = lock, name

        def __enter__(self):
            if in_leaf[0]:
                reentries.append(self.name)
                raise RuntimeError("worker lock reacquired inside source leaf")
            self.lock.acquire()
            return self

        def __exit__(self, *args):
            self.lock.release()

        def locked(self):
            return self.lock.locked()

    monkeypatch.setattr(worker, "_lock", WitnessLock(worker._lock, "worker"))
    monkeypatch.setattr(
        worker, "_status_lock", WitnessLock(worker._status_lock, "status")
    )

    def outside(name, callback):
        def observed(*args, **kwargs):
            locks = (
                worker._lock.locked(),
                worker._status_lock.locked(),
                bool(source and source._lock.locked()),
            )
            external.append((name, in_leaf[0], locks))
            if in_leaf[0]:
                raise RuntimeError("external work entered source leaf")
            return callback(*args, **kwargs)

        return observed

    if source is not None:
        admit = source.admit_start

        def guarded(validate):
            leaf_locks.append((worker._lock.locked(), worker._status_lock.locked()))

            def bounded():
                in_leaf[0] = True
                try:
                    validate()
                finally:
                    in_leaf[0] = False

            return admit(bounded)

        monkeypatch.setattr(source, "admit_start", guarded)
        monkeypatch.setattr(
            source, "is_current", outside("source advice", source.is_current)
        )
        snapshot = FakePublicationSource.snapshot.fget
        monkeypatch.setattr(
            FakePublicationSource, "snapshot", property(outside("snapshot", snapshot))
        )
    for name in ("_save_state", "_notify", "_utc_clock", "_sharing_enabled"):
        monkeypatch.setattr(worker, name, outside(name, getattr(worker, name)))
    monkeypatch.setattr(crypto, "sign_request", outside("sign", crypto.sign_request))
    transport = client.relay._transport

    def completed_http(*args, **kwargs):
        response = transport(*args, **kwargs)
        mono[0] += 0.125
        return response

    monkeypatch.setattr(client.relay, "_transport", outside("HTTP", completed_http))
    timing = worker._timing_context
    stage, start, complete = (
        timing._stage_publication,
        timing._validate_publication,
        worker._scheduler.completed,
    )

    def staged(*args, **kwargs):
        result = stage(*args, **kwargs)
        stages.append((timing._publisher, timing._next_stage_at))
        return result

    def started(*args, **kwargs):
        result = start(*args, **kwargs)
        starts.append(result)
        return result

    def charged(*args, **kwargs):
        completed.append((args, kwargs))
        return complete(*args, **kwargs)

    monkeypatch.setattr(timing, "_stage_publication", staged)
    monkeypatch.setattr(timing, "_validate_publication", started)
    monkeypatch.setattr(worker._scheduler, "completed", charged)
    revision = s.load(client.path).last_revision
    before = mono[0]
    thread, errors = completion_thread(worker, work, fence)
    thread.join(5)
    assert not thread.is_alive(), "completion reacquired a non-reentrant lock"
    assert reentries == [] and errors == []
    assert leaf_locks == (
        []
        if kind == "off"
        else [(True, False)] + [(True, True)] * (2 if error and error[0] == 401 else 1)
    )
    assert all(not under_leaf for _, under_leaf, _ in external)
    assert all(
        not any(locks)
        for name, _, locks in external
        if name in ("_save_state", "_notify", "HTTP", "sign")
    ), "I/O or notification ran under a completion lock"
    assert sum(name == "HTTP" for name, _, _ in external) == 1
    assert sum(name == "sign" for name, _, _ in external) == 1
    assert len(client.puts) == 2
    assert len(stages) == len(starts) == (kind == "publication")
    if kind == "publication":
        assert starts == [before], "completion recaptured actual request start"
        assert (timing._publisher, timing._next_stage_at) == stages[0]
    assert len(completed) == 1 and completed[0][0] == (work, before + 0.125)
    assert worker._scheduler.deadlines["publication"] == before + 0.625
    if error:
        assert worker._scheduler.retry_at[work.key] == before + 1.125
        assert worker.status().state == "error" and worker.status().detail == error[1]
    else:
        assert worker.status().state == ("refused" if kind == "off" else "active")
        assert worker.status().detail == (
            "db_continuity_lost" if kind == "off" else None
        )
    assert sum(name == "_save_state" for name, _, _ in external) == (
        2 if error and error[0] == 401 else 1
    )
    assert s.load(client.path).last_revision == (
        0 if error and error[0] == 401 else revision + 1
    )


def test_failed_combat_ack_does_not_gate_already_authorized_shared_read():
    from tests.test_fleetsharing_worker import COMBAT_DEVICE, rig
    from wingman.fleetsharing.client import FleetRelayError

    worker, client, _, mono = rig(
        device=replace(
            COMBAT_DEVICE,
            acknowledged_capabilities=(p.SHARED_CAPABILITY,),
        )
    )
    client.errors["acknowledge_capabilities"] = FleetRelayError(
        500, "server_error", "down"
    )
    drive(worker, mono, 20)
    assert any(op == "acknowledge_capabilities" for op, _, _ in client.calls)
    assert any(op == "read_snapshot" for op, _, _ in client.calls)
    assert not client.publish_calls


def test_source_revoked_during_actual_http_error_has_no_current_status_effect(
    tmp_path, monkeypatch
):
    worker, client, mono = publication_rig(tmp_path)
    source = ticket(mono[0])
    work, fence = selected_publication(worker, mono, source)
    previous = worker.status()
    transport = client.relay._transport

    def obsolete_error(*args, **kwargs):
        source.revoke()
        client.put_error = (403, "forbidden")
        return transport(*args, **kwargs)

    monkeypatch.setattr(client.relay, "_transport", obsolete_error)
    with pytest.raises(_Obsolete):
        worker._execute(work, fence)
    assert len(client.puts) == 1
    assert worker.status() == previous
    assert worker._catalogue is work.payload.catalogue
    assert not worker._last_published
    assert worker._scheduler.deadlines["publication"] == mono[0] + 0.5


def test_exact_staging_floor_never_becomes_zero_delay_busy_loop(tmp_path):
    def configure(worker, client, mono):
        fetch = client.fetch_eligibility

        def long_proof(**args):
            result = fetch(**args)
            return replace(
                result,
                characters=tuple(
                    replace(entry, expires_at="2026-09-07T12:01:00.000Z")
                    for entry in result.characters
                ),
            )

        client.fetch_eligibility = long_proof

    worker, client, mono = publication_rig(tmp_path, configure=configure)
    mono[0] = nextafter(1023.75, inf)
    for key in worker._due:
        worker._due[key] = 1100
    work, fence = selected_publication(worker, mono, ticket(mono[0]))
    worker._execute(work, fence)
    assert client.puts
    exact_floor = worker._timing_context._next_stage_at
    mono[0] = float(exact_floor)
    assert mono[0] < exact_floor  # Binary64 tie rounds DOWN across1024.
    worker.submit(ticket(mono[0], outgoing=9))
    wait, _ = worker._iterate()
    assert wait > 0, "exact stage floor must not round into a zero-delay refusal loop"
    assert len(client.puts) == 1
    mono[0] = nextafter(mono[0], inf)
    worker.iterate_once()
    assert len(client.puts) == 2


@pytest.mark.parametrize(
    "barrier", ["unwrap", "save", "signing", "prehook", "after_start"]
)
@pytest.mark.parametrize(
    "change", ["source", "off", "timing", "source_control", "automatic"]
)
def test_actual_publication_barriers_fence_before_start_and_late_completion(
    tmp_path, monkeypatch, barrier, change
):
    worker, client, mono = publication_rig(
        tmp_path,
        configure=lambda worker, client, mono: worker.set_source_watch(True),
    )
    source = ticket(mono[0])
    work, fence = selected_publication(worker, mono, source)
    revision = s.load(client.path).last_revision
    if barrier == "unwrap":
        owner, method = worker, "_unwrap_private_key"
    elif barrier == "save":
        owner, method = worker, "_save_state"
    elif barrier == "signing":
        owner, method = crypto, "sign_request"
    elif barrier == "prehook":
        owner, method = urllib.request, "Request"
    else:
        owner, method = client.relay, "_transport"
    original = getattr(owner, method)
    entered, release = threading.Event(), threading.Event()
    errors = []

    def held(*args, **kwargs):
        result = original(*args, **kwargs)
        entered.set()
        assert release.wait(5), "test did not release actual publication barrier"
        return result

    monkeypatch.setattr(owner, method, held)

    def execute():
        try:
            with worker._iteration_lock:
                worker._execute(work, fence)
        except BaseException as exc:  # noqa: BLE001 — forward thread failures, including pytest outcomes, to the asserting owner.
            errors.append(exc)

    thread = threading.Thread(target=execute)
    thread.start()
    try:
        assert entered.wait(5), "actual publication stage was never reached"
        if change == "source":
            source.revoke()
        elif change == "off":
            assert worker.request_participation(
                False, expected_generation=1, binding=worker.status().metadata.binding
            )
        elif change == "timing":
            worker.fence_timing("db_continuity_lost")
        elif change == "source_control":
            assert worker.request_source_start(1, UUID)
        else:
            observed = worker.status().automatic_status
            assert observed is not None
            assert worker.request_automatic(
                True,
                expected_generation=observed.consent.generation,
                expected_revision=observed.consent.revision,
                binding=worker.status().metadata.binding,
            )
        mono[0] += 0.25
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], _Obsolete), errors
    assert len(client.puts) == (barrier == "after_start")
    assert not worker._last_published
    assert worker._timing_context._publisher.associations
    saved = s.load(client.path).last_revision
    assert saved >= revision
    if barrier != "unwrap":
        assert saved == revision + 1
    if barrier == "after_start":
        assert worker._scheduler.deadlines["publication"] == mono[0] + 0.5


@pytest.mark.parametrize(
    "exception",
    [ValueError("source refused unexpectedly"), RuntimeError("poisoned port")],
)
def test_source_port_exception_is_not_laundered_into_timing_or_network_refusal(
    tmp_path, exception
):
    worker, client, mono = publication_rig(tmp_path)
    source = ticket(mono[0])
    work, fence = selected_publication(worker, mono, source)

    def fail(validate):
        raise exception

    source.admit_start = fail
    with pytest.raises(type(exception)) as caught:
        worker._execute(work, fence)
    assert caught.value is exception
    assert client.puts == []
    assert "publication" not in worker._scheduler.failures


@pytest.mark.parametrize(
    "kind,withdraw",
    [
        ("known_inactive", True),
        ("one_direction_available", True),
        ("unavailable", False),
        ("legacy", False),
        ("nan_deadline", False),
        ("invalid_numeric", False),
        ("missing_observation_id", False),
        ("future_activity", False),
        ("unknown_owner", False),
    ],
)
@pytest.mark.parametrize("eligible_bob", [True, False])
def test_any_uncertain_member_prevents_whole_inactivity_withdrawal(
    tmp_path, kind, withdraw, eligible_bob
):
    from tests.test_fleetsharing_remote_worker import _publication_case
    from tests.test_fleetsharing_worker import _source

    worker, client, mono = _publication_case(tmp_path)
    drive(worker, mono, 3)
    assert client.puts and len(client.puts[0]["rows"]) == 2
    count_before = len(client.puts)
    published = worker._last_published
    if not eligible_bob:
        fetch = client.fetch_eligibility

        def alice_only(**args):
            result = fetch(**args)
            return replace(
                result,
                characters=tuple(
                    entry for entry in result.characters if entry.character_id == 1
                ),
            )

        client.fetch_eligibility = alice_only
        worker.submit(None)
        for key in worker._due:
            worker._due[key] = 0 if key == "eligibility" else mono[0] + 60
        worker.iterate_once()
        assert [entry.character_id for entry in worker._eligibility.characters] == [1]
    alice = _source(0, mono[0], inactive=True).snapshot.rows[0]
    bob = _source(0, mono[0], character="Bob", inactive=True).snapshot.rows[0]
    if kind == "one_direction_available":
        bob = replace(bob, dps=None)
    elif kind == "unavailable":
        bob = replace(bob, dps=None, incoming_dps=None)
    elif kind == "legacy":
        bob = replace(bob, combat=None)
    elif kind == "nan_deadline":
        bob = replace(bob, combat=CombatActivity(float("nan"), (LIFETIME, 1)))
    elif kind == "invalid_numeric":
        bob = replace(bob, dps=p.MAX_DPS + 1)
    elif kind == "missing_observation_id":
        bob = replace(bob, combat=CombatActivity(mono[0] + 1))
    elif kind == "future_activity":
        bob = replace(bob, combat=CombatActivity(mono[0] + 31, (LIFETIME, 1)))
    elif kind == "unknown_owner":
        bob = replace(bob, character="Unknown")
    worker.submit(
        FakePublicationSource(
            FleetSnapshot(
                (alice, bob),
                StreamHealth("active"),
                sampled_at_mono=mono[0],
            )
        )
    )
    drive(worker, mono, 4)
    assert client.puts[count_before:] == (
        [{"protocol": 2, "sampled_at_ms": 0, "rows": []}] if withdraw else []
    )
    if not withdraw:
        assert worker._last_published is published


def test_revoked_selection_cannot_borrow_new_mailbox_authority(tmp_path):
    worker, client, mono = publication_rig(tmp_path)
    original = ticket(mono[0], outgoing=7)
    work, fence = selected_publication(worker, mono, original)
    original.revoke()
    mono[0] += 0.25
    fresh = ticket(mono[0], outgoing=99)
    worker.submit(fresh)
    with pytest.raises(_Obsolete):
        worker._execute(work, fence)
    assert client.puts == []
    assert worker._latest is fresh


def test_staging_refusal_keeps_previous_publication_and_never_sends_empty(tmp_path):
    worker, client, mono = publication_rig(tmp_path)
    work, fence = selected_publication(worker, mono, ticket(mono[0]))
    worker._execute(work, fence)
    mono[0] += 0.5
    previous = worker._last_published
    pins = worker._timing_context._publisher
    duplicate = EffectObservation("POINT", mono[0] + 28, (LIFETIME, 1))
    source = ticket(mono[0], effects=(duplicate, duplicate))
    work, fence = selected_publication(worker, mono, source)
    stamp = mono[0]
    with pytest.raises(_Obsolete):
        worker._execute(work, fence)
    assert len(client.puts) == 1 and client.puts[0]["rows"]
    assert worker._last_published is previous
    assert worker._timing_context._publisher is pins
    assert worker._timing_context._next_stage_at is not None, (
        "staging slot was refunded"
    )
    assert worker._timing_context._next_stage_at >= stamp + 0.5
    assert "publication" not in worker._scheduler.failures


def test_submit_and_planning_flood_allocate_no_pins_before_paced_selection(tmp_path):
    worker, client, mono = publication_rig(tmp_path)
    source = ticket(mono[0])
    pins = worker._timing_context._publisher
    for _ in range(1000):
        worker.submit(source)
        assert any(work.operation == "publish_snapshot" for work in worker._work(True))
    assert worker._latest is source
    assert worker._timing_context._publisher is pins
    assert worker._timing_context._next_stage_at is None
    work, fence = selected_publication(worker, mono, source)
    worker._execute(work, fence)
    assert client.puts
    assert len(worker._timing_context._publisher.associations) == 2


@pytest.mark.parametrize("restart", ["thread", "session"])
def test_original_measurement_retry_retains_wire_origins_across_reauthentication(
    tmp_path, restart
):
    worker, client, mono = publication_rig(tmp_path)
    source = ticket(mono[0], outgoing=7)
    work, fence = selected_publication(worker, mono, source)
    original_session = s.load(client.path).session_id
    client.put_error = (
        (401, "unauthorized") if restart == "session" else (500, "server_error")
    )
    worker._execute(work, fence)
    assert len(client.puts) == 1
    first = client.puts[0]
    context = worker._timing_context
    original_pins = tuple(context._publisher.associations.values())
    original_floor = context._next_stage_at
    client.put_error = None
    if restart == "thread":
        assert worker.stop() and worker.start()
    try:
        for _ in range(60):
            wait, _ = worker._iterate()
            if len(client.puts) > 1 or mono[0] >= source.snapshot.sampled_at_mono + 5:
                break
            mono[0] += wait  # Honor actual owner cadence, not a post-call500ms sleep.
        assert len(client.puts) == 2, worker.status()
        assert client.puts[-1] == first
        assert worker._timing_context is context
        assert context._next_stage_at >= original_floor
        assert all(
            context._publisher.associations[pin.evidence.key] is pin
            for pin in original_pins
        )
        if restart == "session":
            assert s.load(client.path).session_id != original_session
        assert worker._latest is source
    finally:
        assert worker.stop()


@pytest.mark.parametrize(
    "rights",
    [
        "approved_capabilities",
        "session_approved_capabilities",
        "acknowledged_capabilities",
    ],
)
@pytest.mark.parametrize("kind", ["combat", "inactive", "off"])
def test_final_held_disclosure_and_applicable_withdrawal_rights(
    tmp_path, monkeypatch, rights, kind
):
    worker, client, mono = publication_rig(tmp_path)
    source = ticket(mono[0])
    if kind != "combat":
        work, fence = selected_publication(worker, mono, source)
        worker._execute(work, fence)
        mono[0] += 0.5
    if kind == "inactive":
        row = source.snapshot.rows[0]
        source = FakePublicationSource(
            replace(
                source.snapshot,
                rows=(replace(row, dps=0, incoming_dps=0, combat=CombatActivity()),),
                sampled_at_mono=mono[0],
            )
        )
        work, fence = selected_publication(worker, mono, source)
    elif kind == "off":
        assert worker.request_participation(
            False, expected_generation=1, binding=worker.status().metadata.binding
        )
        worker._ingest()
        for _ in range(20):
            fence = worker._fence()
            work = worker._scheduler.choose(worker._work(False), mono[0])
            if work is not None and work.key == "withdraw":
                break
            wait, _ = worker._iterate()
            mono[0] += wait
        assert work is not None and work.key == "withdraw"
    else:
        work, fence = selected_publication(worker, mono, source)
    previous = worker._last_published
    count_before = len(client.puts)
    sign = crypto.sign_request
    reached = []

    def revoke_right(*args, **kwargs):
        result = sign(*args, **kwargs)
        reached.append(True)
        # Independent final held-state right, not a source-token substitution.
        worker._state = replace(
            worker._state,
            **{rights: (p.SHARED_CAPABILITY,) if kind == "combat" else ()},
        )
        return result

    monkeypatch.setattr(crypto, "sign_request", revoke_right)
    with pytest.raises(_Obsolete):
        worker._execute(work, fence)
    assert reached == [True]
    assert len(client.puts) == count_before
    assert worker._last_published is previous


@pytest.mark.parametrize("barrier", ["signing", "after_start"])
def test_source_inactivity_keeps_its_ticket_through_start_and_completion(
    tmp_path, monkeypatch, barrier
):
    worker, client, mono = publication_rig(tmp_path)
    work, fence = selected_publication(worker, mono, ticket(mono[0]))
    worker._execute(work, fence)
    previous = worker._last_published
    mono[0] += 0.5
    source = FakePublicationSource(
        FleetSnapshot((), StreamHealth("active"), sampled_at_mono=mono[0])
    )
    work, fence = selected_publication(worker, mono, source)
    owner, method = (
        (crypto, "sign_request")
        if barrier == "signing"
        else (client.relay, "_transport")
    )
    original = getattr(owner, method)

    def invalidate(*args, **kwargs):
        result = original(*args, **kwargs)
        source.revoke()
        return result

    monkeypatch.setattr(owner, method, invalidate)
    with pytest.raises(_Obsolete):
        worker._execute(work, fence)
    assert len(client.puts) == 1 + (barrier == "after_start")
    assert worker._last_published is previous


def test_committed_source_control_retires_selection_from_same_queue_generation(
    tmp_path,
):
    worker, client, mono = publication_rig(tmp_path)
    command_id = worker.request_source_start(1, UUID)
    assert command_id
    client.errors["control_source"] = FleetRelayError(500, "server_error", "try later")
    worker._due["eligibility"] = 0
    for key in worker._due:
        if key != "eligibility":
            worker._due[key] = mono[0] + 60
    for _ in range(60):
        wait, _ = worker._iterate()
        proof = worker._eligibility_proof
        if (
            client.source_requests
            and proof is not None
            and proof.response is worker._eligibility
            and proof.fence.source == worker._fence().source
        ):
            break
        mono[0] += wait
    assert client.source_requests, "actual signed source HTTP not reached"
    assert s.load(client.path).pending_source_commands
    source = ticket(mono[0])
    work, fence = selected_publication(worker, mono, source)
    # Selection already includes the submitted control's queue generation.
    assert fence.source == worker._fence().source
    assert work.payload.proof.fence.source == fence.source
    client.errors.clear()
    worker.submit(None)
    for _ in range(60):
        wait, _ = worker._iterate()
        if not s.load(client.path).pending_source_commands:
            break
        mono[0] += wait
    assert not s.load(client.path).pending_source_commands
    assert any(command.source_id == command_id for command in client.controls)
    assert len(client.source_requests) >= 2  # Failed and committed REAL signed HTTP.
    assert worker._fence().source == fence.source  # No intervening new queue fence.
    assert worker._fence().automatic > fence.automatic  # Own committed invalidation.
    assert mono[0] - source.snapshot.sampled_at_mono < 5
    with pytest.raises(_Obsolete):
        worker._execute(work, fence)
    assert client.puts == []


def test_d_consumer_held_real_put_keeps_test_source_delivery_nonblocking(
    tmp_path, monkeypatch
):
    """Consumer half only; the real coordinator composition test stays unmodified."""
    worker, client, mono = publication_rig(tmp_path)
    initial = ticket(mono[0], outgoing=7)
    work, fence = selected_publication(worker, mono, initial)
    entered, release = threading.Event(), threading.Event()
    errors = []
    transport = client.relay._transport

    def held(*args, **kwargs):
        result = transport(*args, **kwargs)
        entered.set()
        assert release.wait(5)
        return result

    monkeypatch.setattr(client.relay, "_transport", held)

    def execute():
        try:
            with worker._iteration_lock:
                worker._execute(work, fence)
        except BaseException as exc:  # noqa: BLE001 — forward thread failures, including pytest outcomes, to the asserting owner.
            errors.append(exc)

    thread = threading.Thread(target=execute)
    thread.start()
    try:
        assert entered.wait(5), "D consumer's actual HTTP barrier was not reached"
        pins = worker._timing_context._publisher
        before = time.monotonic()
        origin = mono[0]
        for n in range(1000):
            mono[0] = origin + n / 2000
            latest = ticket(mono[0], outgoing=n % 99)
            worker.submit(latest)
        assert time.monotonic() - before < 0.5
        assert worker._latest is latest
        assert worker._timing_context._publisher is pins
        assert len(pins.associations) == 2
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive() and errors == []
    assert len(client.puts) == 1 and client.puts[0]["rows"][0]["outgoing_dps"] == 7
    monkeypatch.setattr(client.relay, "_transport", transport)
    work, fence = selected_publication(worker, mono, latest)
    worker._execute(work, fence)
    assert len(client.puts) == 2 and client.puts[1]["rows"][0]["outgoing_dps"] == 9
    assert worker._latest is latest


@pytest.mark.parametrize("fault", ["advisory", "snapshot"])
def test_exceptional_local_source_does_not_suppress_independent_receiving(
    tmp_path, fault
):
    worker, client, mono = publication_rig(tmp_path)
    source = ticket(mono[0])
    if fault == "snapshot":

        class BrokenSnapshot(FakePublicationSource):
            @property
            def snapshot(self):
                raise OSError("unavailable original producer snapshot")

        source = BrokenSnapshot(source.snapshot)
    else:

        def failed_advice():
            raise RuntimeError("unavailable producer advice")

        source.is_current = failed_advice
    before = sum(op == "read_snapshot" for op, _, _ in client.calls)
    worker.submit(source)
    drive(worker, mono, 8)
    assert client.puts == []
    assert sum(op == "read_snapshot" for op, _, _ in client.calls) > before


def test_session_expiry_projection_cannot_extend_authority_by_utc_callback_wait(
    tmp_path,
):
    worker, client, mono = publication_rig(tmp_path)
    client.device = replace(
        client.device, session_expires_at="2026-09-07T12:00:08.000Z"
    )
    worker._needs_device = True

    def delayed_utc():
        result = NOW + timedelta(seconds=mono[0] - 1000)
        mono[0] += 0.25
        return result

    worker._utc_clock = delayed_utc
    worker.iterate_once()
    assert worker._state.session_expires_at == "2026-09-07T12:00:08.000Z"
    assert worker._expires_at <= 1008, (
        "UTC callback time extended original session authority"
    )


@pytest.mark.parametrize(
    "boundary,allowed",
    [
        ("anchor_equal", True),
        ("anchor_over", False),
        ("row", False),
        ("effect", False),
        ("proof", False),
        ("session", False),
    ],
)
def test_independent_deadlines_are_checked_after_real_leaf_wait(
    tmp_path, boundary, allowed
):
    from wingman.fleetsharing.client import FleetRelayError

    def configure(worker, client, mono):
        if boundary == "proof":
            fetch = client.fetch_eligibility

            def short(**args):
                result = fetch(**args)
                return replace(
                    result,
                    characters=tuple(
                        replace(entry, expires_at="2026-09-07T12:00:08.000Z")
                        for entry in result.characters
                    ),
                )

            client.fetch_eligibility = short
        elif boundary == "session":
            # A legitimate near-expiry session with failed renewal: other work
            # may use its remaining authority, but no later than its original end.
            client.device = replace(
                client.device, session_expires_at="2026-09-07T12:00:08.000Z"
            )
            client.errors["renew_session"] = FleetRelayError(
                500, "server_error", "renewal unavailable"
            )

    worker, client, mono = publication_rig(tmp_path, configure=configure)
    if boundary.startswith("anchor"):
        anchor = worker._timing_context._state.anchor
        mono[0] = float(anchor.received_at) + 59
        worker._due["read"] = worker._due["device"] = mono[0] + 60
        worker.iterate_once()  # Actual urgent eligibility refresh, not a new anchor.
        assert worker._timing_context._state.anchor is anchor
        target = float(anchor.received_at) + 60
        if boundary == "anchor_over":
            target = nextafter(target, inf)
    else:
        target = 1008 if boundary in ("proof", "session") else mono[0] + 0.5
    source = ticket(mono[0])
    if boundary in ("row", "effect"):
        row = source.snapshot.rows[0]
        activity = (
            replace(row.combat, expires_at_mono=target)
            if boundary == "row"
            else replace(
                row.combat,
                observations=(EffectObservation("POINT", target, (LIFETIME, 1), "A"),),
            )
        )
        source = FakePublicationSource(
            replace(source.snapshot, rows=(replace(row, combat=activity),))
        )
    # Isolate the ready publication rather than advancing an already-due read
    # into the very boundary this test is about to hold across.
    for key in worker._due:
        worker._due[key] = mono[0] + 60
    work, fence = selected_publication(worker, mono, source)
    entered, proceed, leaf = threading.Event(), threading.Event(), threading.Event()
    errors = []
    unwrap, admit = worker._unwrap_private_key, source.admit_start

    def held_unwrap(blob):
        entered.set()
        assert proceed.wait(5)
        return unwrap(blob)

    def entering_leaf(validate):
        leaf.set()
        return admit(validate)

    worker._unwrap_private_key = held_unwrap
    source.admit_start = entering_leaf

    def execute():
        try:
            with worker._iteration_lock:
                worker._execute(work, fence)
        except BaseException as exc:  # noqa: BLE001 — forward thread failures, including pytest outcomes, to the asserting owner.
            errors.append(exc)

    thread = threading.Thread(target=execute)
    thread.start()
    try:
        assert entered.wait(5), "prepared publication not reached"
        with source._lock:
            proceed.set()
            assert leaf.wait(5), "actual before_send did not wait for source leaf"
            assert mono[0] <= target
            mono[0] = target
    finally:
        proceed.set()
        thread.join(5)
    assert not thread.is_alive()
    if allowed:
        assert errors == [] and len(client.puts) == 1
    else:
        assert len(errors) == 1 and isinstance(errors[0], _Obsolete), errors
        assert client.puts == []
    assert "publication" not in worker._scheduler.failures
