# EVE client preview subsystem

Design. Base: `bump-3.2.0` (f16b6c0), 2026-08-23.

## Outcome

Live previews of running EVE Online clients, floating over the desktop, with
click-to-focus switching, per-character and cycle hotkeys, custom labels,
and layouts that persist across restarts.

The capability exists today in TriffView (GPL-3.0-only, C#/.NET). This is a
port into Wingman, not a rewrite of TriffView.

**Wingman is GPL-3.0-only as of this branch**, which is what makes deriving
from TriffView lawful. The relicense rides along in the same change: `LICENSE`
carries the GPL-3.0 text, `README.md` and `THIRD-PARTY-NOTICES.md` state it,
and `pyproject.toml` declares `license = "GPL-3.0-only"`.

`GPL-3.0-only` rather than `-or-later` because TriffView's own grant is v3-only
(its `README.md:103`); an "or later" claim could not survive the combination.

Two consequences worth stating plainly, since they outlive this design:
everything Wingman published up to and including 3.1.1 remains MIT and can
still be forked as such — the relicense binds forward, not backward. And the
GPL now runs both ways: preview fixes made here can go back to TriffView,
which was previously blocked in that direction too.

## What was verified, and how

Five throwaway probes ran on Windows against real EVE clients before any of
this was designed. They are the reason the architecture below looks the way
it does, and two of them overturned an earlier plan.

| # | Question | Result |
|---|---|---|
| 1 | Can Python/ctypes host a live DWM thumbnail at all? | **Yes.** `DwmRegisterThumbnail` + `DwmUpdateThumbnailProperties` both `hr=0x0` into a `CreateWindowExW` popup. No .NET, no WPF, no Qt. Confirmed visually. |
| 2 | Can preview HWNDs share pywebview's message pump? | **No.** Windows created on the thread that calls `webview.start()` are orphaned; `InvalidateRect` produced 0 paints. |
| 3 | Why? | pywebview's window lives on a *different* thread (`84212`) from the caller (`58544`). `webview.start()` does not pump on the calling thread. |
| 4 | Does a dedicated preview thread with its own pump work? | **Yes.** `WM_PAINT` delivered, `RegisterHotKey` succeeded on that thread, 3/3 `PostMessage(WM_APP+1)` marshalled in, thumbnails rendered — all with a live pywebview in the same process. |
| 5 | Can Pillow + `UpdateLayeredWindow` replace the GDI+ drawing layer? | **Yes.** Pillow-rendered border and label pushed via `ULW_ALPHA`; the DWM thumbnail composites *over* per-pixel-alpha content, including over an opaque interior. |

Probe 3 is the load-bearing one. An in-process design that assumed pywebview's
pump was reachable would have failed late and confusingly, as a subsystem that
renders but never responds.

## Architecture

```
main thread ──► webview.start()      pywebview owns a separate GUI thread
     │
     │  PostMessage(WM_APP+n)              evaluate_js()
     ▼                                            ▲
preview thread ── GetMessage / DispatchMessage ───┘
     ├─ owns every preview HWND (thread-affine, non-negotiable)
     ├─ RegisterHotKey            → WM_HOTKEY
     ├─ SetWinEventHook           → EVENT_SYSTEM_FOREGROUND
     └─ DwmRegisterThumbnail      → one per client
```

This mirrors a pattern Wingman already established. `ui/scheduler.py`'s
docstring records the same discovery from the Tk-to-pywebview move —
*"`webview.start()` carries none of it"* — and answers it with an owned
off-thread loop. The preview thread is that pattern one level lower, in Win32
rather than `threading.Timer`.

### Threading contract

Every HWND touch happens on the preview thread. This is an invariant, not a
guideline: Win32 window ownership is thread-affine, and violations produce
hangs rather than exceptions, which are far harder to diagnose.

The public API is therefore message-passing only. `PreviewHost` exposes
ordinary Python methods that validate the calling thread and `PostMessage` a
command; nothing outside the module touches an HWND. A debug-mode assertion on
`GetCurrentThreadId()` at every Win32 entry point catches violations where they
happen instead of where they hang.

### Lifecycle

`PreviewHost` has an explicit start/stop contract, and both enable/disable and
application shutdown go through it. Today's shutdown path stops only the
scheduler and the bookmark engine (`__main__.py:410-416`); `PreviewHost.stop()`
must be wired in alongside them.

`stop()` is idempotent, safe to call when never started, and ordered:

1. Unregister hotkeys (`UnregisterHotKey`) — before the windows they target die.
2. Unhook the WinEvent hook (`UnhookWinEvent`).
3. Unregister every DWM thumbnail (`DwmUnregisterThumbnail`).
4. Destroy every preview window (`DestroyWindow`), on the preview thread.
5. `PostQuitMessage` to end the pump.
6. Join the thread with a timeout, and log if it does not exit.

Steps 1-4 must run *on the preview thread*, so `stop()` from the UI thread
marshals a shutdown command and waits. A `stop()` that returns while the thread
still owns HWNDs leaves the process unable to exit cleanly — the failure mode
is a Wingman that vanishes from the tray but lingers in Task Manager.

Disable is the same sequence as shutdown; enable is a fresh `start()`. There is
no half-running state where the thread is alive but previews are hidden.

## Window topology

**One small layered window per preview**, not TriffView's single
desktop-spanning window plus `SetWindowRgn`.

TriffView's topology is the direct cause of its worst performance problem.
`TriffViewSubsystem.cs:4634-4645` documents five separate attempts at bounded
repaint of the colour-keyed label overlay, all producing ghosts or solid white
bands, leaving full-surface repaint of a desktop-sized window as the only
option that worked. Per-preview windows make that problem structurally
impossible: each window is ~320x210, repaint is inherently bounded, and there
is no region to rebuild.

Per-preview windows also give, for free, what TriffView builds by hand:
per-preview opacity and z-order, natural per-monitor DPI behaviour, hit-testing
without region maths, and labels in the same window rather than a second
colour-keyed one.

Cost: N HWNDs instead of 2. HWNDs are cheap; the bookkeeping is a dict.

### Window style

`WS_POPUP`, with `WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE`, plus
`WS_EX_TOPMOST` when the profile allows it. `WS_EX_TOOLWINDOW` keeps previews
out of the taskbar and Alt-Tab; `WS_EX_NOACTIVATE` stops a click from stealing
focus from the EVE client the user is about to switch to.

## Drawing layer

Pillow renders the complete preview chrome — border, label band, label text,
alert ring — into an RGBA image. That image is premultiplied, copied into a
DIB section, and pushed with `UpdateLayeredWindow(..., ULW_ALPHA)`. The DWM
thumbnail composites over it.

This is the single biggest departure from TriffView, and the biggest saving.
It replaces the GDI+ P/Invoke surface (`Graphics`, pens, `DrawString`,
`ClearTypeGridFit`, `StringTrimming`) with a library Wingman already depends
on — and it moves all chrome rendering into pure, Linux-testable Python. A
test can assert the pixels of a rendered label without a Windows box.

Two mechanical points:

- `ULW_ALPHA` requires **premultiplied** BGRA. Skipping premultiplication
  makes translucent pixels glow, which looks correct on dark backgrounds and
  wrong everywhere else. Pillow's raw encoder mode `"BGRa"` (lowercase `a`)
  emits premultiplied bytes directly; the probe used a per-pixel Python loop,
  which is too slow for production and should be replaced by
  `img.tobytes("raw", "BGRa")`. Verify that encoder's output during
  implementation rather than trusting this note.
- Bundled fonts are `.woff2` (`web/fonts/`), which Pillow cannot load. Labels
  need a TTF: either a system font (`segoeui.ttf`, as the probe used) or a
  bundled TTF. Bundling is preferable — it makes label rendering deterministic
  and testable on Linux — and adds a third-party notice entry.

### Redraw discipline

Chrome is static. It re-renders on label change, resize, selection change, or
alert state change — not per frame. The thumbnail itself costs nothing: DWM
composites it continuously without our involvement.

Alert flashing is the one case that would re-render at ~80ms. Rather than
re-rendering the bitmap, pulse `SetLayeredWindowAttributes` alpha or
pre-render a small ring of flash frames. Deferred with alerts (see Scope).

## DPI awareness

Previews need per-monitor DPI to place rects correctly across mixed-scale
monitors. The obvious move — make the process Per-Monitor V2 — is wrong here,
and would break two documented decisions.

`__main__.set_dpi_awareness()` deliberately selects `PROCESS_SYSTEM_DPI_AWARE`,
and says so in its own docstring: *"PROCESS_SYSTEM_DPI_AWARE, not Per-Monitor
V2. System-DPI-aware is correct for a single-window tray utility and avoids
handling WM_DPICHANGED when the window is dragged between monitors of different
scale"* (`__main__.py:99-114`). `ui/chrome.py:177-186` then builds on that
choice, matching pywebview's own `_scale` *"including its known wrongness on a
second monitor at another scale"*, on the reasoning that improving on it there
would just disagree with pywebview.

Changing the process-wide setting would silently invalidate both. It is not an
option.

**The preview thread instead sets its own awareness.** DPI awareness has a
thread-local override, `SetThreadDpiAwarenessContext(PER_MONITOR_AWARE_V2)`,
which applies to windows created on that thread and leaves the process context
untouched. Because previews already live on a dedicated thread that owns all
their HWNDs, this fits the architecture exactly:

- the process stays `PROCESS_SYSTEM_DPI_AWARE`;
- `__main__.py` and `ui/chrome.py` are untouched, and pywebview's window keeps
  behaving exactly as it does today;
- preview windows, created on the preview thread, are Per-Monitor V2 and get
  correct physical rects on every monitor.

The call is made once, first thing on the preview thread, before any window is
created. Its return value is checked rather than assumed — the earlier probes'
success with the process-wide call proves nothing about this path, because they
ran standalone before `set_dpi_awareness()` existed in the process.

## Module boundaries

New package `obs_youtube_uploader/preview/`. Split so the pure-logic half is
testable on Linux, matching the discipline `evewindows.py` already sets.

| Module | Responsibility | Platform |
|---|---|---|
| `win32.py` | ctypes declarations, structs, constants | Windows types, imports anywhere |
| `discovery.py` | Enumerate EVE clients, parse character names, stable keys | Win32 call, pure parsing |
| `geometry.py` | Rects, default stack placement, snapping, hit-testing | **Pure — Linux-testable** |
| `chrome.py` | Pillow rendering of border/label/alert to RGBA | **Pure — Linux-testable** |
| `gestures.py` | Hotkey gesture parsing (`Ctrl+Alt+F1`, `VK_`/hex) | **Pure — Linux-testable** *(deferred)* |
| `cycle.py` | Cycle-group index maths, per-group cursor | **Pure — Linux-testable** *(deferred)* |
| `layout.py` | Persistence of frame rects, labels, hotkeys | **Pure — Linux-testable** |
| `layered.py` | DIB section + `UpdateLayeredWindow` plumbing | Windows |
| `thumbnail.py` | `DwmRegisterThumbnail` lifecycle wrapper | Windows |
| `window.py` | One preview: HWND lifecycle, styles, mouse gestures | Windows |
| `host.py` | The thread, pump, preview registry, hotkeys, WinEvent hook | Windows |

`gestures.py` is named to avoid confusion with the existing top-level
`hotkeys.py`, which supervises the AutoHotkey bookmark engine and is unrelated.

**`obs_youtube_uploader.preview` must be added to `packages` in
`pyproject.toml`.** Package discovery is explicitly enumerated there
(`pyproject.toml:49`), and the surrounding comment states the consequence
plainly: subpackages are not implied by their parent, and a missing entry
"installs cleanly and fails at import time in the built artifact, not in the
checkout where the source tree makes it work anyway"
(`pyproject.toml:38-49`). A source checkout would pass every test while the
frozen release crashed on launch. This is a required step, not a follow-up.

Five of the eleven modules are pure Python, and `discovery.py` is pure
apart from one enumeration call. TriffView's equivalent logic —
geometry, snapping, cycle maths, gesture parsing, position memory — is already
framework-free integer arithmetic (`TriffViewRect.cs`, `TriffViewCycleState.cs`,
`PreviewPointerGesture.cs`); this split just makes that explicit and testable.

## Discovery

`evewindows.py` already enumerates EVE windows with correctly declared
argtypes, and its docstring explains why those declarations are load-bearing.
The temptation is to widen it. Don't.

`list_eve_windows()` returns *sorted, de-duplicated title strings*
(`evewindows.py:80-89`), and `ui/api.py:1288-1303` passes that list straight to
the page for the bookmarks feature. Changing its return type to carry HWNDs
would break that contract silently. **The existing signature is preserved
unchanged.**

Instead, `preview/discovery.py` owns a separate, handle-bearing interface
returning `(hwnd, title, pid, character_name, stable_key)` records. The two
share the low-level enumeration helper in `evewindows.py` — the argtypes
discipline stays in one place — but not the public function. Title-only
consumers keep the old call; the preview subsystem uses the new one.

Discovery also filters by process name, so a browser tab titled
`EVE - something` cannot masquerade as a client. TriffView filters on process
`exefile` before matching the title (`TriffViewSubsystem.cs:4738-4790`).

**This must not use `procid.describe()`.** That function shells out to
PowerShell running `Get-CimInstance` per PID with a ten-second timeout
(`procid.py:21-37`), and its own docstring justifies the cost as "one call on
one code path". At a 700ms sweep across 10-30 clients it would be
catastrophic. Discovery instead uses `QueryFullProcessImageNameW` against a
handle from `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)`, with:

- a `pid -> image name` cache, invalidated periodically (TriffView flushes
  every 512 sweeps, `TriffViewSubsystem.cs:4732`);
- explicit handling of access-denied, which is expected for processes owned by
  another user or at higher integrity — treat as "not an EVE client" rather
  than as an error;
- no fallback to `procid.describe()` on failure, at any sweep rate.

Sweep on a timer (TriffView uses 700ms) plus an immediate re-sweep on
`EVENT_SYSTEM_FOREGROUND`. Identity key is the character name where available,
falling back to HWND — clients sitting at character-select have no stable
identity and must never have a layout persisted against them.

## Persistence and settings

Preview configuration lives in Wingman's existing `settings.py`, not a new
store. TriffView's profile model (multiple named profiles, each with its own
layouts and hotkeys) is more than the first slice needs; a single implicit
profile is enough, with the schema shaped so profiles can be added without
migration.

