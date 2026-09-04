"""Pure prototype crop model: geometry and stage helpers for crop probe.

All functions are pure (no side effects) and accept/return simple types:
  - Rect: position, size tuples for clipping source to fit destination.
  - integer stages: 1, 2, 4, 8 (validated).
  - tuple[int, int] sizes: (width, height).

The model is testable on Linux and has no Windows/preview dependencies.
"""

import math

from wingman.preview.geometry import Rect


def map_selection(selection, destination, source_size, minimum=(16, 16)):
    """Map a selection rect in destination space to source space.

    Args:
        selection: Rect in destination coordinate space.
        destination: Rect in screen coordinate space.
        source_size: (width, height) of source image.
        minimum: (min_width, min_height) below which result is None.

    Returns:
        Rect in source space, or None if unmappable or below minimum.

    Rejects zero destination/source dimensions by returning None, not
    raising division errors.
    """
    # Reject invalid source/destination dimensions.
    if source_size[0] <= 0 or source_size[1] <= 0:
        return None
    if destination.w <= 0 or destination.h <= 0:
        return None

    # Clamp selection to destination bounds.
    left = max(selection.x, destination.x)
    top = max(selection.y, destination.y)
    right = min(selection.right, destination.right)
    bottom = min(selection.bottom, destination.bottom)

    # Clamped selection is empty.
    if right <= left or bottom <= top:
        return None

    # Map to source space: floor left/top, ceil right/bottom.
    source_w, source_h = source_size
    sx = math.floor((left - destination.x) * source_w / destination.w)
    sy = math.floor((top - destination.y) * source_h / destination.h)
    sr = math.ceil((right - destination.x) * source_w / destination.w)
    sb = math.ceil((bottom - destination.y) * source_h / destination.h)

    # Clamp to source bounds.
    sx, sy = max(0, sx), max(0, sy)
    sr, sb = min(source_w, sr), min(source_h, sb)

    # Reject if below minimum.
    if sr - sx < minimum[0] or sb - sy < minimum[1]:
        return None

    return Rect(sx, sy, sr - sx, sb - sy)


def central_source(source_size):
    """Return the middle half of a source image as a Rect.

    Args:
        source_size: (width, height) of source.

    Returns:
        Rect of the central 50% x 50% region.
    """
    w, h = source_size
    return Rect(w // 4, h // 4, w // 2, h // 2)


def fit_within(source_size, maximum=(1200, 800)):
    """Scale source to fit within maximum, preserving aspect ratio.

    Args:
        source_size: (width, height) of source.
        maximum: (max_width, max_height).

    Returns:
        tuple[int, int] scaled (width, height).
    """
    src_w, src_h = source_size
    max_w, max_h = maximum

    # Scale to fit height; if still too wide, scale to fit width.
    scale = min(max_w / src_w, max_h / src_h)
    return (int(src_w * scale), int(src_h * scale))


def stack_from_bottom_right(index, monitor, size, gap=8):
    """Position a window at monitor bottom-right, stacked upward.

    Args:
        index: Stack position (0 = bottom, 1 = above, ...).
        monitor: Rect of monitor (typically monitor.x < 0 for off-screen).
        size: (width, height) of window.
        gap: Pixels between stacked windows (default 8).

    Returns:
        Rect positioned at monitor.bottom_right - size, moved up by
        (index * (height + gap)).
    """
    w, h = size
    # Start at bottom-right of monitor, inset by 8 pixels.
    x = monitor.right - w - 8
    y = monitor.bottom - h - 8
    # Move up for each index.
    y -= index * (h + gap)
    return Rect(x, y, w, h)


def validated_stage(value):
    """Validate and return a probe stage count.

    Args:
        value: int stage count.

    Returns:
        value if in {1, 2, 4, 8}.

    Raises:
        ValueError: if value not valid.
    """
    if value not in (1, 2, 4, 8):
        raise ValueError(f"stage must be 1, 2, 4, or 8; got {value}")
    return value
