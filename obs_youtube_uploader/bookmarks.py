"""Pure logic for the EVE bookmark helper: keybind notation, validation,
INI generation, and legacy import.

Nothing here does I/O or touches a platform API, which is what lets the
whole module be tested on Linux. The engine that consumes its output cannot
be tested at all, so this is where the coverage has to come from.
"""

# Ctrl, Alt, Shift, Win. AHK accepts any order; a fixed one is what makes
# two spellings of the same combo compare equal in collision detection.
_MODIFIERS = (
    ("ctrl", "^", "Ctrl"),
    ("alt", "!", "Alt"),
    ("shift", "+", "Shift"),
    ("meta", "#", "Win"),
)

_MODIFIER_CODES = frozenset(
    {
        "ControlLeft",
        "ControlRight",
        "AltLeft",
        "AltRight",
        "ShiftLeft",
        "ShiftRight",
        "MetaLeft",
        "MetaRight",
    }
)

# event.code -> AHK key name. event.code is used rather than event.key
# because event.key reports the *produced* character: Shift+Comma arrives as
# "<" and the shifting would have to be reversed to recover the "," AHK
# wants. The cost is a US-layout assumption, mitigated by manual entry.
_NAMED = {
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
    # The digit/letter numpad codes fall through to the generic Numpad<n>
    # branch below unchanged, but these six have DOM codes that don't match
    # the AHK key name AHK expects, so they need an explicit translation.
    "NumpadAdd": "NumpadAdd",
    "NumpadSubtract": "NumpadSub",
    "NumpadMultiply": "NumpadMult",
    "NumpadDivide": "NumpadDiv",
    "NumpadDecimal": "NumpadDot",
    "NumpadEnter": "NumpadEnter",
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
        "display": "+".join([*labels, display_key]),
        "error": None,
    }


# Order is display order in the Bookmarks route, matching the order the
# standalone GUI built its rows in (111unified.ahk:285-305): actions, then
# class finishers, then tag finishers.
#
# The two clipboard conveniences the standalone script led with are gone.
# Copy and Paste only ever sent ^c and ^v (111unified.ahk:988-995), so they
# spent a global keyboard hook reproducing what Windows already does.
BIND_IDS = (
    "GrabSig",
    "SetRoot",
    "FormatEnf",
    "ConvertScout",
    "FinH",
    "FinL",
    "FinN",
    "Fin13",
    "Fin1",
    "Fin2",
    "Fin3",
    "Fin4",
    "Fin5",
    "Fin6",
    "FinETag",
    "FinSlash",
    "FinS",
    "FinC",
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
    "Fin1": "Finisher: C1",
    "Fin2": "Finisher: C2",
    "Fin3": "Finisher: C3",
    "Fin4": "Finisher: C4",
    "Fin5": "Finisher: C5",
    "Fin6": "Finisher: C6",
    "FinETag": "e Tag (end of life)",
    "FinSlash": "/ Tag (half mass)",
    "FinS": "f Tag (frig hole)",
    "FinC": "c Tag (critical)",
}

# The three groups the eighteen binds already fall into, DERIVED from the
# labels above rather than listed again here. Round 5's C8: the route
# rendered one flat list of eighteen rows, ten of which opened with the same
# five characters and differed in the last token, at 61.8px per row.
#
# Derived, and derived from the LABELS specifically, because PRODUCT.md
# names BIND_LABELS as the one table a fork rewrites to carry its own house
# style: a fork that renames "Finisher: C1" to its own scheme gets its own
# grouping out of the same edit, and a second list here would be the thing
# it forgot to change. The ids cannot do the job -- FinS ("f Tag") and FinN
# ("Finisher: NS") share a prefix and land in different groups.
#
# The failure mode is deliberately the OLD screen, not a broken one: a fork
# whose labels match neither marker puts every bind in the leading unnamed
# group, which renders exactly as the flat list did.
_GROUP_FINISHER_PREFIX = "Finisher: "
_GROUP_TAG_MARKER = " Tag"


def bind_groups() -> tuple[dict, ...]:
    """BIND_IDS split into display groups, in BIND_IDS order.

    Each group is ``{"name", "ids", "short"}``. ``name`` is "" for the
    leading group, which heads nothing because its members share no token
    to lift. ``short`` maps id -> the label with the group's shared token
    removed, which is what makes the members short enough to render as a
    multi-column block instead of one full-width row each.

    Order within a group, and the order of the groups themselves, follow
    BIND_IDS -- the route's display order, which matches the standalone
    GUI's (see BIND_IDS above). Nothing here re-sorts anything.
    """
    buckets: dict[str, dict] = {}
    order: list[str] = []
    for bid in BIND_IDS:
        label = BIND_LABELS[bid]
        if label.startswith(_GROUP_FINISHER_PREFIX):
            key, short = "Finishers", label[len(_GROUP_FINISHER_PREFIX) :]
        elif _GROUP_TAG_MARKER in label:
            key, short = "Tags", label.replace(_GROUP_TAG_MARKER, "", 1)
        else:
            key, short = "", label
        if key not in buckets:
            buckets[key] = {"name": key, "ids": [], "short": {}}
            order.append(key)
        buckets[key]["ids"].append(bid)
        buckets[key]["short"][bid] = short
    return tuple(buckets[key] for key in order)


