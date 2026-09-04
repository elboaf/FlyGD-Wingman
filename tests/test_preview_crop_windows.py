"""Fake-native tests for the prototype crop controller.

Loaded via importlib, the same pattern tests/test_preview_crop_model.py uses
for tests/manual/preview_crop_model.py: the module under test is a checkout
tool, not a package, and is not on any import path.

_ensure_class's WNDPROC/RegisterClassW machinery is bypassed everywhere
here (autouse fixture below) rather than faked: ctypes.WINFUNCTYPE does not
exist off Windows at all, so window.py's own creation path is likewise
untested on Linux -- "window creation needs a desktop and lives in the
smoke checklist" (test_preview_window.py's module docstring). What *is*
faked is everything the brief asks for: CreateWindowExW, DestroyWindow,
ShowWindow, SetWindowPos, capture, cursor, and DWM -- the six calls a real
crop creation and gesture actually make once the class already exists.
"""

import importlib.util
from pathlib import Path

import pytest

from wingman.preview import discovery, win32
from wingman.preview.geometry import Rect

module_path = Path(__file__).parent / "manual" / "preview_crop_windows.py"
spec = importlib.util.spec_from_file_location("preview_crop_windows", module_path)
windows = importlib.util.module_from_spec(spec)
spec.loader.exec_module(windows)

# Loaded the same way, so the picker confirmation tests below cross-check
# against the SAME map_selection the model's own suite exercises, rather
# than trusting the picker to reimplement its arithmetic correctly.
model_path = Path(__file__).parent / "manual" / "preview_crop_model.py"
model_spec = importlib.util.spec_from_file_location("preview_crop_model", model_path)
model = importlib.util.module_from_spec(model_spec)
model_spec.loader.exec_module(model)


CLIENT = discovery.Client(
    hwnd=555,
    title="EVE - Test Pilot",
    pid=4242,
    character="Test Pilot",
    stable_key="Test Pilot",
)

# A plain, unremarkable monitor for the picker's placement tests -- see
# test_picker_rect_centers_correctly_on_a_negative_origin_monitor below for
# the one that is deliberately not at the origin.
MONITOR = Rect(0, 0, 1920, 1080)


def _pack_lparam(x, y):
    """Pack (x, y) the way Windows delivers WM_* mouse lParams: low word
    x, high word y, both client-relative. The inverse of the picker's own
    _client_point."""
    return ((y & 0xFFFF) << 16) | (x & 0xFFFF)


@pytest.fixture(autouse=True)
def _bypass_class_registration(monkeypatch):
    """Every test drives a class that is already "registered" as far as
    create() is concerned -- see the module docstring above. Both the crop
    window's class and the picker's separate one (_ensure_picker_class) hit
    the same WINFUNCTYPE wall on Linux.

    Also clears windows._CROPS and windows._PICKERS before and after every
    test. Both registries are module-level dicts keyed by HWND, and
    FakeUser32's fake HWNDs always start counting from 1000 -- so a crop or
    picker left registered by one test would already occupy the exact key
    the next test's registry-before-register assertions probe, letting a
    stale entry from a PRIOR test make THIS test's
    registry_present_at_register check pass regardless of whether create()
    actually registered anything."""
    monkeypatch.setattr(windows, "_ensure_class", lambda libs: None)
    monkeypatch.setattr(windows, "_ensure_picker_class", lambda libs: None)
    windows._CROPS.clear()
    windows._PICKERS.clear()
    yield
    windows._CROPS.clear()
    windows._PICKERS.clear()


class FakeUser32:
    """Just enough Win32 for creation and the reduced gesture grammar,
    with the cursor and the queued-message state under test control."""

    def __init__(self, events, teardown_order=None):
        self.events = events
        self.shows = []
        self.positions = []
        self.captures = []
        # Every SetFocus(hwnd) call, in order -- see
        # test_picker_left_button_down_sets_focus_to_the_picker_hwnd for why
        # this needs its own list rather than folding into self.captures:
        # focus and capture are two distinct Win32 calls with two distinct
        # failure modes (a captured-but-unfocused picker never receives
        # WM_KEYDOWN at all).
        self.focus_calls = []
        self.cursor = (0, 0)
        self._next_hwnd = 1000
        # (left, top, right, bottom) of the SOURCE client's area, read by
        # PrototypeCropPicker at creation and again on confirm. None
        # simulates a client that has vanished (GetClientRect failing).
        self.client_rect = (0, 0, 1280, 720)
        # Every CreateWindowExW call, in order, with the arguments that
        # matter for asserting native facts (ex_style, class, owner/parent)
        # -- not just that a window was created, but that it was created
        # with the exact style bits the brief specifies.
        self.created = []
        # Shared with FakeDwm (see FakeLibs) so a single ordered log can
        # prove overlay-destroy / DWM-unregister / picker-destroy ordering
        # across BOTH fakes -- a bare "destroy-window" string in self.events
        # cannot say WHICH hwnd, and there are two DestroyWindow calls per
        # picker teardown.
        self.teardown_order = teardown_order if teardown_order is not None else []

    def CreateWindowExW(
        self,
        ex_style,
        class_name,
        window_name,
        style,
        x,
        y,
        w,
        h,
        parent,
        menu,
        hinstance,
        lparam,
    ):
        self.events.append("create-window")
        hwnd = self._next_hwnd
        self._next_hwnd += 1
        self.created.append(
            {
                "hwnd": hwnd,
                "ex_style": ex_style,
                "class_name": class_name,
                "style": style,
                "rect": (x, y, w, h),
                "parent": parent,
            }
        )
        return hwnd

    def DestroyWindow(self, hwnd):
        self.events.append("destroy-window")
        self.teardown_order.append(("destroy-window", int(hwnd)))
        return True

    def ShowWindow(self, hwnd, cmd):
        self.shows.append((hwnd, cmd))
        self.events.append("show")
        return True

    def SetWindowPos(self, hwnd, insert_after, x, y, w, h, flags):
        self.positions.append((x, y, w, h))
        return True

    def SetCapture(self, hwnd):
        self.captures.append(("set", hwnd))
        return hwnd

    def SetFocus(self, hwnd):
        self.focus_calls.append(hwnd)
        return hwnd

    def ReleaseCapture(self):
        self.captures.append(("release",))
        return True

    def GetCursorPos(self, ptr):
        ptr._obj.x, ptr._obj.y = self.cursor
        return True

    def GetClientRect(self, hwnd, ptr):
        if self.client_rect is None:
            return False
        left, top, right, bottom = self.client_rect
        ptr._obj.left, ptr._obj.top = left, top
        ptr._obj.right, ptr._obj.bottom = right, bottom
        return True

    def PeekMessageW(self, *args):
        return False  # nothing queued behind this event


