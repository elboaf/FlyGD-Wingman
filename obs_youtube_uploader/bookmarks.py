"""Pure logic for the EVE bookmark helper: keybind notation, validation,
INI generation, and legacy import.

Nothing here does I/O or touches a platform API, which is what lets the
whole module be tested on Linux. The engine that consumes its output cannot
be tested at all, so this is where the coverage has to come from.
"""

# Ctrl, Alt, Shift, Win. AHK accepts any order; a fixed one is what makes
# two spellings of the same combo compare equal in collision detection.
_MODIFIERS = (("ctrl", "^", "Ctrl"), ("alt", "!", "Alt"),
              ("shift", "+", "Shift"), ("meta", "#", "Win"))

_MODIFIER_CODES = frozenset({
    "ControlLeft", "ControlRight", "AltLeft", "AltRight",
    "ShiftLeft", "ShiftRight", "MetaLeft", "MetaRight",
})

# event.code -> AHK key name. event.code is used rather than event.key
# because event.key reports the *produced* character: Shift+Comma arrives as
# "<" and the shifting would have to be reversed to recover the "," AHK
# wants. The cost is a US-layout assumption, mitigated by manual entry.
_NAMED = {
    "Space": "Space", "Enter": "Enter", "Tab": "Tab", "Escape": "Esc",
    "Backspace": "Backspace", "Delete": "Delete", "Insert": "Insert",
    "Home": "Home", "End": "End", "PageUp": "PgUp", "PageDown": "PgDn",
    "ArrowUp": "Up", "ArrowDown": "Down", "ArrowLeft": "Left",
    "ArrowRight": "Right",
    "Comma": ",", "Period": ".", "Slash": "/", "Semicolon": ";",
    "Quote": "'", "Backquote": "`", "Minus": "-", "Equal": "=",
    "BracketLeft": "[", "BracketRight": "]", "Backslash": "\\",
    # The digit/letter numpad codes fall through to the generic Numpad<n>
    # branch below unchanged, but these six have DOM codes that don't match
    # the AHK key name AHK expects, so they need an explicit translation.
    "NumpadAdd": "NumpadAdd", "NumpadSubtract": "NumpadSub",
    "NumpadMultiply": "NumpadMult", "NumpadDivide": "NumpadDiv",
    "NumpadDecimal": "NumpadDot", "NumpadEnter": "NumpadEnter",
}


def _base_key(code: str) -> str | None:
    if code in _NAMED:
        return _NAMED[code]
    if len(code) == 4 and code.startswith("Key"):
        return code[3].lower()
    if len(code) == 6 and code.startswith("Digit"):
        return code[5]
    if code.startswith("Numpad") and code[6:].isdigit():
        return code
    if code.startswith("F") and code[1:].isdigit() and 1 <= int(code[1:]) <= 24:
        return code
    return None


def to_ahk(parts: dict) -> dict:
    """Translate a captured DOM key event into AHK hotkey notation.

    Returns both the AHK string and a human label, so the page holds no
    mapping table of its own and cannot drift from this one.
    """
    code = parts.get("code") or ""
    if code in _MODIFIER_CODES:
        return {"ahk": "", "display": "", "error": "modifier-only"}
    base = _base_key(code)
    if base is None:
        return {"ahk": "", "display": "", "error": "unmappable"}

    prefix = "".join(sym for key, sym, _ in _MODIFIERS if parts.get(key))
    labels = [label for key, _, label in _MODIFIERS if parts.get(key)]
    display_key = base.upper() if len(base) == 1 and base.isalpha() else base
    return {
        "ahk": prefix + base,
        "display": "+".join(labels + [display_key]),
        "error": None,
    }
