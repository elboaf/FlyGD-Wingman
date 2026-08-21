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

**2.2.0 has since fixed part of this**, and the fix is evidence for the split
rather than against it. It built a real three-step type scale, masked the webhook,
and made the account control track state — all inside Tkinter, all effective,
because none of it was ever framework-bound. What 2.2.0 could not touch is the
second group below. That is the line this document is drawn along: everything
fixable in Tk is being fixed in Tk; the replatform is for what is not.

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

Type: 2.2.0 built a three-step scale from sv-ttk's rescaled font — headings 1.2×,
body, muted text and column headers 0.875× — and that **structure is adopted, not
replaced**; only its implementation moves from Tk font objects to CSS. Concretely:
13px body, 15.5px headings, 11.5px muted text and column headers, 12px monospace
for machine text, and 10.5px uppercase tracked `.14em` for the section labels
direction B adds.

The deliberate ordering carries over intact: **column headers sit below body size,
not above.** They label the data; they are not the data. A port that "fixes" that
by making headers larger would be undoing a considered decision.

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

Figures below are against **2.2.0** (`d8f79ff`), which this document was rebased
onto after it was first written. See **What 2.2.0 changed** for why that matters.

Unchanged, Tk-free, and untouched by this work — `uploader`, `watcher`, `stitch`,
`combatlog`, `discord`, `library`, `durations`, `obsconfig`, `settings`, `paths`,
`credentials` (1,978 lines). Their tests are unaffected.

Replaced:

| Today | Becomes |
|---|---|
| `app.py` (2,120 lines) | `ui/api.py` — the `js_api` bridge class; `ui/window.py` — window construction and lifecycle |
| `settingsui.py` (566) | Folded into the same bridge; Settings becomes a route in the page, not a second Tk toplevel |
| `theme.py` (277) | Deleted. CSS custom properties replace the token table; light-mode detection is dropped |
| `tooltip.py` (120) | Machinery deleted — a borderless Tk `Toplevel` is a CSS tooltip. **`_CELL_HELP`'s copy is kept verbatim**; it is a text decision with its own passing test, not widget code |
| `__main__.py` (313) | Tray and startup ordering survive, but the Tk event loop does not — `root.after()` currently drives the watcher poll, tray dispatch, and first-run folder selection. See **Process lifecycle and scheduling** |
| — | `web/` — `index.html`, `settings.html`, `style.css`, `app.js`. No build step, no bundler, no Node in the release pipeline |

The Pillow-generated checkbox images, `dpi_scale`, `spacing`, `row_height`,
`apply_typography`, `configure_tree_columns`, `_configure_tree_tags`,
`_apply_zebra_tags`, `_row_tags`, and `_apply_desc_colors` are all deleted rather
than ported. CSS covers every one of them.

### What 2.2.0 changed

This design was drafted against 2.1.0 and rebased onto 2.2.0, which landed a
design-critique pass over both windows (`65b2b4d`). It moves the target in five
ways, all folded into the sections below:

1. **Upload confirmation.** Publishing now confirms first, naming the channel,
   privacy, the exact titles including `build_body`'s `(n/total)` numbering, and
   the totals (`_start_upload`, `format_upload_confirm`). This is a second required
   `confirm` dialog alongside delete, and it is the more important of the two —
   uploading is the app's only irreversible action.
2. **Upload destination.** `uploader.upload()` gained an `on_response` callback and
   `channel_of()` reads `snippet.channelTitle` from it; the channel is persisted as
   `channel_id`/`channel_title` and displayed above Upload Selected. That is a new
   worker callback crossing the bridge and a new piece of always-visible state.
3. **The webhook is masked.** It is a credential, and it is now rendered with a
   bullet mask plus a Show toggle, with `webhook_status()` describing what is stored
   and reporting parse errors. **The approved settings mockup shows it in
   cleartext monospace — that is a regression this port must not reintroduce.**
4. **The account button tracks state** and is disabled during transient states so a
   second press cannot start a second OAuth flow. `onAuthState` must carry enough
   for that, not just connected/disconnected.