class FakeDwm:
    def __init__(
        self, events, register_hr=0, update_hr=0, crops=None, teardown_order=None
    ):
        self.events = events
        self.updates = []
        self.register_hr = register_hr
        self.update_hr = update_hr
        # Injected so the register callback can assert the destination HWND
        # was already in the registry *before* registration -- registry
        # presence is not itself an event, so this is the direct check that
        # would fail if create() ever registered before it recorded the
        # instance windows._dispatch needs to find it.
        self._crops = crops
        self.registry_present_at_register = None
        # Shared with FakeUser32 -- see its own teardown_order comment.
        self.teardown_order = teardown_order if teardown_order is not None else []

    def DwmRegisterThumbnail(self, dest, src, out):
        if self._crops is not None:
            self.registry_present_at_register = int(dest) in self._crops
        if self.register_hr == 0:
            out._obj.value = 0xABC
            self.events.append("register")
        return self.register_hr

    def DwmUnregisterThumbnail(self, handle):
        self.events.append("unregister")
        self.teardown_order.append(("unregister",))
        return 0

    def DwmUpdateThumbnailProperties(self, handle, props):
        self.updates.append(props._obj)
        self.events.append("update")
        return self.update_hr


class FakeKernel32:
    def GetModuleHandleW(self, *_):
        return 1


class FakeLibs:
    def __init__(self, register_hr=0, update_hr=0, crops=None):
        self.events = []
        # Shared across both fakes -- see FakeUser32.teardown_order.
        self.teardown_order = []
        self.user32 = FakeUser32(self.events, teardown_order=self.teardown_order)
        self.dwmapi = FakeDwm(
            self.events,
            register_hr=register_hr,
            update_hr=update_hr,
            crops=crops,
            teardown_order=self.teardown_order,
        )
        self.kernel32 = FakeKernel32()


def make_crop(source, dest, locked=False, libs=None, on_activate=None):
    libs = libs or FakeLibs()
    on_activate = on_activate or (lambda client: None)
    crop = windows.PrototypeCropWindow.create(
        libs, CLIENT, source, dest, on_activate, locked=locked
    )
    assert crop is not None
    return crop, libs


# --- Step 1: creation and failure cleanup -----------------------------------


def test_crop_creation_sets_source_rect_and_shows_without_activation():
    libs = FakeLibs()
    activated = []
    crop = windows.PrototypeCropWindow.create(
        libs, CLIENT, Rect(100, 50, 400, 225), Rect(20, 30, 320, 180), activated.append
    )
    assert crop is not None
    props = libs.dwmapi.updates[-1]
    source = props.rcSource
    assert (source.left, source.top, source.right, source.bottom) == (
        100,
        50,
        500,
        275,
    )
    assert libs.user32.shows[-1] == (crop.hwnd, win32.SW_SHOWNOACTIVATE)
    assert activated == []


def test_crop_initial_update_failure_destroys_dwm_before_hwnd():
    libs = FakeLibs(update_hr=0x80004005)
    crop = windows.PrototypeCropWindow.create(
        libs,
        CLIENT,
        Rect(100, 50, 400, 225),
        Rect(20, 30, 320, 180),
        lambda client: None,
    )
    assert crop is None
    assert libs.events[-2:] == ["unregister", "destroy-window"]


def test_crop_register_failure_destroys_hwnd_without_unregister():
    """No DWM relationship exists yet when registration itself fails, so
    cleanup skips straight to the HWND -- unregistering a handle that was
    never issued would be a use-after-free in DWM's own handle table."""
    libs = FakeLibs(register_hr=0x80004005)
    crop = windows.PrototypeCropWindow.create(
        libs,
        CLIENT,
        Rect(100, 50, 400, 225),
        Rect(20, 30, 320, 180),
        lambda client: None,
    )
    assert crop is None
    assert "unregister" not in libs.events
    assert libs.events[-1] == "destroy-window"


def test_successful_creation_orders_hwnd_registry_register_update_show():
    """Pins the full success-path ordering: the HWND is created, the crop
    is registered in windows._CROPS, THEN registration happens (so
    windows._dispatch could already find this instance if DWM synchronously
    delivered a message), THEN the first update, THEN the show."""
    libs = FakeLibs(crops=windows._CROPS)
    crop = windows.PrototypeCropWindow.create(
        libs, CLIENT, Rect(0, 0, 400, 200), Rect(0, 0, 200, 100), lambda c: None
    )
    assert crop is not None
    assert libs.dwmapi.registry_present_at_register is True
    assert libs.events == ["create-window", "register", "update", "show"]


