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


def test_restored_settings_are_read_from_the_ini(source):
    """Cut in the first port and restored. HomeZeroIs0 in particular must be
    READ, not hardcoded: the engine's compiled default is the opposite of
    Wingman's, so a dropped IniRead silently renumbers every home bookmark."""
    for name in ("HomeZeroIs0", "PrefaceReturn", "ReturnPreface"):
        assert re.search(r"IniRead,\s*" + name + r"\s*,", source,
                         re.IGNORECASE), name


def test_copy_and_paste_binds_are_read_and_handled(source):
    lowered = source.lower()
    assert "kb_copy" in lowered
    assert "kb_paste" in lowered
    assert re.search(r"^DoCopy:", source, re.MULTILINE)
    assert re.search(r"^DoPaste:", source, re.MULTILINE)


def test_the_three_global_binds_are_registered_outside_the_window_loop(source):
    """RefreshHotkeys Step 4 (111unified.ahk:763-771). The per-window loop
    is bounded by its own closing brace, so a global RegisterBind cannot be
    inside it -- and registering SetRoot in both places would make the
    second call fail and land in FailedBinds."""
    loop = re.search(r"if\s*\(Val\s*=\s*\"1\"\)\s*\{[^}]*\}", source,
                     re.IGNORECASE | re.DOTALL)
    assert loop, "per-window registration loop not found"
    body = loop.group(0)
    for bid in ("Copy", "Paste", "SetRoot"):
        assert re.search(r'RegisterBind\("' + bid + r'"', source), bid
        assert not re.search(r'RegisterBind\("' + bid + r'"', body), \
            f"{bid} is registered per-window as well as globally"
    # And the eighteen window-scoped ones must still be in there.
    assert re.search(r'RegisterBind\("GrabSig"', body)


def test_set_root_rechecks_the_active_window(source):
    """It is registered globally, so it can fire anywhere. Without the
    guard, a press inside another application runs the whole copy/parse
    flow there -- Send ^c into a chat window and the root state reset."""
    body = source.split("DoSemi:", 1)[1][:1200]
    assert "IsEveWindow" in body
    assert re.search(r"WinGetTitle\s*,\s*ActiveTitle\s*,\s*A", body,
                     re.IGNORECASE)
    assert re.search(r"if\s*\(!IsEveWindow\)", body)


def test_root_mode_is_published(lowered):
    """The UI must not have to infer it from root == "(home)"."""
    assert "root_mode" in lowered


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


def test_settings_used_inside_functions_are_declared_global(source):
    """AHK v1 makes an undeclared name inside a function LOCAL. HomeZeroIs0
    is read in FireRootFinisher, so without the declaration it reads as
    empty, the home branch never fires, and the setting silently does
    nothing -- a failure with no error and no log line.

    Only settings read inside a function need this. The return-preface pair
    is used from DoSemi and SetManualRoot, which are labels running in
    global scope, so they are deliberately not checked here.
    """
    body = re.search(r"FireRootFinisher\([^)]*\)\s*\{(.*?)\n\}",
                     source, re.DOTALL)
    assert body, "FireRootFinisher not found"
    text = body.group(1)
    if "HomeZeroIs0" in text:
        declarations = re.findall(r"^\s*global\s+([^\n;]+)", text,
                                  re.MULTILINE)
        declared = {name.strip()
                    for line in declarations for name in line.split(",")}
        assert "HomeZeroIs0" in declared, \
            "FireRootFinisher reads HomeZeroIs0 without declaring it global"
