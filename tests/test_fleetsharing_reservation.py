"""State4 owner reservations — exact replacement, response/save and restart barriers.

No sub-256 byte deferral exists under state4. Tests retain the original owner
barriers with full-count journals, real atomic failures and current closed DTOs.
"""

import json
from dataclasses import replace

import pytest

from tests.fleetsharing_capacity_helpers import maximal_state, source_id
from tests.fleetsharing_worker_control_helpers import ControlRelay
from tests.test_fleetsharing_capacity import DiskStore, full_sources
from tests.test_fleetsharing_utf8 import approval_url, upgrade_state
from tests.test_fleetsharing_worker import (
    DATE,
    DEVICE,
    PAIRED_STATE,
    TOKEN,
    UUID,
    FakeRelayClient,
    _worker,
    drive,
)
from tests.test_fleetsharing_worker_state4 import file_rig
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing import state as s


@pytest.mark.parametrize("bound", [False, True])
def test_batch_reserves_pairing_response_growth_and_restarts_after_save_failure(
    tmp_path, monkeypatch, bound
):
    original = replace(
        upgrade_state(),
        pending_source_commands=full_sources(),
        identity=maximal_state().identity,
    )
    worker, _, store, mono = file_rig(tmp_path, original)
    relay = ControlRelay(worker, store)
    relay.approval_url = approval_url()
    exposures, reached = [], []
    worker.subscribe_status(
        lambda value: (
            exposures.append((value.approval_url, s.load(store.path).pending_pairing))
            if value.approval_url
            else None
        )
    )
    write = s.atomicio.write_atomic

    def save(path, text):
        raw = json.loads(text)
        if (
            bound
            and raw["pending_pairing"]
            and raw["pending_pairing"]["approval_url"]
            and not reached
        ):
            reached.append(True)
            raise OSError("response write unavailable")
        write(path, text)

    monkeypatch.setattr(s.atomicio, "write_atomic", save)
    worker.resume_pending()
    for _ in range(8):
        drive(worker, mono, 1)
        if reached or exposures:
            break
    if bound:
        assert reached == [True]
        assert not exposures and s.load(store.path) == original
        assert worker.stop()
        worker = _worker(
            FakeRelayClient(device=DEVICE),
            store=store,
            timing_context=worker._timing_context,
            utc_clock=worker._utc_clock,
            sharing_enabled=lambda: False,
        )
        relay.worker = worker
        from wingman.fleetsharing.client import FleetRelayClient

        worker._client_factory = lambda origin: FleetRelayClient(
            origin, transport=relay.transport
        )
        worker.subscribe_status(
            lambda value: (
                exposures.append(
                    (value.approval_url, s.load(store.path).pending_pairing)
                )
                if value.approval_url
                else None
            )
        )
        worker.resume_pending()
        drive(worker, mono, 6)
    assert exposures and all(
        url == pending.approval_url == approval_url() for url, pending in exposures
    )
    saved = s.load(store.path)
    assert saved.identity == original.identity
    assert saved.pending_source_commands == original.pending_source_commands
    assert saved.pending_pairing.approval_url == approval_url()
    assert all(value.identity == original.identity for value in store.saves)


@pytest.mark.parametrize("old_on", [False, True])
@pytest.mark.parametrize("recovery", [False, True])
def test_full_count_off_bootstrap_preserves_prior_sources_and_old_choice(
    tmp_path, old_on, recovery
):
    pending = s.PendingParticipation(UUID, True, 0, True) if old_on else None
    original = replace(
        PAIRED_STATE,
        pending_source_commands=full_sources(),
        pending_participation=pending,
    )
    if recovery:
        original = replace(
            s.replace_session(original, None),
            pending_recovery=s.PendingRecovery(TOKEN, DATE),
        )
    worker, _, store, mono = file_rig(tmp_path, original)
    relay = ControlRelay(worker, store)
    worker.resume_pending()
    drive(worker, mono, 6)
    retained = s.load(store.path).pending_participation
    action = worker.request_participation(
        False,
        expected_generation=1,
        binding=worker.status().metadata.binding,
        supersedes=retained,
    )
    assert action
    drive(worker, mono, 12)
    saved = s.load(store.path)
    assert (
        saved.pending_participation is None and not relay.device.participation.enabled
    )
    assert saved.pending_source_commands == original.pending_source_commands
    assert saved.identity == original.identity
    requests = [
        (request, state)
        for request, state in relay.calls
        if request.full_url.endswith("/participation")
    ]
    assert len(requests) == 1 and json.loads(requests[0][0].data)["enabled"] is False
    assert requests[0][1].pending_participation.intent_id == action
    if recovery:
        begins = [
            (request, state)
            for request, state in relay.calls
            if request.full_url.endswith("/recovery-challenges")
        ]
        assert begins and all(
            state.pending_recovery.request_id == TOKEN
            and state.pending_recovery.issued_at == DATE
            for request, state in begins
        )
        completions = [
            state
            for request, state in relay.calls
            if "/recovery-challenges/" in request.full_url
        ]
        assert (
            len(completions) == 1
            and completions[0].pending_recovery.completion_attempted
        )
        assert saved.pending_recovery is None


