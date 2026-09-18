"""Setup uses displayed authority and real worker journals, not implicit grants."""

import copy
from dataclasses import replace

from tests.test_fleetsharing_control_authority import ready
from tests.test_fleetsharing_worker import drive
from wingman.fleetsharing import protocol as p


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
