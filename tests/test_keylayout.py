"""The layout-aware capture resolver (ADR 0002).

Fakes stand in for the Windows layout view, so the whole resolver is
exercised off-Windows; the real view's Win32 marshalling is tested with an
injected fake in the same spirit as the other injected seams.
"""

from wingman import keylayout


def test_dvorak_g_position_produces_i():
    """Issue #305's exact repro: on Dvorak the key that types `i` sits at
    the physical position QWERTY calls KeyG, so capture must store from the
    produced character, not the position."""
    dvorak = {"KeyG": "i"}
    got = keylayout.resolve(dvorak.get, "KeyG")
    assert got.token == "i"
    assert got.kind == "layout"


def test_produced_letter_from_any_position_stores_that_letter():
    """AZERTY: the key QWERTY calls Semicolon types `m`. The stored string
    must say `m` -- the letter -- regardless of where the key sits."""
    azerty = {"Semicolon": "m"}
    got = keylayout.resolve(azerty.get, "Semicolon")
    assert got == keylayout.Resolution("layout", "m")


def test_produced_punctuation_in_the_representable_set_stores_it():
    got = keylayout.resolve({"Slash": ","}.get, "Slash")
    assert got == keylayout.Resolution("layout", ",")


def test_produced_character_outside_the_storable_set_falls_back():
    """`é` cannot be written as a Wingman hotkey token at all, so capture
    must degrade to the position-derived key and carry the reason for the
    warning, instead of storing something the engine cannot register. The
    position token itself is the caller's to derive: bookmarks and gestures
    keep their own case conventions for it."""
    got = keylayout.resolve({"Digit2": "é"}.get, "Digit2")
    assert got.token is None
    assert got.kind == "position"
    assert got.reason == "not-representable"


def test_multi_character_production_falls_back():
    got = keylayout.resolve({"KeyP": "ss"}.get, "KeyP")
    assert got.kind == "position"
    assert got.reason == "not-representable"


def test_control_character_production_falls_back():
    """A consultable position that somehow produces a control character has
    no storable spelling either."""
    got = keylayout.resolve({"Comma": "\x1b"}.get, "Comma")
    assert got.kind == "position"
    assert got.reason == "not-representable"


def test_numpad_keys_keep_position_identity():
    """Dvorak's Numpad4 still types `4`, but storing "4" would silently
    turn a numpad bind into a digit-row bind -- VK 0x60-0x69 is where the
    numpad sits regardless of layout. Position-defined keys never resolve."""
    got = keylayout.resolve({"Numpad4": "4"}.get, "Numpad4")
    assert got == keylayout.Resolution("position", None, "position-defined")


def test_named_keys_keep_position_identity():
    """Space, Enter, arrows, nav keys and F-keys sit at layout-independent
    VKs on every Windows layout; consulting the view for them can only
    introduce drift, never information."""
    for code in ("Space", "Enter", "F5", "ArrowUp", "PageDown", "Escape"):
        got = keylayout.resolve({code: "?"}.get, code)
        assert got == keylayout.Resolution("position", None, "position-defined"), code
