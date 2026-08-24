# Nav restructure — implementation notes

Working notes for the title-bar restructure. Delete or fold into the PR
description at completion.

## Decisions (user-confirmed)

1. **Nav: 5 tabs -> 3.** `Uploader | Skills | Profiles`. Bookmarks and
   Previews become sections of the gear Settings route. "EVE Settings" is
   renamed **Profiles**, ending the collision with the gear's "Settings".
2. **Save model: immediate-save, no Cancel/Save footer** — refined during
   discovery, see "Deviation 1" below.
3. **Vocabulary: "keybind"**, user-visible strings only. Internal renames
   (`gesture`, `alert_bookmarks`, `set_preview_binds`) are deferred: they
   cross the Python bridge contract and are invisible to users.
4. **`.btn.acc`: invert** to near-black text on the full-strength brand.
5. **Skills stays a destination.** It is a monitoring workspace, not a
   config form, and `style.css:735` documents it as deliberately not the
   `.settings` wrapper.
6. **EVE gate: deferred**, own decision. See "Open" below.

## Confirmed constraints (evidence)

- `MIN_WIDTH = 840` is PHYSICAL px. `chrome.py:222` establishes WinForms
  reports 96 DPI under this app's system-DPI-aware model, so the CSS
  viewport floor is `840/scale`: 672 at 125%, 560 at 150%.
  `window.py:36` calls it "logical" and is wrong — fix in passing.
- Title bar cannot compress below ~686 CSS px. `.routenav` and `.winbtn`
  are `flex: none`; `.pywebview-drag-region` is the only flexible child
  and has no `min-width`, so its automatic minimum resolves to the
  wordmark's min-content width (~105px).
- **Route entry IS the fetch mechanism.** `bookmarks.js:363`,
  `previews.js:341`, `evesettings.js:261`, `skills.js:72` each match a
  route-name string off `wm:route`.
- **Route LEAVE disarms an armed key capture.** `bookmarks.js:366` and
  `previews.js:345` both document the bug this prevents: both files
  install document-level keydown listeners, `stopPropagation()` does not
  stop a sibling listener on the same node, so an armed capture consumes
  the next keystroke typed elsewhere and persists it into the wrong bind,
  off-screen and silently.
- **Failures here are silent.** `tests/test_bridge_contract.py` docstring:
  a handler name absent from `WM.HANDLERS` throws mid-IIFE, so every
  registration below it never runs and "the route then loads as an inert,
  empty version of itself -- no data, no buttons, no error the user can
  see." It cites a real incident that broke the whole EVE Settings route
  with every test passing.
- `save_bookmarks` (`api.py:1666-1668`) starts/stops the AHK engine;
  `set_preview_enabled` (`api.py:1304`) drives hotkey registration.
- Existing immediate-save patterns to follow: `set_preview_enabled`
  (no-op guard, bool return) and `set_restore_preview_positions`
  (dict return separating `applied` from `persisted`).

## Deviation 1 — what "immediate-save" means

User chose "immediate-save everywhere". Repository evidence shows blur-save
on two fields is destructive, so the model is refined, not reversed:

- **Discrete controls** (privacy, notify, checkboxes, keybinds): commit on
  change. Mostly already true.
- **Free text** (category, folders, webhook): commit on **Enter or an
  explicit affordance**, never on blur.
- **Clearing a configured webhook** requires an explicit action.

Why blur-save is unsafe here:

- `save_settings` rebinds the watcher (`api.py:1152`), and
  `Watcher.rebind` (`watcher.py:132-140`) baselines every file in the new
  folder into `seen`. A blur on a real-but-intermediate path prefix
  therefore swallows that folder, and the corrective blur re-baselines the
  right one — silently suppressing announcements for recordings that
  arrived during the session. Irreversible from the UI.
- Empty webhook bypasses validation (`api.py:1113`) and writes `""`. No
  Cancel, and no pre-edit snapshot exists (`settings.js:43` reassigns
  `current` every render).
- `tests/test_api_settings.py:409-421` documents the blank-writeback
  regression that a pre-hydration blur would reopen.

## Deviation 2 — per-field endpoints

Replacing `save_settings(collect())` with per-field endpoints is required,
not cosmetic. `save_settings` refuses the ENTIRE document on the first
invalid field (`api.py:1108-1122`), stacks non-blocking alerts
(`api.py:314-317` + `panel.js:117-122`), re-pushes the full payload which
rewrites every field including the one being edited (`api.py:1154` ->
`settings.js:40-65`), and re-runs OBS detection plus a whole `list_rows()`
ffprobe sweep on every call with no no-op guard.

Also consolidates a live landmine: `set_recording_dir` can only CREATE a
watcher (`__main__.py:530-531` returns early if one exists) and
`save_settings` can only REPOINT one (`api.py:1152`, guarded on
`_watcher is not None`). With `_watcher` None the folder persists,
`list_rows` un-gates so the UI looks healthy, and nothing ever notices new
recordings until restart.

## New requirement — section enter/leave

Folding Bookmarks and Previews into Settings removes the `wm:route` leave
event that disarms key capture. Switching sub-sections is not a route
change, so an armed capture would survive into Folders or Discord and
swallow keystrokes typed there — the documented bug, with a wider blast
radius (the capture handler `preventDefault()`s every key, Tab included).

Mitigation: emit `wm:section` with the same enter/leave contract
`wm:route` provides, and have both modules listen to route AND section.

## Decision 7 — EVE gate (user-confirmed)

The gate covers only the INERT destinations, and is structurally incapable
of stranding a running feature:

- Hides the **Skills** and **Profiles** tabs. Neither has an enabled flag;
  both do nothing until opened. With both hidden the nav has one
  destination left and `.routenav` hides entirely — the one-tab app the
  README describes.
- Also hides the **Keybinds** and **Previews** sections in Settings, but
  **the gate may only be switched off while both features are already
  off.** If either is on, the control says so and links to it.

Rejected alternatives and why:

- *UI-only, unconditional* — hides the off switch for a feature that is
  still running: previews still painting, 18 global hotkeys still firing,
  no reachable control.
- *Master kill switch* — silently stops global hotkeys mid-session from
  what reads as a display preference, and re-enabling cannot know which of
  the two features to restore without a third persisted value.
- *Suspend without writing the flags* — breaks the invariant that the
  persisted flag IS the runtime switch. `start_engine_if_enabled`
  (`__main__.py:302`) and `start_previews_if_enabled` (`__main__.py:518`)
  read it at every launch, so a suspended-but-true flag restarts the
  engine on next start. Would require the startup path to consult two
  inputs where it consults one.

The confirmed friction: an EVE user wanting everything hidden must turn the
two features off first. That is the point — it is what stops the control
from being a silent kill switch.

## Open

- Statusbar `SIG/ROOT/NEXT` shows on every route incl. Uploader. Last EVE
  state leaking into global chrome; should follow the gate.
- `docs/smoke-checklist.md` has ~10 nav-keyed items, incl. line 778 still
  written for the two-tab era.

## Verification

- `pytest` — `test_bridge_contract.py` and `test_api_settings.py` are the
  two that matter most here.
- No JS test harness exists (`webview-replatform-design.md:545`), so every
  page change needs a manual smoke pass. The IIFE failure mode is silent.
- Title bar must be checked at 100/125/150% scaling at minimum window
  width — the thing this work exists to fix, and NOT covered by pytest.
