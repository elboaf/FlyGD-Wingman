"""Cycle resolution across the running clients. Pure integer/string work.

No cursor is stored as an INDEX anywhere, and that is the whole design. The
client set is rebuilt every 700ms sweep, so an index survives the set it was
taken from and silently addresses a different character the moment anyone
logs in or out. The anchor is an identity instead, and an identity that has
gone simply falls back to the start.
"""


def ordered(keys) -> list:
    """Deterministic order: by name.

    Not discovery order -- that reshuffles as clients appear and disappear,
    which would make "next" mean something different between two presses.
    """
    return sorted(keys)


def step(keys, anchor, delta: int):
    order = ordered(keys)
    if not order:
        return None
    if anchor not in order:
        # Legitimate and common: focus is on a browser, or the character
        # cycled to last has since logged off.
        return order[0]
    return order[(order.index(anchor) + delta) % len(order)]


def next_key(keys, anchor):
    return step(keys, anchor, 1)


def prev_key(keys, anchor):
    return step(keys, anchor, -1)
