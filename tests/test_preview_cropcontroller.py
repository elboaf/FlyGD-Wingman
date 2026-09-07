"""Coordinator over the real store, picker and crop controllers; OS/I/O seams only."""

import itertools
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from queue import SimpleQueue
from threading import Event, Lock, Thread

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
        self.attempted = Event()
        self.entered = Event()
        self.release = Event()
        self.release.set()
        self.fail = False
        self.writes = []

    @contextmanager
    def update(self):
        self.attempted.set()
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


@pytest.mark.parametrize("failure", [None, "native", "save"])
def test_available_enable_prepares_hidden_before_save_and_promotes(rig, failure):
    disabled = replace(DEFINITION, enabled=False)
    r = rig({"Alice": disabled})
    roster(r, 1, client())
    if failure == "native":
        r.native.fail = "register"
    r.transaction.fail = failure == "save"
    r.transaction.release.clear()
    token = r.store.begin("Alice", epoch=1, session=client().session)
    receipt = r.controller.request("enabled", "Alice", True, token)
    if failure == "native":
        assert not receipt["pending"] and receipt["error"]
        assert not r.transaction.writes
        assert deserialize(r.store.snapshot()["definitions"])["Alice"] == disabled
        return
    assert r.transaction.entered.wait(5)
    candidate = r.controller._temporary.candidate.window
    assert candidate.hidden and "Alice" not in r.controller.live
    assert deserialize(r.store.snapshot()["definitions"])["Alice"] == disabled
    r.transaction.release.set()
    finish(r)
    result = r.store.snapshot()["operations"][token.operation_id]
    assert result["persisted"] is (failure is None)
    if failure == "save":
        assert candidate.hwnd is None
        assert deserialize(r.store.snapshot()["definitions"])["Alice"] == disabled
    else:
        assert r.controller.live["Alice"].window is candidate and not candidate.hidden
        assert len([c for c in r.native.events if c[0] == "register"]) == 1


@pytest.mark.parametrize("admitted", [False, True])
@pytest.mark.parametrize("loss", ["session", "stop"])
def test_available_enable_loss_obeys_admission(rig, admitted, loss):
    disabled = replace(DEFINITION, enabled=False)
    r = rig({"Alice": disabled})
    roster(r, 1, client())
    if admitted:
        r.transaction.release.clear()
    else:
        r.transaction.lock.acquire()
    try:
        token = r.store.begin("Alice", epoch=1, session=client().session)
        r.controller.request("enabled", "Alice", True, token)
        assert (r.transaction.entered if admitted else r.transaction.attempted).wait(5)
        candidate = r.controller._temporary.candidate.window
        if loss == "session":
            roster(r, 2, client(serial=2))
        else:
            r.controller.begin_stop(1)
        assert candidate.hwnd is None
    finally:
        r.transaction.release.set()
        if not admitted:
            r.transaction.lock.release()
    finish(r)
    state = r.store.snapshot()
    assert state["operations"][token.operation_id]["persisted"] is admitted
    assert state["definitions"]["Alice"]["enabled"] is admitted
    assert all(live.window is not candidate for live in r.controller.live.values())


def test_cap_full_refuses_offline_enable_on_pump(rig):
    names = [f"Pilot {i}" for i in range(8)]
    r = rig(
        {
            **dict.fromkeys(names, DEFINITION),
            "Offline": replace(DEFINITION, enabled=False),
        }
    )
    roster(r, 1, *(client(name, hwnd=20 + i) for i, name in enumerate(names)))
    token, receipt = request(r, "enabled", "Offline", True)
    finish(r)
    assert not receipt["pending"] and "limit" in receipt["error"].lower()
    assert not r.store.snapshot()["operations"][token.operation_id]["persisted"]
    assert not r.transaction.writes and len(r.controller.live) == 8


def test_offline_enable_reserves_eventual_capacity_against_arrival_and_selection(rig):
    names = [f"Pilot {i}" for i in range(7)]
    r = rig(
        {
            **dict.fromkeys([*names, "Arrival"], DEFINITION),
            "Offline": replace(DEFINITION, enabled=False),
        }
    )
    current = [client(name, hwnd=20 + i) for i, name in enumerate(names)]
    roster(r, 1, *current)
    r.transaction.release.clear()
    token, _ = request(r, "enabled", "Offline", True)
    assert r.transaction.entered.wait(5)
    roster(r, 2, *current, client("Arrival", hwnd=40), client("Selecting", hwnd=41))
    assert len(r.controller.live) == 7
    _, refused = request(r, "select", "Selecting")
    assert not refused["pending"] and "limit" in refused["error"].lower()
    r.transaction.release.set()
    finish(r)
    assert r.store.snapshot()["operations"][token.operation_id]["persisted"]
    assert len(r.controller.live) == 8


