"""Cycle resolution across the running clients. Pure integer/string work.

No cursor is stored as an INDEX anywhere, and that is the whole design. The
client set is rebuilt every 700ms sweep, so an index survives the set it was
taken from and silently addresses a different character the moment anyone
logs in or out. The anchor is an identity instead, and an identity that has
gone simply falls back to the start.
"""

from wingman.preview.labelmarkers import valid_owner

# Bracketed, not free: a typo like 100 vs 10 must not be able to bury a
# character behind several hundred presses of "next".
MIN_PREFERENCE = 1
MAX_PREFERENCE = 999


def validated_stored(raw) -> dict:
    """Stored per-character preferences, dropping malformed entries
    independently so a hand-edited file costs one entry, not the launch."""
    if not isinstance(raw, dict):
        return {}
    out = {}
    for name, value in raw.items():
        if not valid_owner(name):
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        out[name] = max(MIN_PREFERENCE, min(MAX_PREFERENCE, value))
    return out


def effective_order(keys, stored) -> dict:
    """Every key resolved to one number: stored preferences win, unset keys
    get the next free numbers assigned alphabetically among themselves.

    Stored numbers need not be contiguous -- 1, 5, 9 keeps relative order --
    so auto-assignment only skips numbers actually taken, which keeps the
    effective map stable when an unrelated character is renumbered.
    """
    stored = stored or {}
    taken = {n for n in stored.values() if isinstance(n, int)}
    resolved = {}
    for key in sorted(set(keys) | set(stored)):
        value = stored.get(key)
        if isinstance(value, int):
            resolved[key] = value
    for key in sorted(set(keys) - set(resolved)):
        number = 1
        while number in taken:
            number += 1
        resolved[key] = number
        taken.add(number)
    return resolved


def ordered(keys, stored=None) -> list:
    """Deterministic order: stored cycle preference first, then by name.

    Not discovery order -- that reshuffles as clients appear and disappear,
    which would make "next" mean something different between two presses.
    Deduplicate to ensure list.index() finds the same instance of each name.
    The tiebreak on equal numbers is the name, so duplicate preferences
    degrade to alphabetical instead of input order.
    """
    numbers = effective_order(keys, stored)
    return sorted(set(keys), key=lambda key: (numbers.get(key, 0), key))


def step(keys, anchor, delta: int, stored=None):
    order = ordered(keys, stored)
    if not order:
        return None
    if anchor not in order:
        # Legitimate and common: focus is on a browser, or the character
        # cycled to last has since logged off.
        return order[0]
    return order[(order.index(anchor) + delta) % len(order)]


def next_key(keys, anchor, stored=None):
    return step(keys, anchor, 1, stored)


def prev_key(keys, anchor, stored=None):
    return step(keys, anchor, -1, stored)
