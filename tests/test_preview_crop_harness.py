"""Fake-host tests for the prototype crop reconciliation loop.

Loaded via importlib, the same pattern tests/test_preview_crop_model.py and
tests/test_preview_crop_windows.py use: the module under test is a checkout
tool, not a package member, and is on no import path.

Nothing here creates a window. Both native controllers are injected as
recording factories, and `_reconcile_probe` is driven directly rather than
through `_sweep` -- real discovery needs a desktop with EVE running on it,
which is the smoke checklist's job, not pytest's. What IS exercised is
everything between: which clients are eligible, which crops are created,
closed and recreated, where activation is routed, and the order teardown
takes.
"""

import importlib.util
from pathlib import Path

import pytest

from wingman.preview import discovery
from wingman.preview import host as host_mod
from wingman.preview.geometry import Rect


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).parent / relative
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


harness = _load("preview_crop_harness", "manual/preview_crop_harness.py")
model = _load("preview_crop_model", "manual/preview_crop_model.py")


# A named client and one still at character select. discovery gives the
# second a synthetic "hwnd:0x..." stable key and no character at all --
# which is exactly what makes it ineligible for a crop, not a special case
# invented here.
NAMED = discovery.Client(0x10, "EVE - Alice", 101, "Alice", "Alice")
ANONYMOUS = discovery.Client(0x11, "EVE", 102, None, "hwnd:0x11")
OTHER = discovery.Client(0x12, "EVE - bob", 103, "bob", "bob")
THIRD = discovery.Client(0x13, "EVE - Carol", 104, "Carol", "Carol")

MONITOR = Rect(0, 0, 1920, 1080)
CLIENT_SIZE = (1280, 720)


# --- recording factories ---------------------------------------------------


class FakeCrop:
    """Stands in for PrototypeCropWindow with the three methods the host
    ever calls on one: close, set_hidden and set_locked. close() and
    set_hidden() are idempotent, like the real ones."""

    def __init__(self, client, source_rect, rect, on_activate, locked, events):
        self.client = client
        self.source_rect = source_rect
        self.rect = rect
        self.on_activate = on_activate
        self.locked = locked
        self.hidden = False
        self.closed = False
        self.close_calls = 0
        self._events = events

    def close(self):
        self.close_calls += 1
        if self.closed:
            return
        self.closed = True
        self._events.append(("crop-close", self.client.stable_key))

    def set_hidden(self, hidden):
        self.hidden = bool(hidden)

    def set_locked(self, locked):
        self.locked = bool(locked)


class CropCall:
    def __init__(self, libs, client, source_rect, rect, on_activate, locked):
        self.libs = libs
        self.client = client
        self.source_rect = source_rect
        self.rect = rect
        self.on_activate = on_activate
        self.locked = locked


class RecordingCropFactory:
    """`create` appends its arguments and hands back a FakeCrop -- or None
    for any stable key in *fails*, which is how a real factory reports a
    CreateWindowExW or DWM failure."""

    def __init__(self, fails=(), events=None):
        self.calls = []
        self.created = []
        self.fails = set(fails)
        self.events = [] if events is None else events

    def create(self, libs, client, source_rect, rect, on_activate, locked=False):
        self.calls.append(
            CropCall(libs, client, source_rect, rect, on_activate, locked)
        )
        if client.stable_key in self.fails:
            return None
        crop = FakeCrop(client, source_rect, rect, on_activate, locked, self.events)
        self.created.append(crop)
        return crop

    def __call__(self, *args, **kwargs):
        return self.create(*args, **kwargs)


class FakePicker:
    """Stands in for PrototypeCropPicker, including its callback-once
    contract: confirm and cancel share one `_completed` latch, so a host
    cancelling a picker the user already confirmed changes nothing."""

    def __init__(self, client, on_confirm, on_cancel, events):
        self.client = client
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel
        self._events = events
        self.completed = False
        self.reasons = []

    def confirm(self, source_rect):
        if self.completed:
            return
        self.completed = True
        self._events.append(("picker-confirm", self.client.stable_key))
        self._on_confirm(self.client, source_rect)

    def cancel(self, reason="host-cancelled"):
        if self.completed:
            return
        self.completed = True
        self.reasons.append(reason)
        self._events.append(("picker-cancel", reason))
        self._on_cancel(reason)


class PickerCall:
    def __init__(self, libs, client, monitor, on_confirm, on_cancel):
        self.libs = libs
        self.client = client
        self.monitor = monitor
        self.on_confirm = on_confirm
        self.on_cancel = on_cancel


