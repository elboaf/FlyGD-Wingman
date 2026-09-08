"""Task 8 setup bridge: real owner and Settings, offline transport/native seams."""

import json
import threading
from dataclasses import asdict, replace

import pytest

from tests.test_api import FakeWindow, make_state, pushes
from tests.test_fleetsharing_worker import (
    DEVICE,
    PAIRED_STATE,
    UUID,
    drive,
    rig,
)
from wingman import settings
from wingman.fleetsharing import protocol as p
from wingman.fleetsharing import state as s
from wingman.ui.api import Api


class Timers:
    def __init__(self):
        self.pending = []

    def __call__(self, delay, callback):
        pending = self.pending

        class Timer:
            daemon = False

            def start(self):
                pending.append(callback)

            def cancel(self):
                if callback in pending:
                    pending.remove(callback)

        return Timer()

    def drain(self):
        while self.pending:
            self.pending.pop(0)()


def setup(tmp_path, *, state=PAIRED_STATE, enabled=False, telemetry=None):
    worker, client, store, mono = rig(state=state, enabled=enabled)
    timers = Timers()
    app = make_state(tmp_path, **settings.load())
    app.settings["fleet_sharing"]["enabled"] = enabled
    api = Api(app, fleet_sharing=worker, telemetry=telemetry, timer=timers)
    api._window = FakeWindow()
    return api, worker, client, store, mono, timers


def test_startup_probe_and_source_watch_never_write_preference_or_consent(tmp_path):
    api, worker, client, store, mono, _timers = setup(tmp_path)
    api._start_fleet_sharing()
    api._start_fleet_sharing()
    assert worker.resume_pending() is False
    worker.iterate_once()
    assert store.loads == 1 and not store.saves and not client.calls
    assert api.fleet_sharing_state()["metadata"]["loaded"] is True
    assert not api._window.evaluated
    api.fleet_sharing_watch(True)
    drive(worker, mono, 12)
    assert api.fleet_sharing_state()["sources"]["characters"][0]["character_id"] == 1
    api.fleet_sharing_watch(False)
    assert (
        not client.publish_calls
        and not client.participation_calls
        and not client.controls
    )
    assert api._state.settings["fleet_sharing"]["enabled"] is False
    assert all(
        name.startswith("_") or callable(getattr(api, name)) for name in vars(api)
    )
    api.shutdown_fleet_sharing()


def test_explicit_on_even_stored_true_queues_new_intent_without_initial_on(tmp_path):
    api, _worker, client, _store, _mono, _timers = setup(tmp_path, enabled=True)
    api._start_fleet_sharing()
    assert api.fleet_sharing_state()["participation"] is None
    first = api.fleet_sharing_set_enabled(True)
    second = api.fleet_sharing_set_enabled(True)
    assert first["applied"] and first["persisted"] and first["queued"]
    assert second["intent_id"] != first["intent_id"]
    assert client.participation_calls == []
    assert api.fleet_sharing_state()["participation"] == "queued"
    api.shutdown_fleet_sharing()


def test_off_inhibits_before_real_settings_io_and_stays_live_on_save_failure(
    tmp_path, monkeypatch
):
    api, worker, _client, _store, _mono, _timers = setup(tmp_path, enabled=True)
    settings.save(api._state.settings)

    def fail(*args, **kwargs):
        assert worker.status().local_inhibited
        raise OSError("private path must not reach page")

    monkeypatch.setattr(settings.atomicio, "write_atomic", fail)
    result = api.fleet_sharing_set_enabled(False)
    assert result["applied"] is True and result["persisted"] is False
    assert result["queued"] is True
    assert api._state.settings["fleet_sharing"]["enabled"] is False
    assert settings.load()["fleet_sharing"]["enabled"] is True
    assert "restart" in result["error"].lower()
    assert "private path" not in json.dumps(result)
    api.shutdown_fleet_sharing()


