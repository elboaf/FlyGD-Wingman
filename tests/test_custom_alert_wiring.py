"""Real Api/custom authority composition, without native workers or gameplay input."""

import copy
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from tests.test_alerts_wiring import FakePreviewHost, FakeTelemetry
from tests.test_api import make_api, make_state
from tests.test_startup import startup as startup
from tests.test_telemetry_coordinator import FakeDiscovery, _noop_thread_factory
from wingman import __main__ as main_mod
from wingman import paths, settings
from wingman.alerts import service
from wingman.alerts.controller import AlertsController
from wingman.telemetry.coordinator import TelemetryCoordinator
from wingman.telemetry.gamelogs import GameLogStream
from wingman.telemetry.model import CustomMatcherHealth
from wingman.ui.api import Api

# The startup fixture stubs optional construction; keep these real builders so
# its main() execution tests the same composition as a Windows launch.
BUILD_HOST = main_mod.build_preview_host
BUILD_POLICY = main_mod.build_alert_policy
BUILD_TELEMETRY = main_mod.build_telemetry


def enable_custom(api):
    with settings.update(api._state.settings) as document:
        document.setdefault("preview", {}).update(enabled=True)
        document["preview"].setdefault("alerts", {})["enabled"] = True
    result = api.add_custom_alert()
    assert result["applied"] and result["persisted"]
    rule_id = result["rule_id"]
    draft = dict(result["state"]["rules"][0], search="fleet invite", enabled=True)
    draft.pop("id")
    assert api.edit_custom_alert(rule_id, draft)["applied"]
    return rule_id, draft


def inert_runtime(monkeypatch, state, host, controller):
    """Real stream/coordinator; only worker creation and Win32 discovery are fake."""
    monkeypatch.setattr(main_mod.sys, "platform", "win32")
    monkeypatch.setattr("wingman.telemetry.clients.ClientDiscovery", FakeDiscovery)
    monkeypatch.setattr(
        "wingman.telemetry.gamelogs.GameLogStream",
        lambda **kwargs: GameLogStream(**kwargs, _thread_factory=_noop_thread_factory),
    )
    monkeypatch.setattr(
        "wingman.telemetry.coordinator.TelemetryCoordinator",
        lambda **kwargs: TelemetryCoordinator(
            **kwargs, _thread_factory=_noop_thread_factory
        ),
    )
    policy = BUILD_POLICY(state, host, controller)
    runtime = BUILD_TELEMETRY(state, host, policy, controller)
    assert runtime is not None
    return runtime, policy


def test_coordinator_exposes_stream_matcher_health_without_starting(tmp_path):
    from tests.test_telemetry_coordinator import _harness

    stream = GameLogStream(_thread_factory=_noop_thread_factory)
    runtime = _harness(tmp_path, stream=stream).coordinator
    assert runtime.custom_matcher_health() == CustomMatcherHealth("inactive")
    assert not stream._started


def test_real_api_fallback_round_trip_uses_committed_authority(tmp_path):
    api = make_api(tmp_path)
    assert isinstance(api._alerts_controller, AlertsController)
    assert api._alerts_controller._reader is settings.committed_preview(
        api._state.settings
    )
    assert not any(not name.startswith("_") for name in vars(api))
    assert api.get_custom_alert_state()["rules"] == []
    rule_id, draft = enable_custom(api)
    assert (
        settings.load()["preview"]["alerts"]["custom_rules"][0]["search"]
        == "fleet invite"
    )
    assert api.set_custom_alert_enabled(rule_id, False)["applied"]
    assert api.get_custom_alert_state()["rules"][0]["enabled"] is False
    assert api.edit_custom_alert(rule_id, dict(draft, search="new invite"))["applied"]
    assert api.remove_custom_alert(rule_id)["state"]["rules"] == []
    assert not api.edit_custom_alert(rule_id, draft)["applied"]
    assert api._window.evaluated == []  # reads/mutations add no Alerts push


def test_custom_test_facade_uses_style_without_persistence(monkeypatch, tmp_path):
    played = []
    monkeypatch.setattr(
        service, "play_sound", lambda sid, volume: played.append((sid, volume))
    )
    host = FakePreviewHost(characters=("Alice",))
    host.started = 1
    api = make_api(tmp_path, preview_host=host)
    rule_id, draft = enable_custom(api)
    snapshot = api._alerts_controller.runtime_snapshot()
    assert api.test_custom_alert(rule_id, dict(draft, sound="obey")) == {
        "applied": True,
        "persisted": False,
        "error": None,
    }
    assert played == [("obey", 100)]
    assert host.raised[0][0:2] == ("Alice", "custom")
    assert host.raised[0][2]["persist_until_selected"] is False
    assert api._alerts_controller.runtime_snapshot() is snapshot