@pytest.mark.parametrize("pairing", [False, True])
def test_control_reserve_dominates_current_mutable_fields_without_unused_slots(
    tmp_path, pairing
):
    maximum = maximal_state(stops=True)
    candidate = maximum if pairing else replace(maximum, pending_pairing=None)
    s.check_admission_capacity(candidate)
    s.check_control_capacity(candidate)
    path = tmp_path / "maximum.json"
    s.save(path, candidate)
    assert s.load(path) == candidate
    assert len(candidate.pending_source_commands) == p.MAX_SOURCE_INTENTS
    assert all(
        len(s._compact_utf8(p.source_command_body(command)).encode())
        <= s.MAX_SOURCE_COMMAND_BYTES
        for command in candidate.pending_source_commands
    )
    assert path.stat().st_size <= s.MAX_STATE_FILE_BYTES


@pytest.mark.parametrize(
    "character",
    ["é", "漢", "𝄞", '"', "'", "/", "?", "%", "\ud800", "\udfff", "\x00", "\x1f"],
)
def test_control_url_reserve_uses_validated_scalar_width(character):
    prefix = PAIRED_STATE.relay_origin + "/"
    url = prefix + character * (2048 - len(prefix))
    candidate = replace(
        PAIRED_STATE, pending_pairing=s.PendingPairing("upgrade", UUID, url, DATE)
    )
    if character in ("\ud800", "\udfff", "\x00", "\x1f"):
        with pytest.raises(ValueError):
            s.check_admission_capacity(candidate)
    else:
        s.check_admission_capacity(candidate)
        assert (
            s._parse_v4(p.decode_json(s._compact_utf8(s._to_dict(candidate)).encode()))
            == candidate
        )