def test_register_failure_logs_a_warning_with_crop_context(caplog):
    libs = FakeLibs(register_hr=0x80004005)
    with caplog.at_level("WARNING"):
        crop = windows.PrototypeCropWindow.create(
            libs, CLIENT, Rect(0, 0, 400, 200), Rect(0, 0, 200, 100), lambda c: None
        )
    assert crop is None
    assert any(CLIENT.stable_key in r.message for r in caplog.records)


def test_initial_update_failure_logs_a_warning_with_crop_context(caplog):
    libs = FakeLibs(update_hr=0x80004005)
    with caplog.at_level("WARNING"):
        crop = windows.PrototypeCropWindow.create(
            libs, CLIENT, Rect(0, 0, 400, 200), Rect(0, 0, 200, 100), lambda c: None
        )
    assert crop is None
    assert any(CLIENT.stable_key in r.message for r in caplog.records)


def test_successful_creation_is_silent(caplog):
    with caplog.at_level("WARNING"):
        crop, _libs = make_crop(Rect(0, 0, 400, 200), Rect(0, 0, 200, 100))
    assert crop is not None
    assert caplog.records == []


# --- Step 4: the reduced interaction grammar ---------------------------------


def test_locked_left_down_activates_immediately():
    activated = []
    crop, libs = make_crop(
        Rect(0, 0, 400, 200),
        Rect(0, 0, 200, 100),
        locked=True,
        on_activate=activated.append,
    )
    libs.user32.cursor = (10, 10)
    crop._on_message(win32.WM_LBUTTONDOWN, 1, 0)
    assert activated == [CLIENT]
    assert crop._mode is None  # a locked press never arms a gesture


def test_unlocked_click_inside_click_px_activates_once_on_release():
    activated = []
    crop, libs = make_crop(
        Rect(0, 0, 400, 200), Rect(0, 0, 200, 100), on_activate=activated.append
    )
    libs.user32.cursor = (100, 100)
    crop._on_message(win32.WM_LBUTTONDOWN, 1, 0)
    assert activated == []  # not yet -- still undetermined
    libs.user32.cursor = (101, 101)  # inside CLICK_PX
    crop._on_message(win32.WM_MOUSEMOVE, 1, 0)
    crop._on_message(win32.WM_LBUTTONUP, 1, 0)
    assert activated == [CLIENT]


def test_unlocked_left_drag_moves_without_activation():
    activated = []
    crop, libs = make_crop(
        Rect(0, 0, 400, 200), Rect(50, 60, 200, 100), on_activate=activated.append
    )
    libs.user32.cursor = (200, 200)
    crop._on_message(win32.WM_LBUTTONDOWN, 1, 0)
    libs.user32.cursor = (230, 210)
    crop._on_message(win32.WM_MOUSEMOVE, 1, 0)
    crop._on_message(win32.WM_LBUTTONUP, 1, 0)
    assert crop.rect == Rect(80, 70, 200, 100)
    assert activated == []


def test_right_drag_preserves_source_aspect():
    crop, libs = make_crop(source=Rect(0, 0, 400, 200), dest=Rect(0, 0, 200, 100))
    crop._start = (0, 0)
    crop._start_rect = crop.rect
    crop._mode = "resize"
    libs.user32.cursor = (100, 20)
    crop._on_message(win32.WM_MOUSEMOVE, 0, 0)
    assert crop.rect.w / crop.rect.h == pytest.approx(2.0)


def test_a_locked_crop_refuses_the_right_drag_resize():
    crop, libs = make_crop(Rect(0, 0, 400, 200), Rect(0, 0, 200, 100), locked=True)
    libs.user32.cursor = (100, 100)
    crop._on_message(win32.WM_RBUTTONDOWN, 2, 0)
    libs.user32.cursor = (150, 160)
    crop._on_message(win32.WM_MOUSEMOVE, 2, 0)
    crop._on_message(win32.WM_RBUTTONUP, 2, 0)
    assert crop.rect == Rect(0, 0, 200, 100)


def test_a_left_press_during_an_active_resize_does_not_overwrite_it():
    """Right-press/move/left-press/right-release. The stray left press must
    not reclassify the armed resize as a fresh pending_left click -- doing
    so would let the eventual right-release fall into the pending_left
    branch and activate on a gesture the user never intended as a click."""
    activated = []
    crop, libs = make_crop(
        Rect(0, 0, 400, 200), Rect(0, 0, 200, 100), on_activate=activated.append
    )
    libs.user32.cursor = (100, 100)
    crop._on_message(win32.WM_RBUTTONDOWN, 2, 0)
    libs.user32.cursor = (150, 120)
    crop._on_message(win32.WM_MOUSEMOVE, 2, 0)
    assert crop._mode == "resize"
    resized_rect = crop.rect

    crop._on_message(win32.WM_LBUTTONDOWN, 1, 0)
    assert crop._mode == "resize"  # unchanged: the second button is ignored

    crop._on_message(win32.WM_RBUTTONUP, 2, 0)
    assert crop._mode is None
    assert activated == []
    assert crop.rect == resized_rect


