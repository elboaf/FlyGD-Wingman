"""Displayed control authority — real adapter/owner, no transport or native work."""

import copy
import json
from dataclasses import asdict, replace

import pytest

from tests.test_api_fleetsharing import setup
from tests.test_fleetsharing_worker import DATE, PAIRED_STATE, UUID, drive
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing import state as s
from wingman.fleetsharing.worker import PendingSourceStatus

OTHER = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def participation(status):
    return {
        "binding": status.metadata.binding,
        "observed": asdict(status.observed_participation)
        if status.observed_participation
        else None,
        "participation_intent_id": status.participation_intent_id,
        "participation_order": status.participation_order,
        "pending": asdict(status.pending_participation)
        if status.pending_participation
        else None,
    }


def source_observation(status, source=None, command=None):
    stop = isinstance(command, p.SourceStop)
    return {
        "source_id": source.source_id if source else command.source_id,
        "binding": status.metadata.binding,
        "observed": asdict(source) if source else None,
        "pending": {
            "operation": "stop" if stop else "start",
            "intent_id": command.request_id if stop else command.source_id,
        }
        if command
        else None,
        "expected_generation": command.expected_generation
        if stop
        else source.generation
        if source
        else 0,
        "expected_automatic": asdict(command.expected_automatic)
        if stop and command.expected_automatic
        else asdict(source.automatic)
        if not stop and source and source.automatic
        else None,
    }


def ready(tmp_path, **kwargs):
    api, worker, client, store, mono, timers = setup(tmp_path, **kwargs)
    api.fleet_sharing_watch(True)
    drive(worker, mono, 12)
    return api, worker, client, store, mono, timers


@pytest.mark.parametrize(
    "change", ["generation", "binding", "pending", "attempted", "queued", "order"]
)
def test_on_rejects_changed_displayed_authority_before_settings_or_queue(
    tmp_path, change
):
    api, worker, client, store, _mono, _ = ready(tmp_path)
    status = worker.status()
    pending = s.PendingParticipation(UUID, False, 1)
    status = replace(status, pending_participation=pending)
    api._receive_fleet_sharing_status(replace(status, order=status.order + 1))
    shown = participation(status)
    changes = {
        "generation": {"observed_participation": p.Participation(False, 2)},
        "binding": {"metadata": replace(status.metadata, binding="different")},
        "pending": {"pending_participation": replace(pending, intent_id=OTHER)},
        "attempted": {"pending_participation": replace(pending, attempted=True)},
        "queued": {"participation_intent_id": OTHER},
        "order": {"participation_order": status.participation_order + 1},
    }
    api._receive_fleet_sharing_status(
        replace(status, order=status.order + 2, **changes[change])
    )
    saved = store.load()
    assert not api.fleet_sharing_set_enabled(True, shown)["applied"]
    assert not api._state.settings["fleet_sharing"]["enabled"]
    assert not worker._commands and store.load() == saved
    assert not client.participation_calls
    api.shutdown_fleet_sharing()


def test_on_uses_rendered_cas_and_pending_participation_not_delivery_order(tmp_path):
    old = s.PendingParticipation(UUID, False, None)
    api, worker, _, store, mono, _ = ready(
        tmp_path, state=replace(PAIRED_STATE, pending_participation=old)
    )
    status = worker.status()
    shown = participation(status)
    worker._update_status()  # delivery order alone is not changed consent
    result = api.fleet_sharing_set_enabled(True, shown)
    assert result["applied"] and result["queued"]
    queued = worker._commands["participation"]
    assert queued.payload.expected_generation == shown["observed"]["generation"]
    assert queued.binding == shown["binding"] and queued.supersedes == old
    assert not any(c.kind == "automatic" for c in worker._commands.values())
    drive(worker, mono, 12)
    assert store.load().pending_participation is None
    api.shutdown_fleet_sharing()


@pytest.mark.parametrize("observation", [None, {}, {"binding": "stale"}])
def test_bound_on_without_valid_observation_is_refused(tmp_path, observation):
    api, worker, _, _, _, _ = ready(tmp_path)
    result = api.fleet_sharing_set_enabled(True, observation)
    assert not result["applied"] and not worker._commands
    assert not api._state.settings["fleet_sharing"]["enabled"]
    api.shutdown_fleet_sharing()


