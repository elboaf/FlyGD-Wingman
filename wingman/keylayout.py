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