def test_a_wrong_button_release_does_not_activate():
    """A pending left click released via the wrong button must clear the
    gesture without activating -- activation is gated on WM_LBUTTONUP,
    not on "any release while pending_left"."""
    activated = []
    crop, libs = make_crop(
        Rect(0, 0, 400, 200), Rect(0, 0, 200, 100), on_activate=activated.append
    )
    libs.user32.cursor = (100, 100)
    crop._on_message(win32.WM_LBUTTONDOWN, 1, 0)
    assert crop._mode == "pending_left"

    crop._on_message(win32.WM_RBUTTONUP, 2, 0)

    assert activated == []
    assert crop._mode is None


def test_degenerate_source_aspect_takes_the_freeform_resize_path():
    """A zero-height/width source (client at character select, or one that
    quit mid-drag) must not raise -- _source_aspect() returns None and
    resize_result falls back to unlocked width/height deltas."""
    crop, libs = make_crop(source=Rect(0, 0, 0, 200), dest=Rect(0, 0, 200, 100))
    crop._start = (0, 0)
    crop._start_rect = crop.rect
    crop._mode = "resize"
    libs.user32.cursor = (50, 20)
    crop._on_message(win32.WM_MOUSEMOVE, 0, 0)
    assert crop.rect.w == 250
    assert crop.rect.h == 120


def test_pure_move_does_not_call_dwm_update():
    crop, libs = make_crop(Rect(0, 0, 400, 200), Rect(0, 0, 200, 100))
    before = len(libs.dwmapi.updates)
    crop.move(Rect(10, 10, 200, 100))
    assert len(libs.dwmapi.updates) == before
    assert libs.user32.positions[-1] == (10, 10, 200, 100)


def test_resize_calls_dwm_update_with_the_unchanged_source_rectangle():
    source = Rect(100, 50, 400, 225)
    crop, libs = make_crop(source, Rect(0, 0, 320, 180))
    before = len(libs.dwmapi.updates)
    crop.move(Rect(0, 0, 400, 225))
    assert len(libs.dwmapi.updates) == before + 1
    src = libs.dwmapi.updates[-1].rcSource
    assert (src.left, src.top, src.right, src.bottom) == (100, 50, 500, 275)


def test_set_hidden_uses_sw_hide_and_sw_shownoactivate_idempotently():
    crop, libs = make_crop(Rect(0, 0, 400, 200), Rect(0, 0, 200, 100))
    libs.user32.shows.clear()

    crop.set_hidden(True)
    crop.set_hidden(True)
    assert libs.user32.shows == [(crop.hwnd, win32.SW_HIDE)]

    crop.set_hidden(False)
    crop.set_hidden(False)
    assert libs.user32.shows[-1] == (crop.hwnd, win32.SW_SHOWNOACTIVATE)
    assert libs.user32.shows.count((crop.hwnd, win32.SW_SHOWNOACTIVATE)) == 1


def test_set_locked_cancels_an_in_flight_drag_and_the_next_press_activates():
    activated = []
    crop, libs = make_crop(
        Rect(0, 0, 400, 200), Rect(0, 0, 200, 100), on_activate=activated.append
    )
    libs.user32.cursor = (200, 200)
    crop._on_message(win32.WM_LBUTTONDOWN, 1, 0)
    libs.user32.cursor = (230, 210)
    crop._on_message(win32.WM_MOUSEMOVE, 1, 0)  # now dragging (mode == "move")

    crop.set_locked(True)

    assert crop.locked is True
    assert crop._mode is None
    assert libs.user32.captures[-1] == ("release",)

    libs.user32.cursor = (10, 10)
    crop._on_message(win32.WM_LBUTTONDOWN, 1, 0)
    assert activated == [CLIENT]


def test_close_unregisters_and_destroys_exactly_once():
    crop, libs = make_crop(Rect(0, 0, 400, 200), Rect(0, 0, 200, 100))
    before = len(libs.events)

    crop.close()
    crop.close()

    assert libs.events[before:] == ["unregister", "destroy-window"]
    assert crop.hwnd is None


def test_wm_destroy_clears_registry_and_thumbnail_without_double_destroying():
    """A defensive handler for WM_DESTROY reaching this instance through
    some route other than our own close() (which already pops the registry
    and clears hwnd before calling DestroyWindow). Must not call
    DestroyWindow itself -- this handler runs because destruction already
    happened or is happening."""
    crop, libs = make_crop(Rect(0, 0, 400, 200), Rect(0, 0, 200, 100))
    hwnd = crop.hwnd
    assert hwnd in windows._CROPS
    destroy_calls_before = libs.events.count("destroy-window")

    crop._on_message(win32.WM_DESTROY, 0, 0)

    assert crop.hwnd is None
    assert crop._thumb is None
    assert hwnd not in windows._CROPS
    assert libs.events.count("destroy-window") == destroy_calls_before


# --- PrototypeCropPicker -----------------------------------------------


def make_picker(libs=None, client=None, monitor=None, on_confirm=None, on_cancel=None):
    libs = libs or FakeLibs()
    client = client or CLIENT
    monitor = monitor or MONITOR
    on_confirm = on_confirm or (lambda client, source_rect: None)
    on_cancel = on_cancel or (lambda reason: None)
    picker = windows.PrototypeCropPicker.create(
        libs, client, monitor, on_confirm, on_cancel
    )
    assert picker is not None
    return picker, libs


def test_picker_source_client_rect_failure_returns_none_without_hwnd_leak():
    libs = FakeLibs()
    libs.user32.client_rect = None
    picker = windows.PrototypeCropPicker.create(
        libs, CLIENT, MONITOR, lambda c, r: None, lambda reason: None
    )
    assert picker is None
    assert "create-window" not in libs.events


