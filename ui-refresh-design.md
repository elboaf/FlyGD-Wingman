# UI refresh: look and feel

**Date:** 2026-08-20
**Status:** Approved for planning
**Base branch:** `combat-log-upload` (not `main`). This work stacks on the
combat-log feature, which adds an **Upload combat logs** button to the action
bar, a **Discord (combat logs)** section to the settings dialog, two **Detect**
buttons, and `combatlog.py` / `discord.py`. Those widgets are in scope for
theming and spacing; their logic is not.
**Scope:** Presentation layer only — `app.py`, `settingsui.py`, `__main__.py`,
`packaging/uploader.spec`, `packaging/installer.iss`, `.github/workflows/build.yml`

## Intent

The app was inherited from a simple script and its UI shows it: Windows
7-era `ttk` chrome, blurry text on scaled displays, the Tk feather icon, and
a hand-built table. This is a look-and-feel pass. No features are added and
no logic module is touched.

"No functional changes" is interpreted as **do not build features** — not as
"interaction must be byte-identical." Where a more native widget improves the
look at the cost of a changed gesture (Copy/Open moving to a context menu),
the native widget wins.

### Out of scope

- Any change to `library`, `stitch`, `uploader`, `watcher`, `obsconfig`,
  `settings`, `paths`, `credentials`, `combatlog`, or `discord`.
- New settings, new columns, filtering, thumbnails, drag-to-reorder.
- Replacing `messagebox` / `filedialog` with custom dialogs (see Known
  limitations).

## Repository evidence

| Finding | Source |
|---|---|
| No UI tests exist | no `tests/` file imports `app`, `settingsui`, or `UploaderWindow`. **But `tests/test_main.py` imports `configure_logging` and `resolve_recording_dir` from `__main__`** — §4 edits `main()`, so that file is a real gate |
| CI cannot catch UI regressions | `ci.yml` runs pytest on `ubuntu-latest` only |
| A missing dependency yields a green build of a broken app | `build.yml`, "Verify the app's dependencies are importable" |
| Degrade rather than block, for *optional* facilities | `configure_logging`, `resolve_binary`, `probe_duration`, every `icon.notify` — note this is not a codebase-wide rule: `paths.ensure_dirs()` and the initial `settings_mod.save(cfg)` in `main()` are unguarded startup requirements |
| Sorting cannot corrupt upload order | `_chosen()` iterates `self.infos`; `stitch.order_for_stitch` re-sorts by `mtime` |
| Settings dialog sizing was recently fixed for 125%/150% | commit `b23f9cc`, `settingsui.py.__init__` |
| Version is declared in three files and enforced | `ci.yml`, "Check version consistency" |

## Design

### 1. Theming

`sv-ttk` applied once in `__main__.py`, after `tk.Tk()` and before
`UploaderWindow` is constructed.

Theme selection follows the Windows setting
(`HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize`,
`AppsUseLightTheme`). Live switching piggybacks on the existing 3-second
`poll()` loop rather than adding a registry-watch thread.

**The theme check gets its own `try/except` block inside `poll()`**, separate
from the watcher's. The watcher block counts consecutive failures and fires a
"watcher is having trouble" notification at 5; a failed registry read must not
be miscounted as a watcher fault.

Theme application is wrapped so that any failure leaves the app on default
`ttk` rather than killing startup — the established policy for optional
presentation capabilities. Failures are logged through the existing rotating
file handler (`configure_logging`), not swallowed silently: with
`console=False` there is no other place for them to surface, and an unhandled
startup exception is a traceback dialog and a dead app.

#### Applying a theme is a single owner, not a side effect

`sv-ttk` restyles `ttk` widgets only. Everything else in this app must be
re-themed explicitly, and a live OS switch means doing it to widgets that
already exist:

- Directly-assigned widget colours (`app.py:189`, `app.py:210`,
  `settingsui.py:98`) — every token consumer must be re-applied, not just
  re-resolved.
