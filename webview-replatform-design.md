# Replatform the UI onto pywebview + WebView2

**Date:** 2026-08-21
**Status:** Design approved; implementation plan not yet written
**Supersedes:** `ui-refresh-design.md`, `ui-layout-design.md` (and their plans) as the
active UI direction. Those documents describe successive attempts to make Tkinter
look acceptable; this one concludes that goal is unreachable and replaces it.

## Problem

FlyGD Wingman looks amateur, and three prior theming passes have not fixed it.
Inspection of `settings.png` and `newest-version.png` separates the causes into
two groups:

**Layout and typography discipline** — four competing type sizes in one dialog,
label columns that do not align across groups, fields and their Browse/Detect
buttons off a shared baseline, a duplicated webhook URL, a status rendered as an
oversized button. None of this is Tkinter's fault; the same dialog built the same
way would look equally bad in any toolkit.

**A genuine framework ceiling** — no corner radius, no shadows, no glow, no
custom-drawn scrollbar, no custom window chrome, weak hi-DPI handling, and no
motion. `app.py` currently generates checkbox images with Pillow because ttk
cannot draw a checkbox matching the theme, and carries `dpi_scale`, `spacing`,
`row_height`, and `apply_typography` helpers that exist purely to compensate for
Tk's layout model.

The chosen visual direction (below) requires the second group. Continuing to
theme Tkinter cannot deliver it.

## Decision

Replatform the UI onto **pywebview 6.x driving WebView2**, with the page written
in plain HTML/CSS/JS and no frontend build step. Python retains the tray icon,
file watching, ffmpeg work, OAuth, and uploads.

Rejected alternatives, with the reason each lost:

| Option | Why not |
|---|---|
| **PySide6 / Qt Widgets** | The serious contender. Loses on bundle size (would *add* 40–70 MB where the whole webview bundle measured 26 MB), on fidelity (QSS is not CSS; the approved design uses effects QSS reaches only via `QGraphicsDropShadowEffect` and subclassed `paintEvent`s), and on the fact that the packaging risk that justified it was falsified by spike Q4. Its one surviving advantage is no WebView2 dependency. |
| **PySide6 / QML** | Strongest rendering, but QML is a second language to maintain solo for a list-and-form app. Payoff does not justify it. |
| **CustomTkinter** | Buys corner radius; still cannot do glow, shadows, or custom chrome. The same ceiling again in six months. |
| **Flet** | Good output, immature desktop packaging. Not worth betting a signed-installer pipeline on. |
| **Stay on Tkinter, design harder** | Fixes the first group of problems only. The approved direction needs the second. |

## Visual direction

"Direction B", chosen from two full-fidelity mockups of the Settings dialog.

Near-black ground; the existing red logo promoted to the accent colour; uppercase
letter-spaced section labels each preceded by a short brand rule; monospace for
paths, URLs, and other machine text; a soft glow on the primary action and on
status indicators; a custom title bar replacing the OS one.

