"""EVE client window placement records. Pure -- runs on any platform.

Mirrors test_preview_layout.py's cases, because placement.deserialize
mirrors layout.deserialize's forgiving posture on purpose: a hand-edited
settings file should cost one character's position, not the launch.
"""
import pytest

from obs_youtube_uploader.preview import placement
from obs_youtube_uploader.preview.geometry import Rect

SCREEN = Rect(0, 0, 1920, 1080)


def test_round_trip_preserves_rect_and_state():
    entries = {"Pilot One": placement.Placement(Rect(10, 20, 800, 600), True)}
    assert placement.deserialize(placement.serialize(entries)) == entries


@pytest.mark.parametrize("raw", [None, [], "nope", 3])
def test_a_non_dict_deserializes_to_nothing(raw):
    assert placement.deserialize(raw) == {}


def test_a_corrupt_entry_drops_alone():
    """One bad entry must not cost the others -- settings.py's posture."""
    out = placement.deserialize({
        "Good": {"x": 1, "y": 2, "w": 3, "h": 4},
        "Bad": {"x": "nope", "y": 2, "w": 3, "h": 4},
        "Missing": {"x": 1, "y": 2},
    })
    assert list(out) == ["Good"]


@pytest.mark.parametrize("w,h", [(0, 100), (100, 0), (-5, 100)])
def test_non_positive_dimensions_drop_the_entry(w, h):
    assert placement.deserialize({"P": {"x": 0, "y": 0, "w": w, "h": h}}) == {}


def test_maximized_defaults_to_false_when_absent():
    out = placement.deserialize({"P": {"x": 0, "y": 0, "w": 8, "h": 6}})
    assert out["P"].maximized is False


def test_workspace_and_screen_are_inverse_with_a_top_taskbar():
    """A taskbar docked top or left makes the work-area origin non-zero,
    and rcNormalPosition is offset by exactly that."""
    origin = (0, 40)
    rect = Rect(100, 200, 800, 600)
    assert placement.to_screen(rect, origin) == Rect(100, 240, 800, 600)
    assert placement.to_workspace(placement.to_screen(rect, origin),
                                  origin) == rect


def test_a_bottom_taskbar_offset_is_a_no_op():
    rect = Rect(100, 200, 800, 600)
    assert placement.to_screen(rect, (0, 0)) == rect


def test_a_fully_visible_rect_is_reachable():
    assert placement.is_reachable(Rect(100, 100, 800, 600), SCREEN)


def test_a_rect_on_a_vanished_monitor_is_not_reachable():
    assert not placement.is_reachable(Rect(3000, 100, 800, 600), SCREEN)


def test_a_few_pixels_of_overlap_is_not_reachable():
    """The bug an any-intersection test would ship: this rect touches the
    desktop by 5px, but nothing grabbable is on screen."""
    assert not placement.is_reachable(Rect(1915, 100, 800, 600), SCREEN)


def test_a_rect_whose_title_bar_is_above_the_desktop_is_not_reachable():
    """Body visible, title bar off the top -- the classic unrecoverable
    window. Only the top band counts, so this must be rejected."""
    assert not placement.is_reachable(Rect(100, -200, 800, 600), SCREEN)


def test_a_window_narrower_than_the_grab_threshold_still_counts():
    """min_w must not reject a fully-visible window that is simply small."""
    assert placement.is_reachable(Rect(100, 100, 80, 60), SCREEN)


def test_a_negative_origin_desktop_is_handled():
    """A monitor left of the primary makes the virtual desktop origin
    negative; code assuming (0, 0) rejects perfectly valid rects."""
    screen = Rect(-1920, 0, 3840, 1080)
    assert placement.is_reachable(Rect(-1800, 100, 800, 600), screen)