def test_picker_degenerate_source_client_rect_returns_none():
    """A zero-area client area (character select, or a client that quit
    mid-open) must not be sized against -- fit_within((0, h), ...) would
    divide by zero."""
    libs = FakeLibs()
    libs.user32.client_rect = (0, 0, 0, 720)
    picker = windows.PrototypeCropPicker.create(
        libs, CLIENT, MONITOR, lambda c, r: None, lambda reason: None
    )
    assert picker is None
    assert "create-window" not in libs.events


def test_picker_registration_failure_closes_overlay_and_picker():
    libs = FakeLibs(register_hr=0x80004005)
    picker = windows.PrototypeCropPicker.create(
        libs, CLIENT, MONITOR, lambda c, r: None, lambda reason: None
    )
    assert picker is None
    assert "register" not in libs.events
    assert libs.events[-2:] == ["destroy-window", "destroy-window"]


def test_picker_registration_failure_destroys_overlay_before_hwnd_without_unregister():
    """HWND-level version of the test above: no DWM relationship exists
    yet when registration itself fails, so there is no unregister call at
    all -- only the overlay HWND, then the picker HWND."""
    libs = FakeLibs(register_hr=0x80004005)
    picker = windows.PrototypeCropPicker.create(
        libs, CLIENT, MONITOR, lambda c, r: None, lambda reason: None
    )
    assert picker is None
    picker_hwnd, overlay_hwnd = (c["hwnd"] for c in libs.user32.created)
    assert libs.teardown_order == [
        ("destroy-window", overlay_hwnd),
        ("destroy-window", picker_hwnd),
    ]


def test_picker_initial_update_failure_closes_overlay_dwm_and_picker():
    """This failure path used to close DWM before the overlay -- backwards
    from the brief's overlay-then-DWM-then-HWND order -- because create()
    duplicated _close_resources's teardown by hand instead of calling it.
    Fixed by routing every failure branch through _close_resources()."""
    libs = FakeLibs(update_hr=0x80004005)
    picker = windows.PrototypeCropPicker.create(
        libs, CLIENT, MONITOR, lambda c, r: None, lambda reason: None
    )
    assert picker is None
    assert libs.events[-3:] == ["destroy-window", "unregister", "destroy-window"]


def test_picker_initial_update_failure_destroys_overlay_before_dwm_before_hwnd():
    """HWND-level version: proves the ORDER by hwnd/handle identity, not
    just by matching string labels -- overlay destroyed, THEN the DWM
    relationship unregistered, THEN the picker HWND destroyed."""
    libs = FakeLibs(update_hr=0x80004005)
    picker = windows.PrototypeCropPicker.create(
        libs, CLIENT, MONITOR, lambda c, r: None, lambda reason: None
    )
    assert picker is None
    picker_hwnd, overlay_hwnd = (c["hwnd"] for c in libs.user32.created)
    assert libs.teardown_order == [
        ("destroy-window", overlay_hwnd),
        ("unregister",),
        ("destroy-window", picker_hwnd),
    ]


def test_picker_creation_orders_hwnds_registry_overlay_register_update_show():
    libs = FakeLibs(crops=windows._PICKERS)
    _picker, _libs = make_picker(libs=libs)
    assert libs.dwmapi.registry_present_at_register is True
    assert libs.events == [
        "create-window",  # picker HWND
        "create-window",  # overlay HWND
        "show",  # overlay shown
        "register",
        "update",
        "show",  # picker itself shown last
    ]


def test_picker_creation_is_silent(caplog):
    with caplog.at_level("WARNING"):
        picker, _libs = make_picker()
    assert picker is not None
    assert caplog.records == []


def test_picker_creation_native_facts_match_the_brief():
    """Pins the exact style/owner/rect/show facts the brief specifies,
    not just that the right NUMBER of calls happened -- a picker with the
    wrong ex_style or the wrong overlay owner would still pass the ordering
    test above."""
    libs = FakeLibs()
    libs.user32.client_rect = (0, 0, 1280, 720)
    picker, libs = make_picker(libs=libs)

    picker_call, overlay_call = libs.user32.created

    # The picker itself is the DWM destination: an ordinary topmost tool
    # popup, WITHOUT WS_EX_NOACTIVATE -- Enter/Escape must reach its
    # WndProc once clicked.
    assert picker_call["hwnd"] == picker.hwnd
    assert picker_call["ex_style"] == win32.WS_EX_TOOLWINDOW | win32.WS_EX_TOPMOST
    assert picker_call["ex_style"] & win32.WS_EX_NOACTIVATE == 0
    assert picker_call["parent"] is None

    # The overlay is owned by the picker, layered, transparent to hit
    # testing, and itself WS_EX_NOACTIVATE (it must never take focus).
    assert overlay_call["hwnd"] == picker._overlay_hwnd
    assert overlay_call["ex_style"] == (
        win32.WS_EX_LAYERED
        | win32.WS_EX_TRANSPARENT
        | win32.WS_EX_TOOLWINDOW
        | win32.WS_EX_NOACTIVATE
    )
    assert overlay_call["parent"] == picker.hwnd

    # Both windows are shown with SW_SHOWNOACTIVATE -- overlay first, then
    # the picker itself.
    assert libs.user32.shows == [
        (picker._overlay_hwnd, win32.SW_SHOWNOACTIVATE),
        (picker.hwnd, win32.SW_SHOWNOACTIVATE),
    ]

    # The DWM destination is the picker's own FULL client rect, and the
    # source is the client's FULL area -- not any particular crop's
    # source_rect, since the user is choosing a sub-region of the whole
    # thing.
    props = libs.dwmapi.updates[-1]
    assert (
        props.rcDestination.left,
        props.rcDestination.top,
        props.rcDestination.right,
        props.rcDestination.bottom,
    ) == (0, 0, picker.rect.w, picker.rect.h)
    assert (
        props.rcSource.left,
        props.rcSource.top,
        props.rcSource.right,
        props.rcSource.bottom,
    ) == (0, 0, 1280, 720)


