# Integrating the EVE bookmark helper into FlyGD Wingman — design

Status: approved in brainstorming, not yet planned or implemented.
Date: 2026-08-22

## Intended outcome

Wingman gains a second feature area: the EVE wormhole bookmark hotkey helper
currently distributed as a standalone AutoHotkey script (`111unified.ahk`,
1981 lines). Wingman becomes the way that tool is run, and the standalone
script is retired.

The user-visible result is a `Bookmarks` destination in the window holding
configuration — 19 keybinds and per-EVE-window enablement — and a live status
readout in the window's existing global status bar, backed by a supervised
background process providing the hotkey behaviour for the naming scheme the
corp actually uses.

This is a deliberate widening of the product from "OBS recording companion"
to "general EVE assistant", confirmed with the maintainer.

### Scope reductions taken on maintainer feedback

> **Superseded.** Most of the cuts below were reverted; see
> `eve-bookmarks-fidelity-plan.md`. The intent is exact AHK behaviour behind
> Wingman's GUI, and three of these reductions rested on readings of the
> script that the code does not support. They are kept here, struck through,
> because the reasoning that was *wrong* is the part worth not repeating.

The absorbed feature is narrower than the standalone script in exactly one
respect:

- **Protean/v21 mode is dropped.** The engine supports one naming scheme
  (Flygd/ABH). Every `CurrentMode = 1` branch is removed from the vendored
  script, which is a substantial deletion — the mode is threaded through the
  finishers, the parser, and the status text. **This one stands.**

Reverted, with what the original reasoning got wrong:

- ~~**The `HomeZeroIs0` option is dropped**, its behaviour hardcoded to the
  shipped default.~~ **Restored as a setting.** The analysis here was right
  that it is not Protean-specific; the mistake was concluding that a
  hardcoded value was therefore safe. It is not: the compiled default is `.0`
  and Wingman's is now `.1`, so hardcoding either one renumbers somebody.
  Note for anyone touching this — `FireRootFinisher` is a *function*, and an
  undeclared name is local in AHK v1, so the `global HomeZeroIs0` declaration
  is load-bearing: without it the setting silently reads as empty.
- ~~**`PrefaceReturn` and `ReturnPreface` are dropped.** The corp does not
  use a return preface character.~~ **Restored.** The premise was false in
  two ways: it ships *enabled* (`IniRead ..., PrefaceReturn, 1`, `:116`) with
  preface `!`, so everyone on defaults uses it; and it is consumed at `:607`
  and `:1162` with no reference to `CurrentMode`, so grouping it with the
  Protean removal was a misreading. One maintainer having it off is not the
  corp not using it.
- ~~**The Copy and Paste binds are dropped.** Personal Dvorak conveniences.~~
  **Restored.** The handlers are two lines each (`:988-995`). The real
  content of this cut was never the handlers but their *scope* — see below.
- ~~**Set Root becomes window-scoped like everything else.** Its global
  registration existed solely so that, outside an enabled EVE window, it
  could paste a raw root number with the preface stripped — a Protean
  dual-use that disappears with Protean mode.~~ **Restored to global.** The
  out-of-window branch is `Send %RootKey%` guarded only by the window check
  (`:1024-1043`); it never consults `CurrentMode`. It types the current root
  into whatever application is focused, which is a live part of the workflow
  (set root in EVE, paste it into Discord or Pathfinder).

The consequence worth stating plainly, corrected: **three of the 21 binds are
registered globally** — Copy, Paste and Set Root, exactly as `RefreshHotkeys`
Step 4 does (`:763-771`). They fire in every application. That is a real risk
— a bind shadowing a shortcut elsewhere — accepted deliberately for fidelity,
and mitigated by making the scope visible per row in the UI, which the
standalone GUI never did. `DoSemi` re-checks the active window itself, so a
global press outside EVE cannot run the copy/parse flow in the wrong place.

## Repository evidence that shaped this

