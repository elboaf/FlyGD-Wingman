# Smoke checklist

Manual verification for the GUI and live upload paths, which are not
automated: doing so would need live credentials and would consume the very
upload quota the design is constrained by.

The UI refresh (theming, the Treeview list, DPI awareness, the real app
icon) is likewise untested by `pytest` — no file under `tests/` imports
`app` or `settingsui` — so this checklist is the only real verification
those changes get.

Run on Windows against a real install before each release.

## Install
- [ ] Installer runs without an admin prompt
- [ ] Installer wizard, Start Menu entry, and Add/Remove Programs all read
      **FlyGD Wingman**
- [ ] Start Menu shortcut launches the app
- [ ] With "start at login" checked, the app appears after a reboot
- [ ] Uninstall removes the app and leaves `%LOCALAPPDATA%` state intact
- [ ] **The rename upgrades in place rather than installing a second copy.**
      Install a pre-rename build (product name "OBS YouTube Uploader"), sign
      in and change a setting, then run the new installer over it. Expected:
      Add/Remove Programs lists exactly ONE entry, now named FlyGD Wingman;
      `%LOCALAPPDATA%\OBSYouTubeUploader\settings.json` and `token.json`
      survive, so the app is still signed in with the same preferences. This
      is what `AppId=OBS YouTube Uploader` in installer.iss buys — if two
      entries appear, that pin is wrong or missing.
- [ ] Window title bar and tray-icon tooltip both read **FlyGD Wingman**
- [ ] A "new recording(s) ready to upload" notification is titled
      **FlyGD Wingman**

## First run
- [ ] Recording folder is pre-filled from OBS config without being asked
- [ ] With OBS absent, the folder picker appears instead
- [ ] Existing recordings do NOT produce a notification on first launch
- [ ] **Missing ffmpeg disables Stitch instead of breaking the app.**
      Rename `bin\ffmpeg.exe` inside the install directory so it fails to
      resolve, then start the app. Expected: the app still starts and
      lists recordings normally; the Stitch checkbox is disabled with an
      explanatory "(ffmpeg not found — stitching unavailable)" label.
      Restore the binary afterward. **The warning now lives in the upload
      panel, directly under the Stitch checkbox, not in a full-width bar** —
      check the whole sentence is readable there and wraps rather than being
      cut off at the panel edge, at 100% and again at 150%.

## Look and feel

### Layout
- [ ] **The upload panel is intact at 100%, 150% and 200%.** Set
      `Settings > System > Display > Scale`, restart the app at each. The
      panel keeps its proportion to the window, and Title, Description,
      Stitch, the selection summary, Upload combat logs, Retry and Upload
      Selected are all fully visible with no clipped text and no button
      running past the panel edge.
- [ ] **Nothing is clipped at the minimum window size.** Drag the window as
      small as it goes at 150%. Expected: the Description box shrinks first
      and the Retry/Upload Selected row is still fully visible; list columns
      are cramped but present (accepted degradation — see
      ui-layout-design.md, "Narrow windows"). A missing Upload button is a
      defect; a narrow filename column is not.
- [ ] **The window has visible margins on all four edges,** and the
      Description box reads as a bordered field in both light and dark mode
      rather than blending into the panel background.

### Theming
- [ ] **Launches in light mode when Windows is set to Light.**
      `Settings > Personalization > Colors > Choose your mode > Light`, then
      launch. Both windows render with sv-ttk's light theme — no dark chrome,
      and no illegible text in status messages, hint labels, or the ffmpeg
      warning.
- [ ] **Launches in dark mode when Windows is set to Dark.** Same with `Dark`.
      Also check Treeview row striping and the description `tk.Text` box.
      sv-ttk's ttk styling does not cover that box — it is a classic Tk
      widget — but sv-ttk's `configure_colors` calls `tk_setPalette`, which
      recolours classic widgets as a side effect, and that is the only
      reason it looks right. Nothing in this app configures it. So check it
      for legibility rather than assuming it is styled (a known accepted
      limitation).