Tokens (as CSS custom properties, the successor to `theme.py`'s `TOKENS` dict):

| Token | Value | Use |
|---|---|---|
| `--bg` | `#0c0d10` | Window ground |
| `--panel` | `#14161b` | Group/card surface |
| `--panel-border` | `#1e2128` | Card outline |
| `--field` | `#0a0b0e` | Input ground |
| `--field-border` | `#23262e` | Input outline |
| `--text` | `#e8eaed` | Primary text |
| `--text-dim` | `#9aa2b1` | Labels |
| `--text-faint` | `#6f7681` | Hints, secondary |
| `--brand` / `--brand-deep` | `#ff5a4d` / `#c81e12` | Accent, gradients, glow |
| `--ok` / `--warn` / `--err` | `#4ade80` / `#d29922` / `#f85149` | Status, carried from `theme.py` |

Type: one 13px body size, 12px for monospace machine text, 10.5px uppercase
tracked `.14em` for section labels. Three sizes total, replacing today's four
uncoordinated ones.

**Light mode is dropped.** `theme.py` currently detects `AppsUseLightTheme` and
re-themes live. Direction B is a dark design; a light variant would be a second
design to maintain with no evidence anyone wants it. The registry detection and
the live-switch machinery are deleted rather than ported. If demand appears, CSS
custom properties make it far cheaper to add later than it is today.

## Evidence: the spike

A throwaway spike (`C:\Users\tng\wingman-spike`, not merged) tested the risky
parts on Windows 11 with WebView2 Runtime 151.0.4129.93.

| # | Question | Result |
|---|---|---|
| Q1 | WebView2 renders direction B faithfully | Pass |
| Q2 | Frameless window, custom draggable title bar | Pass — drag and close both work |
| Q3a | Page → Python → native folder dialog → page | Pass |
| Q3b | Worker thread streams progress; window stays responsive | Pass — draggable mid-upload |
| Q4 | PyInstaller freeze and run | Pass, first attempt. 26 MB one-folder bundle. One `hiddenimports` entry (`webview.platforms.edgechromium`); no custom hooks |
| Q5 | `pystray` thread + `webview.start()` on main thread | Pass — the arrangement `__main__.py` already uses |
| Q6 | Tray hide/show/quit | **Partial.** Hide passes; `window.destroy()` called directly from the pystray thread passes. Reopening via `show()` from the tray thread was never exercised — see Open items |

Q4 was predicted most likely to fail and did not fight at all. That result is what
moved the recommendation from Qt to the webview.

### Constraints the spike discovered

These are load-bearing and easy to rediscover painfully:

1. **The `js_api` object must expose methods only.** pywebview builds its JS proxy
   by walking the object's public attributes. A public attribute holding a
   `webview.Window` or `pystray.Icon` sends that walk into the WinForms native
   object, where `Rectangle.Empty` returns itself; it recurses until
   `RecursionError` terminates the process. Observed as a hard crash roughly eight
   seconds after launch. Every non-method attribute must be underscore-prefixed.
2. **Frameless windows get no sensible default placement.** Pass explicit `x`/`y`;
   the spike window opened somewhere not visible on the primary screen.
3. **Pin pywebview.** 6.x has live API churn — `FOLDER_DIALOG` is already
   deprecated in favour of `FileDialog.FOLDER`.
4. **Suppress pywebview's native-object logging.** It writes an unbounded property
   walk to stderr. Harmless in a windowed build, but it would swamp any log file
   stderr is redirected into.

## Architecture

### Module layout

Unchanged, Tk-free, and untouched by this work — `uploader`, `watcher`, `stitch`,
`combatlog`, `discord`, `library`, `durations`, `obsconfig`, `settings`, `paths`,
`credentials` (1,877 lines). Their tests are unaffected.

Replaced:

| Today | Becomes |
|---|---|
| `app.py` (1,728 lines) | `ui/api.py` — the `js_api` bridge class; `ui/window.py` — window construction and lifecycle |
| `settingsui.py` (493) | Folded into the same bridge; Settings becomes a route in the page, not a second Tk toplevel |
| `theme.py` (277) | Deleted. CSS custom properties replace the token table; light-mode detection is dropped |
| `__main__.py` (313) | Tray and startup ordering survive, but the Tk event loop does not — `root.after()` currently drives the watcher poll, tray dispatch, and first-run folder selection. See **Process lifecycle and scheduling** |
| — | `web/` — `index.html`, `settings.html`, `style.css`, `app.js`. No build step, no bundler, no Node in the release pipeline |

The Pillow-generated checkbox images, `dpi_scale`, `spacing`, `row_height`,
`apply_typography`, `configure_tree_columns`, `_configure_tree_tags`,
`_apply_zebra_tags`, `_row_tags`, and `_apply_desc_colors` are all deleted rather
than ported. CSS covers every one of them.

### Process lifecycle and scheduling

Tk's event loop is doing more work than "UI" today, and pywebview has no
equivalent of `root.after()`. Everything below must be explicitly rehomed; it is
not carried by `webview.start()`.

| Responsibility | Today | Becomes |
|---|---|---|
| Watcher poll every `POLL_SECONDS` | `root.after(int(POLL_SECONDS*1000), poll)`, self-rescheduling in a `finally` (`__main__.py:302`, `:307`) | A dedicated daemon `threading.Timer` loop owned by a `Scheduler` object, preserving the always-reschedule-on-error guarantee. The poll body runs off the UI thread and reaches the page only through `_push()` |
| Deferred refresh during upload | `refresh_deferred` flag read on the next `after()` tick | Same flag, read on the next scheduler tick. Behaviour unchanged |
| Tray open / quit | `root.after(0, window.show)` / `root.after(0, root.quit)` (`__main__.py:229`) | Direct `window.show()` / `window.destroy()` from the pystray thread. Spike Q6 proved cross-thread `destroy()` works; `show()` is the one path still unverified (see Risks) |
| First-run recording-folder prompt | `resolve_recording_dir()` via `filedialog.askdirectory`, requiring a withdrawn Tk root to exist *before* any window (`__main__.py:135`, `:195`) | **Needs a real answer, not a port.** pywebview's `create_file_dialog` is a method on a window, so no dialog exists before `webview.start()`. Resolution: create the window first, and run first-run resolution as the page's own first screen — a dedicated "choose your recording folder" route that calls `pick_folder`. This changes first-run UX from a bare OS dialog to an in-app screen, which is an improvement, but it is a behaviour change and is called out as such |
| Shutdown | `root.mainloop()` returns, then `icon.stop()` | `webview.start()` returns, then `icon.stop()`. Same shape, verified by spike Q5/Q6 |

Startup ordering therefore becomes: load settings → build tray → start tray
thread → create window → `webview.start()` → page requests state → first-run
folder resolution if needed → watcher scheduler starts.

### The bridge

One rule carries over from the existing `_ui()` chokepoint: **worker threads never
touch the UI directly.** What does *not* carry over is the mechanism.

`_ui()` marshals **widget method calls**, not semantic events — `self._ui(self.progress.config,
{"mode": "indeterminate"})`, `self._ui(self.progress.start, 12)`,
`self._ui(self.retry_btn.state, ["disabled"])`, `self._ui(messagebox.showerror, ...)`
(`app.py:1609`–`:1661`). Those call sites know the widget API, so **the workers do
change**: each becomes a semantic `_push()` of one of the messages below. The
surface is bounded — roughly five call sites across `_upload_worker`,
`_combat_log_worker`, and `_retry_worker` — but it is real work and was previously
understated in this document.

`settingsui.py`'s OAuth polling marshals through `win.after()` rather than `_ui()`
(`settingsui.py:396`) and is rewritten the same way: a worker plus `onStatus` and
`onAuthState` pushes, with no polling loop at all.

Python → page (fire-and-forget):

| Message | Payload | Replaces |
|---|---|---|
| `onRows` | full row list: **row id**, name, date, size, duration, link, **preselected flag** | `refresh()` / `refresh(preselect=...)` |
| `onDuration` | row id + duration + definitive flag | `_apply_duration` (streams in from the ffprobe queue) |
| `onProgress` | mode (`determinate`\|`indeterminate`), pct, text, severity kind | `on_progress`, `on_retry`, and the `progress.config(mode=…)` / `progress.start` / `progress.stop` transitions around stitching |
| `onStatus` | text, severity kind | the status label |
| `onRetryAvailable` | bool | `retry_btn.state(["disabled"])` / `(["!disabled"])` |
| `onLink` | row id + video id | `_set_link` |
| `onSettings` | current settings dict, plus detected-folder suggestions | settings load/save round-trip |
| `onAuthState` | connected bool + message | `_refresh_auth_label` |
| `onDialog` | kind (`info`\|`error`\|`warning`\|`confirm`), title, body, optional request id | `messagebox.showinfo` / `showerror` / `showwarning` / `askyesno` |

`onDialog` is the one genuinely new concept. Modal dialogs are currently native Tk
message boxes called from workers; they become in-page modals. `confirm` carries a
request id and the page answers with `dialog_response(id, ok)` — the only
request/response pair in an otherwise fire-and-forget protocol. **The delete
confirmation (`app.py:1393`) and the no-selection warning (`app.py:1390`) are
required behaviour and must survive**; they were missing from an earlier draft of
this protocol.

Page → Python (invoked via `pywebview.api.*`):

`list_rows`, `delete_selected(ids)`, `start_upload(title, description, privacy,
category, stitch, ids)`, `upload_combat_logs(ids)`, `retry()`, `open_path(id)`,
`copy_path(id)`, `pick_folder(which)`, `detect_folder(which)`, `save_settings(dict)`,
`connect_google()`, `dialog_response(id, ok)`, `minimize()`, `close()`.

`detect_folder(which)` is separate from `pick_folder` and exists for both folders:
Settings has distinct Detect actions for the recording directory (via OBS's own
config) and the EVE gamelogs directory (`settingsui.py:228`, `:240`, `:263`, `:293`).

`save_settings` **must rebind the live watcher** when the recording directory
changes, mirroring `on_settings_saved` today (`__main__.py:215`). Persisting the
setting alone leaves the watcher pointed at the old folder.

#### Row identity

Rows cross the boundary as **opaque ids**, not filesystem paths, and every method
above resolves an id against the API's current server-side row snapshot. This is
design hygiene rather than a security boundary — the page is local, bundled in the
installer, loads no remote content, and is exactly as trusted as the Python — but
it preserves a property the Tk version gets for free: today `_delete_selected`
operates on `self._chosen()`, which can only contain objects from the current
discovered list (`app.py:1387`, `:1398`). Ids keep deletion, opening, and upload
targeting bounded to rows the backend actually knows about, and make a stale page
after a refresh fail cleanly instead of acting on a path that has since changed
meaning.

Deliberately **not** crossing the boundary, because they become pure client state:
row selection *state* (though the initial preselect comes from `onRows`), sort
column and direction, zebra striping, column widths, checkbox rendering, and theme
application.

Severity `kind` values stay `FG` / `SUCCESS` / `WARNING` / `ERROR`, matching
today's `_status_kind`, so the semantics carry over even though the colours move
to CSS.

### Interaction behaviour to preserve

These are deliberate behaviours in the current UI, not accidents, and each must be
reimplemented rather than quietly dropped:

- **Keyboard selection.** Arrow keys move focus; Space toggles the focused row's
  checkbox; focus is established on first entry into the list (`app.py:917`, `:934`).
- **Context menu** on a row, offering copy-path and open (`app.py:956`).
- **Double-click opens the recording without changing the checkbox selection**
  (`app.py:988`) — clicking a row's checkbox and double-clicking its name are
  distinct gestures and must stay distinct.
- **Row focus** is a real concept, not just styling; it is what Space acts on.

All four appear in the smoke checklist (see Testing), since no automated test will
cover them under the agreed approach.

### Main window

Specified here; to be iterated during implementation against the running app.

Two panes, preserving today's split. Left: the recording list. Right: the upload
panel. A status strip spans the bottom.

The list is an HTML table styled with CSS grid columns: checkbox, filename, date,
size, length, link. Header row is sticky, click-to-sort, with the active column
showing direction. Rows are 1px-separated rather than zebra-striped — with a card
surface and adequate row height, zebra striping is compensation for a flat list
and is not needed. Selected rows take a left brand rule and a slightly lifted
surface. Uploaded rows keep the external-link glyph, which becomes a real
hover-highlighted control rather than a text arrow.

The right pane keeps Title, Description, the stitch checkbox, the selection
summary line, and the two action buttons. The Description box is given a sensible
height instead of consuming all vertical space — today it reads as an empty void.
`Upload Selected` is the only brand-accent control on the screen; `Upload combat
logs` is secondary. `Retry` stays disabled-by-default in place.

The bottom strip carries the status text and the progress bar. `Settings` moves
out of the bottom-left corner to a gear control in the custom title bar, where a
window-level action belongs.

Scrollbars are CSS-styled throughout — the classic Windows scrollbar in
`newest-version.png` is one of the most visible tells and disappears for free.

### Settings

As mocked and approved: grouped cards, single aligned label column, fields and
their buttons sharing a baseline, "Connected" as a status pill rather than a
button, the webhook URL shown once, and the two folder pickers grouped together.

Rendered in the same window as a route rather than a separate OS window. This
removes a whole second toplevel's worth of lifecycle code, and the OAuth polling
in `settingsui.py` becomes an ordinary worker + `onStatus` push.

## Compatibility

Explicitly unchanged: the `%LOCALAPPDATA%` state directory, the settings file
format and location, the credentials file, the durations cache, the distribution
name `obs-youtube-uploader`, the PyInstaller entry point, the Inno `AppId`, and
the release workflow's credential-injection step. This is a UI replatform; an
existing installation must upgrade in place with its settings and sign-in intact.

No settings migration is required — no setting changes meaning. The dropped light
theme was never persisted; it was detected from the registry at runtime.

One behaviour change is deliberate and called out rather than buried: **first-run
recording-folder selection moves from a pre-window OS dialog to an in-app screen**
(see Process lifecycle and scheduling, and Risks item 6). Existing installations
already have the setting persisted and never see it.

## Packaging

- `uploader.spec`: drop the sv-ttk `collect_data_files` and the `PIL._tkinter_finder`
  hidden import; add `webview.platforms.edgechromium` and the `web/` directory as
  `datas`. Keep one-folder, keep the ffmpeg binaries, keep `pystray._win32`.
- `pyproject.toml`: remove `sv-ttk` (`pyproject.toml:11`); add `pywebview`
  **pinned** to a known-good 6.x — the spike ran on 6.2.1, and 6.x has live API
  churn (`FOLDER_DIALOG` is already deprecated). Pillow stays; the tray icon needs it.
- `build.yml`: the runtime-dependency import check imports `sv_ttk` explicitly
  (`build.yml:66`) — swap it for `webview`. Replace the "Verify sv-ttk theme data
  is bundled" step (`build.yml:119`) with the equivalent assertion for `web/`. The
  reasoning in that step's comment still applies verbatim: PyInstaller exits 0 when
  a `datas` entry resolves to nothing, and the spike confirmed that trap is live.
- `release.yml`: **has no sv-ttk assertion to replace** — its import check simply
  omits `sv_ttk` today (`release.yml:65`). Add `webview` to that check, and add a
  `web/` bundle assertion mirroring `build.yml`'s, so the release path is not
  weaker than the build path.
- `installer.iss`: **add the WebView2 Evergreen bootstrapper.** The installer
  currently packages only the application tree (`installer.iss:41`), so this needs
  a full definition, not a mention: how the bootstrapper is acquired (bundled at
  build time versus downloaded at install time), how its integrity is verified, how
  an existing runtime is detected, how it is invoked silently, and what happens
  when it fails or the machine is offline. This is the single genuinely new piece
  of installer work and the largest residual risk in the whole plan.

Expected bundle size is roughly flat: the spike's webview stack measured 26 MB
total against a current bundle dominated by ffmpeg.

## Testing

Agreed approach: **bridge-level tests plus an extended manual smoke checklist.**

- `tests/test_api.py` (new): exercise the `Api` class headlessly with a fake
  window object, asserting the messages it emits and the calls it accepts. Runs on
  `ubuntu-latest` with no webview installed. CI configuration is otherwise unchanged.
- Deleted with the widgets they assert on: `test_app_layout`, `test_theme`,
  `test_typography`, `test_treeview_columns`, `test_row_click`, and
  `test_app_selection_summary` (it drives a real `UploaderWindow` through the
  `make_window` fixture and asserts on `selection_summary.cget("text")`).
- **`test_app.py`'s `format_selection_summary` cases survive untouched.** That
  function is pure and already has direct coverage there, independent of any
  widget; it moves to the bridge module as-is. The behaviour
  `test_app_selection_summary` protects — that a landing ffprobe result refreshes
  a summary showing a partial "+" total — is a real regression guard and must be
  re-expressed as a bridge test asserting the `onDuration` handler recomputes and
  re-pushes the summary.
- `docs/smoke-checklist.md`: extend to cover what automated tests no longer reach —
  tray hide/show/quit, the custom title bar drag, native folder dialogs, sort and
  selection behaviour, progress rendering during a real upload, and first-run on a
  machine without the WebView2 runtime. Add explicitly, because they are deliberate
  behaviours with no automated coverage under this approach: **arrow-key focus and
  Space-to-toggle, the row context menu, double-click-to-open leaving the checkbox
  selection unchanged, the delete confirmation dialog, and the indeterminate
  progress bar during a stitch.**

No Playwright. Real UI regression coverage was considered and rejected: the cost
of a browser toolchain falls entirely on a solo maintainer, and the riskiest logic
is already covered by tests that survive the port untouched.

## Risks and open items

1. **WebView2 Runtime on a clean machine — untested.** The spike ran on a host
   that already had it. The installer bootstrapper addresses this, but it cannot
   be validated on the development machine. Highest-priority verification during
   implementation; a clean VM is the only honest test.
2. **`show()` from the pystray thread — untested.** Hide and cross-thread
   `destroy()` both pass, so this is the same category as operations already
   proven, but the tray is the app's primary entry point. Verify first, before
   anything is built on the assumption.
3. **pywebview is a small project.** Frameless-window support on Windows is where
   its coverage is thinnest, and the `js_api` recursion crash is evidence of rough
   edges. Pin the version; treat upgrades as changes requiring a smoke pass.
4. **Antivirus and SmartScreen behaviour may shift** now that a browser engine is
   in the bundle. The installer is already unsigned and already warns; this could
   make it worse. Watch after the first release.
5. **No incremental path.** The Tk and webview UIs cannot run side by side, so this
   lands as one change. Mitigation is ordering: bridge and page built and driven
   against real data before the Tk UI is removed.
6. **First-run UX changes.** Today a bare OS folder dialog appears before any
   window exists, parented to a withdrawn Tk root. Under pywebview no dialog can
   exist before `webview.start()`, so first-run folder selection becomes an in-app
   screen. Arguably better, but it is a deliberate behaviour change to an
   already-shipped flow, not a like-for-like port.
7. **The worker rewrite is larger than first assessed.** `_ui()` marshals widget
   method calls rather than semantic events, so `_upload_worker`,
   `_combat_log_worker`, `_retry_worker`, and `settingsui.py`'s OAuth polling all
   need reworking to emit bridge messages. Bounded — roughly five call sites — but
   it is not the no-op an earlier draft of this document claimed.

## Out of scope

Light mode. Playwright or any browser test toolchain. Any frontend build step,
bundler, or framework. Cross-platform support — this stays Windows-only. Code
signing. Changes to upload, stitching, combat-log, or Discord behaviour. Any
change to the settings file format or state paths.
