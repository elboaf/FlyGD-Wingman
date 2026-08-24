"""Only the gesture arithmetic is tested here -- window creation needs a
desktop and lives in the smoke checklist.

Click-versus-drag is where this goes subtly wrong: a click that moves one
pixel must still focus the client, and a locked preview must never move
but must still activate on release."""
from obs_youtube_uploader.preview import window
from obs_youtube_uploader.preview.geometry import Rect

R = Rect(100, 100, 320, 210)


def test_a_still_press_is_a_click():
    action, rect = window.drag_result((10, 10), (10, 10), R, locked=False,
                                      drag_min=4)
    assert action == "activate" and rect == R


def test_movement_within_the_drag_threshold_is_still_a_click():
    action, _ = window.drag_result((10, 10), (12, 11), R, locked=False,
                                   drag_min=4)
    assert action == "activate"


def test_movement_past_the_threshold_is_a_drag():
    action, rect = window.drag_result((10, 10), (60, 40), R, locked=False,
                                      drag_min=4)
    assert action == "move"
    assert rect == Rect(150, 130, 320, 210)


def test_a_locked_preview_never_moves_but_still_activates():
    """Locking exists so a carefully placed layout survives a stray drag.
    It must not also break click-to-focus."""
    action, rect = window.drag_result((10, 10), (200, 200), R, locked=True,
                                      drag_min=4)
    assert action == "activate" and rect == R


def test_resize_result_floors_at_the_minimum_size():
    """Dragging the handle up and left past zero must clamp, not invert
    the rect -- DWM rejects an inverted destination and the preview goes
    blank with no error."""
    out = window.resize_result((400, 300), (0, 0), R, min_size=(80, 60))
    assert out.w >= 80 and out.h >= 60


def test_resize_grows_from_the_top_left_anchor():
    out = window.resize_result((100, 100), (150, 130), R, min_size=(80, 60))
    assert (out.x, out.y) == (R.x, R.y)
    assert (out.w, out.h) == (R.w + 50, R.h + 30)
