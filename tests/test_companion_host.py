"""Real host/runtime/controller/family integration, only OS calls are doubled."""

import threading
from contextlib import contextmanager

import pytest

from tests.test_companion_controller import until
from tests.test_companion_family import BINDING, Catalog, Window
from tests.test_preview_host import crop_pump as crop_pump
from wingman import settings
from wingman.preview import host as host_mod
from wingman.preview.companioncontroller import CompanionController, CompanionPorts
from wingman.preview.companionfamily import CompanionFamily
from wingman.preview.companions import CompanionCommand
from wingman.preview.layout import Rect
from wingman.preview.runtime import PreviewRuntime


@pytest.fixture
def integrated(crop_pump, monkeypatch, tmp_path):
    r = crop_pump(initial={})
    path = tmp_path / "companion-settings.json"
    document = settings.load(path)
    writes, windows, picks = [], [], []
    catalog = Catalog()
    runtime = PreviewRuntime(r.host)

    @contextmanager
    def update():
        writes.append(threading.get_ident())
        with settings.update(document, path) as current:
            yield current

    controller = CompanionController(
        CompanionPorts(update, runtime, r.host.submit_companion, lambda state: None),
        document["companion_previews"],
        available=True,
    )
    runtime.set_state_callback(controller.runtime_changed)
    r.host.set_companion_controller(controller)

    def create_window(libs, binding, rect, source, **callbacks):
        assert threading.get_ident() == r.host._thread.ident
        window = Window(binding, rect, source, callbacks)
        windows.append(window)
        return window

    def create_picker(*args, **callbacks):
        from types import SimpleNamespace

        picks.append(callbacks)
        return SimpleNamespace(
            cancel=lambda reason: callbacks["on_cancel"](reason),
            process_dialog_message=lambda message: False,
        )

    def family(libs, owner, **kwargs):
        return CompanionFamily(
            libs,
            owner,
            **kwargs,
            catalog=catalog,
            create_window=create_window,
            create_picker=create_picker,
        )

    monkeypatch.setattr(host_mod, "CompanionFamily", family)
    r.runtime, r.controller = runtime, controller
    r.document, r.windows, r.picks, r.catalog, r.writes = (
        document,
        windows,
        picks,
        catalog,
        writes,
    )

    def receipt(pending):
        def result():
            return next(
                (
                    item
                    for item in controller.state()["operations"]
                    if item["operation_id"] == pending["operation_id"]
                    and not item["pending"]
                ),
                None,
            )

        until(result)
        return result()

    r.receipt = receipt
    yield r
    controller.close_admission()
    controller.close_publication()
    assert controller.shutdown()
    assert runtime.shutdown()


def add(r, mode="whole"):
    assert r.receipt(r.controller.set_master(True))["persisted"]
    listing = r.receipt(r.controller.sources())
    pending = r.controller.select(
        None,
        listing["sources"][0]["candidate_token"],
        mode,
        "Map",
        "exact",
        "Mapper",
        None,
    )
    if mode == "region":
        until(lambda: r.picks)
        r.call(
            lambda: r.picks[-1]["on_confirm"](
                BINDING, Rect(100, 100, 400, 300), BINDING.client_size
            )
        )
    assert r.receipt(pending)["persisted"]
    until(lambda: not r.runtime.snapshot().selection_pending)
    until(lambda: pending["id"] in r.host._companion_family.live)
    return pending["id"]


@pytest.mark.parametrize("mode", ["whole", "region"])
def test_real_host_creates_promotes_and_stops_companion_without_eve(integrated, mode):
    r = integrated
    identity = add(r, mode)
    assert r.host._crop_controller is None and not r.host.runtime_enabled
    assert not r.host._registered_text and not r.host._hook
    assert not r.windows[-1].hidden
    assert r.writes and r.host._thread.ident not in r.writes
    generation = r.controller.state()["rows"][0]["generation"]
    assert r.receipt(r.controller.remove(identity, generation))["persisted"]
    until(lambda: r.runtime.snapshot().pump == "stopped")
    assert all(window.closed for window in r.windows)


def test_master_off_keeps_admitted_region_lease_and_saved_definition_not_visible(
    integrated,
):
    r = integrated
    r.receipt(r.controller.set_master(True))
    listing = r.receipt(r.controller.sources())
    pending = r.controller.select(
        None,
        listing["sources"][0]["candidate_token"],
        "region",
        "Map",
        "exact",
        "Mapper",
        None,
    )
    until(lambda: r.picks)
    r.receipt(r.controller.set_master(False))
    assert r.runtime.snapshot().selection_pending and r.host.is_running
    r.call(
        lambda: r.picks[-1]["on_confirm"](
            BINDING, Rect(100, 100, 400, 300), BINDING.client_size
        )
    )
    assert r.receipt(pending)["persisted"]
    until(lambda: r.runtime.snapshot().pump == "stopped")
    assert all(window.hidden and window.closed for window in r.windows)
    assert len(r.document["companion_previews"]["definitions"]) == 1


