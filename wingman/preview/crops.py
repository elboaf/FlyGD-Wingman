"""Normalized crop sources. Pure geometry and records; no native resources."""

import math
from collections.abc import Collection, Mapping
from dataclasses import dataclass

from wingman.telemetry.model import ClientSessionId

from .geometry import Rect

MAX_LIVE_CROPS = 8
MIN_SOURCE_SIZE = (16, 16)


@dataclass(frozen=True)
class CropSource:
    x: float
    y: float
    w: float
    h: float
    original_client_w: int
    original_client_h: int
    original_px: Rect


@dataclass(frozen=True)
class CropDefinition:
    source: CropSource
    window: Rect
    enabled: bool = True
    version: int = 1


@dataclass(frozen=True)
class CropToken:
    """Runtime-only edit identity, never part of a persisted definition.

    Generation is prospective: reserving it must not advance the committed
    generation used to authorize geometry writes. The store owns both counters.
    """

    operation_id: int
    name: str
    epoch: int
    generation: int
    session: ClientSessionId | None


@dataclass(frozen=True)
class CropWriteResult:
    token: CropToken
    applied: bool
    persisted: bool
    error: str | None
    revision: int


def _valid_size(size: tuple[int, int]) -> bool:
    return len(size) == 2 and all(type(v) is int and v > 0 for v in size)


def _integer_rect(rect: Rect) -> bool:
    return all(type(v) is int for v in rect)


def _fractions(x, y, w, h) -> tuple[float, float, float, float]:
    if any(
        type(v) not in (int, float) or (type(v) is float and not math.isfinite(v))
        for v in (x, y, w, h)
    ):
        raise ValueError("Crop fractions must be finite numbers")
    x, y, w, h = (float(max(0, min(1, v))) for v in (x, y, w, h))
    w, h = min(w, 1 - x), min(h, 1 - y)
    if w <= 0 or h <= 0:
        raise ValueError("Crop source must have positive extents inside the client")
    return x, y, w, h


def source_from_pixels(rect: Rect, size: tuple[int, int]) -> CropSource:
    """Normalize a confirmed, in-bounds selection; refuse invalid proposals."""
    if not _valid_size(size) or not _integer_rect(rect):
        raise ValueError("Crop selection and client dimensions must be integers")
    w, h = size
    if (
        rect.x < 0
        or rect.y < 0
        or rect.right > w
        or rect.bottom > h
        or rect.w < MIN_SOURCE_SIZE[0]
        or rect.h < MIN_SOURCE_SIZE[1]
    ):
        raise ValueError(
            "Crop selection must fit the client and be at least "
            f"{MIN_SOURCE_SIZE[0]}x{MIN_SOURCE_SIZE[1]}"
        )
    # Division can put an exact far edge one ULP beyond 1 - origin. Use
    # the persistence normalization now so a successful save cannot drift it.
    fractions = _fractions(rect.x / w, rect.y / h, rect.w / w, rect.h / h)
    return CropSource(*fractions, w, h, rect)


def source_to_pixels(source: CropSource, size: tuple[int, int]) -> Rect | None:
    """Use normalized authority only; a shrunken source may no longer be usable."""
    if not _valid_size(size):
        return None
    try:
        x, y, sw, sh = _fractions(source.x, source.y, source.w, source.h)
    except ValueError:
        return None
    w, h = size
    # Cover the selected edges, matching the picker probe's floor/ceil rule.
    left, top = math.floor(x * w), math.floor(y * h)
    right = min(w, math.ceil((x + sw) * w))
    bottom = min(h, math.ceil((y + sh) * h))
    if right - left < MIN_SOURCE_SIZE[0] or bottom - top < MIN_SOURCE_SIZE[1]:
        return None
    return Rect(left, top, right - left, bottom - top)