Persisted per preview: frame rect, label override, lock state. Persisted
globally: preview size defaults, opacity, border colours, label placement and
size, hotkey bindings, cycle groups.

### Who may write settings

The preview thread must never call `settings.save()` directly. `save()` rewrites
the *complete projected document* from `DEFAULTS` on every call
(`settings.py:145-149`), and `ui/api.py:139-141` replaces app state wholesale,
so two writers racing lose each other's updates entirely — the last writer wins
the whole file, not just its own keys.

`atomicio.py` does not solve this, and the design must not claim it does. Its
docstring is explicit that it exists so "a concurrent reader never sees it
half-written" and that "single writer ownership settles who may write; it says
nothing about what a reader polling on a timer observes mid-write"
(`atomicio.py:1-5`). It addresses torn reads across the Wingman/engine
boundary. The hazard here is lost updates, which is a different problem.

**`settings.save()` is not single-writer today, and assuming it is would be a
mistake.** `ui/api.py:722-739` writes from an upload worker thread, and says so
deliberately: *"The settings write stays on this worker thread deliberately: it
is a short plain-file write, and persisting here means the channel survives a
crash before the next clean exit."* Adding the preview thread makes a third
writer of a file that already has two.

The contract is therefore **serialized writes, each a read-modify-write of its
own subtree**:

- `settings.py` gains a module-level `threading.Lock` held across the whole of
  `save()`. This is a correctness fix for a race that exists today, not new
  machinery for previews — a channel-title write racing a settings-pane write
  can already lose one of them.
- No writer may serialize a stale snapshot. A writer mutates the live settings
  dict and calls `save()`; it must never rebuild the document from a copy it
  read earlier, because `save()` projects the *complete* document from
  `DEFAULTS` (`settings.py:145-149`) and would write back whatever its snapshot
  was missing.
- The preview thread owns preview state in memory and is the authority on it,
  but does not write. On change (moved, resized, relabelled, locked) it marshals
  a delta out; the receiving side merges that delta into the live dict and
  saves.
- **Merges are per-key, never wholesale.** Replacing `preview.layouts` with only
  the previews seen this session would delete the saved position of every client
  that happened not to be running — which is most of them, most of the time.
- Writes are debounced. A drag produces a rect update per mouse-move, and each
  one must not rewrite the file.

## UI integration

The preview subsystem is headless with respect to the webview. Settings reach
it as ordinary calls from `ui/api.py`; state reaches the page through the
existing `evaluate_js` path used for app state today. No new IPC.

The subsystem starts lazily — no preview thread, no hooks, no timer until the
feature is enabled. A Wingman user who never touches EVE previews should not
pay a thread or a 700ms sweep for it.