def test_family_off_does_not_stop_other_family_and_cleanup_failure_retains_pump(
    integrated,
):
    r = integrated
    identity = add(r)
    window = r.host._companion_family.live[identity].window
    r.runtime.set_eve(True, 1)
    until(lambda: r.runtime.snapshot().eve == "active")
    owner = r.host._thread
    r.runtime.set_eve(False, 2)
    until(lambda: r.runtime.snapshot().eve == "stopped")
    assert r.host._thread is owner and not window.closed
    window.close_ok = False
    r.receipt(r.controller.set_master(False))
    r.call(lambda: None)
    assert r.host.is_running and r.host._companion_family is not None
    window.close_ok = True
    r.host._post(0)
    until(lambda: r.runtime.snapshot().pump == "stopped")


def test_construction_binding_and_bounded_reserved_fifo(integrated):
    r = integrated
    add(r)
    with pytest.raises(RuntimeError):
        r.host.set_companion_controller(r.controller)
    entered, release = threading.Event(), threading.Event()
    # Park only a test callback, never a production native operation.
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(r.call, lambda: (entered.set(), release.wait(5)))
        assert entered.wait(3)
        try:
            command = CompanionCommand("reconcile", None, ((), r.host._companion_epoch))
            accepted = [r.host.submit_companion(command) for _ in range(100)]
            assert 0 < sum(accepted) < 100
            assert r.host.submit_companion(CompanionCommand("discard", None, None))
        finally:
            release.set()
            future.result(5)


@pytest.mark.parametrize("first", ["companion", "eve"])
def test_one_temporary_picker_shared_with_real_eve_coordinator(integrated, first):
    from tests.test_preview_cropcontroller import client
    from wingman.telemetry.model import RosterSnapshot

    r = integrated
    r.runtime.set_eve(True, 1)
    until(lambda: r.runtime.snapshot().eve == "active")
    r.host.apply_roster(RosterSnapshot(2, (client(),)))
    r.call(lambda: None)
    listing = r.receipt(r.controller.sources())
    token = listing["sources"][0]["candidate_token"]
    if first == "eve":
        crop = r.host.request_crop("select", "Alice")
        r.call(lambda: None)
        assert r.host._crop_controller.picker is not None
        pending = r.controller.select(
            None, token, "region", "Map", "exact", "Mapper", None
        )
        result = r.receipt(pending)
        assert not result["applied"] and "selection" in result["error"].lower()
        assert not r.picks
        r.call(lambda: r.host._crop_controller.picker.cancel())
    else:
        pending = r.controller.select(
            None, token, "region", "Map", "exact", "Mapper", None
        )
        until(lambda: r.picks)
        crop = r.host.request_crop("select", "Alice")
        r.call(lambda: None)
        assert r.host._crop_controller.picker is None
        r.call(lambda: r.picks[-1]["on_cancel"]("cancelled"))
        assert not r.receipt(pending)["applied"]
    r.store.drain().result(5)
    r.call(lambda: None)
    assert not r.host.crop_state()["operations"][crop["operation_id"]]["persisted"]


def test_safety_timer_failure_closes_native_owner_without_retry_storm(
    integrated, monkeypatch
):
    r = integrated
    attempts = []
    set_timer = r.native.SetTimer

    def fail_timer(hwnd, ident, interval, callback):
        if ident == host_mod.COMPANION_SCAN_TIMER_ID:
            attempts.append(ident)
            return 0
        return set_timer(hwnd, ident, interval, callback)

    monkeypatch.setattr(r.native, "SetTimer", fail_timer)
    r.runtime.set_eve(True, 1)
    until(lambda: r.runtime.snapshot().eve == "active")
    listing = r.receipt(r.controller.sources())
    pending = r.controller.select(
        None,
        listing["sources"][0]["candidate_token"],
        "whole",
        "Map",
        "exact",
        "Mapper",
        None,
    )
    r.receipt(pending)
    for _ in range(5):
        r.call(lambda: None)
    assert len(attempts) == 1
    assert all(window.closed for window in r.windows)
    assert r.runtime.snapshot().eve == "active"


def test_promotion_requires_current_controller_generation_and_lease(integrated):
    from wingman.preview.companions import CompanionToken
    from wingman.preview.runtime import SelectionLease

    r = integrated
    identity = add(r)
    state = r.runtime.snapshot()
    token = CompanionToken(
        999,
        identity,
        state.pump_epoch,
        state.companion_epoch,
        1,
        SelectionLease(999, state.pump_epoch),
    )
    assert not r.host._companion_authorized(token, promotion=True)
