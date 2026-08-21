# Window resize plan

Restore user resizing to the frameless window, using the approach proven by
`spikes/frameless_resize_spike.py` on Windows 11 with WebView2 151.0.4129.93.

## Intended outcome

The main window can be resized by dragging any edge or corner, with the
sizing cursors Windows normally shows. It cannot be dragged smaller than the
layout supports. Maximizing fills the work area and leaves the taskbar
visible. The custom title bar, its drag region, and every existing button
behave exactly as they do now.

Off Windows, and on any Windows box where the native call fails, the app
starts and runs exactly as it does today — a non-resizable window, not a
crash.

## Evidence and constraints

- `ui/window.py:125` passes `frameless=True`. pywebview maps that to
  `FormBorderStyle.None` (`platforms/winforms.py:269`), removing the whole
  non-client frame. `resizable` is left at its `True` default and is not the
  cause.
- **The WebView2 child owns every pixel.** pywebview docks the control
  `DockStyle.Fill` + `BringToFront()` (`platforms/edgechromium.py:95-100`).
  The spike measured four Chromium children — `Chrome_WidgetWin_0`,
  `Chrome_WidgetWin_1`, `Chrome_RenderWidgetHostHWND`, `Intermediate D3D
  Window` — all at exactly the form's rect. `WM_NCHITTEST` goes to the window
  under the cursor, so the parent form never sees it. Measured: **zero**
  hit-tests reached the form while a human dragged the edges.
- **Insetting the control fixes it.** With the form padded, the same build
  resized by dragging (confirmed by hand), the form owned all five probed
  border points, and the spike logged `first WM_NCHITTEST reached the form`.
- **`MinimumSize` is enforced and survives the subclass**, provided
  `WM_GETMINMAXINFO` chains to the original WndProc *before* overriding.
  Spike asked for 400×300 and got exactly 880×560. pywebview sets
  `MinimumSize` from `min_size` (`winforms.py:210`); `ui/window.py` does not
  currently pass it, so today it is the default 200×100.
- **Borderless maximize covers the taskbar unless clamped.** pywebview sets
  no `MaximumSize` and does not handle `WM_GETMINMAXINFO`. With the spike's
  clamp, maximize produced 1920×1032 on a 1920×1080 monitor with a 1920×1032
  work area.
- **DPI**: `__main__.set_dpi_awareness()` selects `PROCESS_SYSTEM_DPI_AWARE`
  (`__main__.py:112`), deliberately not Per-Monitor V2, and
  `packaging/uploader.spec` embeds no DPI manifest — that runtime call is the
  only source of awareness. Under system awareness `GetDpiForWindow` reports
  the system DPI, which is what pywebview's own `_scale` uses
  (`winforms.py:317-325`).
- **The window is already 13×35 px smaller than requested.** `create_window`
  asks for 1040×680; the spike measured 1027×645 every run. pywebview sets
  `Size` at `winforms.py:209` while the form still has its default sizable
  border, then switches to `FormBorderStyle.None` at `:269`, which preserves
  the *client* size. Pre-existing, unrelated to this change, but it means the
  constants in `ui/window.py` do not describe the window users actually get.
- **Settings cannot hold new keys implicitly.** `settings.save()` projects
  onto `DEFAULTS` (`settings.py:72`), and the comment at `:18-19` states
  anything undeclared is dropped on every write.
- **The band's colour will not match the title bar.** The form's `BackColor`
  is `background_color`, i.e. `--bg` `#0c0d10` (`winforms.py:292`,
  `ui/window.py:28`). The page body is the same `#0c0d10`, but the title bar
  is a gradient `#16181d → #101216` (`style.css:96`). So a band blends at the
  sides and bottom and is a visible strip above the title bar.
- **Tests stub pywebview.** `tests/test_window.py` injects a fake `webview`
  module and asserts the construction flags, including
  `frameless is True` / `easy_drag is False` (`:50-58`). Nothing native runs
  in CI, which is ubuntu-only (`ci.yml`).
- The smoke checklist already carries window items that become newly
  meaningful: title-bar drag and Windows snap (`docs/smoke-checklist.md:99`),
  and two "at the minimum window size/width" checks (`:135`, `:181`).

