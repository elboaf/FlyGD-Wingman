"""Coordinator over the real store, picker and crop controllers; OS/I/O seams only."""

import itertools
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from queue import SimpleQueue
from threading import Event, Lock

import pytest

from tests.test_preview_croppicker import Native
from wingman.preview import croppicker, cropwindow, win32
from wingman.preview.crops import (
    CropDefinition,
    deserialize,
    serialize,
    source_from_pixels,
)
from wingman.preview.cropstore import CropStore
from wingman.preview.geometry import Rect
from wingman.telemetry.model import ClientSessionId, RosterClient, RosterSnapshot

MONITOR = Rect(0, 0, 1920, 1080)
DEST = Rect(20, 30, 320, 160)
SOURCE = Rect(100, 50, 400, 200)
DEFINITION = CropDefinition(source_from_pixels(SOURCE, (1280, 720)), DEST)


def client(name="Alice", serial=1, hwnd=16):
    return RosterClient(
        hwnd, 101, "EVE - " + name, name, ClientSessionId(hwnd, 101, name, serial)
    )


class Resources(Native):
    """Multi-source/multi-thumbnail OS recording, retaining real native controllers."""

    def __init__(self):
        super().__init__()
        self.sources = {16: (1280, 720)}
        self.next_thumbnail = 9000
        self.peak = 0

    def GetClientRect(self, hwnd, pointer):
        if hwnd in self.sources:
            size = self.sources[hwnd]
            if size is None:
                return False
            pointer._obj.left = pointer._obj.top = 0
            pointer._obj.right, pointer._obj.bottom = size
            return True
        return super().GetClientRect(hwnd, pointer)

    def DwmRegisterThumbnail(self, dest, source, pointer):
        assert source in self.sources and dest in self.windows
        if not self.attempt("register", dest, source):
            return 0x80004005
        pointer._obj.value = self.next_thumbnail
        self.next_thumbnail += 1
        self.thumbnails.add(pointer._obj.value)
        self.peak = max(self.peak, len(self.thumbnails))
        return 0

    def GetForegroundWindow(self):
        return 0


class Transaction:
    def __init__(self, initial):
        self.document = {"preview": {"crops": serialize(initial)}}
        self.lock = Lock()
        self.entered = Event()
        self.release = Event()
        self.release.set()
        self.fail = False
        self.writes = []

    @contextmanager
    def update(self):
        with self.lock:
            old = deepcopy(self.document)
            try:
                yield self.document
                self.entered.set()  # admission has happened, publication has not
                assert self.release.wait(5)
                if self.fail:
                    raise OSError("disk unavailable")
                self.writes.append(deepcopy(self.document))
            except BaseException:
                self.document = old
                raise


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setattr(cropwindow, "_ensure_class", lambda libs: None)
    monkeypatch.setattr(croppicker, "_ensure_class", lambda libs: None)
    opened = []

    def make(initial=None):
        from wingman.preview.cropcontroller import CropController

        native = Resources()
        monkeypatch.setattr(croppicker.layered, "push", native.push)
        transaction = Transaction(initial or {})
        store = CropStore(
            transaction.update,
            initial or {},
            executor_factory=lambda: ThreadPoolExecutor(max_workers=1),
            debounce_s=100,
        )
        store.open_epoch(1)
        completions = SimpleQueue()
        states, activated = [], []
        sequence = itertools.count(1)
        c = CropController(
            native.lib,
            store,
            epoch=1,
            create_crop=cropwindow.CropWindow.create,
            create_picker=croppicker.CropPicker.create,
            read_client_size=lambda entry: native.sources.get(entry.hwnd),
            monitors=lambda: [MONITOR],
            activate=activated.append,
            is_locked=lambda name: False,
            publish=states.append,
            post_complete=completions.put,
            next_geometry_sequence=lambda: next(sequence),
        )
        r = type("Rig", (), {})()
        r.controller, r.store, r.native = c, store, native
        r.transaction, r.completions, r.states, r.activated = (
            transaction,
            completions,
            states,
            activated,
        )
        opened.append(r)
        return r

    yield make
    for r in opened:
        r.transaction.release.set()
        try:
            r.controller.begin_stop(1).result(5)
            r.controller.close_native()
        finally:
            r.store.close().result(5)
        assert not r.native.thumbnails
        assert not r.native.windows