- `web/app.js:88-104` already implements routing (`WM.route`) over a map of
  `{main, settings, firstrun}`, toggling `.active` on `.route` elements.
  A fourth feature area follows a decision already made twice
  (`webview-replatform-design.md:189, :244`).
- `web/app.js:53` fixes bridge handler names in a registry that throws on an
  unregistered name. Python pushes semantic events; the page calls Python
  only through `WM.send()`.
- `settings.py:31` warns that `save()` projects onto `DEFAULTS` keys, so any
  undeclared key is dropped on every write. Validation is hand-written per
  key in `load()`.
- `stitch.py:87` and `library.py:152` take `runner=subprocess.run` as an
  injected parameter; `stitch.py:27` and `library.py:19` apply
  `CREATE_NO_WINDOW` on win32 only. This is the house pattern for testable
  subprocess code.
- `window-resize-plan.md:130-140` establishes how Windows-only code lives
  here: native work behind an entry point that is "a no-op returning False
  off Windows", so the module imports cleanly on Linux and stays testable
  (`tests/test_chrome.py`).
- `uploader.spec:19-33` records that PyInstaller exits 0 when `datas` fail to
  collect, which is why `build.yml` and `release.yml` carry post-build
  assertions for `web/`.
- `build.yml:155-177` refuses to ship a WebView2 bootstrapper not signed by
  Microsoft.
- `paths.py` provides `state_dir()` for writable state and `bundle_dir()` /
  `resolve_binary()` for bundled binaries, with non-Windows fallbacks so
  tests run off-platform.
- `webview-replatform-design.md:545` puts "Playwright or any browser test
  toolchain" out of scope, so JavaScript cannot be tested in this repo.

## Decision

Bundle a stripped AutoHotkey engine and configure it natively, with the
integration seam designed so the engine can later be replaced by a native
Python implementation without touching the UI or the config model.

Rejected alternatives:

- **Full Python port now.** The naming state machine (two conventions, root
  tracking, numeric/alpha slot allocation, sixteen finishers with tag flags)
  is the valuable part and is relied on mid-fight. A big-bang
  reimplementation risks subtly wrong bookmark names rather than visible
  crashes. It remains the plausible destination, not the first step.
- **Bundling the script unmodified.** Its GUI writes config, which would
  create a second writer competing with Wingman over the same file.
- **Shipping it as a separate download.** No product benefit; rejected with
  the "general EVE assistant" direction.

## Architecture

### Config, commands and status: three files, one writer each

```
settings.json ──generate_ini()──▶ eve_bookmark_helper.ini ──read──▶ engine
   ▲ Wingman writes                   Wingman writes                  │
   │                                                                  │
   │              eve_command.json ──────────read───────────────────▶ │
   │               Wingman writes                                     │ writes
   └────── bridge push ◀── Wingman reads ◀── eve_status.json ◀────────┘
```

`settings.json` is the single source of truth. The INI is a derived artifact,
regenerated on every save, never hand-edited. The engine reads config and
commands, and writes only its own runtime state. **No file has two writers.**

All four live in `paths.state_dir()`. The engine is spawned with
`cwd=state_dir()`, which makes the script's relative `IniFile` (`:71`)
resolve there with no edit to the script.

### The command channel

Set Root and Clear Root are operations rather than settings, so they cannot
travel through the config file. Wingman writes `eve_command.json` holding a
command and a sequence number; the engine reads it on its existing 2s timer
(`:77`), executes anything newer than the last sequence it ran, and records
that sequence in `eve_status.json`.

The sequence number preserves the single-writer rule: the engine never deletes
or rewrites the command file to mark it consumed, it just reports how far it
has got, and Wingman can see the command land.

Three things this needs to be correct rather than merely plausible:

