"""Preview layout persistence.

Pure: dict in, dict out. The caller owns the file, because settings.save()
projects the complete document (settings.py:145-149) and has more than one
writer already -- see preview/store.py for who may write and how.
"""
from typing import NamedTuple

from .geometry import Rect


class Entry(NamedTuple):
    rect: Rect
    locked: bool = False


def serialize(entries: dict) -> dict:
    return {
        key: {"x": e.rect.x, "y": e.rect.y, "w": e.rect.w, "h": e.rect.h,
              "locked": bool(e.locked)}
        for key, e in entries.items()
    }


def deserialize(raw) -> dict:
    """Rebuild entries, dropping anything malformed.

    Deliberately forgiving, matching settings.py's validation posture: a
    hand-edited or partially-written settings file should cost one
    preview's position, not the launch.
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
        out[key] = Entry(Rect(x, y, w, h), bool(value.get("locked", False)))
    return out