@pytest.mark.parametrize("boundary", ["selection", "reply", "save"])
def test_replacement_of_off_invalidates_old_device_effects(
    tmp_path, monkeypatch, boundary
):
    worker, _, store, mono = file_rig(
        tmp_path,
        replace(PAIRED_STATE, pending_source_commands=full_sources()),
        enabled=True,
    )
    relay = ControlRelay(worker, store)
    drive(worker, mono, 4)
    assert worker.request_participation(
        False, expected_generation=1, binding=worker.status().metadata.binding
    )
    replacements, witnessed, reply_snapshots = [], [], []
    if boundary == "reply":
        assert s.load(store.path).observed_participation == p.Participation(True, 1)
        relay.device = replace(DEVICE, participation=p.Participation(False, 2))

    def replace_choice():
        witnessed.append(True)
        replacements.append(
            worker.request_participation(
                True,
                expected_generation=1,
                binding=worker.status().metadata.binding,
                supersedes=worker._state.pending_participation,
            )
        )

    if boundary == "selection":
        choose = worker._scheduler.choose

        def selected(work, now):
            chosen = choose(work, now)
            if chosen and chosen.operation == "fetch_device" and not witnessed:
                replace_choice()
            return chosen

        monkeypatch.setattr(worker._scheduler, "choose", selected)
    elif boundary == "reply":

        def reply(request, saved):
            if request.full_url.endswith("/device") and not witnessed:
                reply_snapshots.append((saved, store.path.read_bytes(), relay.device))
                replace_choice()

        relay.after = reply
    else:
        write = s.atomicio.write_atomic

        def save(path, text):
            write(path, text)
            if (
                relay.calls[-1][0].full_url.endswith("/device")
                and json.loads(text)["pending_participation"]
                and not witnessed
            ):
                replace_choice()

        monkeypatch.setattr(s.atomicio, "write_atomic", save)
    for _ in range(6):
        drive(worker, mono, 1)
        if witnessed:
            break
    assert witnessed == [True] and replacements[0]
    if boundary == "reply":
        # Check before any later owner turn can repair an admitted stale response.
        before_reply, before_bytes, stale_device = reply_snapshots[0]
        assert stale_device.participation == p.Participation(False, 2)
        assert before_reply.observed_participation == p.Participation(True, 1)
        assert s.load(store.path) == before_reply, (
            "stale Device reply changed saved state"
        )
        assert store.path.read_bytes() == before_bytes
        assert worker._state == before_reply
        old_off = before_reply.pending_participation
        assert old_off and not old_off.enabled and old_off.expected_generation == 1
        queued_on = worker._commands["participation"]
        assert queued_on.supersedes == old_off
        assert queued_on.payload.intent_id == replacements[0]
        assert queued_on.payload.enabled and queued_on.payload.expected_generation == 1
    assert worker.status().participation == "queued"
    assert worker.status().participation_intent_id == replacements[0]
    drive(worker, mono, 12)
    if boundary == "reply":
        # Only a subsequent current GET may install Off/gen2. It does not rebase
        # the queued On/CAS1; progress needs a new explicit whole confirmation.
        current = s.load(store.path)
        assert current.observed_participation == p.Participation(False, 2)
        assert current.pending_participation == queued_on.payload
        assert worker.status().participation == "needs_confirmation"
        confirmed = worker.confirm_participation(
            replacements[0],
            expected_generation=2,
            binding=worker.status().metadata.binding,
        )
        assert confirmed and confirmed != replacements[0]
        confirmed_on = worker._commands["participation"]
        assert confirmed_on.supersedes == queued_on.payload
        assert confirmed_on.payload == s.PendingParticipation(confirmed, True, 2)
        drive(worker, mono, 12)
    saved = s.load(store.path)
    assert saved.pending_source_commands == full_sources()
    assert saved.pending_participation is None and relay.device.participation.enabled
    puts = [
        (json.loads(request.data), state.pending_participation)
        for request, state in relay.calls
        if request.full_url.endswith("/participation")
    ]
    assert all(body["enabled"] for body, _ in puts)
    if boundary == "reply":
        assert len(puts) == 1
        body, attempted = puts[0]
        assert body == {"protocol": 2, "enabled": True, "expected_generation": 2}
        assert attempted == replace(confirmed_on.payload, attempted=True)
        assert saved.observed_participation == p.Participation(True, 3)


def test_stale_device_reply_guard_kills_in_memory_fence_mutant(tmp_path, monkeypatch):
    from wingman.fleetsharing.worker import FleetSharingWorker

    check = FleetSharingWorker._check_locked

    def admit_stale_device(self, fence, *, work=None):
        # Remove only Device's queued-choice/generation fence, not identity/session.
        if work is not None and work.operation == "fetch_device":
            work = replace(work, operation="fetch_receipt")
        return check(self, fence, work=work)

    monkeypatch.setattr(FleetSharingWorker, "_check_locked", admit_stale_device)
    with pytest.raises(AssertionError, match="stale Device reply changed saved state"):
        test_replacement_of_off_invalidates_old_device_effects(
            tmp_path, monkeypatch, boundary="reply"
        )


@pytest.mark.parametrize("boundary", ["selection", "reply", "save"])
def test_replacement_of_stop_fences_source_observation_without_cas_rebase(
    tmp_path, monkeypatch, boundary
):
    sources = full_sources()
    worker, _, store, mono = file_rig(
        tmp_path, replace(PAIRED_STATE, pending_source_commands=sources), enabled=True
    )
    relay = ControlRelay(worker, store)
    drive(worker, mono, 4)
    target = sources[0].source_id
    assert worker.request_source_stop(
        target, expected_generation=0, expected_automatic=None, supersedes=sources[0]
    )
    reached = []

    def replace_stop():
        reached.append(None)
        old = next(
            c for c in worker._state.pending_source_commands if c.source_id == target
        )
        reached[0] = worker.request_source_stop(
            target, expected_generation=17, expected_automatic=None, supersedes=old
        )

    if boundary == "selection":
        choose = worker._scheduler.choose

        def selected(work, now):
            chosen = choose(work, now)
            if chosen and chosen.operation == "fetch_receipt" and not reached:
                replace_stop()
            return chosen

        monkeypatch.setattr(worker._scheduler, "choose", selected)
    elif boundary == "reply":

        def reply(request, saved):
            if "/receipts/" in request.full_url and not reached:
                replace_stop()

        relay.after = reply
    else:
        write = s.atomicio.write_atomic

        def save(path, text):
            write(path, text)
            raw = json.loads(text)
            if (
                any(
                    isinstance(c, p.SourceStop)
                    for c in worker._state.pending_source_commands
                )
                and any(
                    c["operation"] == "stop" for c in raw["pending_source_commands"]
                )
                and not reached
            ):
                replace_stop()

        monkeypatch.setattr(s.atomicio, "write_atomic", save)
    for _ in range(8):
        drive(worker, mono, 1)
        if reached:
            break
    assert reached == [True]
    drive(worker, mono, 12)
    pending = s.load(store.path).pending_source_commands
    replacement = next(c for c in pending if c.source_id == target)
    assert replacement.expected_generation == 17
    assert tuple(c for c in pending if c.source_id != target) == sources[1:]
    assert not relay.receipts
    puts = [
        p.parse_source_command(json.loads(request.data))
        for request, _ in relay.calls
        if request.method == "PUT" and request.full_url.endswith("/sources")
    ]
    assert puts and all(command == replacement for command in puts)