@pytest.mark.parametrize("save_fails", [False, True])
@pytest.mark.parametrize("delivery", ["read", "push"])
def test_preference_completion_revises_captured_payload_without_worker_progress(
    tmp_path,
    monkeypatch,
    save_fails,
    delivery,
):
    api, _worker, _client, _store, _mono, timers = setup(tmp_path)
    api._sharing_page_ready = True
    api.fleet_sharing_watch(True)
    entered, release = threading.Event(), threading.Event()
    save = settings._save_locked
    captured, results = [], []

    def held_save(data, path=None):
        entered.set()
        assert release.wait(3)
        if save_fails:
            raise OSError("private disk detail")
        save(data, path)

    monkeypatch.setattr(settings, "_save_locked", held_save)
    runner = threading.Thread(
        target=lambda: results.append(api.fleet_sharing_set_enabled(True))
    )
    runner.start()
    try:
        assert entered.wait(2)
        if delivery == "push":
            api._push = lambda handler, payload: captured.append(payload)
            timers.drain()
        else:
            captured.append(api.fleet_sharing_state())
        # A read during Settings I/O must not expose its partly assembled live
        # mutation under the old presentation tag / persistence warning.
        assert captured[-1]["enabled"] is False
    finally:
        release.set()
        runner.join(3)
    assert not runner.is_alive()
    old, new = captured[-1], results[0]["state"]
    assert new["order"] == old["order"]
    assert new["preference_order"] == old["preference_order"]
    assert new["presentation_order"] > old["presentation_order"]
    assert new["enabled"] is True
    assert bool(new["preference_error"]) is save_fails
    assert "private disk" not in json.dumps(new)
    assert api.fleet_sharing_state() == new
    api.shutdown_fleet_sharing()


def test_runtime_completion_has_new_presentation_and_old_failure_cannot_restore_warning(
    tmp_path,
):
    api, _worker, _client, _store, _mono, _timers = setup(tmp_path)
    entered, release = threading.Event(), threading.Event()
    results = []

    def held_runtime():
        if not entered.is_set():
            entered.set()
            assert release.wait(3)
            raise RuntimeError("old private native failure")

    api._reconcile_eve_runtime = held_runtime
    old = threading.Thread(
        target=lambda: results.append(api.fleet_sharing_set_enabled(True))
    )
    old.start()
    try:
        assert entered.wait(2)
        captured = api.fleet_sharing_state()
        new = api.fleet_sharing_set_enabled(False)["state"]
    finally:
        release.set()
        old.join(3)
    assert not old.is_alive()
    assert new["presentation_order"] > captured["presentation_order"]
    assert api.fleet_sharing_state() == new
    assert results[0]["state"]["runtime_error"] is None
    api.shutdown_fleet_sharing()


def test_owner_projection_restores_pending_uuid_and_never_exposes_keys_or_sessions(
    tmp_path,
):
    source_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    state = replace(
        PAIRED_STATE,
        pending_source_commands=(
            p.StartSource(source_id, 1, UUID, "2026-09-07T12:00:00.000Z"),
        ),
    )
    api, worker, _client, _store, _mono, _timers = setup(tmp_path, state=state)
    worker.resume_pending()
    worker.iterate_once()
    payload = api.fleet_sharing_state()
    pending = payload["pending_sources"][0]
    assert pending == {
        "source_id": source_id,
        "operation": "start",
        "character_id": 1,
        "stage": "persisted",
    }
    assert (
        payload["metadata"]["binding"]
        and payload["metadata"]["paired_origin"] == "https://relay.test"
    )
    text = json.dumps(payload)
    for secret in [
        state.session_id,
        state.identity.public_key_spki_b64,
        state.identity.protected_private_key_b64,
        "intent_created_at",
    ]:
        assert secret not in text
    assert api.fleet_sharing_stop_source(source_id, payload["metadata"]["binding"])[
        "queued"
    ]
    assert worker.status().pending_sources[0].operation == "stop"
    api.shutdown_fleet_sharing()


def test_saved_new_binding_never_exposes_previous_owned_roster():
    worker, _client, _store, mono = rig(enabled=False)
    worker.set_source_watch(True)
    drive(worker, mono, 12)
    old = worker.status().metadata.binding
    seen = []
    worker.subscribe_status(seen.append)
    worker.request_pairing(mode="fresh", configured_origin="https://new-relay.test")
    drive(worker, mono, 1)
    changed = [status for status in seen if status.metadata.binding != old]
    assert changed
    assert all(status.sources is None for status in changed)
    assert all(status.observed_participation is None for status in changed)


