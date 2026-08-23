"""The mapping lives in Python because the repo has no way to test JS
(webview-replatform-design.md:545). These tests are what stands in for the
browser tests we deliberately do not have."""
import pytest
from obs_youtube_uploader import bookmarks

NONE = {"ctrl": False, "alt": False, "shift": False, "meta": False}


def parts(code, **mods):
    return {**NONE, **mods, "code": code}


def test_plain_letter():
    assert bookmarks.to_ahk(parts("KeyS")) == {
        "ahk": "s", "display": "S", "error": None}


def test_modifiers_use_canonical_order():
    """AHK ignores modifier order, collision detection does not: ^+s and +^s
    must produce the same string or a duplicate bind goes undetected."""
    got = bookmarks.to_ahk(parts("KeyS", ctrl=True, shift=True))
    assert got["ahk"] == "^+s"
    assert got["display"] == "Ctrl+Shift+S"


def test_all_four_modifiers():
    got = bookmarks.to_ahk(parts("KeyA", ctrl=True, alt=True, shift=True,
                                 meta=True))
    assert got["ahk"] == "^!+#a"
    assert got["display"] == "Ctrl+Alt+Shift+Win+A"


@pytest.mark.parametrize("code,ahk", [
    ("Comma", ","), ("Period", "."), ("Slash", "/"), ("Quote", "'"),
    ("Semicolon", ";"), ("Backquote", "`"), ("Minus", "-"), ("Equal", "="),
    ("BracketLeft", "["), ("BracketRight", "]"), ("Backslash", "\\"),
])
def test_punctuation(code, ahk):
    """The finishers are historically punctuation-bound -- the handler names
    still read DoComma, DoDot, DoQuote, DoSemi -- so these are the common
    case here, not an edge case."""
    got = bookmarks.to_ahk(parts(code))
    assert got["ahk"] == ahk
    assert got["display"] == ahk


@pytest.mark.parametrize("code,ahk", [
    ("Space", "Space"), ("Enter", "Enter"), ("Tab", "Tab"),
    ("Escape", "Esc"), ("Backspace", "Backspace"), ("Delete", "Delete"),
    ("Home", "Home"), ("End", "End"), ("PageUp", "PgUp"),
    ("PageDown", "PgDn"), ("ArrowUp", "Up"), ("ArrowDown", "Down"),
    ("ArrowLeft", "Left"), ("ArrowRight", "Right"), ("F5", "F5"),
    ("Numpad7", "Numpad7"), ("Digit4", "4"),
])
def test_named_keys(code, ahk):
    got = bookmarks.to_ahk(parts(code))
    assert got["ahk"] == ahk
    assert got["display"] == ahk


def test_modifier_with_nonletter_key():
    """display must also stay correct on the non-letter path, not just for
    single alphabetic base keys -- the two branches of the uppercasing rule
    in to_ahk are otherwise never exercised together."""
    got = bookmarks.to_ahk(parts("Comma", ctrl=True))
    assert got["ahk"] == "^,"
    assert got["display"] == "Ctrl+,"


@pytest.mark.parametrize("code,ahk", [
    ("NumpadAdd", "NumpadAdd"), ("NumpadSubtract", "NumpadSub"),
    ("NumpadMultiply", "NumpadMult"), ("NumpadDivide", "NumpadDiv"),
    ("NumpadDecimal", "NumpadDot"), ("NumpadEnter", "NumpadEnter"),
])
def test_numpad_operator_keys(code, ahk):
    """A real numpad also sends these six codes, and three of them need a
    name translation because the DOM code and the AHK key name differ."""
    got = bookmarks.to_ahk(parts(code))
    assert got["ahk"] == ahk
    assert got["display"] == ahk


@pytest.mark.parametrize("code", [
    "ControlLeft", "ControlRight", "AltLeft", "AltRight",
    "ShiftLeft", "ShiftRight", "MetaLeft", "MetaRight",
])
def test_modifier_only_is_rejected(code):
    """Holding Ctrl to reach a combo must not bind Ctrl."""
    got = bookmarks.to_ahk(parts(code, ctrl=True))
    assert got["error"] == "modifier-only"
    assert got["ahk"] == ""


def test_unknown_code_is_rejected():
    """Better a refusal than a string AHK cannot parse in a file it re-reads
    every ten seconds."""
    got = bookmarks.to_ahk(parts("Fn"))
    assert got["error"] == "unmappable"
    assert got["ahk"] == ""


@pytest.mark.parametrize("text,ahk", [
    ("numpad7", "Numpad7"), ("NUMPAD7", "Numpad7"), ("Numpad007", "Numpad7"),
    ("f5", "F5"), ("F007", "F7"), ("f24", "F24"),
    ("numpadadd", "NumpadAdd"), ("^numpad7", "^Numpad7"),
])
def test_parse_ahk_is_case_insensitive_and_canonicalising(text, ahk):
    """parse_ahk is the only binding path for non-US layouts, and it feeds a
    file the engine re-reads every 10s. Accepting what a human types and
    emitting exactly what AutoHotkey registers are both required."""
    assert bookmarks.parse_ahk(text)["ahk"] == ahk


@pytest.mark.parametrize("text", ["Numpad10", "Numpad99", "F0", "F25"])
def test_parse_ahk_rejects_keys_that_do_not_exist(text):
    """A numpad has ten keys and AutoHotkey has F1-F24. Emitting a string
    AutoHotkey cannot register is worse than refusing it."""
    assert bookmarks.parse_ahk(text)["error"] == "unmappable"


@pytest.mark.parametrize("text,ahk", [("f", "f"), ("F", "f"), ("^f", "^f")])
def test_parse_ahk_accepts_the_letter_f(text, ahk):
    """F is an ordinary letter key. The single-letter branch is checked
    before the function-key branch and every function key is at least two
    characters, so there is no ambiguity to guard against -- an earlier fix
    excluded F on that mistaken basis and made it unbindable."""
    assert bookmarks.parse_ahk(text)["ahk"] == ahk
