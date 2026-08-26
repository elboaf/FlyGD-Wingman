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

from wingman import paths


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
    return "\n".join(
        line for line in source.splitlines() if not line.strip().startswith(";")
    )


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
    sections = set(
        re.findall(r"IniRead,\s*\w+\s*,\s*%IniFile%\s*,\s*(\w+)", source, re.IGNORECASE)
    )
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
    assert re.search(r"ZeroMode\s*:=\s*True", source), (
        "ZeroMode is never entered -- home-hole resumption is dead code"
    )
    # Anchored on DoSemi's body rather than on a bare call count. Comparing
    # calls against definitions matched at column 0 would silently start
    # passing if a future revision ever indented a definition: definitions
    # drops to 0, calls stays 1, and 1 > 0 holds for code that is still
    # dead -- reintroducing exactly the bug this test exists to catch.
    body = re.search(r"^DoSemi:\n(.*?)^Return$", source, re.DOTALL | re.MULTILINE)
    assert body, "DoSemi not found"
    for helper in ("CountValidBookmarkLines", "AllPrefixesSingle"):
        assert re.search(helper + r"\s*\(", body.group(1)), (
            f"{helper} is not called from DoSemi -- it is dead code"
        )


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
    loop = re.search(
        r"if\s*\(Val\s*=\s*\"1\"\)\s*\{[^}]*\}", source, re.IGNORECASE | re.DOTALL
    )
    assert loop, "per-window registration loop not found"
    body = loop.group(0)
    calls = re.findall(r'RegisterBind\("(\w+)"', source)
    inside = re.findall(r'RegisterBind\("(\w+)"', body)
    assert calls, "no registrations at all"
    assert sorted(calls) == sorted(inside), (
        f"registered outside the window loop: {set(calls) - set(inside)}"
    )
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
    loop = re.search(
        r"if\s*\(Val\s*=\s*\"1\"\)\s*\{[^}]*\}", source, re.IGNORECASE | re.DOTALL
    )
    assert loop, "per-window registration loop not found"
    assert 'RegisterBind("SetRoot"' in loop.group(0)
    outside = source.replace(loop.group(0), "")
    assert 'RegisterBind("SetRoot"' not in outside
    # The removal itself, asserted rather than merely described above. The
    # guard's name is the whole of it: IsEveWindow appears nowhere else in
    # the engine, so its return would be caught here.
    assert "IsEveWindow" not in source, (
        "DoSemi's window guard is back -- it was dropped to track the "
        "author's script; re-adding it is a divergence, not a fix"
    )


def test_nothing_sends_the_engine_commands(source, lowered):
    """Wingman configures the engine through the INI and reads its state
    from the status file. There is no channel in the other direction.

    There used to be: eve_command.ini, ReadCommand, SetManualRoot and
    ClearRoot existed so two buttons on the Bookmarks route could set and
    clear the root. Both did a weaker job than the hotkey already does --
    no selection means no used-slot information, so numbering always
    restarted -- and neither appears in the author's documented workflow
    (docs/bookmarks_reference.md). The buttons went, and the channel with
    them, taking one silent failure along: ReadCommand advanced its
    sequence before dispatching, so a malformed command file made the
    button report success while doing nothing.

    Asserted rather than merely deleted because the cost of that channel
    was never obvious from any one file. Re-adding it should be a decision
    someone makes on purpose, in front of this test.
    """
    assert "eve_command" not in lowered
    assert "consumedseq" not in lowered
    for label in ("ReadCommand", "SetManualRoot", "ClearRoot"):
        assert not re.search(r"^" + label + r":", source, re.MULTILINE), label
    # The status file is the whole of the engine -> Wingman contract. AHK
    # escapes a quote by doubling it, so a field reads """name"": in source.
    published = set(re.findall(r'"""(\w+)"":', source))
    assert published == {
        "sig",
        "root",
        "next_num",
        "next_alpha",
        "failed_binds",
        "written",
    }, published


def test_every_registration_records_failures(source):
    """Registration must go through RegisterBind, which checks ErrorLevel.
    Any Hotkey line dereferencing a KB_ variable directly has bypassed it --
    whether or not it also passes UseErrorLevel, since omitting that swallows
    the failure just as silently."""
    direct = re.findall(
        r"^\s*Hotkey\s*,[^\n]*%KB_\w+%", source, re.MULTILINE | re.IGNORECASE
    )
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
        source,
        re.IGNORECASE,
    )


def test_status_is_published_atomically(lowered):
    assert "eve_status.json.tmp" in lowered
    assert re.search(
        r"filemove,\s*eve_status\.json\.tmp,\s*eve_status\.json,\s*1", lowered
    )


