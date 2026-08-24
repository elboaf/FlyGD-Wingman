"""Pure geometry: no Windows, no Pillow, runs in CI on Linux."""
import pytest

from obs_youtube_uploader.preview import geometry as g

SCREEN = g.Rect(0, 0, 1920, 1080)


def test_default_stack_starts_at_the_right_edge():
    r = g.default_stack(0, SCREEN, (320, 210))
    assert r.right <= SCREEN.right
    assert r.x == SCREEN.right - 320 - g.EDGE_MARGIN


def test_default_stack_descends_without_overlapping():
    a = g.default_stack(0, SCREEN, (320, 210))
    b = g.default_stack(1, SCREEN, (320, 210))
    assert b.y >= a.bottom


def test_default_stack_wraps_into_a_new_column_when_it_runs_out_of_height():
    """Twenty clients is an ordinary multiboxing setup; the column must not
    walk off the bottom of the screen and leave previews unreachable."""
    last = g.default_stack(19, SCREEN, (320, 210))
    assert last.bottom <= SCREEN.bottom
    assert last.x < g.default_stack(0, SCREEN, (320, 210)).x


def test_snap_aligns_to_a_nearby_edge():
    moving = g.Rect(100, 103, 320, 210)
    other = g.Rect(100, 300, 320, 210)
    assert g.snap(moving, [other], SCREEN).x == 100


def test_snap_ignores_edges_beyond_the_threshold():
    moving = g.Rect(100, 100, 320, 210)
    other = g.Rect(400, 100, 320, 210)
    assert g.snap(moving, [other], SCREEN, threshold=12) == moving


def test_snap_pulls_to_the_screen_edge():
    moving = g.Rect(5, 400, 320, 210)
    assert g.snap(moving, [], SCREEN).x == 0


def test_snap_never_moves_a_rect_further_than_the_threshold():
    """A snap that teleports a preview across the desktop is a bug that
    reads as 'the drag broke', so bound the correction explicitly."""
    moving = g.Rect(500, 500, 320, 210)
    out = g.snap(moving, [g.Rect(508, 500, 320, 210)], SCREEN, threshold=12)
    assert abs(out.x - moving.x) <= 12


def test_hit_resize_handle_is_the_bottom_right_corner():
    r = g.Rect(100, 100, 320, 210)
    assert g.hit_resize_handle(r, r.right - 4, r.bottom - 4)
    assert not g.hit_resize_handle(r, r.x + 4, r.y + 4)


def test_thumbnail_rect_insets_by_border_and_label():
    r = g.Rect(0, 0, 320, 210)
    t = g.thumbnail_rect(r, border=5, label_h=30)
    assert t == g.Rect(5, 35, 310, 170)


@pytest.mark.parametrize("w,h", [(0, 0), (4, 4)])
def test_thumbnail_rect_never_goes_negative(w, h):
    """A preview dragged smaller than its own chrome must clamp, not hand
    DwmUpdateThumbnailProperties an inverted rect."""
    t = g.thumbnail_rect(g.Rect(0, 0, w, h), border=5, label_h=30)
    assert t.w >= 0 and t.h >= 0


def test_virtual_desktop_reads_the_four_metrics():
    m = {76: 0, 77: 0, 78: 3840, 79: 1080}
    assert g.virtual_desktop(m.get) == g.Rect(0, 0, 3840, 1080)


def test_virtual_desktop_handles_a_negative_origin():
    """A monitor left of or above the primary gives a negative origin.
    Code assuming (0, 0) places previews off-screen on exactly the
    multi-monitor setups this feature is for."""
    m = {76: -1920, 77: -200, 78: 3840, 79: 1280}
    d = g.virtual_desktop(m.get)
    assert d == g.Rect(-1920, -200, 3840, 1280)
    assert d.right == 1920 and d.bottom == 1080


def test_default_stack_respects_a_negative_origin_screen():
    """The first preview must land on-screen even when the virtual desktop
    starts left of zero."""
    screen = g.Rect(-1920, 0, 3840, 1080)
    r = g.default_stack(0, screen, (320, 210))
    assert screen.x <= r.x and r.right <= screen.right