def test_picker_creation_focuses_the_picker_after_showing_it_noactivate():
    """Regression coverage for the SetFocus call added to create(): a
    picker shown only with SW_SHOWNOACTIVATE never becomes the focused
    window, so Escape pressed before the user's first click -- the one
    case _on_message's own WM_LBUTTONDOWN-triggered SetFocus cannot cover,
    since it has not fired yet -- would silently go nowhere. Both facts
    must hold together: the show stays SW_SHOWNOACTIVATE (never steals
    activation from whatever the user was doing) and SetFocus still runs
    exactly once, after it, targeting the picker's own HWND."""
    picker, libs = make_picker()
    assert libs.user32.shows[-1] == (picker.hwnd, win32.SW_SHOWNOACTIVATE)
    assert libs.user32.focus_calls == [picker.hwnd]


def test_picker_rect_is_sized_by_fit_within_and_centered_with_margin():
    libs = FakeLibs()
    libs.user32.client_rect = (0, 0, 2560, 1440)
    picker, libs = make_picker(libs=libs, monitor=Rect(0, 0, 1920, 1080))
    assert model.fit_within((2560, 1440), windows.PICKER_MAX) == (
        picker.rect.w,
        picker.rect.h,
    )
    assert (picker.rect.w, picker.rect.h) == (1200, 675)
    assert (picker.rect.x, picker.rect.y) == (360, 202)


def test_picker_rect_pins_only_the_oversized_dimension_to_monitor_origin():
    """A picker oversize in width but comfortably margined in height must
    have only its width pinned to the monitor's origin -- the height axis
    still centers normally, independent of the other."""
    libs = FakeLibs()
    libs.user32.client_rect = (0, 0, 1280, 720)  # -> picker 1200x675
    picker, libs = make_picker(libs=libs, monitor=Rect(0, 0, 1000, 2000))
    assert picker.rect.x == 0  # oversize (1200 > 1000): pinned
    assert picker.rect.y == (2000 - 675) // 2  # fits with margin: centered


def test_picker_rect_pins_to_origin_on_both_axes_when_oversize_on_both():
    libs = FakeLibs()
    libs.user32.client_rect = (0, 0, 1280, 720)  # -> picker 1200x675
    picker, libs = make_picker(libs=libs, monitor=Rect(0, 0, 600, 400))
    assert (picker.rect.x, picker.rect.y) == (0, 0)


def test_picker_rect_centers_without_margin_when_the_margin_cannot_fit_but_the_picker_does():
    """The picker (1200x675) fits inside a 1220x700 monitor, but not with
    the full 40px margin on every side -- it must still be centered, not
    collapsed to the origin the way an actually-oversize picker is."""
    libs = FakeLibs()
    libs.user32.client_rect = (0, 0, 1280, 720)
    picker, libs = make_picker(libs=libs, monitor=Rect(0, 0, 1220, 700))
    assert (picker.rect.x, picker.rect.y) == (10, 12)


def test_picker_rect_centers_correctly_on_a_negative_origin_monitor():
    libs = FakeLibs()
    libs.user32.client_rect = (0, 0, 1280, 720)
    picker, libs = make_picker(libs=libs, monitor=Rect(-1920, 0, 1920, 1080))
    assert picker.rect.x == -1920 + (1920 - 1200) // 2
    assert picker.rect.y == (1080 - 675) // 2


def test_picker_left_button_down_sets_focus_to_the_picker_hwnd():
    """WM_LBUTTONDOWN previously called SetCapture but never SetFocus, so
    Enter/Escape (delivered via WM_KEYDOWN, which only ever reaches the
    FOCUSED window's WndProc) never reached the picker after a user
    clicked and dragged a selection -- a click captured the mouse without
    making the picker the focused window, so the keystroke went wherever
    focus already was. The picker is a Wingman-owned HWND (unlike
    PrototypeCropWindow's WS_EX_NOACTIVATE crop, this is deliberately not
    NOACTIVATE -- see the class docstring), so focusing it here is safe
    and required, never the EVE client HWND.

    create() itself now also focuses the picker once (see
    test_picker_creation_focuses_the_picker_after_showing_it_noactivate),
    so this asserts the INCREMENT the press itself causes, not the raw
    list -- a regression here would still show a call from creation even
    if WM_LBUTTONDOWN stopped focusing altogether."""
    picker, libs = make_picker()
    before = list(libs.user32.focus_calls)

    picker._on_message(win32.WM_LBUTTONDOWN, 1, _pack_lparam(10, 10))

    assert libs.user32.focus_calls == [*before, picker.hwnd]


