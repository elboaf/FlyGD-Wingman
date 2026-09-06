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

The last section covers the checkout-only CLI. It never reaches Windows
either: the platform check, the single-instance refusal, DPI awareness and
the host itself are all driven through the module's own seams, so the same
tests run on the Linux and Windows CI jobs and neither one opens a window.
"""

import importlib.util
import subprocess
import sys
import textwrap
import types
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


def count_display_reads(host):
    """Replace the two display reads with counting stand-ins and hand back
    the counters. Both are native enumerations on Windows -- EnumDisplay
    Monitors and a run of GetSystemMetrics -- so how many times one
    reconciliation performs them is a fact worth pinning, not an
    implementation detail."""
    reads = {"monitors": 0, "screen": 0}

    def monitors():
        reads["monitors"] += 1
        return [MONITOR]

    def screen():
        reads["screen"] += 1
        return MONITOR

    host._monitors = monitors
    host._screen = screen
    return reads


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


def test_one_display_enumeration_serves_the_picker_and_the_staged_crops():
    """A `pick` character and a load stage in the same reconciliation used
    to read the display twice for one answer -- once for the picker and
    once for the crop batch. The hardware cannot change between the two,
    and a failed enumeration logs a line each time it is asked."""
    crop_factory = RecordingCropFactory()
    picker_factory = RecordingPickerFactory()
    host = make_host(
        character="Carol", crop_factory=crop_factory, picker_factory=picker_factory
    )
    host.set_probe_count(2)
    set_clients(host, NAMED, OTHER, THIRD)
    reads = count_display_reads(host)
    host._reconcile_probe(FakeLibs())

    assert len(picker_factory.calls) == 1
    assert len(crop_factory.calls) == 2
    assert reads == {"monitors": 1, "screen": 1}
    # The one resolved display reached both paths, not just the crops.
    assert picker_factory.calls[0].monitor == MONITOR


def test_a_reconciliation_with_nothing_to_create_reads_no_display():
    """The steady state is every 700ms with nothing to do. Enumerating the
    displays there would be a native call per sweep for an answer nothing
    consumes."""
    host = make_host()
    set_clients(host, NAMED)
    reads = count_display_reads(host)
    host._reconcile_probe(FakeLibs())
    assert reads == {"monitors": 0, "screen": 0}


def test_a_cancelled_picker_needs_no_display_read():
    """Ending an open picker whose client vanished must not wait on an
    enumeration: there is nothing left to place."""
    picker_factory = RecordingPickerFactory()
    host = make_host(character="Alice", picker_factory=picker_factory)
    set_clients(host, NAMED)
    host._reconcile_probe(FakeLibs())
    set_clients(host)
    reads = count_display_reads(host)
    host._reconcile_probe(FakeLibs())
    assert picker_factory.created[0].reasons == ["client-lost"]
    assert reads == {"monitors": 0, "screen": 0}


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


def test_a_client_too_small_to_crop_is_a_recorded_failure_not_a_window():
    """A 1x1 client area has a 0x0 central half, so the staged destination
    rounds to nothing. That is a recorded client-size failure like an
    unreadable rect: a zero-sized layered window would be a DWM
    relationship nothing can be seen through, and it must not be retried
    on every sweep either."""
    crop_factory = RecordingCropFactory()
    host = make_host(crop_factory=crop_factory)
    host.set_probe_count(1)
    set_clients(host, NAMED)
    libs = FakeLibs(client_rects={NAMED.hwnd: (0, 0, 1, 1)})
    host._reconcile_probe(libs)
    host._reconcile_probe(libs)
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


# --- the checkout-only CLI -------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
HARNESS_PATH = ROOT / "tests" / "manual" / "preview_crop_harness.py"
OPT_IN = "--i-understand-this-is-an-ephemeral-windows-probe"


class FakeProbeHost:
    """Stands in for PrototypePreviewHost over a whole CLI run.

    Only the four methods the CLI is allowed to call: start, wait_ready,
    set_probe_count, probe_status and stop. Anything else the CLI reached
    for would fail here, which is the point -- the probe's contract with
    the host is exactly this surface.
    """

    def __init__(self, clients=("Alice",), ready=True, failures_at=None, live_at=None):
        self.character = None
        self.ready = ready
        self.clients = list(clients)
        self._failures_at = dict(failures_at or {})
        self._live_at = dict(live_at or {})
        self.events = []
        self.requested = 0
        self.started = 0
        self.stopped = 0
        self.wait_timeouts = []

    def start(self):
        self.started += 1
        self.events.append(("start",))

    def wait_ready(self, timeout):
        self.wait_timeouts.append(timeout)
        return self.ready

    def set_probe_count(self, count):
        stage = model.validated_stage(count)
        self.requested = stage
        self.events.append(("stage", stage))
        return stage

    def probe_status(self):
        live = self._live_at.get(self.requested, min(self.requested, len(self.clients)))
        return {
            "character": self.character,
            "requested": self.requested,
            "live": live,
            "crops": self.clients[:live],
            "picker_open": False,
            "failures": list(self._failures_at.get(self.requested, ())),
            "clients": list(self.clients),
        }

    def stop(self):
        self.stopped += 1
        self.events.append(("stop",))


def run_cli(
    monkeypatch,
    argv,
    *,
    host=None,
    single_instance=object(),
    platform="win32",
    console=True,
):
    """Drive harness.main() with every Windows seam replaced.

    `host=None` means "this run must refuse before a host exists": the
    factory raises rather than returning one, and main() does not catch
    AssertionError, so a CLI that constructed a host anyway fails loudly
    instead of quietly passing.
    """
    monkeypatch.setattr(harness.sys, "platform", platform)
    monkeypatch.setattr(harness, "_acquire_single_instance", lambda: single_instance)
    dpi_calls = []
    monkeypatch.setattr(harness, "_set_dpi_awareness", lambda: dpi_calls.append(True))

    built = []

    def factory(**kwargs):
        built.append(kwargs)
        if host is None:
            raise AssertionError("the CLI constructed a host it should have refused")
        # Recorded on the fake so probe_status can report it, exactly as
        # the real host stores the requested character.
        host.character = kwargs.get("character")
        host.events.append(("construct",))
        return host

    monkeypatch.setattr(harness, "PrototypePreviewHost", factory)

    presses = []

    def fake_input(*_args):
        presses.append(True)
        if not console:
            raise EOFError
        return ""

    monkeypatch.setattr("builtins.input", fake_input)
    code = harness.main(argv)
    return types.SimpleNamespace(
        code=code, built=built, dpi_calls=dpi_calls, presses=presses
    )


# -- parsing ----------------------------------------------------------------


def test_parser_exposes_pick_and_load():
    args = harness.build_parser().parse_args(["pick", "--character", "Alice", OPT_IN])
    assert args.command == "pick"
    assert args.character == "Alice"
    assert args.handler is harness._run_pick

    args = harness.build_parser().parse_args(["load", OPT_IN])
    assert args.command == "load"
    assert args.handler is harness._run_load


@pytest.mark.parametrize(
    "argv",
    [
        ["pick", "--character", "Alice"],
        ["load"],
    ],
)
def test_both_commands_require_the_acknowledgement(argv):
    with pytest.raises(SystemExit):
        harness.build_parser().parse_args(argv)


def test_abbreviated_acknowledgement_is_rejected():
    """allow_abbrev=False on every parser. The flag is long precisely so
    that it cannot be typed by accident, which a prefix match would undo."""
    with pytest.raises(SystemExit):
        harness.build_parser().parse_args(
            ["load", "--i-understand-this-is-an-ephemeral-windows"]
        )


def test_an_abbreviated_option_is_rejected_too():
    with pytest.raises(SystemExit):
        harness.build_parser().parse_args(["pick", "--charac", "Alice", OPT_IN])


def test_pick_requires_a_character():
    with pytest.raises(SystemExit):
        harness.build_parser().parse_args(["pick", OPT_IN])


@pytest.mark.parametrize("argv", [[], ["probe", OPT_IN]])
def test_an_unknown_or_missing_command_is_rejected(argv):
    with pytest.raises(SystemExit):
        harness.build_parser().parse_args(argv)


def test_the_staged_counts_are_the_models_valid_stages():
    """Derived, not retyped: the pure model owns which counts exist, and
    the ceiling is the probe guard the host already enforces."""
    for stage in harness.PROBE_STAGES:
        assert model.validated_stage(stage) == stage
    assert max(harness.PROBE_STAGES) == harness.PROBE_MAX


# -- import inertness -------------------------------------------------------


def test_importing_the_harness_starts_nothing_and_parses_nothing():
    """A module that parsed argv or started a pump at import would act on
    a stray sys.argv -- including the test runner's own. The subprocess
    gives it a fully valid `pick` argv to act on, so a module that did
    would be caught rather than merely unproven."""
    probe = textwrap.dedent(
        """
        import importlib.util
        import sys
        import threading

        path = sys.argv[1]
        sys.argv = [
            "preview_crop_harness",
            "pick",
            "--character",
            "Alice",
            "--i-understand-this-is-an-ephemeral-windows-probe",
        ]
        before = threading.active_count()
        spec = importlib.util.spec_from_file_location("preview_crop_harness", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert threading.active_count() == before, "the import started a thread"
        assert "wingman.__main__" not in sys.modules, "the import pulled in the app"
        print("inert")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", probe, str(HARNESS_PATH)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "inert"


def test_importing_the_harness_binds_no_native_library(monkeypatch):
    """win32.bind() is the module's only route to a native handle, and the
    same Linux-import constraint the two controllers document applies
    here: nothing native may happen before a subcommand is parsed."""

    def explode():
        raise AssertionError("the import bound the native libraries")

    monkeypatch.setattr(harness.win32, "bind", explode)
    _load("preview_crop_harness_reimport", "manual/preview_crop_harness.py")


# -- refusals ---------------------------------------------------------------


@pytest.mark.parametrize(
    "argv", [["pick", "--character", "Alice", OPT_IN], ["load", OPT_IN]]
)
def test_a_non_windows_run_refuses_before_constructing_a_host(
    monkeypatch, capsys, argv
):
    result = run_cli(monkeypatch, argv, host=None, platform="linux")
    assert result.code == 1
    assert result.built == []
    assert result.dpi_calls == []
    err = capsys.readouterr().err
    assert err.startswith("crop probe failure: ")
    assert "Windows" in err


@pytest.mark.parametrize(
    "argv", [["pick", "--character", "Alice", OPT_IN], ["load", OPT_IN]]
)
def test_a_running_wingman_refuses_before_constructing_a_host(
    monkeypatch, capsys, argv
):
    """Two hosts on one desktop would discover the same clients and hold
    two DWM relationships each, and the installed app owns the real
    settings file this probe must never touch."""
    result = run_cli(monkeypatch, argv, host=None, single_instance=None)
    assert result.code == 1
    assert result.built == []
    err = capsys.readouterr().err
    assert err.startswith("crop probe failure: ")
    assert "Wingman" in err


def test_a_console_that_cannot_be_read_is_a_refusal_not_a_traceback(
    monkeypatch, capsys
):
    host = FakeProbeHost()
    result = run_cli(
        monkeypatch,
        ["pick", "--character", "Alice", OPT_IN],
        host=host,
        console=False,
    )
    assert result.code == 1
    assert host.stopped == 1  # the finally still ran
    assert "crop probe failure: " in capsys.readouterr().err


def test_an_oserror_from_the_host_is_reported_and_returns_one(monkeypatch, capsys):
    host = FakeProbeHost()

    def explode():
        raise OSError("RegisterClassW failed")

    monkeypatch.setattr(host, "start", explode)
    result = run_cli(monkeypatch, ["pick", "--character", "Alice", OPT_IN], host=host)
    assert result.code == 1
    assert host.stopped == 1
    assert "crop probe failure: RegisterClassW failed" in capsys.readouterr().err


def test_ctrl_c_ends_the_run_at_130_with_no_traceback(monkeypatch, capsys):
    """Ctrl+C is a documented way to end a probe run, so it is an ordinary
    exit: the host still stops through the context manager's finally, the
    operator gets one line rather than a traceback that looks like an
    unclean teardown, and 130 is the shell's own SIGINT convention."""
    host = FakeProbeHost()

    def interrupt(*_args):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", interrupt)
    monkeypatch.setattr(harness.sys, "platform", "win32")
    monkeypatch.setattr(harness, "_acquire_single_instance", lambda: object())
    monkeypatch.setattr(harness, "_set_dpi_awareness", lambda: None)
    monkeypatch.setattr(harness, "PrototypePreviewHost", lambda **_kwargs: host)

    assert harness.main(["pick", "--character", "Alice", OPT_IN]) == 130
    assert host.stopped == 1
    captured = capsys.readouterr()
    assert captured.err.strip() == "crop probe interrupted"
    assert "Traceback" not in captured.err


# -- one host lifecycle -----------------------------------------------------


def test_the_probe_starts_exactly_one_host_and_always_stops_it(monkeypatch):
    host = FakeProbeHost()
    result = run_cli(monkeypatch, ["pick", "--character", "Alice", OPT_IN], host=host)
    assert result.code == 0
    assert len(result.built) == 1
    assert host.started == 1
    assert host.stopped == 1
    assert host.events[0] == ("construct",)
    assert host.events[-1] == ("stop",)


def test_dpi_awareness_is_set_before_the_host_is_constructed(monkeypatch):
    """The host's windows are placed in physical pixels the moment the
    pump starts, so a process that became DPI-aware afterwards would
    measure a scaled desktop it no longer has."""
    order = []
    monkeypatch.setattr(harness.sys, "platform", "win32")
    monkeypatch.setattr(harness, "_acquire_single_instance", lambda: object())
    monkeypatch.setattr(harness, "_set_dpi_awareness", lambda: order.append("dpi"))

    host = FakeProbeHost()

    def factory(**kwargs):
        order.append("host")
        host.character = kwargs.get("character")
        return host

    monkeypatch.setattr(harness, "PrototypePreviewHost", factory)
    monkeypatch.setattr("builtins.input", lambda *_: "")
    assert harness.main(["pick", "--character", "Alice", OPT_IN]) == 0
    assert order == ["dpi", "host"]


def test_the_probe_persists_nothing_through_the_cli(monkeypatch):
    """No settings callbacks cross the CLI at all -- the only keyword it
    passes is the character the picker waits for."""
    host = FakeProbeHost()
    result = run_cli(monkeypatch, ["pick", "--character", "Alice", OPT_IN], host=host)
    assert result.built == [{"character": "Alice"}]


def test_a_host_that_never_becomes_ready_is_stopped_and_reported(monkeypatch, capsys):
    host = FakeProbeHost(ready=False)
    result = run_cli(monkeypatch, ["load", OPT_IN], host=host)
    assert result.code == 1
    assert host.stopped == 1
    assert host.wait_timeouts == [harness.READY_TIMEOUT_S]
    assert "crop probe failure: " in capsys.readouterr().err


# -- pick -------------------------------------------------------------------


def test_pick_prints_both_control_grammars_and_waits_for_enter(monkeypatch, capsys):
    host = FakeProbeHost()
    result = run_cli(monkeypatch, ["pick", "--character", "Alice", OPT_IN], host=host)
    out = capsys.readouterr().out
    assert result.code == 0
    assert result.presses == [True]
    for phrase in (
        "left drag selects",
        "Enter confirms",
        "Escape cancels",
        "left click activates",
        "left drag moves",
        "right drag resizes",
    ):
        assert phrase in out, phrase
    assert "Alice" in out


# -- load -------------------------------------------------------------------


def test_load_refuses_when_no_named_client_is_running(monkeypatch, capsys):
    host = FakeProbeHost(clients=())
    result = run_cli(monkeypatch, ["load", OPT_IN], host=host)
    assert result.code == 1
    assert ("stage", 1) not in host.events
    assert host.stopped == 1
    assert "crop probe failure: " in capsys.readouterr().err


def test_load_walks_every_stage_and_waits_between_them(monkeypatch, capsys):
    host = FakeProbeHost(clients=("A", "B", "C", "D", "E", "F", "G", "H"))
    result = run_cli(monkeypatch, ["load", OPT_IN], host=host)
    assert result.code == 0
    assert [e for e in host.events if e[0] == "stage"] == [
        ("stage", stage) for stage in harness.PROBE_STAGES
    ]
    # One console pause per stage, so the operator can record metrics
    # before the next one opens.
    assert len(result.presses) == len(harness.PROBE_STAGES)
    out = capsys.readouterr().out
    assert out.count("live crops:") == len(harness.PROBE_STAGES)


def test_load_stops_at_the_stage_the_machine_cannot_fill(monkeypatch, capsys):
    """A stage with fewer clients than crops would measure a different
    thing than the one the gate names, so it is not run at all."""
    host = FakeProbeHost(clients=("A", "B", "C"))
    result = run_cli(monkeypatch, ["load", OPT_IN], host=host)
    assert result.code == 0
    assert [e for e in host.events if e[0] == "stage"] == [("stage", 1), ("stage", 2)]
    assert "3 named client" in capsys.readouterr().out


def test_load_stops_on_the_first_stage_that_reports_a_failure(monkeypatch, capsys):
    host = FakeProbeHost(
        clients=("A", "B", "C", "D"),
        failures_at={2: [{"stable_key": "B", "reason": "crop-failed"}]},
    )
    result = run_cli(monkeypatch, ["load", OPT_IN], host=host)
    assert result.code == 0
    assert [e for e in host.events if e[0] == "stage"] == [("stage", 1), ("stage", 2)]
    out = capsys.readouterr().out
    assert "crop-failed" in out
    assert host.stopped == 1


def test_a_stage_is_awaited_until_its_crops_are_live(monkeypatch):
    """set_probe_count only stores intent and wakes the pump; the crops
    appear on a later sweep, so printing the status immediately would
    report every stage as empty."""
    host = FakeProbeHost(clients=("A", "B"))
    live = {"n": 0}

    def status():
        live["n"] += 1
        return {
            "character": None,
            "requested": 1,
            "live": 1 if live["n"] > 2 else 0,
            "crops": ["A"] if live["n"] > 2 else [],
            "picker_open": False,
            "failures": [],
            "clients": ["A", "B"],
        }

    monkeypatch.setattr(host, "probe_status", status)
    slept = []
    monkeypatch.setattr(harness.time, "sleep", slept.append)
    settled = harness._await_stage(host, 1)
    assert settled["live"] == 1
    assert slept  # it waited rather than reporting the empty first read


def test_an_unfillable_stage_gives_up_instead_of_waiting_forever(monkeypatch):
    host = FakeProbeHost(clients=("A",), live_at={1: 0})
    monkeypatch.setattr(harness.time, "sleep", lambda _seconds: None)
    # The first two readings establish the deadline and one in-loop check
    # still short of it; every reading after that -- however many times
    # _await_stage's loop calls time.monotonic(), a detail this test must
    # not pin -- returns the same past-the-deadline value, so a call count
    # different from exactly three fails the timeout assertion below
    # instead of raising StopIteration from an exhausted iterator.
    readings = [0.0, 0.0, harness.STAGE_TIMEOUT_S + 1]

    def fake_monotonic():
        if readings:
            return readings.pop(0)
        return harness.STAGE_TIMEOUT_S + 1

    monkeypatch.setattr(harness.time, "monotonic", fake_monotonic)
    assert harness._await_stage(host, 1)["live"] == 0


# -- documentation ----------------------------------------------------------


def test_the_readme_documents_the_exact_commands_and_boundaries():
    """The commands are not retyped prose: an operator copies them, and a
    README that drifted from the parser would be a run that refuses or,
    worse, one that does something else."""
    readme = (ROOT / "tests" / "manual" / "README.md").read_text(encoding="utf-8")
    assert "tests/manual/preview_crop_harness.py pick" in readme
    assert "tests/manual/preview_crop_harness.py load" in readme
    assert OPT_IN in readme
    assert "--character" in readme
    for phrase in (
        "saves nothing",
        "moves no EVE window",
        "eight",
        "must not run beside",
    ):
        assert phrase in readme, phrase
