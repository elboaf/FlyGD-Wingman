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
from tests.test_fleetsharing_utf8 import approval_url, legacy_save, legacy_upgrade
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


@pytest.mark.parametrize("bound", [False, True])
def test_legacy_batch_reserves_generation_growth_and_recreates_after_deferred_save(
    tmp_path, monkeypatch, bound
):
    # Removing control reservation saves every small-generation Stop before the
    # older URL arrives. It then cannot admit that URL or make any server progress.
    original = replace(legacy_upgrade(), identity=maximal_state().identity)
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
    restarted = None
    try:
        worker.resume_pending()
        worker.iterate_once()
        binding = worker.status().metadata.binding if bound else None
        targets = tuple(
            source_id(i)
            for i in range(len(original.pending_source_commands), p.MAX_SOURCE_INTENTS)
        )
        for target in targets:
            client.source_views[target] = p.SourceView(
                target, p.INT4_MAX - 1, 1, "active", None, None
            )
            assert worker.request_source_stop(target, binding=binding)
        off = worker.request_participation(False)
        worker.iterate_once()
        queued = dict(worker._commands)
        assert queued and all(c.kind == "source" for c in queued.values())
        assert worker.status().local_inhibited
        assert store.load().pending_participation.intent_id == off
        assert not worker.status().source_results
        summaries = {
            item.source_id: item.stage for item in worker.status().pending_sources
        }
        for command in queued.values():
            assert summaries[command.payload.source_id] == "queued"
            assert command.payload == p.StopSource(command.payload.source_id, 0)
        assert set(targets) <= {
            c.source_id for c in store.load().pending_source_commands
        } | {c.payload.source_id for c in queued.values()}
        assert worker.stop() and worker.start()  # Same owner retains unsaved choices.
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
            # Pair admission may be sent once, but its failed save cannot lead
            # to completion/device/control sends or a fabricated durable URL.
            assert all(call[0] == "begin_pairing" for call in client.calls[calls:])
            assert store.load().pending_pairing.pairing_id is None
        # Check the actual disk journal before every signed send, not a planner
        # approximation. It must preserve the attempted revision and CAS intent.
        call = client._call

        def journal_before_send(operation, args, apply):
            saved = store.load()
            if "revision" in args:
                assert saved.last_revision == args["revision"]
                if operation == "control_source":
                    assert args["command"] in saved.pending_source_commands
                if operation == "set_participation":
                    assert saved.pending_participation.attempted
                    assert (
                        saved.pending_participation.expected_generation
                        == args["expected_generation"]
                    )
            return call(operation, args, apply)

        client._call = journal_before_send
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
        assert store.load().pending_participation.intent_id == off
        assert worker.stop()
        restarted = _worker(
            client, store=store, clock=lambda: mono[0], sharing_enabled=lambda: False
        )
        restarted.resume_pending()
        drive(restarted, mono, len(targets) + 40)
        assert not client.device.participation.enabled
        assert all(client.source_views[target].state == "ended" for target in targets)
        assert all(
            c.expected_generation == p.INT4_MAX - 1
            for c in client.controls
            if isinstance(c, p.StopSource)
        )
        assert not store.rejected and not client.cadence_refusals
        retain_originals(original, store, client)
    finally:
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
        drive(worker, mono, 40)
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
        )
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
    store, _ = dense_store(tmp_path)
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
        drive(worker, mono, 40)
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
        injected = []
        save = worker._save_state

        def save_then_submit(candidate):
            save(candidate)
            if candidate.pending_pairing and not injected:
                injected.append(True)
                assert all(
                    api.fleet_sharing_stop_source(t, binding)["queued"]
                    for t in targets[:-1]
                )
                assert api.fleet_sharing_set_enabled(False)["queued"]

        worker._save_state = save_then_submit
        assert api.fleet_sharing_pair("upgrade")["queued"]
        worker.iterate_once()
        assert injected and store.load().pending_pairing
        assert api.fleet_sharing_state()["sources"] is not None
        assert worker.stop() and worker.start()
        drive(worker, mono, 2)
        assert api.fleet_sharing_state()["sources"] is None
        api._receive_fleet_sharing_status(old_status)
        assert api.fleet_sharing_state()["sources"] is None
        assert not api.fleet_sharing_stop_source(targets[-1], binding)["queued"]
        assert store.load().pending_pairing.approval_url == approval_url()
        drive(worker, mono, len(targets) + 55)
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
        drive(worker, mono, 30)
        assert client.source_views[target].state == "ended"
        assert not store.rejected and not client.cadence_refusals
        retain_originals(original, store, client)
    finally:
        assert worker.stop()
