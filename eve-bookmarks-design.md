# Integrating the EVE bookmark helper into FlyGD Wingman — design

Status: approved in brainstorming, not yet planned or implemented.
Date: 2026-08-22

## Intended outcome

Wingman gains a second feature area: the EVE wormhole bookmark hotkey helper
currently distributed as a standalone AutoHotkey script (`111unified.ahk`,
1981 lines). Wingman becomes the way that tool is run, and the standalone
script is retired.

The user-visible result is a `Bookmarks` destination in the window offering
native configuration — 21 keybinds, four mode settings, per-EVE-window
enablement — plus a live status readout, backed by a supervised background
process that provides the hotkey behaviour unchanged.

This is a deliberate widening of the product from "OBS recording companion"
to "general EVE assistant", confirmed with the maintainer.

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

### Config and status: two files, one writer each

```
settings.json ──generate_ini()──▶ eve_bookmark_helper.ini ──read──▶ engine
   ▲ Wingman writes                   Wingman writes                  │
   │                                                                  │ writes
   └────── bridge push ◀── Wingman reads ◀── eve_status.json ◀────────┘
```

`settings.json` is the single source of truth. The INI is a derived artifact,
regenerated on every save, never hand-edited. The engine reads config and
writes only its own runtime state. No file has two writers.

All three live in `paths.state_dir()`. The engine is spawned with
`cwd=state_dir()`, which makes the script's relative `IniFile` (`:71`)
resolve there with no edit to the script.

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
    "mode": 1,                 # 1 = Protean/v21, 2 = Flygd/ABH
    "home_zero_is_0": True,
    "preface_return": True,
    "return_preface": "!",
    "keybinds": {...},         # 21 entries, AHK notation, "" = unbound
    "windows": {...},          # "EVE - Character Name" -> bool
}
```

`load()` gains a nested validation pass. It must be defensive: these values
are written into a file that drives global keyboard hooks, so a corrupt entry
falls back to its default and is logged rather than propagated.

Two defaults are deliberate:

- **`enabled` defaults to False.** Upgrading users do not silently acquire a
  global keyboard hook; they opt in.
- **Keybinds default unbound.** The script ships 20 of 21 blank
  (`:120-140`); preserving that means no surprise collisions on first run.

## The vendored script

Wingman vendors a stripped copy. Removed: the GUI (`BuildMainGui`,
`ShowMainGui`, all GUI event handlers), the tray menu (`:63-68`), and all
config writing (`SaveAllSettings`, `SaveWindowSettings`). Retained: the
hotkey engine, the INI reader, and `ToolTip` feedback (`ShowRootTooltip`,
`:682`), which is the in-game feedback users actually read.

Three changes rather than deletions:

1. `GoSub, LoadAllSettings` at the top of `RefreshHotkeys`. The 10s timer
   (`:76`) already re-reads `[Enabled]` (`:716`), but `[Keybinds]` and
   `[Settings]` are startup-only globals. This one line makes the whole INI
   hot-reloadable, so config changes apply without restarting the process
   and losing in-flight state (root system, used slots).
2. `RefreshStatusTab` (`:365-389`) is repurposed. It already computes the
   five status values on a 2s timer; only its sink changes, from five
   `GuiControl` calls to writing `eve_status.json`.
3. `#SingleInstance` (`:5`) is pinned to `Force`, so a duplicate spawn
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
  is recorded in `state_dir()`; every start terminates a recorded PID that is
  still alive before spawning.
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

The panel is driven by **engine liveness, not file contents** — a stale
readout is worse than none, because a plausible-looking dead root system
would be acted on.

- not enabled → "Not running", no values
- enabled, process gone → "Stopped", values cleared, not frozen
- running, status file not updated within a few ticks → "Stale"

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
- detect collisions across all 21 binds — `RefreshHotkeys` (`:707-828`)
  registers with `UseErrorLevel` and silently lets one win
- reject unmappable keys rather than writing a string AHK cannot parse

**Two facts the UI must state.** Copy, Paste and Set Root register globally
(`:765-772`) while the other eighteen require an active enabled EVE window;
a global bind can shadow a shortcut in every other application, so those
three are marked rather than presented as uniform rows. And blank is a valid
value — every row needs an explicit clear affordance, round-tripping to an
empty INI value that `RefreshHotkeys` already treats as "do not register".

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
- **Third-party attribution.** AutoHotkey is GPLv2, as is the bundled FFmpeg
  build. The README's licence section (`:319-321`) states MIT only, so a
  written offer of source appears to be missing today for FFmpeg. Adding a
  section covering both is in scope; the pre-existing FFmpeg half rides along
  at the maintainer's discretion.

## Testing and verification

Testable on Linux, covering every decision above:

| Under test | Approach |
|---|---|
| INI generation | golden-file, pure |
| Keybind → AHK notation | table-driven, incl. punctuation and `^;` in INI |
| Collision + modifier-only rejection | pure |
| Nested settings validation | corrupt/missing/wrong-type falls back |
| Supervisor start/stop/liveness | injected `spawner`, per `test_chrome.py` |
| Orphan recovery, status staleness | injected `spawner` + fake PID/status files |

**Not testable, stated plainly:** no test can confirm the hotkeys still fire
after the strip. Mitigations are that the strip is deletions plus one changed
sink, so it reads cleanly in review, and additions to
`docs/smoke-checklist.md`: hotkeys fire in a real EVE window, config applies
within 10s, orphan cleanup after a killed Wingman, no console flash, and the
title-bar drag region still drags with nav present.

**One guard, modelled on `test_no_tk.py`:** assert the vendored `.ahk`
contains no `Gui,` commands and no `IniWrite`. That pins both invariants this
design rests on — the GUI stays gone and the engine never writes config — and
fails loudly if someone re-syncs from upstream and undoes the strip.

## Risks and open items

1. **The strip is unverifiable by test.** Highest residual risk. Mitigated by
   review and the smoke checklist, not eliminated.
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
