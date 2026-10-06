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

import ctypes
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
_STORABLE_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789,./;'`-=[]\\")

_NUMPAD_OPERATORS = frozenset(
    {"NumpadAdd", "NumpadSub", "NumpadMult", "NumpadDiv", "NumpadDot"}
)

# Keys whose stored token names a physical key that sits at the same VK on
# every Windows layout: numpad, F-number, the named non-printing keys. The
# layout cannot change what they produce into a *different* storable key,
# so resolving them can only introduce drift (Numpad4 types "4" on Dvorak;
# storing "4" would silently move the bind onto the digit row). The named
# numpad operators belong here too: they are physical keys with fixed VKs,
# and leaving them out would make every well-defined capture of one warn.
_POSITION_DEFINED = frozenset(
    {
        "Space",
        "Enter",
        "Tab",
        "Escape",
        "Backspace",
        "Delete",
        "Insert",
        "Home",
        "End",
        "PageUp",
        "PageDown",
        "ArrowUp",
        "ArrowDown",
        "ArrowLeft",
        "ArrowRight",
        "NumpadAdd",
        "NumpadSub",
        "NumpadMult",
        "NumpadDiv",
        "NumpadDot",
        "NumpadEnter",
    }
)


def _is_position_defined(code: str) -> bool:
    return (
        code in _POSITION_DEFINED
        or (code.startswith("Numpad") and len(code) == 7 and code[6:].isdigit())
        or (code.startswith("F") and code[1:].isdigit() and 1 <= int(code[1:]) <= 24)
    )


def _representable(token: str) -> bool:
    return (
        (len(token) == 1 and token in _STORABLE_CHARS)
        or token in _NUMPAD_OPERATORS
        or (token.startswith("Numpad") and len(token) == 7 and token[6:].isdigit())
        or (token.startswith("F") and token[1:].isdigit() and 1 <= int(token[1:]) <= 24)
    )


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
    except Exception:  # noqa: BLE001 -- degrade, never fail a capture
        return Resolution("position", None, "resolver-failed")
    if char is None:
        return Resolution("position", None, "no-layout")
    if not _representable(char):
        return Resolution("position", None, "not-representable")
    return Resolution("layout", char)


# --- the Windows layout view ------------------------------------------------

_MAPVK_VK_TO_VSC = 0
_MAPVK_VSC_TO_VK = 1
_MAPVK_VSC_TO_VK_EX = 3

# DOM position -> physical scancode, the "Writing System Keys" rows of the
# W3C uievents-code table (US-layout PS/2 Set 1 make codes). event.code
# names a PHYSICAL key, so this table is layout-independent by definition:
# it is what makes the view's first leg a position lookup rather than a
# lookup under the user's own layout (which would be circular -- Dvorak
# relocates the VKs, and the round trip would collapse into an identity).
_POSITION_SCAN = {
    "Backquote": 0x29,
    "Digit1": 0x02,
    "Digit2": 0x03,
    "Digit3": 0x04,
    "Digit4": 0x05,
    "Digit5": 0x06,
    "Digit6": 0x07,
    "Digit7": 0x08,
    "Digit8": 0x09,
    "Digit9": 0x0A,
    "Digit0": 0x0B,
    "Minus": 0x0C,
    "Equal": 0x0D,
    "KeyQ": 0x10,
    "KeyW": 0x11,
    "KeyE": 0x12,
    "KeyR": 0x13,
    "KeyT": 0x14,
    "KeyY": 0x15,
    "KeyU": 0x16,
    "KeyI": 0x17,
    "KeyO": 0x18,
    "KeyP": 0x19,
    "BracketLeft": 0x1A,
    "BracketRight": 0x1B,
    "Backslash": 0x2B,
    "KeyA": 0x1E,
    "KeyS": 0x1F,
    "KeyD": 0x20,
    "KeyF": 0x21,
    "KeyG": 0x22,
    "KeyH": 0x23,
    "KeyJ": 0x24,
    "KeyK": 0x25,
    "KeyL": 0x26,
    "Semicolon": 0x27,
    "Quote": 0x28,
    "Enter": 0x1C,
    "KeyZ": 0x2C,
    "KeyX": 0x2D,
    "KeyC": 0x2E,
    "KeyV": 0x2F,
    "KeyB": 0x30,
    "KeyN": 0x31,
    "KeyM": 0x32,
    "Comma": 0x33,
    "Period": 0x34,
    "Slash": 0x35,
    "Space": 0x39,
}


