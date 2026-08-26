"""Pure geometry: no Windows, no Pillow, runs in CI on Linux."""

import itertools

import pytest

from wingman.preview import geometry as g

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


# --- Monitors are not the virtual desktop -----------------------------------
#
# SM_*VIRTUALSCREEN gives the bounding RECTANGLE of all monitors, not their
# union. Whenever monitors are not flush-aligned, the bounding box contains
# dead zones that belong to no display. A rect placed there is invisible and,
# because it cannot be grabbed, can never be dragged back.
#
# Reproduces a real arrangement: a 4K primary at 192 DPI spanning y 0..2160,
# with two 1440p monitors either side whose tops sit ~300px lower.
REAL_MONITORS = [
    g.Rect(3840, 291, 2560, 1440),  # right, y 291..1731
    g.Rect(-2560, 306, 2560, 1440),  # left,  y 306..1746
    g.Rect(0, 0, 3840, 2160),  # primary, the only one reaching y=0
]
REAL_VIRTUAL = g.Rect(-2560, 0, 8960, 2160)


def test_clamp_leaves_a_rect_that_is_already_on_a_monitor_alone():
    on_primary = g.Rect(100, 100, 320, 210)
    assert g.clamp_to_monitors(on_primary, REAL_MONITORS) == on_primary


def test_clamp_pulls_a_rect_in_a_dead_zone_onto_a_monitor():
    """The gap above the right-hand monitor is inside the virtual desktop's
    bounding box but belongs to no display.

    Asserts the exact rect, not merely "somewhere visible": which monitor
    is chosen is the most debatable decision in the clamp, and an
    assertion that only checks for intersection passes just as happily
    with the nearest-monitor search inverted."""
    dead = g.Rect(6062, 18, 320, 210)
    # Straight down onto the right-hand panel, whose top edge is y=291.
    assert g.clamp_to_monitors(dead, REAL_MONITORS) == g.Rect(6062, 291, 320, 210)


def test_clamp_measures_distance_to_the_monitor_not_to_its_centre():
    """A small display far away must not beat a large one right next door.

    Centre distance gets this wrong: a small monitor's centre sits close
    to its own edges, so it wins comparisons it has no business winning.
    Here the rect is 10px off the primary's right edge, and the corner
    panel's nearest edge is over 1100px away."""
    primary = g.Rect(0, 0, 3840, 2160)
    corner = g.Rect(3840, 0, 1024, 768)
    just_off_the_primary = g.Rect(3850, 1900, 320, 210)
    landed = g.clamp_to_monitors(just_off_the_primary, [primary, corner])
    assert landed.x < corner.x, landed
    assert landed == g.Rect(3520, 1900, 320, 210)


def test_clamp_pins_a_preview_larger_than_the_monitor_to_its_origin():
    """The upper bound goes negative for an oversize rect, so an unguarded
    min() would hang it off the origin side instead."""
    small = g.Rect(0, 0, 800, 600)
    huge = g.Rect(2000, 2000, 1200, 900)
    assert g.clamp_to_monitors(huge, [small]) == g.Rect(0, 0, 1200, 900)


def test_clamp_keeps_the_rect_fully_within_the_monitor_it_lands_on():
    dead = g.Rect(6062, 18, 320, 210)
    fixed = g.clamp_to_monitors(dead, REAL_MONITORS)
    host = next(m for m in REAL_MONITORS if _intersects(fixed, m))
    assert fixed.x >= host.x and fixed.right <= host.right
    assert fixed.y >= host.y and fixed.bottom <= host.bottom


def test_clamp_rescues_a_saved_rect_on_a_monitor_that_was_unplugged():
    """A layout saved against a monitor that is no longer attached must not
    resurrect the preview into empty space."""
    gone = g.Rect(-5000, 400, 320, 210)
    fixed = g.clamp_to_monitors(gone, REAL_MONITORS)
    assert any(_intersects(fixed, m) for m in REAL_MONITORS), fixed


def test_clamp_without_any_monitors_returns_the_rect_unchanged():
    """EnumDisplayMonitors returning nothing is not a reason to move a
    preview to the origin."""
    r = g.Rect(100, 100, 320, 210)
    assert g.clamp_to_monitors(r, []) == r


