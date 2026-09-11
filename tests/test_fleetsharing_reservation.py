"""Owner reserves response growth before accepting more durable control bytes."""

import json
from dataclasses import fields, replace

import pytest

from tests.fleetsharing_capacity_helpers import (
    fixture_bytes,
    maximal_state,
    source_id,
    start_boundary,
)
from tests.test_fleetsharing_capacity import DiskStore
from tests.test_fleetsharing_utf8 import (
    admitted_upgrade,
    approval_url,
    legacy_save,
    legacy_upgrade,
)
from tests.test_fleetsharing_worker import (
    DATE,
    DEVICE,
    EXPIRY,
    KEY,
    PAIRED_STATE,
    TOKEN,
    UUID,
    FakeRelayClient,
    _worker,
    drive,
)
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing import state as s


def disk_legacy(tmp_path, original):
    path = tmp_path / "legacy.json"
    legacy_save(path, original)
    store = DiskStore.__new__(DiskStore)
    store.path, store.saved, store.rejected = path, [], []
    assert store.load() == original
    return store


def retain_originals(original, store, client, replaced=()):
    pending = {c.source_id: c for c in store.load().pending_source_commands}
    for command in original.pending_source_commands:
        if command.source_id not in replaced:
            assert (
                pending.get(command.source_id) == command
                or client.source_intents.get(command.source_id) == command
            )
    assert all(saved.identity == original.identity for saved in store.saved)
    assert all(
        c in original.pending_source_commands
        for c in client.controls
        if isinstance(c, p.StartSource)
    )


def assert_tail_originals(original, state, store, client):
    # A retained UUID with a rewritten payload is not preservation, even if an
    # earlier attempt of that UUID was acknowledged by the relay.
    pending = {c.source_id: c for c in state.pending_source_commands}
    assert all(c in original.pending_source_commands for c in pending.values())
    for command in original.pending_source_commands:
        if command.source_id in pending:
            assert pending[command.source_id] == command
        else:
            assert client.source_intents.get(command.source_id) == command
    assert state.identity == original.identity
    assert all(saved.identity == original.identity for saved in store.saved)
    assert all(
        c in original.pending_source_commands
        for c in client.controls
        if isinstance(c, p.StartSource)
    )
    assert not store.rejected and not client.cadence_refusals


def drive_control_tail(
    worker, mono, turns, original, store, client, completed, *, fetch_sources=False
):
    # The old total turn count is a failure budget, not a per-phase allowance.
    # Completion callbacks assert disk immediately at the first cheap candidate:
    # another turn must not repair a missing write and hide an early publication.
    attempts, acknowledgements, errors = [], [], []
    fetches = 0
    control, fetch = client.control_source, client.fetch_sources

    def observe_control(**args):
        attempts.append(args["command"])
        result = control(**args)
        acknowledgements.append((args["command"], result))
        return result

    def observe_fetch(**args):
        nonlocal fetches
        result = fetch(**args)
        fetches += 1  # Failed attempts do not constitute resumption.
        return result

    def observe_status(status):
        # Capacity deferral is the fixture's premise, not a relay refusal.
        if status.state == "refused" or (
            status.state == "error" and status.detail != "source_queue_full"
        ):
            errors.append((status.state, status.detail))

    client.control_source, client.fetch_sources = observe_control, observe_fetch
    unsubscribe = worker.subscribe_status(observe_status)
    prior = None
    resumed = fetched = False
    try:
        for _ in range(turns):
            drive(worker, mono, 1)
            assert not errors
            if prior is None:
                state = completed()
                if state is None:
                    continue
                assert_tail_originals(original, state, store, client)
                # Deliberately exclude pre-existing acknowledgements. The Stop
                # replacement fixture already has one before its stale read.
                candidates = [
                    c
                    for c in original.pending_source_commands
                    if c in state.pending_source_commands
                    and client.source_intents.get(c.source_id) != c
                ]
                assert candidates, "no unacknowledged original Start at transition"
                prior = candidates[0]
                attempt_floor = len(attempts)
                ack_floor = len(acknowledgements)
                fetch_floor = fetches
                continue
            if not resumed and client.source_intents.get(prior.source_id) == prior:
                assert prior in attempts[attempt_floor:], "original Start not resumed"
                replies = [v for c, v in acknowledgements[ack_floor:] if c == prior]
                assert replies, "original Start lacks a NEW successful acknowledgement"
                assert all(v.source_id == prior.source_id for v in replies)
                assert all(v.state == "active" for v in replies)
                state = store.load()
                assert all(
                    c.source_id != prior.source_id
                    for c in state.pending_source_commands
                ), "resumed Start retirement was not persisted"
                assert_tail_originals(original, state, store, client)
                resumed = True
            fetched = fetches > fetch_floor
            if resumed and (not fetch_sources or fetched):
                break
        assert prior is not None, "target did not complete within original turn budget"
        assert resumed, "original Start did not resume within original turn budget"
        assert not fetch_sources or fetched, "no NEW successful post-transition fetch"
        return prior
    finally:
        unsubscribe()
        client.control_source, client.fetch_sources = control, fetch


