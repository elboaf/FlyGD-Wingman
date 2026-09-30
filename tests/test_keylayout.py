"""The layout-aware capture resolver (ADR 0002).

Fakes stand in for the Windows layout view, so the whole resolver is
exercised off-Windows; the real view's Win32 marshalling is tested with an
injected fake in the same spirit as the other injected seams.
"""

import types

from wingman import keylayout


def test_dvorak_g_position_produces_i():
    """Issue #305's exact repro: on Dvorak the key that types `i` sits at
    the physical position QWERTY calls KeyG, so capture must store from the
    produced character, not the position."""
    dvorak = {"KeyG": "i"}
    got = keylayout.resolve(dvorak.get, "KeyG")
    assert got.token == "i"
    assert got.kind == "layout"


def test_produced_letter_from_any_position_stores_that_letter():
    """AZERTY: the key QWERTY calls Semicolon types `m`. The stored string
    must say `m` -- the letter -- regardless of where the key sits."""
    azerty = {"Semicolon": "m"}
    got = keylayout.resolve(azerty.get, "Semicolon")
    assert got == keylayout.Resolution("layout", "m")


def test_produced_punctuation_in_the_representable_set_stores_it():
    got = keylayout.resolve({"Slash": ","}.get, "Slash")
    assert got == keylayout.Resolution("layout", ",")


def test_produced_character_outside_the_storable_set_falls_back():
    """`é` cannot be written as a Wingman hotkey token at all, so capture
    must degrade to the position-derived key and carry the reason for the
    warning, instead of storing something the engine cannot register. The
    position token itself is the caller's to derive: bookmarks and gestures
    keep their own case conventions for it."""
    got = keylayout.resolve({"Digit2": "é"}.get, "Digit2")
    assert got.token is None
    assert got.kind == "position"
    assert got.reason == "not-representable"


def test_multi_character_production_falls_back():
    got = keylayout.resolve({"KeyP": "ss"}.get, "KeyP")
    assert got.kind == "position"
    assert got.reason == "not-representable"


def test_control_character_production_falls_back():
    """A consultable position that somehow produces a control character has
    no storable spelling either."""
    got = keylayout.resolve({"Comma": "\x1b"}.get, "Comma")
    assert got.kind == "position"
    assert got.reason == "not-representable"


def test_numpad_keys_keep_position_identity():
    """Dvorak's Numpad4 still types `4`, but storing "4" would silently
    turn a numpad bind into a digit-row bind -- VK 0x60-0x69 is where the
    numpad sits regardless of layout. Position-defined keys never resolve."""
    got = keylayout.resolve({"Numpad4": "4"}.get, "Numpad4")
    assert got == keylayout.Resolution("position", None, "position-defined")


def test_numpad_operators_keep_position_identity_without_warning():
    """The named operators are physical keys with fixed VKs: pass-through,
    and no warn -- nothing about them degraded."""
    for code in (
        "NumpadAdd",
        "NumpadSub",
        "NumpadMult",
        "NumpadDiv",
        "NumpadDot",
        "NumpadEnter",
    ):
        got = keylayout.resolve({code: "?"}.get, code)
        assert got == keylayout.Resolution("position", None, "position-defined"), code


def test_named_keys_keep_position_identity():
    """Space, Enter, arrows, nav keys and F-keys sit at layout-independent
    VKs on every Windows layout; consulting the view for them can only
    introduce drift, never information."""
    for code in ("Space", "Enter", "F5", "ArrowUp", "PageDown", "Escape"):
        got = keylayout.resolve({code: "?"}.get, code)
        assert got == keylayout.Resolution("position", None, "position-defined"), code


# --- the Windows layout view (injected user32; see windows_layout_view) ---


class _FakeUser32:
    """Maps by scancode -> layout-VK -> produced character, the two legs
    the real API performs under the user's layout (leg 1, the fixed
    position table, is keylayout's own)."""

    def __init__(self, sc_to_vk, vk_to_char):
        self._sc_to_vk = sc_to_vk
        self._vk_to_char = vk_to_char

    def MapVirtualKeyExW(self, code, mode, hkl):
        if mode == keylayout._MAPVK_VSC_TO_VK_EX:
            return self._sc_to_vk.get(code, 0)
        return 0

    def ToUnicodeEx(self, vk, sc, keystate, buf, size, flags, hkl):
        char = self._vk_to_char.get(vk)
        if char is None:
            return 0
        buf.value = char
        return 1