class RecordingPickerFactory:
    def __init__(self, fails=(), events=None):
        self.calls = []
        self.created = []
        self.fails = set(fails)
        self.events = [] if events is None else events

    def create(self, libs, client, monitor, on_confirm, on_cancel):
        self.calls.append(PickerCall(libs, client, monitor, on_confirm, on_cancel))
        if client.stable_key in self.fails:
            return None
        picker = FakePicker(client, on_confirm, on_cancel, self.events)
        self.created.append(picker)
        return picker

    def __call__(self, *args, **kwargs):
        return self.create(*args, **kwargs)


# --- fake natives ----------------------------------------------------------


class FakeUser32:
    def __init__(self, client_rects):
        self.client_rects = client_rects

    def GetClientRect(self, hwnd, ptr):
        rect = self.client_rects.get(int(hwnd), (0, 0, *CLIENT_SIZE))
        if rect is None:
            return False
        ptr._obj.left, ptr._obj.top, ptr._obj.right, ptr._obj.bottom = rect
        return True


class FakeLibs:
    """Only GetClientRect: the prototype host itself makes no other native
    call. Everything else it would touch belongs to the injected factories
    or to the base host, which these tests drive directly."""

    def __init__(self, client_rects=None):
        self.user32 = FakeUser32(dict(client_rects or {}))


def make_host(character=None, crop_factory=None, picker_factory=None, **kwargs):
    host = harness.PrototypePreviewHost(
        character=character,
        crop_factory=(
            crop_factory if crop_factory is not None else RecordingCropFactory()
        ),
        picker_factory=(
            picker_factory if picker_factory is not None else RecordingPickerFactory()
        ),
        **kwargs,
    )
    # The two display reads the probe makes. Both call win32.bind() on the
    # real host, which does not exist off Windows at all -- the same wall
    # tests/test_preview_crop_windows.py documents for window creation.
    host._monitors = lambda: [MONITOR]
    host._screen = lambda: MONITOR
    return host


def set_clients(host, *clients):
    host._clients = {client.stable_key: client for client in clients}


# --- interactive picker ----------------------------------------------------


def test_interactive_probe_rejects_anonymous_clients():
    """A client at character select has no character to own a crop, and
    borrowing the previous one's is exactly what the design forbids."""
    picker_factory = RecordingPickerFactory()
    host = make_host(character="Alice", picker_factory=picker_factory)
    set_clients(host, ANONYMOUS)
    host._reconcile_probe(FakeLibs())
    assert picker_factory.calls == []


def test_a_rejected_anonymous_sweep_still_opens_the_picker_later():
    """The rejection above must not consume the one attempt: the client
    that is at character select now is usually the one that logs in a
    moment later."""
    picker_factory = RecordingPickerFactory()
    host = make_host(character="Alice", picker_factory=picker_factory)
    set_clients(host, ANONYMOUS)
    host._reconcile_probe(FakeLibs())
    set_clients(host, NAMED)
    host._reconcile_probe(FakeLibs())
    assert [call.client for call in picker_factory.calls] == [NAMED]


def test_one_picker_opens_for_a_named_character():
    picker_factory = RecordingPickerFactory()
    host = make_host(character="Alice", picker_factory=picker_factory)
    set_clients(host, NAMED)
    host._reconcile_probe(FakeLibs())
    host._reconcile_probe(FakeLibs())
    assert len(picker_factory.calls) == 1
    assert picker_factory.calls[0].client == NAMED
    assert picker_factory.calls[0].monitor == MONITOR
    assert host.probe_status()["picker_open"] is True


def test_cancel_does_not_reopen_picker_on_every_sweep():
    picker_factory = RecordingPickerFactory()
    host = make_host(character="Alice", picker_factory=picker_factory)
    host._clients = {NAMED.stable_key: NAMED}
    host._reconcile_probe(FakeLibs())
    picker_factory.created[0].cancel("user-cancelled")
    host._reconcile_probe(FakeLibs())
    assert len(picker_factory.calls) == 1


def test_confirm_creates_exactly_one_crop_with_the_selected_source():
    crop_factory = RecordingCropFactory()
    picker_factory = RecordingPickerFactory()
    host = make_host(
        character="Alice", crop_factory=crop_factory, picker_factory=picker_factory
    )
    set_clients(host, NAMED)
    host._reconcile_probe(FakeLibs())
    picker_factory.created[0].confirm(Rect(100, 50, 400, 200))

    assert len(crop_factory.calls) == 1
    assert crop_factory.calls[0].source_rect == Rect(100, 50, 400, 200)
    assert crop_factory.calls[0].client == NAMED
    assert host.probe_status()["crops"] == ["Alice"]
    assert host.probe_status()["picker_open"] is False


