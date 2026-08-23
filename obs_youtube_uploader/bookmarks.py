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


_CRLF = "\r\n"


def generate_ini(section: dict) -> str:
    """Render the engine's INI from a validated eve_bookmarks section.

    Pure: the caller writes it, atomically. Every known bind is emitted even
    when blank, because a missing key makes IniRead fall back to its
    compiled-in default -- which would resurrect ConvertScout's ^+s after a
    user deliberately cleared it.
    """
    binds = section.get("keybinds") or {}
    windows = section.get("windows") or {}

    lines = ["[Keybinds]"]
    for bid in BIND_IDS:
        value = binds.get(bid) or ""
        lines.append(f"{bid}={sanitise(value)}")

    lines.append("")
    lines.append("[Enabled]")
    for title, on in windows.items():
        clean = sanitise(title)
        if not is_engine_window_title(clean):
            continue
        lines.append(f"{clean}={1 if on else 0}")

    return _CRLF.join(lines) + _CRLF


def sanitise(value: str) -> str:
    """Strip line breaks to prevent multi-line INI entries.

    Public because hotkeys.send_command needs it too: the Set Root argument
    is free text the user typed and lands in a file the engine parses.
    Window titles come from the OS and bind values from user input; neither
    is trusted to contain a line break. Note: this does not make arbitrary
    text safe as an INI key; it only strips line breaks.
    """
    return "".join(ch for ch in str(value) if ch not in "\r\n").strip()


# The engine matches window titles against ^EVE -  (111unified.ahk:248), so
# anything else is dead weight in the generated file. Filtering on that here
# is also what closes the INI-injection vectors sanitise() does not: the
# title is written as a KEY, and Windows parses a line starting with "[" as a
# section header and one starting with ";" as a comment, while an embedded
# "=" moves the key/value split and makes the entry unmatchable. A title that
# starts with "EVE - " can do none of those.
#
# Public: evewindows.list_eve_windows uses this as the single source of what
# counts as an EVE client window, so the window it offers to enable and the
# window generate_ini actually writes never drift apart.
ENGINE_TITLE_PREFIX = "EVE - "


def is_engine_window_title(title: str) -> bool:
    return title.startswith(ENGINE_TITLE_PREFIX) and "=" not in title


# Settings the standalone script carried that the engine no longer has.
# Named individually so import can tell the user what it dropped.
_REMOVED_SETTINGS = ("Mode", "PrefaceReturn", "ReturnPreface")
_REMOVED_BINDS = ("Copy", "Paste")


def _parse_ini(text: str) -> dict:
    """Minimal INI reader. configparser is not used: the legacy file has
    section keys (window titles) containing '=' and characters configparser
    mangles, and we only need two flat sections."""
    out: dict[str, dict[str, str]] = {}
    current = None
    # A UTF-8 BOM survives .strip() and would make the first section header
    # fail the "[" test below, silently discarding that entire section --
    # which, since the legacy script writes [Keybinds] first, means every
    # keybind. Notepad adds a BOM whenever someone hand-edits and saves.
    text = (text or "").lstrip("﻿")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            out.setdefault(current, {})
            continue
        if current is None or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[current][key.strip()] = value.strip()
    return out


def import_legacy_ini(text: str) -> dict:
    """Translate a standalone eve_bookmark_helper.ini into a settings section.

    Returns what was imported, what was dropped, and any behaviour change
    the user needs to be told about in their own terms. Never enables the
    feature: reading someone's old settings is not consent to start a
    global keyboard hook.
    """
    parsed = _parse_ini(text)
    legacy_binds = parsed.get("Keybinds", {})
    legacy_settings = parsed.get("Settings", {})
    legacy_windows = parsed.get("Enabled", {})

    section = {"enabled": False,
               "keybinds": dict(DEFAULT_BINDS),
               "windows": {}}
    for bid in BIND_IDS:
        if bid in legacy_binds:
            section["keybinds"][bid] = sanitise(legacy_binds[bid])
    discarded_windows = []
    for title, value in legacy_windows.items():
        clean = sanitise(title)
        if not clean:
            # Deliberately not reported: a line naming a window with no name
            # carries no information the user can act on.
            continue
        if not is_engine_window_title(clean):
            # The engine only ever matches ^EVE -  (111unified.ahk:248), so
            # generate_ini would drop this silently on the next write.
            discarded_windows.append(clean)
            continue
        section["windows"][clean] = value.strip() == "1"

    discarded = [f"{name} (setting)" for name in _REMOVED_SETTINGS
                 if legacy_settings.get(name)]
    discarded += [f"{name} (keybind)" for name in _REMOVED_BINDS
                  if legacy_binds.get(name)]
    discarded += [f"{title} (window, not an EVE client window)"
                  for title in discarded_windows]

    notes = []
    # HomeZeroIs0 defaults to 1 (111unified.ahk:32) and the engine now
    # hardcodes that. Only a user who turned it OFF sees a change: it is not
    # tied to any naming mode (111unified.ahk:870,886,893), so this must be
    # described as a renumbering, not as "no longer applies".
    if legacy_settings.get("HomeZeroIs0", "1").strip() == "0":
        notes.append(
            "Your home-mode bookmarks used to start at .1; they will now "
            "start at .0. That option no longer exists.")
    return {"section": section, "discarded": discarded, "notes": notes}
