"""Setup uses displayed authority and real worker journals, not implicit grants."""

import copy
from dataclasses import replace

import pytest

from tests.test_api_fleetsharing import await_approval, setup
from tests.test_fleetsharing_control_authority import ready
from tests.test_fleetsharing_worker import DATE, PAIRED_STATE, UUID, drive
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing import state as s


def shown(api, kind):
    return api.fleet_sharing_state()["setup_controls"][kind]


def test_automatic_on_then_off_are_account_consent_not_local_participation(tmp_path):
    api, worker, client, store, mono, _ = ready(tmp_path)
    assert api.fleet_sharing_automatic("on", shown(api, "automatic"))["queued"]
    drive(worker, mono, 16)
    assert store.load().automatic.observed_consent.enabled
    assert not api.fleet_sharing_state()["enabled"]
    assert api.fleet_sharing_automatic("off", shown(api, "automatic"))["queued"]
    drive(worker, mono, 16)
    assert not store.load().automatic.observed_consent.enabled
    assert not client.participation_calls
    api.shutdown_fleet_sharing()


def test_automatic_stale_and_malformed_choices_never_queue(tmp_path):
    api, worker, _, _, _, _ = ready(tmp_path)
    original = shown(api, "automatic")
    wrong = copy.deepcopy(original)
    wrong["observed"]["generation"] += 1
    assert not api.fleet_sharing_automatic("on", wrong)["queued"]
    assert not api.fleet_sharing_automatic("on", None)["queued"]
    wrong = copy.deepcopy(original)
    wrong["extra"] = True
    assert not api.fleet_sharing_automatic("off", wrong)["queued"]
    assert not worker._commands
    api.shutdown_fleet_sharing()


def test_combat_approval_requests_combat_rights_without_enabling_either_consent(
    tmp_path,
):
    api, worker, _, _, _, _ = ready(tmp_path)
    assert api.fleet_sharing_setup("combat", shown(api, "setup"))["queued"]
    command = worker._commands["pairing"]
    assert command.payload[0] == "upgrade"
    assert set(command.payload[3]) == {p.SHARED_CAPABILITY, p.COMBAT_CAPABILITY}
    assert not api._state.settings["fleet_sharing"]["enabled"]
    assert "automatic" not in worker._commands
    api.shutdown_fleet_sharing()


@pytest.mark.parametrize("choice", ["automatic", "participation"])
def test_fresh_setup_cannot_discard_a_choice_queued_since_render(tmp_path, choice):
    api, worker, _, _, _, _ = ready(tmp_path)
    before = shown(api, "setup")
    if choice == "automatic":
        assert api.fleet_sharing_automatic("on", shown(api, "automatic"))["queued"]
    else:
        observation = api.fleet_sharing_state()["controls"]["participation"]
        assert api.fleet_sharing_set_enabled(True, observation)["queued"]
    assert not api.fleet_sharing_setup("fresh", before, True)["queued"]
    assert not api.fleet_sharing_setup("fresh", shown(api, "setup"), True)["queued"]
    assert "pairing" not in worker._commands
    api.shutdown_fleet_sharing()


def test_fresh_setup_acknowledges_only_displayed_settled_history(tmp_path):
    api, worker, _, store, _, _ = ready(tmp_path)
    original = shown(api, "setup")
    assert api.fleet_sharing_setup("fresh", original, True)["queued"]
    action = worker._commands["pairing"]
    assert action.automatic_history == store.load().automatic
    assert action.binding == original["binding"]
    api.shutdown_fleet_sharing()


def test_queued_automatic_on_can_be_cancelled_before_its_first_save(tmp_path):
    api, worker, _, store, mono, _ = ready(tmp_path)
    assert api.fleet_sharing_automatic("on", shown(api, "automatic"))["queued"]
    assert api.fleet_sharing_automatic("cancel", shown(api, "automatic"))["queued"]
    drive(worker, mono, 24)
    assert store.load().automatic.pending is None
    assert not store.load().automatic.observed_consent.enabled
    api.shutdown_fleet_sharing()


def test_legacy_history_requires_displayed_dismissal_then_explicit_removal(tmp_path):
    from tests.test_fleetsharing_worker_state4 import FileStore, legacy_file

    legacy = FileStore(tmp_path / "legacy.json")
    original = legacy_file(legacy)
    api, worker, _, store, mono, _ = ready(tmp_path, state=legacy.load())
    captured = shown(api, "setup")
    assert not api.fleet_sharing_setup("fresh", captured, True)["queued"]
    assert api.fleet_sharing_setup("dismiss_legacy", captured)["queued"]
    drive(worker, mono, 8)
    saved = store.load()
    assert saved.cutover.original == original
    assert all(item.status != "fenced" for item in saved.cutover.outcomes)
    assert not api.fleet_sharing_setup("remove_legacy", captured)["queued"]
    assert api.fleet_sharing_setup("remove_legacy", shown(api, "setup"))["queued"]
    drive(worker, mono, 8)
    assert store.load().cutover is None
    assert store.load().identity == saved.identity
    api.shutdown_fleet_sharing()


def test_empty_legacy_archive_is_visible_and_explicitly_removable(tmp_path):
    import json
    from dataclasses import asdict

    from tests.fleetsharing_state4_helpers import LEGACY_V1

    raw = {
        **LEGACY_V1,
        "identity": asdict(PAIRED_STATE.identity),
        "relay_origin": PAIRED_STATE.relay_origin,
        "session_id": None,
        "last_revision": 0,
    }
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(raw), encoding="utf8")
    api, worker, _, store, mono, _ = ready(tmp_path, state=s.load(path))
    view = shown(api, "setup")
    assert view["legacy_archive"] and view["cutover"] == []
    assert api.fleet_sharing_setup("remove_legacy", view)["queued"]
    drive(worker, mono, 8)
    assert store.load().cutover is None
    api.shutdown_fleet_sharing()


