"""Semantic crop bridge over the real retained host/store; no native launches."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import get_ident

import pytest

from tests.test_api import make_api, pushes
from tests.test_preview_cropcontroller import DEFINITION, Transaction, client
from tests.test_preview_host import crop_pump as crop_pump
from wingman.preview import win32
from wingman.preview.cropstore import CropStore
from wingman.preview.geometry import Rect
from wingman.preview.host import PreviewHost
from wingman.telemetry.model import RosterSnapshot


@pytest.fixture
def crop_api(tmp_path):
    transaction = Transaction({"Alice": DEFINITION})
    store = CropStore(
        transaction.update,
        {"Alice": DEFINITION},
        executor_factory=lambda: ThreadPoolExecutor(max_workers=1),
    )
    api = make_api(tmp_path)
    host = PreviewHost(
        on_layout_changed=lambda *args: None,
        crop_store=store,
        on_crops_changed=api.push_preview_crops,
    )
    api._preview_host = host
    try:
        yield api, host, store, transaction
    finally:
        transaction.release.set()
        host.stop(final=True)
        store.close().result(5)


def refused(result):
    assert not result["applied"] and not result["persisted"]
    assert not result["pending"] and result["error"]


@pytest.mark.parametrize(
    "name", [None, 7, True, [], {}, "", " ", "hwnd:0x123", " Alice", "Alice\n"]
)
@pytest.mark.parametrize("action", ["select", "enabled", "remove"])
def test_crop_requests_reject_malformed_or_anonymous_owners(crop_api, name, action):
    api, _host, store, _transaction = crop_api
    method = {
        "select": api.select_preview_crop,
        "enabled": api.set_preview_crop_enabled,
        "remove": api.remove_preview_crop,
    }[action]
    refused(method(name, True) if action == "enabled" else method(name))
    assert not store.snapshot()["operations"]


@pytest.mark.parametrize("value", [0, 1, None, "false", "true", [], {}])
def test_crop_enable_requires_a_boolean(crop_api, value):
    api, _host, store, _transaction = crop_api
    refused(api.set_preview_crop_enabled("Alice", value))
    assert not store.snapshot()["operations"]


def test_crop_requests_without_host_are_final_refusals(tmp_path):
    api = make_api(tmp_path)
    refused(api.select_preview_crop("Alice"))
    refused(api.set_preview_crop_enabled("Alice", False))
    refused(api.remove_preview_crop("Alice"))
    state = api.get_preview_crop_state()
    assert state == dict(
        revision=0,
        definitions={},
        operations={},
        statuses={},
        live_count=0,
        cap=8,
        runtime_enabled=False,
        busy=False,
    )
    assert api.get_preview_hotkey_state()["crops"] == state


def test_crop_validation_uses_committed_definitions_not_tentative_settings(crop_api):
    api, _host, store, transaction = crop_api
    api._state.settings["preview"] = {"crops": {"Tentative": {"enabled": True}}}
    refused(api.set_preview_crop_enabled("Tentative", False))
    refused(api.remove_preview_crop("Tentative"))
    refused(api.select_preview_crop("Alice"))  # master off, never starts host
    transaction.release.clear()
    receipt = api.set_preview_crop_enabled("Alice", False)
    assert transaction.entered.wait(5)
    assert receipt == dict(
        applied=False, persisted=False, pending=True, operation_id=1, error=None
    )
    state = api.get_preview_crop_state()
    assert state["definitions"]["Alice"]["enabled"] is True
    assert state["operations"][1]["pending"]
    assert api.get_preview_hotkey_state()["crops"] == state
    transaction.release.set()
    store.drain().result(5)
    assert api.get_preview_crop_state()["definitions"]["Alice"]["enabled"] is False


@pytest.mark.parametrize("fail", [False, True])
def test_crop_offline_completion_and_missed_push_recovery(crop_api, fail):
    api, host, store, transaction = crop_api
    api._window = None  # readiness push is deliberately missed
    transaction.fail = fail
    transaction.release.clear()
    receipt = api.remove_preview_crop("Alice")
    assert transaction.entered.wait(5)
    assert receipt["pending"] and not receipt["persisted"]
    before = api.get_preview_crop_state()
    transaction.release.set()
    store.drain().result(5)
    after = api.get_preview_crop_state()
    assert after["revision"] > before["revision"]
    outcome = after["operations"][receipt["operation_id"]]
    assert not outcome["pending"] and outcome["persisted"] is not fail
    assert ("Alice" in after["definitions"]) is fail
    assert not host.is_running
    # No roster membership is needed to recover removal outcomes.
    assert api.get_preview_hotkey_state()["crops"] == after


def test_crop_completion_before_receipt_is_recoverable(crop_api, monkeypatch):
    api, host, store, _transaction = crop_api
    original = host._drain_offline_crop_commands

    def complete_before_return():
        result = original()
        store.drain().result(5)
        return result

    monkeypatch.setattr(host, "_drain_offline_crop_commands", complete_before_return)
    receipt = api.remove_preview_crop("Alice")
    assert receipt["persisted"] and not receipt["pending"]
    delivered = [
        state for name, state in pushes(api._window) if name == "onPreviewCrops"
    ]
    assert any(
        state["operations"][str(receipt["operation_id"])]["persisted"]
        for state in delivered
    )
    state = api.get_preview_crop_state()
    assert state["operations"][receipt["operation_id"]]["persisted"]
    assert state["definitions"] == {}


def test_crop_noop_never_overtakes_pending_same_owner_disable(crop_api):
    api, _host, store, transaction = crop_api
    assert api.set_preview_crop_enabled("Alice", True) == dict(
        applied=True, persisted=True, pending=False, operation_id=None, error=None
    )
    assert not transaction.writes
    transaction.release.clear()
    first = api.set_preview_crop_enabled("Alice", False)
    assert transaction.entered.wait(5)
    second = api.set_preview_crop_enabled("Alice", True)
    assert second["pending"] and second["operation_id"] != first["operation_id"]
    transaction.release.set()
    store.drain().result(5)
    state = api.get_preview_crop_state()
    assert state["definitions"]["Alice"]["enabled"] is True
    assert all(
        state["operations"][r["operation_id"]]["persisted"] for r in [first, second]
    )


def test_pending_receipt_can_arrive_after_terminal_push(crop_api, monkeypatch):
    api, _host, store, transaction = crop_api
    transaction.release.clear()
    caller = get_ident()
    evaluate = api._window.evaluate_js
    delivered = []

    def page(script):
        evaluate(script)
        if get_ident() == caller and not delivered:
            delivered.append(True)
            assert transaction.entered.wait(5)
            transaction.release.set()
            store.drain().result(5)

    monkeypatch.setattr(api._window, "evaluate_js", page)
    receipt = api.set_preview_crop_enabled("Alice", False)
    assert receipt["pending"] and not receipt["persisted"]
    states = [
        payload for name, payload in pushes(api._window) if name == "onPreviewCrops"
    ]
    assert any(
        state["operations"][str(receipt["operation_id"])]["persisted"]
        for state in states
    )
    recovered = api.get_preview_crop_state()
    assert recovered["operations"][receipt["operation_id"]]["persisted"]
    assert recovered["definitions"]["Alice"]["enabled"] is False


def test_noop_enable_after_pending_remove_is_not_fabricated_success(crop_api):
    api, _host, store, transaction = crop_api
    transaction.release.clear()
    removing = api.remove_preview_crop("Alice")
    assert transaction.entered.wait(5)
    enabling = api.set_preview_crop_enabled("Alice", True)
    assert enabling["pending"] and enabling["operation_id"] != removing["operation_id"]
    transaction.release.set()
    store.drain().result(5)
    state = api.get_preview_crop_state()
    assert state["definitions"] == {}
    outcome = state["operations"][enabling["operation_id"]]
    assert not outcome["persisted"] and not outcome["pending"] and outcome["error"]


def test_select_uses_named_session_without_primary_preview_or_page_native_identity(
    tmp_path, crop_pump
):
    r = crop_pump(initial={})
    h = r.host
    api = make_api(tmp_path, preview_host=h)
    h._on_crops_changed = api.push_preview_crops
    h.start()
    assert h.characters() == []  # primary exclusion must not gate crop selection
    refused(api.select_preview_crop("Offline"))
    receipt = api.select_preview_crop("Alice")
    assert receipt["pending"] and not receipt["persisted"]
    r.call(lambda: None)
    assert api.get_preview_crop_state()["statuses"]["Alice"] == "selecting"

    def confirm():
        picker = h._crop_controller.picker
        picker.selection = Rect(
            picker.destination.x + 20, picker.destination.y + 20, 100, 80
        )
        picker._confirm()

    r.call(confirm)
    r.store.drain().result(5)
    r.call(lambda: None)
    state = api.get_preview_crop_state()
    assert state["operations"][receipt["operation_id"]]["persisted"]
    assert state["statuses"]["Alice"] == "live"
    assert api.get_preview_hotkey_state()["crops"] == state
    assert state["revision"] == h.crop_state()["revision"]
    assert not any(
        word in str(state).lower() for word in ["hwnd", "pid", "session", "generation"]
    )
    again = api.select_preview_crop("Alice")
    assert again["operation_id"] != receipt["operation_id"]
    r.call(lambda: h._crop_controller.picker.cancel("user"))
    outcome = api.get_preview_crop_state()["operations"][again["operation_id"]]
    assert not outcome["pending"] and not outcome["persisted"] and outcome["error"]


def test_api_enable_native_failure_is_safe_terminal_outcome(tmp_path, crop_pump):
    r = crop_pump(initial={"Alice": replace(DEFINITION, enabled=False)})
    r.host.start()
    api = make_api(tmp_path, preview_host=r.host)
    r.native.fail = "register"
    receipt = api.set_preview_crop_enabled("Alice", True)
    r.call(lambda: None)
    outcome = api.get_preview_crop_state()["operations"][receipt["operation_id"]]
    assert not outcome["pending"] and not outcome["persisted"]
    assert "display" in outcome["error"].lower()
    assert "hwnd" not in outcome["error"].lower()
    assert not r.transaction.writes
    assert not api.get_preview_crop_state()["definitions"]["Alice"]["enabled"]


@pytest.mark.parametrize("late", [False, True])
@pytest.mark.parametrize("saved_enabled", [False, True])
def test_api_offline_enable_refuses_full_cap_even_if_arrivals_beat_delivery(
    tmp_path, crop_pump, monkeypatch, late, saved_enabled
):
    names = [f"Pilot {i}" for i in range(8)]
    r = crop_pump(
        initial={
            **dict.fromkeys(names, DEFINITION),
            "Offline": replace(DEFINITION, enabled=saved_enabled),
        }
    )
    clients = tuple(client(name, hwnd=20 + i) for i, name in enumerate(names))
    for entry in clients:
        r.native.sources[entry.hwnd] = (1280, 720)
    r.host.apply_roster(RosterSnapshot(2, clients[:-1] if late else clients))
    r.host.start()
    r.call(lambda: None)
    api = make_api(tmp_path, preview_host=r.host)
    original = r.host._post
    monkeypatch.setattr(
        r.host,
        "_post",
        lambda msg, *args: (
            None if msg == win32.WM_APP_CROP_COMMAND else original(msg, *args)
        ),
    )
    receipt = api.set_preview_crop_enabled("Offline", True)
    if late:
        assert receipt["pending"]
        r.host.apply_roster(RosterSnapshot(3, clients))
        r.call(lambda: r.host._apply_crop_commands(r.native.lib))
        outcome = api.get_preview_crop_state()["operations"][receipt["operation_id"]]
        refused(outcome)
        assert "limit" in outcome["error"].lower()
    else:
        refused(receipt)
        assert receipt["operation_id"] is None
    assert not r.transaction.writes
    assert (
        api.get_preview_crop_state()["definitions"]["Offline"]["enabled"]
        is saved_enabled
    )


def test_crop_state_getter_returns_independent_private_safe_snapshots(crop_api):
    api, host, store, _transaction = crop_api
    state = api.get_preview_crop_state()
    revision = state["revision"]
    state["definitions"].clear()
    assert api.get_preview_crop_state()["definitions"]["Alice"]
    assert api.get_preview_crop_state()["revision"] == revision
    assert state["revision"] == host.crop_state()["revision"]
    assert "generations" not in state
    # Exercise an outcome too; runtime identity is never a bridge field.
    api.remove_preview_crop("Alice")
    store.drain().result(5)

    def keys(value):
        if isinstance(value, dict):
            for key, child in value.items():
                yield key
                yield from keys(child)
        elif isinstance(value, list):
            for child in value:
                yield from keys(child)

    assert not {"session", "hwnd", "pid", "epoch", "token", "generations"}.intersection(
        keys(api.get_preview_crop_state())
    )
