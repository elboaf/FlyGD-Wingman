"""ui/chrome.py -- the resize-border geometry, and the off-Windows guard.

Nothing native runs here. CI is ubuntu (`.github/workflows/ci.yml`), so
WinForms, WebView2 and a message pump are all unavailable, and the
subclass itself can only ever be checked by hand on Windows.

`hit_code` is the part that CAN be covered, which is exactly why chrome.py
builds its Win32 types lazily instead of at module scope -- if importing
the module raised off Windows, this file could not exist and the feature
would ship with no automated coverage at all. That this module imports is
itself part of what these tests assert.
"""

import ctypes
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from wingman.ui import chrome

WEB = Path(__file__).resolve().parents[1] / "wingman" / "web"
APP_JS = (WEB / "app.js").read_text(encoding="utf-8")

# 1000x600 at (100, 100). Deliberately not square and not at the origin, so
# a transposed or origin-relative bug cannot pass by coincidence.
RECT = (100, 100, 1100, 700)


def test_the_middle_of_the_window_is_not_a_resize_zone():
    """None means "not mine", and the caller must chain to the original proc.

    Returning a hit code here would take the mouse away from the page.
    """
    assert chrome.hit_code(RECT, 600, 400) is None


@pytest.mark.parametrize(
    "x, y, expected",
    [
        (600, 102, chrome.HTTOP),
        (600, 698, chrome.HTBOTTOM),
        (102, 400, chrome.HTLEFT),
        (1098, 400, chrome.HTRIGHT),
        (102, 102, chrome.HTTOPLEFT),
        (1098, 102, chrome.HTTOPRIGHT),
        (102, 698, chrome.HTBOTTOMLEFT),
        (1098, 698, chrome.HTBOTTOMRIGHT),
    ],
)
def test_every_edge_and_corner_has_its_own_zone(x, y, expected):
    assert chrome.hit_code(RECT, x, y) == expected


@pytest.mark.parametrize(
    "x, y, expected",
    [
        # Along the top edge, inside the corner reach but outside the border.
        (108, 102, chrome.HTTOPLEFT),
        (1092, 102, chrome.HTTOPRIGHT),
        # Down the left edge, likewise -- the reach works in both axes.
        (102, 108, chrome.HTTOPLEFT),
        (102, 692, chrome.HTBOTTOMLEFT),
    ],
)
def test_corners_reach_further_than_the_edges(x, y, expected):
    """A BORDER-sized corner square is too small to hit reliably.

    CORNER is more than twice BORDER for this reason; these points are
    beyond the border band on one axis but still inside the corner reach.
    """
    assert chrome.hit_code(RECT, x, y) == expected


def test_just_inside_the_border_is_still_the_edge():
    assert chrome.hit_code(RECT, 600, 105) == chrome.HTTOP


def test_just_past_the_border_is_the_page():
    """The band is exclusive at its inner limit.

    BORDER is 6, so y=106 is the first row that belongs to the page. Off by
    one here either steals a row of pixels from the page or gives away a
    row of grab band, and both are invisible until someone is annoyed.
    """
    assert chrome.hit_code(RECT, 600, 106) is None


@pytest.mark.parametrize(
    "scale, y, expected",
    [
        # Each pair straddles the band's inner limit at that scale:
        # int(BORDER * scale) is 6, 9 and 12 respectively.
        (1.0, 105, chrome.HTTOP),
        (1.0, 106, None),
        (1.5, 108, chrome.HTTOP),
        (1.5, 109, None),
        (2.0, 111, chrome.HTTOP),
        (2.0, 112, None),
    ],
)
def test_the_band_scales_with_dpi(scale, y, expected):
    """At 150% the band must stay the same APPARENT thickness.

    Without this the grab target shrinks as the display scales up, and on a
    high-DPI screen it becomes unhittable -- the failure mode is "resizing
    works on my machine" from whoever tested at 100%.
    """
    assert chrome.hit_code(RECT, 600, y, scale) == expected


def test_the_band_never_scales_away_entirely():
    """A pathological scale must not produce a zero-width band.

    int() truncation toward zero would make the border 0 at a small enough
    scale, and every edge would silently stop responding.
    """
    assert chrome.hit_code(RECT, 100, 400, scale=0.01) == chrome.HTLEFT


def test_the_grab_band_never_exceeds_the_inset():
    """BORDER must not out-reach INSET, or part of the band is dead.

    The band is only form surface as far as the inset goes; beyond it the
    WebView2 child owns the pixels and no hit-test ever arrives. A BORDER
    larger than INSET therefore claims a zone that silently does nothing --
    and it fails exactly the way a too-thin band does, so it would be
    diagnosed as "resizing is fiddly" rather than as a bug.

    Both are scaled by the same factor at runtime, so comparing the
    unscaled constants is the whole check.
    """
    assert chrome.BORDER <= chrome.INSET


