"""Retiring the standalone script without importing its INI would discard
every existing user's configuration, which -- since Wingman is meant to
REPLACE the script -- is everyone, not an edge case."""
from obs_youtube_uploader import bookmarks

LEGACY = (
    "[Settings]\r\n"
    "HomeZeroIs0=1\r\n"
    "Mode=2\r\n"
    "PrefaceReturn=1\r\n"
    "ReturnPreface=!\r\n"
    "[Keybinds]\r\n"
    "Copy=^c\r\n"
    "Paste=^v\r\n"
    "GrabSig=q\r\n"
    "SetRoot=`;\r\n"
    "FinH=y\r\n"
    "ConvertScout=^+s\r\n"
    "[Enabled]\r\n"
    "EVE - Pilot=1\r\n"
    "EVE - Alt=0\r\n"
)

# Deliberately [Keybinds]-first, matching what the standalone script writes
# (111unified.ahk:143-165 before :167-171). The BOM test needs this order:
# with [Settings] first, a BOM destroys [Settings] and the bind assertions
# would pass whether or not the guard exists.
KEYBINDS_FIRST = (
    "[Keybinds]\r\nGrabSig=q\r\nFinH=y\r\nCopy=^c\r\n"
    "[Settings]\r\nHomeZeroIs0=0\r\nMode=2\r\n"
    "[Enabled]\r\nEVE - Pilot=1\r\n"
)


def test_binds_that_still_exist_are_carried_over():
    got = bookmarks.import_legacy_ini(LEGACY)
    assert got["section"]["keybinds"]["GrabSig"] == "q"
    assert got["section"]["keybinds"]["FinH"] == "y"
    assert got["section"]["keybinds"]["ConvertScout"] == "^+s"


def test_window_enablement_is_carried_over():
    got = bookmarks.import_legacy_ini(LEGACY)
    assert got["section"]["windows"] == {"EVE - Pilot": True,
                                         "EVE - Alt": False}


def test_copy_and_paste_are_carried_over():
    """Cut in the first port, restored. A user who loses a working key
    would only find out by pressing it and getting nothing."""
    got = bookmarks.import_legacy_ini(LEGACY)
    assert got["section"]["keybinds"]["Copy"] == "^c"
    assert got["section"]["keybinds"]["Paste"] == "^v"
    assert not any("Copy" in d for d in got["discarded"])


def test_settings_are_carried_over():
    got = bookmarks.import_legacy_ini(LEGACY)["section"]
    assert got["home_zero"] is True
    assert got["preface_return"] is True
    assert got["return_preface"] == "!"


def test_absent_settings_take_the_SCRIPT_default_not_wingman_s():
    """The whole point of importing is that nobody is renumbered. A legacy
    file with no HomeZeroIs0 was being numbered from .0
    (111unified.ahk:32), so it must import as .0 even though a fresh
    Wingman install defaults to .1."""
    got = bookmarks.import_legacy_ini("[Keybinds]\r\nFinH=y\r\n")["section"]
    assert got["home_zero"] is True
    assert got["preface_return"] is True
    assert got["return_preface"] == "!"


def test_home_zero_off_is_carried_over_rather_than_described():
    """This used to emit a note saying the user was about to be renumbered.
    The setting exists again, so there is nothing to warn about."""
    off = LEGACY.replace("HomeZeroIs0=1", "HomeZeroIs0=0")
    got = bookmarks.import_legacy_ini(off)
    assert got["section"]["home_zero"] is False
    assert not any(".0" in n and ".1" in n for n in got["notes"])


def test_protean_is_the_one_thing_still_reported():
    got = bookmarks.import_legacy_ini(LEGACY.replace("Mode=2", "Mode=1"))
    assert any("Protean" in n for n in got["notes"])
    assert not any("Protean" in n
                   for n in bookmarks.import_legacy_ini(LEGACY)["notes"])


