"""Destinations may move; auxiliary sources may only be read/captured."""

from types import SimpleNamespace

import pytest

from wingman.preview import win32
from wingman.preview.chrome import border_color
from wingman.preview.layout import Rect
from wingman.preview.window import BORDER


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
    # The ring rides a real UpdateLayeredWindow; record the bitmaps instead.
    pushed = []
    monkeypatch.setattr(
        companionwindow.layered,
        "push",
        lambda libs, hwnd, img, x, y: pushed.append((hwnd, img, x, y)) or True,
    )
    native.pushed = pushed
    binding = SourceBinding(
        10, 20, 42, r"c:\tools\browser.exe", "Browser", "Mapper", (1280, 720)
    )
    activated, geometry = [], []

    def create(region=None, selection_color=None):
        return CompanionWindow.create(
            native.libs,
            binding,
            Rect(50, 60, 320, 180),
            region,
            on_activate=lambda: activated.append(True),
            on_geometry=geometry.append,
            selection_color=selection_color,
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


@pytest.mark.parametrize("region", [None, Rect(100, 200, 400, 300)])
@pytest.mark.parametrize(
    "delta, expected_size",
    [((100, 0), (420, 180)), ((0, 90), (320, 270)), ((-500, -500), (32, 32))],
)
def test_right_drag_resizes_each_axis_independently(make, region, delta, expected_size):
    create, native, activated, geometry = make
    window = create(region)
    window.set_hidden(False)
    try:
        window._on_message(win32.WM_RBUTTONDOWN, 0, 0)
        native.cursor = delta
        window._on_message(win32.WM_RBUTTONUP, 0, 0)
        expected = Rect(50, 60, *expected_size)
        assert window.rect == expected
        assert geometry == [expected]
        assert not activated
        assert ("move", 100, expected) in native.calls
        # The destination changes, never the chosen source or region.
        assert window.source_rect == region
        assert window.binding.client_size == (1280, 720)
        props = native.props[-1]
        # The thumbnail sits inside the chrome inset, never edge to edge:
        # the ring needs somewhere to draw without being overpainted.
        assert (
            props.rcDestination.right,
            props.rcDestination.bottom,
        ) == (expected_size[0] - BORDER, expected_size[1] - BORDER)
    finally:
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


def _edge(img):
    return img.getpixel((0, 0))


def test_ring_draws_only_while_active_and_unchanged_sweeps_skip_the_push(make):
    """The companion ring mirrors the EVE previews' chrome: same border
    width, same colour source, drawn only while this companion's source
    holds the foreground. Unchanged chrome never re-pushes a bitmap."""
    create, native, _, _ = make
    window = create()
    window.set_hidden(False)
    assert window.active is False
    assert len(native.pushed) == 1  # initial chrome, ringless
    assert _edge(native.pushed[0][1]) == (8, 10, 14, 255)

    window.set_active(True)
    assert len(native.pushed) == 2
    assert _edge(native.pushed[1][1]) == border_color(window.selection_color)
    window.set_active(True)  # idempotent sweeps are free
    assert len(native.pushed) == 2

    window.move(Rect(10, 10, 320, 180))  # geometry alone re-pushes nothing
    assert len(native.pushed) == 2

    window.set_active(False)
    assert len(native.pushed) == 3
    assert _edge(native.pushed[2][1]) == (8, 10, 14, 255)
    window.close()


def test_ring_colour_arrives_at_creation_and_live_through_the_family_seam(make):
    create, native, _, _ = make
    window = create(selection_color="#ff00ff")
    assert window.selection_color == "#ff00ff"
    assert window._chrome_cache_key == (320, 180, False, "#ff00ff")
    window.set_active(True)
    assert _edge(native.pushed[-1][1]) == border_color("#ff00ff")
    window.selection_color = "#00ff00"
    window.set_active(False)
    window.set_active(True)  # recolour participates in the cache key
    assert _edge(native.pushed[-1][1]) == (0, 255, 0, 255)
    window.close()
