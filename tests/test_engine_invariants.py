# tests/test_engine_invariants.py
"""The engine cannot be exercised by pytest, so these are the only
automated checks on it. Modelled on test_no_tk.py, which exists for exactly
this reason: to stop something that was removed on purpose creeping back.
"""
import re
import pytest
from obs_youtube_uploader import paths


def _code(source: str) -> str:
    """The script with full-line comments removed.

    These assertions are about live code, not about whether a string appears
    anywhere in the file. The engine deliberately names HomeZeroIs0 and
    CurrentMode in a comment explaining why home numbering is now fixed --
    that comment is the reason a future reader will find the removal at all,
    and it must not be what fails this test.

    The mirror case matters just as much: a presence assertion searching the
    whole text could be satisfied by a comment describing a teardown loop
    that someone had deleted.

    Only whole-line comments are stripped. A trailing comment on a code line
    would still be searched; if that ever produces a false failure, move the
    comment onto its own line rather than weakening the assertion.
    """
    return "\n".join(line for line in source.splitlines()
                     if not line.strip().startswith(";"))


@pytest.fixture
def source():
    script = paths.engine_script()
    assert script is not None, "vendored engine script is missing"
    return _code(script.read_text(encoding="utf-8", errors="replace"))


def test_no_gui(source):
    """The GUI is Wingman's job now. A returning Gui command means a second
    config surface, and with it the two-writer problem the design removed."""
    assert not re.search(r"^\s*Gui[,\s]", source, re.MULTILINE)
    assert not re.search(r"^\s*GuiControl", source, re.MULTILINE)


def test_engine_never_writes_config(source):
    """settings.json is the single source of truth and the INI is derived
    from it. An IniWrite here would make the engine a second writer."""
    assert "IniWrite" not in source


def test_no_tray_menu(source):
    assert not re.search(r"^\s*Menu,\s*Tray", source, re.MULTILINE)


def test_single_instance_is_pinned(source):
    """Unparameterised #SingleInstance prompts, and there is no GUI left to
    answer the prompt in."""
    assert "#SingleInstance Force" in source


def test_protean_mode_is_gone(source):
    assert "CurrentMode" not in source
    assert "FormatProteanClipAndPaste" not in source


def test_removed_settings_are_gone(source):
    for name in ("HomeZeroIs0", "PrefaceReturn", "ReturnPreface"):
        assert name not in source


def test_copy_and_paste_binds_are_gone(source):
    assert "KB_Copy" not in source
    assert "KB_Paste" not in source


def test_every_registration_records_failures(source):
    """Registration must go through RegisterBind, which checks ErrorLevel.
    A bare Hotkey ... On UseErrorLevel would swallow the failure again."""
    bare = re.findall(r"Hotkey,\s*%KB_\w+%.*On\s+UseErrorLevel", source)
    assert bare == []
    assert "RegisterBind(" in source


def test_window_scoped_teardown_exists(source):
    """The teardown bug: variants registered under IfWinActive <title> can
    only be disabled from inside that criterion."""
    assert "RegisteredWindows" in source


def test_status_is_published_atomically(source):
    assert "eve_status.json.tmp" in source
    assert re.search(r"FileMove,\s*eve_status\.json\.tmp,\s*eve_status\.json,\s*1",
                     source)