- [ ] **The right-click context menu is legible in dark mode.** With Windows
      set to Dark, right-click a list row and read the menu: "Copy link" and
      "Open in browser" must be readable, not white-on-white or black-on-black,
      and the greyed-out state must still be distinguishable. `tk.Menu` is a
      classic Tk widget, and on Windows sv-ttk's `config_menus` returns
      immediately — so the menu's entire appearance rests on `tk_setPalette`,
      which nothing in this app controls and no test covers.
- [ ] **The Settings auth status dot is legible in dark mode.** Open Settings
      with Windows set to Dark and check the dot beside the Google account
      row in both states (connected and not connected): the dot must be
      visible against the dialog background, not a light square sitting on a
      dark panel. It is a `tk.Canvas` — again a classic Tk widget whose
      background comes from `tk_setPalette`, not from sv-ttk styling.
- [ ] **LOAD-BEARING: switching the OS theme live, with both windows open.**
      Open the main window and Settings together, then flip
      `Choose your mode`. Within a few seconds both must re-theme fully:
      status line, ffmpeg warning, auth status dot and text, hint labels,
      Treeview striping, the preselect highlight, and the checkbox images.
      No half-themed widget anywhere.
      *Why this is load-bearing:* the app sets these colours from a deferred
      `after_idle` callback because `sv_ttk.set_theme()` fires a QUEUED
      `<<ThemeChanged>>` event that runs `tk_setPalette` on the next tick and
      resets any directly-set widget foreground. That ordering was observed
      under WSLg. If native Windows Tk dispatches differently, colours may
      revert one tick after the switch — watch for a correct flash followed
      by a reset.
- [ ] **A red error status survives a live theme switch.** Force an upload
      failure so the status line is red, then flip the OS theme. It must
      re-colour to the other theme's red — not reset to the default
      foreground, and not stay in the old theme's red.
- [ ] **A rapid double-flip settles correctly.** Flip light→dark→light
      quickly. Intermediate flicker is acceptable; a stuck or wrong final
      colour is not.
- [ ] **Opening Settings repeatedly does not leak theme consumers.** Open and
      close Settings five times, then flip the OS theme. Confirm
      `%LOCALAPPDATA%\OBSYouTubeUploader\logs\uploader_debug.log` contains no
      `TclError` warnings from stale consumers holding destroyed windows.
- [ ] **A failed theme read does not trigger the watcher's failure
      notification.** Run several minutes with the theme untouched and
      confirm zero "watcher is having trouble" notifications. The theme check
      has its own try/except inside `poll()`, separate from the watcher's
      consecutive-failure counter; that notification must stay reserved for
      real recording-folder faults.

### Display scaling
- [ ] **100% scaling.** Both windows render at native size, text sharp, no
      clipping.
- [ ] **125% scaling.** Settings dialog not clipped — Recording folder frame
      and the Save/Cancel row fully visible AND above the taskbar.
- [ ] **150% scaling.** Neither window opens larger than the screen.
- [ ] **200% scaling.** Neither window opens larger than the screen, the
      Settings dialog is still unclipped with Save/Cancel reachable, and the
      status bar still fits its progress bar and label.
- [ ] **LOAD-BEARING: list ROW TEXT is not vertically clipped at 200%.**
      Distinct from the checkbox item below, which only covers the image, and
      from the window-fits items above. Read the Filename and Date
      cells: descenders (g, p, y) and the tops of capitals must be fully
      visible, not shaved by the row boundary. sv-ttk computes its row height
      once from the UNSCALED font when `sv.tcl` is sourced and never
      re-evaluates it, so the app re-measures the corrected font in
      `_apply_row_height()` and takes the larger of that and the checkbox
      height. If text is cropped, that re-measurement is what to look at.
      Check it after a light↔dark switch too, since `set_theme` re-asserts
      sv-ttk's own stale value each time.
- [ ] **LOAD-BEARING: on a NARROW window and a SHORT screen, not just
      1080p.** The minsize clamping fixes only bite in those configurations —
      a default 1080p pass exercises neither. On a short screen, confirm the
      Settings dialog can still be resized smaller and moved, i.e. Save and
      Cancel are always reachable.
