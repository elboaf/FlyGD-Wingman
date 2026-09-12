"""Shared runtime, both controllers and real primary reconciliation over OS doubles."""

import threading
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from tests.test_companion_controller import until
from tests.test_companion_host import add
from tests.test_companion_host import integrated as integrated
from tests.test_preview_host import crop_pump as crop_pump
from tests.test_preview_runtime_review import parked
from tests.test_wanderer_worker import Client, Clock, ObservedCondition, success
from wingman import settings
from wingman.preview import host as host_mod
from wingman.preview import window
from wingman.telemetry.model import ClientSessionId, RosterClient, RosterSnapshot
from wingman.ui.copy import wanderer_status
from wingman.wanderer.controller import WandererController, WandererPorts
from wingman.wanderer.credentials import CredentialStore
from wingman.wanderer.worker import WandererWorker

BASE = "https://wanderer.example"
PILOT = RosterClient(
    16,
    101,
    "EVE - First Pilot",
    "First Pilot",
    ClientSessionId(16, 101, "First Pilot", 1),
)


@pytest.fixture
def shared(integrated, monkeypatch, tmp_path):
    r = integrated
    h = r.host
    # crop_pump intentionally stubs primary reconciliation for crop-only tests.
    # Restore it: metadata must come from a successfully created primary, never
    # from a fabricated admitted-session set or companion definition.
    monkeypatch.setattr(
        h, "_reconcile_roster", host_mod.PreviewHost._reconcile_roster.__get__(h)
    )
    h._show_labels = lambda: False

    def create(libs, client, rect, **kwargs):
        preview = window.PreviewWindow(libs, client, rect, **kwargs)
        preview.hwnd = 8000 + len(r.native.windows)
        r.native.windows[preview.hwnd] = "primary"
        return preview

    monkeypatch.setattr(host_mod.PreviewWindow, "create", create)
    cfg = settings.load()
    cfg["wanderer"] = {"enabled": True, "base_url": BASE, "map_identifier": "map"}
    credentials = CredentialStore(
        tmp_path / "synthetic-credential",
        protect=lambda b: b[::-1],
        unprotect=lambda b: b[::-1],
    )
    credentials.replace(BASE, "map", "synthetic-token")
    r.client, r.clock, r.cv = Client(), Clock(), ObservedCondition()

    def worker_factory(client, publish):
        r.worker = WandererWorker(client, publish, clock=r.clock, condition=r.cv)
        return r.worker

    r.wanderer = WandererController(
        cfg["wanderer"],
        previews_enabled=True,
        credentials=credentials,
        client=r.client,
        worker_factory=worker_factory,
        ports=WandererPorts(
            update_settings=lambda: settings.update(cfg),
            set_metadata_callback=h.set_metadata_callback,
            set_metadata_generation=lambda *args: h.set_metadata_generation(*args),
            submit_metadata=h.submit_metadata,
            close_metadata_admission=h.close_metadata_admission,
            publish_state=lambda state: None,
            describe_status=wanderer_status,
        ),
    )
    assert r.wanderer.start()

    def wait(predicate):
        with r.cv:
            assert r.cv.wait_for(lambda: predicate(r.wanderer.state()), 5), (
                r.wanderer.state()
            )

    def roster(generation=1, pilot=PILOT):
        h.apply_roster(RosterSnapshot(generation, (pilot,)))
        r.call(lambda: None)

    def eve_on(revision=1):
        r.runtime.set_eve(True, revision)
        until(lambda: r.runtime.snapshot().eve == "active")
        roster(revision)
        wait(lambda state: state["automatic_ready"] and state["previewed"] == 1)

    def advance(now):
        with r.cv:
            r.clock.now = now
            r.cv.notify_all()

    r.wait_metadata, r.roster, r.eve_on, r.advance = wait, roster, eve_on, advance
    yield r
    r.wanderer.close_admission()
    with r.client.cv:
        for call in r.client.calls:
            call.reply(success())
    assert r.wanderer.stop(5)


def label(r, expected="HOME"):
    # Worker health is published before its detached metadata callback returns.
    # Wait for the actual pump-visible result, not just the worker's projection.
    until(
        lambda: (
            r.call(lambda: r.host._windows[PILOT.character]._system_name) == expected
        )
    )
    return r.call(lambda: r.host._windows[PILOT.character]._system_name)