def test_enable_candidate_keeps_monitor_rescue_unsaved(rig):
    disabled = replace(DEFINITION, enabled=False, window=Rect(5000, 5000, 320, 160))
    r = rig({"Alice": disabled})
    roster(r, 1, client())
    token = r.store.begin("Alice", epoch=1, session=client().session)
    r.controller.request("enabled", "Alice", True, token)
    finish(r)
    assert r.controller.live["Alice"].window.rect == Rect(1600, 920, 320, 160)
    assert (
        deserialize(r.store.snapshot()["definitions"])["Alice"].window
        == disabled.window
    )
    assert len(r.transaction.writes) == 1


def test_enabling_shares_temporary_slot_and_reports_saving_not_selecting(rig):
    r = rig({"Alice": replace(DEFINITION, enabled=False)})
    roster(r, 1, client(), client("Bob", hwnd=20))
    r.transaction.release.clear()
    token = r.store.begin("Alice", epoch=1, session=client().session)
    r.controller.request("enabled", "Alice", True, token)
    assert r.transaction.entered.wait(5)
    assert r.states[-1]["statuses"]["Alice"] == "saving"
    _, receipt = request(r, "select", "Bob")
    assert not receipt["pending"] and "another crop" in receipt["error"].lower()
    assert r.controller.picker is None and len(r.native.thumbnails) == 1
    r.transaction.release.set()
    finish(r)
    assert r.controller.live["Alice"].window.hwnd is not None


def test_enable_setup_failure_never_announces_a_picker(rig):
    r = rig({"Alice": replace(DEFINITION, enabled=False)})
    roster(r, 1, client())
    r.native.fail = "register"
    token = r.store.begin("Alice", epoch=1, session=client().session)
    r.controller.request("enabled", "Alice", True, token)
    assert all(state["statuses"].get("Alice") != "selecting" for state in r.states)


def test_enable_invalid_current_source_preserves_disabled_definition(rig):
    disabled = replace(DEFINITION, enabled=False)
    r = rig({"Alice": disabled})
    roster(r, 1, client())
    r.native.sources[16] = (20, 20)
    token = r.store.begin("Alice", epoch=1, session=client().session)
    receipt = r.controller.request("enabled", "Alice", True, token)
    assert not receipt["pending"] and "reselect" in receipt["error"].lower()
    assert not r.transaction.writes and not r.native.thumbnails
    assert deserialize(r.store.snapshot()["definitions"])["Alice"] == disabled


def test_native_enable_reservation_refuses_offline_enable_before_publication(rig):
    names = [f"Pilot {i}" for i in range(7)]
    r = rig(
        {
            **dict.fromkeys(names, DEFINITION),
            "Alice": replace(DEFINITION, enabled=False),
            "Offline": replace(DEFINITION, enabled=False),
        }
    )
    roster(r, 1, client(), *(client(name, hwnd=20 + i) for i, name in enumerate(names)))
    r.transaction.release.clear()
    token = r.store.begin("Alice", epoch=1, session=client().session)
    r.controller.request("enabled", "Alice", True, token)
    assert r.transaction.entered.wait(5)
    _, receipt = request(r, "enabled", "Offline", True)
    assert not receipt["pending"] and "limit" in receipt["error"].lower()
    assert len(r.native.thumbnails) == 8 and r.controller.picker is None
    r.transaction.release.set()
    finish(r)
    assert not r.store.snapshot()["definitions"]["Offline"]["enabled"]
    assert r.store.snapshot()["definitions"]["Alice"]["enabled"]


@pytest.mark.parametrize("admitted", [False, True])
def test_enable_candidate_failure_cancels_only_before_admission(rig, admitted):
    r = rig({"Alice": replace(DEFINITION, enabled=False)})
    roster(r, 1, client())
    if admitted:
        r.transaction.release.clear()
    else:
        r.transaction.lock.acquire()
    try:
        token = r.store.begin("Alice", epoch=1, session=client().session)
        r.controller.request("enabled", "Alice", True, token)
        assert (r.transaction.entered if admitted else r.transaction.attempted).wait(5)
        candidate = r.controller._temporary.candidate.window
        r.native.fail = "update"
        candidate.move(Rect(20, 30, 500, 200))
        assert candidate.hwnd is None
        r.native.fail = None
    finally:
        r.transaction.release.set()
        if not admitted:
            r.transaction.lock.release()
    finish(r)
    state = r.store.snapshot()
    assert state["operations"][token.operation_id]["persisted"] is admitted
    assert state["definitions"]["Alice"]["enabled"] is admitted
    assert not r.controller.live
    before = r.native.next_thumbnail
    roster(r, 2, client())
    assert r.native.next_thumbnail == before