**Every cross-process file is published atomically.** One writer per file
prevents *conflicting* writes; it does nothing about a reader observing a
half-written file. All four files are written to a temporary name on the same
volume and then renamed over the target — `os.replace` on the Python side,
`FileMove` with overwrite on the AHK side. Without this a 2s poll can read
truncated JSON, and the INI is equally exposed since the engine re-reads it
every 10s while Wingman may be rewriting it.

**The sequence is durable and monotonic across restarts.** It is persisted
with the rest of the state, not held in memory. If Wingman restarted and
resumed from zero while a command file with a higher sequence remained on
disk, commands would either be silently ignored or re-executed depending on
which side reset first. On engine start, the last-consumed sequence is
initialised from the command file currently on disk rather than from zero, so
a stale command left by a previous session is never replayed.

**An unconsumed command is never overwritten.** The slot holds one command,
and the poll interval is up to two seconds, so a second action taken quickly
would destroy the first. Wingman does not write a new command while the status
file shows the previous sequence unconsumed: the buttons disable until the
engine acknowledges, and surface an error if no acknowledgement arrives within
a few poll intervals. That doubles as the user-visible signal that the engine
has stopped responding.

This is the one piece of genuinely new machinery in the design. It reuses the
existing timer and carries only two commands, so it stays small — but it is a
third channel, and adding more commands to it later should be a deliberate
decision rather than a habit.

### Modules

- **`bookmarks.py`** — pure. Settings validation, INI generation, keybind
  notation mapping, collision detection. No I/O, no platform code.
- **`hotkeys.py`** — the supervisor. Spawn, stop, liveness, status reading.
  AutoHotkey appears nowhere in its public signatures; that is the seam
  that keeps a future port a swap rather than a rewrite.

```python
class HotkeyEngine:
    def __init__(self, exe, script, state_dir, spawner=subprocess.Popen)
    def apply(self, settings: dict) -> None
    def start(self) -> bool
    def stop(self, timeout: float = 5.0) -> None
    def is_running(self) -> bool
    def status(self) -> EngineStatus
```

## Data model

One nested key added to `settings.DEFAULTS`:

```python
"eve_bookmarks": {
    "enabled": False,
    "keybinds": {...},         # 19 entries, AHK notation, "" = unbound
    "windows": {...},          # "EVE - Character Name" -> bool
}
```

The mode and preface settings the standalone script carried are gone with the
scope reductions above, so the schema is only an enable switch, the binds, and
the window list.

`load()` gains a nested validation pass. It must be defensive: these values
are written into a file that drives global keyboard hooks, so a corrupt entry
falls back to its default and is logged rather than propagated.

**Nesting breaks an assumption the current loader makes.** `load()` starts
with `data = dict(DEFAULTS)` (`settings.py:38`), a shallow copy — fine while
every default is a scalar, wrong the moment one is a dict. As written, the
returned settings would share the `keybinds` and `windows` objects with the
module-level `DEFAULTS`, so the first in-place edit would corrupt the defaults
for the rest of the process, and every later `load()` would return the
mutated values. The nested branch must build fresh dicts (or deep-copy)
before validating or mutating. This is a quiet, process-lifetime failure
rather than a crash, so it needs a test that loads, mutates, and reloads.

Two defaults are deliberate:

- **`enabled` defaults to False.** Upgrading users do not silently acquire a
  global keyboard hook; they opt in.
- **Keybinds match what the script ships.** Eighteen of the nineteen are
  blank (`:120-140`), so there are no surprise collisions on first run — but
  `ConvertScout` ships bound to `^+s` (`:57`, `:140`) and must keep that
  default. Defaulting every bind to blank would silently take a working
  binding away from every existing user.

### Migrating an existing installation

Users already running the standalone script have an
`eve_bookmark_helper.ini` holding their modes, binds and per-window
enablement (`:71`, `:114-140`, `:143-190`). Retiring the script without
importing that file discards their configuration, and since this design's
whole premise is that Wingman *replaces* the script, that would hit every
current user rather than an edge case.