@pytest.mark.parametrize("operation", ["start", "stop"])
@pytest.mark.parametrize("transition", ["fresh", "upgrade", "rejected-fresh"])
def test_bound_source_queued_after_pairing_keeps_saved_identity_at_ingestion(
    operation,
    transition,
):
    worker, _client, store, mono = rig(enabled=False)
    worker.set_source_watch(True)
    drive(worker, mono, 12)
    old = worker.status().metadata.binding
    seen = []
    worker.subscribe_status(seen.append)
    # The serialized owner is held between iterations: pairing reserves its
    # future epoch while the old Settings view is still valid at submission.
    worker.request_pairing(
        mode="upgrade" if transition == "upgrade" else "fresh",
        configured_origin="https://new-relay.test" if transition == "fresh" else None,
    )
    if operation == "start":
        source_id = worker.request_source_start(1, UUID, binding=old)
        assert source_id
    else:
        source_id = UUID
        assert worker.request_source_stop(source_id, binding=old)
    drive(worker, mono, 1)
    if transition == "fresh":
        changed = [status for status in seen if status.metadata.binding != old]
        assert changed
        assert all(not status.pending_sources for status in changed)
        assert all(not status.source_results for status in changed)
        assert all(not status.sources for status in changed)
        assert not store.load().pending_source_commands
        current = worker.status().metadata.binding
        new_id = worker.request_source_start(1, UUID, binding=current)
        drive(worker, mono, 1)
        assert any(c.source_id == new_id for c in store.load().pending_source_commands)
    else:
        assert worker.status().metadata.binding == old
        assert any(
            c.source_id == source_id
            for saved in store.saves
            for c in saved.pending_source_commands
        )


def test_hidden_window_closes_watch_without_stopping_and_show_restores_it(tmp_path):
    api, worker, client, _store, mono, _timers = setup(tmp_path)
    api.fleet_sharing_watch(True)
    drive(worker, mono, 12)
    api.close()
    count = len(client.calls)
    drive(worker, mono, 20)
    assert len(client.calls) == count
    api._set_sharing_window_visible(True)
    drive(worker, mono, 5)
    assert len(client.calls) > count
    assert not client.controls and not client.publish_calls
    api.shutdown_fleet_sharing()


def test_late_section_entry_cannot_restart_actual_watch_after_native_hide(tmp_path):
    api, worker, client, _store, mono, _timers = setup(tmp_path)
    api.fleet_sharing_watch(True)
    drive(worker, mono, 12)
    api.fleet_sharing_watch(False)
    entered, release = threading.Event(), threading.Event()
    set_watch = worker.set_source_watch
    effects = []

    def held(value):
        if value and not entered.is_set():
            entered.set()
            assert release.wait(3)
        effects.append(value)
        return set_watch(value)

    worker.set_source_watch = held
    entry = threading.Thread(target=lambda: api.fleet_sharing_watch(True))
    entry.start()
    try:
        assert entered.wait(2)
        api._set_sharing_window_visible(False)
    finally:
        release.set()
        entry.join(3)
    assert not entry.is_alive()
    before = len(client.calls)
    drive(worker, mono, 20)
    assert len(client.calls) == before, "late entry left actual network watching on"
    assert effects[-1] is False
    api._set_sharing_window_visible(True)
    drive(worker, mono, 5)
    assert len(client.calls) > before
    assert not client.controls and not client.publish_calls
    api.shutdown_fleet_sharing()


def test_watch_effect_callback_can_close_section_without_lifecycle_deadlock(tmp_path):
    api, worker, client, _store, mono, _timers = setup(tmp_path)
    set_watch = worker.set_source_watch
    reentered = []

    def callback(value):
        if value and not reentered:
            reentered.append(True)
            api.fleet_sharing_watch(False)
        return set_watch(value)

    worker.set_source_watch = callback
    entry = threading.Thread(target=lambda: api.fleet_sharing_watch(True), daemon=True)
    entry.start()
    entry.join(2)
    assert not entry.is_alive(), "watch effect callback deadlocked"
    drive(worker, mono, 20)
    assert not client.calls
    api.shutdown_fleet_sharing()


