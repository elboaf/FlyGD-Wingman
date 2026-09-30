# FlyGD Wingman

A tray-resident Windows desktop app for EVE Online multiboxing: bookmark
keybinds, live client previews, and integrations with external tools.

## Language

### Bookmarks

**Set Root**:
A bookmark keybind that establishes the root system for subsequent bookmark
numbering; on a single selected bookmark it also captures a pre-jump prime
and (unchanged from before) places the root value on the clipboard.
_Avoid_: root mode, DoSemi (that's the engine handler's name)

**RootKey**:
The J-code system identifier extracted by Set Root from the selected
bookmark's text. It is the clipboard value and the name field of a prime.
_Avoid_: root value, root system name

**Position code**:
The hardware identity of a key (`event.code`, e.g. `KeyG`): where the key
sits on a reference board, not what it types. Never stored; capture input
only.
_Avoid_: keycode, scan code

**Produced character**:
The character the user's active OS layout generates for a key; what capture
resolves a position code into before storing a keybind. Press = label = key
that fires.
_Avoid_: layout key, resolved key

**Finisher tag**:
One of the four flag characters appended to a bookmark name by the finisher
keybinds: `e` (end of life), `/` (half mass), `c` (critical mass), `f`
(frigate hole).
_Avoid_: flag char, suffix

### Pre-jump prime (issue #281)

**Prime** (pre-jump record):
A bounded record captured at Set Root time — root J-code, parsed finisher
tags, EVE character ID, expected source solar system, map binding, event ID,
expiry — staged on Wanderer and consumed at most once. Not a bookmark, not a
clipboard value. The `e` tag maps to Wanderer's 4-hour EOL bucket
(`time_status` 2), not the 1-hour bucket.
_Avoid_: pre-jump flag, cached bookmark

**Staging**:
Pushing a prime to Wanderer's narrow write endpoint, where it waits to be
matched against a tracked character's location update. A staged prime is not
applied and not confirmed consumed.
_Avoid_: upload, write-through

**Consume**:
The server-side, at-most-once application of a staged prime to a newly
created connection (and a new destination system's name) during the matching
character's location update. Consumed only on a new connection; a stale prime
expires without side effects.
_Avoid_: clear, apply, spend

**Source match**:
The consume-time requirement that character, map, and expected source solar
system all match the tracked movement; the guard that keeps a stale prime
from populating the wrong system.
_Avoid_: jump match, validation

### Region crops (issue #272)

**Crop**:
An additional floating mirror of a bounded region of one character's client,
kept live above other windows. Distinct from that character's main preview,
which mirrors the whole client.
_Avoid_: secondary preview, additional region preview, overlay

**Crop owner**:
The character whose client a crop mirrors; the identity a crop is managed
by. The exact character name, never a window handle.
_Avoid_: source character, crop character

**Crop id**:
The stable identity distinguishing one of an owner's crops from their
others; assigned at creation, persisted, never reused or renumbered after a
delete. Its creation sequence is also the crop's stable order for display
("Crop 1") and for global-cap tiebreaks.
_Avoid_: crop index, crop slot, crop name

**Crop definition**:
The persisted record of one crop: source region fractions, floating window
geometry, enabled flag. Versioned; malformed entries are dropped
individually, never poisoning siblings.
_Avoid_: crop settings

**Live crop**:
An enabled crop whose owner currently has a named session and holds one of
the cap's slots. Live is runtime state; it never changes what is saved.
_Avoid_: active crop, running crop

**Cap**:
The fixed maximum number of simultaneously live crops across all characters
(32). A separate, smaller per-character limit bounds how many crops one
owner may define.
_Avoid_: crop limit, MAX_LIVE_CROPS

**Per-character limit**:
The maximum number of crop definitions one owner may have (4), whether
enabled or not.
_Avoid_: crop cap

**Toggle-all**:
The main-preview right-click gesture over one owner's crops: if any is
enabled, all become disabled; if none is, all become enabled.
_Avoid_: hide crops, crop toggle

**Hide-active**:
The runtime visibility rule that hides the foreground character's preview
windows (main and crops) without changing any saved enabled flag.
_Avoid_: toggle-all (that flips saved state), auto-hide

**Master preview switch**:
The setting that disables all previews and crops together, regardless of
individual crop enabled flags.
_Avoid_: preview enabled, global toggle

**Region select**:
The native drag-out overlay that captures the source region for a crop; used
identically for first selection and reselection, and reselection never
disturbs the crop's enabled flag.
_Avoid_: crop picker, screenshot region