The script writes its INI relative to its working directory, so its location
is not knowable in general — there is no reliable path to probe. The route
therefore offers an explicit **"Import from an existing helper"** action with
a file picker, and checks the handful of obvious locations (alongside a
`111unified.ahk` found in common places) to pre-fill it.

Import parses the INI into the `eve_bookmarks` schema, reports what it found,
and requires confirmation before overwriting current values. Settings that no
longer exist — mode, the return preface, and the Copy and Paste binds — are
**discarded with an explicit note** rather than silently dropped, so a user
who relied on them learns that here rather than by noticing a key has stopped
working.

`HomeZeroIs0` gets its own treatment, because discarding it is not neutral.
An imported INI with `HomeZeroIs0=0` describes a user whose home bookmarks
number from 1, and the engine now always numbers from 0. Import must say so
in those terms — "your home bookmarks will start at .0 instead of .1" — not
report it as a setting that no longer applies.

It is available at any time, not only on first run: users will not all migrate
on the same day, and a one-shot prompt is easy to dismiss and then
irrecoverable.

## The vendored script

Wingman vendors a stripped copy. Removed: the GUI (`BuildMainGui`,
`ShowMainGui`, the config event handlers), the tray menu (`:63-68`), all
config writing (`SaveAllSettings`, `SaveWindowSettings`), the `DoCopy` and
`DoPaste` handlers, and every Protean/v21 branch together with the
`HomeZeroIs0` and return-preface logic. Retained: the hotkey engine, the INI
reader, and `ToolTip` feedback (`ShowRootTooltip`, `:682`), which is the
in-game feedback users actually read.

**The Protean removal is the largest single deletion and the riskiest.** The
mode is not localised — it branches inside every finisher, the parser, and
the status text — so this is threading logic out of the engine rather than
deleting a block. It is also, like the rest of the engine, untestable. The
smoke pass has to cover the surviving Flygd/ABH path deliberately rather than
assume that removing a branch left the other one intact.

**Two GUI handlers are operations, not configuration, and must survive.**
`SetManualRoot` and `ClearRoot` (`:218-222`, `:577-634`) mutate live engine
state: `SetManualRoot` parses a typed system name through `ParseBookmark` and
resets slot allocation, `ClearRoot` returns the engine to home mode. Removing
the GUI would delete them with no replacement.

Their coverage is partial rather than absent — `DoSemi` already sets root
from a selection and enters home mode on an empty clipboard — so the specific
loss is **setting a root by typing a system name**, which has no hotkey
equivalent. Both are retained and driven from the route through the command
channel below.

Four changes rather than deletions:

1. **`RefreshHotkeys` teardown is repaired, and only then made hot-reloadable.**
   Adding `GoSub, LoadAllSettings` at the top is necessary — the 10s timer
   (`:76`) already re-reads `[Enabled]` (`:716`) while `[Keybinds]` and
   `[Settings]` are startup-only globals — but it is **not sufficient**, and
   an earlier draft of this document wrongly claimed it was.

   Step 1 of `RefreshHotkeys` resets to the global context with
   `Hotkey, IfWinActive` (`:705-713`) and then disables bindings *in that
   context*. The eighteen window-scoped bindings are registered under
   `Hotkey, IfWinActive, %WinTitle%` (`:786`), a different criterion, and
   AHK v1 disables only the variant matching the current one. Those variants
   are therefore never torn down. This is a latent bug in the script today,
   rarely hit because rebinding is rare; routing every config change through
   this path would make it routine, leaving stale hotkeys live against
   windows the user has just disabled.

   The repair: record the window titles registered on the previous pass, and
   before rebinding, re-enter each of those contexts and disable its
   variants explicitly. Only then is the reload claim true.

   **This enlarges the script work materially.** `RefreshHotkeys` becomes
   modified logic rather than a deletion, which raises both review burden and
   the risk carried by the untestable part of this change. If the repair
   proves unreliable in the smoke pass, the fallback is to restart the
   process on any change to bindings or window enablement — correct by
   construction, at the cost of the in-flight state (root system, used slots)
   that hot reload exists to protect.