def test_missing_runtime_reads_do_not_trigger_lazy_build(monkeypatch, tmp_path):
    def forbidden():
        pytest.fail("a read or custom edit must not construct telemetry")

    monkeypatch.setattr(service, "play_sound", lambda *_args: None)
    api = make_api(tmp_path, telemetry_factory=forbidden)
    assert api._custom_matcher_health().state == "inactive"
    rule_id, draft = enable_custom(api)
    state = api.get_custom_alert_state()
    assert state["matcher"] == {"state": "waiting", "detail": None}
    assert state["reader"]["running"] is False
    assert api.get_alert_state()["running"] is False
    assert api._custom_matcher_health().state == "waiting"
    result = api.test_custom_alert(rule_id, dict(draft, sound="obey"))
    assert result["applied"] and not result["persisted"]
    assert "unavailable" in result["error"]


def test_supplied_controller_is_retained_and_health_ports_follow_lazy_runtime(
    monkeypatch, tmp_path
):
    state = make_state(tmp_path)
    box = {}
    controller = main_mod.build_alerts_controller(state, None, box)
    box["alerts"] = controller

    def forbidden(_self):
        pytest.fail("supplied controller must not be duplicated")

    monkeypatch.setattr(Api, "_build_alerts_controller", forbidden)
    runtime, _policy = inert_runtime(monkeypatch, state, None, controller)
    attempts = []

    def factory():
        attempts.append(True)
        return runtime if len(attempts) == 2 else None

    api = Api(state, alerts_controller=controller, telemetry_factory=factory)
    box["api"] = api
    api._fleet_worker._thread_factory = _noop_thread_factory
    enable_custom(api)
    assert api._alerts_controller is controller
    assert controller.state()["matcher"]["state"] == "waiting"
    assert attempts == []
    try:
        api._reconcile_eve_runtime()
        assert api._telemetry is None
        api._reconcile_eve_runtime()
        assert api._telemetry is runtime
        assert len(attempts) == 2
        snapshot = controller.runtime_snapshot()
        assert runtime._custom_snapshot() is snapshot
        assert runtime._stream._custom_snapshot() is snapshot
        health = CustomMatcherHealth("degraded", detail="matcher_failed")
        monkeypatch.setattr(runtime._stream, "custom_health", lambda: health)
        assert runtime.custom_matcher_health() is health
        assert api._custom_matcher_health() is health
        assert controller.state()["matcher"] == {
            "state": "degraded",
            "detail": "matcher_failed",
        }
        assert controller.state()["reader"] == api._custom_reader_state()
    finally:
        api.shutdown_previews()


def test_fleet_only_keeps_shared_reader_but_empty_matcher(monkeypatch, tmp_path):
    state = make_state(
        tmp_path, gamelogs_dir=str(tmp_path), fleet_bar={"enabled": True}
    )
    box = {}
    controller = main_mod.build_alerts_controller(state, None, box)
    box["alerts"] = controller
    runtime, policy = inert_runtime(monkeypatch, state, None, controller)
    api = Api(state, alerts_controller=controller, telemetry=runtime)
    box["api"] = api
    api._fleet_worker._thread_factory = _noop_thread_factory
    try:
        api._reconcile_eve_runtime()
        assert policy is None  # preserve optional-host behavior
        assert runtime._stream._started
        assert runtime._stream._custom_snapshot().executable == ()
        assert api.get_custom_alert_state()["reader"]["running"] is True
        assert api.get_custom_alert_state()["matcher"]["state"] == "inactive"
        assert api.get_alert_state()["running"] is False
    finally:
        api.shutdown_previews()


def test_builtin_style_and_volume_do_not_retire_custom_or_restart_stream(tmp_path):
    telemetry = FakeTelemetry()
    api = make_api(tmp_path, telemetry=telemetry)
    rule_id, draft = enable_custom(api)
    before = api._alerts_controller.runtime_snapshot()
    assert api.set_alert_event("combat", "color", "#abcdef")["applied"]
    assert api.set_alert_volume(23)["applied"]
    after = api._alerts_controller.runtime_snapshot()
    assert after.custom_rules == before.custom_rules
    assert after.rules_revision == before.rules_revision
    assert after.activation_epoch == before.activation_epoch
    assert after.volume == 23
    assert api.edit_custom_alert(rule_id, dict(draft, search="new invite"))["applied"]
    changed = api._alerts_controller.runtime_snapshot()
    assert changed.custom_rules[0].generation > before.custom_rules[0].generation
    assert not api._alerts_controller.is_current(
        rule_id, before.custom_rules[0].generation, before.activation_epoch
    )
    assert telemetry.reconciled == telemetry.stopped == 0