@pytest.mark.parametrize(
    "x, y, expected",
    [
        (102, 400, chrome.HTLEFT),
        (102, 102, chrome.HTLEFT),
        (102, 698, chrome.HTLEFT),
        (1098, 400, chrome.HTRIGHT),
        (1098, 102, chrome.HTRIGHT),
        (1098, 698, chrome.HTRIGHT),
    ],
)
def test_horizontal_hit_zones_use_only_left_and_right_edges(x, y, expected):
    assert chrome.hit_code(RECT, x, y, edges=chrome.HORIZONTAL_EDGES) == expected


@pytest.mark.parametrize("x, y", [(600, 102), (600, 698)])
def test_horizontal_hit_zones_ignore_top_and_bottom(x, y):
    assert chrome.hit_code(RECT, x, y, edges=chrome.HORIZONTAL_EDGES) is None


def test_horizontal_hit_zones_leave_the_page_interior_alone():
    assert chrome.hit_code(RECT, 600, 400, edges=chrome.HORIZONTAL_EDGES) is None


def test_horizontal_hit_zones_keep_negative_coordinates_signed():
    rect = (-500, 100, 500, 700)
    assert (
        chrome.hit_code(rect, -498, 400, edges=chrome.HORIZONTAL_EDGES) == chrome.HTLEFT
    )


@pytest.mark.parametrize(
    "scale, x, y, expected",
    [
        (1.0, 600, 105, chrome.HTTOP),
        (1.25, 600, 106, chrome.HTTOP),
        (1.5, 600, 108, chrome.HTTOP),
        (2.0, 600, 111, chrome.HTTOP),
    ],
)
def test_explicit_all_edges_preserves_the_default_hit_policy(scale, x, y, expected):
    assert chrome.hit_code(RECT, x, y, scale=scale) == expected
    assert chrome.hit_code(RECT, x, y, scale=scale, edges=chrome.ALL_EDGES) == expected


class _FakeHandle:
    def __init__(self, value=123):
        self._value = value

    def ToInt64(self):
        return self._value


class _FakeNative:
    def __init__(self):
        self.Handle = _FakeHandle()
        self.InvokeRequired = False
        self.Padding = 0
        self.DeviceDpi = 96
        self.ClientRectangle = SimpleNamespace(Width=500, Height=300)
        self.DisplayRectangle = SimpleNamespace(X=0, Y=0, Width=500, Height=300)


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _Rect(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint32),
        ("rcMonitor", _Rect),
        ("rcWork", _Rect),
        ("dwFlags", ctypes.c_uint32),
    ]


class _MINMAXINFO(ctypes.Structure):
    _fields_ = [
        ("ptReserved", _Point),
        ("ptMaxSize", _Point),
        ("ptMaxPosition", _Point),
        ("ptMinTrackSize", _Point),
        ("ptMaxTrackSize", _Point),
    ]


def _fake_horizontal_attach(
    monkeypatch, *, scale=1.0, physical_insets=None, install_ok=True
):
    monkeypatch.setattr(chrome.sys, "platform", "win32")
    monkeypatch.setattr(chrome, "_KEEPALIVE", [])
    monkeypatch.setattr(chrome, "_on_ui_thread", lambda native, fn: fn())
    monkeypatch.setattr(chrome, "_log_geometry", lambda *args, **kwargs: None)

    native = _FakeNative()
    if physical_insets is not None:
        native._physical_insets = physical_insets
    window = SimpleNamespace(native=native)

    wintypes = SimpleNamespace(
        HWND=ctypes.c_void_p,
        HANDLE=ctypes.c_void_p,
        DWORD=ctypes.c_uint32,
        RECT=_Rect,
        POINT=_Point,
        UINT=ctypes.c_uint,
    )
    WNDPROC = ctypes.CFUNCTYPE(
        ctypes.c_ssize_t,
        wintypes.HWND,
        wintypes.UINT,
        ctypes.c_size_t,
        ctypes.c_ssize_t,
    )

    def previous_proc(hwnd, msg, wparam, lparam):
        if msg == chrome.WM_GETMINMAXINFO:
            info = ctypes.cast(lparam, ctypes.POINTER(_MINMAXINFO)).contents
            info.ptMinTrackSize = _Point(320, 250)
            info.ptMaxTrackSize = _Point(5000, 900)
        return 777

    previous_callback = WNDPROC(previous_proc)
    previous_ptr = (
        ctypes.cast(previous_callback, ctypes.c_void_p).value if install_ok else 0
    )
    state = {"previous_callback": previous_callback}

    class _User32:
        def CallWindowProcW(self, proc, hwnd, msg, wparam, lparam):
            state.setdefault("call_window_proc", []).append(msg)
            return proc(hwnd, msg, wparam, lparam)

        def DefWindowProcW(self, hwnd, msg, wparam, lparam):
            state.setdefault("def_window_proc", []).append(msg)
            return -1

        def GetWindowRect(self, hwnd, rect_ptr):
            rect = ctypes.cast(rect_ptr, ctypes.POINTER(_Rect)).contents
            rect.left, rect.top, rect.right, rect.bottom = RECT
            return 1

        def MonitorFromWindow(self, hwnd, flags):
            return 1

        def GetMonitorInfoW(self, monitor, info_ptr):
            info = ctypes.cast(info_ptr, ctypes.POINTER(_MONITORINFO)).contents
            info.rcMonitor = _Rect(0, 0, 1920, 1080)
            info.rcWork = _Rect(0, 0, 1900, 1040)
            return 1

    user32 = _User32()

    def set_ptr(handle, index, callback):
        state["callback"] = callback
        return previous_ptr

    def fake_win32():
        return user32, set_ptr, WNDPROC, _MONITORINFO, _MINMAXINFO, wintypes

    def fake_apply_inset(native, *args, **kwargs):
        pad = kwargs.get("pad")
        if pad is None:
            pad = args[0] if args else 0
        edges = kwargs.get("edges")
        if edges is None and len(args) > 1:
            edges = args[1]
        if edges is None:
            edges = chrome.ALL_EDGES
        if pad == 0:
            left = top = right = bottom = 0
        else:
            left, top, right, bottom = getattr(
                native,
                "_physical_insets",
                (
                    pad if "left" in edges else 0,
                    pad if "top" in edges else 0,
                    pad if "right" in edges else 0,
                    pad if "bottom" in edges else 0,
                ),
            )
        native.Padding = pad
        native.DisplayRectangle = SimpleNamespace(
            X=left,
            Y=top,
            Width=native.ClientRectangle.Width - left - right,
            Height=native.ClientRectangle.Height - top - bottom,
        )

    monkeypatch.setattr(chrome, "_win32", fake_win32)
    monkeypatch.setattr(chrome, "_scale_for", lambda user32, handle: scale)
    monkeypatch.setattr(chrome, "_apply_inset", fake_apply_inset)
    return SimpleNamespace(
        window=window,
        native=native,
        state=state,
        MINMAXINFO=_MINMAXINFO,
    )