2. **Registration failures are recorded.** Every `Hotkey ... On UseErrorLevel`
   suppresses errors and nothing ever reads the result (`:767-823`), so a
   bind Windows refuses — one already claimed by another application —
   fails silently while the engine looks healthy. Each registration checks
   `ErrorLevel` and accumulates the failures, which are published in the
   status file and surfaced in the route.

3. `RefreshStatusTab` (`:365-389`) is repurposed. It already computes the
   five status values on a 2s timer; its sink changes from five `GuiControl`
   calls to writing `eve_status.json`, and it gains the failed-registration
   list and the last-consumed command sequence number.

4. `#SingleInstance` (`:5`) is pinned to `Force`, so a duplicate spawn
   replaces cleanly rather than prompting a user who has no GUI to answer.

## Lifecycle

- **Start** on app launch only when `enabled`, and on toggle. Spawned with
  `CREATE_NO_WINDOW` via the `_NO_WINDOW_KWARGS` idiom; without it a console
  flashes on every launch in the `console=False` build.
- **Stop** on Wingman exit, hooked in beside the existing `icon.stop()` /
  `scheduler.stop()` calls at `__main__.py:348`.
- **Orphan recovery is mandatory.** If Wingman crashes the child survives —
  a global keyboard hook with no UI left to disable it, recoverable only via
  Task Manager by a user who does not know what to look for. The spawned PID
  is recorded in `state_dir()` and terminated on the next start.

  **The PID alone is not sufficient identity.** Windows reuses PIDs, and this
  code path exists precisely to run after an unclean shutdown, when the
  recorded PID may since have been handed to something unrelated. Killing on
  a bare PID match would terminate an arbitrary user process.

  Nor is the image path enough on its own: the bundled interpreter is a
  general-purpose binary and could legitimately be running some other script.
  Identity is therefore the image path **plus** a run token — a unique value
  passed on the engine's command line at spawn and recorded alongside the PID
  — verified against the running process's command line. A mismatch on either
  means the entry is stale and is discarded rather than acted on.

  **Neither this nor `#SingleInstance Force` helps the user who never
  reopens Wingman.** An earlier draft claimed a distinction between them;
  there is none worth relying on, since both act only at the next spawn. A
  surviving engine after a crashed Wingman keeps its hook until Wingman is
  started again. Clean shutdown is what actually covers the common case, and
  this recovery is the backstop for when that did not happen — not a general
  answer to orphaned processes.
- **No auto-restart on unexpected death.** Surface "Stopped unexpectedly"
  with a Start button. A restart loop against a persistent failure — missing
  binary, corrupt INI, antivirus quarantine — respawns forever while
  appearing healthy, and quarantine is precisely the case where silent
  respawning is worst.
- **Binary resolution is bundled-only, with no PATH fallback.**
  `resolve_binary()` falls back to `shutil.which()`, which is right for
  ffmpeg and wrong here: a user with AutoHotkey v2 installed would have their
  v2 interpreter handed a v1 script, failing with parse errors that look like
  our bug. A missing engine reports "reinstall" instead. The `.ahk` is data,
  so it needs an `icon_file()`-style two-case resolver rather than
  `resolve_binary()`.

## Status display

**The status values live in the window's global status bar, not in the
Bookmarks route.** That bar already exists as chrome outside the routes
(`web/index.html:220-226`), holding upload status, a progress track and a
percentage, so this needs no new structure — the EVE values become a second
segment alongside them.

Placing them there rather than in the route is the point: current sig, root,
next numeric and next alpha stay visible while you are on Uploader, or with
the window parked on a second monitor. A readout you must navigate to is a
readout you will not look at mid-chain.