def test_runtime_failure_does_not_lie_about_applied_preference(tmp_path):
    api, _worker, _client, _store, _mono, _timers = setup(tmp_path)

    def fail():
        raise RuntimeError("unavailable native runtime")

    api._telemetry_factory = fail
    result = api.fleet_sharing_set_enabled(True)
    assert result["applied"] and result["persisted"] and result["queued"]
    assert result["runtime_error"]
    assert settings.load()["fleet_sharing"]["enabled"]
    api.shutdown_fleet_sharing()


def test_status_order_and_binding_follow_saved_identity_not_submission_epoch():
    worker, _client, _store, mono = rig(enabled=False)
    worker.resume_pending()
    worker.iterate_once()
    before = worker.status()
    worker.request_pairing(mode="fresh")  # owner will reject, no durable key change
    drive(worker, mono, 1)
    after = worker.status()
    assert after.metadata.binding == before.metadata.binding
    assert after.order > before.order
    assert asdict(after.metadata)["has_session"] is True


def test_callback_only_coalesces_and_schedules_page_delivery(tmp_path):
    api, worker, _client, _store, _mono, timers = setup(tmp_path)
    api.fleet_sharing_watch(True)
    worker.request_participation(False)
    worker.request_participation(True)
    assert not api._window.evaluated
    api._sharing_page_ready = True
    worker.request_participation(False)
    worker.request_participation(True)
    assert len(timers.pending) == 1
    timers.drain()
    delivered = pushes(api._window)
    assert delivered[-1][0] == "onFleetSharingState"
    assert len(delivered) == 1
    api.fleet_sharing_watch(False)
    worker.request_participation(False)
    timers.drain()
    assert len(pushes(api._window)) == 1
    api.shutdown_fleet_sharing()


def test_blocked_page_delivery_keeps_one_coalesced_callback_not_parallel_timers(
    tmp_path,
):
    api, worker, _client, _store, _mono, timers = setup(tmp_path)
    api._sharing_page_ready = True
    api.fleet_sharing_watch(True)
    entered, release = threading.Event(), threading.Event()
    push = api._push

    def held(handler, payload):
        entered.set()
        assert release.wait(3)
        push(handler, payload)

    api._push = held
    delivery = threading.Thread(target=timers.pending.pop(0))
    delivery.start()
    try:
        assert entered.wait(2)
        for _ in range(20):
            worker.request_participation(False)
        assert not timers.pending
    finally:
        release.set()
        delivery.join(3)
    assert not delivery.is_alive()
    timers.drain()
    assert len(pushes(api._window)) == 2
    api.shutdown_fleet_sharing()


def test_pairing_browser_is_current_explicit_persisted_action_once(
    tmp_path, monkeypatch
):
    api, worker, _client, store, _mono, timers = setup(tmp_path, state=s.EMPTY)
    opened = []
    monkeypatch.setattr("wingman.ui.api.webbrowser.open", opened.append)
    worker.resume_pending()
    worker.iterate_once()
    assert api.fleet_sharing_pair()["queued"]
    worker.iterate_once()
    assert worker.status().pairing == "awaiting_approval"
    assert store.load().pending_pairing.approval_url
    assert opened == []
    timers.drain()
    assert len(opened) == 1
    api.fleet_sharing_state()
    api.fleet_sharing_watch(True)
    timers.drain()
    assert len(opened) == 1
    # A replacement action must not open the old admission URL.
    api.fleet_sharing_pair()
    timers.drain()
    assert len(opened) == 1
    api.shutdown_fleet_sharing()