@pytest.mark.parametrize("bound", [False, True])
def test_legacy_batch_reserves_generation_growth_and_recreates_after_deferred_save(
    tmp_path, monkeypatch, bound
):
    # Unbound: the first response must fit without a retry or restart. Bound:
    # maximum-width observations must survive deferred I/O and both owner restarts.
    original = replace(legacy_upgrade(), identity=maximal_state().identity)
    store = disk_legacy(tmp_path, original)
    assert store.path.stat().st_size <= 65536
    mono = [1000.0]
    client = FakeRelayClient(device=DEVICE)
    begin = client.begin_pairing
    responses = []

    def long_url(**kwargs):
        response = replace(begin(**kwargs), approval_url=approval_url())
        responses.append(response)
        return response

    client.begin_pairing = long_url
    worker = _worker(
        client, store=store, clock=lambda: mono[0], sharing_enabled=lambda: False
    )
    publications, journals, callback_errors = [], [], []

    def observe_url(status):
        # Capture first exposure, not completion's intermediate metadata push
        # after it clears the pairing journal but before it clears the old URL.
        if status.approval_url is not None and not publications:
            try:
                publications.append((status.approval_url, store.load().pending_pairing))
            except Exception as error:  # noqa: BLE001 - assert in the test, outside subscriber swallowing
                callback_errors.append(error)

    unsubscribe = worker.subscribe_status(observe_url)
    call = client._call

    def journal_before_send(operation, args, apply):
        if "revision" in args:
            try:
                journals.append((operation, args, store.load()))
            except Exception as error:  # noqa: BLE001 - assert in the test, outside owner swallowing
                callback_errors.append(error)
        return call(operation, args, apply)

    client._call = journal_before_send
    restarted = None
    try:
        worker.resume_pending()
        worker.iterate_once()
        assert not client.calls  # Loading still owes the startup bootstrap deadline.
        binding = worker.status().metadata.binding if bound else None
        if bound:
            assert binding is not None
        generation = p.INT4_MAX - 1 if bound else 1
        targets = tuple(
            source_id(i)
            for i in range(len(original.pending_source_commands), p.MAX_SOURCE_INTENTS)
        )
        for target in targets:
            client.source_views[target] = p.SourceView(
                target, generation, 1, "active", None, None
            )
            assert worker.request_source_stop(target, binding=binding)
        off = worker.request_participation(False)
        worker.iterate_once()
        queued = dict(worker._commands)
        assert queued and all(c.kind == "source" for c in queued.values())
        assert worker.status().local_inhibited
        assert store.load().pending_participation.intent_id == off
        assert not worker.status().source_results
        assert not client.calls
        summaries = {
            item.source_id: item.stage for item in worker.status().pending_sources
        }
        for command in queued.values():
            assert summaries[command.payload.source_id] == "queued"
            assert command.payload == p.StopSource(command.payload.source_id, 0)
        assert set(targets) <= {
            c.source_id for c in store.load().pending_source_commands
        } | {c.payload.source_id for c in queued.values()}
        retain_originals(original, store, client)
        if bound:
            assert worker.stop() and worker.start()
            assert worker._commands == queued, (
                "same-owner restart discarded deferred controls"
            )
            before = store.path.read_bytes()
            calls = len(client.calls)
            with monkeypatch.context() as patch:

                def fail(*args):
                    raise OSError("controlled atomic failure")

                patch.setattr(s.atomicio, "write_atomic", fail)
                drive(worker, mono, 3)
                assert store.path.read_bytes() == before
                assert worker._commands == queued
                assert worker.status().detail == "persistence_failed"
                # A response was received, but a failed save must not expose it
                # or authorize completion/device/control sends.
                assert len(responses) == 1
                assert all(call[0] == "begin_pairing" for call in client.calls[calls:])
                assert store.load().pending_pairing.pairing_id is None
                assert not publications, (
                    "approval URL published before durable response"
                )
                assert worker.status().approval_url is None
        else:
            # Stop AT the first successful response, before any later turn can
            # retry admission or complete pairing and erase its durable evidence.
            for _ in range(4):
                drive(worker, mono, 1)
                if responses:
                    break
            assert len(responses) == 1
            response = responses[0]
            admitted = store.load()
            assert admitted.pending_pairing == s.PendingPairing(
                "upgrade",
                response.pairing_id,
                response.approval_url,
                response.expires_at,
            ), "first pairing response was not saved"
            assert store.saved[-1] == admitted
            assert (
                worker.status().approval_url == response.approval_url == approval_url()
            )
            assert not callback_errors
            assert publications == [(approval_url(), admitted.pending_pairing)], (
                "approval URL published before durable response"
            )
            assert store.path.stat().st_size <= 65536
            assert [item[0] for item in client.calls] == ["begin_pairing"]
            assert not client.controls and not client.participation_calls
            assert admitted.pending_participation.intent_id == off
            assert worker.status().local_inhibited
        for _ in range(20):
            drive(worker, mono, 1)
            if not worker._commands:
                break
        assert not worker._commands
        assert any(
            saved.pending_pairing
            and saved.pending_pairing.approval_url == approval_url()
            for saved in store.saved
        )
        assert publications and not callback_errors
        assert all(
            pairing is not None and pairing.approval_url == url
            for url, pairing in publications
        ), "approval URL published before durable response"
        assert store.load().pending_participation.intent_id == off
        active = worker
        if bound:
            assert worker.stop()
            restarted = _worker(
                client,
                store=store,
                clock=lambda: mono[0],
                sharing_enabled=lambda: False,
            )
            restarted.resume_pending()
            active = restarted
        drive(active, mono, len(targets) + 40)
        assert not client.device.participation.enabled
        assert all(client.source_views[target].state == "ended" for target in targets)
        assert all(
            c.expected_generation == generation
            for c in client.controls
            if isinstance(c, p.StopSource)
        )
        # These snapshots came from the real loader BEFORE signed sends. Assert
        # here: an assertion in _call would be swallowed by the owner's fail-close.
        assert not callback_errors
        assert {"control_source", "set_participation"} <= {j[0] for j in journals}
        for operation, args, saved in journals:
            assert saved.last_revision == args["revision"]
            if operation == "control_source":
                assert args["command"] in saved.pending_source_commands
            if operation == "set_participation":
                assert saved.pending_participation.intent_id == off
                assert saved.pending_participation.attempted
                assert (
                    saved.pending_participation.expected_generation
                    == args["expected_generation"]
                )
        if not bound:
            assert len(responses) == len(client.pair_keys) == 1
        assert not store.rejected and not client.cadence_refusals
        retain_originals(original, store, client)
    finally:
        unsubscribe()
        assert worker.stop()
        if restarted is not None:
            assert restarted.stop()