- `Treeview` row tags — tag colours are configured on the widget and do not
  follow a theme change.
- The classic `tk.Text` description box.
- The generated checkbox images, which bake in theme colours and must be
  **regenerated**, not merely re-assigned.

Therefore `theme.py` exposes one entry point — `apply(root, mode)` — that is
the sole path for both initial application and live switching. It sets the
sv-ttk theme, regenerates images, and walks the registered token consumers.
Windows register themselves with it; nothing re-themes itself ad hoc. Without
a single owner, a live switch produces a half-themed window, which is worse
than not following the OS at all.

### 2. Colour tokens

A new `theme.py` exposes named tokens (`SUCCESS`, `ERROR`, `WARNING`, `MUTED`,
`LINK`, `FG`, `ROW_ODD`, `ROW_EVEN`, `ROW_PRESELECT`) resolved per active theme.

`FG` is the neutral status foreground, and it exists because of a live bug:
`_combat_log_worker` sets `foreground="black"` on the status line
(`app.py:351`). Unlike the green/red literals — which are merely suboptimal in
dark mode — black on a dark background is *invisible*. Every literal colour is
replaced by a token:

- `app.py` — `fg="blue"` on the link entry; `foreground=` `"orange"`,
  `"green"`, `"red"` in the ffmpeg warning, `_copy`, `_upload_worker`,
  `_upload_one.on_retry`, `_retry_worker`; and `"black"`, `"green"`, `"red"`
  in `_combat_log_worker`.
- `settingsui.py` — `"gray"` on the two hint labels and on `lbl_webhook`;
  `"green"` / `"red"` / `"orange"` in `_refresh_auth_label` and `_connect`.

This is the change that touches the most lines and is required for dark mode
to be legible at all.

### 3. Video list → `ttk.Treeview`

Replaces the `tk.Canvas` + packed-`ttk.Frame` rows and the fixed-character
header in `_build`/`refresh`.

Six columns — checkbox, Filename, Date, Size, Duration, YouTube Link, matching
today's header exactly — with click-to-sort headers, striping via row tags, and
a native scrollbar.

- **Checkboxes** — a first column whose cell image toggles on click. Images
  are generated at runtime with Pillow at the active DPI scale and theme
  colours, following the pattern `build_tray` already uses for the tray icon.
  Generated images are held in an instance attribute; Tk garbage-collects
  unreferenced `PhotoImage` objects.
- **Selection state is unchanged.** `self.selected` stays
  `dict[Path, tk.BooleanVar]`, so `_chosen`, `_set_all`, and `_start_upload`
  are untouched.
- **Preselection stays visible.** `refresh(preselect=...)` scrolls the first
  preselected row into view and tags those rows with `ROW_PRESELECT`. Today a
  newly-ready recording can be checked below the fold with no indication;
  this is strictly better.