def test_stopping_refusal_does_not_replace_admitted_enable_receipt(rig):
    r = rig({"Alice": replace(DEFINITION, enabled=False)})
    roster(r, 1, client())
    r.transaction.release.clear()
    token = r.store.begin("Alice", epoch=1, session=client().session)
    r.controller.request("enabled", "Alice", True, token)
    assert r.transaction.entered.wait(5)
    r.controller.begin_stop(1)
    receipt = r.controller.request("enabled", "Alice", True, token)
    assert receipt["pending"] and receipt["error"] is None
    r.transaction.release.set()
    finish(r)
    assert r.store.snapshot()["operations"][token.operation_id]["persisted"]


def test_queued_enable_does_not_keep_the_committed_disabled_window_visible(rig):
    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    old = r.controller.live["Alice"].window
    r.transaction.release.clear()
    request(r, "enabled", value=False)
    assert r.transaction.entered.wait(5)
    token = r.store.begin("Alice", epoch=1, session=client().session)
    r.controller.request("enabled", "Alice", True, token)
    r.transaction.release.set()
    disabled_result = r.completions.get(timeout=5)
    assert disabled_result.persisted
    r.transaction.entered.clear()
    r.transaction.release.clear()
    r.controller.complete(disabled_result)
    assert r.transaction.entered.wait(5)
    assert old.hwnd is None
    assert "Alice" not in r.controller.live
    assert r.controller._temporary.candidate.window.hidden
    assert not r.store.snapshot()["definitions"]["Alice"]["enabled"]
    r.transaction.release.set()
    finish(r)
    assert r.controller.live["Alice"].window is not old


def test_host_batch_continues_same_owner_after_picker_preparation_exception(
    rig, monkeypatch
):
    from wingman.preview.host import PreviewHost

    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    h = PreviewHost(on_layout_changed=lambda *args: None, crop_store=r.store)
    h._crop_controller = r.controller
    selecting = r.store.begin("Alice", epoch=1, session=client().session)
    following = r.store.begin("Alice", epoch=1, session=None)
    h._crop_commands = [
        ("select", "Alice", None, selecting),
        ("enabled", "Alice", True, following),
    ]

    def fail_picker(*args, **kwargs):
        raise RuntimeError("picker preparation failed")

    monkeypatch.setattr(r.controller, "_create_picker", fail_picker)
    h._apply_crop_commands(None)
    finish(r)
    outcomes = r.store.snapshot()["operations"]
    assert not outcomes[selecting.operation_id]["pending"]
    assert outcomes[following.operation_id]["persisted"]
    assert not r.states[-1]["busy"] and r.controller.picker is None
    assert r.native.peak == 1


def test_host_command_exception_does_not_undo_admitted_write(rig, monkeypatch):
    from wingman.preview.host import PreviewHost

    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    h = PreviewHost(on_layout_changed=lambda *args: None, crop_store=r.store)
    h._crop_controller = r.controller
    first = r.store.begin("Alice", epoch=1, session=None)
    following = r.store.begin("Alice", epoch=1, session=None)
    h._crop_commands = [
        ("enabled", "Alice", True, first),
        ("remove", "Alice", None, following),
    ]
    original = r.controller.request
    r.transaction.release.clear()

    def fail_after_admission(action, name, value, token):
        receipt = original(action, name, value, token)
        if token == first:
            assert r.transaction.entered.wait(5)
            raise RuntimeError("failure after admission")
        return receipt

    monkeypatch.setattr(r.controller, "request", fail_after_admission)
    h._apply_crop_commands(None)
    assert r.store.snapshot()["operations"][following.operation_id]["pending"]
    r.transaction.release.set()
    result = r.completions.get(timeout=5)
    assert result.token == first and result.persisted
    r.controller.complete(result)
    result = r.completions.get(timeout=5)
    assert result.token == following and result.persisted
    r.controller.complete(result)
    assert r.store.snapshot()["definitions"] == {}
    assert len(r.transaction.writes) == 2