@pytest.mark.parametrize("demand", ["companion", "selection"])
def test_unrelated_pump_does_not_authorize_automatic_metadata_but_test_works(
    shared, demand
):
    r = shared
    if demand == "companion":
        add(r)
    else:
        lease = r.runtime.acquire_selection(900)
        assert lease
        until(lambda: r.runtime.snapshot().pump == "active")
    r.call(lambda: None)
    assert r.host.is_running and not r.host.runtime_enabled
    assert not r.host.metadata_available()
    assert not r.host.metadata_sessions()
    r.wanderer._apply_runtime()
    assert not r.wanderer.state()["automatic_ready"]
    assert r.worker._request_thread is None
    assert r.wanderer.test_connection(BASE, "map", "")["test_accepted"]
    r.client.call(1).reply(success())
    r.wait_metadata(lambda state: state["test_result"] == "success")
    assert not r.wanderer.state()["automatic_ready"]
    if demand == "selection":
        r.runtime.release_selection(lease)


def test_eve_off_atomically_fences_metadata_while_companion_and_selection_survive(
    shared,
):
    r = shared
    identity = add(r)
    companion = r.host._companion_family.live[identity].window
    r.eve_on()
    r.client.call(1).reply(success())
    r.wait_metadata(lambda state: state["available"] == 1)
    assert label(r) == "HOME"
    generation = r.wanderer.state()["generation"]
    owner, hwnd = r.host._thread, r.host._hwnd
    lease = r.runtime.acquire_selection(901)
    with parked(r):
        r.runtime.set_eve(False, 2)
        assert not r.host.metadata_available()
        assert not r.host.metadata_sessions()
        assert not r.host._metadata_values
        assert not r.host._metadata_generation_active
        assert not r.host._metadata_wake_pending
        r.host.submit_metadata(generation, {PILOT.session: "OLD"})
        assert not r.host._metadata_values
    until(lambda: r.runtime.snapshot().eve == "stopped")
    assert r.host._thread is owner and r.host._hwnd == hwnd
    assert r.host.is_running and not companion.closed
    assert r.runtime.snapshot().selection_pending
    r.runtime.release_selection(lease)


def test_delayed_generation_handoff_cannot_acquire_a_new_eve_epoch(shared, monkeypatch):
    r = shared
    add(r)
    r.eve_on()
    old_http = r.client.call(1)
    entered, release = Event(), Event()
    setter = r.host.set_metadata_generation
    observed = []

    def delayed(*args):
        if not entered.is_set():
            observed.append(args)
            entered.set()
            assert release.wait(5)
            result = setter(*args)
            observed.append(result)
            r.host.submit_metadata(args[0], {PILOT.session: "DELAYED CONFIG"})
            observed.append(dict(r.host._metadata_values))
            return result
        return setter(*args)

    monkeypatch.setattr(r.host, "set_metadata_generation", delayed)
    with ThreadPoolExecutor(max_workers=1) as pool:
        # Force a new *ready* connection config to pause after capture, not an
        # already-disabled config which could never start automatic HTTP.
        changing = pool.submit(r.wanderer.test_connection, BASE, "new-map", "new-token")
        assert entered.wait(5)
        try:
            r.runtime.set_eve(False, 2)
            until(lambda: r.runtime.snapshot().eve == "stopped")
            r.runtime.set_eve(True, 3)
            until(lambda: r.runtime.snapshot().eve == "active")
            r.roster(3)
        finally:
            release.set()
        changing.result(5)
    assert len(observed[0]) == 2, "controller must return its captured EVE epoch"
    assert observed[1] is False and observed[2] == {}
    r.wanderer.set_previews_enabled(True)
    old_http.reply(success())
    r.wait_metadata(lambda state: not state["in_flight"])
    assert label(r, None) is None
    r.advance(102)
    r.client.call(2).reply(success(102))
    r.wait_metadata(lambda state: state["available"] == 1)
    assert label(r) == "HOME"
    r.advance(116)
    r.wait_metadata(lambda state: state["stale"] == 1)
    assert label(r, None) is None


def test_old_metadata_wake_cannot_spend_new_epoch_wake(shared):
    r = shared
    add(r)
    r.eve_on()
    r.client.call(1).reply(success())
    r.wait_metadata(lambda state: state["available"] == 1)
    old_epoch = r.host._eve_epoch
    r.runtime.set_eve(False, 2)
    until(lambda: r.runtime.snapshot().eve == "stopped")
    r.eve_on(3)
    r.advance(102)
    r.client.call(2).reply(success(102))
    r.wait_metadata(lambda state: state["available"] == 1)

    def old_before_new():
        generation = r.wanderer.state()["generation"]
        r.host.submit_metadata(generation, {PILOT.session: "FRESH"})
        assert r.host._metadata_wake_pending
        r.host._host_proc(42, host_mod.win32.WM_APP_METADATA, old_epoch, 0)
        assert r.host._metadata_wake_pending
        r.host._host_proc(42, host_mod.win32.WM_APP_METADATA, r.host._eve_epoch, 0)
        assert not r.host._metadata_wake_pending
        assert r.host._windows[PILOT.character]._system_name == "FRESH"

    r.call(old_before_new)


