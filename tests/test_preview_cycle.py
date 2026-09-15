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


# ---- the stored preference ------------------------------------------


def test_stored_preference_orders_the_walk_before_name():
    """The whole feature: the user's numbers decide, not the alphabet."""
    keys = {"Charlie", "Alice", "Bravo"}
    stored = {"Charlie": 1, "Alice": 2, "Bravo": 3}
    assert cycle.next_key(keys, "Charlie", stored) == "Alice"
    assert cycle.next_key(keys, "Alice", stored) == "Bravo"
    assert cycle.next_key(keys, "Bravo", stored) == "Charlie"


def test_equal_numbers_fall_back_to_name_order():
    """Duplicate preferences are user error that must not make the walk
    input-order dependent; the name tiebreak degrades to alphabetical."""
    keys = {"Charlie", "Alice", "Bravo"}
    assert cycle.ordered(keys, {"Alice": 5, "Bravo": 5, "Charlie": 1}) == [
        "Charlie",
        "Alice",
        "Bravo",
    ]


def test_numbers_need_not_be_contiguous():
    """1, 5, 9 keeps relative order -- renumbering one character is not
    required to make room for another."""
    keys = {"A", "B", "C"}
    stored = {"A": 1, "B": 5, "C": 9}
    assert cycle.ordered(keys, stored) == ["A", "B", "C"]


def test_offline_stored_entries_are_kept_and_do_not_perturb_the_walk():
    """effective_order resolves every known name -- the settings page
    paints offline characters too -- but a stored entry for a character
    not cycling must not consume anything the walk depends on."""
    effective = cycle.effective_order({"Alice"}, {"Alice": 2, "Ghost": 1})
    assert effective == {"Alice": 2, "Ghost": 1}
    assert cycle.ordered({"Alice"}, {"Ghost": 1}) == ["Alice"]


def test_effective_order_auto_assigns_unset_alphabetically_after_stored():
    """Auto-assignment: stored numbers win, then unset characters take the
    next free numbers in alphabetical order. The resulting map is exactly
    'numbered characters first, then the rest alphabetically'."""
    effective = cycle.effective_order(
        {"Charlie", "Alice", "Bravo", "Delta"}, {"Charlie": 1, "Delta": 3}
    )
    assert effective == {
        "Charlie": 1,
        "Delta": 3,
        "Alice": 2,
        "Bravo": 4,
    }


def test_effective_order_skips_only_numbers_actually_taken():
    """Gaps from removed preferences are not filled preferentially; the
    next free number after the taken set is. Keeping this stable means
    clearing one character's number does not silently renumber anyone
    else's display value."""
    effective = cycle.effective_order({"A", "B", "C", "D"}, {"A": 10})
    assert effective == {"A": 10, "B": 1, "C": 2, "D": 3}


def test_empty_stored_is_the_shipped_alphabetical_walk():
    """No preferences anywhere means today's behaviour, exactly."""
    keys = {"Zulu", "Alice"}
    assert cycle.ordered(keys, None) == ["Alice", "Zulu"]
    assert cycle.ordered(keys, {}) == ["Alice", "Zulu"]
    assert cycle.next_key(keys, "Alice", {}) == "Zulu"


def test_validated_stored_drops_malformed_entries_independently():
    from wingman.preview.cycle import MAX_PREFERENCE, MIN_PREFERENCE

    stored = cycle.validated_stored(
        {
            "Alice": 2,
            "Bravo": True,  # bool is an int subclass; it is not a number here
            "Charlie": "3",
            "Delta": None,
            "Eve": 0,  # below the bracket -> clamped, not rejected
            "Zulu": 100_000,  # above the bracket -> clamped
            "hwnd:12": 4,  # no stable identity
            " Bad ": 5,  # not a valid owner name
        }
    )
    assert stored == {
        "Alice": 2,
        "Eve": MIN_PREFERENCE,
        "Zulu": MAX_PREFERENCE,
    }
    assert cycle.validated_stored(None) == {}
    assert cycle.validated_stored(["Alice", 1]) == {}
