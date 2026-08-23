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
    # Single digit: a numpad has ten keys. DOM capture only ever emits
    # Numpad0-9, but parse_ahk reaches here too and the bound belongs with
    # the mapping, not only with its caller.
    if code.startswith("Numpad") and len(code) == 7 and code[6:].isdigit():
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


# Order is display order in the Bookmarks route, grouped the way the
# standalone GUI grouped them (111unified.ahk:285-305): actions, then
# class finishers, then tag finishers.
BIND_IDS = (
    "GrabSig", "SetRoot", "FormatEnf", "ConvertScout",
    "FinH", "FinL", "FinN", "Fin13",
    "Fin1", "Fin2", "Fin3", "Fin4", "Fin5", "Fin6",
    "FinETag", "FinSlash", "FinM", "FinS", "FinC",
)

# Human labels for the route. Kept beside the ids so the two cannot drift.
BIND_LABELS = {
    "GrabSig": "Grab Sig ID",
    "SetRoot": "Set Root",
    "FormatEnf": "Format Enforcer",
    "ConvertScout": "Convert EvE-Scout Bookmarks",
    "FinH": "Finisher: HS (highsec)",
    "FinL": "Finisher: LS (lowsec)",
    "FinN": "Finisher: NS (nullsec)",
    "Fin13": "Finisher: C13 (shattered)",
    "Fin1": "Finisher: C1", "Fin2": "Finisher: C2",
    "Fin3": "Finisher: C3", "Fin4": "Finisher: C4",
    "Fin5": "Finisher: C5", "Fin6": "Finisher: C6",
    "FinETag": "E Tag (end of life)",
    "FinSlash": "/ Tag (half mass)",
    "FinM": "M Tag (medium hole)",
    "FinS": "S Tag (frig hole)",
    "FinC": "C Tag (critical)",
}

# Only ConvertScout ships bound (111unified.ahk:57,140). The other
# eighteen are blank on purpose: no default global bind means no surprise
# collision on first run.
DEFAULT_BINDS = {bid: ("^+s" if bid == "ConvertScout" else "")
                 for bid in BIND_IDS}

_SYMBOL_TO_KEY = {sym: key for key, sym, _ in _MODIFIERS}


def collisions(binds: dict) -> dict:
    """Map each doubly-bound AHK string to every bind id claiming it.

    Blank means "do not register" to RefreshHotkeys, so blanks are skipped
    rather than treated as a shared value.
    """
    seen: dict[str, list[str]] = {}
    for bid in BIND_IDS:
        value = (binds.get(bid) or "").strip()
        if not value:
            continue
        seen.setdefault(value, []).append(bid)
    return {k: v for k, v in seen.items() if len(v) > 1}


def parse_ahk(text: str) -> dict:
    """Validate a hand-typed AHK hotkey string.

    The escape hatch for non-US layouts, where the event.code table maps to
    the wrong character. Routed through the same rules as capture so the
    two cannot disagree.
    """
    raw = (text or "").strip()
    parts = dict.fromkeys(("ctrl", "alt", "shift", "meta"), False)
    index = 0
    while index < len(raw) and raw[index] in _SYMBOL_TO_KEY:
        parts[_SYMBOL_TO_KEY[raw[index]]] = True
        index += 1
    base = raw[index:]
    if not base:
        return {"ahk": "", "display": "", "error": "modifier-only"}

    # Reverse the mapping table so a typed "," and a captured Comma agree.
    code = None
    for candidate, mapped in _NAMED.items():
        if mapped.lower() == base.lower():
            code = candidate
            break
    if code is None:
        lowered = base.lower()
        if len(base) == 1 and base.isalpha():
            code = "Key" + base.upper()
        elif len(base) == 1 and base.isdigit():
            code = "Digit" + base
        elif lowered.startswith("numpad") and base[6:].isdigit():
            # Canonicalise rather than forward the text: a numpad has ten
            # keys, so "Numpad10" is not a key at all and "Numpad007" is
            # the right key spelled wrongly. The named numpad operators
            # (NumpadAdd and friends) were already matched by the reverse
            # lookup above and never reach here.
            digits = base[6:]
            if len(digits) > 1 and digits.lstrip("0") == "":
                digits = "0"
            else:
                digits = digits.lstrip("0") or "0"
            if len(digits) != 1:
                return {"ahk": "", "display": "", "error": "unmappable"}
            code = "Numpad" + digits
        elif lowered.startswith("f"):
            # If it starts with F, it MUST be a function key (F1-F24).
            # Same reason: int("007") is 7 and passes the range check, but
            # the literal "F007" is not a hotkey AutoHotkey will register.
            if not base[1:].isdigit():
                return {"ahk": "", "display": "", "error": "unmappable"}
            number = int(base[1:])
            if not 1 <= number <= 24:
                return {"ahk": "", "display": "", "error": "unmappable"}
            code = "F" + str(number)
        else:
            return {"ahk": "", "display": "", "error": "unmappable"}
    return to_ahk({**parts, "code": code})