@pytest.mark.parametrize("outcome", ["canceled", "persisted"])
def test_delayed_pruned_command_returns_expired_receipt_without_replay(rig, outcome):
    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    token = r.store.begin("Alice", epoch=1, session=client().session)
    if outcome == "canceled":
        assert r.store.cancel(token)
    else:
        assert r.store.put(token, DEFINITION).result(5).persisted
    for index in range(33):
        later = r.store.begin(str(index), epoch=1, session=None)
        assert r.store.remove(later).result(5).persisted
    assert token.operation_id not in r.store.snapshot()["operations"]
    before = r.store.snapshot()
    receipt = r.controller.request("select", "Alice", None, token)
    assert not receipt["pending"] and receipt["error"]
    assert receipt["operation_id"] == token.operation_id
    assert r.controller.picker is None
    assert r.store.snapshot() == before


def test_retained_canceled_command_does_not_open_a_picker(rig):
    r = rig()
    roster(r, 1, client())
    token = r.store.begin("Alice", epoch=1, session=client().session)
    assert r.store.cancel(token)
    receipt = r.controller.request("select", "Alice", None, token)
    assert not receipt["pending"] and not receipt["persisted"]
    assert r.controller.picker is None and not r.native.windows


def test_pruned_ingress_command_does_not_drop_later_host_batch_intent(rig):
    from wingman.preview.host import PreviewHost

    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    token = r.store.begin("Alice", epoch=1, session=client().session)
    latest = RosterSnapshot(2, ())
    r.store.observe_roster(1, latest)
    for index in range(33):
        later = r.store.begin(str(index), epoch=1, session=None)
        assert r.store.remove(later).result(5).persisted
    h = PreviewHost(on_layout_changed=lambda *args: None, crop_store=r.store)
    h._crop_controller = r.controller
    h._crop_epoch = 1
    h.apply_roster(latest)
    disable = r.store.begin("Alice", epoch=1, session=None)
    h._crop_commands = [
        ("select", "Alice", None, token),
        ("enabled", "Alice", False, disable),
    ]
    h._apply_crop_commands(None)
    finish(r)
    assert r.store.snapshot()["operations"][disable.operation_id]["persisted"]
    assert not deserialize(r.store.snapshot()["definitions"])["Alice"].enabled
    assert not r.controller.live and not r.controller.picker


def test_host_isolates_command_failure_and_terminalizes_unadmitted_intent(
    rig, monkeypatch, caplog
):
    from wingman.preview.host import PreviewHost

    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    h = PreviewHost(on_layout_changed=lambda *args: None, crop_store=r.store)
    h._crop_controller = r.controller
    first = r.store.begin("Alice", epoch=1, session=None)
    following = r.store.begin("Alice", epoch=1, session=None)
    h._crop_commands = [
        ("enabled", "Alice", False, first),
        ("remove", "Alice", None, following),
    ]
    original = r.controller.request

    def fail_first(action, name, value, token):
        if token == first:
            raise RuntimeError("command handler failed")
        return original(action, name, value, token)

    monkeypatch.setattr(r.controller, "request", fail_first)
    h._apply_crop_commands(None)
    finish(r)
    outcomes = r.store.snapshot()["operations"]
    assert not outcomes[first.operation_id]["pending"]
    assert not outcomes[first.operation_id]["persisted"]
    assert outcomes[following.operation_id]["persisted"]
    assert r.store.snapshot()["definitions"] == {}
    assert "command handler failed" in caplog.text


def test_repeated_enable_does_not_persist_untouched_monitor_rescue(rig):
    saved = replace(DEFINITION, window=Rect(5000, 5000, 320, 160))
    r = rig({"Alice": saved})
    roster(r, 1, client())
    window = r.controller.live["Alice"].window
    assert window.rect == Rect(1600, 920, 320, 160)
    for count in (1, 2):
        token, _ = request(r, "enabled", value=True)
        finish(r)
        assert r.controller.live["Alice"].window is window
        assert r.controller.live["Alice"].generation == token.generation
        assert deserialize(r.store.snapshot()["definitions"])["Alice"] == saved
        assert len(r.transaction.writes) == count
    assert r.native.next_thumbnail == 9001


