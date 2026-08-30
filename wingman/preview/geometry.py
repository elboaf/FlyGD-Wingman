"""Preview geometry. Pure integer arithmetic -- no Windows, no Pillow.

All rects are absolute virtual-desktop pixels. Conversion to a window's
own client coordinates happens at the Win32 boundary, not here, so this
module stays testable on any platform.
"""

import re
from typing import NamedTuple

EDGE_MARGIN = 18  # gap from the screen edge for the default stack
STACK_GAP = 10  # vertical gap between stacked previews
RESIZE_HANDLE = 16


class Rect(NamedTuple):
    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h


def default_stack(index: int, screen: Rect, size: tuple) -> Rect:
    """Place preview *index* down the right edge, wrapping into columns.

    Wrapping is not decoration: twenty clients at 210px tall overflow a
    1080p screen after four, and a preview placed off-screen cannot be
    dragged back.
    """
    w, h = size
    per_column = max(1, (screen.h - EDGE_MARGIN) // (h + STACK_GAP))
    column, row = divmod(index, per_column)
    x = screen.right - w - EDGE_MARGIN - column * (w + STACK_GAP)
    y = screen.y + EDGE_MARGIN + row * (h + STACK_GAP)
    return Rect(x, y, w, h)


def _snap_axis(value: int, targets: list, threshold: int) -> int:
    best, best_delta = value, threshold + 1
    for t in targets:
        delta = abs(t - value)
        if delta < best_delta:
            best, best_delta = t, delta
    return best if best_delta <= threshold else value


def snap(rect: Rect, others: list, screen: Rect, threshold: int = 12) -> Rect:
    """Pull *rect* onto nearby preview edges and screen edges."""
    xs = [screen.x, screen.right - rect.w]
    ys = [screen.y, screen.bottom - rect.h]
    for o in others:
        xs += [o.x, o.right, o.right - rect.w, o.x - rect.w]
        ys += [o.y, o.bottom, o.bottom - rect.h, o.y - rect.h]
    return Rect(
        _snap_axis(rect.x, xs, threshold),
        _snap_axis(rect.y, ys, threshold),
        rect.w,
        rect.h,
    )


def hit_resize_handle(
    rect: Rect, px: int, py: int, handle: int = RESIZE_HANDLE
) -> bool:
    return (
        rect.right - handle <= px <= rect.right
        and rect.bottom - handle <= py <= rect.bottom
    )


def thumbnail_rect(rect: Rect, border: int) -> Rect:
    """The client-coordinate rect the DWM thumbnail is drawn into.

    Clamped at zero: a preview dragged smaller than its own chrome would
    otherwise produce an inverted rect, which DWM rejects.

    No label term: the character name is an overlay window riding above
    the video (see chrome.render_label), not a band the picture must
    shrink to make room for, so the thumbnail runs the full interior at
    every size.
    """
    return Rect(
        border,
        border,
        max(0, rect.w - border * 2),
        max(0, rect.h - border * 2),
    )


def virtual_desktop(metrics) -> Rect:
    """Bounding rectangle of every monitor, from four GetSystemMetrics values.

    This is NOT the union of the monitors. SM_*VIRTUALSCREEN describes the
    smallest rectangle containing them all, so any arrangement that is not
    flush-aligned leaves dead zones inside it that belong to no display.
    Placement must therefore be clamped with `clamp_to_monitors`; treating
    this rect as safe space is what put previews off-screen.

    Pure so the negative-origin case is testable: a monitor to the left of
    or above the primary makes x or y negative, and code that assumes a
    (0, 0) origin places previews off-screen on exactly the multi-monitor
    setups this feature exists for.

    *metrics* is a callable taking an SM_ index, so the Win32 call stays
    at the boundary.
    """
    return Rect(metrics(76), metrics(77), metrics(78), metrics(79))


def stack_monitor(monitors: list, screen: Rect) -> Rect:
    """The display `default_stack` should build down.

    The default stack has always run down the right-hand edge. Handing it
    the virtual desktop makes that the right edge of the BOUNDING BOX,
    whose top belongs to whichever monitor happens to reach highest --
    usually not the one the stack is actually descending. Rows then start
    above the target display, and the first one lands in dead space.

    Clamping alone cannot repair that. A clamped row 0 is pulled down onto
    row 1, and row 1 itself keeps a partial overhang: it overlaps the
    monitor enough to escape the clamp while its label band, which is the
    top ~35px, stays in the dead zone.

    Choosing the rightmost display and stacking inside it fixes both at
    the source, and keeps the x-coordinate the stack already used -- the
    rightmost monitor's right edge is the bounding box's right edge.

    Falls back to *screen* when enumeration gave nothing, which reproduces
    the previous behaviour rather than inventing a new one.
    """
    if not monitors:
        return screen
    # Tie broken by the topmost, so a stacked pair of right-edge monitors
    # is deterministic rather than dependent on enumeration order.
    return max(monitors, key=lambda m: (m.right, -m.y))


def _intersects(rect: Rect, monitor: Rect) -> bool:
    return not (
        rect.right <= monitor.x
        or rect.x >= monitor.right
        or rect.bottom <= monitor.y
        or rect.y >= monitor.bottom
    )


def clamp_to_monitors(rect: Rect, monitors: list) -> Rect:
    """Pull *rect* onto the nearest monitor if it is on none of them.

    `virtual_desktop` is a bounding rectangle, not the union of the
    monitors inside it. Whenever monitors are not flush-aligned -- a 4K
    primary spanning y 0..2160 beside a 1440p panel starting at y 291, say
    -- the difference is dead zone: coordinates that are inside the
    bounding box and on no display at all.

    A preview placed there is not merely misplaced, it is unrecoverable.
    It renders to nothing, so the user cannot find it, and it cannot be
    dragged, so it can never acquire the saved position that would rescue
    it on the next launch.

    It is the FIRST preview of a column that lands there -- `default_stack`
    anchors row 0 at `screen.y + EDGE_MARGIN`, which is the top of the
    bounding box rather than the top of any monitor. Later rows clear the
    dead zone on their own. That makes this the common case rather than a
    rare one: the first preview placed when none are saved yet.

    The same clamp covers a saved layout whose monitor has since been
    unplugged, which fails identically and for the same reason.

    Monitors are passed in rather than read here so this stays pure: the
    Win32 enumeration belongs at the boundary, and the dead-zone case is
    only testable off-Windows if the arrangement is an argument.
    """
    if not monitors or any(_intersects(rect, m) for m in monitors):
        return rect

    def distance(m: Rect) -> int:
        # Distance between the RECTS, not between their centres. Centre
        # distance is wrong in a way that only shows on mixed sizes: a
        # small monitor's centre sits close to its own edges, so a distant
        # small display can beat an immediately adjacent large one. A rect
        # 10px off the side of a 4K primary would be thrown onto a 1024x768
        # corner panel 1132px away. Zero for a monitor that contains it.
        dx = max(m.x - rect.right, rect.x - m.right, 0)
        dy = max(m.y - rect.bottom, rect.y - m.bottom, 0)
        return dx * dx + dy * dy

    target = min(monitors, key=distance)
    # max(...) on the upper bound keeps a preview larger than the monitor
    # pinned to the monitor's origin. Without it the upper bound goes
    # negative, and the rect ends up hanging off the origin side instead.
    x = min(max(rect.x, target.x), max(target.x, target.right - rect.w))
    y = min(max(rect.y, target.y), max(target.y, target.bottom - rect.h))
    return Rect(x, y, rect.w, rect.h)


_SIZE_RE = re.compile(r"^\s*(\d{1,5})\s*[xX×]\s*(\d{1,5})\s*$")  # noqa: RUF001


def parse_size(text):
    """Parse "1280x720" into a (w, h) pair, or None.

    Same contract as gestures.parse: None for anything not accepted, never
    an exception. Deliberately does NOT clamp -- the floor belongs to the
    caller, which knows the chrome, and a parser that silently repaired a
    typo would hand back a size the user never typed.
    """
    if not isinstance(text, str):
        return None
    match = _SIZE_RE.match(text)
    if not match:
        return None
    w, h = int(match.group(1)), int(match.group(2))
    if w <= 0 or h <= 0:
        return None
    return w, h


def lock_to_aspect(w, h, aspect, chrome, min_size, drive="w"):
    """The nearest window size whose PICTURE is *aspect* wide per unit tall.

    *chrome* is (dw, dh): the pixels the window spends on its border. It
    is a parameter and not a constant because the caller owns the
    border's value; today every caller passes (BORDER*2, BORDER*2), since
    the character name became an overlay that reserves no space -- the
    parameter stays because "the window is not all picture" is the
    function's contract, not an implementation detail of one caller.

    *drive* names the axis to believe, "w" or "h"; the other is derived.
    It is the caller's job to decide, because only the caller knows which
    way the pointer actually moved. Anything that is not "h" is treated as
    "w", because a raise on the preview thread kills the message pump and
    a freeform resize is the better failure. Note what that costs: the one
    live caller (window.resize_result) passes a computed variable, not a
    literal, so a typo here does not raise -- it silently reinstates the
    old dead-handle-in-Y behaviour. `drive="height"` is exactly `"w"`.

    This used to take `pw = max(pw, ph * aspect)` instead -- believe
    whichever axis implies the LARGER picture -- to stop a mostly-vertical
    drag being inert. It did that, and in exchange it made SHRINKING
    impossible: on a rect already at the locked ratio, which is every rect
    after the first locked drag, a pure-horizontal drag left the untouched
    height winning and a pure-vertical drag left the untouched width
    winning. Either one returned the rect byte-identical, so the handle
    was dead in both directions unless the user happened to drag the
    diagonal. Growing worked from either axis throughout, which is what
    made it read as a mystery rather than a limit.

    The floor is applied in PICTURE space and the height re-derived from
    it, so clamping cannot itself distort the result.
    """
    dw, dh = chrome
    if not aspect or aspect <= 0:
        return max(min_size[0], w), max(min_size[1], h)
    pw = max(1, w - dw)
    if drive == "h":
        pw = max(1, h - dh) * aspect
    pw = max(pw, min_size[0] - dw, 1)
    floor_h = max(1, min_size[1] - dh)
    if pw / aspect < floor_h:
        pw = floor_h * aspect
    return round(pw + dw), round(pw / aspect + dh)