def roster(r, generation, *clients):
    for entry in clients:
        r.native.sources.setdefault(entry.hwnd, (1280, 720))
    snapshot = RosterSnapshot(generation, clients)
    r.store.observe_roster(1, snapshot)
    r.controller.reconcile(snapshot)


def request(r, action="select", name="Alice", value=None):
    session = r.controller.sessions[name].session if action == "select" else None
    token = r.store.begin(name, epoch=1, session=session)
    receipt = r.controller.request(action, name, value, token)
    return token, receipt


def finish(r):
    r.store.drain().result(5)
    while not r.completions.empty():
        r.controller.complete(r.completions.get_nowait())
    r.store.drain().result(5)


def confirm(r):
    picker = r.controller.picker
    assert picker is not None
    # The real Use region path maps and closes the whole bundle before callback.
    picker.selection = Rect(
        picker.destination.x + 20, picker.destination.y + 20, 100, 80
    )
    picker._confirm()


def test_stopping_windows_cannot_be_revealed_by_later_visibility_updates(rig):
    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    r.controller.begin_stop(1).result(5)
    r.controller.set_hidden(False)
    assert r.controller.live["Alice"].window.hidden


def test_invalid_source_at_completion_is_reported_without_recreation(rig):
    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    request(r)
    confirm(r)
    result = r.completions.get(timeout=5)
    r.native.sources[16] = (20, 20)
    r.controller.complete(result)
    assert not r.controller.live
    assert r.states[-1]["statuses"]["Alice"] == "invalid-source"


def test_old_epoch_command_cannot_open_picker_for_same_discovery_session(rig):
    r = rig()
    roster(r, 1, client())
    token = r.store.begin("Alice", epoch=0, session=client().session)
    receipt = r.controller.request("select", "Alice", None, token)
    assert not receipt["pending"] and receipt["error"]
    assert not r.native.windows and r.controller.picker is None


def test_failure_of_a_previously_swapped_candidate_is_degraded_not_retried(rig):
    r = rig()
    roster(r, 1, client())
    request(r)
    confirm(r)
    finish(r)
    window = r.controller.live["Alice"].window
    r.native.fail = "update"
    window.set_hidden(True)
    assert window.hwnd is None
    r.native.fail = None
    before = r.native.next_thumbnail
    roster(r, 2, client())
    assert r.native.next_thumbnail == before
    assert r.states[-1]["statuses"]["Alice"] == "native-failed"


def test_pruned_cancellation_outcome_does_not_strand_picker_resources(rig):
    r = rig()
    roster(r, 1, client())
    selecting, _ = request(r)
    latest = RosterSnapshot(2, ())
    r.store.observe_roster(1, latest)
    # The pump was delayed while configuration completions aged out an ingress
    # cancellation. Pending work is never pruned, but this token is terminal.
    for index in range(33):
        token = r.store.begin(str(index), epoch=1, session=None)
        assert r.store.remove(token).result(5).persisted
    assert selecting.operation_id not in r.store.snapshot()["operations"]
    r.controller.reconcile(latest)
    assert r.controller.picker is None and not r.native.thumbnails
    assert not r.states[-1]["busy"]


def test_stop_without_user_geometry_does_not_persist_a_rescued_destination(rig):
    destination = Rect(5000, 5000, 320, 160)
    r = rig({"Alice": replace(DEFINITION, window=destination)})
    roster(r, 1, client())
    r.controller.begin_stop(1).result(5)
    assert not r.transaction.writes
    assert deserialize(r.store.snapshot()["definitions"])["Alice"].window == destination


def test_published_remove_can_wait_for_completion_while_roster_arrives(rig):
    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    request(r, "remove")
    result = r.completions.get(timeout=5)
    roster(r, 2, client())
    assert r.controller.live["Alice"].window.hwnd is not None
    r.controller.complete(result)
    assert not r.controller.live