@pytest.mark.parametrize("failure", ["false", "exception"])
@pytest.mark.parametrize("kind", ["pair", "grant"])
def test_browser_launch_failure_is_visible_and_only_new_explicit_action_retries(
    tmp_path,
    monkeypatch,
    failure,
    kind,
):
    api, worker, client, _store, mono, timers = setup(
        tmp_path,
        state=s.EMPTY if kind == "pair" else PAIRED_STATE,
    )
    api.fleet_sharing_watch(True)
    drive(worker, mono, 12)
    opened = []

    def browser(url):
        opened.append(url)
        if len(opened) > 1:
            return True
        if failure == "exception":
            raise RuntimeError("secret URL and OS detail")
        return False

    monkeypatch.setattr("wingman.ui.api.webbrowser.open", browser)

    def request():
        if kind == "pair":
            return api.fleet_sharing_pair()
        return api.fleet_sharing_grant_fleet_read(
            1, api.fleet_sharing_state()["metadata"]["binding"]
        )

    first = request()
    drive(worker, mono, 1)
    timers.drain()
    payload = api.fleet_sharing_state()
    assert payload["browser_error"]
    assert "secret" not in json.dumps(payload)
    assert payload["browser_retry"] == kind
    for _ in range(3):
        api.fleet_sharing_state()
        api.fleet_sharing_watch(True)
        timers.drain()
    assert len(opened) == 1
    second = request()
    assert second["action_id"] != first["action_id"]
    drive(worker, mono, 3)
    timers.drain()
    assert len(opened) == 2
    assert api.fleet_sharing_state()["browser_error"] is None
    if kind == "pair":
        assert list(client.pairings) == ["pair-id", "pair-id-2"], (
            "retry must obtain a new admission"
        )
    api.shutdown_fleet_sharing()


@pytest.mark.parametrize("failure_timing", ["before_completion", "after_completion"])
def test_completed_pairing_retires_same_action_browser_failure(
    tmp_path, monkeypatch, failure_timing
):
    api, worker, client, store, mono, timers = setup(tmp_path)
    api.fleet_sharing_watch(True)
    drive(worker, mono, 12)
    binding = api.fleet_sharing_state()["metadata"]["binding"]
    client.loss.add("complete_pairing")
    action = api.fleet_sharing_pair("upgrade")["action_id"]
    drive(worker, mono, 1)
    assert worker.status().pairing == "awaiting_approval"
    assert store.load().pending_pairing is not None
    opened = []

    def complete_pairing():
        # Real owner recovery after an uncertain completion clears the journal
        # without changing this same-key upgrade's binding or explicit action.
        drive(worker, mono, 35)
        status = worker.status()
        assert status.pairing == "acknowledged"
        assert status.pairing_action_id == action
        assert status.metadata.binding == binding
        assert store.load().pending_pairing is None
        assert client.recoveries > 0

    def browser(url):
        opened.append(url)
        if failure_timing == "after_completion":
            complete_pairing()
        return False

    monkeypatch.setattr("wingman.ui.api.webbrowser.open", browser)
    try:
        timers.drain()
        if failure_timing == "before_completion":
            failed = api.fleet_sharing_state()
            assert failed["browser_retry"] == "pair"
            assert failed["browser_error"]
            complete_pairing()
        payload = api.fleet_sharing_state()
        assert payload["browser_retry"] is None
        assert payload["browser_error"] is None
        timers.drain()
        assert len(opened) == 1
        assert len(client.pairings) == 1
    finally:
        api.shutdown_fleet_sharing()


def test_completed_pairing_does_not_suppress_or_clear_independent_grant_failure(
    tmp_path, monkeypatch
):
    api, worker, client, store, mono, timers = setup(tmp_path)
    api.fleet_sharing_watch(True)
    drive(worker, mono, 12)
    client.loss.add("complete_pairing")
    api.fleet_sharing_pair("upgrade")
    drive(worker, mono, 1)
    monkeypatch.setattr("wingman.ui.api.webbrowser.open", lambda url: True)
    timers.drain()
    drive(worker, mono, 35)
    assert worker.status().pairing == "acknowledged"
    assert store.load().pending_pairing is None
    binding = api.fleet_sharing_state()["metadata"]["binding"]
    monkeypatch.setattr("wingman.ui.api.webbrowser.open", lambda url: False)
    try:
        assert api.fleet_sharing_grant_fleet_read(1, binding)["queued"]
        timers.drain()
        failed = api.fleet_sharing_state()
        assert failed["browser_retry"] == "grant"
        assert failed["browser_error"]
        # Another genuine owner status still carries acknowledged pairing;
        # that independent observation must not erase Fleet Read's failure.
        worker.request_participation(False)
        current = api.fleet_sharing_state()
        assert current["order"] > failed["order"]
        assert current["pairing"] == "acknowledged"
        assert current["browser_retry"] == "grant"
        assert current["browser_error"] == failed["browser_error"]
    finally:
        api.shutdown_fleet_sharing()