def test_fresh_observation_binds_displayed_configured_server(tmp_path, monkeypatch):
    api, worker, _, _, _, _ = ready(tmp_path)
    old = shown(api, "setup")
    monkeypatch.setattr(
        "wingman.fleetsharing.config.resolve_relay_origin",
        lambda **_: "https://other.test",
    )
    assert not api.fleet_sharing_setup("fresh", old, True)["queued"]
    assert not worker._commands
    api.shutdown_fleet_sharing()


@pytest.mark.parametrize("ingest_off", [False, True])
def test_fresh_admission_cannot_overtake_an_intervening_automatic_off(
    tmp_path, monkeypatch, ingest_off
):
    api, worker, client, store, mono, _ = ready(tmp_path)
    assert api.fleet_sharing_automatic("on", shown(api, "automatic"))["queued"]
    drive(worker, mono, 12)
    assert client.automatic_consent.enabled
    original = worker.request_pairing

    def concurrent_off(**kwargs):
        assert api.fleet_sharing_automatic("off", shown(api, "automatic"))["queued"]
        if ingest_off:
            worker.iterate_once()
        return original(**kwargs)

    monkeypatch.setattr(worker, "request_pairing", concurrent_off)
    monkeypatch.setattr(
        "wingman.fleetsharing.config.resolve_relay_origin",
        lambda **_: "https://other.test",
    )
    assert not api.fleet_sharing_setup("fresh", shown(api, "setup"), True)["queued"]
    drive(worker, mono, 16)
    assert store.load().relay_origin == PAIRED_STATE.relay_origin
    assert not client.automatic_consent.enabled
    api.shutdown_fleet_sharing()


def test_cancel_queued_on_replacement_keeps_older_unresolved_journal(tmp_path):
    old = s.PendingAutomatic(p.AutomaticCommand(UUID, DATE, False, 1, 1))
    consent = p.Consent(2, 2, True, UUID, DATE, None, None)
    state = replace(
        PAIRED_STATE, device_id=UUID, automatic=s.AutomaticState(consent, old)
    )
    api, worker, client, store, mono, _ = setup(tmp_path, state=state)
    client.automatic_consent = consent
    api.fleet_sharing_watch(True)
    drive(worker, mono, 12)
    assert api.fleet_sharing_automatic("on", shown(api, "automatic"))["queued"]
    replacement = worker._commands["automatic"].payload.request_id
    assert api.fleet_sharing_automatic("cancel", shown(api, "automatic"))["queued"]
    drive(worker, mono, 16)
    assert client.automatic_consent == consent
    assert store.load().automatic.pending.command == old.command
    assert all(
        c.payload.request_id != replacement
        for c in worker._commands.values()
        if c.kind == "automatic"
    )
    api.shutdown_fleet_sharing()


@pytest.mark.parametrize("after_write", [False, True])
def test_cancelling_queued_on_crossing_its_save_never_sends_on(
    tmp_path, monkeypatch, after_write
):
    api, worker, client, store, mono, _ = ready(tmp_path)
    assert api.fleet_sharing_automatic("on", shown(api, "automatic"))["queued"]
    request_id = worker._commands["automatic"].payload.request_id
    original = worker._save_state
    fired = []

    def save(candidate):
        pending = candidate.automatic.pending
        trigger = not fired and pending and pending.command.request_id == request_id
        if after_write:
            original(candidate)
        if trigger:
            fired.append(True)
            assert api.fleet_sharing_automatic("cancel", shown(api, "automatic"))[
                "queued"
            ]
        if not after_write:
            original(candidate)

    monkeypatch.setattr(worker, "_save_state", save)
    drive(worker, mono, 20)
    assert fired
    assert store.load().automatic.pending is None
    assert not client.automatic_consent.enabled
    api.shutdown_fleet_sharing()


def test_retry_preserves_unregistered_pairing_mode_and_requested_combat(tmp_path):
    api, worker, client, store, mono, _ = setup(tmp_path, state=s.EMPTY)
    api.fleet_sharing_watch(True)
    drive(worker, mono, 4)
    assert api.fleet_sharing_setup("combat", shown(api, "setup"))["queued"]
    action_id = worker.status().pairing_action_id
    await_approval(worker, store, mono, action_id)
    assert store.load().pending_pairing.mode == "initial"
    client.precommit_loss.add("complete_pairing")
    assert api.fleet_sharing_setup("retry", shown(api, "setup"))["queued"]
    queued = worker._commands["pairing"].payload
    assert queued[0] == "initial"
    assert p.COMBAT_CAPABILITY in queued[3]
    drive(worker, mono, 30)
    assert worker.status().pairing == "needs_retry"
    assert store.load().pending_pairing.mode == "initial"
    api.shutdown_fleet_sharing()


def test_setup_observation_rejects_history_changed_since_render(tmp_path):
    api, worker, _, _, _, _ = ready(tmp_path)
    original = shown(api, "setup")
    status = worker.status()
    changed = replace(
        status.automatic,
        observed_consent=replace(status.automatic.observed_consent, revision=99),
    )
    api._receive_fleet_sharing_status(
        replace(status, automatic=changed, order=status.order + 1)
    )
    assert not api.fleet_sharing_setup("fresh", original, True)["queued"]
    assert not worker._commands
    api.shutdown_fleet_sharing()
