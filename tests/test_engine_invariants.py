# tests/test_engine_invariants.py
"""The engine cannot be exercised by pytest, so these are the only
automated checks on it. Modelled on test_no_tk.py, which exists for exactly
this reason: to stop something that was removed on purpose creeping back.

What this cannot catch, recorded so a green run is not mistaken for "the
engine is verified":

- A configuration surface returning by another route -- InputBox, MsgBox,
  Progress, or a native window via DllCall("CreateWindowEx", ...).
- Config-writing returning via FileAppend or FileOpen against the INI path,
  or DllCall("WritePrivateProfileString", ...), none of which contain the
  word IniWrite.
- A dual-scheme naming mode reintroduced under a different variable name.
  This is purely lexical; only the old spelling is watched.
- AutoHotkey block comments. _code() strips whole-line ; comments only;
  there are no /* */ blocks in the file today.

The manual smoke checklist is the backstop for all of these.
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


@pytest.fixture
def lowered(source):
    """For substring assertions. AHK commands are case-insensitive, so a
    lowercase `iniwrite` would otherwise evade a case-sensitive check."""
    return source.lower()


def test_no_gui(source):
    """The GUI is Wingman's job now. A returning Gui command means a second
    config surface, and with it the two-writer problem the design removed."""
    assert not re.search(r"^\s*Gui[,\s]", source, re.MULTILINE | re.IGNORECASE)
    assert not re.search(r"^\s*GuiControl", source, re.MULTILINE | re.IGNORECASE)


def test_engine_never_writes_config(lowered):
    """settings.json is the single source of truth and the INI is derived
    from it. An IniWrite here would make the engine a second writer."""
    assert "iniwrite" not in lowered


def test_no_tray_menu(source):
    assert not re.search(r"^\s*Menu,\s*Tray", source, re.MULTILINE | re.IGNORECASE)


def test_single_instance_is_pinned(lowered):
    """Unparameterised #SingleInstance prompts, and there is no GUI left to
    answer the prompt in."""
    assert "#singleinstance force" in lowered


def test_protean_mode_is_gone(lowered):
    assert "currentmode" not in lowered
    assert "formatproteanclipandpaste" not in lowered


def test_removed_settings_are_gone(lowered):
    for name in ("homezeroIs0", "PrefaceReturn", "ReturnPreface"):
        assert name.lower() not in lowered, name


def test_copy_and_paste_binds_are_gone(lowered):
    assert "kb_copy" not in lowered
    assert "kb_paste" not in lowered


def test_every_registration_records_failures(source):
    """Registration must go through RegisterBind, which checks ErrorLevel.
    Any Hotkey line dereferencing a KB_ variable directly has bypassed it --
    whether or not it also passes UseErrorLevel, since omitting that swallows
    the failure just as silently."""
    direct = re.findall(r"^\s*Hotkey\s*,[^\n]*%KB_\w+%", source,
                         re.MULTILINE | re.IGNORECASE)
    assert direct == [], f"registration bypassing RegisterBind: {direct}"
    assert re.search(r"RegisterBind\s*\(", source, re.IGNORECASE)


def test_window_scoped_teardown_exists(source):
    """The teardown bug: variants registered under IfWinActive <title> can
    only be disabled from inside that criterion. Asserting merely that
    "RegisteredWindows" appears somewhere is not enough -- the name occurs in
    the declaration and the push too, so the loop body could be gutted while
    the string survives and this test stayed green."""
    assert re.search(r"RegisteredWindows", source, re.IGNORECASE)
    # One regex spanning the loop header through its body, rather than two
    # independent searches: the earlier version passed as long as
    # "Hotkey, IfWinActive, %var%" appeared ANYWHERE in the file, even
    # outside this loop. `[^}]*` stops the match at the loop's own closing
    # brace, so the Hotkey line must actually be inside it.
    assert re.search(
        r"For\s+\w+\s*,\s*\w+\s+in\s+RegisteredWindows\s*\{[^}]*"
        r"Hotkey\s*,\s*IfWinActive\s*,\s*%\w+%",
        source, re.IGNORECASE)


def test_status_is_published_atomically(lowered):
    assert "eve_status.json.tmp" in lowered
    assert re.search(r"filemove,\s*eve_status\.json\.tmp,\s*eve_status\.json,\s*1",
                      lowered)