# Only ConvertScout ships bound, which is exactly what the standalone
# script did: its compiled-in IniRead defaults (111unified.ahk:120-140) and
# its own Reset Defaults handler (:655-676) leave every other bind blank.
# Fidelity is the reason, not caution -- RECOMMENDED_BINDS below is how a
# new user gets a working set without one being imposed on them.
DEFAULT_BINDS = {bid: ("^+s" if bid == "ConvertScout" else "") for bid in BIND_IDS}

# The set the corp actually runs, offered behind the route's "Reset
# defaults" button (the standalone GUI's :319 button, which the port
# dropped). Not DEFAULT_BINDS: applied on request, never silently, so a
# bind the user deliberately cleared cannot come back on its own.
#
# ConvertScout stays at the script's compiled default rather than the ^s
# the shipped INI carries -- maintainer's call.
RECOMMENDED_BINDS = {
    "GrabSig": "^q",
    "SetRoot": "^;",
    "FormatEnf": "^e",
    "ConvertScout": "^+s",
    "FinH": "^y",
    "FinL": "^p",
    "FinN": "^.",
    "Fin13": "^o",
    "Fin1": "^1",
    "Fin2": "^2",
    "Fin3": "^3",
    "Fin4": "^4",
    "Fin5": "^5",
    "Fin6": "^6",
    "FinETag": "^'",
    "FinSlash": "^,",
    "FinS": "^i",
    "FinC": "^x",
}

_SYMBOL_TO_KEY = {sym: key for key, sym, _ in _MODIFIERS}

# Reasons a running engine would register nothing. Returned as ids rather
# than sentences: the page owns the wording, this owns the fact.
NO_WINDOWS = "no_windows"
NO_BINDS = "no_binds"


def registration_blockers(section: dict) -> list[str]:
    """Why a running engine would register no hotkeys at all.

    Two config states produce a live engine that does nothing, and neither
    announces itself. RegisterBind returns early on a blank key WITHOUT
    recording a failure, and the per-window loop it sits inside never
    executes when no window is enabled. Either way the status file is
    written normally with an empty failed_binds, so the UI reports
    "Running", shows no warning, and every keypress does nothing -- which
    looks exactly like the feature being broken.

    Decided here rather than in the page because Wingman generates the INI
    and therefore knows what it would produce. Nothing is inferred.

    Both reasons are reported when both apply: fixing one would leave the
    user in the same silence, and naming only the first sends them round
    twice.
    """
    windows = section.get("windows")
    binds = section.get("keybinds")
    reasons = []
    # isinstance rather than a truthiness test: settings.json is
    # hand-editable, and a wrong type must not be read as a working setup.
    # This is the failure the whole check exists to prevent, so it errs
    # towards warning.
    if not isinstance(windows, dict) or not any(bool(on) for on in windows.values()):
        reasons.append(NO_WINDOWS)
    if not isinstance(binds, dict) or not any(
        str(value).strip() for value in binds.values()
    ):
        reasons.append(NO_BINDS)
    return reasons


def collisions(binds: dict) -> dict:
    """Map each doubly-bound AHK string to every bind id claiming it.

    Blank means "do not register" to RefreshHotkeys, so blanks are skipped
    rather than treated as a shared value. Keyed through parse_ahk() rather
    than the raw trimmed string: AHK accepts modifiers in any order, so
    "+^s" and "^+s" are the same physical hotkey and must collide here --
    the check exists precisely to catch what RefreshHotkeys itself only
    reports as a silent ErrorLevel at registration.
    """
    seen: dict[str, list[str]] = {}
    for bid in BIND_IDS:
        value = (binds.get(bid) or "").strip()
        if not value:
            continue
        # Fall back to the raw value when parse_ahk rejects it: an invalid
        # bind is still worth flagging if it happens to be typed identically
        # twice, and the fallback is exactly what a human typed, so it still
        # reads sensibly if ever shown.
        key = parse_ahk(value)["ahk"] or value
        seen.setdefault(key, []).append(bid)
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

