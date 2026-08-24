# Reference material

## `111unified.ahk`

The standalone AutoHotkey script the EVE bookmark feature was ported from.
It is kept verbatim, and is **not** built, shipped, or executed — the
vendored engine at `obs_youtube_uploader/engine/eve_bookmarks.ahk` replaces
it.

It stays in the tree because roughly a dozen comments and tests cite it by
line number to record *why* the port behaves as it does — which finisher
names it produced, which hotkeys it registered globally, which bug it
carried. Those citations use the bare filename (`111unified.ahk:71`), so
they remain accurate from here.

Do not edit it. If the port needs to diverge, change the engine and update
the citing comment.

## `author-cleanup.ahk`

The helper author's own later revision, supplied by them as the version
that matches how the corp actually works. **This, not `111unified.ahk`, is
what the shipped engine is now vendored from.**

The two differ more than their shared lineage suggests. `111unified.ahk`
carries `ZeroMode`, `CountValidBookmarkLines` and `AllPrefixesSingle` as
dead code — the variable is assigned `False` in six places and `True` in
none, and neither helper is ever called. `author-cleanup.ahk` wires all
three up, which is what makes Set Root resume numbering past the used
slots when every selected bookmark has a single-character prefix (the home
holes). The port inherited the dead version, so that resumption silently
did nothing; see `test_home_hole_resumption_is_reachable`.

It is kept verbatim and is not built, shipped, or executed. Note it is a
*partially* stripped script: the GUI is gone, but `SaveAllSettings` and
`SaveWindowSettings` remain and still call `GuiControlGet`, so both are
broken where they stand. The vendored engine drops them, along with the 20
`IniWrite` calls — Wingman owns the INI.

When the author ships a new revision, replace this file and re-apply the
integration layer marked `WINGMAN` in the engine, rather than porting
changes across by hand. Hand-porting is how the last divergence happened.