@pytest.mark.parametrize("replacement", ["action", "binding"])
@pytest.mark.parametrize("kind", ["pair", "grant"])
def test_old_browser_failure_cannot_overwrite_new_action_or_binding(
    tmp_path,
    monkeypatch,
    replacement,
    kind,
):
    api, worker, _client, _store, mono, timers = setup(
        tmp_path,
        state=s.EMPTY if kind == "pair" else PAIRED_STATE,
    )
    api.fleet_sharing_watch(True)
    drive(worker, mono, 12)
    entered, release = threading.Event(), threading.Event()

    def held(url):
        entered.set()
        assert release.wait(3)
        raise RuntimeError("private old failure")

    monkeypatch.setattr("wingman.ui.api.webbrowser.open", held)
    binding = api.fleet_sharing_state()["metadata"]["binding"]

    def request():
        if kind == "pair":
            api.fleet_sharing_pair()
            drive(worker, mono, 1)
        else:
            api.fleet_sharing_grant_fleet_read(1, binding)

    request()
    runner = threading.Thread(target=timers.pending.pop(0))
    runner.start()
    try:
        assert entered.wait(2)
        if replacement == "action":
            request()
        else:
            worker.request_pairing(
                mode="fresh", configured_origin="https://other-relay.test"
            )
            drive(worker, mono, 1)
    finally:
        release.set()
        runner.join(3)
    assert not runner.is_alive()
    assert api.fleet_sharing_state()["browser_error"] is None
    monkeypatch.setattr("wingman.ui.api.webbrowser.open", lambda url: True)
    timers.drain()
    assert api.fleet_sharing_state()["browser_error"] is None
    api.shutdown_fleet_sharing()


def test_pairing_restart_and_generic_auth_error_never_open_browser(
    tmp_path, monkeypatch
):
    api, worker, _client, store, mono, timers = setup(tmp_path, state=s.EMPTY)
    worker.request_pairing()
    worker.iterate_once()
    persisted = store.load()
    api.shutdown_fleet_sharing()
    api, worker, _client, store, mono, timers = setup(tmp_path, state=persisted)
    opened = []
    monkeypatch.setattr("wingman.ui.api.webbrowser.open", opened.append)
    api.fleet_sharing_watch(True)
    api._sharing_page_ready = True
    drive(worker, mono, 2)
    timers.drain()
    assert opened == []
    api.shutdown_fleet_sharing()
    from wingman.fleetsharing.client import FleetRelayError

    api, worker, client, _store, mono, timers = setup(tmp_path)
    client.errors["fetch_device"] = FleetRelayError(
        401, "unauthorized", "not proof of revocation"
    )
    api.fleet_sharing_watch(True)
    api._sharing_page_ready = True
    drive(worker, mono, 10)
    timers.drain()
    assert opened == []
    assert client.recoveries > 0
    api.shutdown_fleet_sharing()


@pytest.mark.parametrize("with_telemetry", [False, True])
def test_reentrant_submission_can_turn_on_back_off_without_deadlock(
    tmp_path, with_telemetry
):
    from tests.test_fleet_bar import FakeTelemetry

    telemetry = FakeTelemetry() if with_telemetry else None
    api, worker, _client, _store, _mono, _timers = setup(tmp_path, telemetry=telemetry)
    reentered = []

    def callback(status):
        if status.participation == "queued" and not reentered:
            reentered.append(True)
            api.fleet_sharing_set_enabled(False)

    worker.subscribe_status(callback)
    outcome = []
    runner = threading.Thread(
        target=lambda: outcome.append(api.fleet_sharing_set_enabled(True)), daemon=True
    )
    runner.start()
    runner.join(2)
    assert not runner.is_alive(), (
        "a synchronous callback deadlocked under the API submission lock"
    )
    assert not api._state.settings["fleet_sharing"]["enabled"]
    assert not settings.load()["fleet_sharing"]["enabled"]
    assert worker.status().local_inhibited
    if telemetry is not None:
        assert telemetry.subscribers == [api._receive_fleet_snapshot, worker.submit]
    api.shutdown_previews()
    if telemetry is not None:
        assert telemetry.subscribers == []


