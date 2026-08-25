"""Gesture parsing. Pure, so this is where the real coverage lives -- the
Win32 half cannot be exercised in CI at all."""

from obs_youtube_uploader.preview import gestures


def test_parses_a_modified_function_key():
    g = gestures.parse("Ctrl+Alt+F1")
    assert g.vk == 0x70
    assert g.mods & gestures.MOD_CONTROL
    assert g.mods & gestures.MOD_ALT
    assert not g.mods & gestures.MOD_SHIFT


def test_every_parsed_gesture_carries_no_repeat():
    """Without MOD_NOREPEAT a held chord posts WM_HOTKEY at the keyboard
    repeat rate, and each one runs a full foreground-switch sequence."""
    for text in ("Ctrl+F1", "Alt+Shift+A", "Win+Ctrl+Numpad5"):
        assert gestures.parse(text).mods & gestures.MOD_NOREPEAT


def test_a_chord_with_no_modifier_is_rejected():
    """RegisterHotKey would happily claim a bare F1 desktop-wide, in every
    application, until the process exits."""
    assert gestures.parse("F1") is None
    assert gestures.parse("A") is None


def test_unknown_key_is_rejected():
    assert gestures.parse("Ctrl+Nonsense") is None
    assert gestures.parse("") is None
    assert gestures.parse("Ctrl+") is None


def test_round_trips_through_display():
    for text in (
        "Ctrl+F1",
        "Ctrl+Alt+Shift+A",
        "Win+Delete",
        "Ctrl+Numpad0",
        "Ctrl+,",
        "Alt+[",
    ):
        assert gestures.display(gestures.parse(text)) == text


def test_display_orders_modifiers_canonically():
    """Two spellings of one chord must not read as two different bindings
    in the clash check."""
    assert gestures.display(gestures.parse("Alt+Ctrl+F2")) == "Ctrl+Alt+F2"


def test_accepts_explicit_virtual_key_forms():
    assert gestures.parse("Ctrl+VK_F1") == gestures.parse("Ctrl+F1")
    assert gestures.parse("Ctrl+0x70") == gestures.parse("Ctrl+F1")


def test_capture_maps_a_dom_event():
    result = gestures.from_capture(
        {"ctrl": True, "alt": True, "shift": False, "meta": False, "code": "F1"}
    )
    assert result == {"gesture": "Ctrl+Alt+F1", "error": None}


def test_capture_letters_and_digits():
    assert gestures.from_capture({"ctrl": True, "code": "KeyA"})["gesture"] == "Ctrl+A"
    assert (
        gestures.from_capture({"ctrl": True, "code": "Digit4"})["gesture"] == "Ctrl+4"
    )


def test_capture_reports_a_modifier_only_press_distinctly():
    """The user is still reaching for the combination -- not an error worth
    telling them about, but not a binding either."""
    result = gestures.from_capture({"ctrl": True, "code": "ControlLeft"})
    assert result["error"] == "modifier-only"
    assert result["gesture"] == ""


def test_capture_rejects_an_unmodified_key():
    result = gestures.from_capture({"code": "F1"})
    assert result["error"] == "no-modifier"


def test_capture_rejects_an_unmappable_code():
    result = gestures.from_capture({"ctrl": True, "code": "MediaPlayPause"})
    assert result["error"] == "unmappable"


def test_imports_without_windows():
    """settings.py imports this for validation, and CI is ubuntu-latest."""
    assert gestures.parse("Ctrl+F1") is not None