def test_publication_between_geometry_generation_read_and_record_keeps_movement(
    rig, monkeypatch
):
    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    old = r.controller.live["Alice"].window
    request(r)
    r.transaction.release.clear()
    confirm(r)
    assert r.transaction.entered.wait(5)
    original = r.store.record_geometry
    results = []

    def publish_then_record(*args):
        if not results:
            r.transaction.release.set()
            results.append(r.completions.get(timeout=5))
        original(*args)

    monkeypatch.setattr(r.store, "record_geometry", publish_then_record)
    moved = Rect(270, 330, 320, 160)
    old.move(moved)
    roster(r, 2)
    r.controller.complete(results[0])
    r.store.drain().result(5)
    assert deserialize(r.store.snapshot()["definitions"])["Alice"].window == moved


def test_movement_after_publication_survives_source_loss_before_completion(rig):
    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    old = r.controller.live["Alice"].window
    request(r)
    confirm(r)
    result = r.completions.get(timeout=5)
    moved = Rect(250, 300, 320, 160)
    old.move(moved)
    roster(r, 2)
    r.controller.complete(result)
    r.store.drain().result(5)
    assert deserialize(r.store.snapshot()["definitions"])["Alice"].window == moved


def test_arrivals_cannot_overfill_cap_while_disable_awaits_completion(rig):
    names = [f"Pilot {i}" for i in range(8)]
    r = rig(dict.fromkeys([*names, "Alice"], DEFINITION))
    roster(r, 1, *(client(name, hwnd=20 + i) for i, name in enumerate(names)))
    request(r, "enabled", name="Pilot 7", value=False)
    result = r.completions.get(timeout=5)
    roster(r, 2, client(), *(client(name, hwnd=20 + i) for i, name in enumerate(names)))
    assert len(r.native.thumbnails) <= 8
    r.controller.complete(result)
    assert len(r.controller.live) == 8
    assert "Alice" in r.controller.live and "Pilot 7" not in r.controller.live
    assert r.native.peak == 8


def test_stop_keeps_committed_resources_until_explicit_native_close(rig):
    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    window = r.controller.live["Alice"].window
    request(r)
    r.transaction.release.clear()
    stopped = r.controller.begin_stop(1)
    assert window.hwnd is not None
    assert window.locked
    r.transaction.release.set()
    assert stopped.result(5)
    assert window.hwnd is not None
    r.controller.close_native()
    assert window.hwnd is None


def test_later_remove_supersedes_all_older_unadmitted_selections(rig):
    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    first, _ = request(r)
    second, _ = request(r)
    remove, _ = request(r, "remove")
    finish(r)
    state = r.store.snapshot()
    assert not state["operations"][first.operation_id]["pending"]
    assert not state["operations"][second.operation_id]["pending"]
    assert state["operations"][remove.operation_id]["persisted"]
    assert state["definitions"] == {}
    assert r.controller.picker is None


def test_native_failure_has_one_degraded_episode_per_session_generation(rig):
    r = rig({"Alice": DEFINITION})
    r.native.fail = "register"
    roster(r, 1, client())
    assert r.states[-1]["statuses"]["Alice"] == "native-failed"
    assert "0x10" not in str(r.states)
    r.native.fail = None
    roster(r, 2, client())
    assert not r.controller.live
    request(r, "enabled", value=True)
    finish(r)
    assert "Alice" in r.controller.live


def test_candidate_failure_after_admission_is_not_retried_on_completion_or_scan(rig):
    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    request(r)
    r.transaction.release.clear()
    confirm(r)
    assert r.transaction.entered.wait(5)
    candidate = r.controller._temporary.candidate.window
    r.native.fail = "update"
    candidate.move(Rect(20, 30, 500, 200))
    assert candidate.hwnd is None
    r.native.fail = None
    r.transaction.release.set()
    finish(r)
    before = r.native.next_thumbnail
    roster(r, 2, client())
    assert r.native.next_thumbnail == before
    assert not r.controller.live
    assert r.states[-1]["statuses"]["Alice"] == "native-failed"


