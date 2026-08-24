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


def test_the_engine_reads_only_keybinds_and_enabled(source):
    """The re-vendored engine has no [Settings] at all.

    HomeZeroIs0, PrefaceReturn and ReturnPreface were restored during the
    fork and are gone again with it: the helper author's script never had
    them, and Wingman had frozen all three off, so the branches they gated
    could not fire. What matters now is the inverse of the old assertion --
    the engine must not grow a read of config Wingman no longer writes,
    because an IniRead default would then decide behaviour nobody chose.
    That is exactly how the compiled HomeZeroIs0 default came to renumber
    home bookmarks.
    """
    sections = set(re.findall(r"IniRead,\s*\w+\s*,\s*%IniFile%\s*,\s*(\w+)",
                              source, re.IGNORECASE))
    assert sections == {"Keybinds", "Enabled"}, sections


def test_home_hole_resumption_is_reachable(source):
    """The bug this file exists to prevent recurring.

    ZeroMode is the bulk-renumber state Set Root enters when every selected
    bookmark has a single-character prefix -- the home holes. The forked
    engine carried ZeroMode, CountValidBookmarkLines and AllPrefixesSingle
    as *dead code*: the variable was assigned False in six places and True
    in none, and neither helper was ever called. Set Root therefore read
    the character "1" as the root and restarted numbering at 1 instead of
    resuming past the used slots.

    Nothing caught it, because every assertion here was about the presence
    of names rather than about their being reachable. Hence this one.
    """
    assert re.search(r"ZeroMode\s*:=\s*True", source), \
        "ZeroMode is never entered -- home-hole resumption is dead code"
    for helper in ("CountValidBookmarkLines", "AllPrefixesSingle"):
        calls = re.findall(helper + r"\s*\(", source)
        definitions = re.findall(r"^" + helper + r"\s*\(", source,
                                 re.MULTILINE)
        assert len(calls) > len(definitions), \
            f"{helper} is defined but never called"


def test_copy_and_paste_are_gone(source):
    """Their handlers were Send ^c and Send ^v (111unified.ahk:988-995).
    Reinstating them spends a system-wide keyboard hook reproducing what
    Windows already does, which is why they were cut."""
    lowered = source.lower()
    assert "kb_copy" not in lowered
    assert "kb_paste" not in lowered
    assert not re.search(r"^DoCopy:", source, re.MULTILINE)
    assert not re.search(r"^DoPaste:", source, re.MULTILINE)


def test_tags_are_written_in_the_helper_authors_lowercase(source):
    """The tag letters land in the bookmark name itself, so a regression
    here is visible to everyone in the corp and fixable only by retagging
    by hand. Matched on the emitting lines rather than a bare substring:
    " C" also appears in the C1-C6 class finishers, which are a different
    code path and stay uppercase."""
    emits = re.findall(r'Result \.=\s*"\s*(\S+)"', source)
    assert "e" in emits and "E" not in emits
    assert "c" in emits and "C" not in emits
    assert "f" in emits and "S" not in emits
    assert "/" in emits
    assert "M" not in emits, "the medium-hole tag is gone"


def test_a_legacy_frig_tag_is_still_read(source):
    """S was the frig tag before the rework. Re-tagging a bookmark that
    still carries one must not leave both an S and an f on the line, so the
    parser has to keep recognising it. AHK's `=` is case-insensitive, so
    only S -- a different letter, not a different case -- needs this."""
    assert re.search(r'\(t = "f" \|\| t = "S"\)', source)


def test_the_medium_hole_tag_is_gone(source):
    """It was removed with the author's tag rework, along with the
    three-way exclusivity it needed against the frig tag."""
    lowered = source.lower()
    for name in ("kb_finm", "newm", "existingm", "finalm", "dom:"):
        assert name not in lowered, name


def test_every_bind_is_registered_inside_the_window_loop(source):
    """Nothing is global any more. RefreshHotkeys Step 4
    (111unified.ahk:763-771) kept three binds outside the per-window loop;
    Set Root was the last one left, and a hotkey that rewrites the
    clipboard and resets the root state must not fire in a browser.

    The loop is bounded by its own closing brace, so a RegisterBind outside
    it cannot match `body` -- which is exactly what this asserts.
    """
    loop = re.search(r"if\s*\(Val\s*=\s*\"1\"\)\s*\{[^}]*\}", source,
                     re.IGNORECASE | re.DOTALL)
    assert loop, "per-window registration loop not found"
    body = loop.group(0)
    calls = re.findall(r'RegisterBind\("(\w+)"', source)
    inside = re.findall(r'RegisterBind\("(\w+)"', body)
    assert calls, "no registrations at all"
    assert sorted(calls) == sorted(inside), \
        f"registered outside the window loop: {set(calls) - set(inside)}"
    assert "SetRoot" in inside
    assert "GrabSig" in inside


def test_set_root_is_scoped_by_registration_alone(source):
    """DoSemi's own window re-check is gone, deliberately.

    The fork carried an IsEveWindow guard inside the handler. It was kept
    for one narrow case: RefreshHotkeys runs on a 10s timer, so between a
    window being unticked and the refresh that tears its binds down, the
    bind is still live, and a press in that gap resets the root state in a
    window the user just disabled. The maintainer's call is to track the
    helper author's script exactly rather than carry the extra branch, so
    the per-window registration above is now the only thing scoping Set
    Root -- which makes test_every_bind_is_registered_inside_the_window_loop
    load-bearing for it, not merely tidy.

    Asserted positively so this cannot pass vacuously: Set Root must still
    be registered, and only inside the window loop.
    """
    loop = re.search(r"if\s*\(Val\s*=\s*\"1\"\)\s*\{[^}]*\}", source,
                     re.IGNORECASE | re.DOTALL)
    assert loop, "per-window registration loop not found"
    assert 'RegisterBind("SetRoot"' in loop.group(0)
    outside = source.replace(loop.group(0), "")
    assert 'RegisterBind("SetRoot"' not in outside
    assert "DoSemi" in source


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
