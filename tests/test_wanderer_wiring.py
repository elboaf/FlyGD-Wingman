"""Exercise Api composition, committed master gates and both shutdown paths."""

import json
import threading
from typing import get_args

import pytest

from tests.test_api import make_api, pushes
from tests.test_preview_metadata import client
from tests.test_preview_metadata import runtime as runtime
from tests.test_startup import startup as startup
from wingman import __main__ as main_mod
from wingman import settings
from wingman.preview.host import PreviewHost
from wingman.ui import copy as copy_mod
from wingman.ui.api import Api
from wingman.wanderer.client import ErrorCode
from wingman.wanderer.worker import WorkerStatus


def test_api_composes_nonsecret_state_and_transaction_facades(tmp_path):
    api = make_api(tmp_path)
    assert hasattr(api, "wanderer_state")
    try:
        state = api.wanderer_state()
        assert state["enabled"] is False
        assert state["credential_present"] is False
        result = api.test_wanderer_connection(
            "https://EXAMPLE.test:443/prefix/", "map", ""
        )
        assert not result["applied"] and not result["test_accepted"]
        assert result["acknowledged"]["base_url"] == ""
        assert api.set_wanderer_enabled(True)["applied"]
        assert settings.load()["wanderer"]["enabled"]
        result = api.test_wanderer_connection(
            "http://unsafe.example", "map", "never-return-this"
        )
        assert not result["applied"]
        assert "never-return-this" not in json.dumps(result)
        api._publish_wanderer_state(api.wanderer_state())
        assert pushes(api._window)[-1][0] == "onWandererState"
    finally:
        api.shutdown_previews()


def test_metadata_availability_not_running_or_runtime_enabled(tmp_path, monkeypatch):
    host = PreviewHost(on_layout_changed=lambda *args: None)
    api = make_api(tmp_path, preview_host=host)
    assert hasattr(api, "_wanderer")
    try:
        with monkeypatch.context() as patch:
            patch.setattr(PreviewHost, "is_running", property(lambda self: True))
            assert host.is_running and host.runtime_enabled
            assert not host.metadata_available()
            assert api._wanderer.start()
            assert not api.wanderer_state()["host_available"]
            assert api._wanderer._worker.state().previewed == 0
    finally:
        api.shutdown_previews()


def test_controller_receives_only_created_named_primary_sessions(
    tmp_path, runtime, monkeypatch
):
    from wingman.preview import host as host_mod

    create = host_mod.PreviewWindow.create
    monkeypatch.setattr(
        host_mod.PreviewWindow,
        "create",
        lambda libs, c, *a, **kw: (
            None if c.character == "Failed" else create(libs, c, *a, **kw)
        ),
    )
    runtime.host._excluded = lambda: ["Excluded"]
    good = tuple(client(f"Pilot {i}", i + 100) for i in range(91))
    runtime.roster(
        1, *good, client("Failed", 4), client("Excluded", 5), client(None, 6)
    )
    api = make_api(tmp_path, preview_host=runtime.host)
    try:
        assert api._wanderer.start()
        assert api.wanderer_state()["previewed"] == 91
        assert api._wanderer._sessions == frozenset(c.session for c in good)
        assert all(
            s.character not in {"Failed", "Excluded"} for s in api._wanderer._sessions
        )
    finally:
        api.shutdown_previews()


def test_failed_preview_master_transaction_does_not_change_wanderer_gate(
    tmp_path, monkeypatch
):
    api = make_api(tmp_path)
    assert hasattr(api, "_wanderer")
    try:
        assert api.set_preview_enabled(True) is True
        assert api.wanderer_state()["previews_enabled"]

        def fail(*args):
            raise OSError("save refused")

        monkeypatch.setattr(settings, "_save_locked", fail)
        assert api.set_preview_enabled(False) is False
        assert api.wanderer_state()["previews_enabled"]
    finally:
        api.shutdown_previews()