def test_source_size_change_during_save_updates_old_and_hidden_candidate(rig):
    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    old = r.controller.live["Alice"].window
    request(r)
    r.transaction.release.clear()
    confirm(r)
    assert r.transaction.entered.wait(5)
    candidate = r.controller._temporary.candidate.window
    r.native.sources[16] = (640, 360)
    roster(r, 2, client())
    assert old.source_rect == Rect(50, 25, 200, 100)
    assert candidate.source_rect.w < 100
    assert candidate.hidden
    r.transaction.release.set()
    finish(r)


def test_movement_during_admitted_save_survives_replacement_failure(rig):
    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    old = r.controller.live["Alice"].window
    request(r)
    r.transaction.release.clear()
    confirm(r)
    assert r.transaction.entered.wait(5)
    moved = Rect(320, 240, 500, 250)
    old.move(moved)
    r.transaction.fail = True
    r.transaction.release.set()
    result = r.completions.get(timeout=5)
    assert not result.persisted
    r.transaction.fail = False
    r.controller.complete(result)
    r.store.drain().result(5)
    assert r.controller.live["Alice"].window is old
    assert deserialize(r.store.snapshot()["definitions"])["Alice"].window == moved


def test_host_ingress_fences_unadmitted_work_without_native_reconcile(rig, monkeypatch):
    from wingman.preview.host import PreviewHost

    r = rig({"Alice": DEFINITION})
    h = PreviewHost(on_layout_changed=lambda *args: None, crop_store=r.store)
    h._crop_epoch = 1
    h.apply_roster(RosterSnapshot(1, (client(),)))
    token = r.store.begin("Alice", epoch=1, session=client().session)
    h.apply_roster(RosterSnapshot(2, (client(serial=2),)))
    assert not r.store.snapshot()["operations"][token.operation_id]["pending"]
    assert not r.transaction.writes and not r.native.windows
    h.apply_roster(RosterSnapshot(1, (client(),)))
    newer = r.store.begin("Alice", epoch=1, session=client(serial=2).session)
    assert r.store.put(newer, DEFINITION).result(5).persisted


def test_host_crop_activation_bypasses_primary_exclusion_and_uses_current_session(
    rig, monkeypatch
):
    from wingman.preview import host

    r = rig({"Alice": DEFINITION})
    h = host.PreviewHost(
        on_layout_changed=lambda *args: None,
        crop_store=r.store,
        excluded=lambda: ["Alice"],
    )
    h._crop_epoch = 1
    monkeypatch.setattr(h, "_monitors", lambda: [MONITOR])
    monkeypatch.setattr(h, "_activate_client", lambda libs, c: r.activated.append(c))
    h._init_crop_controller(r.native.lib)
    h.apply_roster(RosterSnapshot(1, (client(),)))
    h._apply_pending_roster(r.native.lib)
    assert h._windows == {} and "Alice" in h._clients
    live = h._crop_controller.live["Alice"].window
    live._on_activate(live.client)
    assert r.activated[-1].stable_key == "Alice" and r.activated[-1].hwnd == 16
    h.apply_roster(RosterSnapshot(2, (client(serial=2, hwnd=42),)))
    r.native.sources[42] = (1280, 720)
    live._on_activate(live.client)
    assert r.activated[-1].hwnd == 42
    h._crop_controller.begin_stop(h._crop_epoch).result(5)
    h._crop_controller.close_native()


def test_host_retains_geometry_sequence_across_pump_lifetimes(rig, monkeypatch):
    from wingman.preview.host import PreviewHost

    r = rig({"Alice": DEFINITION})
    h = PreviewHost(on_layout_changed=lambda *args: None, crop_store=r.store)
    h._crop_epoch = 1
    monkeypatch.setattr(h, "_monitors", lambda: [MONITOR])
    for generation, rect in [
        (1, Rect(100, 100, 320, 160)),
        (2, Rect(200, 200, 320, 160)),
    ]:
        h._init_crop_controller(r.native.lib)
        snapshot = RosterSnapshot(generation, (client(serial=generation),))
        h.apply_roster(snapshot)
        h._crop_controller.reconcile(snapshot)
        h._crop_controller.live["Alice"].window.move(rect)
        h._crop_controller.begin_stop(h._crop_epoch).result(5)
        h._crop_controller.close_native()
        assert deserialize(r.store.snapshot()["definitions"])["Alice"].window == rect


