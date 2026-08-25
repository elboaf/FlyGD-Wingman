"""Hotkey gestures for previews: text and DOM events in, (mods, vk) out.

Pure by construction -- no ctypes, no Windows -- because settings.py imports
it for validation and CI runs on ubuntu-latest.

Deliberately NOT bookmarks.py's AHK notation. That format exists because an
AutoHotkey engine consumes it literally, and it carries constraints from
that engine's storage: bookmarks reject "=" purely because their INI cannot
hold it (see preview/discovery.py's note on the same leak). These gestures
go to RegisterHotKey, which wants modifier flags and a virtual-key code, and
the translation between the two notations is lossy in both directions.
"""

from typing import NamedTuple

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
# Set on EVERY gesture. Without it a held chord posts WM_HOTKEY at the
# keyboard repeat rate and each message runs a foreground-switch sequence:
# invisible when testing with a tap, and awful in a fight.
MOD_NOREPEAT = 0x4000

# Order is display order, so two spellings of one chord produce one string
# and the clash check cannot be fooled by "Alt+Ctrl+F2" vs "Ctrl+Alt+F2".
_MODIFIERS = (
    ("ctrl", MOD_CONTROL, "Ctrl"),
    ("alt", MOD_ALT, "Alt"),
    ("shift", MOD_SHIFT, "Shift"),
    ("meta", MOD_WIN, "Win"),
)

_MODIFIER_CODES = {
    "ControlLeft",
    "ControlRight",
    "AltLeft",
    "AltRight",
    "ShiftLeft",
    "ShiftRight",
    "MetaLeft",
    "MetaRight",
}

# name -> virtual-key. The name is what the user sees and types.
_KEYS = {
    "Space": 0x20,
    "Enter": 0x0D,
    "Tab": 0x09,
    "Esc": 0x1B,
    "Backspace": 0x08,
    "Delete": 0x2E,
    "Insert": 0x2D,
    "Home": 0x24,
    "End": 0x23,
    "PgUp": 0x21,
    "PgDn": 0x22,
    "Up": 0x26,
    "Down": 0x28,
    "Left": 0x25,
    "Right": 0x27,
    ",": 0xBC,
    ".": 0xBE,
    "/": 0xBF,
    ";": 0xBA,
    "'": 0xDE,
    "`": 0xC0,
    "-": 0xBD,
    "=": 0xBB,
    "[": 0xDB,
    "]": 0xDD,
    "\\": 0xDC,
    "NumpadAdd": 0x6B,
    "NumpadSub": 0x6D,
    "NumpadMult": 0x6A,
    "NumpadDiv": 0x6F,
    "NumpadDot": 0x6E,
}
for _i in range(10):
    _KEYS[str(_i)] = 0x30 + _i
    _KEYS[f"Numpad{_i}"] = 0x60 + _i
for _i in range(26):
    _KEYS[chr(ord("A") + _i)] = 0x41 + _i
for _i in range(1, 25):
    _KEYS[f"F{_i}"] = 0x70 + _i - 1

_NAMES = {vk: name for name, vk in _KEYS.items()}

# DOM event.code -> our key name. Same US-layout assumption bookmarks.py
# documents, and mitigated the same way: an Edit... escape hatch in the UI.
_CODES = {
    "Space": "Space",
    "Enter": "Enter",
    "Tab": "Tab",
    "Escape": "Esc",
    "Backspace": "Backspace",
    "Delete": "Delete",
    "Insert": "Insert",
    "Home": "Home",
    "End": "End",
    "PageUp": "PgUp",
    "PageDown": "PgDn",
    "ArrowUp": "Up",
    "ArrowDown": "Down",
    "ArrowLeft": "Left",
    "ArrowRight": "Right",
    "Comma": ",",
    "Period": ".",
    "Slash": "/",
    "Semicolon": ";",
    "Quote": "'",
    "Backquote": "`",
    "Minus": "-",
    "Equal": "=",
    "BracketLeft": "[",
    "BracketRight": "]",
    "Backslash": "\\",
    "NumpadAdd": "NumpadAdd",
    "NumpadSubtract": "NumpadSub",
    "NumpadMultiply": "NumpadMult",
    "NumpadDivide": "NumpadDiv",
    "NumpadDecimal": "NumpadDot",
}


class Gesture(NamedTuple):
    mods: int
    vk: int


def _code_to_name(code: str):
    if code in _CODES:
        return _CODES[code]
    if len(code) == 4 and code.startswith("Key"):
        return code[3].upper()
    if len(code) == 6 and code.startswith("Digit"):
        return code[5]
    if code.startswith("Numpad") and len(code) == 7 and code[6:].isdigit():
        return code
    if code.startswith("F") and code[1:].isdigit() and 1 <= int(code[1:]) <= 24:
        return code
    return None


def _vk(token: str):
    """Resolve a key token: a name, a VK_ name, or a hex literal."""
    if token in _KEYS:
        return _KEYS[token]
    upper = token.upper()
    if upper in _KEYS:
        return _KEYS[upper]
    if upper.startswith("VK_"):
        return _KEYS.get(upper[3:])
    if upper.startswith("0X"):
        try:
            value = int(upper, 16)
        except ValueError:
            return None
        return value if 0 < value <= 0xFF else None
    return None


def parse(text):
    """A gesture, or None if the text is not one.

    None rather than an exception: every caller -- typed entry, settings
    validation, the bridge -- treats an unparseable chord as "drop this one
    binding", never as a failure worth propagating.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    tokens = [t.strip() for t in text.split("+")]
    # A trailing "+" means the key token is empty, which is not the "+" key:
    # that arrives as "=" with Shift, or as NumpadAdd.
    if any(not t for t in tokens):
        return None

    mods, key = 0, tokens[-1]
    by_label = {label.lower(): flag for _, flag, label in _MODIFIERS}
    for token in tokens[:-1]:
        flag = by_label.get(token.lower())
        if flag is None:
            return None
        mods |= flag
    if not mods:
        return None  # a bare chord would be claimed desktop-wide
    vk = _vk(key)
    if vk is None:
        return None
    return Gesture(mods | MOD_NOREPEAT, vk)


def display(g) -> str:
    if g is None:
        return ""
    parts = [label for _, flag, label in _MODIFIERS if g.mods & flag]
    parts.append(_NAMES.get(g.vk, f"0x{g.vk:02X}"))
    return "+".join(parts)


def from_capture(parts) -> dict:
    """Translate a captured DOM key event.

    Returns the canonical gesture string rather than a structure, so the
    page holds no mapping table of its own and cannot drift from this one --
    the same contract bookmarks.to_ahk keeps.
    """
    if not isinstance(parts, dict):
        return {"gesture": "", "error": "unmappable"}
    code = parts.get("code") or ""
    if code in _MODIFIER_CODES:
        # Not an error the user needs told about: they are still reaching
        # for the combination.
        return {"gesture": "", "error": "modifier-only"}
    name = _code_to_name(code)
    if name is None:
        return {"gesture": "", "error": "unmappable"}
    labels = [label for key, _, label in _MODIFIERS if parts.get(key)]
    if not labels:
        return {"gesture": "", "error": "no-modifier"}
    return {"gesture": "+".join([*labels, name]), "error": None}