@pytest.mark.parametrize(
    "phase", ["during-save", "after-publication", "after-completion"]
)
def test_repeated_enable_preserves_real_movement_from_monitor_rescue(rig, phase):
    r = rig({"Alice": replace(DEFINITION, window=Rect(5000, 5000, 320, 160))})
    roster(r, 1, client())
    window = r.controller.live["Alice"].window
    assert window.rect == Rect(1600, 920, 320, 160)
    r.transaction.release.clear()
    token, _ = request(r, "enabled", value=True)
    assert r.transaction.entered.wait(5)
    moved = Rect(450, 320, 320, 160)
    if phase == "during-save":
        window.move(moved)
    r.transaction.release.set()
    result = r.completions.get(timeout=5)
    assert result.persisted
    if phase == "after-publication":
        window.move(moved)
    r.controller.complete(result)
    if phase == "after-completion":
        window.move(moved)
    r.store.drain().result(5)
    assert r.controller.live["Alice"].window is window
    assert r.controller.live["Alice"].generation == token.generation
    assert deserialize(r.store.snapshot()["definitions"])["Alice"] == replace(
        DEFINITION, window=moved
    )
    assert r.native.next_thumbnail == 9001


def test_real_movement_back_to_rescue_position_is_persisted(rig):
    r = rig({"Alice": replace(DEFINITION, window=Rect(5000, 5000, 320, 160))})
    roster(r, 1, client())
    window = r.controller.live["Alice"].window
    rescued = window.rect
    request(r, "enabled", value=True)
    result = r.completions.get(timeout=5)
    window.move(Rect(450, 320, 320, 160))
    window.move(rescued)
    r.controller.complete(result)
    r.store.drain().result(5)
    assert r.controller.live["Alice"].window is window
    assert deserialize(r.store.snapshot()["definitions"])["Alice"].window == rescued


@pytest.mark.parametrize("phase", ["during-save", "after-publication"])
@pytest.mark.parametrize("fail", [False, True])
def test_repeated_enable_preserves_live_window_and_latest_geometry(rig, phase, fail):
    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    old = r.controller.live["Alice"].window
    r.transaction.release.clear()
    token, _ = request(r, "enabled", value=True)
    assert r.transaction.entered.wait(5)
    moved = Rect(450, 320, 320, 160)
    if phase == "during-save":
        old.move(moved)
    r.transaction.fail = fail
    r.transaction.release.set()
    result = r.completions.get(timeout=5)
    assert result.persisted is not fail
    r.transaction.fail = False
    if phase == "after-publication":
        old.move(moved)
    r.controller.complete(result)
    r.store.drain().result(5)
    assert r.controller.live["Alice"].window is old
    assert old.rect == moved
    state = r.store.snapshot()
    assert state["generations"]["Alice"] == (0 if fail else token.generation)
    assert deserialize(state["definitions"])["Alice"] == replace(
        DEFINITION, window=moved
    )
    # Future drags must use the newly committed generation too.
    later = Rect(510, 340, 400, 200)
    old.move(later)
    r.store.drain().result(5)
    assert deserialize(r.store.snapshot()["definitions"])["Alice"].window == later
    assert r.native.next_thumbnail == 9001 and r.native.peak == 1


def test_repeated_enable_publication_racing_move_survives_source_loss(rig, monkeypatch):
    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    old = r.controller.live["Alice"].window
    r.transaction.release.clear()
    request(r, "enabled", value=True)
    assert r.transaction.entered.wait(5)
    original = r.store.record_geometry
    results = []

    def publish_then_record(*args):
        if not results:
            r.transaction.release.set()
            results.append(r.completions.get(timeout=5))
        original(*args)

    monkeypatch.setattr(r.store, "record_geometry", publish_then_record)
    moved = Rect(450, 320, 320, 160)
    old.move(moved)
    roster(r, 2)
    r.controller.complete(results[0])
    r.store.drain().result(5)
    assert not r.controller.live
    assert deserialize(r.store.snapshot()["definitions"])["Alice"] == replace(
        DEFINITION, window=moved
    )