def test_globals_written_inside_functions_are_declared(source):
    """AHK v1 makes an undeclared name inside a function LOCAL.

    This used to guard HomeZeroIs0 in FireRootFinisher. HomeZeroIs0 is gone
    with the re-vendor, which left the test green and guarding nothing --
    its whole body sat behind `if "HomeZeroIs0" in text:`. The trap it was
    written for is still live, and now has a sharper instance: RegisterBind
    *writes* FailedBinds, so without the declaration every registration
    failure accumulates into a local that is discarded when the function
    returns, the status file reports an empty failed_binds, and the UI says
    every hotkey registered fine. That is a wrong answer, not a missing one.

    Checked for every function that touches a script-level global rather
    than for one name, so the next function to reach for one is covered
    without anybody remembering to come back here.
    """
    watched = {
        "FailedBinds",
        "UsedNums",
        "UsedAlphas",
        "NextNum",
        "NextAlpha",
        "RootKey",
        "RootModeActive",
        "ZeroMode",
        "LastSigId",
        "ConsumedSeq",
        "ReadyToIncrement",
    }
    functions = re.findall(
        r"^([A-Za-z_]\w*)\s*\([^)]*\)\s*\{(.*?)^\}", source, re.DOTALL | re.MULTILINE
    )
    # `if (...) {` at column 0 matches the same shape as a definition.
    keywords = {"if", "while", "for", "loop", "else", "return"}
    functions = [(n, b) for n, b in functions if n.lower() not in keywords]
    assert functions, "no functions found"
    checked = 0
    for name, body in functions:
        declarations = re.findall(r"^\s*global\s+([^\n;]+)", body, re.MULTILINE)
        declared = {n.strip() for line in declarations for n in line.split(",")}
        for global_name in watched:
            if not re.search(r"\b" + global_name + r"\b", body):
                continue
            checked += 1
            assert global_name in declared, (
                f"{name}() touches {global_name} without declaring it "
                f"global -- in AHK v1 that is a local, and the write is lost"
            )
    # Guards against the whole loop quietly matching nothing, which is
    # exactly how the previous version of this test died.
    assert checked, "no function touched a watched global -- test is vacuous"


def _label_body(source, label):
    match = re.search(
        r"^" + label + r":\n(.*?)^Return$", source, re.DOTALL | re.MULTILINE
    )
    assert match, f"{label} not found"
    return match.group(1)


# Every handler that copies a selection out of EVE in order to read it.
_CLIPBOARD_READERS = ("DoQ", "DoSemi", "DoConvertScout", "ReadField")


def test_no_clipboard_read_can_pick_up_stale_data(source):
    """A handler must clear the clipboard before its own `Send ^c`.

    Without the clear, a copy that does not land -- focus not where the user
    thought, EVE dropping the synthetic keystroke, another process holding
    the clipboard lock -- leaves the PREVIOUS contents in place. `ClipWait`
    then returns immediately and successfully, because the clipboard is not
    empty, so there is not even the two-second stall that would hint at
    trouble, and the handler reads whatever was already there.

    That was live in DoQ, and it was the worst instance available: DoSemi
    ends with `Clipboard := RootKey`, so straight after a Set Root the
    clipboard holds the root. A failed Grab Sig took its first three
    characters as the signature -- root J214811 becoming sig "-J21" -- and
    FireRootFinisher then baked that into real bookmarks, with the status
    bar showing it like any ordinary signature. A confident wrong answer
    with no tell anywhere.

    Clearing first converts every one of those failures into an empty read,
    which each handler already treats as "nothing was selected".
    """
    for label in _CLIPBOARD_READERS:
        body = _label_body(source, label)
        assert "Send ^c" in body, label
        before = body[: body.index("Send ^c")]
        assert re.search(r"Clipboard\s*:=\s*\"\"", before), (
            f"{label} sends ^c without first clearing the clipboard, so a "
            f"failed copy silently reads whatever was already there"
        )


def test_grab_sig_reports_a_failed_copy(source):
    """DoQ must check ClipWait's ErrorLevel, not just read what it finds.

    Clearing the clipboard (above) turns a failed copy into an empty read,
    which stops the wrong-signature bug -- but on its own it would make a
    failed Grab Sig indistinguishable from a successful one, since the next
    finisher would simply paste a bookmark with no sig at all and say
    nothing about why.

    Checked here and not for the other readers because DoQ is the one whose
    result is carried forward into later actions. DoSemi's failure is
    visible in the tooltip and the status bar, and ReadField's is a paste
    that does nothing; the author's script leaves both unchecked and this
    does not change that. DoConvertScout already reports its own.
    """
    body = _label_body(source, "DoQ")
    assert re.search(r"if\s*\(ErrorLevel\)", body), (
        "DoQ ignores ClipWait's ErrorLevel, so a failed copy is silent"
    )
    assert "ToolTip" in body, "DoQ has no way to tell the user the copy failed"