The segment appears only when the engine is enabled, so nothing changes for
users who never turn it on. At minimum window width it and the upload
progress compete for room; the EVE segment yields, since an upload in flight
is the more urgent of the two.

The panel is driven by **engine liveness, not file contents** — a stale
readout is worse than none, because a plausible-looking dead root system
would be acted on.

- not enabled → "Not running", no values
- enabled, process gone → "Stopped", values cleared, not frozen
- running, status file not updated within a few ticks → "Stale"

**Liveness is not health.** A process can be alive with some or all of its
bindings unregistered: every registration passes `UseErrorLevel` and nothing
reads the result (`:767-823`), so a bind Windows refuses — most commonly one
already claimed by another application — fails silently. Nothing in the five
status values would reveal it, and the user would simply find that a key does
nothing.

The status file therefore carries the failed-registration list produced by
the engine change above. The **Bookmarks route** reports it in full — which
binds failed, not merely that something did — since that is where the binds
are configured and fixed. The status bar carries only a warning marker
pointing there, because a list of failures does not fit a one-line strip.
Note this is a different failure from the collision check in `bookmarks.py`,
which can only catch conflicts *within* our own binds — it cannot know what
the rest of the system has claimed.

Wingman polls while running (existing `ui/scheduler.py`, ~1Hz) and pushes an
`onEveStatus` semantic event. The in-game tooltip is retained; the two serve
different moments — transient over the game, versus glanceable on a second
monitor.

## Navigation

The passive route label becomes a segmented control:

```
[▶ WINGMAN]  ( Uploader │ Bookmarks )     [⚙] [–] [✕]
 └ drag ─┘   └─ peer destinations ─┘       └ window actions ┘
```

This changes the kind of an existing element rather than its location, leaves
the two-pane main layout untouched, and preserves the distinction that
Settings is a window-level action while Uploader and Bookmarks are peers.

**The nav must be a sibling of `.pywebview-drag-region`, not a child.**
`style.css:100-102` states only that element drags and buttons must stay
clickable; clickable children of the drag region yield either dead buttons or
an immovable window. The existing winbtns show the correct pattern. The 44px
bar (`--titlebar-h`) is fixed, and this design strains past about four
destinations.

**The nav item is always visible; the master switch lives in the route.**
This keeps the feature discoverable despite `enabled` defaulting to False:
users find it, read what it does, then turn it on.

First-run hides the nav, exactly as it hides the gear (`app.js:100-102`) —
that screen is not dismissable.

## Keybind capture

**The mapping lives in Python.** JavaScript cannot be tested in this repo by
policy, so JS captures the raw event and renders what it is given; Python
makes every judgement and is covered by pytest.

```
JS ──▶ {ctrl, alt, shift, meta, code: "Comma"}
          │ bridge
          ▼
bookmarks.to_ahk(parts) ──▶ {"ahk": "^+,", "display": "Ctrl+Shift+,", "error": null}
```

Python returns both strings so JS holds no mapping table and cannot drift.

**`event.code`, not `event.key`.** `event.key` reports the produced character,
so Shift+`,` arrives as `<` and the shifting must be reversed to recover what
AHK wants. `event.code` is deterministic and testable.

**Accepted limitation:** this assumes a US layout. On AZERTY/QWERTZ the table
maps `Period` to `.` while the physical key produces something else, and AHK
resolves through the active layout. Punctuation binds are the expected usage
here rather than an edge case — the handler names still encode the original
keys (`DoComma`, `DoDot`, `DoQuote`, `DoSemi`) even though every bind is now
user-chosen and ships blank — so non-US users would hit this. Mitigated by a
manual entry field accepting an AHK string directly, validated by the same
function.

Validation the original GUI never performed, all pure and testable:

- reject modifier-only presses
- detect collisions across all 19 binds — `RefreshHotkeys` (`:707-828`)
  registers with `UseErrorLevel` and silently lets one win
- reject unmappable keys rather than writing a string AHK cannot parse

