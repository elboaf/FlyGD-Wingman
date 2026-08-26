"""Cycle resolution. The client set changes every 700ms, so everything here
is about behaving sanely when it does."""

from wingman.preview import cycle


def test_next_advances_in_name_order():
    keys = {"Charlie", "Alice", "Bravo"}
    assert cycle.next_key(keys, "Alice") == "Bravo"
    assert cycle.next_key(keys, "Bravo") == "Charlie"


def test_next_wraps_at_the_end():
    assert cycle.next_key({"Alice", "Bravo"}, "Bravo") == "Alice"


def test_prev_wraps_at_the_start():
    assert cycle.prev_key({"Alice", "Bravo"}, "Alice") == "Bravo"


def test_order_is_by_name_not_insertion():
    """Discovery order reshuffles as clients come and go, which would make
    'next' mean something different between two presses."""
    assert cycle.ordered(["Zulu", "Alice"]) == ["Alice", "Zulu"]
    assert cycle.ordered(["Alice", "Zulu"]) == ["Alice", "Zulu"]


def test_a_missing_anchor_starts_at_the_beginning():
    """The anchor is the foreground client. It is legitimately absent when
    focus is on a browser, or when the last-cycled character logged off."""
    assert cycle.next_key({"Alice", "Bravo"}, None) == "Alice"
    assert cycle.next_key({"Alice", "Bravo"}, "Ghost") == "Alice"


def test_an_empty_set_resolves_to_nothing():
    assert cycle.next_key(set(), None) is None
    assert cycle.next_key(set(), "Alice") is None


def test_a_single_client_cycles_to_itself():
    assert cycle.next_key({"Alice"}, "Alice") == "Alice"
    assert cycle.prev_key({"Alice"}, "Alice") == "Alice"


def test_a_client_joining_does_not_skip_the_anchor():
    """The bug a stored index would have: the set grows and the cursor
    silently points at a different character."""
    assert cycle.next_key({"Alice", "Charlie"}, "Alice") == "Charlie"
    assert cycle.next_key({"Alice", "Bravo", "Charlie"}, "Alice") == "Bravo"


def test_a_duplicate_in_a_list_input_does_not_stall_the_cycle():
    """list.index() finds the first occurrence, so an undeduped duplicate
    makes "next" land on the same name again instead of advancing."""
    assert cycle.next_key(["Alice", "Alice", "Bravo"], "Alice") == "Bravo"