def test_dialog_message_drains_picker_after_hwnd_is_gone(rig):
    from ctypes import wintypes

    r = rig()
    roster(r, 1, client())
    request(r)
    picker = r.controller.picker
    hwnd = picker.hwnd
    picker._on_message(win32.WM_DESTROY, 0, 0)
    picker._on_message(win32.WM_NCDESTROY, 0, 0)
    r.native.windows.pop(hwnd)  # OS has completed the parent destruction
    assert picker.hwnd is None and r.controller.picker is picker
    r.controller.process_dialog_message(wintypes.MSG())
    assert r.controller.picker is None
    assert not r.states[-1]["busy"]
    assert not r.native.thumbnails


def test_eight_plus_picker_then_candidate_then_eight(rig):
    names = ["Alice"] + [f"Pilot {i}" for i in range(7)]
    r = rig(dict.fromkeys(names, DEFINITION))
    roster(r, 1, *(client(name, hwnd=16 + i) for i, name in enumerate(names)))
    old = r.controller.live["Alice"].window
    token, receipt = request(r)
    assert receipt["pending"] and receipt["operation_id"] == token.operation_id
    assert len(r.native.thumbnails) == 9
    picker = r.controller.picker
    picker_handles = set(r.native.windows) - {
        live.window.hwnd for live in r.controller.live.values()
    }
    r.transaction.release.clear()
    confirm(r)
    assert r.transaction.entered.wait(5)
    assert picker.hwnd is None and r.controller.picker is None
    assert not picker_handles.intersection(r.native.windows)
    assert len(r.native.thumbnails) == 9
    assert old.hwnd is not None
    assert not r.store.snapshot()["operations"][token.operation_id]["persisted"]
    candidate = r.controller._temporary.candidate.window
    assert candidate.hidden
    r.controller.set_hidden(False)
    assert candidate.hidden
    r.transaction.release.set()
    finish(r)
    assert old.hwnd is None
    assert r.controller.live["Alice"].window is candidate
    assert not candidate.hidden
    assert len(r.native.thumbnails) == 8 and r.native.peak == 9
    assert r.store.snapshot()["operations"][token.operation_id]["persisted"]


def test_at_cap_refuses_creation_without_discarding_saved_suppressed_definitions(rig):
    names = [f"Pilot {i}" for i in range(9)]
    r = rig(dict.fromkeys(names, DEFINITION))
    roster(r, 1, *(client(name, hwnd=16 + i) for i, name in enumerate(names)))
    token, receipt = request(r, name="Pilot 8")
    assert not receipt["pending"] and receipt["error"]
    assert r.controller.picker is None
    assert len(r.native.thumbnails) == 8
    assert len(r.store.snapshot()["definitions"]) == 9
    assert not r.store.snapshot()["operations"][token.operation_id]["pending"]


def test_new_selection_reserves_arrival_capacity_and_temporary_slot(rig):
    names = [f"Pilot {i}" for i in range(8)]
    r = rig(dict.fromkeys(names, DEFINITION))
    roster(
        r, 1, client(), *(client(name, hwnd=20 + i) for i, name in enumerate(names[:7]))
    )
    token, _ = request(r)
    picker = r.controller.picker
    roster(r, 2, client(), *(client(name, hwnd=20 + i) for i, name in enumerate(names)))
    assert len(r.controller.live) == 7
    assert r.states[-1]["statuses"]["Pilot 7"] == "suppressed"
    _, refused = request(r, name="Pilot 0")
    assert refused["error"] and r.controller.picker is picker
    assert r.native.peak == 8
    picker.cancel()
    assert len(r.controller.live) == 8
    assert not r.store.snapshot()["operations"][token.operation_id]["pending"]