def dense_store(tmp_path, *, participation=None, recovery=False):
    # Independent byte preparation; the actual writer still proves both sides
    # of the boundary before each distinct owner lifecycle starts.
    original = replace(
        PAIRED_STATE,
        identity=maximal_state().identity,
        pending_participation=participation,
        device_id=DEVICE.device_id,
        session_expires_at=DEVICE.session_expires_at,
        feature_enabled=DEVICE.feature_enabled,
        approved_capabilities=DEVICE.approved_capabilities,
        session_approved_capabilities=DEVICE.session_approved_capabilities,
        acknowledged_capabilities=DEVICE.acknowledged_capabilities,
        observed_participation=DEVICE.participation,
    )
    if recovery:
        original = replace(
            s.replace_session(original, None),
            pending_recovery=s.PendingRecovery(
                TOKEN, DATE, p.RecoveryChallenge(UUID, TOKEN, TOKEN, EXPIRY)
            ),
        )
    original, candidate = start_boundary(original)
    store = DiskStore(tmp_path / "dense.json", original)
    before = fixture_bytes(original)
    assert store.path.read_bytes() == before
    assert store.load() == original
    assert len(candidate.pending_source_commands) <= p.MAX_SOURCE_INTENTS
    with pytest.raises(s.CapacityError, match="size limit"):
        store.save(candidate)
    assert store.path.read_bytes() == before
    assert store.load() == original
    # Only the preparation refusal is expected. Keep every later owner failure
    # visible to the lifecycle assertions below.
    assert store.rejected == [candidate]
    store.rejected.clear()
    return store, original


