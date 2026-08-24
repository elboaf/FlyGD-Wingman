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