def test_confirm_against_a_client_that_moved_on_creates_nothing():
    """The picker's client record is as old as the picker. A confirmation
    must be re-resolved against the CURRENT registry, or the crop mirrors
    an HWND that belongs to a different process by the time it opens."""
    crop_factory = RecordingCropFactory()
    picker_factory = RecordingPickerFactory()
    host = make_host(
        character="Alice", crop_factory=crop_factory, picker_factory=picker_factory
    )
    set_clients(host, NAMED)
    host._reconcile_probe(FakeLibs())
    set_clients(host, NAMED._replace(hwnd=0x20, pid=202))
    picker_factory.created[0].confirm(Rect(100, 50, 400, 200))
    assert crop_factory.calls == []


def test_a_picker_is_cancelled_when_its_client_disappears():
    picker_factory = RecordingPickerFactory()
    host = make_host(character="Alice", picker_factory=picker_factory)
    set_clients(host, NAMED)
    host._reconcile_probe(FakeLibs())
    set_clients(host)
    host._reconcile_probe(FakeLibs())
    assert picker_factory.created[0].reasons == ["client-lost"]
    assert host.probe_status()["picker_open"] is False


def test_a_failed_picker_is_not_retried_every_sweep():
    picker_factory = RecordingPickerFactory(fails={"Alice"})
    host = make_host(character="Alice", picker_factory=picker_factory)
    set_clients(host, NAMED)
    host._reconcile_probe(FakeLibs())
    host._reconcile_probe(FakeLibs())
    assert len(picker_factory.calls) == 1
    assert [f["reason"] for f in host.probe_status()["failures"]] == ["picker-failed"]


# --- load staging ----------------------------------------------------------


def test_only_stages_1_2_4_and_8_are_accepted():
    host = make_host()
    for stage in (1, 2, 4, 8):
        host.set_probe_count(stage)
        assert host.probe_status()["requested"] == stage


@pytest.mark.parametrize("count", [-1, 0, 3, 5, 6, 7, 9, 16])
def test_every_other_stage_is_rejected(count):
    host = make_host()
    with pytest.raises(ValueError):
        host.set_probe_count(count)
    assert host.probe_status()["requested"] == 0


def test_the_desired_count_is_stored_before_the_host_window_exists():
    """set_probe_count is called by the CLI before the pump has created
    its message-only window. request_sweep is a no-op until then, so the
    stored intent is the only thing that carries the request across."""
    host = make_host()
    assert host._hwnd is None
    host.set_probe_count(4)
    assert host.probe_status()["requested"] == 4


def test_a_load_stage_creates_the_central_half_of_the_current_client():
    crop_factory = RecordingCropFactory()
    host = make_host(crop_factory=crop_factory)
    host.set_probe_count(1)
    set_clients(host, NAMED)
    host._reconcile_probe(FakeLibs())

    call = crop_factory.calls[0]
    assert call.source_rect == model.central_source(CLIENT_SIZE)
    expected_size = model.fit_within(
        (call.source_rect.w, call.source_rect.h), harness.PROBE_SIZE_MAX
    )
    assert call.rect == model.stack_from_bottom_right(0, MONITOR, expected_size)


def test_named_clients_are_staged_in_case_insensitive_order():
    """'bob' before 'Carol'. A plain sort puts every capital first, which
    would stage a lowercase character last however many clients are up."""
    crop_factory = RecordingCropFactory()
    host = make_host(crop_factory=crop_factory)
    host.set_probe_count(2)
    set_clients(host, THIRD, OTHER, NAMED)
    host._reconcile_probe(FakeLibs())
    assert [call.client.stable_key for call in crop_factory.calls] == ["Alice", "bob"]


def test_an_anonymous_client_never_occupies_a_load_slot():
    crop_factory = RecordingCropFactory()
    host = make_host(crop_factory=crop_factory)
    host.set_probe_count(2)
    set_clients(host, ANONYMOUS, NAMED)
    host._reconcile_probe(FakeLibs())
    assert [call.client.stable_key for call in crop_factory.calls] == ["Alice"]


def test_a_decreased_stage_closes_the_excess_crops():
    crop_factory = RecordingCropFactory()
    host = make_host(crop_factory=crop_factory)
    host.set_probe_count(2)
    set_clients(host, NAMED, OTHER)
    host._reconcile_probe(FakeLibs())
    host.set_probe_count(1)
    host._reconcile_probe(FakeLibs())

    assert host.probe_status()["crops"] == ["Alice"]
    closed = [crop.client.stable_key for crop in crop_factory.created if crop.closed]
    assert closed == ["bob"]