@pytest.mark.parametrize("old_on", [False, True])
@pytest.mark.parametrize("recovery", [False, True])
def test_deferred_off_allows_bootstrap_and_prior_sources_not_old_participation(
    tmp_path, old_on, recovery
):
    # Allowing deferred metadata reads without suppressing their old intent
    # effects would acknowledge On or uninhibit before the new Off is durable.
    old = s.PendingParticipation(UUID, True, 0, True) if old_on else None
    store, original = dense_store(tmp_path, participation=old, recovery=recovery)
    mono = [1000.0]
    client = FakeRelayClient(device=replace(DEVICE, acknowledged_capabilities=()))
    if recovery:
        from wingman.fleetsharing import crypto

        client.admissions[(crypto.public_key_spki(KEY), TOKEN)] = (
            DATE,
            original.pending_recovery.challenge,
        )
    worker = _worker(
        client, store=store, clock=lambda: mono[0], sharing_enabled=lambda: False
    )
    statuses = []
    unsubscribe = worker.subscribe_status(statuses.append)
    try:
        off = worker.request_participation(False)
        worker.iterate_once()
        assert worker._commands["participation"].payload.intent_id == off
        assert store.load().pending_participation == old
        assert worker.status().participation == "queued"
        assert worker.status().local_inhibited

        def completed():
            if worker.status().participation != "acknowledged":
                return None
            state = store.load()
            assert worker.status().participation_intent_id == off
            assert not worker._commands
            assert state.pending_participation is None
            assert state.observed_participation == client.device.participation
            assert not state.observed_participation.enabled
            assert worker.status().local_inhibited
            assert all(status.local_inhibited for status in statuses)
            assert all(not enabled for enabled, _ in client.participation_calls)
            assert any(c[0] == "acknowledge_capabilities" for c in client.calls)
            if recovery:
                assert client.recoveries == 1 and not client.pair_keys
                assert state.pending_recovery is None
            return state

        resumed = drive_control_tail(
            worker, mono, 40, original, store, client, completed
        )
        assert resumed in original.pending_source_commands
        assert client.source_intents.get(resumed.source_id) == resumed
        assert resumed not in store.load().pending_source_commands
        assert not client.device.participation.enabled
        assert store.load().pending_participation is None
        assert not worker._commands
        assert all(status.local_inhibited for status in statuses)
        assert all(not enabled for enabled, _ in client.participation_calls)
        assert any(c[0] == "acknowledge_capabilities" for c in client.calls)
        if recovery:
            assert client.recoveries == 1
            assert not client.pair_keys
            assert store.load().pending_recovery is None
        assert not store.rejected and not client.cadence_refusals
        retain_originals(original, store, client)
    finally:
        unsubscribe()
        assert worker.stop()