def win32_available(user32) -> bool:
    """Both functions the view needs, present (skipped on Wine-like shims)."""
    return bool(
        getattr(user32, "MapVirtualKeyExW", None)
        and getattr(user32, "ToUnicodeEx", None)
    )


def _pin_user32_signatures(user32) -> None:
    """Pin the W-function signatures before first use.

    Without them ctypes marshals HKL as a 32-bit c_int: GetKeyboardLayout's
    value comes back negative, goes back in half-width, and MapVirtualKeyExW
    fails with 0 on real x64 Windows -- the failure the injected-fake tests
    cannot see. HKL travels as c_size_t (unsigned, pointer-sized); every
    code is c_uint so 0xBA-style VKs never ride as negative ints.

    A test double's plain methods have no argtypes to pin: the assignment
    raises AttributeError there, which means "fake" and pins nothing.
    """
    from ctypes import c_int, c_size_t, c_uint, c_void_p, c_wchar_p

    try:
        user32.GetKeyboardLayout.argtypes = (c_uint,)
        user32.GetKeyboardLayout.restype = c_size_t
        user32.MapVirtualKeyExW.argtypes = (c_uint, c_uint, c_size_t)
        user32.MapVirtualKeyExW.restype = c_uint
        user32.ToUnicodeEx.argtypes = (
            c_uint,
            c_uint,
            c_void_p,
            c_wchar_p,
            c_int,
            c_uint,
            c_size_t,
        )
        user32.ToUnicodeEx.restype = c_int
    except AttributeError:
        return


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
    from ctypes import c_ubyte, create_unicode_buffer  # noqa: I001 -- lazy Win32 imports stay at point of use

    def view(code: str):
        # Leg 1 is the FIXED position table, not a lookup under the user's
        # layout: the DOM code names a physical key, and asking this layout
        # for that key's scancode would relocate it (Dvorak's VKs move) and
        # collapse the whole chain into an identity.
        sc = _POSITION_SCAN.get(code)
        if sc is None:
            return None
        # Legs 2 and 3 run under the user's layout: which VK sits at this
        # physical key, and what character that VK produces.
        layout_vk = user32.MapVirtualKeyExW(sc, _MAPVK_VSC_TO_VK_EX, hkl)
        if not layout_vk:
            return None
        buf = create_unicode_buffer(8)
        # n == 1 is the only clean answer: 0 is unbound, < 0 is a dead key,
        # > 1 is a ligature or surrogate pair -- all unrepresentable here.
        n = user32.ToUnicodeEx(layout_vk, sc, (c_ubyte * 256)(), buf, len(buf), 0, hkl)
        if n != 1:
            return None
        return buf.value

    return view


def char_vk(char: str):
    """The layout's own answer to "which key types this character".

    Returns ``(vk, shift)`` -- the virtual key VkKeyScanExW binds the
    character to under the foreground thread's layout, and whether that
    binding includes Shift. None when Win32 is unavailable (Linux tests
    and stripped builds), the character is not exactly one WCHAR, or no
    key on the layout produces it.

    The stream coupling's send (#320) needs this direction: the stored
    chord holds the character the layout PRODUCED at capture time (ADR
    0002), and replaying it faithfully means pressing the key this
    layout types it with -- not the US-layout guess a static table
    would make (";" sits elsewhere on half the layouts). The reverse
    direction is windows_layout_view above.
    """
    if not isinstance(char, str) or len(char) != 1:
        return None
    import ctypes

    try:
        user32 = ctypes.windll.user32
    except (AttributeError, OSError, ImportError):
        return None
    if not win32_available(user32):
        return None
    from ctypes import c_short, c_size_t, c_wchar

    try:
        user32.VkKeyScanExW.argtypes = (c_wchar, c_size_t)
        user32.VkKeyScanExW.restype = c_short
    except AttributeError:
        return None
    hkl = _foreground_hkl(user32)
    # Low byte is the VK, bit 0 of the high byte is Shift (2=Ctrl, 4=Alt).
    # -1 (c_short) means the layout cannot produce the character.
    result = user32.VkKeyScanExW(char, hkl)
    if result == -1:
        return None
    vk = result & 0xFF
    if not vk:
        return None
    return (vk, bool(result & 0x0100))