def test_picker_drag_builds_sorted_selection_and_pushes_overlay(monkeypatch):
    pushes = []
    monkeypatch.setattr(
        windows.layered,
        "push",
        lambda libs, hwnd, img, x, y: pushes.append((hwnd, img.size, x, y)),
    )
    picker, _libs = make_picker()
    # Dragged from bottom-right to top-left: the rect must come out
    # normalized (sorted), not with a negative width/height.
    picker._on_message(win32.WM_LBUTTONDOWN, 1, _pack_lparam(300, 200))
    picker._on_message(win32.WM_MOUSEMOVE, 1, _pack_lparam(100, 50))
    assert picker.selection == Rect(100, 50, 200, 150)
    assert pushes[-1][0] == picker._overlay_hwnd
    assert pushes[-1][1] == (picker.rect.w, picker.rect.h)
    assert pushes[-1][2:] == (picker.rect.x, picker.rect.y)


def test_picker_drag_coalesces_queued_mouse_moves_to_the_newest_position(monkeypatch):
    """A fast drag queues WM_MOUSEMOVE far faster than a render+push can
    keep up (see window.coalesce_moves's own docstring). This one
    WM_MOUSEMOVE dispatch must drain the two queued behind it and render
    only the LAST position -- not the one it was itself called with, and
    not once per queued message."""
    pushes = []
    monkeypatch.setattr(
        windows.layered, "push", lambda libs, hwnd, img, x, y: pushes.append(1)
    )
    picker, libs = make_picker()
    picker._on_message(win32.WM_LBUTTONDOWN, 1, _pack_lparam(0, 0))

    queued = [_pack_lparam(50, 40), _pack_lparam(150, 120)]

    def fake_peek(msg_ptr, hwnd, lo, hi, flags):
        if not queued:
            return False
        msg_ptr._obj.lParam = queued.pop(0)
        return True

    libs.user32.PeekMessageW = fake_peek

    picker._on_message(win32.WM_MOUSEMOVE, 1, _pack_lparam(10, 10))

    assert picker.selection == Rect(0, 0, 150, 120)  # the LAST queued position
    assert len(pushes) == 1  # one dispatch, one render -- not one per queued move


def test_picker_mouse_move_without_a_prior_press_is_ignored(monkeypatch):
    monkeypatch.setattr(windows.layered, "push", lambda *a, **k: None)
    picker, _libs = make_picker()
    picker._on_message(win32.WM_MOUSEMOVE, 0, _pack_lparam(100, 50))
    assert picker.selection is None


def test_render_selection_overlay_masks_outside_and_clears_inside():
    img = windows._render_selection_overlay((40, 30), Rect(10, 10, 10, 10))
    assert img.getpixel((0, 0)) == (0, 0, 0, windows.PICKER_MASK_ALPHA)
    assert img.getpixel((15, 15)) == (0, 0, 0, 0)  # inside, off the border
    assert img.getpixel((10, 15)) == windows.PICKER_BORDER  # left edge


def test_render_selection_overlay_with_no_selection_is_fully_masked():
    img = windows._render_selection_overlay((10, 10), None)
    assert img.getpixel((5, 5)) == (0, 0, 0, windows.PICKER_MASK_ALPHA)


def test_picker_enter_without_a_selection_is_a_noop():
    confirmed, cancelled = [], []
    picker, _libs = make_picker(
        on_confirm=lambda c, r: confirmed.append((c, r)), on_cancel=cancelled.append
    )
    picker._on_message(windows.WM_KEYDOWN, windows.VK_RETURN, 0)
    assert confirmed == []
    assert cancelled == []
    assert picker.hwnd is not None


def test_picker_enter_with_a_valid_selection_confirms_once():
    confirmed = []
    libs = FakeLibs()
    libs.user32.client_rect = (0, 0, 1280, 720)
    picker, libs = make_picker(
        libs=libs, on_confirm=lambda c, r: confirmed.append((c, r))
    )
    picker.selection = Rect(0, 0, picker.rect.w, picker.rect.h)

    picker._on_message(windows.WM_KEYDOWN, windows.VK_RETURN, 0)

    assert len(confirmed) == 1
    client, source_rect = confirmed[0]
    assert client is CLIENT  # identity passed through unchanged
    assert source_rect == Rect(0, 0, 1280, 720)
    assert picker.hwnd is None
    assert picker._overlay_hwnd is None
    assert picker._thumb is None


def test_picker_confirm_destroys_overlay_before_dwm_before_hwnd():
    """HWND-level teardown-order proof on the SUCCESS path, matching the
    two failure-path versions above."""
    libs = FakeLibs()
    libs.user32.client_rect = (0, 0, 1280, 720)
    picker, libs = make_picker(libs=libs)
    overlay_hwnd, picker_hwnd = picker._overlay_hwnd, picker.hwnd
    picker.selection = Rect(0, 0, picker.rect.w, picker.rect.h)

    picker._on_message(windows.WM_KEYDOWN, windows.VK_RETURN, 0)

    assert libs.teardown_order == [
        ("destroy-window", overlay_hwnd),
        ("unregister",),
        ("destroy-window", picker_hwnd),
    ]


def test_picker_enter_maps_a_partial_selection_the_same_way_the_model_does():
    confirmed = []
    libs = FakeLibs()
    libs.user32.client_rect = (0, 0, 1280, 720)
    picker, libs = make_picker(
        libs=libs, on_confirm=lambda c, r: confirmed.append((c, r))
    )
    picker.selection = Rect(0, 0, 600, 337)

    picker._on_message(windows.WM_KEYDOWN, windows.VK_RETURN, 0)

    expected = model.map_selection(
        Rect(0, 0, 600, 337), Rect(0, 0, picker.rect.w, picker.rect.h), (1280, 720)
    )
    assert confirmed[0][1] == expected


