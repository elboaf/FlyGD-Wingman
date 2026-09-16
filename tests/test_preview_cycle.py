"""Cycle resolution. The caller supplies the member list already in cycle
order -- a group's stored order, filtered to who is running -- so the module
decides no order of its own. Everything here is about the running set
changing under the walk."""

from wingman.preview import cycle


def test_next_advances_in_list_order():
    keys = ["Charlie", "Alice", "Bravo"]
    assert cycle.next_key(keys, "Alice") == "Bravo"
    assert cycle.next_key(keys, "Bravo") == "Charlie"


def test_list_order_is_the_stored_group_order_not_the_alphabet():
    """The group's own order decides; the module must never re-sort."""
    keys = ["Charlie", "Alice", "Bravo"]
    assert cycle.next_key(keys, "Charlie") == "Alice"
    assert cycle.prev_key(keys, "Charlie") == "Bravo"


def test_next_wraps_at_the_end():
    assert cycle.next_key(["Alice", "Bravo"], "Bravo") == "Alice"


def test_prev_wraps_at_the_start():
    assert cycle.prev_key(["Alice", "Bravo"], "Alice") == "Bravo"


def test_a_missing_anchor_starts_at_the_beginning():
    """The anchor is the foreground client. It is legitimately absent when
    focus is on a browser, on a non-member, or when the last-cycled
    character logged off."""
    assert cycle.next_key(["Alice", "Bravo"], None) == "Alice"
    assert cycle.next_key(["Alice", "Bravo"], "Ghost") == "Alice"


def test_an_empty_set_resolves_to_nothing():
    assert cycle.next_key([], None) is None
    assert cycle.next_key([], "Alice") is None


def test_a_single_member_cycles_to_itself():
    assert cycle.next_key(["Alice"], "Alice") == "Alice"
    assert cycle.prev_key(["Alice"], "Alice") == "Alice"


def test_a_member_joining_does_not_skip_the_anchor():
    """The bug a stored index would have: the set grows and the cursor
    silently points at a different character."""
    assert cycle.next_key(["Alice", "Charlie"], "Alice") == "Charlie"
    assert cycle.next_key(["Alice", "Bravo", "Charlie"], "Alice") == "Bravo"


def test_a_duplicate_in_the_member_list_does_not_stall_the_cycle():
    """list.index() finds the first occurrence, so an undeduped duplicate
    makes "next" land on the same name again instead of advancing."""
    assert cycle.next_key(["Alice", "Alice", "Bravo"], "Alice") == "Bravo"