# --- Defaults stack down a monitor, not down the bounding box ---------------


def test_stack_monitor_is_the_rightmost_display():
    """The default stack has always built down the right edge; that must
    keep meaning the right edge of a screen."""
    assert g.stack_monitor(REAL_MONITORS, REAL_VIRTUAL) == REAL_MONITORS[0]


def test_stack_monitor_falls_back_to_the_bounding_box_with_no_monitors():
    assert g.stack_monitor([], REAL_VIRTUAL) == REAL_VIRTUAL


def test_defaults_stacked_on_a_monitor_start_below_its_top_edge():
    """Anchored to the monitor's own top (291), not the bounding box's (0).
    Clamping alone could not fix this: index 1 lands at y=238, which
    overlaps the monitor enough to escape the clamp while leaving its
    label band in the dead zone."""
    mon = g.stack_monitor(REAL_MONITORS, REAL_VIRTUAL)
    assert g.default_stack(0, mon, (320, 210)) == g.Rect(6062, 309, 320, 210)


def test_defaults_stacked_on_a_monitor_never_overlap_each_other():
    """The clamp pulled index 0 down onto index 1, which is a regression
    the clamp itself introduced. Stacking down the monitor avoids it."""
    mon = g.stack_monitor(REAL_MONITORS, REAL_VIRTUAL)
    placed = [g.default_stack(i, mon, (320, 210)) for i in range(6)]
    for a, b in itertools.pairwise(placed):
        assert b.y >= a.bottom, (a, b)


def test_defaults_stacked_on_a_monitor_are_fully_on_it():
    """Not merely intersecting: a preview whose label band is off-screen is
    unlabelled, and one whose resize corner is off-screen cannot be
    resized."""
    mon = g.stack_monitor(REAL_MONITORS, REAL_VIRTUAL)
    for i in range(6):
        r = g.default_stack(i, mon, (320, 210))
        assert r.x >= mon.x and r.right <= mon.right, (i, r)
        assert r.y >= mon.y and r.bottom <= mon.bottom, (i, r)


def test_default_stack_on_the_real_arrangement_is_off_screen_without_clamping():
    """Regression for the bug this clamp exists to fix: the first defaulted
    preview lands 273px above the top of the only monitor beneath it."""
    placed = g.default_stack(0, REAL_VIRTUAL, (320, 210))
    assert not any(_intersects(placed, m) for m in REAL_MONITORS)
    rescued = g.clamp_to_monitors(placed, REAL_MONITORS)
    assert any(_intersects(rescued, m) for m in REAL_MONITORS), rescued


def _intersects(r, m):
    return not (r.right <= m.x or r.x >= m.right or r.bottom <= m.y or r.y >= m.bottom)


# --- Task 1: parse_size ---


def test_parse_size_accepts_the_obvious_spelling():
    assert g.parse_size("1280x720") == (1280, 720)


def test_parse_size_tolerates_spacing_and_capital_x():
    assert g.parse_size("  640 X 360 ") == (640, 360)
    assert g.parse_size("640×360") == (640, 360)  # noqa: RUF001


def test_parse_size_rejects_junk_rather_than_raising():
    """Same contract as gestures.parse: the caller gets None, never an
    exception, because this runs on typed input."""
    for text in ("", "x", "640", "640x", "axb", "640x720x480", None, 640):
        assert g.parse_size(text) is None


def test_parse_size_rejects_zero_and_negative():
    assert g.parse_size("0x720") is None
    assert g.parse_size("-640x360") is None


def test_parse_size_does_not_clamp():
    """The floor belongs to the caller, which knows the chrome. A parser
    that silently repaired a typo would hand back a size nobody typed."""
    assert g.parse_size("1x1") == (1, 1)


# --- Task 2: lock_to_aspect ---


LABELS_ON = (4, 34)  # BORDER * 2, BORDER * 2 + LABEL_H
LABELS_OFF = (4, 4)  # the same window with show_labels off
FLOOR = (120, 90)


def _picture(size, chrome):
    return size[0] - chrome[0], size[1] - chrome[1]


