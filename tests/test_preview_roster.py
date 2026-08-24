"""The roster of characters seen. Exists so a binding can be made for an
alt that is not logged in right now."""
from obs_youtube_uploader.preview import roster


def test_a_new_name_goes_to_the_front():
    assert roster.touch(["Bravo"], "Alice") == ["Alice", "Bravo"]


def test_a_seen_name_moves_to_the_front_rather_than_duplicating():
    assert roster.touch(["Alice", "Bravo"], "Bravo") == ["Bravo", "Alice"]


def test_hwnd_keys_never_enter():
    """A client at character-select has no stable identity, and the parent
    design forbids persisting state against one. A roster of dead HWND keys
    would also fill the bind list with rows naming nothing."""
    assert roster.touch(["Alice"], "hwnd:0x1234") == ["Alice"]


def test_empty_and_non_string_names_are_ignored():
    assert roster.touch(["Alice"], "") == ["Alice"]
    assert roster.touch(["Alice"], None) == ["Alice"]


def test_eviction_takes_from_the_stale_end():
    seen = [f"Char{i}" for i in range(64)]
    result = roster.touch(seen, "New", cap=64)
    assert result[0] == "New"
    assert len(result) == 64
    assert "Char63" not in result       # the least recently seen
    assert "Char0" in result


def test_a_bound_character_is_never_evicted():
    """Evicting a character that still holds a chord would leave a binding
    the UI cannot show a row for."""
    seen = [f"Char{i}" for i in range(64)]
    result = roster.touch(seen, "New", cap=64, protected={"Char63"})
    assert "Char63" in result
    assert "Char62" not in result
    assert len(result) == 64


def test_an_all_protected_roster_grows_rather_than_dropping_a_binding():
    seen = [f"Char{i}" for i in range(4)]
    result = roster.touch(seen, "New", cap=4, protected=set(seen))
    assert len(result) == 5


def test_deserialize_drops_malformed_entries():
    """Same posture as preview/layout.py: a hand-edited file costs one
    entry, not the launch."""
    assert roster.deserialize(["Alice", 5, "", None, "hwnd:0x1",
                               "Bravo"]) == ["Alice", "Bravo"]
    assert roster.deserialize("nonsense") == []
    assert roster.deserialize(None) == []


def test_deserialize_dedupes_preserving_order():
    assert roster.deserialize(["Alice", "Bravo", "Alice"]) == ["Alice", "Bravo"]


def test_deserialize_applies_the_cap():
    assert len(roster.deserialize([f"C{i}" for i in range(200)])) == roster.CAP