@pytest.mark.parametrize("failure", ["native", "persistence"])
def test_failed_replacement_keeps_old_crop_and_committed_definition(rig, failure):
    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    old = r.controller.live["Alice"].window
    token, _ = request(r)
    if failure == "native":
        r.native.fail = "register"
    else:
        r.transaction.fail = True
    confirm(r)
    r.transaction.release.set()
    r.store.drain().result(5)
    r.transaction.fail = False
    finish(r)
    assert r.controller.live["Alice"].window is old and old.hwnd is not None
    assert deserialize(r.store.snapshot()["definitions"])["Alice"] == DEFINITION
    assert not r.store.snapshot()["operations"][token.operation_id]["persisted"]
    assert len(r.native.thumbnails) == 1
    assert "0x10" not in str(r.states)


def test_picker_initial_failure_is_terminal_without_unassigned_window_access(rig):
    r = rig()
    roster(r, 1, client())
    r.native.fail = "register"
    token, receipt = request(r)
    assert not receipt["pending"]
    assert not r.store.snapshot()["operations"][token.operation_id]["pending"]
    assert not r.native.thumbnails and r.controller.picker is None
    assert not r.states[-1]["busy"]


def test_renewed_session_cancels_picker_even_with_same_hwnd_pid(rig):
    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    token, _ = request(r)
    picker = r.controller.picker
    roster(r, 2, client(serial=2))
    assert picker.hwnd is None and r.controller.picker is None
    assert not r.store.snapshot()["operations"][token.operation_id]["pending"]
    assert not r.transaction.writes
    assert r.controller.live["Alice"].window.client == client(serial=2)


def test_loss_after_admission_preserves_success_but_never_reveals_stale_candidate(rig):
    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    token, _ = request(r)
    r.transaction.release.clear()
    confirm(r)
    assert r.transaction.entered.wait(5)
    candidate = r.controller._temporary.candidate.window
    roster(r, 2)
    assert candidate.hwnd is None and not r.controller.live
    r.transaction.release.set()
    finish(r)
    assert r.store.snapshot()["operations"][token.operation_id]["persisted"]
    assert not r.controller.live and not r.native.thumbnails
    roster(r, 3, client(serial=3, hwnd=42))
    assert r.controller.live["Alice"].window.client.hwnd == 42
    assert r.states[-1]["statuses"]["Alice"] == "live"


def test_geometry_after_publication_before_completion_is_saved_at_replacement_generation(
    rig,
):
    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    old = r.controller.live["Alice"].window
    token, _ = request(r)
    confirm(r)
    result = r.completions.get(timeout=5)
    assert result.persisted
    moved = Rect(310, 240, 460, 230)
    old.move(moved)
    assert r.store.snapshot()["generations"]["Alice"] == token.generation
    r.controller.complete(result)
    r.store.drain().result(5)
    assert r.controller.live["Alice"].window.rect == moved
    assert deserialize(r.store.snapshot()["definitions"])["Alice"].window == moved


def test_later_disable_waits_for_pump_completion_not_just_worker_publication(rig):
    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    put, _ = request(r)
    confirm(r)
    result = r.completions.get(timeout=5)
    disable, _ = request(r, "enabled", value=False)
    r.store.drain().result(5)
    assert r.store.snapshot()["operations"][disable.operation_id]["pending"]
    assert len(r.transaction.writes) == 1
    r.controller.complete(result)
    finish(r)
    assert not r.controller.live
    assert r.store.snapshot()["operations"][put.operation_id]["persisted"]
    assert r.store.snapshot()["operations"][disable.operation_id]["persisted"]
    assert not deserialize(r.store.snapshot()["definitions"])["Alice"].enabled


def test_disable_supersedes_picker_before_admission(rig):
    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    selecting, _ = request(r)
    picker = r.controller.picker
    disable, _ = request(r, "enabled", value=False)
    assert picker.hwnd is None
    finish(r)
    assert not r.store.snapshot()["operations"][selecting.operation_id]["persisted"]
    assert r.store.snapshot()["operations"][disable.operation_id]["persisted"]
    assert len(r.transaction.writes) == 1
    assert not r.controller.live