**One fact the UI must state.** Blank is a valid value — every row needs an
explicit clear affordance, round-tripping to an empty INI value that
`RefreshHotkeys` already treats as "do not register".

An earlier draft required the UI to mark Copy, Paste and Set Root as globally
scoped. That distinction is gone: those two binds are removed and Set Root is
now window-scoped like the rest, so all 19 rows are uniform and every one of
them is inert unless an enabled EVE window is active.

## Packaging and CI

- `packaging/fetch_autohotkey.py` mirrors `fetch_ffmpeg.py`: pinned URL plus
  SHA256 into `packaging/bin/`, with a `.autohotkey-version` sidecar so a
  bumped pin cannot silently keep shipping the old binary.
- `uploader.spec` gains the interpreter under `binaries` (destination `bin`)
  and the `.ahk` under `datas`.
- **A post-build assertion for the `.ahk` is required**, matching the
  existing ones for `web/`. Without it an uncollected script yields a green
  build and an engine that will not start.
- **Mirror the signature check** at `build.yml:155-177` against the
  AutoHotkey binary. Whether v1.1 releases are Authenticode-signed must be
  verified during implementation, not assumed.
- `installer.iss:56` copies the one-folder output wholesale; no installer
  change is needed.
- **GPL source obligations, which attribution alone does not satisfy.**
  AutoHotkey is GPLv2, as is the bundled FFmpeg build. Distributing the
  binaries obliges us to provide corresponding source or a valid written
  offer — a licence note in the README (`:319-321`) is not that, and
  `fetch_ffmpeg.py` deliberately extracts only `ffmpeg.exe` and `ffprobe.exe`
  (`:22`, `:54-65`), so no source accompanies either binary today.

  The design's answer: a `THIRD-PARTY-NOTICES` file shipped *in the installed
  tree*, naming each binary, its exact pinned version, its licence, and a
  written offer with the upstream source URL for that version. Pinning the
  version is what makes the offer valid — "latest upstream" does not
  correspond to what we shipped. The fetchers record the pin already, so the
  notice can be generated from the same constants rather than hand-maintained
  and left to drift.

  **This exposes a pre-existing gap for FFmpeg**, which ships today under the
  same terms with no offer at all. Fixing it is adjacent scope; whether it
  rides along is the maintainer's call, but adding a second GPL binary is a
  poor moment to leave the first one unaddressed.

## Testing and verification

Testable on Linux, covering every decision above:

| Under test | Approach |
|---|---|
| INI generation | golden-file, pure |
| INI import parsing | golden-file, incl. partial and corrupt inputs |
| Keybind → AHK notation | table-driven, incl. punctuation and `^;` in INI |
| Collision + modifier-only rejection | pure |
| Nested settings validation | corrupt/missing/wrong-type falls back |
| Nested defaults are not aliased | load → mutate → reload returns defaults |
| Atomic publication | writers use temp-plus-rename, never in-place |
| Command file sequencing | monotonic seq, replay suppression, restart init |
| Unconsumed-command guard | no overwrite before acknowledgement |
| Supervisor start/stop/liveness | injected `spawner`, per `test_chrome.py` |
| Orphan recovery incl. PID identity | injected `spawner` + fake PID/status files |
| Status staleness + failed-bind reporting | fake status files |

**Not testable, and the gap is wider than an earlier draft claimed.** No test
can confirm the hotkeys still fire after the strip. That draft argued the
strip was "deletions plus one changed sink, so it reads cleanly in review" —
that is no longer true. `RefreshHotkeys` now carries a repaired teardown and
per-registration error checking, so the untestable part contains **modified
control flow**, not just removals. Review is correspondingly harder and the
smoke pass matters more.

Additions to `docs/smoke-checklist.md`:

- hotkeys fire in a real EVE window
- **every finisher still produces the correct Flygd/ABH name** once the
  Protean branches are threaded out — the check that removing one mode did
  not disturb the other