- [ ] **LOAD-BEARING: the list checkbox is not clipped at 125%, 150%, and
      200%.** sv-ttk sets Treeview row height from a font that does not
      follow `tk scaling`, so the app raises the row height itself to fit the
      scaled checkbox image. This was measured under WSLg only. Also confirm
      a light↔dark switch does not re-clip it — sv-ttk re-asserts its own row
      height on every `set_theme`.
- [ ] **Text is sharp, not bitmap-stretched, at 150%.** The process declares
      DPI awareness but the HRESULT is discarded, so blurriness is the only
      observable sign the call silently failed.
- [ ] **LOAD-BEARING: text is the right SIZE at 150% and 200%, not merely
      sharp.** Sharpness and size are separate failures and the item above
      only catches the first one. Compare the app's text against Notepad (or
      any native Windows app) side by side at the same scale factor, or
      against the app on a 100% machine: labels, buttons, list rows and
      column headings must look the same apparent size as native UI, not
      noticeably smaller. Crisp-but-undersized text means sv-ttk's ttk fonts
      are not following `tk scaling` — sv.tcl declares them in absolute
      pixels, and `theme._rescale_sv_fonts()` is what corrects that. Check it
      after a light↔dark switch too, since `apply()` reruns the rescale each
      time (a font that keeps shrinking, or doubles, means the rescale is
      compounding rather than deriving from sv-ttk's base sizes).
      *Note the interaction:* undersized text makes every "nothing is
      clipped" item on this list pass more easily, so a size regression can
      hide behind an otherwise-green scaling section — check size first.

### Typography
- [ ] **Column headers are bold and the rows are not.** Filename, Date,
      Size, Length and Link read heavier than the row text beneath them.
      Row text is intentionally uniform — `ttk.Treeview` has no per-column
      fonts and the row tags are already spent on striping, preselection
      and the link colour — so uneven-looking rows are a bug, not the
      hierarchy.
- [ ] **The panel's "Upload" heading is bold**, and heavier than the
      "Title"/"Description" field labels under it.
- [ ] **Secondary text is muted, not black-on-black.** The selection
      summary and any hint labels read visibly lighter than the primary
      text in BOTH light and dark — the muted colour is a theme token, so
      an unreadable one means the style was not re-applied for that mode.
- [ ] **LOAD-BEARING: bold survives a live OS theme switch.** With the main
      window open, flip `Choose your mode`. After the switch, the column
      headers and the "Upload" heading must still be bold, still the right
      size, and the muted text must have taken the new mode's colour. ttk
      stores style options per theme and `sv_ttk.set_theme` replaces the
      theme, so everything configured here is wiped on every switch and
      re-asserted from the window's single theme consumer. A switch that
      leaves plain headings behind means that re-assert is not running, or
      is running before `set_theme` rather than after.
- [ ] **Heading size follows display scaling.** At 150% and 200%, the bold
      headers grow with the rest of the UI rather than staying at their
      100% size — they are derived from sv-ttk's own font *after* it has
      been rescaled, so a frozen-looking header means that ordering broke.

### The list
- [ ] **LOAD-BEARING: clicking a checkbox toggles it.** The click handler
      relies on `identify_region()` returning `"tree"` for the checkbox
      column and something else elsewhere. That was confirmed on X11 only.
      Also confirm clicking a data column does NOT toggle.
- [ ] **LOAD-BEARING: the context menu releases its grab.** Right-click a
      row, then dismiss it by clicking elsewhere; repeat and dismiss with
      Escape. After each, confirm the window still responds to clicks. This
      path has NO automated coverage of any kind — a retained pointer grab
      presents as "the app is frozen".
- [ ] **Copy link and Open in browser** from the context menu work on a row
      with a link, and are greyed out on a row without one.
- [ ] **Double-click opens the YouTube link** — and does NOT open a browser
      when double-clicking the checkbox column.
- [ ] **Keyboard: Space toggles the focused row.** Tab to the list, use the
      arrow keys to move, press Space. Confirm it toggles exactly one row and
      that Upload Selected agrees with what is checked. Then trigger a list
      rebuild (delete a file, or save Settings) and confirm the keyboard
      still works afterwards without touching the mouse.
- [ ] **Treeview tag colours actually render** — zebra striping, the
      preselect highlight, and the blue link foreground, in both light and
      dark. Tag backgrounds under a themed Treeview style are historically
      theme- and version-dependent.
- [ ] **Sorting does not affect upload order or stitch order.** Sort by each
      column, then select rows out of their displayed order and upload —
      first with Stitch off, then on. The `(1/n)` numbering and stitched clip
      order must follow the underlying data, not the display.
- [ ] **Newly announced recordings are pre-checked, scrolled into view, and
      visibly highlighted** — even when they would otherwise be below the
      fold.
- [ ] **Sorting by Length while durations are still loading.** Delete
      `durations.json`, launch against a large folder, and click the
      Length header while rows still read "…". Expected: pending rows
      sort together (they have no value yet) and each fills in where it
      sits — rows do NOT re-order themselves under the cursor as results
      arrive. Click the header again afterwards to re-sort with the real
      values.
- [ ] **Column headers line up with their data.** Filename and Date read
      left-aligned with left-aligned headers; Size and Length read
      right-aligned with right-aligned headers; the checkbox and Link
      headers are centred. Confirm the fourth column's header reads
      **Length**, and that clicking it still sorts by duration (a short
      recording and a long one swap places) — the header text changed but
      the sort key deliberately did not.
- [ ] **Only the Filename column grows.** Widen the window from its minimum
      to full screen: Filename takes all the new space; Date, Size, Length
      and Link stay put.
- [ ] **LOAD-BEARING: the list at the minimum window width.** Drag the
      window to its floor (750px at 100%). Expected: every column is still
      present and readable, Filename truncates rather than pushing the
      others off, and NO horizontal scrollbar appears. Cramped is the
      accepted outcome here — a column that vanishes, overlaps, or
      collapses to nothing is not. The preferred widths (620px total) do
      not fit in the pane at that size; the per-column minimums (410px
      total) are what hold it together, so this is the only place that
      arithmetic is exercised.
- [ ] **The Link column shows ↗, not a URL.** After an upload completes, the
      row's Link cell shows a single arrow glyph in the link colour. Then
      confirm the URL is still reachable three ways on that row:
      double-click opens the video, right-click → Copy link pastes a working
      URL, right-click → Open in browser opens the same page. These read the
      in-memory link map rather than the cell, so a regression here means
      the wiring changed, not the glyph.
- [ ] **Rows have breathing room.** Compare against a pre-change build if
      one is handy: rows should look noticeably less cramped over a long
      list. At 100%, 125%, 150% and 200% confirm the extra height did not
      cost anything — descenders and the checkbox are still fully visible,
      and still are after a light↔dark switch.

### Icon
- [ ] **The icon appears in all five locations:** main window title bar,
      Settings title bar, taskbar, system tray, and — after running the built
      installer — the Start Menu shortcut and Add/Remove Programs entry.
      Note the icon can only ever be verified on Windows: on Linux,
      `iconbitmap` always fails because X11 Tk has no `.ico` support, so
      development runs show no icon by design.
- [ ] **A missing icon does not break startup.** Rename `app.ico` inside the
      install directory and relaunch: the app still starts, and the tray
      falls back to its drawn placeholder.

### Frozen build
- [ ] **LOAD-BEARING: the installed build renders themed, not plain ttk.**
      This is the only proof sv-ttk's `.tcl` files were both bundled AND are
      loadable. CI asserts the files exist; only launching proves they load.
- [ ] **Checkboxes appear in the list in the frozen build.** They are
      generated through `PIL.ImageTk`, which depends on the
      `PIL._tkinter_finder` hidden import. If that is wrong the list renders
      with no checkboxes at all, and no source-checkout test can see it.
- [ ] **`Accent.TButton` renders visually distinct** on Upload Selected and
      on Settings' Save.

## Watcher
- [ ] Recording in OBS then stopping produces one notification
- [ ] Notification does not steal focus from a fullscreen game
- [ ] Clicking the tray icon opens the uploader window
- [ ] With `notify_mode: popup`, the window raises instead
- [ ] A recording made while the app was closed is announced on next launch
- [ ] Existing recordings are NOT re-announced on an ordinary restart
- [ ] **Newly announced recordings are already checked when the window
      opens, scrolled into view, and visibly highlighted.** With the window
      closed, create a new recording so the watcher detects it, then open
      the window from the tray. Its row is pre-checked, the list is scrolled
      so the row is visible without manual scrolling (even if it would
      otherwise be below the fold), and it carries a distinct highlight
      (`ROW_PRESELECT`) visually different from the ordinary row stripes.
- [ ] **Persistent watcher failure surfaces exactly one notification.** Make
      the recording folder unreachable while the app is running (rename it,
      or unmount the drive it's on). After roughly 15 seconds, expect ONE
      tray notification that the watcher is having trouble — not one every
      poll cycle, and not silence. Restore the folder and confirm polling
      resumes normally afterward.
- [ ] **A file deleted outside the app and recreated at the same path.**
      With the app running, delete a recording in Explorer, then create a
      new file at that exact path. This is a known limitation of the
      seen-entry tracking: the recreated file may not be re-announced until
      the app restarts. That is expected behavior, not a bug to report.

## Settings
- [ ] Settings button opens the dialog
- [ ] **The dialog appears immediately, before the account state resolves.**
      Open Settings on a cold app start (the Google libraries load on first
      use). Expected: the window is drawn straight away with a grey status
      dot and "Checking…" beside it, which then becomes green "Connected"
      or red "Not connected". The dialog must never hang blank before
      appearing, and must never stay stuck on "Checking…". Flip the OS
      theme while it still reads "Checking…" and confirm the grey dot
      re-themes with everything else.
- [ ] Connect Google Account opens a browser and reports "Connected"
- [ ] **Click Connect Google Account while the account state is still
      resolving.** On a cold app start, open Settings and click Connect
      immediately, while the label still reads "Checking…". Expected: the
      label goes to "Waiting for browser…" and STAYS there until the
      sign-in finishes — the startup check completing behind it must not
      flip it to a red "Not connected" mid-sign-in.
- [ ] **The YouTube Terms of Service link is visible and works.** In the
      Google account section, confirm the line "Videos are uploaded to
      YouTube and are subject to the YouTube Terms of Service:" and the
      https://www.youtube.com/t/terms link beneath it are both fully
      visible (check at 150% display scaling too — this section grew by
      two lines), and that clicking the link opens YouTube's terms in a
      browser. Developer Policies III.A.1 requires this link to be
      displayed by the application, so it must not be clipped away.
      Then switch the Windows app mode between Light and Dark with the
      dialog open: both lines must recolour with the rest of the dialog.
      They are repainted by `_repaint_tokens`, and a label missing from
      that pass keeps its old colour — which in dark mode leaves the
      link a dark blue on a dark background, i.e. displayed but unreadable.
- [ ] **Close the Settings dialog while a Google sign-in is in flight.**
      Click Connect Google Account, then close the Settings window before
      completing (or without completing) the browser sign-in. The OAuth
      worker thread later calls back into the now-destroyed window.
      Expected: at worst a traceback printed to stderr; no crash of the
      app, no corrupted settings file, and the tray icon keeps working.
- [ ] Changing privacy and saving persists across an app restart
- [ ] Changing the recording folder takes effect without a restart —
      new recordings in the NEW folder are announced, old folder is ignored
- [ ] Switching notify mode to popup takes effect on the next recording,
      without a restart
- [ ] A non-numeric category ID is rejected with a warning

## Video list and durations
These cover the duration cache and the background probe. Do them against a
folder with a realistic number of recordings (30+); the whole point is
behavior that only shows up at size.

- [ ] **The window opens immediately on a large folder.** Launch with 30+
      recordings and no `durations.json` (delete it from
      `%LOCALAPPDATA%\OBSYouTubeUploader\` first). Expected: the list
      appears at once with every row present, Length reading "…", and
      the values filling in over the next few seconds. The window must be
      draggable and scrollable the whole time — never a frozen white
      rectangle.
- [ ] **A second launch is instant.** Restart the app without changing the
      folder. Expected: durations are already filled in on first paint, no
      "…" at all, and no visible ffprobe activity.
- [ ] **Saving Settings does not re-freeze the list.** With the same large
      folder, open Settings, change privacy, Save. Expected: the list
      refreshes instantly with durations still shown; no pause.
- [ ] **A new recording probes alone.** Record a short clip and let the
      watcher announce it. Expected: only the new row shows "…" briefly;
      every existing row keeps its duration without re-probing.
- [ ] **Deleting recordings does not grow the cache forever.** Delete
      several recordings in the app, then check that `durations.json`
      shrinks to match what remains in the folder. This must happen on the
      delete itself, not only after some later recording is probed.
- [ ] **An unreachable recording folder must NOT wipe the cache.** With a
      warm `durations.json`, disconnect the drive the recordings live on
      (or rename the folder) and leave the app running through a few poll
      cycles, opening the window once. Expected: the list shows "Found 0
      video(s)" but `durations.json` still holds every entry. Reconnect and
      confirm the durations reappear with no re-probing.
- [ ] **Missing ffprobe degrades to "?" and stays recoverable.** Rename
      `bin\ffprobe.exe`, delete `durations.json`, and launch. Expected:
      rows show "…" then settle on "?" — never stuck on "…". Restore the
      binary, relaunch, and confirm real durations come back.
- [ ] **ffprobe removed *while the app is running* must not poison the
      cache.** With the app open, rename `bin\ffprobe.exe`, then delete a
      recording to force a refresh of a folder with new files. Expected:
      affected rows show "?". Restore the binary and relaunch: those
      recordings must show real durations again. A failure that was never
      ffprobe's verdict about the file must never be remembered — if it
      is, the row stays "?" forever and combat-log upload refuses for it
      permanently.

## Combat logs

- [ ] **No webhook configured.** Clear the Discord webhook field (or use a
      fresh install), select a recording, and click **Upload combat logs**.
      Expected: a warning dialog naming the problem ("Enter a Discord
      webhook URL.") and directing you to add one in Settings. No thread is
      started, no archive is written.
- [ ] **An invalid webhook URL is refused on Save.** In Settings, paste a
      URL that is not a Discord webhook (e.g. `https://example.com/hook`,
      or `https://discord.com.evil.example/api/webhooks/1/x`) and click
      **Save**. Expected: a warning naming the problem, the dialog stays
      open, and NOTHING is written to `settings.json` — reopen Settings and
      confirm the old value is still there. Then clear the field entirely
      and Save: that must succeed, since an empty webhook simply means the
      feature is unconfigured. `parse_webhook` itself has unit tests, but
      the dialog wiring that calls it does not, so this is the only check
      that the Save path honors the validator's rejection.
- [ ] **The webhook summary label tracks what you type.** In Settings, with
      a webhook already configured, paste a *different* valid webhook URL
      over it. Expected: the summary line underneath updates immediately to
      the new webhook's id — it must not keep describing the previous one.
      Type something invalid and it reads "not configured"; clear the field
      and it reads "not configured" too. At no point does the label show the
      token portion of the URL.
- [ ] **Gamelogs folder not found.** Rename your `Gamelogs` folder (or run
      from an account with no EVE install) with no `gamelogs_dir` set in
      Settings, then click **Upload combat logs**. Expected: a warning
      dialog saying the Gamelogs folder could not be found, telling you to
      set it in Settings. Then open Settings → **Detect** next to Gamelogs
      with the real folder present: it fills in the entry. Click **Detect**
      again with the field already set to that path: a dialog says it's
      already set to the detected folder, rather than silently re-filling it.
- [ ] **A normal successful upload.** Select one or more recordings from a
      real fight, click **Upload combat logs**. Expected: status label
      steps through "Collecting combat logs…" → "Building archive…" →
      "Posting to Discord…" → a green "Posted \<name\>.zip (N KB)." message.
      In Discord, the message names the character(s) and file count, and
      the attached zip contains a `manifest.json` plus the `.txt` logs. The
      temp archive under `%LOCALAPPDATA%\...\tmp` is gone afterward.
- [ ] **Selection spanning one fight in multiple clips posts ONE archive.**
      Select three clips that together cover one continuous fight. Expected:
      a single upload covering the earliest start to the latest end across
      all three — not three separate posts.
- [ ] **No readable duration (ffprobe missing/failed).** Rename
      `bin\ffprobe.exe` in the install directory, then select a recording and
      click **Upload combat logs**. Expected: a warning dialog titled
      "Cannot determine the time window" that lists the specific recording
      filename(s) affected and mentions ffprobe. No thread is started.
      Restore the binary afterward.
- [ ] **Clicking Upload combat logs before the durations finish loading.**
      Delete `durations.json`, launch against a large folder, and click
      **Upload combat logs** immediately, while rows still read "…".
      Expected: a brief pause while just the selected recordings are
      probed, then the normal upload — NOT the "Cannot determine the time
      window" warning. That warning must only ever mean ffprobe actually
      failed.
- [ ] **Select All then Upload combat logs on a cold cache.** Same setup,
      but click **Select All** first. Expected: a busy cursor and a status
      line counting "Reading recording lengths… (n/N)" while it works —
      the window must explain itself rather than sitting frozen with no
      indication anything is happening.
- [ ] **A window matching no logs.** Pick a recording (or a time range) far
      from any real EVE session, or point Gamelogs at an empty folder, and
      upload. Expected: an info dialog "No EVE logs overlap that window,"
      showing the window in UTC and the folder path, and stating plainly
      that EVE timestamps are UTC. The status label reads "No combat logs
      found." No archive is left behind.
- [ ] **A failed post (e.g. a deleted webhook).** Configure a webhook, then
      delete it in Discord's channel settings without updating the app, and
      upload. Expected: an error dialog "Combat log upload failed" whose
      message explains the webhook is invalid/deleted, AND explicitly shows
      the archive's path so it can be uploaded by hand. Confirm the file at
      that path still exists after the dialog — a failed post must never
      delete the archive.
- [ ] **Settings dialog at 100% and 150% Windows display scaling.** Open
      Settings at each scale factor and confirm all six packed frames
      (Google account, Upload defaults, When a recording finishes, Discord
      (combat logs), Recording folder, and the Save/Cancel row) are fully
      visible with nothing clipped, and that Save/Cancel are reachable
      without resizing. A previous release shipped with a section clipped
      off the bottom of the dialog at high DPI, and the Discord
      webhook/Gamelogs fields are exactly the kind of addition that could
      reintroduce it. See the "Look and feel > Display scaling" items above
      for the general scaling checks (125%, narrow/short screens, checkbox
      clipping); this item only covers the Discord (combat logs) section
      specifically, not a duplicate of those.
- [ ] **Combat-log and YouTube uploads share one busy guard.** Start a
      combat-log upload for a large-enough window that it takes a moment,
      then immediately click **Upload Selected** (YouTube). Expected: the
      "An upload is already in progress" warning. Then do the reverse —
      start a YouTube upload, immediately click **Upload combat logs** —
      and confirm the same warning appears there too.
- [ ] **Combat-log status messages are legible in dark mode.** With Windows
      set to Dark, run a combat-log upload and watch the status line through
      "Collecting combat logs…", "Building archive…", and "Posting to
      Discord…". All three must be readable. Before this refresh the first
      of them was hardcoded to black, which was invisible on a dark
      background — this item exists to catch that regressing.
- [ ] **The Upload combat logs button survived the chrome rework.** Confirm
      it is present in the action bar, sits beside Retry on the right, and
      is NOT styled as the accent button — Upload Selected is the primary
      action.

## Upload
- [ ] **First upload triggers Google sign-in automatically, without
      Settings.** Delete `%LOCALAPPDATA%\OBSYouTubeUploader\token.json`
      first, so no token is stored. Select a recording and click **Upload
      Selected** directly — do not open Settings. Expected: the browser
      opens for Google sign-in, and once you consent, the upload proceeds
      on its own. This is the automatic reauth path in the upload worker,
      separate from the Settings → Connect Google Account button, and is
      likely the most common first-run route (install, see recordings,
      upload, never touch Settings).
- [ ] Single upload completes and the link column fills in with ↗
- [ ] **Copy link via the row's right-click context menu puts a working URL
      on the clipboard.** Right-click a row with a completed upload, choose
      "Copy link", paste elsewhere to confirm. Confirm "Copy link" is greyed
      out on a row with no link yet.
- [ ] **Open in browser via the context menu opens the video's YouTube
      page** — not the local video file. Confirm it is greyed out on a row
      with no link yet.
- [ ] **Double-clicking a row with a completed upload opens its YouTube
      link**, same destination as the context menu. Double-clicking a row
      with no link does nothing.
- [ ] Multi-select without stitch uploads each with `(1/n)` titles
- [ ] Each row gets its own correct link
- [ ] Stitch of two videos produces one upload, both rows show the same link
- [ ] Stitch finishes in seconds (stream copy, no re-encode) and the
      uploaded video plays through the join with audio in sync
- [ ] No `stitch-*` leftovers (video or concat list) in `%LOCALAPPDATA%\...\tmp`
- [ ] Killing the network mid-upload shows "retrying in Ns", then resumes
- [ ] After exhausting retries, the Retry button becomes enabled
- [ ] Retry resumes rather than restarting from 0%
- [ ] Retry of a 3-file batch that failed on file 2 uploads files 2 and 3,
      and fills in links for both
- [ ] Retry of a failed STITCHED upload re-stitches and restarts (expected —
      the temp file is deleted on failure by design)
- [ ] No `stitch-*` leftovers (video or concat list) even after a failed upload
- [ ] **Non-retryable upload failure disables Retry.** Trigger a hard API
      error rather than a network blip — either exhaust the shared daily
      quota, or revoke the app's access from your Google account's
      permissions page and then upload. Expected: a plain-language error
      dialog (not a traceback or stack trace), and the Retry button stays
      DISABLED, since retrying cannot help. This is a distinct code path
      from the "kill the network" case above — confirm Retry's state
      differs between the two.

## Delete
- [ ] Confirmation dialog lists the correct filenames
- [ ] Cancelling deletes nothing
- [ ] Confirming removes the files and refreshes the list
- [ ] A deleted file is not re-announced by the watcher

## Single instance
- [ ] Launching a second copy exits quietly with no second tray icon
- [ ] The first instance keeps working normally afterwards
- [ ] **Tray Quit actually exits.** Right-click the tray icon and choose
      Quit. Expected: the process ends, the tray icon disappears (no
      orphaned icon lingering until Explorer refreshes it away), and no
      background process remains running.

## Release
- [ ] **Version-consistency check catches a mismatch.** Bump one of
      `pyproject.toml`, `obs_youtube_uploader/__init__.py`, or
      `packaging/installer.iss`'s `AppVersion` (but not the other two),
      push, and confirm CI's "Check version consistency" step fails and
      names all three versions, including the mismatched one.
- [ ] **The app icon appears on the Start Menu shortcut and in Add/Remove
      Programs.** Run the built installer, then check the Start Menu entry's
      icon and `Settings > Apps > Installed apps`. Both should show the real
      icon rather than a generic exe icon, since `installer.iss`'s
      `UninstallDisplayIcon` reads the icon embedded by `uploader.spec`.