def test_expired_start_is_correlated_to_exact_uuid_not_aggregate_status(tmp_path):
    old = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    state = replace(
        PAIRED_STATE,
        pending_source_commands=(
            p.StartSource(old, 1, UUID, "2026-09-07T11:50:00.000Z"),
        ),
    )
    api, worker, _client, _store, mono, _timers = setup(tmp_path, state=state)
    api.fleet_sharing_watch(True)
    drive(worker, mono, 12)
    payload = api.fleet_sharing_state()
    assert payload["source_results"] == (
        {"source_id": old, "operation": "start", "character_id": 1, "stage": "expired"},
    )
    assert payload["pending_sources"] == ()
    api.shutdown_fleet_sharing()


def test_one_source_ack_never_acknowledges_another_pending_uuid(tmp_path):
    api, worker, _client, _store, mono, _timers = setup(tmp_path)
    api.fleet_sharing_watch(True)
    drive(worker, mono, 12)
    binding = api.fleet_sharing_state()["metadata"]["binding"]
    first = api.fleet_sharing_start_source(1, UUID, binding)["source_id"]
    second = api.fleet_sharing_start_source(1, UUID, binding)["source_id"]
    drive(worker, mono, 1)
    payload = api.fleet_sharing_state()
    assert payload["source_control"] == "acknowledged"
    assert [row["source_id"] for row in payload["pending_sources"]] == [second]
    assert any(row["source_id"] == first for row in payload["sources"]["sources"])
    api.shutdown_fleet_sharing()


def test_pending_source_from_actual_json_is_stoppable_through_new_api(tmp_path):
    from tests.test_fleetsharing_worker import FakeRelayClient, _worker

    file = tmp_path / "sharing.json"
    source_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    s.save(
        file,
        replace(
            PAIRED_STATE,
            pending_source_commands=(
                p.StartSource(source_id, 1, UUID, "2026-09-07T12:00:00.000Z"),
            ),
        ),
    )

    class Disk:
        def load(self):
            return s.load(file)

        def save(self, state):
            s.save(file, state)

    worker = _worker(
        FakeRelayClient(device=DEVICE), store=Disk(), sharing_enabled=lambda: False
    )
    api = Api(make_state(tmp_path), fleet_sharing=worker, timer=Timers())
    api._start_fleet_sharing()
    worker.iterate_once()
    payload = api.fleet_sharing_state()
    assert payload["pending_sources"][0]["source_id"] == source_id
    assert api.fleet_sharing_stop_source(source_id, payload["metadata"]["binding"])[
        "queued"
    ]
    worker.iterate_once()
    assert isinstance(s.load(file).pending_source_commands[0], p.StopSource)
    api.shutdown_fleet_sharing()


def test_concurrent_off_inhibits_while_on_is_saving_and_wins_live_and_disk(
    tmp_path, monkeypatch
):
    api, worker, _client, _store, _mono, _timers = setup(tmp_path)
    entered, release, off_queued = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )
    original = settings._save_locked
    calls = []

    def hold(data, path=None):
        if data["fleet_sharing"]["enabled"]:
            entered.set()
            assert release.wait(3)
        original(data, path)

    def observed(status):
        if entered.is_set() and status.participation == "queued":
            off_queued.set()

    monkeypatch.setattr(settings, "_save_locked", hold)
    worker.subscribe_status(observed)
    on = threading.Thread(
        target=lambda: calls.append(api.fleet_sharing_set_enabled(True))
    )
    off = threading.Thread(
        target=lambda: calls.append(api.fleet_sharing_set_enabled(False))
    )
    on.start()
    try:
        assert entered.wait(2)
        off.start()
        assert off_queued.wait(2)
        assert worker.status().local_inhibited
    finally:
        release.set()
        on.join(3)
        if off.ident:
            off.join(3)
    assert not on.is_alive() and not off.is_alive()
    assert not api._state.settings["fleet_sharing"]["enabled"]
    assert not settings.load()["fleet_sharing"]["enabled"]
    assert len(calls) == 2
    api.shutdown_fleet_sharing()