- **home-mode bookmarks still number from `.0`** with the flag hardcoded —
  the check that dropping `HomeZeroIs0` preserved shipped behaviour rather
  than flipping it
- the status segment appears in the status bar while on the Uploader route,
  and yields to upload progress at minimum width
- **rebinding a window-scoped hotkey stops the old binding firing** — the
  direct test of the teardown repair, and the one that would have caught the
  original bug
- disabling a window stops its bindings firing
- a deliberately conflicting bind is reported as failed rather than silently dead
- Set Root and Clear Root from the route reach the engine
- importing an existing `eve_bookmark_helper.ini` reproduces that setup
- config applies within 10s without losing root and used slots
- orphan cleanup after a killed Wingman, and *no* kill when the PID has been
  reused by something else
- no console flash on spawn
- the title-bar drag region still drags with nav present

**One guard, modelled on `test_no_tk.py`:** assert the vendored `.ahk`
contains no `Gui,` commands and no `IniWrite`. That pins both invariants this
design rests on — the GUI stays gone and the engine never writes config — and
fails loudly if someone re-syncs from upstream and undoes the strip.

## Risks and open items

1. **The engine changes are unverifiable by test, and they grew.** Highest
   residual risk by some margin. What began as deletions plus one changed
   sink now also includes a repaired `RefreshHotkeys` teardown,
   per-registration error checking, a command-file reader, and the removal of
   Protean/v21 logic threaded through the finishers and parser. None of it
   can be exercised by pytest. Mitigated by review and an expanded smoke
   checklist, not eliminated.
2. **AutoHotkey signing is unconfirmed.** If v1.1 binaries are unsigned, the
   CI check cannot mirror the WebView2 one and that should be a conscious
   decision rather than a silent omission.
3. **Antivirus and SmartScreen.** The installer is unsigned
   (`webview-replatform-design.md:509`, risk 4, already flags this as a
   watch item). The maintainer reports no problems in practice; adding a
   keyboard-hook binary is nevertheless a change to that posture.
4. **Non-US keyboard layouts** are a known gap, mitigated but not solved by
   manual entry.
5. **Windows enumeration** must follow the Linux-importable pattern; the EVE
   window list is discovered by title prefix `EVE - `, which is how the
   script already identifies them (`:248`, `:1028`).
6. **INI escaping.** Values reach AHK via `IniRead` into a variable and are
   never parsed as script text, and Windows INI parsing treats `;` as a
   comment only at line start. `Copy=^;` should therefore survive, but this
   warrants a test rather than confidence.

## Out of scope

- Porting the naming logic to Python. The seam is designed for it; the work
  is not part of this change.
- Reviving the AHK GUI in any form. The status *values* it displayed are
  reproduced natively (see Status display); the window itself is not, and
  nothing may reintroduce a second surface that writes config.
- Any change to upload, stitching, combat-log, or Discord behaviour.
- Code signing the installer.
- Light mode, a frontend build step, or a browser test toolchain.
- More than two peer destinations in the title bar.

## Assumptions that may change

- Wingman replaces the standalone script; the vendored copy is canonical and
  no upstream re-sync is planned.
- Two destinations plus Settings fit the 44px title bar comfortably. A third
  feature area would reopen the navigation question.
- The 10s reload timer is fast enough for config changes to feel applied. If
  not, the timer interval is the adjustment, not the architecture.
- **Nobody in the corp needs Protean/v21, `HomeZeroIs0`, a return preface, or
  the Copy and Paste binds.** This is the assumption the scope reductions rest
  on, and it is the one most likely to be wrong for someone outside the
  immediate group. Restoring any of them means re-adding logic the vendored
  script no longer contains, so it is cheap to decide now and expensive to
  reverse later — which is why import reports discarded settings explicitly
  rather than dropping them quietly.
- The status segment and upload progress can share one status bar without
  either becoming unreadable. If they cannot, the EVE values move rather than
  the bar growing.
