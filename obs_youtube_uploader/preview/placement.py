"""EVE client window placement. Pure: dict in, dict out.

Distinct from layout.py, which persists where the preview TILES sit. These
two share a stable key and nothing else -- one records the game windows,
the other the thumbnails floating over them.

The caller owns the file, for the reason layout.py states: settings.save()
projects the complete document and has more than one writer. See
settings.update() for the boundary this module's consumer writes through.
"""
from typing import NamedTuple

from .geometry import Rect

# The window's first TITLE_BAND_H pixels hold the title bar and the
# draggable frame -- the region a mouse actually needs to reach.
TITLE_BAND_H = 32
MIN_GRAB_W = 120


class Placement(NamedTuple):
    rect: Rect
    maximized: bool = False


def serialize(entries: dict) -> dict:
    return {
        key: {"x": p.rect.x, "y": p.rect.y, "w": p.rect.w, "h": p.rect.h,
              "maximized": bool(p.maximized)}
        for key, p in entries.items()
    }


def deserialize(raw) -> dict:
    """Rebuild placements, dropping anything malformed.

    Deliberately forgiving, matching layout.deserialize and settings.py's
    validation posture: a hand-edited or partially-written settings file
    should cost one character's saved position, not the launch.
    """
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        try:
            x, y, w, h = (int(value["x"]), int(value["y"]),
                          int(value["w"]), int(value["h"]))
        except (KeyError, TypeError, ValueError):
            continue
        if w <= 0 or h <= 0:
            continue
        out[key] = Placement(Rect(x, y, w, h),
                             bool(value.get("maximized", False)))
    return out


def to_screen(rect: Rect, origin: tuple) -> Rect:
    """Workspace -> screen. WINDOWPLACEMENT.rcNormalPosition is in
    workspace coordinates, offset from screen coordinates by the primary
    monitor's work-area origin: (0, 0) for a taskbar docked bottom or
    right, non-zero for one docked top or left.

    Stored values are screen coordinates so they can be checked against
    geometry.virtual_desktop(). Raw workspace values cannot be compared
    against anything.
    """
    ox, oy = origin
    return Rect(rect.x + ox, rect.y + oy, rect.w, rect.h)


def to_workspace(rect: Rect, origin: tuple) -> Rect:
    ox, oy = origin
    return Rect(rect.x - ox, rect.y - oy, rect.w, rect.h)


def is_reachable(rect: Rect, screen: Rect, band_h: int = TITLE_BAND_H,
                 min_w: int = MIN_GRAB_W) -> bool:
    """Can the user actually grab this window if we put it here?

    NOT a bare intersection test. A rect can overlap the virtual desktop
    by a single pixel, or hang its title bar off the top edge, while
    remaining impossible to see or drag -- and stranding a client is the
    worst outcome available to a feature whose whole job is moving
    windows. So the question asked is whether the window's TOP BAND is on
    screen by at least a real grab target's width.

    min_w is capped at the window's own width so a legitimately narrow
    window that is fully visible is not rejected.
    """
    band_bottom = rect.y + min(band_h, rect.h)
    overlap_w = min(rect.right, screen.right) - max(rect.x, screen.x)
    overlap_h = min(band_bottom, screen.bottom) - max(rect.y, screen.y)
    return overlap_w >= min(min_w, rect.w) and overlap_h > 0