def test_lock_to_aspect_matches_the_picture_not_the_window():
    """The label band is not part of the picture. Locking the WINDOW to
    16:9 leaves the picture stretched by exactly the band's height."""
    w, h = g.lock_to_aspect(640, 999, 16 / 9, LABELS_ON, FLOOR)
    pw, ph = _picture((w, h), LABELS_ON)
    assert abs(pw / ph - 16 / 9) < 0.01


def test_lock_to_aspect_uses_the_chrome_it_is_given():
    """Labels off removes 30px of band, so the same window width needs a
    different window height for the same picture shape. A fixed chrome
    distorts the picture for everyone who turned labels off -- silently,
    while the control reports success."""
    on = g.lock_to_aspect(1284, 100, 16 / 9, LABELS_ON, FLOOR)
    off = g.lock_to_aspect(1284, 100, 16 / 9, LABELS_OFF, FLOOR)
    assert on[0] == off[0] == 1284
    assert on[1] - off[1] == 30


def test_lock_to_aspect_lets_a_vertical_drag_do_something():
    """Driving from width alone would make a downward drag inert. The
    axis is now the caller's to name rather than inferred from whichever
    one implies the larger picture, but the guarantee is unchanged."""
    grown = g.lock_to_aspect(640, 900, 16 / 9, LABELS_ON, FLOOR, drive="h")
    assert grown[0] > 640


def test_lock_to_aspect_applies_the_floor_without_distorting():
    """The clamp must not be the thing that breaks the ratio."""
    w, h = g.lock_to_aspect(1, 1, 16 / 9, LABELS_ON, FLOOR)
    assert w >= FLOOR[0] and h >= FLOOR[1]
    pw, ph = _picture((w, h), LABELS_ON)
    assert abs(pw / ph - 16 / 9) < 0.01


def test_lock_to_aspect_applies_the_floor_through_the_height_branch_too():
    """The floor clamp lives after the drive branch, so it has to hold for
    both. Only the width branch was covered when `drive` was added, and
    the height branch is the half this change introduced."""
    for w, h in ((1, 1000), (1000, 1), (1, 1)):
        out = g.lock_to_aspect(w, h, 16 / 9, LABELS_ON, FLOOR, drive="h")
        assert out[0] >= FLOOR[0] and out[1] >= FLOOR[1]
        pw, ph = _picture(out, LABELS_ON)
        assert abs(pw / ph - 16 / 9) < 0.01


def test_lock_to_aspect_without_an_aspect_only_floors():
    """None is the character-select and client-gone fallback: today's
    freeform behaviour, unchanged."""
    assert g.lock_to_aspect(500, 400, None, LABELS_ON, FLOOR) == (500, 400)
    assert g.lock_to_aspect(10, 10, None, LABELS_ON, FLOOR) == (120, 90)


def test_lock_to_aspect_shrinks_from_a_horizontal_drag():
    """Dragging the handle inward along X alone must make the window
    smaller. Deriving the picture from `max(pw, ph * aspect)` made the
    untouched height win every time, so a pure-horizontal shrink was a
    dead handle -- the window did not move a pixel."""
    w, h = g.lock_to_aspect(540, 392, 16 / 9, LABELS_ON, FLOOR, drive="w")
    assert w < 640
    pw, ph = _picture((w, h), LABELS_ON)
    assert abs(pw / ph - 16 / 9) < 0.01


def test_lock_to_aspect_shrinks_from_a_vertical_drag():
    """The same dead handle in the other axis: dragging up alone left the
    untouched width driving, so nothing happened."""
    w, h = g.lock_to_aspect(640, 292, 16 / 9, LABELS_ON, FLOOR, drive="h")
    assert h < 392
    pw, ph = _picture((w, h), LABELS_ON)
    assert abs(pw / ph - 16 / 9) < 0.01


def test_lock_to_aspect_drive_picks_which_axis_is_believed():
    """The whole point of the parameter: the same candidate rect resolves
    two different ways depending on which axis the user actually dragged."""
    by_w = g.lock_to_aspect(540, 392, 16 / 9, LABELS_ON, FLOOR, drive="w")
    by_h = g.lock_to_aspect(540, 392, 16 / 9, LABELS_ON, FLOOR, drive="h")
    assert by_w[0] == 540
    assert by_h[1] == 392
    assert by_w != by_h
