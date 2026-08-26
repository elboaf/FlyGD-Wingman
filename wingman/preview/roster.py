"""Characters seen, most recently first.

A character can only be NAMED while it is running, so without this a user
could not bind an alt that flies on weekends without logging it in first.
preview.layouts is keyed by character but is written only on a rect change,
so a preview that was never dragged has no key -- it is not a roster.

Pure: list in, list out. The caller owns the file.
"""

CAP = 64


def _usable(name) -> bool:
    # "hwnd:" keys belong to clients at character-select, which have no
    # stable identity. discovery.py falls back to them precisely because
    # there is no name yet.
    return isinstance(name, str) and bool(name) and not name.startswith("hwnd:")


def touch(seen, name, *, cap: int = CAP, protected=()) -> list:
    """Record *name* as most recently seen.

    Move-to-front rather than append: the list is ordered by recency, and
    an append would leave a re-seen character at the stale end where
    eviction finds it first.
    """
    out = [n for n in seen if _usable(n) and n != name]
    if not _usable(name):
        return out
    out.insert(0, name)

    while len(out) > cap:
        for i in range(len(out) - 1, 0, -1):
            # Skip index 0 (the most recently seen). Never evict the item
            # just added; the most-recent is always kept.
            if out[i] not in protected:
                del out[i]
                break
        else:
            # Every remaining entry holds a binding. Overshooting the cap
            # is the lesser evil: dropping one would leave a chord the bind
            # list has no row for, which is worse than a slightly long file.
            break
    return out


def deserialize(raw, *, cap: int = CAP) -> list:
    """Rebuild the roster, dropping anything malformed.

    Deliberately forgiving, matching preview/layout.py and settings.py: a
    hand-edited file should cost one entry, not the launch.
    """
    if not isinstance(raw, list):
        return []
    out = []
    for name in raw:
        if _usable(name) and name not in out:
            out.append(name)
    return out[:cap]