def test_hot_worker_submission_inside_pairing_save_preserves_reserved_batch(tmp_path):
    original = replace(PAIRED_STATE, pending_source_commands=full_sources())
    worker, _, store, mono = file_rig(tmp_path, original, enabled=True)
    relay = ControlRelay(worker, store)
    relay.approved = True
    drive(worker, mono, 4)
    save = worker._save_state
    submissions = []

    def saving(candidate):
        save(candidate)
        if candidate.pending_pairing and not submissions:
            submissions.append(True)
            old = candidate.pending_source_commands[0]
            submissions.append(
                worker.request_source_stop(
                    old.source_id,
                    expected_generation=0,
                    expected_automatic=None,
                    supersedes=old,
                    binding=worker.status().metadata.binding,
                )
            )
            submissions.append(worker.request_participation(False))

    worker._save_state = saving
    assert worker.request_pairing(mode="upgrade")
    worker.iterate_once()
    assert len(submissions) == 3 and all(submissions)
    assert worker.status().participation == "queued"
    drive(worker, mono, 6)
    pending = s.load(store.path).pending_participation
    assert pending and not pending.enabled
    assert worker.confirm_participation(
        pending.intent_id,
        expected_generation=1,
        binding=worker.status().metadata.binding,
    )
    drive(worker, mono, 12)
    saved = s.load(store.path)
    assert (
        saved.pending_participation is None and not relay.device.participation.enabled
    )
    assert saved.pending_source_commands == original.pending_source_commands[1:]
    assert len(relay.receipts) == 1 and saved.identity == original.identity


@pytest.mark.parametrize("transition", ["participation", "source", "pairing"])
def test_retained_original_start_resumes_after_full_count_terminal_transition(
    tmp_path, transition
):
    # The old drive_control_tail barrier was stronger than preserving UUIDs:
    # an original, still-live Start must really resume after the target completes.
    sources = full_sources()
    original_start = p.SourceStart(sources[-1].source_id, 1, UUID, DATE)
    original = replace(
        PAIRED_STATE, pending_source_commands=(*sources[:-1], original_start)
    )
    worker, _, store, mono = file_rig(tmp_path, original, enabled=True)
    relay = ControlRelay(worker, store)
    blocked = [True]

    def before(request, saved):
        if (
            request.method == "PUT"
            and request.full_url.endswith("/sources")
            and json.loads(request.data)["operation"] == "start"
            and blocked[0]
        ):
            raise OSError("original Start held until terminal transition completes")

    relay.before = before
    drive(worker, mono, 4)
    assert original_start in s.load(store.path).pending_source_commands
    if transition == "participation":
        assert worker.request_participation(
            False, expected_generation=1, binding=worker.status().metadata.binding
        )
    elif transition == "source":
        assert worker.request_source_stop(
            sources[0].source_id,
            expected_generation=0,
            expected_automatic=None,
            supersedes=sources[0],
        )
    else:
        relay.approved = True
        relay.approval_url = approval_url()
        assert worker.request_pairing(mode="upgrade")
    for _ in range(20):
        drive(worker, mono, 1)
        saved = s.load(store.path)
        done = (
            (
                not relay.device.participation.enabled
                and saved.pending_participation is None
            )
            if transition == "participation"
            else (
                bool(relay.receipts)
                if transition == "source"
                else (
                    saved.session_id != original.session_id
                    and saved.pending_pairing is None
                )
            )
        )
        if done:
            break
    assert done and original_start in saved.pending_source_commands
    assert original_start.source_id not in relay.starts
    blocked[0] = False
    floor = len(relay.calls)
    drive(worker, mono, 20)
    assert relay.starts[original_start.source_id] == original_start
    saved = s.load(store.path)
    assert original_start not in saved.pending_source_commands
    expected = sources[1:-1] if transition == "source" else sources[:-1]
    assert saved.pending_source_commands == expected
    resumed = [
        p.parse_source_command(json.loads(request.data))
        for request, _ in relay.calls[floor:]
        if request.method == "PUT" and request.full_url.endswith("/sources")
    ]
    assert original_start in resumed
    assert all(command == original_start for command in resumed)
    assert all(state.identity == original.identity for state in store.saves)