@pytest.mark.parametrize("pairing", [False, True])
def test_control_reserve_dominates_current_mutable_fields_without_unused_slots(
    tmp_path, pairing
):
    maximum = maximal_state()
    original = replace(legacy_upgrade(), identity=maximum.identity)
    if not pairing:
        original = replace(original, pending_pairing=None)
    else:
        # Independent full-count witness: even true UTF-8 cannot save all 256
        # commands plus the response. Reservation must defer some Stops, not
        # merely pick a more compact encoding or silently lose the old journal.
        response = replace(
            original,
            pending_source_commands=(
                *original.pending_source_commands,
                *(
                    p.StopSource(source_id(i), 0)
                    for i in range(len(original.pending_source_commands), 256)
                ),
            ),
            pending_pairing=admitted_upgrade().pending_pairing,
            pending_participation=s.PendingParticipation(UUID, False),
        )
        assert len(response.pending_source_commands) == 256
        data = json.dumps(
            s._to_dict(response),
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        assert s._parse_v3(p.decode_json(data)) == response
        assert len(data) > 65536
        path = tmp_path / "overflow.json"
        legacy_save(path, original)
        before = path.read_bytes()
        assert len(before) <= 65536
        with pytest.raises(s.CapacityError, match="size limit"):
            s.save(path, response)
        assert path.read_bytes() == before
        assert s.load(path) == original
    # Existing legacy work is not new admission: its immutable Start payloads
    # must not be charged AGAIN as every unused future Stop slot.
    with pytest.raises(s.CapacityError):
        s.check_admission_capacity(original)
    s.check_control_capacity(original)
    admitted = original
    for i in range(len(original.pending_source_commands), p.MAX_SOURCE_INTENTS):
        candidate = replace(
            admitted,
            pending_source_commands=(
                *admitted.pending_source_commands,
                p.StopSource(source_id(i), 0),
            ),
        )
        try:
            s.check_control_capacity(candidate)
        except s.CapacityError:
            break
        admitted = candidate
    assert len(admitted.pending_source_commands) > len(original.pending_source_commands)
    if pairing:
        assert len(admitted.pending_source_commands) < p.MAX_SOURCE_INTENTS
    # Independent legal maximum metadata fixture, not an envelope used as its
    # own oracle. Pin model shapes so field/type growth requires bound review.
    assert {f.name for f in fields(p.StartSource)} == {
        "source_id",
        "character_id",
        "character_link_epoch",
        "intent_created_at",
        "expected_generation",
    }
    assert {f.name for f in fields(p.StopSource)} == {
        "source_id",
        "expected_generation",
    }
    future = replace(
        maximum,
        identity=admitted.identity,
        relay_origin=admitted.relay_origin,
        pending_source_commands=tuple(
            replace(c, expected_generation=p.INT4_MAX - 1)
            if isinstance(c, p.StopSource)
            else c
            for c in admitted.pending_source_commands
        ),
        pending_pairing=replace(maximum.pending_pairing, approval_url=approval_url())
        if pairing
        else None,
    )
    raw = s._to_dict(future)
    assert set(raw) == {"version", *(f.name for f in fields(s.SharingState))}
    assert s._parse_v3(p.decode_json(s._compact_utf8(raw).encode())) == future
    envelope = s._mutable_envelope(admitted)
    for name, value in raw.items():
        assert len(s._compact_utf8({name: value}).encode()) <= len(
            s._compact_utf8({name: envelope[name]}).encode()
        ), f"control reserve undercharges {name}"
    path = tmp_path / "future.json"
    s.save(path, future)
    assert path.stat().st_size <= s.MAX_STATE_FILE_BYTES
    assert s.load(path) == future


@pytest.mark.parametrize(
    "character",
    ["é", "漢", "𝄞", '"', "'", "/", "?", "%", "\ud800", "\udfff", "\x00", "\x1f"],
)
def test_control_url_reserve_uses_validated_scalar_width(character):
    prefix = PAIRED_STATE.relay_origin + "/"
    value = prefix + character * (2048 - len(prefix))
    candidate = replace(
        PAIRED_STATE,
        pending_pairing=s.PendingPairing("upgrade", "p" * 128, value, DATE),
    )
    raw = s._to_dict(candidate)
    if character in ("\ud800", "\udfff", "\x00", "\x1f"):
        # Six-byte escapes are encoder-compatible but not valid URL input; a
        # validator relaxation must revisit the four-byte reservation proof.
        with pytest.raises(ValueError):
            s._parse_v3(p.decode_json(json.dumps(raw).encode()))
    else:
        assert s._parse_v3(p.decode_json(s._compact_utf8(raw).encode())) == candidate
        assert len(s._compact_utf8({"url": value}).encode()) <= len(
            s._compact_utf8({"url": "𝄞" * 2048}).encode()
        )


@pytest.mark.parametrize("boundary", ["selection", "reply", "save"])
def test_replacement_of_deferred_off_invalidates_old_device_effects(tmp_path, boundary):
    store, original = dense_store(tmp_path)
    mono = [1000.0]
    client = FakeRelayClient(device=DEVICE)
    worker = _worker(
        client, store=store, clock=lambda: mono[0], sharing_enabled=lambda: False
    )
    replacements = []

    def replace_choice():
        replacements.append(worker.request_participation(True))

    if boundary == "reply":
        client.device = replace(DEVICE, participation=p.Participation(False, 2))
    if boundary == "selection":
        choose = worker._scheduler.choose

        def choose_then_replace(work, now):
            chosen = choose(work, now)
            if chosen and not replacements:
                assert chosen.operation == "fetch_device"
                replace_choice()
            return chosen

        worker._scheduler.choose = choose_then_replace
    elif boundary == "reply":
        fetch = client.fetch_device

        def fetch_then_replace(**args):
            result = fetch(**args)
            if not replacements:
                replace_choice()
            return result

        client.fetch_device = fetch_then_replace
    else:
        save = worker._save_state

        def save_then_replace(candidate):
            save(candidate)
            if client.calls and not replacements:
                replace_choice()

        worker._save_state = save_then_replace
    try:
        worker.request_participation(False)
        worker.iterate_once()
        assert len(replacements) == 1
        assert worker.status().participation_intent_id == replacements[0]
        assert worker.status().participation == "queued"
        assert worker.status().local_inhibited
        assert not client.participation_calls
        assert worker._commands["participation"].payload.intent_id == replacements[0]
        if boundary == "selection":
            assert not client.calls
        else:
            assert [c[0] for c in client.calls] == ["fetch_device"]
        if boundary == "reply":
            assert store.load().observed_participation == DEVICE.participation
            client.device = DEVICE

        def completed():
            if worker.status().participation != "acknowledged":
                return None
            state = store.load()
            assert worker.status().participation_intent_id == replacements[0]
            assert not worker._commands
            assert state.pending_participation is None
            assert state.observed_participation == DEVICE.participation
            assert client.device.participation == DEVICE.participation
            assert not worker.status().local_inhibited
            assert not client.participation_calls  # No obsolete Off CAS.
            return state

        resumed = drive_control_tail(
            worker, mono, 40, original, store, client, completed
        )
        assert resumed in original.pending_source_commands
        assert client.source_intents.get(resumed.source_id) == resumed
        assert resumed not in store.load().pending_source_commands
        assert not worker._commands
        assert worker.status().participation_intent_id == replacements[0]
        assert worker.status().participation == "acknowledged"
        assert not client.participation_calls  # Already On, not an obsolete Off CAS.
    finally:
        assert worker.stop()


def test_hot_api_submission_inside_pairing_save_preserves_reserved_batch(tmp_path):
    # Real Api membership/binding checks can see the old source cache inside a
    # successful pairing save. Safety comes from reservation, not cache absence.
    from tests.test_api import FakeWindow, make_state
    from tests.test_api_fleetsharing import Timers
    from wingman import settings
    from wingman.ui.api import Api

    original = replace(PAIRED_STATE, identity=maximal_state().identity)
    for command in legacy_upgrade().pending_source_commands:
        candidate = replace(
            original,
            pending_source_commands=(*original.pending_source_commands, command),
        )
        try:
            s.check_admission_capacity(candidate)
        except s.CapacityError:
            break
        original = candidate
    assert original.pending_source_commands
    store = disk_legacy(tmp_path, original)
    mono = [1000.0]
    client = FakeRelayClient(device=DEVICE)
    begin = client.begin_pairing
    client.begin_pairing = lambda **kw: replace(
        begin(**kw), approval_url=approval_url()
    )
    worker = _worker(
        client, store=store, clock=lambda: mono[0], sharing_enabled=lambda: False
    )
    app = make_state(tmp_path, **settings.load())
    app.settings["fleet_sharing"]["enabled"] = False
    timers = Timers()
    api = Api(app, fleet_sharing=worker, timer=timers)
    api._window = FakeWindow()
    try:
        targets = tuple(
            source_id(i)
            for i in range(len(original.pending_source_commands), p.MAX_SOURCE_INTENTS)
        )
        for target in targets:
            client.source_views[target] = p.SourceView(
                target, 1, 1, "active", None, None
            )
        assert api.fleet_sharing_watch(True)["queued"]
        for _ in range(20):
            drive(worker, mono, 1)
            if api.fleet_sharing_state()["sources"] is not None:
                break
        assert api.fleet_sharing_state()["sources"] is not None
        binding = api.fleet_sharing_state()["metadata"]["binding"]
        old_status = worker.status()
        injected, submissions, callback_errors = [], [], []
        save = worker._save_state

        def save_then_submit(candidate):
            save(candidate)
            if candidate.pending_pairing and not injected:
                injected.append(True)
                try:
                    for target in targets[:-1]:
                        submissions.append(
                            api.fleet_sharing_stop_source(target, binding)
                        )
                    submissions.append(api.fleet_sharing_set_enabled(False))
                except Exception as error:  # noqa: BLE001 - assert outside the owner's save-failure swallowing
                    callback_errors.append(error)

        worker._save_state = save_then_submit
        pairing = api.fleet_sharing_pair("upgrade")
        assert pairing["queued"]
        worker.iterate_once()
        assert not callback_errors
        assert len(submissions) == len(targets)
        assert all(result["queued"] for result in submissions)
        off = submissions[-1]["intent_id"]
        assert injected and store.load().pending_pairing
        assert api.fleet_sharing_state()["sources"] is not None
        assert worker.stop() and worker.start()
        drive(worker, mono, 2)
        assert api.fleet_sharing_state()["sources"] is None
        api._receive_fleet_sharing_status(old_status)
        assert api.fleet_sharing_state()["sources"] is None
        assert not api.fleet_sharing_stop_source(targets[-1], binding)["queued"]
        assert store.load().pending_pairing.approval_url == approval_url()

        def completed():
            if not (
                all(client.source_views[t].state == "ended" for t in targets[:-1])
                and not client.device.participation.enabled
                and worker.status().pairing == "acknowledged"
            ):
                return None
            state = store.load()
            status = worker.status()
            assert not callback_errors
            assert not worker._commands
            assert state.pending_pairing is None and state.pending_recovery is None
            assert state.session_id == client.active_session != original.session_id
            assert status.pairing_action_id == pairing["action_id"]
            assert status.approval_url is None
            assert status.participation_intent_id == off
            assert status.participation == "acknowledged" and status.local_inhibited
            assert state.pending_participation is None
            assert state.observed_participation == client.device.participation
            assert client.source_views[targets[-1]].state == "active"
            assert not any(
                isinstance(c, p.StopSource) for c in state.pending_source_commands
            )
            return state

        resumed = drive_control_tail(
            worker,
            mono,
            len(targets) + 55,
            original,
            store,
            client,
            completed,
            fetch_sources=True,
        )
        assert resumed in original.pending_source_commands
        assert client.source_intents.get(resumed.source_id) == resumed
        assert resumed not in store.load().pending_source_commands
        assert all(client.source_views[t].state == "ended" for t in targets[:-1])
        assert client.source_views[targets[-1]].state == "active"
        assert not client.device.participation.enabled
        assert not store.rejected and not client.cadence_refusals
        retain_originals(original, store, client)
    finally:
        assert api.shutdown_fleet_sharing()
        assert worker.stop()
        assert not timers.pending
        assert all(not subs for subs in worker._subscribers.values())


@pytest.mark.parametrize("boundary", ["selection", "reply", "save"])
def test_replacement_of_deferred_stop_fences_source_observation(tmp_path, boundary):
    # A known deferred Stop permits reconciliation, but a same-UUID replacement
    # at any boundary must not inherit that permission or retire old work.
    original = replace(
        PAIRED_STATE,
        pending_source_commands=legacy_upgrade().pending_source_commands
        + tuple(
            p.StartSource(source_id(i), 1, UUID, DATE)
            for i in range(200, p.MAX_SOURCE_INTENTS)
        ),
    )
    store = DiskStore(tmp_path / "full-count.json", original)
    mono = [1000.0]
    client = FakeRelayClient(device=DEVICE)
    worker = _worker(
        client, store=store, clock=lambda: mono[0], sharing_enabled=lambda: False
    )
    target = source_id(p.MAX_SOURCE_INTENTS)
    acknowledged = original.pending_source_commands[0]
    client.source_views[acknowledged.source_id] = p.SourceView(
        acknowledged.source_id, 1, 1, "active", None, None
    )
    client.source_intents[acknowledged.source_id] = acknowledged
    replaced = []

    def replace_stop():
        replaced.append(True)
        assert worker.request_source_stop(target, expected_generation=17)

    if boundary == "selection":
        choose = worker._scheduler.choose

        def choose_then_replace(work, now):
            chosen = choose(work, now)
            if chosen and chosen.operation == "fetch_sources" and not replaced:
                replace_stop()
            return chosen

        worker._scheduler.choose = choose_then_replace
    elif boundary == "reply":
        fetch = client.fetch_sources

        def fetch_then_replace(**args):
            result = fetch(**args)
            if not replaced:
                replace_stop()
            return result

        client.fetch_sources = fetch_then_replace
    else:
        save = worker._save_state

        def save_then_replace(candidate):
            save(candidate)
            if client.calls and client.calls[-1][0] == "fetch_sources" and not replaced:
                replace_stop()

        worker._save_state = save_then_replace
    try:
        assert worker.request_source_stop(target)
        for _ in range(10):
            drive(worker, mono, 1)
            if replaced:
                break
        assert replaced
        assert worker._commands["source:" + target].payload == p.StopSource(target, 17)
        assert worker.status().source_control == "queued"
        assert worker.status().sources is None
        assert store.load().pending_source_commands == (
            original.pending_source_commands[1:]
            if boundary == "save"
            else original.pending_source_commands
        )

        def completed():
            view = client.source_views.get(target)
            if view is None or view.state != "ended":
                return None
            state = store.load()
            assert not worker._commands
            assert all(c.source_id != target for c in state.pending_source_commands)
            assert worker.status().source_control == "acknowledged"
            return state

        resumed = drive_control_tail(
            worker, mono, 30, original, store, client, completed
        )
        assert resumed in original.pending_source_commands
        assert client.source_intents.get(resumed.source_id) == resumed
        assert resumed not in store.load().pending_source_commands
        assert client.source_views[target].state == "ended"
        assert not store.rejected and not client.cadence_refusals
        retain_originals(original, store, client)
    finally:
        assert worker.stop()