@pytest.mark.parametrize(
    "path,value",
    [
        (("extra",), 1),
        (("observed", "generation"), True),
        (("observed", "enabled"), 1),
        (("participation_order",), False),
        (("participation_intent_id",), "bad"),
        (("binding",), 7),
    ],
)
def test_on_control_closed_native_types(tmp_path, path, value):
    api, worker, _, _, _, _ = ready(tmp_path)
    shown = participation(worker.status())
    target = shown
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert not api.fleet_sharing_set_enabled(True, shown)["applied"]
    assert not worker._commands
    api.shutdown_fleet_sharing()


def test_stale_off_inhibits_and_preserves_unseen_durable_choice(tmp_path):
    old = s.PendingParticipation(UUID, True, None, True)
    api, worker, _, store, mono, _ = ready(
        tmp_path, state=replace(PAIRED_STATE, pending_participation=old), enabled=True
    )
    result = api.fleet_sharing_set_enabled(False, {"binding": "stale"})
    assert result["applied"] and worker.status().local_inhibited
    queued = worker._commands["participation"]
    assert queued.binding is None and queued.payload.expected_generation is None
    assert queued.supersedes is None
    drive(worker, mono, 3)
    assert store.load().pending_participation == old
    assert not api._state.settings["fleet_sharing"]["enabled"]
    api.shutdown_fleet_sharing()


@pytest.mark.parametrize(
    "change",
    ["generation", "automatic", "pending", "binding", "missing", "bool", "extra"],
)
def test_stop_refuses_stale_or_malformed_observation(tmp_path, change):
    api, worker, _, _, _, _ = ready(tmp_path)
    source = p.SourceView(UUID, 3, 1, "active", None, None, p.AutomaticBinding(7))
    status = replace(worker.status(), sources=p.Sources((source,), ()))
    api._receive_fleet_sharing_status(replace(status, order=status.order + 1))
    shown = source_observation(status, source)
    if change == "generation":
        status = replace(
            status, sources=p.Sources((replace(source, generation=4),), ())
        )
    elif change == "automatic":
        status = replace(
            status,
            sources=p.Sources((replace(source, automatic=p.AutomaticBinding(8)),), ()),
        )
    elif change == "pending":
        command = p.SourceStart(UUID, 1, OTHER, DATE)
        status = replace(
            status,
            pending_sources=(
                PendingSourceStatus(UUID, "start", 1, "persisted", command),
            ),
        )
    elif change == "binding":
        status = replace(status, metadata=replace(status.metadata, binding="different"))
    elif change == "missing":
        shown = None
    elif change == "bool":
        shown["expected_generation"] = True
    else:
        shown["extra"] = 1
    api._receive_fleet_sharing_status(replace(status, order=status.order + 2))
    assert not api.fleet_sharing_stop_source(
        UUID, worker.status().metadata.binding, shown
    )["queued"]
    assert not worker._commands
    api.shutdown_fleet_sharing()


@pytest.mark.parametrize("observed", [False, True])
def test_original_start_stop_and_repeated_stop_reuse_exact_command(tmp_path, observed):
    start = p.SourceStart(OTHER, 1, UUID, "2026-09-07T11:50:00.000Z")
    api, worker, client, _store, mono, _ = setup(
        tmp_path, state=replace(PAIRED_STATE, pending_source_commands=(start,))
    )
    if observed:
        client.source_views[OTHER] = p.SourceView(
            OTHER, 4, 1, "active", None, None, p.AutomaticBinding(9)
        )
    api.fleet_sharing_watch(True)
    drive(worker, mono, 12)
    status = worker.status()
    source = next((v for v in status.sources.sources if v.source_id == OTHER), None)
    shown = source_observation(status, source, start)
    assert api.fleet_sharing_stop_source(OTHER, shown["binding"], shown)["queued"]
    queued = worker._commands["source:" + OTHER]
    original = queued.payload
    assert queued.supersedes == start
    assert original.expected_generation == (4 if observed else 0)
    assert original.expected_automatic == (p.AutomaticBinding(9) if observed else None)
    repeat = source_observation(worker.status(), source, original)
    assert api.fleet_sharing_stop_source(OTHER, shown["binding"], repeat)["queued"]
    assert worker._commands["source:" + OTHER] is queued
    assert worker._commands["source:" + OTHER].payload == original
    api.shutdown_fleet_sharing()


@pytest.mark.parametrize("change", ["pending", "attempted", "queued", "order"])
def test_stale_on_guards_kill_in_memory_latest_authority_mutant(
    tmp_path, monkeypatch, change
):
    from wingman.ui.api import Api

    monkeypatch.setattr(
        Api, "_sharing_control_matches", staticmethod(lambda value, expected: True)
    )
    with pytest.raises(AssertionError):
        test_on_rejects_changed_displayed_authority_before_settings_or_queue(
            tmp_path, change
        )