@pytest.mark.parametrize("ingress_phase", ["before-open", "after-open"])
def test_startup_seeds_newest_roster_across_epoch_open_gap(
    rig, monkeypatch, ingress_phase
):
    from wingman.preview.host import PreviewHost

    r = rig({"Alice": DEFINITION})
    h = PreviewHost(
        on_layout_changed=lambda *args: None,
        crop_store=r.store,
        excluded=lambda: ["Alice"],
    )
    h._crop_epoch = 1
    h.apply_roster(RosterSnapshot(1, (client(),)))
    opening, arrived = Event(), Event()
    latest = RosterSnapshot(2, (client(serial=2),))
    original_open = r.store.open_epoch

    def open_epoch(epoch):
        if ingress_phase == "after-open":
            original_open(epoch)
        opening.set()
        assert arrived.wait(5)
        if ingress_phase == "before-open":
            original_open(epoch)

    def ingress():
        assert opening.wait(5)
        h.apply_roster(latest)
        arrived.set()

    monkeypatch.setattr(r.store, "open_epoch", open_epoch)
    monkeypatch.setattr(h, "_monitors", lambda: [MONITOR])
    worker = Thread(target=ingress)
    worker.start()
    try:
        h._init_crop_controller(r.native.lib)
        h._apply_pending_roster(r.native.lib)
        assert h._crop_controller.sessions["Alice"] == latest.clients[0]
        stale = r.store.begin("Alice", epoch=h._crop_epoch, session=client().session)
        assert not r.store.put(stale, DEFINITION).result(5).persisted
        current = r.store.begin(
            "Alice", epoch=h._crop_epoch, session=client(serial=2).session
        )
        assert r.store.put(current, DEFINITION).result(5).persisted
    finally:
        worker.join(5)
        assert not worker.is_alive()
        if h._crop_controller is not None:
            h._crop_controller.begin_stop(h._crop_epoch).result(5)
            h._crop_controller.close_native()


@pytest.mark.parametrize("action,value", [("enabled", False), ("remove", None)])
@pytest.mark.parametrize("fail_later", [False, True])
def test_disable_remove_cancels_submitted_selection_before_admission(
    rig, action, value, fail_later
):
    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    old = r.controller.live["Alice"].window
    selecting, _ = request(r)
    with r.transaction.lock:
        confirm(r)
        assert r.transaction.attempted.wait(5)
        assert not r.transaction.entered.is_set()
        candidate = r.controller._temporary.candidate.window
        later, _ = request(r, action, value=value)
        assert candidate.hwnd is None
        assert old.hwnd is not None
        assert not r.store.snapshot()["operations"][selecting.operation_id]["pending"]
        r.transaction.fail = fail_later
    result = r.completions.get(timeout=5)
    assert result.token == selecting and not result.persisted
    r.controller.complete(result)
    result = r.completions.get(timeout=5)
    assert result.token == later and result.persisted is not fail_later
    r.transaction.fail = False
    r.controller.complete(result)
    r.store.drain().result(5)
    definitions = deserialize(r.store.snapshot()["definitions"])
    assert len(r.transaction.writes) == (0 if fail_later else 1)
    if fail_later:
        assert definitions["Alice"] == DEFINITION
        assert r.controller.live["Alice"].window is old
    elif action == "enabled":
        assert definitions["Alice"] == replace(DEFINITION, enabled=False)
        assert not r.controller.live
    else:
        assert definitions == {} and not r.controller.live
    assert r.native.peak == 2


@pytest.mark.parametrize("action,value", [("enabled", False), ("remove", None)])
@pytest.mark.parametrize("fail_later", [False, True])
def test_disable_remove_cannot_cancel_admitted_selection(
    rig, action, value, fail_later
):
    r = rig({"Alice": DEFINITION})
    roster(r, 1, client())
    selecting, _ = request(r)
    r.transaction.release.clear()
    confirm(r)
    assert r.transaction.entered.wait(5)
    candidate = r.controller._temporary.candidate.window
    later, _ = request(r, action, value=value)
    assert candidate.hwnd is not None
    assert r.store.snapshot()["operations"][selecting.operation_id]["pending"]
    r.transaction.release.set()
    result = r.completions.get(timeout=5)
    assert result.token == selecting and result.persisted
    replacement = deserialize(r.store.snapshot()["definitions"])["Alice"]
    assert replacement.source != DEFINITION.source
    assert r.store.snapshot()["operations"][later.operation_id]["pending"]
    r.transaction.fail = fail_later
    r.controller.complete(result)
    result = r.completions.get(timeout=5)
    assert result.token == later and result.persisted is not fail_later
    r.transaction.fail = False
    r.controller.complete(result)
    definitions = deserialize(r.store.snapshot()["definitions"])
    if fail_later:
        assert definitions["Alice"] == replacement
        assert r.controller.live["Alice"].window is candidate
    elif action == "enabled":
        assert definitions["Alice"] == replace(replacement, enabled=False)
    else:
        assert definitions == {}
    assert len(r.transaction.writes) == (1 if fail_later else 2)
    assert r.native.peak == 2


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