5. **A type scale now exists**, derived from sv-ttk's rescaled font: headings 1.2×,
   body, muted text and column headers 0.875×. Column headers sit *below* body
   deliberately — they label the data, they are not the data.

It also established a convention worth adopting rather than merely preserving:
**every user-visible string is a pure module-level function**, following
`format_selection_summary`, because copy is what regresses and widgets are the
layer with no test harness. That convention is what makes this port cheap — those
functions and their tests cross unchanged, and the port should extend it rather
than inline strings into HTML.

### Process lifecycle and scheduling

Tk's event loop is doing more work than "UI" today, and pywebview has no
equivalent of `root.after()`. Everything below must be explicitly rehomed; it is
not carried by `webview.start()`.

| Responsibility | Today | Becomes |
|---|---|---|
| Watcher poll every `POLL_SECONDS` | `root.after(int(POLL_SECONDS*1000), poll)`, self-rescheduling in a `finally` (`__main__.py`, the `poll()` loop) | A dedicated daemon `threading.Timer` loop owned by a `Scheduler` object, preserving the always-reschedule-on-error guarantee. The poll body runs off the UI thread and reaches the page only through `_push()` |
| Deferred refresh during upload | `refresh_deferred` flag read on the next `after()` tick | Same flag, read on the next scheduler tick. Behaviour unchanged |
| Tray open / quit | `root.after(0, window.show)` / `root.after(0, root.quit)` (`__main__.py`, `build_tray(on_open=..., on_quit=...)`) | Direct `window.show()` / `window.destroy()` from the pystray thread. Spike Q6 proved cross-thread `destroy()` works; `show()` is the one path still unverified (see Risks) |
| First-run recording-folder prompt | `resolve_recording_dir()` via `filedialog.askdirectory`, requiring a withdrawn Tk root to exist *before* any window (`__main__.py`, `resolve_recording_dir`) | **Needs a real answer, not a port.** pywebview's `create_file_dialog` is a method on a window, so no dialog exists before `webview.start()`. Resolution: create the window first, and run first-run resolution as the page's own first screen — a dedicated "choose your recording folder" route that calls `pick_folder`. This changes first-run UX from a bare OS dialog to an in-app screen, which is an improvement, but it is a behaviour change and is called out as such |
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
(`_upload_worker`). Those call sites know the widget API, so **the workers do
change**: each becomes a semantic `_push()` of one of the messages below. The
surface is bounded — roughly five call sites across `_upload_worker`,
`_combat_log_worker`, and `_retry_worker` — but it is real work and was previously
understated in this document.

