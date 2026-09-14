"""Shared presentation with real main adapters, native pump and durable writer."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event, get_ident
from types import SimpleNamespace

import pytest

from tests.test_api import Api, make_api, make_state, pushes
from tests.test_preview_cropcontroller import client
from tests.test_preview_host import crop_pump as crop_pump
from tests.test_preview_layout_batch import batch_host as batch_host
from tests.test_preview_layout_batch import roster
from tests.test_preview_layout_batch import writer as writer
from tests.test_preview_runtime_review import eve_on
from tests.test_preview_runtime_review import runtime_pump as runtime_pump
from wingman import __main__ as main_mod
from wingman.preview.geometry import Rect
from wingman.preview.host import PreviewHost


def main_api(r, tmp_path, monkeypatch):
    state = make_state(tmp_path)
    state.settings = r.doc
    box = {}
    # Construct the real production closures against the same writer. Only
    # Windows discovery/native calls are substituted by the existing fixture.
    with monkeypatch.context() as patch:
        patch.setattr(main_mod.sys, "platform", "win32")
        wired = main_mod.build_preview_host(
            state,
            box,
            layout_store=r.layouts,
            layout_admission=r.host._layout_admission,
        )
    assert wired is not None
    for name in (
        "_on_layout_changed",
        "_on_clients_changed",
        "_on_layouts_changed",
        "_on_hotkey_status",
        "_on_bind_captured",
        "_on_crops_changed",
    ):
        setattr(r.host, name, getattr(wired, name))
    api = Api(state, preview_host=r.host, preview_runtime=r.runtime)
    box["api"] = api
    return api


def test_main_adapters_never_present_on_pump_and_coalesce_while_page_blocked(
    batch_host, tmp_path, monkeypatch
):
    r = batch_host
    api = main_api(r, tmp_path, monkeypatch)
    entered, release, delivered, crops_delivered = Event(), Event(), Event(), Event()
    calls = []
    eve_on(r)
    pump = r.call(get_ident)
    blocking = Event()

    def page(script):
        calls.append((get_ident(), script))
        if "onPreviewHotkeys" in script and blocking.is_set():
            entered.set()
            assert release.wait(10)
            payload = pushes(SimpleNamespace(evaluated=[script]))[0][1]
            if "Newest" in payload["roster"]:
                delivered.set()
        if "onPreviewCrops" in script:
            payload = pushes(SimpleNamespace(evaluated=[script]))[0][1]
            if payload["revision"] == 50:
                crops_delivered.set()

    api._window = SimpleNamespace(evaluate_js=page)
    try:
        # Production ingress itself must be data-only even before startup.
        r.call(lambda: r.host._on_clients_changed(["Intermediate"]))
        assert not calls, "main adapter performed synchronous page work on the pump"
        blocking.set()
        assert api._start_presentation()
        assert entered.wait(5)
        roster(r, 1, client())
        saved = api.create_preview_layout("Actual")
        assert saved["persisted"]
        selected = saved["state"]["layouts"][0]
        assert api.apply_preview_layout(selected["id"], selected["revision"])[
            "persisted"
        ]
        assert api.set_preview_excluded("Alice", True)["persisted"]
        assert api.set_preview_excluded("Alice", False)["persisted"]
        for revision in range(1, 51):
            r.call(lambda n=revision: r.host._on_crops_changed({"revision": n}))
            r.call(lambda: r.host._on_hotkey_status({"stale": True}))
        # Older arrivals cannot replace the newest detached crop state.
        r.call(lambda: r.host._on_crops_changed({"revision": 1}))
        r.call(lambda: r.host._on_clients_changed(["Newest"]))
        r.call(lambda: r.host._layout_changed("Newest", Rect(1, 2, 320, 210), False))
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(r.layouts.flush).result(5)
        assert {"Intermediate", "Newest"} <= set(r.reader.get("seen"))
        assert r.reader.get("layouts")["Newest"]["x"] == 1
        assert r.call(lambda: 42) == 42
        assert api._preview_crops_pending == {"revision": 50}
        assert api._preview_primary_dirty is True
        release.set()
        assert delivered.wait(5), "notification during delivery lost its wakeup"
        assert crops_delivered.wait(5), "newest crop state was not delivered"
    finally:
        release.set()
        api._close_eve_runtime()
        assert api._stop_fleet_presentation(5)
    assert all(thread != pump for thread, _ in calls)
    events = pushes(SimpleNamespace(evaluated=[script for _, script in calls]))
    assert ("onPreviewCrops", {"revision": 50}) in events
    assert all("stale" not in payload.get("registration", {}) for _, payload in events)


def test_preview_dispatch_survives_domain_failure_and_preserves_fleet_deadline(
    tmp_path, monkeypatch
):
    api = make_api(tmp_path)
    api.push_preview_hotkeys()
    api.push_preview_crops({"revision": 9})
    monkeypatch.setattr(api, "get_preview_hotkey_state", lambda: 1 / 0)
    monkeypatch.setattr(api, "_present_fleet_snapshot", lambda: 123.0)
    api._fleet_worker.iterate_once()
    assert ("onPreviewCrops", {"revision": 9}) in pushes(api._window)
    assert api._fleet_worker._deadline == 123.0


def test_crop_serialization_failure_cannot_discard_detached_capture(
    tmp_path, monkeypatch
):
    from wingman.ui import api as api_mod

    api = make_api(tmp_path)
    serialize = api_mod._page_payload

    def fail_crop(payload):
        if payload == {"revision": 9}:
            raise RuntimeError("crop serialization failed")
        return serialize(payload)

    monkeypatch.setattr(api_mod, "_page_payload", fail_crop)
    api.push_preview_crops({"revision": 9})
    api.push_bind_captured("Ctrl+F1", 1)
    api._fleet_worker.iterate_once()
    assert ("onPreviewBindCaptured", {"gesture": "Ctrl+F1", "session": 1}) in pushes(
        api._window
    )


def test_final_close_fences_both_pages_and_retains_entered_worker(tmp_path):
    api = make_api(tmp_path)
    entered, release = Event(), Event()
    calls = []

    def page(script):
        calls.append(script)
        entered.set()
        assert release.wait(5)

    api._window = SimpleNamespace(evaluate_js=page)
    sigbar = []
    api._sigbar_window = SimpleNamespace(evaluate_js=sigbar.append)
    owner = api._fleet_worker
    try:
        assert api._start_presentation()
        api.push_preview_hotkeys()
        assert entered.wait(5)
        api.push_preview_crops({"revision": 19})
        api._close_eve_runtime()
        assert not api._stop_fleet_presentation(0)
        assert api._fleet_worker is owner
        assert not api._start_presentation()
        api.push_preview_hotkeys()
        api.push_preview_crops({"revision": 20})
    finally:
        release.set()
        assert api._stop_fleet_presentation(5)
    assert len(calls) == 1
    assert not sigbar


def test_identified_capture_through_main_while_old_delivery_is_blocked(
    batch_host, tmp_path, monkeypatch
):
    r = batch_host
    api = main_api(r, tmp_path, monkeypatch)
    eve_on(r)
    entered, release, newest = Event(), Event(), Event()
    seen = []

    def page(script):
        handler, payload = pushes(SimpleNamespace(evaluated=[script]))[0]
        if handler != "onPreviewBindCaptured":
            return
        seen.append(payload)
        if payload["session"] == 1:
            entered.set()
            assert release.wait(5)
        else:
            newest.set()

    api._window = SimpleNamespace(evaluate_js=page)
    try:
        assert api.set_bind_capture(True, 1)
        assert r.call(lambda: r.host._take_capture("Ctrl+F1"))
        assert api._start_presentation()
        assert entered.wait(5)
        assert api.set_bind_capture(False, 1)
        assert api.set_bind_capture(True, 2)
        assert not api.set_bind_capture(True, 1)
        assert not api.set_bind_capture(False, 1)
        assert r.call(lambda: r.host._take_capture("Ctrl+F2"))
        assert not r.call(lambda: r.host._take_capture("Ctrl+F3"))
        assert api._preview_capture_pending == ("Ctrl+F2", 2)
        api.push_bind_captured("Ctrl+F1", 1)
        assert api._preview_capture_pending == ("Ctrl+F2", 2)
        release.set()
        assert newest.wait(5)
    finally:
        release.set()
        api._close_eve_runtime()
        assert api._stop_fleet_presentation(5)
    assert seen == [
        {"gesture": "Ctrl+F1", "session": 1},
        {"gesture": "Ctrl+F2", "session": 2},
    ]


@pytest.mark.parametrize(
    "session", [True, False, 0, -1, 1.5, "1", {}, 9007199254740992]
)
def test_capture_rejects_invalid_identifiers_without_replacing_active(session):
    host = PreviewHost(on_layout_changed=lambda *a: None)
    host._eve_admitted = True
    assert host.set_capture(True, 1)
    assert not host.set_capture(False, session)
    assert host._take_capture("Ctrl+F1")


@pytest.mark.parametrize("sequence", [(True, 1, False, 1), (False, 2, True, 1)])
def test_identified_capture_rejects_reversed_arm_and_disarm(sequence):
    captured = []
    host = PreviewHost(
        on_layout_changed=lambda *a: None,
        on_bind_captured=lambda *a: captured.append(a),
    )
    host._eve_admitted = True
    first, a, second, b = sequence
    host.set_capture(first, a)
    host.set_capture(second, b)
    assert not host.set_capture(True, 1)
    assert host.set_capture(True, 3)
    assert not host.set_capture(False, 1)
    assert not host.set_capture(True, 2)
    assert not host.set_capture(False), (
        "legacy requests must not disarm identified capture"
    )
    assert host._take_capture("Ctrl+F8")
    assert captured == [("Ctrl+F8", 3)]
    assert not host._take_capture("Ctrl+F9"), "consume disarms before page delivery"
    assert not host.set_capture(True, 3), (
        "same-session retry cannot resurrect consumed capture"
    )