## Testing

- **Pure modules** (geometry, chrome, gestures, cycle, layout): ordinary
  pytest on Linux, in CI. This is the majority of the logic and where the real
  bugs live — snapping, cycle wrap-around, gesture parsing, rect resolution.
- **Chrome rendering**: assert on rendered pixels — border colour at known
  offsets, label band height, text bounding box. Deterministic given a bundled
  TTF.
- **Windows-only modules**: thin by construction, exercised through a manual
  smoke checklist. The bookmarks work established this pattern already
  (`docs/` smoke checks for the engine).
- **Note**: `ci.yml` runs on `ubuntu-latest`; only build/release use Windows.
  Nothing here changes that.
  `test_discord.py::test_unreadable_archive_is_reported_not_raised` already
  fails on Windows (it revokes read permission via `chmod`, which Windows
  ignores) and will need a `skipif` if the suite is ever run there.

### Observability

The Windows-only half is exercised by a manual checklist, which means when it
breaks in the field the log is the only evidence. Wingman already has durable
rotating logging (`__main__.py:26-64`); the preview subsystem uses it rather
than inventing anything.

Logged with context, at least once per occurrence and never in a tight loop:

- discovery sweep results when the client set changes — count, and the identity
  keys added or removed;
- `DwmRegisterThumbnail` failure, with the `HRESULT` and the target title;
- `SetWinEventHook` or `RegisterHotKey` failure, with which gesture failed and
  why (a hotkey already claimed by another application is the common case, and
  is a user-actionable condition, not a bug);