def test_stop_submits_held_configuration_in_order_before_drain(rig):
    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    request(r)
    r.transaction.release.clear()
    confirm(r)
    assert r.transaction.entered.wait(5)
    disable, _ = request(r, "enabled", value=False)
    remove, _ = request(r, "remove")
    stopped = r.controller.begin_stop(1)
    assert not stopped.done()
    r.transaction.release.set()
    assert stopped.result(5)
    state = r.store.snapshot()
    assert state["definitions"] == {}
    assert all(not op["pending"] for op in state["operations"].values())
    assert state["operations"][disable.operation_id]["persisted"]
    assert state["operations"][remove.operation_id]["persisted"]
    r.controller.close_native()
    finish(r)
    assert not r.controller.live


def test_hide_and_lock_reach_new_live_windows_and_candidate_without_reveal(rig):
    r = rig({"Alice": DEFINITION})
    r.controller.set_hidden(True)
    r.controller._is_locked = lambda name: True
    roster(r, 1, client())
    live = r.controller.live["Alice"].window
    assert live.hidden and live.locked
    request(r)
    r.transaction.release.clear()
    confirm(r)
    assert r.transaction.entered.wait(5)
    candidate = r.controller._temporary.candidate.window
    r.controller._is_locked = lambda name: False
    r.controller.restyle()
    r.controller.set_hidden(False)
    assert not live.hidden and not live.locked
    assert candidate.hidden and not candidate.locked
    r.transaction.release.set()
    finish(r)
    assert not candidate.hidden


def test_native_close_requests_disable_transaction_instead_of_destroying(rig):
    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    live = r.controller.live["Alice"].window
    r.transaction.release.clear()
    live._on_message(win32.WM_CLOSE, 0, 0)
    assert r.transaction.entered.wait(5)
    assert live.hwnd is not None
    r.transaction.release.set()
    finish(r)
    assert live.hwnd is None
    assert not deserialize(r.store.snapshot()["definitions"])["Alice"].enabled


def test_reconcile_retains_full_sessions_and_does_not_recreate_per_scan(rig):
    r = rig({"Alice": DEFINITION})
    entry = client()
    roster(r, 1, entry)
    first = r.controller.live["Alice"].window
    assert first.client == entry
    assert first.source_rect == SOURCE
    roster(r, 2, entry)
    assert r.controller.live["Alice"].window is first
    roster(r, 3, client(serial=2))
    assert first.hwnd is None
    assert r.controller.live["Alice"].window.client.session == client(serial=2).session
    assert len(r.native.thumbnails) == 1


def test_source_dimensions_recompute_and_invalid_source_is_not_retried_per_scan(rig):
    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    window = r.controller.live["Alice"].window
    r.native.sources[16] = (640, 360)
    roster(r, 2, client())
    assert window.source_rect == Rect(50, 25, 200, 100)
    r.native.sources[16] = (20, 20)
    roster(r, 3, client())
    assert window.hwnd is None
    assert r.states[-1]["statuses"]["Alice"] == "invalid-source"
    attempts = r.native.next_thumbnail
    r.native.sources[16] = (1280, 720)
    roster(r, 4, client())
    assert r.native.next_thumbnail == attempts
    roster(r, 5, client(serial=2))
    assert "Alice" in r.controller.live


@pytest.mark.parametrize(
    "destination,expected",
    [
        (Rect(5000, 5000, 320, 160), Rect(1600, 920, 320, 160)),
        (Rect(-100, 30, 320, 160), Rect(-100, 30, 320, 160)),
    ],
)
def test_only_wholly_offscreen_destinations_are_rescued(rig, destination, expected):
    r = rig({"Alice": replace(DEFINITION, window=destination)})
    roster(r, 1, client())
    assert r.controller.live["Alice"].window.rect == expected
    assert deserialize(r.store.snapshot()["definitions"])["Alice"].window == destination