@pytest.mark.parametrize(
    ("scale", "physical_insets", "expected_tracks"),
    [
        pytest.param(1.0, (6, 0, 6, 0), (432, 732), id="100%"),
        pytest.param(1.25, (7, 0, 8, 0), (540, 915), id="125%"),
        pytest.param(1.5, (9, 0, 9, 0), (648, 1098), id="150%"),
        pytest.param(2.0, (12, 0, 12, 0), (864, 1464), id="200%"),
    ],
)
def test_enable_horizontal_resize_reports_logical_insets_and_physical_outer_track_widths(
    monkeypatch, scale, physical_insets, expected_tracks
):
    attached = _fake_horizontal_attach(
        monkeypatch, scale=scale, physical_insets=physical_insets
    )

    insets = chrome.enable_horizontal_resize(
        attached.window, min_content_width=420, max_content_width=720
    )

    assert insets == chrome.ResizeInsets(left=6, top=0, right=6, bottom=0)
    assert insets.horizontal == 12

    info = attached.MINMAXINFO()
    result = attached.state["callback"](
        123, chrome.WM_GETMINMAXINFO, 0, ctypes.addressof(info)
    )

    assert result == 777
    assert (info.ptMinTrackSize.x, info.ptMaxTrackSize.x) == expected_tracks
    assert (info.ptMinTrackSize.y, info.ptMaxTrackSize.y) == (250, 900)


def test_enable_horizontal_resize_removes_the_inset_if_wndproc_install_fails(
    monkeypatch,
):
    attached = _fake_horizontal_attach(monkeypatch, install_ok=False)

    assert (
        chrome.enable_horizontal_resize(
            attached.window, min_content_width=420, max_content_width=720
        )
        is None
    )
    assert attached.native.Padding == 0
    assert attached.native.DisplayRectangle.X == 0
    assert attached.native.DisplayRectangle.Y == 0


class _Explosive:
    """A window that fails the test if anything is read off it."""

    @property
    def native(self):
        raise AssertionError("enable_resize touched the window off Windows")


@pytest.mark.skipif(sys.platform == "win32", reason="the guard under test")
def test_enable_resize_is_a_no_op_off_windows():
    """Off Windows it must return False without touching the window.

    Development happens on Linux, and the guard is what lets window.py call
    this unconditionally instead of duplicating a platform check.
    """
    assert chrome.enable_resize(_Explosive()) is False


def test_enable_resize_survives_a_window_with_no_native_handle():
    """`native` is None until the window is shown (winforms.py:195).

    Being called too early must degrade to a fixed-size window, not raise
    into whatever was mid-launch.
    """

    class NotShownYet:
        native = None

    assert chrome.enable_resize(NotShownYet()) is False


def test_the_settings_gear_badge_updates_its_accessible_name_from_update_status():
    assert "function renderUpdateBadge(payload)" in APP_JS
    assert "var available = !!payload.update_available;" in APP_JS
    title_line = "gear.title = available ? 'Settings — update available' : 'Settings';"

    assert "gear.classList.toggle('update-available', available);" in APP_JS
    assert title_line in APP_JS
    assert "gear.setAttribute('aria-label', gear.title);" in APP_JS
    assert "new CustomEvent('wm:update-status', {detail: payload})" in APP_JS