- `SetThreadDpiAwarenessContext` result at thread start;
- preview thread death, from the joiner's side.

Two of these need a **user-visible degraded state**, not just a log line: a
hotkey that could not be registered, and DWM composition being unavailable.
Both are conditions the user can act on and would otherwise experience as "the
feature silently does nothing". They surface in the UI the same way other
status is pushed to the page.

## Scope

**First slice** — the daily-use core:

1. Discovery of running clients with stable identity.
2. One layered preview window per client, Pillow chrome, DWM thumbnail.
3. Click-to-focus, including the `AttachThreadInput` foreground sequence.
4. Drag to move, resize handle, snapping.
5. Layout persistence across restarts.
6. Enable/disable from the Wingman UI.

**Deferred, in rough priority order:**

7. Per-character and cycle-group hotkeys, including `gestures.py` and
   `cycle.py`. These are deferred *whole* — writing them unwired in the first
   slice would be speculative, since their only consumers are deferred too.
8. Custom labels, label placement and colours.
9. Alert flashing driven by EVE log watching.
10. Minimize-inactive-on-switch, hide-active-preview.
11. EVE client window layout save/restore.
12. Multiple named profiles.
13. EVE-O / EVE-X preview profile import.

**Explicitly excluded**: anything that reads EVE process memory, injects input
into a client, performs OCR, or automates gameplay. Previews are DWM
compositions of windows the OS already exposes; focus switching uses documented
window-activation APIs. This boundary matches TriffView's own stated position
and should not be quietly crossed.

## Risks and open questions

1. **Thread-local DPI awareness must be verified.** See the DPI section
   above. `SetThreadDpiAwarenessContext` is documented as Windows 10 1607+ and
   should be checked against Wingman's supported floor, and the interaction
   between a Per-Monitor-V2 thread and `DwmUpdateThumbnailProperties`
   destination rects is unverified. If thread-local awareness does not hold,
   the fallback is to keep the preview thread System-aware like the rest of the
   process and accept TriffView-equivalent behaviour on mixed-DPI setups —
   **not** to change the process-wide setting.
2. **Premultiplied-alpha encoder.** `img.tobytes("raw", "BGRa")` is expected to
   produce premultiplied output; unverified. The fallback is a numpy-free
   per-pixel loop, which is too slow, or `ImageChops` arithmetic.
3. **Thumbnail count.** Probes ran 2 thumbnails; TriffView users run 10-30. DWM
   cost per thumbnail is not measured. Worth a scaling probe before committing
   to the sweep interval.
4. **Occlusion between topmost windows.** With TriffView also running, z-order
   among `WS_EX_TOPMOST` windows is arbitrary — visible in probe 4, where the
   probe window ended up behind TriffView's previews. Not a defect, but it means
   running both simultaneously is not a supported configuration.
5. **`AttachThreadInput` focus sequence** must be replicated exactly, including
   strictly balanced detach and reading the verdict from `GetForegroundWindow`
   rather than `SetForegroundWindow`'s return value
   (`TriffViewSubsystem.cs:3055-3170`).

## Sizing

TriffView's equivalent is ≈4,050 lines of C# (excluding EVE-O import,
combat-log export, and alert-service glue). The Python port should be
materially smaller: Pillow removes the GDI+ layer, per-preview windows remove
the region and colour-key machinery, and the profile model is deferred. The
first slice is the discovery, geometry, chrome, layered, thumbnail, window, and
host modules — call it 1,200-1,600 lines including tests, with the pure half
carrying most of the test weight.