@pytest.mark.parametrize("permanent_loss", [False, True])
def test_rendered_terminal_controls_settle_without_telemetry_or_timing(
    tmp_path, permanent_loss
):
    api, worker, client, store, mono, _ = ready(tmp_path, enabled=True)
    client.source_views[OTHER] = p.SourceView(OTHER, 3, 1, "active", None, None, None)
    drive(worker, mono, 12)
    controls = api.fleet_sharing_state()["controls"]
    shown = next(row for row in controls["sources"] if row["source_id"] == OTHER)
    if permanent_loss:
        worker.fence_timing("elapsed_continuity_lost")
        assert worker._timing_context._timing_loss.cutoff is None
    assert api.fleet_sharing_set_enabled(False, controls["participation"])["applied"]
    assert worker.status().local_inhibited
    assert api.fleet_sharing_stop_source(OTHER, shown["binding"], shown)["queued"]
    drive(worker, mono, 40)
    assert not client.device.participation.enabled
    assert client.source_views[OTHER].state == "ended"
    assert store.load().pending_participation is None
    assert not store.load().pending_source_commands
    assert not client.publish_calls
    if permanent_loss:
        assert worker._control_time_fenced
    api.shutdown_fleet_sharing()


def test_persisted_stop_reuses_original_request_and_timestamp(tmp_path):
    stop = p.SourceStop(OTHER, 3, UUID, DATE, p.AutomaticBinding(4))
    api, worker, _, store, _, _ = setup(
        tmp_path, state=replace(PAIRED_STATE, pending_source_commands=(stop,))
    )
    worker.resume_pending()
    worker.iterate_once()
    shown = api.fleet_sharing_state()["controls"]["sources"][0]
    assert shown["pending"] == {"operation": "stop", "intent_id": UUID}
    for _ in range(2):
        assert api.fleet_sharing_stop_source(OTHER, shown["binding"], shown)["queued"]
        assert store.load().pending_source_commands == (stop,)
        assert not worker._commands
    api.shutdown_fleet_sharing()


def test_projection_is_detached_and_does_not_serialize_automatic_private_history(
    tmp_path,
):
    api, worker, _, _, _, _ = ready(tmp_path)
    command = p.AutomaticCommand(OTHER, DATE, True, 1, 2)
    pending = s.PendingAutomatic(command, True, s.CancelAfterOn(UUID, DATE))
    consent = p.Consent(2, 3, False, None, None, None, None)
    receipt = p.AutomaticReceipt(command, DATE, "2026-09-08T12:00:00.000Z", consent)
    status = replace(
        worker.status(),
        automatic=s.AutomaticState(
            consent, pending, s.AutomaticCompletion(pending, "applied", receipt)
        ),
    )
    api._receive_fleet_sharing_status(replace(status, order=status.order + 1))
    payload = api.fleet_sharing_state()
    text = json.dumps(payload)
    for private in (
        "intent_created_at",
        "cancel_after_on",
        "receipt",
        "command",
        DATE,
        OTHER,
    ):
        assert private not in text
    assert payload["controls"]["participation"] == participation(status)
    saved = copy.deepcopy(payload)
    payload["controls"]["participation"]["observed"]["generation"] = 999
    assert api.fleet_sharing_state() == saved
    api.shutdown_fleet_sharing()


@pytest.mark.parametrize(
    "kind", ["enabled", "pending", "unknown", "queued", "cutover", "terminal"]
)
def test_hide_guard_keeps_unresolved_automatic_authority_visible(tmp_path, kind):
    api, worker, _, _, _, _ = ready(tmp_path)
    status = worker.status()
    automatic = status.automatic
    command = s.PendingAutomatic(p.AutomaticCommand(OTHER, DATE, True, 0, 0), True)
    changes = {}
    if kind == "enabled":
        automatic = replace(
            automatic,
            observed_consent=replace(automatic.observed_consent, enabled=True),
        )
    elif kind == "pending":
        automatic = replace(automatic, pending=command)
    elif kind == "unknown":
        changes["automatic_status"] = None
    elif kind == "queued":
        changes["automatic_stage"] = "queued"
    elif kind == "cutover":
        changes["cutover_outcomes"] = (s.CutoverOutcome("participation", "fenced"),)
    else:
        automatic = replace(
            automatic, last_result=s.AutomaticCompletion(command, "applied")
        )
    api._receive_fleet_sharing_status(
        replace(status, order=status.order + 1, automatic=automatic, **changes)
    )
    assert api.set_show_eve_tools(False)["applied"] is (kind == "terminal")
    api.shutdown_fleet_sharing()