def test_hot_api_submission_inside_pairing_save_preserves_reserved_batch(tmp_path):
    # Coordinator-owned composition remains visible: B proves the owner above,
    # never invents missing Api provenance/confirmation in production.
    from tests.test_api import FakeWindow, make_state
    from tests.test_api_fleetsharing import Timers
    from wingman import settings
    from wingman.ui.api import Api

    original = replace(
        PAIRED_STATE, pending_source_commands=upgrade_state().pending_source_commands
    )
    store = DiskStore(tmp_path / "api.json", original)
    mono = [1000.0]
    client = FakeRelayClient(device=DEVICE)
    begin = client.begin_pairing
    client.begin_pairing = lambda **kwargs: replace(
        begin(**kwargs), approval_url=approval_url()
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
        targets = tuple(source_id(i) for i in range(200, p.MAX_SOURCE_INTENTS))
        for target in targets:
            client.source_views[target] = p.SourceView(
                target, 1, 1, "active", None, None, None
            )
        assert api.fleet_sharing_watch(True)["queued"]
        for _ in range(40):
            drive(worker, mono, 1)
            if api.fleet_sharing_state()["sources"] is not None:
                break
        binding = api.fleet_sharing_state()["metadata"]["binding"]
        assert api.fleet_sharing_state()["sources"] is not None
        old_status = worker.status()
        submissions, errors, reached = [], [], []
        save = worker._save_state

        def saving(candidate):
            save(candidate)
            if candidate.pending_pairing and not reached:
                reached.append(True)
                try:
                    for target in targets[:-1]:
                        submissions.append(
                            api.fleet_sharing_stop_source(target, binding)
                        )
                    submissions.append(api.fleet_sharing_set_enabled(False))
                except Exception as error:  # noqa: BLE001 - assert outside owner callback swallowing
                    errors.append(error)

        worker._save_state = saving
        pairing = api.fleet_sharing_pair("upgrade")
        assert pairing["queued"]
        worker.iterate_once()
        assert reached == [True]
        assert not errors
        assert len(submissions) == len(targets) and all(
            v["queued"] for v in submissions
        )
        off = submissions[-1]["intent_id"]
        assert store.load().pending_pairing
        assert api.fleet_sharing_state()["sources"] is not None
        assert worker.stop() and worker.start()
        drive(worker, mono, 2)
        assert api.fleet_sharing_state()["sources"] is None
        api._receive_fleet_sharing_status(old_status)
        assert api.fleet_sharing_state()["sources"] is None
        assert not api.fleet_sharing_stop_source(targets[-1], binding)["queued"]
        assert store.load().pending_pairing.approval_url == approval_url()
        for _ in range(len(targets) + 55):
            drive(worker, mono, 1)
            if (
                all(client.source_views[t].state == "ended" for t in targets[:-1])
                and not client.device.participation.enabled
                and worker.status().pairing == "acknowledged"
            ):
                break
        state, status = store.load(), worker.status()
        assert not errors and not worker._commands
        assert state.pending_pairing is None and state.pending_recovery is None
        assert state.session_id == client.active_session != original.session_id
        assert (
            status.pairing_action_id == pairing["action_id"]
            and status.approval_url is None
        )
        assert (
            status.participation_intent_id == off
            and status.participation == "acknowledged"
        )
        assert status.local_inhibited and state.pending_participation is None
        assert state.observed_participation == client.device.participation
        assert client.source_views[targets[-1]].state == "active"
        assert all(client.source_views[t].state == "ended" for t in targets[:-1])
        assert not any(
            isinstance(c, p.StopSource) for c in state.pending_source_commands
        )
        pending = set(state.pending_source_commands)
        assert all(
            c in pending or client.source_intents.get(c.source_id) == c
            for c in original.pending_source_commands
        )
        assert all(saved.identity == original.identity for saved in store.saved)
        assert client.cadence_refusals == 0
    finally:
        assert api.shutdown_fleet_sharing()
        assert worker.stop()
        assert not timers.pending and all(
            not subs for subs in worker._subscribers.values()
        )