def test_a_kept_crop_is_not_recreated_on_the_next_sweep():
    """Re-registering a live thumbnail every 700ms is a visible flicker --
    the same reason the primary registry reconciles rather than rebuilds."""
    crop_factory = RecordingCropFactory()
    host = make_host(crop_factory=crop_factory)
    host.set_probe_count(1)
    set_clients(host, NAMED)
    host._reconcile_probe(FakeLibs())
    host._reconcile_probe(FakeLibs())
    assert len(crop_factory.calls) == 1
    assert crop_factory.created[0].closed is False


def test_logout_closes_the_crop():
    crop_factory = RecordingCropFactory()
    host = make_host(crop_factory=crop_factory)
    host.set_probe_count(1)
    set_clients(host, NAMED)
    host._reconcile_probe(FakeLibs())
    # The same physical client, now at character select: a new stable key
    # and no character, which is a logout as far as identity is concerned.
    set_clients(host, discovery.Client(0x10, "EVE", 101, None, "hwnd:0x10"))
    host._reconcile_probe(FakeLibs())
    assert crop_factory.created[0].closed is True
    assert host.probe_status()["crops"] == []


def test_same_character_new_hwnd_and_pid_recreates_crop():
    crop_factory = RecordingCropFactory()
    host = make_host(crop_factory=crop_factory)
    host.set_probe_count(1)
    host._clients = {NAMED.stable_key: NAMED}
    host._reconcile_probe(FakeLibs())
    replacement = NAMED._replace(hwnd=0x20, pid=202)
    host._clients = {replacement.stable_key: replacement}
    host._reconcile_probe(FakeLibs())
    assert crop_factory.created[0].closed is True
    assert [call.client.hwnd for call in crop_factory.calls] == [0x10, 0x20]


def test_a_confirmed_crop_returns_on_a_new_process_with_its_own_source():
    """The interactive selection is the user's, and there is nothing to
    recompute it from -- so it is retained in memory and replayed onto the
    replacement client rather than falling back to the central half."""
    crop_factory = RecordingCropFactory()
    picker_factory = RecordingPickerFactory()
    host = make_host(
        character="Alice", crop_factory=crop_factory, picker_factory=picker_factory
    )
    set_clients(host, NAMED)
    host._reconcile_probe(FakeLibs())
    picker_factory.created[0].confirm(Rect(100, 50, 400, 200))
    first = crop_factory.calls[0]

    set_clients(host)
    host._reconcile_probe(FakeLibs())
    assert crop_factory.created[0].closed is True

    set_clients(host, NAMED._replace(hwnd=0x20, pid=202))
    host._reconcile_probe(FakeLibs())
    second = crop_factory.calls[1]
    assert second.client.hwnd == 0x20
    assert (second.source_rect, second.rect) == (first.source_rect, first.rect)


def test_a_failed_crop_is_recorded_once_and_not_retried_every_sweep():
    crop_factory = RecordingCropFactory(fails={"Alice"})
    host = make_host(crop_factory=crop_factory)
    host.set_probe_count(1)
    set_clients(host, NAMED)
    host._reconcile_probe(FakeLibs())
    host._reconcile_probe(FakeLibs())

    assert len(crop_factory.calls) == 1
    failures = host.probe_status()["failures"]
    assert [(f["stable_key"], f["reason"]) for f in failures] == [
        ("Alice", "crop-failed")
    ]


def test_an_explicit_stage_request_clears_recorded_failures():
    """The design forbids retrying a failed crop every 700ms and allows it
    on an explicit user action. Asking for a stage again is that action."""
    crop_factory = RecordingCropFactory(fails={"Alice"})
    host = make_host(crop_factory=crop_factory)
    host.set_probe_count(1)
    set_clients(host, NAMED)
    host._reconcile_probe(FakeLibs())
    host.set_probe_count(1)
    host._reconcile_probe(FakeLibs())
    assert len(crop_factory.calls) == 2
    assert len(host.probe_status()["failures"]) == 1


def test_an_unreadable_client_rect_is_a_recorded_failure_not_a_crash():
    crop_factory = RecordingCropFactory()
    host = make_host(crop_factory=crop_factory)
    host.set_probe_count(1)
    set_clients(host, NAMED)
    host._reconcile_probe(FakeLibs(client_rects={NAMED.hwnd: None}))
    assert crop_factory.calls == []
    assert [f["reason"] for f in host.probe_status()["failures"]] == ["client-size"]


# --- activation, visibility and lock ---------------------------------------