@pytest.mark.parametrize("master", ["alerts", "preview"])
def test_master_off_on_retires_old_activation_not_rule_generation(tmp_path, master):
    telemetry = FakeTelemetry()
    api = make_api(tmp_path, telemetry=telemetry)
    api._fleet_worker._thread_factory = _noop_thread_factory
    rule_id, _draft = enable_custom(api)
    controller = api._alerts_controller
    before = controller.runtime_snapshot()
    generation = before.custom_rules[0].generation
    change = api.set_alert_enabled if master == "alerts" else api.set_preview_enabled
    try:
        assert change(False)
        assert not controller.is_current(rule_id, generation, before.activation_epoch)
        assert change(True)
        after = controller.runtime_snapshot()
        assert after.custom_rules[0].generation == generation
        assert after.rules_revision == before.rules_revision
        assert after.activation_epoch > before.activation_epoch
        assert not controller.is_current(rule_id, generation, before.activation_epoch)
        assert controller.is_current(rule_id, generation, after.activation_epoch)
        assert telemetry.reconciled == 2
    finally:
        api.shutdown_previews()


@pytest.mark.parametrize("fails", [False, True], ids=["commit", "rollback"])
@pytest.mark.parametrize("mutation", ["edit", "alerts", "preview", "volume"])
def test_real_api_readers_remain_committed_during_save(
    monkeypatch, tmp_path, fails, mutation
):
    telemetry = FakeTelemetry()
    host = FakePreviewHost()
    api = make_api(tmp_path, telemetry=telemetry, preview_host=host)
    api._fleet_worker._thread_factory = _noop_thread_factory
    rule_id, draft = enable_custom(api)
    controller = api._alerts_controller
    old = controller.runtime_snapshot()
    old_state = api.get_alert_state()
    old_file = paths.settings_file().read_bytes()
    entered, release = Event(), Event()
    original_save = settings._save_locked

    def held_save(document, path=None):
        entered.set()
        assert release.wait(5)
        if fails:
            raise OSError("read-only")
        original_save(document, path)

    monkeypatch.setattr(settings, "_save_locked", held_save)
    calls = {
        "edit": lambda: api.edit_custom_alert(
            rule_id, dict(draft, search="changed invite")
        ),
        "alerts": lambda: api.set_alert_enabled(False),
        "preview": lambda: api.set_preview_enabled(False),
        "volume": lambda: api.set_alert_volume(23),
    }
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            future = pool.submit(calls[mutation])
            try:
                assert entered.wait(3)
                assert pool.submit(api.get_alert_state).result(timeout=1) == old_state
                assert pool.submit(controller.runtime_snapshot).result(timeout=1) is old
                assert (
                    pool.submit(api.get_custom_alert_state).result(timeout=1)["rules"][
                        0
                    ]["search"]
                    == "fleet invite"
                )
                assert telemetry.reconciled == 0
            finally:
                release.set()
            result = future.result(timeout=3)
        applied = result if mutation == "preview" else result["applied"]
        assert applied is not fails
        assert telemetry.reconciled == (
            int(not fails) if mutation in {"preview", "alerts"} else 0
        )
        if fails:
            assert controller.runtime_snapshot() is old
            assert paths.settings_file().read_bytes() == old_file
        else:
            now = controller.runtime_snapshot()
            if mutation in {"preview", "alerts"}:
                assert now.custom_rules[0].generation == old.custom_rules[0].generation
                assert now.activation_epoch > old.activation_epoch
                assert now.executable == ()
            elif mutation == "edit":
                assert now.custom_rules[0].generation > old.custom_rules[0].generation
            else:
                assert now.volume == 23
                assert now.custom_rules == old.custom_rules
    finally:
        api.shutdown_previews()