@pytest.mark.parametrize("boundary", ["render", "rebind"])
def test_off_during_primary_native_callback_cannot_readmit_old_roster(
    shared, monkeypatch, boundary
):
    r = shared
    add(r)
    r.eve_on()
    r.client.call(1).reply(success())
    r.wait_metadata(lambda state: state["available"] == 1)
    assert label(r) == "HOME"
    preview = r.host._windows[PILOT.character]
    entered, release = Event(), Event()
    method = "set_system_name" if boundary == "render" else "rebind_client"
    original = getattr(preview, method)

    def held(*args):
        if not entered.is_set():
            entered.set()
            assert release.wait(5)
        return original(*args)

    monkeypatch.setattr(preview, method, held)
    with ThreadPoolExecutor(max_workers=1) as pool:
        if boundary == "render":
            pending = pool.submit(r.call, r.host._apply_metadata)
        else:
            replacement = RosterClient(
                16,
                101,
                PILOT.title,
                PILOT.character,
                ClientSessionId(16, 101, PILOT.character, 2),
            )
            pending = pool.submit(r.roster, 2, replacement)
        assert entered.wait(5)
        try:
            r.runtime.set_eve(False, 2)
            assert not r.host.metadata_sessions()
        finally:
            release.set()
        pending.result(5)
    assert preview._system_name is None
    until(lambda: r.runtime.snapshot().eve == "stopped")
    assert not r.host.metadata_sessions() and not r.host._latest_roster
    assert not r.host._primary_sessions and not r.host._metadata_values
    assert r.host.is_running


@pytest.mark.parametrize("boundary", ["storage", "activation"])
def test_eve_not_ready_during_drain_or_failed_activation_companion_remains(
    shared, monkeypatch, boundary
):
    r = shared
    identity = add(r)
    companion = r.host._companion_family.live[identity].window
    if boundary == "storage":
        r.eve_on()
        entered, release = Event(), Event()
        r.store._flush_primary = lambda: (entered.set(), release.wait(5))[-1]
        r.runtime.set_eve(False, 2)
        assert entered.wait(5)
        try:
            r.runtime.set_eve(True, 3)
            r.call(lambda: None)
            assert not r.host.metadata_available()
            assert not r.host.metadata_sessions()
            assert not companion.closed and r.host.is_running
        finally:
            release.set()
        until(lambda: r.runtime.snapshot().eve == "active")
        until(r.host.metadata_available)
    else:

        def fail(libs):
            raise OSError("synthetic hook failure")

        monkeypatch.setattr(r.host, "_install_hook", fail)
        r.runtime.set_eve(True, 1)
        until(lambda: r.runtime.snapshot().eve == "failed")
        r.call(lambda: None)
        assert not r.host.metadata_available()
        assert not r.host.metadata_sessions()
        assert not companion.closed and r.host.is_running


def test_companion_toggle_preserves_fresh_metadata_generation_and_pending_test(shared):
    r = shared
    add(r)
    r.eve_on()
    r.client.call(1).reply(success())
    r.wait_metadata(lambda state: state["available"] == 1)
    assert label(r) == "HOME"
    assert r.wanderer.test_connection(BASE, "map", "")["test_accepted"]
    generation = r.wanderer.state()["generation"]
    for enabled in (False, True):
        assert r.receipt(r.controller.set_master(enabled))["persisted"]
        until(
            lambda: (
                r.runtime.snapshot().companions == ("active" if enabled else "stopped")
            )
        )
        r.wanderer._apply_runtime()
        assert r.wanderer.state()["generation"] == generation
        assert r.wanderer.state()["test_pending"]
        assert label(r) == "HOME"
    r.advance(102)
    r.client.call(2).reply(success(102))
    r.wait_metadata(lambda state: state["test_result"] == "success")


