# EVE client preview subsystem

Design. Base: `bump-3.2.0` (f16b6c0), 2026-08-23.

## Outcome

Live previews of running EVE Online clients, floating over the desktop, with
click-to-focus switching, per-character and cycle hotkeys, custom labels,
and layouts that persist across restarts.

The capability exists today in TriffView (GPL-3.0-only, C#/.NET). This is a
port into Wingman, not a rewrite of TriffView. Wingman relicensed from MIT to
GPL-3.0-only to make that lawful; see `worktree-gpl3-relicense`. **The
relicense is not yet effective** — elboaf holds the copyright line and has to
agree before it is published. No TriffView-derived code may land until it is.

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

## Module boundaries

New package `obs_youtube_uploader/preview/`. Split so the pure-logic half is
testable on Linux, matching the discipline `evewindows.py` already sets.

| Module | Responsibility | Platform |
|---|---|---|
| `win32.py` | ctypes declarations, structs, constants | Windows types, imports anywhere |
| `discovery.py` | Enumerate EVE clients, parse character names, stable keys | Win32 call, pure parsing |
| `geometry.py` | Rects, default stack placement, snapping, hit-testing | **Pure — Linux-testable** |
| `chrome.py` | Pillow rendering of border/label/alert to RGBA | **Pure — Linux-testable** |
| `gestures.py` | Hotkey gesture parsing (`Ctrl+Alt+F1`, `VK_`/hex) | **Pure — Linux-testable** |
| `cycle.py` | Cycle-group index maths, per-group cursor | **Pure — Linux-testable** |
| `layout.py` | Persistence of frame rects, labels, hotkeys | **Pure — Linux-testable** |
| `layered.py` | DIB section + `UpdateLayeredWindow` plumbing | Windows |
| `thumbnail.py` | `DwmRegisterThumbnail` lifecycle wrapper | Windows |
| `window.py` | One preview: HWND lifecycle, styles, mouse gestures | Windows |
| `host.py` | The thread, pump, preview registry, hotkeys, WinEvent hook | Windows |

`gestures.py` is named to avoid confusion with the existing top-level
`hotkeys.py`, which supervises the AutoHotkey bookmark engine and is unrelated.

Five of the eleven modules are pure Python, and `discovery.py` is pure
apart from one enumeration call. TriffView's equivalent logic —
geometry, snapping, cycle maths, gesture parsing, position memory — is already
framework-free integer arithmetic (`TriffViewRect.cs`, `TriffViewCycleState.cs`,
`PreviewPointerGesture.cs`); this split just makes that explicit and testable.

## Discovery

Extends the existing `evewindows.py` rather than duplicating it. That module
already enumerates EVE windows by title with correctly declared argtypes, and
its docstring explains why those declarations are load-bearing.

Two changes it needs: return HWNDs (it currently returns titles), and filter by
process name so a browser tab titled `EVE - something` cannot masquerade as a
client. TriffView filters on process `exefile` before matching the title
(`TriffViewSubsystem.cs:4738-4790`); Wingman's `procid.py` already has the
process-identity machinery.

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

Layout writes go through `atomicio.py`, which the bookmarks work already added
for exactly this class of problem.

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
  Nothing here changes that. `test_discord.py::test_unreadable_archive_is_reported_not_raised`
  already fails on Windows (it revokes read permission via `chmod`, which
  Windows ignores) and will need a `skipif` if the suite is ever run there.

## Scope

**First slice** — the daily-use core:

1. Discovery of running clients with stable identity.
2. One layered preview window per client, Pillow chrome, DWM thumbnail.
3. Click-to-focus, including the `AttachThreadInput` foreground sequence.
4. Drag to move, resize handle, snapping.
5. Layout persistence across restarts.
6. Enable/disable from the Wingman UI.

**Deferred, in rough priority order:**

7. Per-character and cycle-group hotkeys (`gestures.py`, `cycle.py` land in the
   first slice as pure logic, unwired).
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

1. **Process DPI awareness is set once, process-wide, before any window
   exists.** The probes called `SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)`
   at import, before pywebview initialised, and it returned true. In Wingman the
   preview subsystem starts *after* the webview, by which point WinForms has
   very likely already set process awareness — our call would fail, and if
   WinForms chose System-aware, every rect is silently virtualized on a
   multi-DPI setup. **Mitigation**: set PMv2 in `__main__.py` before pywebview
   is imported, and read back the effective awareness rather than assuming.
   **This is unverified and is the highest-risk open item.**
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
