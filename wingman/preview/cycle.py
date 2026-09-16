"""Cycle resolution across a cycle group's members. Pure list work.

No cursor is stored as an INDEX anywhere, and that is the whole design. The
running-member set is rebuilt on every press, so an index survives the set
it was taken from and silently addresses a different character the moment
anyone logs in or out. The anchor is an identity instead, and an identity
that has gone simply falls back to the start.

The caller supplies the member list already in cycle order -- a group's
stored order, filtered to who is running. This module adds only the
deduplication and wrap-around; it decides no order of its own.
"""


def step(keys, anchor, delta: int):
    """*keys* is an ordered list of names. Deduplicated, because
    list.index() finds the first occurrence and an undeduped duplicate
    makes "next" land on the same name again instead of advancing."""
    order = []
    for key in keys:
        if key not in order:
            order.append(key)
    if not order:
        return None
    if anchor not in order:
        # Legitimate and common: focus is on a browser, on a non-member, or
        # the character cycled to last has since logged off.
        return order[0]
    return order[(order.index(anchor) + delta) % len(order)]


def next_key(keys, anchor):
    return step(keys, anchor, 1)


def prev_key(keys, anchor):
    return step(keys, anchor, -1)