def map_selection(
    selection: Rect, destination: Rect, size: tuple[int, int]
) -> Rect | None:
    """Map a drag in picker-client coordinates, including the mirror inset.

    A reversed drag is valid; a zero-area drag or empty intersection is not.
    The source-pixel minimum is tested after rounding, not in picker pixels.
    """
    if (
        not _valid_size(size)
        or not _integer_rect(selection)
        or not _integer_rect(destination)
        or destination.w <= 0
        or destination.h <= 0
    ):
        return None
    left = max(min(selection.x, selection.right), destination.x)
    top = max(min(selection.y, selection.bottom), destination.y)
    right = min(max(selection.x, selection.right), destination.right)
    bottom = min(max(selection.y, selection.bottom), destination.bottom)
    if right <= left or bottom <= top:
        return None
    w, h = size
    sx = math.floor((left - destination.x) * w / destination.w)
    sy = math.floor((top - destination.y) * h / destination.h)
    sr = min(w, math.ceil((right - destination.x) * w / destination.w))
    sb = min(h, math.ceil((bottom - destination.y) * h / destination.h))
    if sr - sx < MIN_SOURCE_SIZE[0] or sb - sy < MIN_SOURCE_SIZE[1]:
        return None
    return Rect(sx, sy, sr - sx, sb - sy)


def valid_owner(name: object) -> bool:
    """Exact manageable character identity; never normalize onto another owner."""
    return (
        isinstance(name, str)
        and bool(name)
        and name == name.strip()
        and name.isprintable()
        and not name.startswith("hwnd:")
    )


def deserialize(raw: object) -> dict[str, CropDefinition]:
    """Rebuild version-1 definitions, dropping malformed owners individually.

    Diagnostic pixels must be well formed, but need not agree with the
    fractions. They never decide which part of a current client is mirrored.
    """
    if not isinstance(raw, dict):
        return {}
    out = {}
    for name, value in raw.items():
        if not valid_owner(name) or not isinstance(value, dict):
            continue
        if type(value.get("version")) is not int or value["version"] != 1:
            continue
        if type(value.get("enabled")) is not bool:
            continue
        source, window = value.get("source"), value.get("window")
        if not isinstance(source, dict) or not isinstance(window, dict):
            continue
        try:
            fractions = _fractions(source["x"], source["y"], source["w"], source["h"])
            original_size = (source["original_client_w"], source["original_client_h"])
            pixels = source["original_px"]
            if not isinstance(pixels, list) or len(pixels) != 4:
                continue
            original_px = Rect(*pixels)
            destination = Rect(window["x"], window["y"], window["w"], window["h"])
        except (KeyError, ValueError):
            continue
        if (
            not _valid_size(original_size)
            or not _integer_rect(original_px)
            or original_px.x < 0
            or original_px.y < 0
            or original_px.w <= 0
            or original_px.h <= 0
            or not _integer_rect(destination)
            or destination.w <= 0
            or destination.h <= 0
        ):
            continue
        out[name] = CropDefinition(
            CropSource(*fractions, *original_size, original_px),
            destination,
            value["enabled"],
            value["version"],
        )
    return out


def serialize(definitions: dict[str, CropDefinition]) -> dict:
    """Serialize definitions explicitly: runtime identities never belong here."""
    return {
        name: {
            "version": definition.version,
            "enabled": definition.enabled,
            "source": {
                "x": definition.source.x,
                "y": definition.source.y,
                "w": definition.source.w,
                "h": definition.source.h,
                "original_client_w": definition.source.original_client_w,
                "original_client_h": definition.source.original_client_h,
                "original_px": list(definition.source.original_px),
            },
            "window": definition.window._asdict(),
        }
        for name, definition in definitions.items()
    }


def eligible_names(
    definitions: Mapping[str, CropDefinition],
    sessions: Collection[str],
    limit: int = MAX_LIVE_CROPS,
) -> tuple[str, ...]:
    """Choose enabled owners with current named sessions, independent of scans.

    `sessions` supplies name membership (normally the coordinator's session
    map). Suppression affects only runtime selection, never saved definitions.
    """
    names = (
        name
        for name, entry in definitions.items()
        if entry.enabled and name in sessions
    )
    return tuple(sorted(names, key=lambda name: (name.casefold(), name))[:limit])
