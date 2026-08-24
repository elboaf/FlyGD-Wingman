"""Preview geometry. Pure integer arithmetic -- no Windows, no Pillow.

All rects are absolute virtual-desktop pixels. Conversion to a window's
own client coordinates happens at the Win32 boundary, not here, so this
module stays testable on any platform.
"""
from typing import NamedTuple

EDGE_MARGIN = 18   # gap from the screen edge for the default stack
STACK_GAP = 10     # vertical gap between stacked previews
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
    return Rect(_snap_axis(rect.x, xs, threshold),
                _snap_axis(rect.y, ys, threshold), rect.w, rect.h)


def hit_resize_handle(rect: Rect, px: int, py: int,
                      handle: int = RESIZE_HANDLE) -> bool:
    return (rect.right - handle <= px <= rect.right
            and rect.bottom - handle <= py <= rect.bottom)


def thumbnail_rect(rect: Rect, border: int, label_h: int) -> Rect:
    """The client-coordinate rect the DWM thumbnail is drawn into.

    Clamped at zero: a preview dragged smaller than its own chrome would
    otherwise produce an inverted rect, which DWM rejects.
    """
    return Rect(border, border + label_h,
                max(0, rect.w - border * 2),
                max(0, rect.h - border - border - label_h))
