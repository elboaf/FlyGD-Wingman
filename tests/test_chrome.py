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
import sys

import pytest

from obs_youtube_uploader.ui import chrome

# 1000x600 at (100, 100). Deliberately not square and not at the origin, so
# a transposed or origin-relative bug cannot pass by coincidence.
RECT = (100, 100, 1100, 700)


def test_the_middle_of_the_window_is_not_a_resize_zone():
    """None means "not mine", and the caller must chain to the original proc.

    Returning a hit code here would take the mouse away from the page.
    """
    assert chrome.hit_code(RECT, 600, 400) is None


@pytest.mark.parametrize("x, y, expected", [
    (600, 102, chrome.HTTOP),
    (600, 698, chrome.HTBOTTOM),
    (102, 400, chrome.HTLEFT),
    (1098, 400, chrome.HTRIGHT),
    (102, 102, chrome.HTTOPLEFT),
    (1098, 102, chrome.HTTOPRIGHT),
    (102, 698, chrome.HTBOTTOMLEFT),
    (1098, 698, chrome.HTBOTTOMRIGHT),
])
def test_every_edge_and_corner_has_its_own_zone(x, y, expected):
    assert chrome.hit_code(RECT, x, y) == expected


@pytest.mark.parametrize("x, y, expected", [
    # Along the top edge, inside the corner reach but outside the border.
    (108, 102, chrome.HTTOPLEFT),
    (1092, 102, chrome.HTTOPRIGHT),
    # Down the left edge, likewise -- the reach works in both axes.
    (102, 108, chrome.HTTOPLEFT),
    (102, 692, chrome.HTBOTTOMLEFT),
])
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


@pytest.mark.parametrize("scale, y, expected", [
    # Each pair straddles the band's inner limit at that scale:
    # int(BORDER * scale) is 6, 9 and 12 respectively.
    (1.0, 105, chrome.HTTOP), (1.0, 106, None),
    (1.5, 108, chrome.HTTOP), (1.5, 109, None),
    (2.0, 111, chrome.HTTOP), (2.0, 112, None),
])
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