def test_lazy_runtime_sharing_subscribes_once_off_to_on_and_detaches_before_stop(
    tmp_path,
):
    from tests.test_telemetry_coordinator import FakeDiscovery, FakeStream
    from wingman.telemetry.coordinator import TelemetryCoordinator, _noop_thread_factory
    from wingman.telemetry.metrics import FleetMetrics

    api, worker, _client, _store, _mono, _timers = setup(tmp_path)
    discovery, stream = FakeDiscovery(), FakeStream()
    coordinator = TelemetryCoordinator(
        preview_enabled=lambda: False,
        fleet_enabled=lambda: False,
        alerts_enabled=lambda: False,
        sharing_enabled=lambda: api._state.settings["fleet_sharing"]["enabled"],
        gamelogs_folder=lambda: tmp_path,
        discovery=discovery,
        stream=stream,
        metrics=FleetMetrics(),
        _thread_factory=_noop_thread_factory,
    )
    subscriptions, events = [], []
    subscribe = coordinator.subscribe_fleet

    def track(callback):
        subscriptions.append(callback)
        unsub = subscribe(callback)

        def detach():
            events.append("detach")
            unsub()

        return detach

    coordinator.subscribe_fleet = track
    api._telemetry_factory = lambda: coordinator
    api._reconcile_eve_runtime()
    api._reconcile_eve_runtime()
    assert subscriptions.count(worker.submit) == 1
    assert discovery.starts == 0
    result = api.fleet_sharing_set_enabled(True)
    assert result["applied"] and discovery.starts == 1
    assert subscriptions.count(worker.submit) == 1
    original_stop = worker.stop
    worker.stop = lambda timeout: (
        events.append("sharing-stop"),
        original_stop(timeout),
    )[1]
    api.shutdown_previews()
    assert events.index("detach") < events.index("sharing-stop")
    assert discovery.stops > 0


@pytest.mark.parametrize("value", [1, "true", None, [], {}])
def test_enable_rejects_non_boolean_without_queue_or_settings_write(tmp_path, value):
    api, worker, _client, _store, _mono, _timers = setup(tmp_path)
    result = api.fleet_sharing_set_enabled(value)
    assert result["applied"] is False
    assert worker.status().participation is None


def test_owned_grant_uses_exact_paired_origin_and_rejects_stale_binding(
    tmp_path, monkeypatch
):
    api, worker, client, _store, mono, timers = setup(tmp_path)
    api.fleet_sharing_watch(True)
    drive(worker, mono, 12)
    binding = api.fleet_sharing_state()["metadata"]["binding"]
    opened = []
    monkeypatch.setattr("wingman.ui.api.webbrowser.open", opened.append)
    assert api.fleet_sharing_grant_fleet_read(1, binding)["queued"]
    timers.drain()
    assert opened == ["https://relay.test/auth/eve/fleet-read?character=1"]
    for character, token in [(2, binding), (True, binding), (1, "stale")]:
        assert not api.fleet_sharing_grant_fleet_read(character, token)["queued"]
    assert not client.controls and not client.participation_calls
    assert api.fleet_sharing_grant_fleet_read(1, binding)["queued"]
    worker.request_pairing(mode="fresh", configured_origin="https://other-relay.test")
    drive(worker, mono, 1)
    timers.drain()
    assert opened == ["https://relay.test/auth/eve/fleet-read?character=1"]
    api.shutdown_fleet_sharing()


def test_rejected_unpaired_off_does_not_permanently_prevent_hiding_eve_tools(tmp_path):
    api, worker, _client, _store, mono, _timers = setup(tmp_path, state=s.EMPTY)
    assert api.fleet_sharing_set_enabled(False)["applied"]
    drive(worker, mono, 1)
    assert api.fleet_sharing_state()["metadata"]["binding"] is None
    assert api.set_show_eve_tools(False)["applied"]
    api.shutdown_fleet_sharing()


def test_unknown_sources_or_pending_work_cannot_hide_controls(tmp_path):
    api, worker, _client, _store, mono, _timers = setup(tmp_path)
    api._state.settings["show_eve_tools"] = True
    assert api.set_show_eve_tools(False)["applied"] is False
    api.fleet_sharing_watch(True)
    drive(worker, mono, 12)
    assert api.set_show_eve_tools(False)["applied"] is True
    binding = api.fleet_sharing_state()["metadata"]["binding"]
    result = api.fleet_sharing_start_source(1, UUID, binding)
    assert result["source_id"]
    assert api.set_show_eve_tools(False)["applied"] is False
    api.shutdown_fleet_sharing()
