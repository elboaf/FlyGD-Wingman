"""The INI is a generated artifact: Wingman writes it, the engine only ever
reads it. These tests pin the exact bytes because the consumer is an AHK
script we cannot test."""
from obs_youtube_uploader import bookmarks


def section(**over):
    base = {"enabled": True, "keybinds": dict(bookmarks.DEFAULT_BINDS),
            "windows": {}}
    base.update(over)
    return base


def test_uses_crlf_and_ends_with_a_newline():
    """GetPrivateProfileString is a Windows API reading a Windows file."""
    text = bookmarks.generate_ini(section())
    assert "\r\n" in text
    assert text.endswith("\r\n")
    assert "\n" not in text.replace("\r\n", "")


def test_every_bind_is_written_even_when_blank():
    """Blank means "do not register" to RefreshHotkeys (111unified.ahk:719).
    Omitting the key entirely would leave IniRead returning its default
    instead, which for ConvertScout is ^+s -- so a deliberately cleared
    bind would come back."""
    text = bookmarks.generate_ini(section())
    for bid in bookmarks.BIND_IDS:
        assert f"{bid}=" in text
    assert "ConvertScout=^+s\r\n" in text
    assert "FinH=\r\n" in text


def test_enabled_windows_are_written_as_one_and_zero():
    text = bookmarks.generate_ini(section(
        windows={"EVE - Pilot": True, "EVE - Alt": False}))
    assert "[Enabled]\r\n" in text
    assert "EVE - Pilot=1\r\n" in text
    assert "EVE - Alt=0\r\n" in text


def test_semicolon_bind_survives():
    """Windows INI treats ; as a comment only at line start, and the value
    reaches AHK through IniRead into a variable so it is never parsed as
    script text. Pinned by a test rather than by confidence."""
    text = bookmarks.generate_ini(section(
        keybinds=dict(bookmarks.DEFAULT_BINDS, FinH="^;")))
    assert "FinH=^;\r\n" in text


def test_newline_in_a_window_title_cannot_forge_a_line():
    """Window titles come from the OS, but a hostile or malformed one must
    not be able to inject an extra INI entry. Asserted line-anchored: the
    sanitised title becomes "EVE - BadFinH=1", which *contains* "FinH=1"
    as a substring without being a forged line."""
    text = bookmarks.generate_ini(section(
        windows={"EVE - Bad\r\nFinH": True}))
    lines = text.split("\r\n")
    assert "FinH=1" not in lines
    assert "EVE - BadFinH=1" in lines


def test_no_mode_or_preface_settings():
    """Protean/v21, HomeZeroIs0 and the return preface are gone; the engine
    hardcodes their surviving behaviour."""
    text = bookmarks.generate_ini(section())
    for gone in ("Mode", "HomeZeroIs0", "PrefaceReturn", "ReturnPreface"):
        assert gone not in text