def test_a_crop_click_activates_through_the_inherited_coordinator():
    """The prototype never touches SetForegroundWindow: activation policy,
    the pending-switch retry and the minimize decision all live in the
    base host, and a probe that reimplemented them would prove nothing
    about the real one."""
    crop_factory = RecordingCropFactory()
    host = make_host(crop_factory=crop_factory)
    host.set_probe_count(1)
    set_clients(host, NAMED)
    libs = FakeLibs()
    activated = []
    host._activate_client = lambda passed_libs, client: activated.append(
        (passed_libs, client)
    )
    host._reconcile_probe(libs)
    crop_factory.calls[0].on_activate(NAMED)
    assert activated == [(libs, NAMED)]


def test_hidden_previews_hide_every_crop():
    crop_factory = RecordingCropFactory()
    host = make_host(crop_factory=crop_factory)
    host.set_probe_count(1)
    set_clients(host, NAMED)
    host._reconcile_probe(FakeLibs())
    host._hide_on_lost_focus = lambda: True
    host._foreground_is_ours = lambda libs, foreground: False

    host._apply_visibility(None, 0x9999)
    assert crop_factory.created[0].hidden is True
    host._foreground_is_ours = lambda libs, foreground: True
    host._apply_visibility(None, 0x9999)
    assert crop_factory.created[0].hidden is False


def test_a_crop_created_while_previews_are_hidden_is_born_hidden():
    """The base host re-applies visibility every sweep for exactly this
    case. A crop is created AFTER that pass, so it has to be told."""
    crop_factory = RecordingCropFactory()
    host = make_host(crop_factory=crop_factory)
    host.set_probe_count(1)
    set_clients(host, NAMED)
    host._previews_hidden = True
    host._reconcile_probe(FakeLibs())
    assert crop_factory.created[0].hidden is True


def test_a_crop_opens_and_restyles_with_the_characters_lock():
    crop_factory = RecordingCropFactory()
    locked = ["Alice"]
    host = make_host(crop_factory=crop_factory, locked=lambda: list(locked))
    host.set_probe_count(1)
    set_clients(host, NAMED)
    host._reconcile_probe(FakeLibs())
    assert crop_factory.created[0].locked is True

    locked.clear()
    host._restyle(None)
    assert crop_factory.created[0].locked is False


# --- teardown --------------------------------------------------------------


def test_teardown_closes_the_picker_and_crops_before_the_base_teardown(monkeypatch):
    """Ordering, not merely closure: the base teardown destroys the host
    window and ends the pump, and a crop closed after that is a DWM
    relationship unwound with nothing pumping for it."""
    events = []
    crop_factory = RecordingCropFactory(events=events)
    picker_factory = RecordingPickerFactory(events=events)
    host = make_host(
        character="Carol", crop_factory=crop_factory, picker_factory=picker_factory
    )
    host.set_probe_count(1)
    set_clients(host, NAMED, THIRD)
    host._reconcile_probe(FakeLibs())
    assert crop_factory.created and picker_factory.created

    monkeypatch.setattr(
        host_mod.PreviewHost, "_teardown", lambda self, libs: events.append(("base",))
    )
    host._teardown(FakeLibs())

    assert events[-1] == ("base",)
    assert events.index(("picker-cancel", "host-teardown")) < events.index(("base",))
    assert ("crop-close", "Alice") in events[: events.index(("base",))]
    assert host.probe_status()["crops"] == []
    assert host.probe_status()["picker_open"] is False


def test_teardown_is_safe_with_no_picker_and_no_crops(monkeypatch):
    events = []
    host = make_host()
    monkeypatch.setattr(
        host_mod.PreviewHost, "_teardown", lambda self, libs: events.append(("base",))
    )
    host._teardown(FakeLibs())
    assert events == [("base",)]


# --- public surface --------------------------------------------------------


def test_wait_ready_reports_the_inherited_pump_readiness():
    host = make_host()
    assert host.wait_ready(0.01) is False
    host._ready.set()
    assert host.wait_ready(0.01) is True


def test_probe_status_reports_the_characters_currently_discovered():
    host = make_host()
    set_clients(host, NAMED, ANONYMOUS)
    assert host.probe_status()["clients"] == ["Alice"]


def test_the_prototype_persists_nothing():
    """No settings callbacks at all: the probe is ephemeral by design, and
    a layout write from it would edit the real user's settings file."""
    host = make_host()
    host._layout_changed("Alice", Rect(0, 0, 10, 10), False)
    assert host._flush_layouts is None
    assert host._replace_layout is None
    assert host._clear_layouts is None
