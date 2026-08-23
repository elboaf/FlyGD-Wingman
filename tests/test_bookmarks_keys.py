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
    assert bookmarks.to_ahk(parts(code))["ahk"] == ahk


@pytest.mark.parametrize("code,ahk", [
    ("Space", "Space"), ("Enter", "Enter"), ("Tab", "Tab"),
    ("Escape", "Esc"), ("Backspace", "Backspace"), ("Delete", "Delete"),
    ("Home", "Home"), ("End", "End"), ("PageUp", "PgUp"),
    ("PageDown", "PgDn"), ("ArrowUp", "Up"), ("ArrowDown", "Down"),
    ("ArrowLeft", "Left"), ("ArrowRight", "Right"), ("F5", "F5"),
    ("Numpad7", "Numpad7"), ("Digit4", "4"),
])
def test_named_keys(code, ahk):
    assert bookmarks.to_ahk(parts(code))["ahk"] == ahk


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
