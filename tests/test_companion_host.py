"""Real host/runtime/controller/family integration, only OS calls are doubled."""

import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace

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
    writes, windows, picks, published = [], [], [], []
    changed = threading.Condition()
    catalog = Catalog()
    runtime = PreviewRuntime(r.host)

    @contextmanager
    def update():
        writes.append(threading.get_ident())
        with settings.update(document, path) as current:
            yield current

    def notify():
        with changed:
            changed.notify_all()

    def publish(state):
        published.append(state)
        notify()

    controller = CompanionController(
        CompanionPorts(update, runtime, r.host.submit_companion, publish),
        document["companion_previews"],
        available=True,
    )

    def runtime_changed(state):
        # Forward before taking the observer lock — waiters read real owners.
        controller.runtime_changed(state)
        notify()

    runtime.set_state_callback(runtime_changed)
    r.host.set_companion_controller(controller)
    controller.state()  # Subscribe through the normal publication contract.

    def create_window(libs, binding, rect, source, **callbacks):
        assert threading.get_ident() == r.host._thread.ident
        window = Window(binding, rect, source, callbacks)
        windows.append(window)
        return window

    def create_picker(*args, **callbacks):
        from types import SimpleNamespace

        picks.append(callbacks)
        notify()
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

    def wait(predicate):
        with changed:
            result = changed.wait_for(predicate, 3)
        assert result, (
            f"runtime={runtime.snapshot()}; "
            f"operations={controller.state()['operations']}"
        )
        return result

    def terminal(pending):
        if not pending["pending"]:
            return pending
        return next(
            (
                item
                for item in controller.state()["operations"]
                if item["operation_id"] == pending["operation_id"]
                and not item["pending"]
            ),
            None,
        )

    def receipt(pending):
        return wait(lambda: terminal(pending))

    def wait_selection_ready():
        def ready():
            state = runtime.snapshot()
            assert state.error is None and "failed" not in (
                state.pump,
                state.eve,
                state.companions,
            ), state
            # Test-owned demand stays stable; this is not atomic admission.
            # Active/no-demand may have released enumeration but not stopped yet.
            return not state.selection_pending and (
                state.pump == "stopped"
                or (
                    state.pump == "active"
                    and (state.eve == "active" or state.companions == "active")
                )
            )

        wait(ready)

    def wait_picker(pending, before):
        wait(lambda: len(picks) > before or terminal(pending))
        result = terminal(pending)
        assert len(picks) > before and (result is None or result["applied"]), (
            f"picker not admitted: receipt={result}; runtime={runtime.snapshot()}"
        )
        return picks[before]

    r.changed, r.published = changed, published
    r.wait, r.receipt = wait, receipt
    r.wait_selection_ready, r.wait_picker = wait_selection_ready, wait_picker
    try:
        yield r
    finally:
        controller.close_admission()
        controller.close_publication()
        try:
            controller_stopped = controller.shutdown()
        finally:
            runtime_stopped = runtime.shutdown()
        # Attempt both owners before asserting either result. The pump/store
        # fixture also retains its own final cleanup even if these checks fail.
        assert controller_stopped and runtime_stopped
        for worker in (controller._worker, runtime._worker):
            if worker is not None:
                worker.join(3)
                assert not worker.is_alive()
        assert r.host._thread is None