@pytest.mark.parametrize("entrypoint", ["_close_eve_runtime", "shutdown_previews"])
def test_early_and_final_shutdown_detach_before_host_native_stop(
    tmp_path, monkeypatch, entrypoint
):
    host = PreviewHost(on_layout_changed=lambda *args: None)
    api = make_api(tmp_path, preview_host=host)
    assert hasattr(api, "_wanderer")
    assert api._wanderer.start()
    callback = host._metadata_callback
    seen = []

    def native_stop(*args, **kwargs):
        assert host._metadata_callback is None
        assert not host.metadata_available()
        assert api.wanderer_state()["status"] == "stopped"
        seen.append("native")
        return True

    monkeypatch.setattr(host, "stop", native_stop)
    try:
        getattr(api, entrypoint)()
        callback(999, frozenset(), True)
        assert not api._wanderer.start()
        assert not api.wanderer_state()["host_available"]
        api._publish_wanderer_state({"status": "connected"})
        assert not any(
            payload == {"status": "connected"} for _, payload in pushes(api._window)
        )
    finally:
        api.shutdown_previews()
    assert seen


def test_main_binds_before_preview_start_and_closes_before_window_destroy(
    startup, monkeypatch
):
    from wingman.wanderer.controller import WandererController

    started = []
    real_start = WandererController.start
    real_previews = Api.start_previews_if_enabled

    def start(controller):
        result = real_start(controller)
        started.append(controller)
        return result

    def previews(api):
        assert started == [api._wanderer]
        return real_previews(api)

    monkeypatch.setattr(WandererController, "start", start)
    monkeypatch.setattr(Api, "start_previews_if_enabled", previews)

    def during_run():
        api = startup.captured["api"]
        window = startup.captured["window"]
        original = window.destroy

        def destroy():
            assert api.wanderer_state()["status"] == "stopped"
            assert not api._wanderer.start()
            original()

        window.destroy = destroy
        startup.captured["on_quit"]()

    startup.captured["during_run"] = during_run
    main_mod.main()
    assert startup.captured["window"].destroyed == 1
    assert startup.captured["api"]._wanderer.stop(1)


def test_wanderer_joins_are_outside_api_state_locks(tmp_path, monkeypatch):
    api = make_api(tmp_path)
    assert hasattr(api, "_wanderer")
    original = api._wanderer.stop

    def stop(timeout=1):
        acquired = threading.Event()

        def probe():
            with api._eve_runtime_lock, api._preview_mode_lock:
                acquired.set()

        owner = threading.Thread(target=probe)
        owner.start()
        assert acquired.wait(2)
        owner.join(2)
        return original(timeout)

    monkeypatch.setattr(api._wanderer, "stop", stop)
    api.shutdown_previews()


@pytest.mark.parametrize(
    "status", [*get_args(WorkerStatus), "credential_error", "persistence_error"]
)
def test_status_copy_explains_every_safe_health_state(status):
    formatter = getattr(copy_mod, "wanderer_status", None)
    assert formatter is not None
    assert formatter(status, None)
    assert "unavailable" not in formatter("off", None).lower()
    if status == "persistence_error":
        assert "restart" in formatter(status, None).lower()
        assert "saved" in formatter(status, None).lower()


def test_invalid_configuration_copy_guides_input_correction():
    message = copy_mod.wanderer_status("error", "invalid_configuration")
    assert message == (
        "Check the Wanderer application URL, map and token, then test again."
    )
    assert message != copy_mod.wanderer_status("error", "transport_error")
    assert message != copy_mod.wanderer_status("error", "service_unavailable")


@pytest.mark.parametrize("code", get_args(ErrorCode))
def test_failure_copy_never_echoes_external_errors(code):
    formatter = getattr(copy_mod, "wanderer_status", None)
    assert formatter is not None
    assert formatter("error", code)
    assert "private-exception" not in formatter("error", "private-exception")
