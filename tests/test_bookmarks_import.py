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


def test_binds_that_still_exist_are_carried_over():
    got = bookmarks.import_legacy_ini(LEGACY)
    assert got["section"]["keybinds"]["GrabSig"] == "q"
    assert got["section"]["keybinds"]["FinH"] == "y"
    assert got["section"]["keybinds"]["ConvertScout"] == "^+s"


def test_window_enablement_is_carried_over():
    got = bookmarks.import_legacy_ini(LEGACY)
    assert got["section"]["windows"] == {"EVE - Pilot": True,
                                         "EVE - Alt": False}


def test_removed_binds_are_reported_not_silently_dropped():
    """A user who loses a working key should learn it here rather than by
    pressing it and getting nothing."""
    got = bookmarks.import_legacy_ini(LEGACY)
    assert "Copy" not in got["section"]["keybinds"]
    assert "Paste" not in got["section"]["keybinds"]
    assert any("Copy" in d for d in got["discarded"])
    assert any("Paste" in d for d in got["discarded"])


def test_removed_settings_are_reported():
    got = bookmarks.import_legacy_ini(LEGACY)
    joined = " ".join(got["discarded"])
    assert "Mode" in joined
    assert "PrefaceReturn" in joined
    assert "ReturnPreface" in joined


def test_home_numbering_change_is_described_in_user_terms():
    """HomeZeroIs0 is NOT Protean-specific: FireRootFinisher applies it with
    no reference to CurrentMode (111unified.ahk:870,886,893). A user who had
    it off gets renumbered bookmarks, so this cannot read as "no longer
    applies"."""
    off = LEGACY.replace("HomeZeroIs0=1", "HomeZeroIs0=0")
    got = bookmarks.import_legacy_ini(off)
    note = " ".join(got["notes"])
    assert ".0" in note and ".1" in note


def test_no_note_when_home_numbering_already_matched():
    got = bookmarks.import_legacy_ini(LEGACY)
    assert not any(".0" in n and ".1" in n for n in got["notes"])


def test_import_never_enables_the_engine():
    """Importing settings is not consent to start a keyboard hook."""
    assert bookmarks.import_legacy_ini(LEGACY)["section"]["enabled"] is False


def test_garbage_yields_defaults_rather_than_raising():
    got = bookmarks.import_legacy_ini("not an ini at all\x00\x01")
    assert got["section"]["keybinds"] == bookmarks.DEFAULT_BINDS


def test_a_byte_order_mark_does_not_destroy_the_first_section():
    """Notepad adds a BOM on save. It survives .strip(), so an unguarded
    parser fails the section-header test on the first line and skips that
    whole section -- and the legacy script writes [Keybinds] first, so the
    user would silently lose every bind."""
    got = bookmarks.import_legacy_ini("﻿" + LEGACY)
    assert got["section"]["keybinds"]["GrabSig"] == "q"
    assert got["section"]["keybinds"]["FinH"] == "y"


def test_a_byte_order_mark_does_not_suppress_the_numbering_note():
    off = "﻿" + LEGACY.replace("HomeZeroIs0=1", "HomeZeroIs0=0")
    note = " ".join(bookmarks.import_legacy_ini(off)["notes"])
    assert ".0" in note and ".1" in note


def test_windows_the_engine_could_never_match_are_reported():
    """generate_ini drops these on the next write; a loss the user is never
    told about is exactly what this function exists to prevent."""
    got = bookmarks.import_legacy_ini(
        "[Enabled]\r\nNotepad=1\r\nEVE - Ok=1\r\n")
    assert got["section"]["windows"] == {"EVE - Ok": True}
    assert any("Notepad" in d for d in got["discarded"])
