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