def test_windows_view_resolves_position_to_produced_character():
    # Dvorak: the key at the G position (Set 1 scancode 0x22) hosts VK 0x49
    # (`i`), and that VK produces `i`.
    user32 = _FakeUser32({0x22: 0x49}, {0x49: "i"})
    view = keylayout.windows_layout_view(user32, hkl=0xF001041)
    got = keylayout.resolve(view, "KeyG")
    assert got == keylayout.Resolution("layout", "i")


def test_windows_view_punctuation_position_resolves():
    # AZERTY: the key at the Semicolon position (scancode 0x27) hosts VK 0x4D
    # (`m`), and that VK produces `m`.
    user32 = _FakeUser32({0x27: 0x4D}, {0x4D: "m"})
    view = keylayout.windows_layout_view(user32, hkl=0x40C)
    got = keylayout.resolve(view, "Semicolon")
    assert got == keylayout.Resolution("layout", "m")


def test_windows_view_returns_none_for_unbound_position():
    user32 = _FakeUser32({}, {})
    view = keylayout.windows_layout_view(user32, hkl=7)
    assert keylayout.resolve(view, "KeyG").reason == "no-layout"


def test_windows_view_falls_back_to_current_thread_layout():
    class WithLayout(_FakeUser32):
        def GetKeyboardLayout(self, thread):
            return 0xF0020409

    user32 = WithLayout({0x22: 0x49}, {0x49: "i"})
    view = keylayout.windows_layout_view(user32)
    assert keylayout.resolve(view, "KeyG").kind == "layout"


def test_win32_available_requires_both_functions():
    assert keylayout.win32_available(object()) is False
    user32 = _FakeUser32({}, {})
    assert keylayout.win32_available(user32) is True


# --- which layout the bridge consults (receiving thread, cached) -----------


def test_bridge_view_uses_the_receiving_threads_layout(monkeypatch):
    """ADR 0002's consequence: the layout consulted is the one receiving
    the keys (the foreground thread the capture UI types into), not
    blindly the calling thread's."""
    calls = []

    class Receiving(_FakeUser32):
        def GetGUIThreadInfo(self, thread, info):
            calls.append("gti")
            info.contents.hwndFocus = 0x1234
            return 1

        def GetWindowThreadProcessId(self, hwnd, unused):
            calls.append(("tid", hwnd))
            return 4242

        def GetKeyboardLayout(self, thread):
            calls.append(("layout", thread))
            return 0xA if thread == 4242 else 0xB

    monkeypatch.setattr(keylayout, "_VIEWS", {})
    user32 = Receiving({0x22: 0x49}, {0x49: "i"})
    monkeypatch.setattr(
        keylayout.ctypes, "windll", types.SimpleNamespace(user32=user32), raising=False
    )
    view = keylayout.bridge_view()
    assert view is not None
    assert ("layout", 4242) in calls, calls


def test_bridge_view_falls_back_to_the_calling_thread(monkeypatch):
    class NoForeground(_FakeUser32):
        def GetGUIThreadInfo(self, thread, info):
            return 0

        def GetKeyboardLayout(self, thread):
            return 0xC

    monkeypatch.setattr(keylayout, "_VIEWS", {})
    user32 = NoForeground({0x22: 0x49}, {0x49: "i"})
    monkeypatch.setattr(
        keylayout.ctypes, "windll", types.SimpleNamespace(user32=user32), raising=False
    )
    assert keylayout.bridge_view() is not None


def test_bridge_view_caches_one_view_per_layout(monkeypatch):
    """One ctypes signature pin and one closure per layout, not one per
    captured keystroke."""

    class Counting(_FakeUser32):
        built = 0
        layouts = iter([0xA, 0xA, 0xB])

        def GetGUIThreadInfo(self, thread, info):
            return 0

        def GetKeyboardLayout(self, thread):
            try:
                return next(self.layouts)
            except StopIteration:
                return 0xB

    monkeypatch.setattr(keylayout, "_VIEWS", {})
    user32 = Counting({0x22: 0x49}, {0x49: "i"})
    monkeypatch.setattr(
        keylayout.ctypes, "windll", types.SimpleNamespace(user32=user32), raising=False
    )
    first = keylayout.bridge_view()
    second = keylayout.bridge_view()
    third = keylayout.bridge_view()
    assert first is second
    assert third is not first
    assert sorted(keylayout._VIEWS) == [0xA, 0xB]


def test_page_supplied_bridge_keys_are_never_trusted():
    """`produced`/`warn_reason` are the bridge's reserved keys: the page
    sends only what a DOM event carries, and a crafted payload must not be
    able to dictate what a capture stores."""
    parts = {
        "ctrl": True,
        "code": "Numpad4",
        "produced": "a",
        "warn_reason": "not-representable",
    }
    got = keylayout.capture_parts(parts)
    assert "produced" not in got
    assert "warn_reason" not in got