- **Copy / Open** become a right-click context menu ("Copy link", "Open in
  browser") plus double-click, which opens the row's **YouTube link** — never
  the local video file. Both are disabled when the row has no link yet.
  `_copy` and `_open` read from a new `dict[Path, str]` instead of an `Entry`;
  `_set_link` writes there and updates the cell.

  **The dict is cleared in `refresh()`, exactly as `self.links` is today**
  (`app.py:172`). This is a deliberate choice to keep the change
  presentation-only: making links survive a rebuild would be a behavior
  improvement, and improvements are out of scope here. Consequently a
  `refresh()` still clears the link column — including the deferred refresh
  in `poll()` that fires once an upload finishes. That is pre-existing
  behavior, not a regression introduced by this design, and it is recorded
  under Known limitations.

  `_set_link` keeps its "unknown path is a no-op" guard, but note what that
  guard is actually for: a `_ui`-queued update arriving for a path that is no
  longer in the rebuilt list (a file deleted or moved out from under the
  app). It does **not** protect against the refresh-clears-links case above,
  and an earlier draft of this spec wrongly claimed it did.

Sorting is display-only and provably cannot affect upload numbering or stitch
order (see evidence table).

### 4. DPI awareness — sequenced separately

Process DPI awareness is declared before the root window exists, guarded for
non-Windows as `__main__.py` already does for the single-instance mutex.

**Decisions this needs to make explicitly:**

- **Awareness mode.** `SetProcessDpiAwareness(PROCESS_SYSTEM_DPI_AWARE)`, not
  Per-Monitor V2. System-DPI-aware is correct for a single-window tray utility
  and avoids handling `WM_DPICHANGED` when a window is dragged between
  monitors of different scale; Per-Monitor would look better on mixed-DPI
  setups but requires re-laying out and regenerating checkbox images on every
  monitor change. Revisit only if mixed-DPI complaints appear.
- **Scaling formula.** `root.tk.call("tk", "scaling", dpi / 72.0)`, where
  `dpi` comes from `GetDpiForSystem`. Tk's `scaling` is points-per-pixel, so
  the divisor is 72, not 96.
- **Ownership.** `tk scaling` is set **once**, in `__main__.py`, immediately
  after the root is created and before any window is constructed. No other
  module calls it. Double-scaling — the OS stretching a nominally-aware
  process, or two `tk scaling` calls compounding — is the failure mode to
  design against.

**This ships as its own commit with its own smoke pass.** Not because it
breaks commit `b23f9cc`'s settings-dialog fix outright — that fix makes height
content-driven, which stays correct — but because it changes the *physical
meaning* of every fixed pixel constant in the UI at once. `settingsui.py`'s
`max(520, winfo_reqwidth())` floor, `app.py`'s `1350x650`, and
`minsize(750, 450)` were all chosen while the process was DPI-unaware and the
OS was bitmap-stretching it. Each has to be re-evaluated in real pixels and
re-verified at 125% and 150%, which is a smoke pass in its own right rather
than a line inside a theming commit.

Initial geometry is clamped to the work area so the window cannot open larger
than the screen at 150%.

### 5. Window chrome

- Action bar regrouped: secondary and destructive actions left, **Upload
  Selected** as the accent button right. Today's mix of `side=LEFT` and
  `side=RIGHT` renders the buttons right-aligned in reverse order. The bar
  carries six controls — Settings, Delete Selected, Select All, Select None,
  **Upload combat logs**, Upload Selected — plus Retry and the stitch
  checkbox, so deliberate grouping matters more than it would with four.
- Progress bar and status line become one fixed-height bottom bar, so the
  window does not shift when status text wraps or the bar switches to
  indeterminate during stitching.
- The ffmpeg-missing warning becomes a themed inline warning.

### 6. Settings dialog

- One spacing scale shared with the main window, replacing the current mix of
  `padx=8, pady=6`, `padding=10`, `pady=(6, 0)`, `pady=(4, 0)`.
- Auth line becomes a status row: coloured dot plus
  Connected / Not connected / Waiting for browser….
- Consistent label column so `Privacy:` and `Category ID:` align — and, in the
  Discord frame, `Webhook URL:` and `Gamelogs:`.
- The dialog has **six** `LabelFrame`s, not five: Google account, Upload
  defaults, When a recording finishes, **Discord (combat logs)**, Recording
  folder, and the button row. The Discord frame's `lbl_webhook` status line
  (currently `foreground="gray"`) takes the `MUTED` token, and its two
  **Detect** buttons plus **Browse…** adopt the shared spacing scale.
- `Save` becomes `Accent.TButton`; `Cancel` stays neutral.
- The DPI-driven sizing logic and its comment stay, updated per §4 — including
  the comment's "five packed LabelFrames", which is now six. The extra frame
  makes the clipping check *more* load-bearing, not less; the combat-log work
  already added its own 100%/150% checklist item for exactly this reason.

### 7. Icon

A real `.ico` replacing the Tk feather, used in three places:

1. `root.iconbitmap` at runtime — needs a `datas` entry, resolved with care:
   `paths.bundle_dir()` has the same source-vs-frozen mismatch that
   `resolve_binary`'s docstring documents.
2. `icon=` on `EXE(...)` in `uploader.spec` — this also fixes the Start Menu
   shortcut and the uninstaller entry for free, via `installer.iss`'s
   `UninstallDisplayIcon={app}\{#AppExe}`.
3. The tray icon, replacing the PIL-drawn placeholder in `build_tray`.

### 8. Packaging

- `sv-ttk` added to `pyproject.toml` dependencies.
- `uploader.spec` gains a `datas` entry for sv-ttk's `.tcl` files, which
  imports alone will not pull in.
- `build.yml`'s importability check gains `sv_ttk`. **This is necessary but
  not sufficient, and an earlier draft of this spec overstated it.** That step
  runs in the *build environment* before PyInstaller has run
  (`build.yml:55`), so it proves only that sv-ttk is installed on the runner
  — nothing about whether its `.tcl` files reached the bundle. The existing
  post-build assertions inspect ffmpeg only (`build.yml:88`).
- **Therefore `build.yml` also gains a post-build assertion** that sv-ttk's
  theme data exists under `dist/OBSYouTubeUploader/_internal/`, written in the
  same style and for the same reason as the existing ffmpeg check — which
  already carries the comment explaining that PyInstaller exits 0 on a missing
  resource. Without this, a wrong `datas` entry produces a green build of an
  app that dies on launch, and nothing in CI notices.
- A frozen build is produced and **launched** before the visual work stacks
  up, not at release time. The bundle assertion catches a missing file; only
  launching catches a file that is present but unloadable.

## Verification

No UI tests are added; the existing suite covers only logic modules, none of
which change.

1. `python -m pytest tests/` stays green (baseline: 175 passed) — proves the
   refactor did not leak into logic.
2. **A `workflow_dispatch` test build early**, confirming sv-ttk's `.tcl`
   files land in the bundle (post-build assertion, §8) *and* that the frozen
   app launches. The assertion alone cannot prove loadability.
3. Manual `docs/smoke-checklist.md` at **100% and 150%** scaling, in **light
   and dark**, with the OS theme switched while the app is running — with both
   windows open, since a live switch is where a half-themed window would show
   up.
4. Checklist items needing rewording for the new interaction: "Copy button
   puts a working URL on the clipboard" and "Open button opens the video in a
   browser" become context-menu items; "Newly announced recordings are
   already checked when the window opens" gains the scrolled-into-view and
   highlight assertions.

## Known limitations (accepted)

- `messagebox` and `filedialog` are native Win32 dialogs and follow the OS,
  not the app theme. A dark window can raise a light dialog. Replacing them
  with custom `Toplevel`s is a functional change and is out of scope.
- `tk.Text` (description box) is a classic Tk widget outside sv-ttk's ttk
  styling. It is deliberately left unconfigured and is NOT a token consumer:
  it looks correct in both modes only because sv-ttk's `configure_colors`
  calls `tk_setPalette`, which recolours already-created classic widgets as
  a side effect. That is sv-ttk's behaviour, not ours, so its appearance is
  inherited rather than guaranteed — hence the smoke-checklist legibility
  item rather than a re-theming path.
- The title bar needs `DwmSetWindowAttribute(hwnd, 20, ...)` via ctypes
  (Windows 10 1809+) or the chrome stays light around a dark window.
- No free sorting existed before and rows are still rebuilt on each
  `refresh()`; `Treeview` makes both cheaper but neither is a goal here.
- **A `refresh()` still clears the YouTube link column**, so links set during
  an upload disappear when new recordings arrive or when the deferred refresh
  in `poll()` fires. This is today's behavior (`app.py:172`) and is preserved
  deliberately — see §3. Persisting links across rebuilds is a reasonable
  future improvement, but it is an improvement, not a look-and-feel change.

## Open questions

None blocking. Light/Dark follows the OS with no user override; a Settings
control can be added later if following the OS proves annoying.
