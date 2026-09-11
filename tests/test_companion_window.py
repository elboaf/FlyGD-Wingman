"""Destinations may move; auxiliary sources may only be read/captured."""

from types import SimpleNamespace

import pytest

from wingman.preview import win32
from wingman.preview.layout import Rect


class WindowOS:
    def __init__(self):
        self.owned = set()
        self.relationships = set()
        self.calls = []
        self.props = []
        self.fail = None
        self.cursor = (0, 0)
        self.capture = None
        self.libs = SimpleNamespace(
            user32=self,
            dwmapi=self,
            kernel32=SimpleNamespace(GetModuleHandleW=lambda _: 1),
        )

    def CreateWindowExW(self, ex, cls, label, style, x, y, w, h, *rest):
        assert not style & win32.WS_VISIBLE
        self.owned.add(100)
        return 100

    def DestroyWindow(self, hwnd):
        assert hwnd in self.owned
        self.calls.append(("destroy", hwnd))
        if self.fail == "destroy":
            return False
        self.owned.remove(hwnd)
        return True

    def IsWindow(self, hwnd):
        return hwnd in self.owned

    def SetWindowPos(self, hwnd, after, x, y, w, h, flags):
        assert hwnd in self.owned
        self.calls.append(("move", hwnd, Rect(x, y, w, h)))
        return True

    def ShowWindow(self, hwnd, mode):
        assert hwnd in self.owned
        self.calls.append(("show", hwnd, mode))
        return False

    def DwmRegisterThumbnail(self, dest, source, pointer):
        assert dest in self.owned and source == 10
        if self.fail == "register":
            return 1
        pointer._obj.value = 55
        self.relationships.add(55)
        return 0

    def DwmUpdateThumbnailProperties(self, handle, pointer):
        assert handle.value in self.relationships
        self.props.append(win32.DWM_THUMBNAIL_PROPERTIES.from_buffer_copy(pointer._obj))
        return 1 if self.fail == "update" else 0

    def DwmUnregisterThumbnail(self, handle):
        self.calls.append(("unregister", handle.value))
        if self.fail == "unregister":
            return 1
        self.relationships.remove(handle.value)
        return 0

    def GetCapture(self):
        return self.capture

    def SetCapture(self, hwnd):
        assert hwnd in self.owned
        self.capture = hwnd

    def ReleaseCapture(self):
        self.capture = None

    def GetCursorPos(self, pointer):
        pointer._obj.x, pointer._obj.y = self.cursor
        return True

    def PeekMessageW(self, *args):
        return False


@pytest.fixture
def make(monkeypatch):
    from wingman.preview import companionwindow
    from wingman.preview.companions import SourceBinding
    from wingman.preview.companionwindow import CompanionWindow

    monkeypatch.setattr(companionwindow, "_ensure_class", lambda libs: None)
    native = WindowOS()
    binding = SourceBinding(
        10, 20, 42, r"c:\tools\browser.exe", "Browser", "Mapper", (1280, 720)
    )
    activated, geometry = [], []

    def create(region=None):
        return CompanionWindow.create(
            native.libs,
            binding,
            Rect(50, 60, 320, 180),
            region,
            on_activate=lambda: activated.append(True),
            on_geometry=geometry.append,
        )

    return create, native, activated, geometry


@pytest.mark.parametrize("region", [None, Rect(100, 200, 400, 300)])
def test_hidden_initial_dwm_is_client_only_and_moves_owned_destination(make, region):
    create, native, _, _ = make
    window = create(region)
    assert window is not None and window.hidden
    assert not any(call[0] == "show" for call in native.calls)
    props = native.props[-1]
    assert props.fSourceClientAreaOnly and not props.fVisible
    assert bool(props.dwFlags & win32.DWM_TNP_RECTSOURCE) == (region is not None)
    if region:
        assert (
            props.rcSource.left,
            props.rcSource.top,
            props.rcSource.right,
            props.rcSource.bottom,
        ) == (100, 200, 500, 500)
    window.set_hidden(False)
    window.move(Rect(-400, 20, 640, 360))
    assert ("move", 100, Rect(-400, 20, 640, 360)) in native.calls
    assert window.close()
    assert not native.owned and not native.relationships


@pytest.mark.parametrize("failure", ["unregister", "destroy"])
def test_failed_cleanup_keeps_owner_and_retries_without_double_release(make, failure):
    create, native, _, _ = make
    window = create()
    native.fail = failure
    assert window.close() is False
    assert window.hwnd == 100
    native.fail = None
    assert window.close() is True
    assert window.close() is True
    assert not native.owned and not native.relationships


def test_click_activates_but_drag_only_moves_preview(make):
    create, native, activated, geometry = make
    window = create()
    window.set_hidden(False)
    window._on_message(win32.WM_LBUTTONDOWN, 0, 0)
    window._on_message(win32.WM_LBUTTONUP, 0, 0)
    assert activated == [True]
    window._on_message(win32.WM_LBUTTONDOWN, 0, 0)
    native.cursor = (100, 50)
    window._on_message(win32.WM_LBUTTONUP, 0, 0)
    assert activated == [True]
    assert geometry == [Rect(150, 110, 320, 180)]
    window.close()


def test_revocation_during_visible_update_never_shows_candidate(make):
    create, native, _, _ = make
    window = create()
    window.set_hidden(False, authorized=lambda: False)
    assert window.hidden
    assert not any(
        call == ("show", 100, win32.SW_SHOWNOACTIVATE) for call in native.calls
    )
    window.close()