# Bookmark naming is fixed, and there are no naming knobs left anywhere:
# not in the UI, not in settings.json, and not in the INI. The re-vendored
# engine has no [Settings] section at all -- it numbers home holes from .1
# and never prefaces the return bookmark -- so anything written here would
# be config nothing reads. A key that looks like it controls behaviour but
# does not is exactly what cost a debugging session once already.
#
# The one place a preface character is still named is the legacy importer
# below, and only to tell someone migrating from the standalone tool that
# the preface they had is gone. That is a migration note, not a setting.


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

    Window titles come from the OS and bind values from user input; neither
    is trusted to contain a line break. Note: this does not make arbitrary
    text safe as an INI key; it only strips line breaks.
    """
    return "".join(ch for ch in str(value) if ch not in "\r\n").strip()


# Only "EVE - " titles reach the generated file. This used to be described
# as the engine's own constraint, quoting DoSemi's `ActiveTitle ~= "^EVE - "`
# guard -- that guard is gone with the re-vendor, so the engine now scopes
# binds purely by the titles it is handed. The filter stays because the
# reasons below are Wingman's own, and are the load-bearing ones: the title
# is written as an INI KEY, and Windows parses a line starting with "[" as a
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


def decode_ini_bytes(data: bytes) -> str:
    """Decode a legacy helper INI, whichever encoding it was saved in.

    AutoHotkey's IniWrite produces UTF-16 LE with a BOM on a Unicode build,
    which is what the shipped file actually is -- decoding that as UTF-8
    leaves a NUL after every character, so every section header fails
    _parse_ini's "]" test and the whole file imports as nothing. Notepad
    round-trips add a UTF-8 BOM instead, and a hand-written file may have no
    BOM at all. Sniffing the BOM covers all three; UTF-8 with replacement is
    the fallback, because a file we cannot decode should still surface
    whatever ASCII it holds rather than failing outright.
    """
    if data.startswith(b"\xff\xfe"):
        return data.decode("utf-16-le", errors="replace")
    if data.startswith(b"\xfe\xff"):
        return data.decode("utf-16-be", errors="replace")
    return data.decode("utf-8-sig", errors="replace")


def _parse_ini(text: str) -> dict:
    """Minimal INI reader. configparser is not used: the legacy file has
    section keys (window titles) containing '=' and characters configparser
    mangles, and we only need three flat sections."""
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

    section = {"enabled": False, "keybinds": dict(DEFAULT_BINDS), "windows": {}}
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
            # generate_ini writes only "EVE - " titles (see
            # ENGINE_TITLE_PREFIX), so this would be dropped silently on
            # the next write.
            discarded_windows.append(clean)
            continue
        section["windows"][clean] = value.strip() == "1"

    # Nothing is reported as discarded for Mode: the engine implements
    # Flygd/ABH, so Mode=2 is preserved behaviour and saying otherwise
    # would alarm a user who lost nothing. Mode=1 is a real loss and gets a
    # note below that says what actually changes for them.
    discarded = [
        f"{title} (window, not an EVE client window)" for title in discarded_windows
    ]
    # The loop above is over BIND_IDS, so a legacy Copy or Paste bind is
    # dropped by construction. Silently, unless it is named here -- and a
    # user who had bound them will otherwise just find two dead keys.
    discarded += [
        f"{bid} (hotkey, no longer part of Wingman)"
        for bid in ("Copy", "Paste", "FinM")
        if sanitise(legacy_binds.get(bid, ""))
    ]

    notes = []

    # Bookmark naming used to be imported along with everything else. It is
    # fixed now, so instead of carrying a value across, the mismatch has to
    # be described -- these change how every bookmark comes out, and the
    # user has no control left to put them back.
    #
    # Absence means the script's own compiled default, not Wingman's
    # (111unified.ahk:32,114-117), which is why each read defaults to "1"
    # rather than to what Wingman does.
    if legacy_settings.get("HomeZeroIs0", "1").strip() != "0":
        notes.append(
            "Your first home hole was numbered .0. Wingman always numbers "
            "home holes from .1, so they will come out one higher than you "
            "are used to."
        )
    preface_on = legacy_settings.get("PrefaceReturn", "1").strip() != "0"
    # "!" is the standalone script's own compiled default, used when the
    # legacy file omits the key -- not a Wingman value. Wingman has none.
    preface = sanitise(legacy_settings.get("ReturnPreface", "!"))
    if preface_on:
        # The character is quoted back rather than assumed: the legacy file
        # carries whatever the user chose, and "your ! is gone" is no help
        # to someone who had set it to something else.
        notes.append(
            f"Your return bookmarks were prefaced with {preface}. Wingman "
            "does not preface them."
        )

    # Protean/v21 is the one behaviour the engine cannot reproduce, so a
    # user who was running it needs telling in their own terms rather than
    # being left to notice their bookmarks come out differently.
    if legacy_settings.get("Mode", "").strip() == "1":
        notes.append(
            "You were using Protean/v21 naming. Wingman only supports the "
            "Flygd/ABH scheme, so your bookmarks will be formatted "
            "differently."
        )
    # A file that yielded no sections at all did not parse -- an empty
    # config is indistinguishable from a wrong encoding here, and the
    # caller must not save this section over the user's real settings.
    return {
        "section": section,
        "discarded": discarded,
        "notes": notes,
        "parsed": bool(parsed),
    }