### Unresolved before implementation

`--pad 6` produced only a **3px inset per side** (form 1027×645, children
1021×639). The cause is not established, and it decides the band width. First
implementation step is a diagnostic: log `ClientRectangle`,
`DisplayRectangle`, `Padding`, `DeviceDpi`, and the WebView2 control's
`Bounds` immediately after assignment. Do not pick a shipping value before
that reads out.

## Decisions for review

### 1. Where the band goes, and what it costs (UX — highest risk)

The band is the only user-visible cost, and it is asymmetric: at the sides and
bottom it is `#0c0d10` against a `#0c0d10` page and should be invisible; at
the top it sits above a `#16181d` title bar and will read as a dark strip.

**Proposed:** pad all four sides. Accept the top strip.

The alternative — `Padding(n, 0, n, n)`, no top inset — keeps the title bar
flush but gives up top-edge resizing. That is a real loss: resizing from the
top is common, and its absence is the kind of asymmetry users notice without
being able to name.

This is the decision most worth overruling me on, and it wants eyes on a
screenshot rather than a paragraph. Both variants are one constant apart, so
build both and look before committing.

### 2. Where the native code lives (architecture)

**Proposed:** a new `ui/chrome.py` holding the ctypes subclass, with a single
entry point `enable_resize(window, border=..., pad=...)` that is a no-op
returning `False` off Windows.

`ui/window.py` stays what it is — flags, placement, and lifecycle, testable
against a stubbed `webview`. Putting `WNDPROC` and `MINMAXINFO` in it would
drag Win32 structures into the one module that currently has none, and
`tests/test_window.py` builds its whole fixture on that module importing
cleanly on Linux.

The guard mirrors `__main__.set_dpi_awareness()` and
`acquire_single_instance()`: a `sys.platform != "win32"` early return, and the
Win32 calls wrapped so a failure degrades rather than raises.

### 3. Hit-zone math as a pure function (interfaces / testability)

**Proposed:** `chrome.hit_code(rect, x, y, scale) -> int | None`, taking a
plain 4-tuple and returning an `HT*` constant or `None`, with no ctypes in its
signature.

This is the only part of the feature CI can actually cover. Ubuntu CI cannot
run WinForms, WebView2, or a message pump, so if the geometry lives inside the
WndProc callback it gets **zero** automated coverage. Pulled out, the corner
reach, the edge priority, and the DPI scaling are all exhaustively testable as
a table, matching how `tests/` already covers pure functions.

### 4. Failure handling (must not regress startup)

The spike established two ways this kills a process, and both must be handled
deliberately rather than by luck:

- The `WNDPROC` callback must be pinned in a module-global. A collected
  callback crashes at the next message, nowhere near the cause.
- Every exception inside the callback must be swallowed and logged, then the
  original proc called. An exception unwinding through the native message pump
  is fatal.

Plus, from the deadlock the spike actually hit: **the `Padding` assignment
must be marshalled onto the UI thread** via `Invoke`, exactly as pywebview
guards its own equivalents (`winforms.py:546`, `:597`). Assigning it from the
`shown` handler deadlocked the process into an unkillable-by-UI window.

If `SetWindowLongPtr` fails, log a warning and continue. A non-resizable
window is today's behaviour; a failed launch is a regression.

### 5. `min_size`, and the size constants

**Proposed:** pass `min_size` derived from the layout floor — the list grid
`34 + minmax(120,52ch) + 92 + 84 + 76 + 46` (`style.css:233`) plus the fixed
`320px` upload pane (`:376`) plus gaps and padding — rather than the 880×560
the spike used, which was an estimate.

Related but **proposed as out of scope**: the 13×35 px shortfall from
`winforms.py:209`. Correcting it changes the default window size for every
existing user, which is a visible change unrelated to resizing. Worth its own
issue; noted here so the constants are not silently trusted.

### 6. Maximize (scope)

The `WM_GETMINMAXINFO` clamp is needed regardless — once a window can be
resized, Aero Snap or a maximize path may become reachable, and covering the
taskbar is a defect. Whether to *also* add a maximize/restore button to the
title bar is a separate question; the API works and the spike confirmed it,
but it is a new control in an approved design.