# One built view per layout HKL, so a capture costs two syscalls, not a
# signature re-pin and a closure per keystroke. Layouts are per-thread and
# switched rarely; the dict is bounded by how many layouts the user has.
_VIEWS = {}


def _foreground_hkl(user32):
    """The layout of the thread receiving the keys.

    GetGUIThreadInfo(NULL) describes the foreground input thread; its focus
    window's thread owns the layout the user's keystrokes land under. Zero
    (no foreground, or a blocked call) falls back to the calling thread's
    own layout -- in Wingman that thread serves the capture UI anyway.
    """
    from ctypes import (
        Structure,
        c_size_t,
        c_uint,
        c_void_p,
        pointer,
    )

    class GUITHREADINFO(Structure):
        _fields_ = [
            ("cbSize", c_uint),
            ("flags", c_uint),
            ("hwndActive", c_void_p),
            ("hwndFocus", c_void_p),
            ("hwndCapture", c_void_p),
            ("hwndMenuOwner", c_void_p),
            ("hwndMoveSize", c_void_p),
            ("hwndCaret", c_void_p),
            ("rcCaret", c_size_t * 4),
        ]

    info = GUITHREADINFO()
    info.cbSize = ctypes.sizeof(GUITHREADINFO)
    get_info = getattr(user32, "GetGUIThreadInfo", None)
    if get_info is not None and get_info(0, pointer(info)):
        thread = user32.GetWindowThreadProcessId(info.hwndFocus, None)
        if thread:
            return user32.GetKeyboardLayout(thread)
    return user32.GetKeyboardLayout(0)


def bridge_view():
    """The view the bridge uses, on this process's input desktop.

    The capture UI lives in the WebView2 window; the layout consulted is the
    foreground thread's -- the one actually receiving the user's keys
    (layouts are per-thread, and a user mid-switch may have per-window
    layouts). Views are cached per layout, so a capture costs two syscalls.
    None when Win32 is unavailable -- Linux tests and stripped builds get
    the position-only path, not an exception.
    """
    import ctypes

    try:
        user32 = ctypes.windll.user32
    except (AttributeError, OSError, ImportError):
        return None
    if not win32_available(user32):
        return None
    _pin_user32_signatures(user32)
    hkl = _foreground_hkl(user32)
    view = _VIEWS.get(hkl)
    if view is None:
        view = windows_layout_view(user32, hkl=hkl)
        _VIEWS[hkl] = view
    return view


def capture_parts(parts: dict) -> dict:
    """Enrich a captured DOM key event with the layout's answer.

    Never raises and never errors: any failure degrades to the position
    mapping with a warn reason (ADR 0002). Position-defined keys (numpad,
    F-keys, named keys) skip the view entirely -- the layout cannot change
    what they mean, so consulting it can only add drift.
    """
    code = parts.get("code") or ""
    # `produced`/`warn_reason` are this module's reserved outputs. They are
    # stripped before anything else so a crafted page payload cannot
    # dictate what a capture stores: only this module's resolution --
    # against a layout this side of the bridge actually consulted -- may
    # set them.
    enriched = {
        key: value
        for key, value in parts.items()
        if key not in ("produced", "warn_reason")
    }
    try:
        view = bridge_view()
        missing_reason = "no-layout"
    except Exception:  # noqa: BLE001 -- degrade, never fail a capture
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
        # position-defined keys degrade silently: nothing about them
        # changed, and the strip above guarantees no stale warn survives.
        if resolved.reason != "position-defined":
            enriched["warn_reason"] = resolved.reason
    return enriched