def test_picker_enter_with_a_too_small_selection_keeps_the_picker_open():
    confirmed = []
    picker, _libs = make_picker(on_confirm=lambda c, r: confirmed.append((c, r)))
    picker.selection = Rect(0, 0, 1, 1)

    picker._on_message(windows.WM_KEYDOWN, windows.VK_RETURN, 0)

    assert confirmed == []
    assert picker.hwnd is not None


def test_picker_confirm_against_a_vanished_client_cancels_client_unavailable():
    cancelled = []
    libs = FakeLibs()
    libs.user32.client_rect = (0, 0, 1280, 720)
    picker, libs = make_picker(libs=libs, on_cancel=cancelled.append)
    picker.selection = Rect(0, 0, picker.rect.w, picker.rect.h)

    libs.user32.client_rect = None  # client vanished before Enter
    picker._on_message(windows.WM_KEYDOWN, windows.VK_RETURN, 0)

    assert cancelled == ["client-unavailable"]
    assert picker.hwnd is None


def test_picker_confirm_against_a_resized_client_cancels_client_resized():
    """Phase 0 does not guess a remap when the client's shape has changed
    since the picker opened -- it cancels instead."""
    cancelled = []
    libs = FakeLibs()
    libs.user32.client_rect = (0, 0, 1280, 720)
    picker, libs = make_picker(libs=libs, on_cancel=cancelled.append)
    picker.selection = Rect(0, 0, picker.rect.w, picker.rect.h)

    libs.user32.client_rect = (0, 0, 1024, 768)  # resized since creation
    picker._on_message(windows.WM_KEYDOWN, windows.VK_RETURN, 0)

    assert cancelled == ["client-resized"]
    assert picker.hwnd is None


def test_picker_escape_cancels_exactly_once():
    cancelled = []
    picker, _libs = make_picker(on_cancel=cancelled.append)

    picker._on_message(windows.WM_KEYDOWN, windows.VK_ESCAPE, 0)
    picker._on_message(windows.WM_KEYDOWN, windows.VK_ESCAPE, 0)  # already torn down

    assert cancelled == ["cancelled"]
    assert picker.hwnd is None
    assert picker._overlay_hwnd is None


def test_picker_escape_destroys_overlay_before_dwm_before_hwnd():
    picker, libs = make_picker()
    overlay_hwnd, picker_hwnd = picker._overlay_hwnd, picker.hwnd

    picker._on_message(windows.WM_KEYDOWN, windows.VK_ESCAPE, 0)

    assert libs.teardown_order == [
        ("destroy-window", overlay_hwnd),
        ("unregister",),
        ("destroy-window", picker_hwnd),
    ]


def test_picker_close_cancels_exactly_once():
    cancelled = []
    picker, _libs = make_picker(on_cancel=cancelled.append)

    picker._on_message(win32.WM_CLOSE, 0, 0)
    picker._on_message(win32.WM_CLOSE, 0, 0)

    assert cancelled == ["cancelled"]
    assert picker.hwnd is None


def test_picker_cancel_is_a_public_host_facing_dismissal_seam():
    """Task 5's host needs a way to end a picker (e.g. superseding one
    with another) without reaching into private confirm/cancel machinery.
    cancel() is that seam."""
    cancelled = []
    picker, _libs = make_picker(on_cancel=cancelled.append)

    picker.cancel("superseded")

    assert cancelled == ["superseded"]
    assert picker.hwnd is None
    assert picker._overlay_hwnd is None


def test_picker_cancel_defaults_to_host_cancelled():
    cancelled = []
    picker, _libs = make_picker(on_cancel=cancelled.append)

    picker.cancel()

    assert cancelled == ["host-cancelled"]


def test_picker_cancel_after_confirm_does_not_double_fire():
    confirmed, cancelled = [], []
    libs = FakeLibs()
    libs.user32.client_rect = (0, 0, 1280, 720)
    picker, libs = make_picker(
        libs=libs,
        on_confirm=lambda c, r: confirmed.append((c, r)),
        on_cancel=cancelled.append,
    )
    picker.selection = Rect(0, 0, picker.rect.w, picker.rect.h)
    picker._on_message(windows.WM_KEYDOWN, windows.VK_RETURN, 0)

    picker.cancel("superseded")

    assert len(confirmed) == 1
    assert cancelled == []


def test_picker_escape_after_confirm_does_not_double_fire():
    """Guards the shared _completed flag from both directions: a picker
    that already confirmed must not also cancel if a stray Escape
    arrives before the WndProc is fully torn down."""
    confirmed, cancelled = [], []
    libs = FakeLibs()
    libs.user32.client_rect = (0, 0, 1280, 720)
    picker, libs = make_picker(
        libs=libs,
        on_confirm=lambda c, r: confirmed.append((c, r)),
        on_cancel=cancelled.append,
    )
    picker.selection = Rect(0, 0, picker.rect.w, picker.rect.h)
    picker._on_message(windows.WM_KEYDOWN, windows.VK_RETURN, 0)

    picker._on_message(windows.WM_KEYDOWN, windows.VK_ESCAPE, 0)

    assert len(confirmed) == 1
    assert cancelled == []


def test_picker_wm_destroy_clears_registry_and_thumbnail_without_double_destroying():
    picker, libs = make_picker()
    hwnd = picker.hwnd
    assert hwnd in windows._PICKERS
    destroy_calls_before = libs.events.count("destroy-window")

    picker._on_message(win32.WM_DESTROY, 0, 0)

    assert picker.hwnd is None
    assert picker._thumb is None
    assert hwnd not in windows._PICKERS
    assert libs.events.count("destroy-window") == destroy_calls_before