**Proposed:** ship the clamp, defer the button.

### 7. Testing and verification

Automated coverage is limited to what ubuntu CI can run, and the plan should
not pretend otherwise:

- `hit_code` table tests: all eight zones, the corner reach, the None case in
  the middle, and scaling at 1.0 / 1.5 / 2.0.
- `chrome.enable_resize` returns `False` and touches nothing when
  `sys.platform != "win32"`.
- `tests/test_window.py` extended for the new `min_size` kwarg, alongside the
  existing `frameless` / `easy_drag` assertions.

Everything native stays manual, via the spike's own checklist.

## Alternatives and tradeoffs

| Option | Why not |
|---|---|
| Plain `WM_NCHITTEST` subclass, no inset | **Measured to fail.** Zero hit-tests reach the form; the WebView2 child covers every border pixel. |
| `WS_THICKFRAME` via `GWL_STYLE` | Leaves an unpainted non-client border without `WM_NCCALCSIZE` handling, and `toggle_fullscreen` reassigns `FormBorderStyle` (`winforms.py:558`, `:577`), which can recreate the handle and drop the bit. |
| `WM_NCCALCSIZE` custom chrome | The rigorous answer, and it would likely restore Aero Snap too. Rejected as disproportionate for now; revisit if the band proves unacceptable. |
| Drop `frameless`, use the OS title bar | Simplest and most robust, but discards the approved custom title bar. |
| JS resize grips over the bridge | Every mousemove becomes a `js_bridge_call`: a new `Thread` plus an `evaluate_js` round-trip per event (`util.py:247-267`). The synchronous fast path exists only for `pywebviewMoveWindow` (`util.py:280`). |
| `Form.MaximumSize` for the taskbar | A single global cap; it would also stop the window growing on a larger second monitor. `WM_GETMINMAXINFO` is per-monitor and evaluated at maximize time. |

## Ordered implementation steps

1. **Diagnose the 6→3 inset** (see above). Everything downstream depends on
   the number.
2. Add `ui/chrome.py`: constants, `hit_code` as a pure function, the
   `MINMAXINFO`/`MONITORINFO` structures, the pinned-callback subclass, the
   work-area clamp, and `enable_resize()` with its platform guard.
3. Wire it into `ui/window.py`: pass `min_size`, register a `shown` handler
   that applies the `Padding` via `Invoke` and then calls `enable_resize`.
4. Tests: the `hit_code` table, the off-Windows no-op, the new `min_size`
   assertion.
5. Docs: add the resize, min-size, and maximize-vs-taskbar checks to
   `docs/smoke-checklist.md`, near the existing title-bar drag item.
6. Verify on Windows with a real build; run the spike's checklist items that
   remain open (Aero Snap, edge double-click, 150%/175%, second monitor).

## Adaptation points

- **If the inset diagnostic shows the padding is scaled**, the band constant
  becomes DPI-dependent and step 2 needs the scale factor threaded through.
- **If the top strip looks wrong**, fall back to decision 1's asymmetric
  variant and accept losing top-edge resize.
- **If Aero Snap turns out to be dead** and that matters, the
  `WM_NCCALCSIZE` approach comes back on the table — it is the only rejected
  option that would restore it.
- **If `Padding` proves unreliable**, the fallback is to size and position the
  WebView2 control directly instead of relying on `DisplayRectangle`.

## Explicit exclusions

- Persisting window geometry across restarts. It would need new `DEFAULTS`
  keys (`settings.py:11-30`) and a migration story, and it is a separate
  feature from being able to resize at all.
- Correcting the 13×35 px size shortfall (decision 5).
- A maximize/restore button (decision 6).
- Per-Monitor V2 DPI awareness and `WM_DPICHANGED` handling. `__main__.py:100`
  documents system-awareness as a deliberate choice; changing it is a much
  larger blast radius than this feature.
- Any change to `packaging/`. No new dependency — `ctypes` is stdlib — so
  `uploader.spec` and the installer are untouched.