`settingsui.py`'s OAuth polling marshals through `win.after()` rather than `_ui()`
(`settingsui.py`'s `_poll_auth`) and is rewritten the same way: a worker plus `onStatus` and
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
| `onChannel` | channel title + id | the upload-destination line above Upload Selected, learned via `uploader.upload(on_response=...)` and persisted as `channel_id`/`channel_title` |
| `onAuthState` | state (`disconnected`\|`connecting`\|`connected`\|`revoking`) + message | `_refresh_auth_label`, and the button-disabled-during-transient-states behaviour |
| `onDialog` | kind (`info`\|`error`\|`warning`\|`confirm`), title, body, optional request id | `messagebox.showinfo` / `showerror` / `showwarning` / `askyesno` |

`onDialog` is the one genuinely new concept. Modal dialogs are currently native Tk
message boxes called from workers; they become in-page modals. `confirm` carries a
request id and the page answers with `dialog_response(id, ok)` — the only
request/response pair in an otherwise fire-and-forget protocol.

**Three confirmations are required behaviour and must survive:**

| Confirmation | Source | Why it matters |
|---|---|---|
| **Upload** — names channel, privacy, exact `(n/total)` titles, totals | `_start_upload` → `format_upload_confirm` | Uploading is the app's only irreversible action. Added deliberately in 2.2.0; losing it would undo that work |
| **Delete** — lists the files, warns it cannot be undone | `_delete_selected`'s `askyesno` | Destroys local files |
| **No-selection / busy warnings** | `showwarning` in `_delete_selected`, `_start_upload`, `_start_combat_log_upload` | Several distinct messages, not one generic guard |

`format_upload_confirm` is already a pure module-level function and crosses the
bridge unchanged — it produces the body string, and `onDialog` merely carries it.

Page → Python (invoked via `pywebview.api.*`):

`list_rows`, `delete_selected(ids)`, `start_upload(title, description, privacy,
category, stitch, ids)`, `upload_combat_logs(ids)`, `retry()`, `open_path(id)`,
`copy_path(id)`, `pick_folder(which)`, `detect_folder(which)`, `save_settings(dict)`,
`connect_google()`, `dialog_response(id, ok)`, `minimize()`, `close()`.

`detect_folder(which)` is separate from `pick_folder` and exists for both folders:
Settings has distinct Detect actions for the recording directory (via OBS's own
config) and the EVE gamelogs directory (`settingsui.py`'s Detect handlers).

`save_settings` **must rebind the live watcher** when the recording directory
changes, mirroring `on_settings_saved` today (`__main__.py`'s `on_settings_saved`). Persisting the
setting alone leaves the watcher pointed at the old folder.

#### Row identity

Rows cross the boundary as **opaque ids**, not filesystem paths, and every method
above resolves an id against the API's current server-side row snapshot. This is
design hygiene rather than a security boundary — the page is local, bundled in the
installer, loads no remote content, and is exactly as trusted as the Python — but
it preserves a property the Tk version gets for free: today `_delete_selected`
operates on `self._chosen()`, which can only contain objects from the current
discovered list (`_delete_selected` via `_chosen()`). Ids keep deletion, opening, and upload
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
  checkbox; focus is established on first entry into the list (`_on_tree_space`, `_ensure_focus_item`).
- **Context menu** on a row, offering copy-path and open (`_build_context_menu`).
- **Double-click opens the recording without changing the checkbox selection**
  (`_on_row_double_click`) — clicking a row's checkbox and double-clicking its name are
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

**Two corrections to the approved mockup**, both from behaviour 2.2.0 added after
it was drawn:

- **The webhook must be masked**, with a Show toggle, and `webhook_status()`'s line
  underneath describing what is stored — including reporting a parse error rather
  than calling an invalid URL "not configured". The mockup renders the full webhook
  in cleartext monospace, which was correct against 2.1.0 and is a credential leak
  against 2.2.0. Mask by default; the Show toggle reveals.
- **The account control tracks state.** It is not a permanently-labelled "Connect
  Google Account" button; it reflects disconnected/connecting/connected/revoking
  and is disabled during the transient states so a second press cannot start a
  second OAuth flow. The status pill and the button are two views of one state, fed
  by `onAuthState`.

Rendered in the same window as a route rather than a separate OS window. This
removes a whole second toplevel's worth of lifecycle code, and the OAuth polling
in `settingsui.py` becomes an ordinary worker + `onAuthState` push with no polling
loop at all.

## Compatibility

Explicitly unchanged: the `%LOCALAPPDATA%` state directory, the settings file
format and location, the credentials file, the durations cache, the distribution
name `obs-youtube-uploader`, the PyInstaller entry point, the Inno `AppId`, and
the release workflow's credential-injection step. This is a UI replatform; an
existing installation must upgrade in place with its settings and sign-in intact.

No settings migration is required — no setting changes meaning. The dropped light
theme was never persisted; it was detected from the registry at runtime. The
`channel_id`/`channel_title` keys 2.2.0 added are read and displayed unchanged,
including `settings.py`'s coercion of a non-string from a hand-edited file to `""`
— that guard exists because both values reach a label, and they still do.

One behaviour change is deliberate and called out rather than buried: **first-run
recording-folder selection moves from a pre-window OS dialog to an in-app screen**
(see Process lifecycle and scheduling, and Risks item 6). Existing installations
already have the setting persisted and never see it.

## Packaging

- `uploader.spec`: drop the sv-ttk `collect_data_files` and the `PIL._tkinter_finder`
  hidden import; add `webview.platforms.edgechromium` and the `web/` directory as
  `datas`. Keep one-folder, keep the ffmpeg binaries, keep `pystray._win32`.
- `pyproject.toml`: remove `sv-ttk` (`pyproject.toml`'s dependency list); add `pywebview`
  **pinned** to a known-good 6.x — the spike ran on 6.2.1, and 6.x has live API
  churn (`FOLDER_DIALOG` is already deprecated). Pillow stays; the tray icon needs it.
- `build.yml`: the runtime-dependency import check imports `sv_ttk` explicitly
  (`build.yml`'s runtime-dependency import check) — swap it for `webview`. Replace the "Verify sv-ttk theme data
  is bundled" step (the "Verify sv-ttk theme data is bundled" step) with the equivalent assertion for `web/`. The
  reasoning in that step's comment still applies verbatim: PyInstaller exits 0 when
  a `datas` entry resolves to nothing, and the spike confirmed that trap is live.
- `release.yml`: **has no sv-ttk assertion to replace** — its import check simply
  omits `sv_ttk` today (its runtime-dependency import check). Add `webview` to that check, and add a
  `web/` bundle assertion mirroring `build.yml`'s, so the release path is not
  weaker than the build path.
- `installer.iss`: **add the WebView2 Evergreen bootstrapper.** The installer
  currently packages only the application tree (`installer.iss`'s `[Files]` section), so this needs
  a full definition, not a mention: how the bootstrapper is acquired (bundled at
  build time versus downloaded at install time), how its integrity is verified, how
  an existing runtime is detected, how it is invoked silently, and what happens
  when it fails or the machine is offline. This is the single genuinely new piece
  of installer work and the largest residual risk in the whole plan.

Expected bundle size is roughly flat: the spike's webview stack measured 26 MB
total against a current bundle dominated by ffmpeg.

## Testing

Agreed approach: **bridge-level tests plus an extended manual smoke checklist.**

The suite is 476 tests as of 2.2.0. Its structure is unusually favourable here,
because 2.2.0 made copy a layer of pure module-level functions: **the tests that
cover what the UI *says* are widget-free and cross the port untouched, and only the
tests that cover how Tk *renders* it are lost.**

Survive unchanged (pure, no widgets):

- `test_app.py`'s `format_selection_summary` cases
- `test_app_upload_copy.py` — the upload-confirmation body, including `(n/total)` titles
- `test_settingsui_copy.py` — `webhook_status()` and account-state strings
- `test_tooltip.py` — the `_CELL_HELP` text decisions
- `test_uploader.py`, `test_settings.py`, and every non-UI module's tests

Deleted with the widgets they assert on:

- `test_app_layout`, `test_theme`, `test_treeview_columns`, `test_row_click`
- `test_typography` — asserts Tk font objects; the *scale* survives, its
  implementation does not
- `test_app_last_upload` — drives a real window
- `test_app_selection_summary` — drives a real `UploaderWindow` through the
  `make_window` fixture and asserts on `selection_summary.cget("text")`

New:

- `tests/test_api.py`: exercise the `Api` class headlessly with a fake window
  object, asserting the messages it emits and the calls it accepts. Runs on
  `ubuntu-latest` with no webview installed. CI configuration is otherwise unchanged.
- Two behaviours lose their only guard and must be re-expressed as bridge tests:
  that a landing ffprobe result refreshes a summary showing a partial "+" total
  (from `test_app_selection_summary`), and that the last-upload channel is surfaced
  after a successful upload (from `test_app_last_upload`).

- `docs/smoke-checklist.md` (already 116 lines longer as of 2.2.0): extend to cover
  what automated tests no longer reach — tray hide/show/quit, the custom title bar
  drag, native folder dialogs, sort and selection behaviour, progress rendering
  during a real upload, and first-run on a machine without the WebView2 runtime.
  Add explicitly, because they are deliberate behaviours with no automated coverage
  under this approach: **arrow-key focus and Space-to-toggle, the row context menu,
  double-click-to-open leaving the checkbox selection unchanged, the upload and
  delete confirmation dialogs, the masked webhook and its Show toggle, and the
  indeterminate progress bar during a stitch.**

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
