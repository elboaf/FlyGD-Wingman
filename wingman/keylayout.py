"""Resolve a captured key's position code to what the user's layout produces.

ADR 0002: keybind capture on a non-QWERTY layout stored the wrong letter,
because `event.code` names the physical key and the stored hotkey means "the
key that produces this letter" (AHK binds character keys against the active
layout at registration). This module is the one seam both capture paths go
through so they cannot drift.

Pure by construction: the Windows layout view is injected, so the whole
resolver is unit-testable on Linux; only the real view's thin wrapper
binds Win32.
"""

from typing import NamedTuple


class Resolution(NamedTuple):
    kind: str
    token: str
    reason: str | None = None


# The characters a stored hotkey token can carry. Letters and digits are
# AHK-safe by construction; the punctuation list is exactly the punctuation
# keys the two capture tables have always mapped, i.e. the alphabet Edit...
# validation (parse_ahk) and the engine's INI round-trip already accept.
# A produced character outside this set (é, a dead key's combining mark, a
# multi-character ligature) has no storable spelling, so capture degrades to
# the position-derived key -- ADR 0002's warn-and-degrade rule.
_STORABLE_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyz0123456789,./;'`-=[]\\"
)

_NUMPAD_OPERATORS = frozenset(
    {"NumpadAdd", "NumpadSub", "NumpadMult", "NumpadDiv", "NumpadDot"}
)

# Keys whose stored token names a physical key that sits at the same VK on
# every Windows layout: numpad, F-number, the named non-printing keys. The
# layout cannot change what they produce into a *different* storable key,
# so resolving them can only introduce drift (Numpad4 types "4" on Dvorak;
# storing "4" would silently move the bind onto the digit row).
_POSITION_DEFINED = frozenset(
    {"Space", "Enter", "Tab", "Escape", "Backspace", "Delete", "Insert",
     "Home", "End", "PageUp", "PageDown",
     "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"}
)


def _is_position_defined(code: str) -> bool:
    if code in _POSITION_DEFINED:
        return True
    if code.startswith("Numpad") and len(code) == 7 and code[6:].isdigit():
        return True
    if code.startswith("F") and code[1:].isdigit() and 1 <= int(code[1:]) <= 24:
        return True
    return False


def _representable(token: str) -> bool:
    if len(token) == 1 and token in _STORABLE_CHARS:
        return True
    if token in _NUMPAD_OPERATORS:
        return True
    if token.startswith("Numpad") and len(token) == 7 and token[6:].isdigit():
        return True
    if token.startswith("F") and token[1:].isdigit() and 1 <= int(token[1:]) <= 24:
        return True
    return False


def resolve(view, code: str) -> Resolution:
    """What the layout view says `code` produces, or a position fallback.

    kind "layout": `token` is the produced character.
    kind "position": `token` is None -- the caller derives its own
    position token from its existing table, because the two consumers keep
    different case conventions for it. `reason` says why resolution did not
    apply. Never raises: a resolver failure must not turn a capture into an
    error, it degrades to today's behavior.
    """
    if _is_position_defined(code):
        return Resolution("position", None, "position-defined")
    try:
        char = view(code)
    except Exception:
        return Resolution("position", None, "resolver-failed")
    if char is None:
        return Resolution("position", None, "no-layout")
    if not _representable(char):
        return Resolution("position", None, "not-representable")
    return Resolution("layout", char)


# --- the Windows layout view ------------------------------------------------

_MAPVK_VK_TO_VSC = 0
_MAPVK_VSC_TO_VK_EX = 4

# Position -> VK for the consultable punctuation positions. Letters and
# digits keep their fixed VKs (0x41+, 0x30+); these do too (the OEM-1..8
# block), but they are the ones with no arithmetic spelling.
_PUNCT_VK = {
    "Semicolon": 0xBA,
    "Equal": 0xBB,
    "Comma": 0xBC,
    "Minus": 0xBD,
    "Period": 0xBE,
    "Slash": 0xBF,
    "Backquote": 0xC0,
    "BracketLeft": 0xDB,
    "Backslash": 0xDC,
    "BracketRight": 0xDD,
    "Quote": 0xDE,
}


def win32_available(user32) -> bool:
    """Both functions the view needs, present (skipped on Wine-like shims)."""
    return bool(
        getattr(user32, "MapVirtualKeyExW", None)
        and getattr(user32, "ToUnicodeEx", None)
    )


def _position_vk(code: str) -> int | None:
    if len(code) == 4 and code.startswith("Key"):
        return 0x41 + ord(code[3].upper()) - ord("A")
    if len(code) == 6 and code.startswith("Digit") and code[5].isdigit():
        return 0x30 + int(code[5])
    return _PUNCT_VK.get(code)


def windows_layout_view(user32, hkl=None):
    """The injected view: position code -> produced character, via the
    documented chain. `hkl` is the layout of the thread that receives the
    keys; None asks for the calling thread's (GetKeyboardLayout(0)).

    ToUnicodeEx runs with a zeroed key state on purpose: the bridge resolves
    the *base* character and leaves the captured modifier flags alone, so
    Shift never has to be reversed -- the same reason event.code was chosen
    over event.key in the original design.
    """
    if hkl is None:
        hkl = user32.GetKeyboardLayout(0)
    from ctypes import c_ubyte, create_unicode_buffer

    def view(code: str):
        vk = _position_vk(code)
        if vk is None:
            return None
        sc = user32.MapVirtualKeyExW(vk, _MAPVK_VK_TO_VSC, hkl)
        if not sc:
            return None
        layout_vk = user32.MapVirtualKeyExW(sc, _MAPVK_VSC_TO_VK_EX, hkl)
        if not layout_vk:
            return None
        buf = create_unicode_buffer(8)
        # n == 1 is the only clean answer: 0 is unbound, < 0 is a dead key,
        # > 1 is a ligature or surrogate pair -- all unrepresentable here.
        n = user32.ToUnicodeEx(
            layout_vk, sc, (c_ubyte * 256)(), buf, len(buf), 0, hkl
        )
        if n != 1:
            return None
        return buf.value

    return view


def bridge_view():
    """The view the bridge uses, on this process's input desktop.

    The capture UI lives in the WebView2 window, whose thread's layout is
    what the user is pressing keys under (layouts are per-thread; the
    foreground app can differ). None when Win32 is unavailable -- Linux
    tests and stripped builds get the position-only path, not an exception.
    """
    import ctypes

    try:
        user32 = ctypes.windll.user32
    except (AttributeError, OSError, ImportError):
        return None
    if not win32_available(user32):
        return None
    return windows_layout_view(user32)


def capture_parts(parts: dict) -> dict:
    """Enrich a captured DOM key event with the layout's answer.

    Never raises and never errors: any failure degrades to the position
    mapping with a warn reason (ADR 0002). Position-defined keys (numpad,
    F-keys, named keys) skip the view entirely -- the layout cannot change
    what they mean, so consulting it can only add drift.
    """
    code = parts.get("code") or ""
    enriched = dict(parts)
    try:
        view = bridge_view()
        missing_reason = "no-layout"
    except Exception:
        view = None
        missing_reason = "resolver-failed"
    if view is None:
        if code and not _is_position_defined(code):
            return {**enriched, "warn_reason": missing_reason}
        return enriched
    resolved = resolve(view, code)
    if resolved.kind == "layout":
        enriched["produced"] = resolved.token
    else:
        # position-defined keys degrade silently: nothing about them changed.
        if resolved.reason == "position-defined":
            enriched.pop("warn_reason", None)
        else:
            enriched["warn_reason"] = resolved.reason
    return enriched