"""Companion bridge composition, exact forwarding and final-storage boundary."""

from types import SimpleNamespace

import pytest

from tests.test_api import make_api, make_state, pushes
from wingman import __main__ as main
from wingman.preview.runtime import PreviewRuntime


@pytest.mark.parametrize(
    "facade,method,args",
    [
        ("companion_previews_state", "state", ()),
        ("companion_previews_sources", "sources", ()),
        ("set_companion_previews_enabled", "set_master", (False,)),
        (
            "companion_preview_select",
            "select",
            (None, "opaque", "region", "Map", "contains", "Map", None),
        ),
        ("companion_preview_reselect_region", "reselect_region", ("id", 3)),
        ("companion_preview_set_enabled", "set_enabled", ("id", False, 3)),
        ("companion_preview_edit", "edit", ("id", "Map", "exact", "Map", 3)),
        ("companion_preview_remove", "remove", ("id", 3)),
        ("companion_preview_reset_geometry", "reset_geometry", ("id", 3)),
    ],
)
def test_facades_forward_arguments_and_receipt_unchanged(
    tmp_path, facade, method, args
):
    receipt = {"pending": True, "applied": False, "persisted": False, "revision": 9}
    received = []
    controller = SimpleNamespace(
        **{method: lambda *actual: (received.append(actual), receipt)[1]}
    )
    api = make_api(tmp_path, companion_controller=controller)
    assert getattr(api, facade)(*args) is receipt
    assert received == [args]


def test_literal_companion_push_is_fenced_when_view_closes(tmp_path):
    api = make_api(tmp_path)
    api._push_companion_previews({"revision": 7})
    assert pushes(api._window) == [("onCompanionPreviews", {"revision": 7})]
    api._close_eve_runtime()
    api._push_companion_previews({"revision": 8})
    assert len(pushes(api._window)) == 1
    assert api._companions.shutdown()


def test_composition_binds_before_demand_and_does_not_touch_eve(tmp_path):
    state = make_state(tmp_path)
    calls = []
    host = SimpleNamespace(
        submit_companion=lambda command: True,
        set_companion_controller=lambda controller: calls.append(controller),
    )
    runtime = PreviewRuntime(None)
    controller = main.build_companion_controller(state, host, runtime, {})
    assert calls == [controller]
    assert controller.state()["available"]
    assert runtime.snapshot().eve == "stopped"
    assert controller.shutdown()


def test_storage_timeout_keeps_runtime_owner_until_a_later_shutdown(
    tmp_path, monkeypatch
):
    api = make_api(tmp_path)
    original = api._companions
    calls = []
    api._companions = SimpleNamespace(
        close_publication=lambda: calls.append("publication"),
        close_admission=lambda: calls.append("admission"),
        shutdown=lambda: False,
    )
    monkeypatch.setattr(
        api._preview_runtime, "shutdown", lambda: calls.append("runtime") or True
    )
    api.shutdown_previews()
    assert "runtime" not in calls
    api._companions.shutdown = lambda: True
    api.shutdown_previews()
    assert calls[-1] == "runtime"
    assert original.shutdown()