def test_real_stream_edit_changes_matcher_without_restart(monkeypatch, tmp_path):
    from tests.test_telemetry_gamelogs import NOW, _log

    host = FakePreviewHost(characters=("Alice",))
    host.runtime_enabled = True
    api = make_api(tmp_path, preview_host=host)
    api._fleet_worker._thread_factory = _noop_thread_factory
    rule_id, draft = enable_custom(api)
    with settings.update(api._state.settings) as document:
        document["gamelogs_dir"] = str(tmp_path)
    runtime, _policy = inert_runtime(
        monkeypatch, api._state, host, api._alerts_controller
    )
    api._telemetry = runtime
    path = _log(tmp_path, "Alice")
    stream = runtime._stream
    try:
        api._reconcile_eve_runtime()
        stream.scan_once(NOW)
        runtime.dispatch_once(0)
        owner = stream._worker
        epoch = runtime._stream_delivery_epoch
        with path.open("a", encoding="utf-8") as output:
            output.write("(notify) FLEET INVITE\n")
        stream.scan_once(NOW)
        runtime.dispatch_once(0)
        assert [(character, kind) for character, kind, _ in host.raised] == [
            ("Alice", "custom")
        ]
        assert api.get_custom_alert_state()["matcher"]["state"] == "active"
        assert api.edit_custom_alert(rule_id, dict(draft, search="changed invite"))[
            "applied"
        ]
        assert api.get_custom_alert_state()["matcher"]["state"] == "waiting"
        with path.open("a", encoding="utf-8") as output:
            output.write("(notify) FLEET INVITE\n")
        stream.scan_once(NOW)
        runtime.dispatch_once(0)
        assert len(host.raised) == 1
        with path.open("a", encoding="utf-8") as output:
            output.write("(notify) CHANGED INVITE\n")
        stream.scan_once(NOW)
        runtime.dispatch_once(0)
        assert len(host.raised) == 2
        assert stream._worker is owner
        assert runtime._stream_delivery_epoch == epoch
        assert api.get_custom_alert_state()["matcher"]["state"] == "active"
    finally:
        api.shutdown_previews()


def test_shutdown_fences_controller_and_old_ingress_before_host_teardown(
    monkeypatch, tmp_path
):
    from tests.test_custom_alert_admission import _match
    from tests.test_telemetry_coordinator import _lifecycle
    from wingman.telemetry.model import StreamBatch

    host = FakePreviewHost()
    host.runtime_enabled = True
    api = make_api(tmp_path, preview_host=host)
    api._fleet_worker._thread_factory = _noop_thread_factory
    rule_id, draft = enable_custom(api)
    with settings.update(api._state.settings) as document:
        document["gamelogs_dir"] = str(tmp_path)
    controller = api._alerts_controller
    snapshot = controller.runtime_snapshot()
    runtime, _ = inert_runtime(monkeypatch, api._state, host, controller)
    api._telemetry = runtime
    api._reconcile_eve_runtime()
    runtime.dispatch_once(0)
    callback = runtime._stream._batch_subscribers[0]
    batch = StreamBatch((_lifecycle("Alice"),), (_match(snapshot),))
    callback(batch)
    assert runtime._custom_pending
    tokens = (rule_id, snapshot.custom_rules[0].generation, snapshot.activation_epoch)
    assert controller.is_current(*tokens)
    stopped = []

    def native_stop(timeout=5.0, *, final=False):
        assert final
        assert not controller.is_current(*tokens)
        assert not controller.is_current(rule_id, 0, 0)
        assert runtime._custom_pending == {}
        assert not runtime._custom_admission_open
        stopped.append(True)
        return False  # native owner remains retained for cleanup, never replaced

    host.stop = native_stop
    api.shutdown_previews()
    assert stopped == [True]
    assert api._telemetry is runtime and api._preview_host is host
    callback(batch)
    assert runtime._custom_pending == {}
    assert not api.test_custom_alert(rule_id, draft)["applied"]
    assert api._reconcile_eve_runtime() is None
    assert controller.runtime_snapshot() is snapshot


def test_shutdown_deadline_keeps_inflight_owner_and_closes_custom_immediately(tmp_path):
    telemetry = FakeTelemetry()
    api = make_api(tmp_path, telemetry=telemetry)
    api._fleet_worker._thread_factory = _noop_thread_factory
    rule_id, _draft = enable_custom(api)
    entered, release = Event(), Event()
    waits = []

    class TimedOutIdle:
        def clear(self):
            pass

        def set(self):
            pass

        def wait(self, timeout):
            waits.append(timeout)
            return False

    api._eve_runtime_idle = TimedOutIdle()

    def held_reconcile():
        entered.set()
        assert release.wait(5)

    telemetry.reconcile = held_reconcile
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(api._reconcile_eve_runtime)
        try:
            assert entered.wait(3)
            api.shutdown_previews()
            assert waits == [5.0]
            assert telemetry.custom_closed and telemetry.stopped == 0
            assert not api._alerts_controller.is_current(rule_id, 0, 0)
            assert api._telemetry is telemetry
            assert api._reconcile_eve_runtime() is None
        finally:
            release.set()
        future.result(timeout=3)
    assert telemetry.stopped == 1
    assert telemetry.subscribers == []


