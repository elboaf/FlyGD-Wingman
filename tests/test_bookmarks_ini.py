"""The INI is a generated artifact: Wingman writes it, the engine only ever
reads it. These tests pin the exact bytes because the consumer is an AHK
script we cannot test."""

import pytest

from wingman import bookmarks, settings


def section(**over):
    # Built from the real validator rather than a literal, so the fixture
    # cannot drift from the schema generate_ini is actually handed.
    base = settings.validated_eve({})
    base["enabled"] = True
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
    text = bookmarks.generate_ini(
        section(windows={"EVE - Pilot": True, "EVE - Alt": False})
    )
    assert "[Enabled]\r\n" in text
    assert "EVE - Pilot=1\r\n" in text
    assert "EVE - Alt=0\r\n" in text


def test_semicolon_bind_survives():
    """Windows INI treats ; as a comment only at line start, and the value
    reaches AHK through IniRead into a variable so it is never parsed as
    script text. Pinned by a test rather than by confidence."""
    text = bookmarks.generate_ini(
        section(keybinds=dict(bookmarks.DEFAULT_BINDS, FinH="^;"))
    )
    assert "FinH=^;\r\n" in text


def test_newline_in_a_window_title_cannot_forge_a_line():
    """Window titles come from the OS, but a hostile or malformed one must
    not be able to inject an extra INI entry. Asserted line-anchored: the
    sanitised title becomes "EVE - BadFinH=1", which *contains* "FinH=1"
    as a substring without being a forged line."""
    text = bookmarks.generate_ini(section(windows={"EVE - Bad\r\nFinH": True}))
    lines = text.split("\r\n")
    assert "FinH=1" not in lines
    assert "EVE - BadFinH=1" in lines


def test_no_settings_section_is_written_at_all():
    """The re-vendored engine reads only [Keybinds] and [Enabled].

    Wingman used to write HomeZeroIs0, PrefaceReturn and ReturnPreface on
    every pass so the engine could not fall back to its own compiled
    defaults. The engine has no such settings now -- it numbers home holes
    from .1 and never prefaces -- so writing them would be config that
    nothing reads. test_engine_invariants pins the other half of this: the
    engine must not grow a read of a section Wingman no longer writes.
    """
    text = bookmarks.generate_ini(section())
    assert "[Settings]" not in text
    assert "Mode=" not in text
    for key in ("HomeZeroIs0", "PrefaceReturn", "ReturnPreface"):
        assert key not in text, key
    assert text.split("\r\n\r\n")[-1].startswith("[Enabled]")


def test_naming_is_fixed_and_ignores_whatever_the_section_says():
    """The controls are gone, so a stale settings.json -- or a hand-edited
    one -- must not be able to steer naming, or to smuggle a line into the
    INI through a value that never reaches it."""
    text = bookmarks.generate_ini(
        section(home_zero=True, preface_return=True, return_preface="@\r\nMode=1")
    )
    assert "[Settings]" not in text
    assert "@" not in text
    assert "\r\nMode=1\r\n" not in text


def test_no_naming_constants_survive():
    """Belt and braces on the pair above. These names existed to be written
    into [Settings]; leaving one defined invites a future writer to start
    emitting it again, which the engine would then ignore in silence."""
    for name in ("HOME_ZERO", "PREFACE_RETURN", "RETURN_PREFACE"):
        assert not hasattr(bookmarks, name), name


@pytest.mark.parametrize(
    "title",
    [
        "[Keybinds]",
        ";EVE - Pilot",
        "Notepad",
        "EVE - A=B",
        "",
    ],
)
def test_titles_the_engine_could_never_match_are_dropped(title):
    """Titles are written as INI keys. A leading "[" is parsed as a section
    header and would relocate every following entry; a leading ";" as a
    comment; an embedded "=" moves the key/value split. The engine only ever
    matches ^EVE - , so filtering on that closes all three."""
    text = bookmarks.generate_ini(section(windows={title: True}))
    body = text.split("[Enabled]\r\n", 1)[1]
    assert body.strip() == ""


def test_real_eve_titles_still_pass():
    text = bookmarks.generate_ini(
        section(windows={"EVE - Pilot One": True, "EVE - Alt Two": False})
    )
    lines = text.split("\r\n")
    assert "EVE - Pilot One=1" in lines
    assert "EVE - Alt Two=0" in lines