def test_metadata_only_close_does_not_close_eve_alerts_companions_or_selection(shared):
    r = shared
    identity = add(r)
    companion = r.host._companion_family.live[identity].window
    r.eve_on()
    r.client.call(1).reply(success())
    r.wait_metadata(lambda state: state["available"] == 1)
    assert label(r) == "HOME"
    owner, crop = r.host._thread, r.host._crop_controller
    lease = r.runtime.acquire_selection(902)
    with parked(r):
        r.host.raise_alert(PILOT.character, "warp_scramble", {})
        alerts = list(r.host._pending_alerts)
        r.wanderer.close_admission()
        assert not r.host.metadata_available() and not r.host.metadata_sessions()
        assert r.host._pending_alerts == alerts
        # The OS double has no bitmap DC. Consume the verified admission here;
        # existing alert-native tests own the paint path, not this boundary.
        assert r.host._drain_alerts() == alerts
        assert r.host.runtime_enabled and not r.host._closing
    assert label(r, None) is None
    assert r.host._thread is owner and r.host._crop_controller is crop
    assert not companion.closed and r.runtime.snapshot().selection_pending
    r.runtime.release_selection(lease)


def test_reordered_callbacks_carry_actual_epoch_even_with_same_session(
    shared, monkeypatch
):
    r = shared
    add(r)
    r.eve_on()
    old = r.client.call(1)
    generation = r.wanderer.state()["generation"]
    callback, notifications = r.host._metadata_callback, []
    monkeypatch.setattr(
        r.host, "_metadata_callback", lambda *args: notifications.append(args)
    )
    with r.wanderer._handoff_lock:
        r.runtime.set_eve(False, 2)
        until(lambda: r.runtime.snapshot().eve == "stopped")
        r.runtime.set_eve(True, 3)
        until(lambda: r.runtime.snapshot().eve == "active")
        r.roster(3)
        for notice in reversed(notifications):
            callback(*notice)
    r.wait_metadata(lambda state: state["generation"] > generation)
    old.reply(success())
    r.wait_metadata(lambda state: not state["in_flight"])
    assert label(r, None) is None
    assert r.wanderer._host_epoch == r.host._eve_epoch
    assert r.wanderer._sessions == frozenset({PILOT.session})


def test_retained_eve_picker_fonts_withhold_metadata_not_companion_dispatch(shared):
    r = shared
    identity = add(r)
    r.eve_on()
    r.host.request_crop("select", PILOT.character)
    r.call(lambda: None)

    def retain_fonts():
        picker = r.host._crop_controller.picker
        assert picker is not None
        r.native.held_fonts.update(r.native.fonts)
        picker.cancel()
        return picker

    picker = r.call(retain_fonts)
    try:
        r.runtime.set_eve(False, 2)
        r.runtime.set_eve(True, 3)
        r.store.drain().result(5)
        r.call(lambda: None)
        assert r.host._crop_controller.picker is picker
        assert not r.host.metadata_available() and not r.host.metadata_sessions()
        assert r.host.is_running
        assert not r.host._companion_family.live[identity].window.closed
    finally:
        r.native.held_fonts.clear()
        r.host._post(0)
    until(lambda: r.runtime.snapshot().eve == "active")
    until(r.host.metadata_available)


def api_for_shared(r, tmp_path):
    from tests.test_api import make_api

    api = make_api(
        tmp_path,
        preview_host=r.host,
        preview_runtime=r.runtime,
        companion_controller=r.controller,
    )
    # Replace only the unopened default controller with our synthetic-credential
    # controller. Both use the same real host ports, bound before any demand.
    api._wanderer = r.wanderer
    return api


def test_failed_preview_persistence_changes_neither_demand_nor_wanderer(
    shared, tmp_path, monkeypatch
):
    r = shared
    api = api_for_shared(r, tmp_path)
    add(r)
    try:
        assert api.set_preview_enabled(True)
        until(lambda: r.runtime.snapshot().eve == "active")
        r.roster()
        r.wanderer._apply_runtime()
        demand = r.runtime._demand
        generation = r.wanderer.state()["generation"]

        def fail(*args):
            raise OSError("synthetic save failure")

        monkeypatch.setattr(settings, "_save_locked", fail)
        assert not api.set_preview_enabled(False)
        assert r.runtime._demand == demand
        assert r.wanderer.state()["previews_enabled"]
        assert r.wanderer.state()["generation"] == generation
        assert r.host.runtime_enabled
    finally:
        api.shutdown_previews()


