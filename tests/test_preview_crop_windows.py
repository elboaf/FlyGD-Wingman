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


CLIENT = discovery.Client(
    hwnd=555,
    title="EVE - Test Pilot",
    pid=4242,
    character="Test Pilot",
    stable_key="Test Pilot",
)


@pytest.fixture(autouse=True)
def _bypass_class_registration(monkeypatch):
    """Every test drives a class that is already "registered" as far as
    create() is concerned -- see the module docstring above."""
    monkeypatch.setattr(windows, "_ensure_class", lambda libs: None)


class FakeUser32:
    """Just enough Win32 for creation and the reduced gesture grammar,
    with the cursor and the queued-message state under test control."""

    def __init__(self, events):
        self.events = events
        self.shows = []
        self.positions = []
        self.captures = []
        self.cursor = (0, 0)
        self._next_hwnd = 1000

    def CreateWindowExW(self, *args, **kwargs):
        self.events.append("create-window")
        hwnd = self._next_hwnd
        self._next_hwnd += 1
        return hwnd

    def DestroyWindow(self, hwnd):
        self.events.append("destroy-window")
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

    def ReleaseCapture(self):
        self.captures.append(("release",))
        return True

    def GetCursorPos(self, ptr):
        ptr._obj.x, ptr._obj.y = self.cursor
        return True

    def PeekMessageW(self, *args):
        return False  # nothing queued behind this event


class FakeDwm:
    def __init__(self, events, register_hr=0, update_hr=0, crops=None):
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

    def DwmRegisterThumbnail(self, dest, src, out):
        if self._crops is not None:
            self.registry_present_at_register = int(dest) in self._crops
        if self.register_hr == 0:
            out._obj.value = 0xABC
            self.events.append("register")
        return self.register_hr

    def DwmUnregisterThumbnail(self, handle):
        self.events.append("unregister")
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
        self.user32 = FakeUser32(self.events)
        self.dwmapi = FakeDwm(
            self.events, register_hr=register_hr, update_hr=update_hr, crops=crops
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