def test_import_never_enables_the_engine():
    """Importing settings is not consent to start a keyboard hook."""
    assert bookmarks.import_legacy_ini(LEGACY)["section"]["enabled"] is False


def test_garbage_yields_defaults_rather_than_raising():
    got = bookmarks.import_legacy_ini("not an ini at all\x00\x01")
    assert got["section"]["keybinds"] == bookmarks.DEFAULT_BINDS


def test_a_byte_order_mark_does_not_destroy_the_first_section():
    """The legacy script writes [Keybinds] first, so an unguarded parser
    loses every bind to a BOM -- silently, which is the whole failure this
    function exists to prevent."""
    got = bookmarks.import_legacy_ini("﻿" + KEYBINDS_FIRST)
    assert got["section"]["keybinds"]["GrabSig"] == "q"
    assert got["section"]["keybinds"]["FinH"] == "y"
    assert got["section"]["windows"] == {"EVE - Pilot": True}
    assert got["section"]["keybinds"]["Copy"] == "^c"


def test_a_byte_order_mark_does_not_suppress_a_setting():
    off = "﻿" + LEGACY.replace("HomeZeroIs0=1", "HomeZeroIs0=0")
    assert bookmarks.import_legacy_ini(off)["section"]["home_zero"] is False


def test_windows_the_engine_could_never_match_are_reported():
    """generate_ini drops these on the next write; a loss the user is never
    told about is exactly what this function exists to prevent."""
    got = bookmarks.import_legacy_ini(
        "[Enabled]\r\nNotepad=1\r\nEVE - Ok=1\r\n")
    assert got["section"]["windows"] == {"EVE - Ok": True}
    assert any("Notepad" in d for d in got["discarded"])


# --- Encoding -------------------------------------------------------------
#
# The shipped eve_bookmark_helper.ini is UTF-16 LE with a BOM, because that
# is what AutoHotkey's IniWrite produces on a Unicode build. Reading it as
# UTF-8 leaves a NUL after every character, so every section header fails
# _parse_ini's "]" test and the entire file imports as nothing -- which the
# caller then saved over the user's real settings while reporting success.
# These pin the decode, and the shape of the bug, so it cannot come back.

def _encoded(text, encoding):
    return text.encode(encoding)


def test_utf16_le_with_bom_is_the_real_world_case():
    raw = "﻿".encode("utf-16-le") + LEGACY.encode("utf-16-le")
    got = bookmarks.import_legacy_ini(bookmarks.decode_ini_bytes(raw))
    assert got["section"]["keybinds"]["GrabSig"] == "q"
    assert got["section"]["keybinds"]["Copy"] == "^c"
    assert got["section"]["windows"] == {"EVE - Pilot": True,
                                         "EVE - Alt": False}
    assert got["parsed"] is True


def test_utf16_be_with_bom():
    raw = "﻿".encode("utf-16-be") + LEGACY.encode("utf-16-be")
    got = bookmarks.import_legacy_ini(bookmarks.decode_ini_bytes(raw))
    assert got["section"]["keybinds"]["GrabSig"] == "q"


def test_utf8_with_and_without_a_bom():
    for raw in (LEGACY.encode("utf-8"),
                b"\xef\xbb\xbf" + LEGACY.encode("utf-8")):
        got = bookmarks.import_legacy_ini(bookmarks.decode_ini_bytes(raw))
        assert got["section"]["keybinds"]["GrabSig"] == "q"


def test_a_file_that_yields_no_sections_is_not_an_empty_config():
    """An undecodable file and a genuinely empty one are indistinguishable
    by their parsed contents, so the caller is told which it was. Saving
    this section would wipe the settings it was meant to preserve."""
    assert bookmarks.import_legacy_ini("")["parsed"] is False
    assert bookmarks.import_legacy_ini("not an ini")["parsed"] is False
    assert bookmarks.import_legacy_ini(LEGACY)["parsed"] is True