def test_master_demand_fences_before_slow_wanderer_handoff(
    shared, tmp_path, monkeypatch
):
    r = shared
    api = api_for_shared(r, tmp_path)
    add(r)
    assert api.set_preview_enabled(True)
    until(lambda: r.runtime.snapshot().eve == "active")
    r.roster()
    entered, release = Event(), Event()
    original = r.wanderer.set_previews_enabled

    def held(enabled):
        entered.set()
        assert release.wait(5)
        original(enabled)

    monkeypatch.setattr(r.wanderer, "set_previews_enabled", held)
    with ThreadPoolExecutor(max_workers=1) as pool:
        stopping = pool.submit(api.set_preview_enabled, False)
        try:
            assert entered.wait(5)
            assert not r.host.runtime_enabled and not r.host.metadata_available()
            assert not r.runtime._demand.eve
            assert r.runtime._demand.companions
        finally:
            release.set()
            assert stopping.result(5)
            api.shutdown_previews()


def test_final_close_retains_http_and_companion_save_owners_independently(
    shared, tmp_path, monkeypatch
):
    r = shared
    api = api_for_shared(r, tmp_path)
    identity = add(r)
    assert api.set_preview_enabled(True)
    until(lambda: r.runtime.snapshot().eve == "active")
    r.roster()
    r.wait_metadata(lambda state: state["automatic_ready"])
    blocked_http = r.client.call(1)
    http_owner, native_owner = r.worker._request_thread, r.host._thread
    companion_owner = r.controller._worker
    entered, release = Event(), Event()
    save = settings._save_locked

    def held_save(*args):
        if threading.current_thread() is companion_owner:
            entered.set()
            assert release.wait(5)
        return save(*args)

    monkeypatch.setattr(settings, "_save_locked", held_save)
    generation = r.controller.state()["rows"][0]["generation"]
    pending = r.controller.edit(identity, "New label", "exact", "Mapper", generation)
    assert entered.wait(5)
    stop_http, stop_companion = r.wanderer.stop, r.controller.shutdown
    monkeypatch.setattr(r.wanderer, "stop", lambda timeout=1: stop_http(0))
    monkeypatch.setattr(r.controller, "shutdown", lambda timeout=5: stop_companion(0))
    try:
        api.shutdown_previews()
        assert r.host._closing and r.host._metadata_callback is None
        assert not r.host.metadata_available() and not r.host.metadata_sessions()
        assert r.host._thread is native_owner and native_owner.is_alive()
        assert r.worker._request_thread is http_owner and http_owner.is_alive()
        assert r.controller._worker is companion_owner
        assert not r.wanderer.start()
        assert r.runtime.acquire_selection(999) is None
        release.set()
        assert r.controller._done.wait(5)
        assert r.receipt(pending)["persisted"]
        api.shutdown_previews()
        assert not native_owner.is_alive()
        assert http_owner.is_alive(), "native completion must not wait for HTTP"
        blocked_http.reply(success())
        assert stop_http(5)
        assert r.worker._request_thread is http_owner
    finally:
        release.set()
        blocked_http.reply(success())
        assert stop_http(5)
        assert stop_companion(5)
        api.shutdown_previews()


def test_test_refuses_rejected_epoch_handoff_instead_of_testing_old_connection(
    shared, monkeypatch
):
    r = shared
    add(r)
    r.eve_on()
    r.client.call(1).reply(success())
    r.wait_metadata(lambda state: not state["in_flight"])
    callback, notifications = r.host._metadata_callback, []
    with monkeypatch.context() as patch:
        patch.setattr(
            r.host, "_metadata_callback", lambda *args: notifications.append(args)
        )
        r.runtime.set_eve(False, 2)
        until(lambda: r.runtime.snapshot().eve == "stopped")
        r.runtime.set_eve(True, 3)
        until(lambda: r.runtime.snapshot().eve == "active")
        r.roster(3)
        try:
            result = r.wanderer.test_connection(BASE, "new-map", "new-token")
            assert result["persisted"]
            assert not result["test_accepted"], (
                "rejected handoff must not test the old binding"
            )
            assert not r.worker.state().test_pending
        finally:
            callback(*notifications[-1])
    r.wait_metadata(lambda state: state["generation"] > 1 and state["automatic_ready"])
    assert r.wanderer.test_connection(BASE, "new-map", "")["test_accepted"]
    r.advance(102)
    call = r.client.call(2)
    assert call.args[:3] == (BASE, "new-map", "new-token")
    call.reply(success(102))
    r.wait_metadata(lambda state: state["test_result"] == "success")


def test_host_application_messages_are_disjoint():
    messages = {
        name: value
        for name, value in vars(host_mod.win32).items()
        if name.startswith("WM_APP_")
    }
    assert len(set(messages.values())) == len(messages), messages