@pytest.mark.parametrize("lazy", [False, True])
def test_main_composes_one_controller_before_any_start_and_lazy_reuses_it(
    startup, monkeypatch, tmp_path, lazy
):
    box_seen, controllers, runtimes = [], [], []
    native_hosts = []
    attempts = []
    original_controller = main_mod.build_alerts_controller

    def make_host(state, box):
        reader = settings.committed_preview(state.settings)
        # Exercise the actual constructor callback wiring without starting HWNDs.
        host = BUILD_HOST(state, box)
        assert host is not None
        host._test_reader = reader
        box_seen.append(box)
        return host

    def capture_host(**kwargs):
        host = FakePreviewHost()
        host.runtime_enabled = True
        host._custom_alert_current = kwargs["custom_alert_current"]
        host.set_discovery_request = lambda callback: None
        original_start = host.start

        def start():
            box = box_seen[0]
            assert box["api"]._alerts_controller is box["alerts"]
            original_start()

        host.start = start
        native_hosts.append(host)
        return host

    def build_controller(state, host, box):
        controller = original_controller(state, host, box)
        assert controller._reader is host._test_reader
        controllers.append(controller)
        return controller

    def build_telemetry(state, host, policy, controller):
        attempts.append(controller)
        assert box_seen[0]["alerts"] is controller
        runtime, _ = inert_runtime(monkeypatch, state, host, controller)
        runtime._alert_policy = policy
        runtimes.append(runtime)
        start = runtime._stream.start

        def composed_start(folder):
            assert box_seen[0]["api"]._alerts_controller is controller
            return start(folder)

        runtime._stream.start = composed_start
        # Initial failure; Api startup retries through main's actual closure.
        return None if lazy and len(attempts) == 1 else runtime

    monkeypatch.setattr(main_mod.sys, "platform", "win32")
    monkeypatch.setattr("wingman.preview.host.PreviewHost", capture_host)
    monkeypatch.setattr(main_mod, "build_preview_host", make_host)
    monkeypatch.setattr(main_mod, "build_alerts_controller", build_controller)
    monkeypatch.setattr(main_mod, "build_alert_policy", BUILD_POLICY)
    monkeypatch.setattr(main_mod, "build_telemetry", build_telemetry)
    monkeypatch.setattr(main_mod, "build_fleet_sharing_worker", lambda state: None)
    document = copy.deepcopy(settings.DEFAULTS)
    document["preview"] = settings.validated_preview(
        {"enabled": True, "alerts": {"enabled": True}}
    )
    document["gamelogs_dir"] = str(tmp_path)
    monkeypatch.setattr(settings, "load", lambda path=None: document)

    def during_run():
        api = startup.captured["api"]
        controller = controllers[0]
        assert api._alerts_controller is controller
        assert attempts == [controller] * (2 if lazy else 1)
        runtime = runtimes[-1]
        assert api._telemetry is runtime
        assert not hasattr(controller, "_tailer")
        assert not hasattr(runtime._alert_policy, "_tailer")
        rule_id, _draft = enable_custom(api)
        snapshot = controller.runtime_snapshot()
        tokens = (
            rule_id,
            snapshot.custom_rules[0].generation,
            snapshot.activation_epoch,
        )
        current = native_hosts[0]._custom_alert_current
        assert current(*tokens)
        assert runtime._alert_policy._runtime_snapshot() is snapshot
        assert runtime._alert_policy._custom_current(*tokens)
        assert runtime._custom_snapshot() is snapshot
        assert runtime._stream._custom_snapshot() is snapshot
        destroy = startup.captured["window"].destroy

        def fenced_destroy():
            assert not current(*tokens)
            assert not runtime._custom_admission_open
            destroy()

        startup.captured["window"].destroy = fenced_destroy
        api._request_shutdown()
        assert not api.test_custom_alert(
            rule_id, {"color": "#abcdef", "sound": "none", "cooldown_s": 8}
        )["applied"]
        assert api._reconcile_eve_runtime() is None
        assert len(attempts) == (2 if lazy else 1)

    startup.captured["during_run"] = during_run
    assert main_mod.main() == 0
    assert len(controllers) == 1
    assert native_hosts[0].started == 1