def add(r, mode="whole"):
    assert r.receipt(r.controller.set_master(True))["persisted"]
    listing = r.receipt(r.controller.sources())
    assert listing["applied"], listing
    r.wait_selection_ready()
    before = len(r.picks)
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
        picker = r.wait_picker(pending, before)
        r.call(
            lambda: picker["on_confirm"](
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
    assert listing["applied"], listing
    r.wait_selection_ready()
    before = len(r.picks)
    pending = r.controller.select(
        None,
        listing["sources"][0]["candidate_token"],
        "region",
        "Map",
        "exact",
        "Mapper",
        None,
    )
    picker = r.wait_picker(pending, before)
    r.receipt(r.controller.set_master(False))
    assert r.runtime.snapshot().selection_pending and r.host.is_running
    r.call(
        lambda: picker["on_confirm"](
            BINDING, Rect(100, 100, 400, 300), BINDING.client_size
        )
    )
    assert r.receipt(pending)["persisted"]
    until(lambda: r.runtime.snapshot().pump == "stopped")
    assert all(window.hidden and window.closed for window in r.windows)
    assert len(r.document["companion_previews"]["definitions"]) == 1


@pytest.mark.parametrize("mode", ["whole", "region"])
def test_selection_during_retirement_refuses_then_recovers(
    integrated, monkeypatch, mode
):
    r = integrated
    entered, release = threading.Event(), threading.Event()
    stop = r.host.stop
    commands = []
    submit = r.controller._ports.submit_native

    def submit_native(command):
        result = submit(command)
        commands.append(command)
        return result

    def held_stop(*args, **kwargs):
        if not kwargs.get("final", False) and not entered.is_set():
            # The real executor has committed retirement and released its lock.
            entered.set()
            try:
                assert release.wait(3), "retirement barrier not released"
            finally:
                stopped = stop(*args, **kwargs)
            return stopped
        return stop(*args, **kwargs)

    monkeypatch.setattr(r.host, "stop", held_stop)
    monkeypatch.setattr(
        r.controller,
        "_ports",
        replace(r.controller._ports, submit_native=submit_native),
    )
    try:
        assert r.receipt(r.controller.set_master(True))["persisted"]
        listing = r.receipt(r.controller.sources())
        assert listing["applied"], listing
        assert entered.wait(3), r.runtime.snapshot()
        state = r.runtime.snapshot()
        assert state.pump == "stopping"
        old_pump, executor = r.host._thread, r.runtime._worker
        token = listing["sources"][0]["candidate_token"]
        before = len(r.picks)
        pending = r.controller.select(None, token, mode, "Map", "exact", "Mapper", None)
        result = r.receipt(pending)
        assert result["pending"] is False
        assert result["applied"] is False
        assert result["persisted"] is False
        assert result["error"] == (
            "Another source selection is pending or the preview host is stopping"
        )
        assert r.runtime.snapshot().selection_pending is False
        assert r.host._thread is old_pump and r.host.is_running
        assert not r.picks and not r.windows
        assert not any(
            command.token and command.token.operation_id == pending["operation_id"]
            for command in commands
        )
        if mode == "region":
            # A completed refusal is actionable now, not a picker timeout.
            with monkeypatch.context() as patch:
                patch.setattr(
                    r.changed,
                    "wait",
                    lambda timeout=None: pytest.fail("waited despite terminal refusal"),
                )
                with pytest.raises(AssertionError, match=result["error"]):
                    r.wait_picker(pending, before)

        waiting = threading.Event()
        condition_wait = r.changed.wait

        def wait_for_cleanup(timeout=None):
            waiting.set()
            return condition_wait(timeout)

        # Observe the readiness wait actually blocking, rather than checking a
        # future before its thread has evaluated the held-retirement snapshot.
        with monkeypatch.context() as patch, ThreadPoolExecutor(max_workers=1) as pool:
            patch.setattr(r.changed, "wait", wait_for_cleanup)
            ready = pool.submit(r.wait_selection_ready)
            try:
                assert waiting.wait(3), "readiness did not wait for retirement"
                assert not ready.done()
            finally:
                release.set()
            ready.result(3)
        assert r.runtime.snapshot().pump == "stopped"
        assert not old_pump.is_alive() and r.host._thread is None

        before = len(r.picks)
        pending = r.controller.select(None, token, mode, "Map", "exact", "Mapper", None)
        if mode == "region":
            picker = r.wait_picker(pending, before)
            assert r.runtime.snapshot().selection_pending
            assert r.receipt(r.controller.set_master(False))["persisted"]
            assert r.runtime.snapshot().selection_pending and r.host.is_running
            r.call(
                lambda: picker["on_confirm"](
                    BINDING, Rect(100, 100, 400, 300), BINDING.client_size
                )
            )
        result = r.receipt(pending)
        assert result["applied"] and result["persisted"] and result["error"] is None
        assert any(
            command.token
            and command.token.operation_id == pending["operation_id"]
            and command.token.selection_lease.pump_epoch == state.pump_epoch + 1
            for command in commands
        )
        assert r.runtime._worker is executor
        r.wait_selection_ready()
        assert len(r.document["companion_previews"]["definitions"]) == 1
        if mode == "region":
            assert r.runtime.snapshot().pump == "stopped"
            assert r.windows and all(w.hidden and w.closed for w in r.windows)
        else:
            assert r.runtime.snapshot().companions == "active"
            assert r.runtime.snapshot().pump_epoch == state.pump_epoch + 1
            assert r.host._thread is not old_pump
            generation = r.controller.state()["rows"][0]["generation"]
            assert r.receipt(r.controller.remove(pending["id"], generation))[
                "persisted"
            ]
            r.wait(lambda: r.runtime.snapshot().pump == "stopped")
            assert all(w.closed for w in r.windows)
    finally:
        release.set()


@pytest.mark.parametrize("helper", ["receipt", "wait_picker"])
def test_synchronous_selection_refusal_never_waits(integrated, monkeypatch, helper):
    r = integrated
    r.runtime.set_eve(True, 1)
    r.wait(lambda: r.runtime.snapshot().eve == "active")
    listing = r.receipt(r.controller.sources())
    assert listing["applied"], listing
    r.wait_selection_ready()
    token = listing["sources"][0]["candidate_token"]
    before = len(r.picks)
    pending = r.controller.select(None, token, "region", "Map", "exact", "Mapper", None)
    picker = r.wait_picker(pending, before)
    try:
        assert pending["pending"] and r.runtime.snapshot().selection_pending
        assert len(r.picks) == before + 1
        before = len(r.picks)
        refused = r.controller.select(
            None, token, "region", "Map", "exact", "Mapper", None
        )
        assert refused["pending"] is False and refused["operation_id"] is None
        assert not refused["applied"] and not refused["persisted"]
        assert refused["error"] == "Another source selection is pending"
        assert all(
            item["operation_id"] is not None
            for item in r.controller.state()["operations"]
        )
        with monkeypatch.context() as patch:
            patch.setattr(
                r.changed,
                "wait",
                lambda timeout=None: pytest.fail("waited despite synchronous refusal"),
            )
            if helper == "receipt":
                assert r.receipt(refused) is refused
            else:
                with pytest.raises(AssertionError, match=refused["error"]):
                    r.wait_picker(refused, before)
        assert len(r.picks) == before and r.runtime.snapshot().selection_pending
    finally:
        r.call(lambda: picker["on_cancel"]("cancelled"))
        result = r.receipt(pending)
        assert not result["applied"] and result["error"] == "cancelled"
        r.wait_selection_ready()


def test_selection_readiness_keeps_active_eve_on_same_pump(integrated, monkeypatch):
    r = integrated
    stops = []
    stop = r.host.stop

    def record_stop(*args, **kwargs):
        stops.append(kwargs.get("final", False))
        return stop(*args, **kwargs)

    monkeypatch.setattr(r.host, "stop", record_stop)
    r.runtime.set_eve(True, 1)
    r.wait(lambda: r.runtime.snapshot().eve == "active")
    pump, epoch = r.host._thread, r.runtime.snapshot().pump_epoch
    assert r.receipt(r.controller.set_master(True))["persisted"]
    listing = r.receipt(r.controller.sources())
    assert listing["applied"], listing
    r.wait_selection_ready()
    token = listing["sources"][0]["candidate_token"]
    before = len(r.picks)
    cancelled = r.controller.select(
        None, token, "region", "Map", "exact", "Mapper", None
    )
    previous_picker = r.wait_picker(cancelled, before)
    r.call(lambda: previous_picker["on_cancel"]("cancelled"))
    assert not r.receipt(cancelled)["applied"]
    r.wait_selection_ready()
    before = len(r.picks)
    pending = r.controller.select(None, token, "region", "Map", "exact", "Mapper", None)
    picker = r.wait_picker(pending, before)
    assert picker is not previous_picker
    assert r.runtime.snapshot().selection_pending
    assert r.host._thread is pump and r.runtime.snapshot().pump_epoch == epoch
    r.call(
        lambda: picker["on_confirm"](
            BINDING, Rect(100, 100, 400, 300), BINDING.client_size
        )
    )
    assert r.receipt(pending)["persisted"]
    r.wait_selection_ready()
    assert r.host._thread is pump and r.runtime.snapshot().pump_epoch == epoch
    assert r.runtime.snapshot().eve == "active" and not stops


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
        before = len(r.picks)
        pending = r.controller.select(
            None, token, "region", "Map", "exact", "Mapper", None
        )
        picker = r.wait_picker(pending, before)
        crop = r.host.request_crop("select", "Alice")
        r.call(lambda: None)
        assert r.host._crop_controller.picker is None
        r.call(lambda: picker["on_cancel"]("cancelled"))
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
