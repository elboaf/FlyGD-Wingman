# Smoke checklist

Manual verification for the GUI and live upload paths, which are not
automated: doing so would need live credentials and would consume the very
upload quota the design is constrained by.

The UI itself is likewise untested by `pytest`. `tests/test_api*.py` drive
the bridge headlessly against a fake window and cover what the API *says*
and accepts; nothing under `tests/` renders the page, sends it input, opens
a native dialog, or touches the tray. There is deliberately no Playwright
and no browser toolchain. **This checklist is the only verification any of
that gets.**

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

## WebView2 runtime

The app renders its entire UI in WebView2 and has no fallback. These items
exist because the failure mode is silent: without the runtime, pywebview
logs a load failure, `webview.start()` returns normally, and the process
exits **0** — no window, no error, no crash dialog, and a success code.

- [ ] **The installer skips the bootstrapper when the runtime is already
      there.** Run with `/VERYSILENT /LOG=%TEMP%\i.log`, then
      `findstr /C:"WebView2:" %TEMP%\i.log`. Expected: exactly one line,
      "runtime already present, skipping the bootstrapper", and no
      `bootstrapper exited with` line. A bootstrapper that runs on every
      install is a several-minute delay nobody asked for.
- [ ] **LOAD-BEARING: a missing runtime produces a native dialog and a
      NON-ZERO exit.** Testable without a VM, exactly as spike Q7 did it:
      point `WEBVIEW2_BROWSER_EXECUTABLE_FOLDER` at an empty directory for
      one process and launch the installed exe from `cmd`, then read
      `echo %ERRORLEVEL%`. Expected: a native Windows message box naming
      the Microsoft Edge WebView2 runtime and its download URL, and a
      non-zero exit code. **An exit code of 0 is the defect** — that is the
      pre-refactor behaviour, and it means the pre-flight check is not
      running before `webview.start()`. Nothing is uninstalled by this test
      and the variable dies with the shell.
- [ ] **The pre-flight message box is readable and dismissible.** Confirm
      it has a title, names the runtime by its full name, shows a URL that
      can be selected or typed out, and closes on OK without leaving a
      process behind (check Task Manager).
- [ ] **CLEAN VM ONLY — DEFERRED, no VM available: the bootstrapper actually
      installs the runtime.**
      On a fresh Windows VM with no WebView2 runtime, run the installer.
      Expected: the wizard pauses briefly at the end, the log shows "runtime
      absent, running the bundled Evergreen bootstrapper" followed by
      "runtime installed successfully", and the app launches and renders.
      There is no way to fake this on a machine that already has the runtime
      — the `WEBVIEW2_BROWSER_EXECUTABLE_FOLDER` trick fools the loader, not
      the registry. **Leave this unticked rather than assuming it; it is the
      largest untested risk in the release.**
- [ ] **CLEAN VM ONLY — DEFERRED, no VM available: an offline install fails
      honestly.** Same VM,
      network disconnected. Expected: the install still completes, ONE error
      dialog explains the runtime could not be installed and gives the
      download URL, the Finished page repeats the warning, and the app is
      installed rather than rolled back. Reconnect, install the runtime by
      hand, and confirm the app then starts with no reinstallation.

## First run
- [ ] Recording folder is pre-filled from OBS config without being asked
- [ ] With OBS absent, the in-app first-run folder screen appears instead of
      a bare OS dialog — see the LOAD-BEARING first-run item under
      Settings > Folder dialogs for the full check
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

### Window chrome
- [ ] **LOAD-BEARING: the custom title bar drags the window.** The OS title
      bar is gone; dragging is the page's `pywebview-drag-region`. Grab the
      bar and move the window across two monitors. Expected: the window
      follows with no lag. This is the single most visible thing that breaks
      with a frameless window and it has no automated coverage of any kind.
- [ ] **Windows snap, as far as it goes.** `Win+Up` must maximize. `Win+Left`
      and `Win+Right` are KNOWN NOT TO WORK and are not a regression:
      half-snap needs `WS_THICKFRAME`, which a frameless window does not
      have, so Windows does not treat this window as snappable however it
      hit-tests. Only `WM_NCCALCSIZE` or giving up the custom title bar
      would recover it. Check `Win+Up` still works; do not file the others.

      Dragging the title bar to a screen edge does not snap either, and
      never has — pywebview moves the window with `SetWindowPos`
      (`util.py:280`), which never enters the OS drag loop that snap hooks
      into. An earlier version of this checklist expected it to "snap
      normally", which was never true. Confirmed against 3.0.0.
- [ ] **Resizing at 150% or 175% scaling — NOT YET VERIFIED.** Everything
      above was checked on a single 4K display at 200%, so `scale = 2.0` is
      the only factor real hardware has ever exercised; 1.5 exists only in
      the unit tests' arithmetic. Repeat the edge drags on a scaled display
      when one is available. Expected: the band stays the same apparent
      thickness. If it does not, the inset and the hit-test have diverged,
      which presents as "resizing is fiddly on that laptop" rather than as
      a bug.
- [ ] **The drag region excludes the controls.** Press and hold on the gear,
      minimize and close in turn and move the pointer a few pixels.
      Expected: none of them drags the window; each still activates on
      release.
- [ ] **The title-bar controls do what they say.** The gear opens the
      Settings route in the same window (not a second OS window), minimize
      minimizes to the taskbar, and close HIDES to the tray rather than
      exiting — confirm the process is still running and the tray icon is
      still there.
- [ ] **The window opens fully on screen.** Launch on the primary monitor,
      again with a second monitor attached, then again after disconnecting
      it. Expected: fully visible and its title bar reachable every time.
- [ ] **LOAD-BEARING: every edge and corner resizes.** Drag all four edges
      and all four corners in turn; check the pointer becomes the sizing
      arrow BEFORE the drag, not after. Expected: all eight respond.
      Frameless windows have no OS resize border — this one is a band of
      form surface left by insetting the web view, so a change to that
      inset, to the page's own edges, or to DPI handling can take the whole
      thing away silently. There is no automated coverage: CI is ubuntu and
      cannot run a message pump.
- [ ] **The window will not shrink below its floor.** Drag any edge inward
      as far as it goes. Expected: it stops at 840x625 logical, and at that
      size nothing in either pane is cut off or unreachable. Those numbers
      were measured off the real page, not derived — if the layout changes,
      they need re-measuring, and `min_size` in `ui/window.py` needs
      updating with them.
- [ ] **Maximize leaves the taskbar alone.** Maximize with `Win+Up` — NOT by
      dragging the title bar to the top edge, which does not maximize and
      never has (see the snap item above). Expected: it fills the work area
      only, and the taskbar stays visible and clickable. A borderless
      window maximizes over the taskbar unless it is explicitly clamped.
- [ ] **The inset band is not ugly.** Look at the edge of the window against
      the page. Expected: the band reads as part of the window, not as a
      misaligned frame. It matches the page background at the sides and
      bottom, but it sits above the title bar's gradient at the top, which
      is the one place it can look wrong.
- [ ] **Scrollbars are the app's, not Windows'.** Scroll a long list. The
      scrollbar must be the styled thin one, not the classic grey Windows
      scrollbar.

### Typography and layout
- [ ] **The three type steps are visibly distinct** — panel/section headings
      largest, filenames and field text body, column headers and hints
      smallest.
- [ ] **Column headers sit below the data, not above it.** The header row
      must read as quieter than the filenames beneath it. Deliberate,
      carried over from 2.2.0: headers label the data, they are not the data.
- [ ] **Machine text is monospace.** Paths, the webhook field and the
      webhook summary render in the monospace face; prose does not.
- [ ] **Display scaling at 100%, 125%, 150% and 200%.** Restart at each.
      Expected: text sharp AND the right apparent size next to Notepad;
      neither route opens larger than the screen; Title, Description,
      Stitch, the combat-log checkbox, the summary, Retry and Upload all
      fully visible with nothing clipped.
- [ ] **Nothing is clipped at the minimum window size** at 150%. The
      Description box shrinks first and the Retry / Delete row is
      still fully visible. Drag the window down to its floor (840x625
      logical) to check this — before resizing existed, "minimum" was the
      only size the window ever had and this was free; now a user can
      actually get here.

### The list
- [ ] **Clicking ANYWHERE on a row toggles it,** not just the checkbox cell.
      Rows accumulate — clicking a second must not clear the first.
- [ ] **Select all and Select none repaint every checkbox,** not just the
      summary. The two must never disagree.
- [ ] **Click-to-sort works on every column and shows direction,** on the
      active column only. Sorting is pure client state; a sort that
      round-trips to Python or clears the selection is a defect.
- [ ] **The leftmost header is a bare check, not a checkbox.** Clicking it
      SORTS by checked state — it must not select or clear anything.
- [ ] **Sorting does not affect upload order or stitch order.** Sort by each
      column, select out of displayed order, upload with Stitch off then on.
      The `(1/n)` numbering and clip order follow the underlying data.
- [ ] **Sorting by Length while durations are still loading.** Delete
      `durations.json`, launch against a large folder, click Length while
      rows read "…". Pending rows sort together and each fills in where it
      sits — rows do NOT re-order under the cursor as results arrive.
- [ ] **LOAD-BEARING: arrow keys move focus and Space toggles.** Tab in,
      move with ↑/↓, press Space. Focus is visibly distinct from "checked",
      Space toggles exactly the focused row, and Space does NOT scroll. Then
      trigger a rebuild (delete a file, or save Settings) and confirm the
      keyboard still works without touching the mouse.
- [ ] **LOAD-BEARING: the row context menu opens and dismisses cleanly.**
      Dismiss by clicking away; by Escape; and by right-clicking a different
      row while the first is open. After each, the window still responds and
      only one menu is ever visible.
- [ ] **Copy link and Open in browser work and grey out correctly.** Both
      work on a row with a completed upload, both greyed without one, and
      Copy link puts a URL that actually opens on the clipboard.
- [ ] **LOAD-BEARING: double-click opens the link and LEAVES THE CHECKBOX SELECTION UNCHANGED.**
      Tick two rows, double-click a third with a link: the browser opens and
      the third row is still unticked. Repeat on a row that starts ticked —
      still ticked afterwards. A row left changed here is a defect, not
      cosmetic.
- [ ] **Newly announced recordings are pre-checked, scrolled into view, and
      visibly highlighted** — even when below the fold.
- [ ] **Selected, focused and uploaded rows are distinguishable** from one
      another at a glance.
- [ ] **Hovering an unreadable Length explains it,** and a `…` cell reads
      "Measuring length…" instead — the two glyphs mean opposite things.
- [ ] **Hovering the link glyph explains both gestures,** and no tooltip
      appears over an empty Link cell, a filename, a header, or empty space.
- [ ] **The list at the minimum window width.** Drag the window to its floor
      (840 logical). Every column still present, Filename truncates rather
      than pushing others off, NO horizontal scrollbar. That width was
      measured as the point where this stops being true, so it is the exact
      edge — not a comfortable margin inside it.
- [ ] **The Modified column reads as relative time, not a timestamp.** It
      must say "just now" / "23h ago" / "yesterday" / "4d ago" for the last
      week, and a bare date ("Aug 13", or "2025 Nov 02" outside this year)
      beyond it. It shows the file's MTIME, which is why it must not look
      like the recording timestamp already in the filename: for a copied or
      remuxed recording the two legitimately differ by minutes or hours,
      and printing both as clock times made the app look like it was
      contradicting itself. The header must read **Modified**, not "Date".
- [ ] **Sorting by Modified still orders newest-first.** Click Modified.
      The order must follow the underlying mtime, NOT the rendered text — a
      text sort would put "2d ago" before "3h ago" and "Aug" before "Dec".
      Check with a folder holding both a recording from today and one over
      a week old.
- [ ] **The filename column does not swallow the window.** Widen the window
      well past the default. Filename must stop growing once it fits its
      text, keeping Modified/Size/Length/Link near it, rather than
      stretching and pushing them to the far edge with a gap in the middle.

### Frozen build
- [ ] **LOAD-BEARING: the installed build renders the page at all.** The
      only proof `web/` was both bundled AND loadable. CI asserts the files
      exist at `_internal\web\`; only launching proves the window finds
      them. A blank window means the datas entry resolved to the wrong
      place — and the app will still exit 0 when you close it.
- [ ] **The frozen build loads nothing from the network.** Disconnect and
      launch. The page renders identically — fonts, icons and styles local.
- [ ] **The tray icon still draws in the frozen build.** Pillow survives
      solely for the tray. Confirm the icon is the real app icon, and that
      renaming `app.ico` falls back to the drawn placeholder rather than
      breaking startup.
- [ ] **The primary action is visually distinct.** `Upload` is the
      only brand-accent control on the screen.

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
- [ ] Sign in with Google opens a browser and reports "Connected"
- [ ] **The account line names the channel once one is known.** With at
      least one completed upload, Settings must read **Connected as
      &lt;your channel&gt;**, not a bare "Connected" — the whole point is
      being able to tell WHICH account is signed in, since the app can
      otherwise upload to the wrong channel without ever saying so.
      Note it names the YouTube CHANNEL, not the Google account email:
      the app holds `youtube.upload` alone and cannot call channels.list,
      so the name is learned from an upload response.
- [ ] **Before any upload it correctly stays a bare "Connected".** Sign in
      on a profile that has never completed an upload (delete
      `channel_title` from settings.json to simulate). Expected: plain
      "Connected" with no trailing "as" and no empty gap.
- [ ] **The name appears in the session that learns it, not the next one.**
      With `channel_title` absent, sign in and complete one upload with
      Settings closed, then open Settings WITHOUT restarting. Expected:
      it already reads "Connected as &lt;channel&gt;".
- [ ] **The account button's label tracks the account state.** Not
      connected: it reads **Sign in with Google** and is clickable. While
      the lookup runs: **Checking…**, greyed. During the browser flow:
      **Waiting for browser…**, greyed, so a second press cannot start a
      second OAuth flow over the first. Once connected: **Switch account**.
      The old build showed the constant "Connect Google Account", including
      underneath the word "Connected", which said nothing about what
      pressing it would do.
- [ ] **The Discord webhook is masked by default.** Open Settings with a
      webhook already saved. Expected: the field shows bullets, not the
      URL. Tick **Show** and confirm the real value appears; close and
      reopen the dialog and confirm it is masked again. The webhook is a
      credential — anyone holding it can post to the channel.
- [ ] **Pasting into the masked webhook field still works.** Copy a webhook
      URL, paste into the masked field, confirm the line beneath resolves to
      `discord.com/api/webhooks/{id}…` (the id, never the token).
- [ ] **An invalid webhook says what is wrong.** Type `http://discord.com/api/webhooks/1/2`
      (http, not https). Expected: the line beneath reads "Webhook URL must
      use https.", not "not configured". Clear the field entirely and
      confirm it returns to "not configured".
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
- [ ] **The webhook is still masked after a route change.** Open Settings
      with a webhook saved, tick **Show**, navigate back to the list, then
      return. Expected: masked again. A revealed credential that survives
      navigation is a leak — the mockup's cleartext webhook is exactly the
      regression this port must not reintroduce.
- [ ] **The account control tracks state through the route.** Start a
      sign-in, navigate away mid-flow, return. Expected: still reads
      **Waiting for browser…** and still disabled — `onAuthState` is the
      source of truth, not the DOM that was torn down.

### Folder dialogs

Native OS dialogs opened from the page through the bridge. Nothing
automated reaches them; the bridge tests can only assert the call was made.

- [ ] **Browse picks the recording folder.** A native picker appears, modal
      to the app window, and the chosen path lands in the field. The window
      is still draggable and responsive afterwards.
- [ ] **Browse picks the Gamelogs folder,** same expectations.
- [ ] **Cancelling a Browse changes nothing** — the field keeps its previous
      value, not blank and not the dialog's starting directory.
- [ ] **Detect fills in the recording folder from OBS's own config,** and a
      second press with the field already at that path says it is already
      set rather than silently re-filling it.
- [ ] **Detect fills in the Gamelogs folder,** with the same already-set
      behaviour. With no EVE install, Detect says so rather than leaving the
      field blank with no explanation.
- [ ] **Saving a changed recording folder rebinds the live watcher.** Change
      it and Save without restarting. New recordings in the NEW folder are
      announced and the old folder is ignored. Persisting without rebinding
      is the specific failure to watch for — it looks correct until the next
      recording.
- [ ] **LOAD-BEARING: the first-run folder screen.** Delete
      `%LOCALAPPDATA%\OBSYouTubeUploader\settings.json` and launch with OBS
      absent. Expected: the window opens and shows an in-app "choose your
      recording folder" screen, from which Browse opens the native picker
      and choosing proceeds to the normal list. This is a deliberate
      behaviour change: there is no longer a bare OS dialog before any
      window exists. Confirm the screen cannot be skipped past into an
      unusable empty list.

## Video list and durations
These cover the duration cache and the background probe. Do them against a
folder with a realistic number of recordings (30+); the whole point is
behavior that only shows up at size.

- [ ] **Hovering an unreadable Length explains it.** Find a row showing `?`
      in the Length column and rest the pointer on that cell. Expected: a
      tooltip appears after a short delay saying ffprobe could not open the
      file and combat-log upload is unavailable for it. Hover a row showing
      `…` and confirm it reads "Measuring length…" instead — the two glyphs
      mean opposite things and both were previously unexplained.
- [ ] **Hovering the ↗ link glyph explains both gestures.** Rest the pointer
      on a filled Link cell. Expected: a tooltip naming double-click to open
      and right-click to copy. Confirm no tooltip appears over an empty Link
      cell, over a filename, over the column headers, or over the empty
      space below the last row.
- [ ] **Tooltips follow the theme.** With a tooltip showing, confirm it uses
      the app's colours in both Light and Dark rather than a Tk-default
      yellow, and that it disappears on click and when the pointer leaves
      the list.
- [ ] **Hovering the greyed Retry button explains why it is greyed.**
      Expected: a tooltip saying it is enabled after a failure and resumes
      rather than restarts. Disabled is its normal state, so without this it
      reads as broken.

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
      fresh install), select a recording, and press **Upload** with **Also
      post combat logs to Discord** ticked. Expected: the VIDEO uploads
      normally, and the status strip finishes on an amber "Upload complete —
      combat logs skipped: Enter a Discord webhook URL. Set it up in
      Settings." There is NO dialog, and the video half is never blocked by
      the Discord half being unconfigured — that regression is the whole
      reason the two buttons could be merged.
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
      Settings, then press **Upload** with the logs box ticked. Expected:
      the video uploads, and the strip finishes amber on "…combat logs
      skipped: your EVE Gamelogs folder was not found. Set it in Settings."
      No dialog. Then open Settings → **Detect** next to Gamelogs
      with the real folder present: it fills in the entry. Click **Detect**
      again with the field already set to that path: a dialog says it's
      already set to the detected folder, rather than silently re-filling it.
- [ ] **A normal successful upload.** Select one or more recordings from a
      real fight and press **Upload** with the logs box ticked. Expected:
      the video uploads first, the strip says "Upload complete!", and then
      it steps through "Collecting combat logs…" → "Building archive…" →
      "Posting to Discord…" → a green "Posted \<name\>.zip (N KB)." message.
      "Upload complete!" must NOT be the last thing said — a user who reads
      it as the end will close the window mid-post.
      In Discord, the message names the character(s) and file count, and
      the attached zip contains a `manifest.json` plus the `.txt` logs. The
      temp archive under `%LOCALAPPDATA%\...\tmp` is gone afterward.
- [ ] **Unticking the box uploads the video alone.** With a working webhook
      and Gamelogs folder, untick **Also post combat logs to Discord** and
      press **Upload**. Expected: the video publishes, the strip rests on
      "Upload complete!", and NOTHING is posted to Discord — check the
      channel. This is the only way to get a video without logs, so it has
      to work.
- [ ] **Selection spanning one fight in multiple clips posts ONE archive.**
      Select three clips that together cover one continuous fight. Expected:
      a single upload covering the earliest start to the latest end across
      all three — not three separate posts.
- [ ] **No readable duration (ffprobe missing/failed).** Rename
      `bin\ffprobe.exe` in the install directory, then select a recording and
      press **Upload** with the logs box ticked. Expected: the video
      uploads, then an amber "…combat logs skipped: no readable duration for
      \<filename\>…" naming the specific recordings affected and mentioning
      ffprobe. No dialog. Restore the binary afterward.
- [ ] **Uploading before the durations finish loading.** Delete
      `durations.json`, launch against a large folder, and press **Upload**
      with the logs box ticked immediately, while rows still read "…".
      Expected: after the video, a brief pause while just the selected
      recordings are probed, then the normal log post — NOT the "no readable
      duration" skip. That message must only ever mean ffprobe actually
      failed.
- [ ] **Select All then Upload on a cold cache.** Same setup,
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
- [ ] **One upload at a time, both halves included.** Start an upload with
      the logs box ticked, and while the Discord half is still posting press
      **Upload** again. Expected: the "An upload is already in progress"
      warning. Both halves run on one worker thread, so the guard that
      always covered the video now covers the log post as well.
- [ ] **Combat-log status messages are legible in dark mode.** With Windows
      set to Dark, run an upload with logs and watch the status line through
      "Collecting combat logs…", "Building archive…", and "Posting to
      Discord…". All three must be readable. Before this refresh the first
      of them was hardcoded to black, which was invisible on a dark
      background — this item exists to catch that regressing.
- [ ] **The combat-log checkbox is where the other upload options are.**
      Confirm **Also post combat logs to Discord** sits in the **Upload card
      on the right, directly under Stitch** — not in the Publish card beside
      the buttons — and that it is TICKED on a fresh launch. It is not
      persisted, so every launch starts ticked.

## Upload
- [ ] **Upload confirms before publishing anything.** Select two
      recordings and press it. Expected: a dialog naming the destination
      channel, the privacy setting, the exact title(s) that will be sent
      (including the `(1/2)` … `(2/2)` numbering), the total size and
      duration, and — while the logs box is ticked — a "Logs:" line saying
      combat logs will be posted to Discord afterwards, and a closing line
      naming BOTH as un-undoable. Untick the box and confirm both the Logs
      line and the Discord half of the closing line disappear: this dialog
      is the only disclosure that one press publishes to two places. Choose No and confirm nothing uploads. This is the app's
      only irreversible action, and deleting local files — which are
      recoverable — already confirmed.
- [ ] **The confirm is honest before the first upload.** With no upload ever
      completed, confirm the Channel line reads "not known yet (learned from
      this upload)" rather than being blank. The app holds only the
      `youtube.upload` scope, so it cannot look the channel up.
- [ ] **The destination line fills in after the first successful upload.**
      Complete one upload. Expected: the muted line above Upload
      changes from "Channel confirmed after the first upload" to
      "Uploads go to &lt;your channel&gt;", and still says so after
      restarting the app (it is persisted to settings.json). The privacy
      setting is deliberately NOT in this line; if it reappears there,
      format_destination has been reverted.
- [ ] **A batch's progress text names which file it is measuring.** Upload
      three recordings. Expected: "Uploading file 2 of 3… 41.2%", with the
      bar tracking the whole batch. The previous wording ("Uploading 2/3 —
      41.2%") sat beside a bar at a different value and read as a
      contradiction. A single-file upload reads "Uploading… 41.2%" with no
      file count.
- [ ] **The Title label warns about batch numbering.** Select one recording:
      the label reads "Title". Select ten: "Title (applies to all 10,
      numbered 1-10)". Tick **Stitch selected videos**: "Title (one stitched
      video)". Untick and confirm it reverts.
- [ ] **First upload triggers Google sign-in automatically, without
      Settings.** Delete `%LOCALAPPDATA%\OBSYouTubeUploader\token.json`
      first, so no token is stored. Select a recording and click **Upload
      Selected** directly — do not open Settings. Expected: the browser
      opens for Google sign-in, and once you consent, the upload proceeds
      on its own. This is the automatic reauth path in the upload worker,
      separate from the Settings → Connect Google Account button, and is
      likely the most common first-run route (install, see recordings,
      upload, never touch Settings).
- [ ] **The finished upload's link stays put.** Complete one upload and
      leave the window open for a minute. Expected: the row keeps its ↗ and
      its tint, and the **Open video** / **Copy link** pair stays in the
      upload panel. This is the regression to watch: `poll()` fires a
      deferred `refresh()` the moment an upload finishes, and `refresh()`
      used to clear `self.links` — so the link appeared and then vanished a
      moment later. Trigger an extra rebuild by recording something new,
      and confirm the link still survives.
- [ ] **Open video opens the uploaded video**, and **Copy link** puts the
      same URL on the clipboard with "Link copied to clipboard" in the
      status line.
- [ ] **The pair is hidden before anything has uploaded.** On a fresh start
      with no uploads this session, confirm no Open/Copy buttons are shown
      rather than two dead ones.
- [ ] **The pair points at the newest upload.** Upload two recordings
      separately and confirm Open video opens the second.
- [ ] **Deleting the recording behind the link removes the pair.** Upload a
      recording, then Delete Selected on that same row. Expected: the
      buttons disappear rather than offering to open a row that is gone.
- [ ] **Single upload completes and the link column fills in with ↗**
- [ ] **Copy link via the row's right-click context menu puts a working URL
      on the clipboard.** Right-click a row with a completed upload, choose
      "Copy link", paste elsewhere to confirm. Confirm "Copy link" is greyed
      out on a row with no link yet.
- [ ] **Open in browser via the context menu opens the video's YouTube
      page** — not the local video file. Confirm it is greyed out on a row
      with no link yet.
- [ ] **Double-clicking a row with a completed upload opens its YouTube
      link**, same destination as the context menu, and leaves the row's
      tick state unchanged. Double-clicking a row with no link does
      nothing at all — it must not leave the row ticked either.
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

## Dialogs and confirmations

Modal dialogs were native `messagebox` calls and are now in-page modals fed
by `onDialog`, with `confirm` answered by `dialog_response(id, ok)` — the one
request/response pair in an otherwise fire-and-forget protocol. A dropped
response leaves a worker waiting forever, which presents as a hung upload.

- [ ] **LOAD-BEARING: Upload confirms before publishing anything.**
      Select two recordings and press it. Expected: a modal naming the
      destination channel, the privacy setting, the exact title(s) including
      `(1/2)` … `(2/2)` numbering, the total size and duration, and the
      "Logs:" line while the combat-log box is ticked. Choose No: nothing
      uploads, NOTHING is posted to Discord, and the app is not left busy.
      Then repeat and choose Yes. This modal now guards two public actions,
      not one.
- [ ] **The confirm is honest before the first upload.** With no upload ever
      completed, the Channel line reads "not known yet (learned from this
      upload)" rather than being blank.
- [ ] **The delete confirmation lists the correct filenames,** warns it
      cannot be undone, Cancel deletes nothing, Confirm removes and
      refreshes.
- [ ] **The no-selection and busy warnings are distinct messages.** Press
      Upload and Delete selected each with nothing selected, and read both.
      Then start an upload and press the other mid-flight. These are
      several specific messages, not one generic guard.
- [ ] **Escape and the scrim answer a confirm as "no", never as nothing.**
      Both cancel cleanly and the app is immediately usable — no upload, no
      stuck busy state, and Upload works on the next press.
- [ ] **A dialog raised from a worker thread reaches the page.** Kill the
      network mid-upload and let the retries exhaust. The error modal
      appears with plain-language text, not a traceback, and the window is
      responsive behind it.

## Progress

- [ ] **LOAD-BEARING: the progress bar is indeterminate during a stitch.**
      Select two, tick Stitch, upload. While ffmpeg runs the bar animates
      continuously with NO percentage — stitching reports no progress and a
      bar sitting at 0% reads as a hang — and switches to a real percentage
      the moment the upload begins. Stitch twice in one session and confirm
      it switches back correctly.
- [ ] **Progress renders during a real upload.** Upload three recordings.
      "Uploading file 2 of 3… 41.2%" with the bar tracking the whole batch,
      updating smoothly rather than jumping only at file boundaries.
- [ ] **The window stays responsive throughout.** Mid-upload, drag the
      window, scroll the list, sort a column and open the context menu. A UI
      that stalls means work is running on the wrong thread.
- [ ] **The retry countdown is visible.** Kill the network mid-upload:
      "retrying in Ns" counting down, then a resume — not a frozen bar. When
      the retries are exhausted, Retry becomes enabled.
- [ ] **Status severity colours are distinguishable.** Force a red error, a
      green success and an ordinary status in one session. All three legible
      against the near-black ground and clearly different.

## Release
- [ ] **`uv.lock` carries the new version.** It records this project's own
      version alongside its dependencies, and CI's version-consistency check
      covers only `pyproject.toml`, `__init__.py` and `installer.iss` — so a
      bump that misses the lockfile passes CI and ships a lock claiming the
      previous version. Run `uv lock` after bumping the three, confirm the
      `obs-youtube-uploader` entry matches, and commit it with the bump.
      (It was last observed stale at `2.0.0` against `2.1.0`.)
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

## EVE bookmark hotkeys

Requires a Windows machine with EVE running. None of this is covered by
pytest — the engine is AutoHotkey.

- [ ] Bookmarks appears in the title bar; the window still drags by the
      wordmark area
- [ ] With the feature off, the status bar shows no EVE segment
- [ ] Enabling starts the engine; the status bar segment appears
- [ ] Hotkeys fire in an enabled EVE window and do nothing in an unenabled one
- [ ] **All nineteen binds do nothing when a non-EVE window is focused.**
      Registration happens inside a function called while an `IfWinActive`
      criterion is active; if that criterion does not carry into the
      function, they register globally and fire everywhere. Nothing in the
      repository can test this; confirm it by hand.
- [ ] **Set Root does nothing outside an EVE window.** It used to be
      registered with no window restriction (Step 4) and is now inside the
      per-window loop like everything else. Nothing in the route says
      "everywhere" any more.
- [ ] **Set Root still re-checks the active window.** The guard is
      unreachable on a settled configuration, so it cannot be confirmed
      from the outside — check by reading `DoSemi`. It covers the window
      between a window being disabled and the ~10s refresh that tears its
      binds down, where a press would otherwise run the whole copy/parse
      flow in whatever is focused: `Send ^c` into a chat window, and the
      root state reset.
- [ ] **There is no Copy or Paste row in the Keybinds card**, and no key
      Wingman registers sends a bare `^c` or `^v`
- [ ] **Rebinding a window-scoped hotkey stops the old key firing** — the
      direct test of the teardown repair, and the bug that shipped for years
- [ ] Disabling a window stops its hotkeys firing, within ~10s
- [ ] Every finisher produces the correct Flygd/ABH name (Protean removal)
- [ ] **Tags are written lowercase: `e`, `/`, `f`, `c`.** The class
      finishers (`H`/`L`/`N`/`13`/`C1`-`C6`) are a different code path and
      stay uppercase
- [ ] **There is no medium-hole tag** — no `M` row in Keybinds, and no key
      writes an ` M`
- [ ] **The frig tag writes `f`, not `S`.** Same bind and INI key (`FinS`),
      so an existing binding for it still works
- [ ] **Re-tagging a bookmark that already carries a legacy ` S` replaces
      it with ` f`** rather than leaving both on the line
- [ ] **There is no Bookmark naming card in the route** — home holes, the
      return-bookmark toggle and the preface field are all gone
- [ ] **Home bookmarks start at `.1`.** Fixed now, but still written into
      the INI rather than left to the engine, whose compiled default is the
      opposite. `HomeZeroIs0` is read inside a *function*, and an undeclared
      name is local in AHK v1 — if the `global` declaration is lost it reads
      as empty and the numbering silently changes, with no error anywhere.
- [ ] **Return bookmarks are NOT prefaced** — no `!`, matching the helper
      author's own script. Wingman writes `PrefaceReturn=0`; the engine's
      compiled default is `1`, so this is one the INI has to say out loud
- [ ] **Root mode reads Home/Zero, Active, or Not set** in the Root card and
      tracks Set Root / Clear Root
- [ ] Deliberately binding two actions to one key shows the collision warning
- [ ] Binding a key another application owns shows a registration failure,
      not a silently dead key
- [ ] Set Root and Clear Root from the route change the status bar values
- [ ] A second action taken immediately is not lost
- [ ] **Importing a REAL `eve_bookmark_helper.ini` reproduces that setup.**
      AutoHotkey writes it as UTF-16 LE; reading it as UTF-8 parsed nothing
      and saved that nothing over the user's settings while reporting
      success. Use a file written by the standalone script, not one retyped
      in an editor — retyping it changes the encoding and hides the bug.
- [ ] Importing a file that is not a helper INI refuses and leaves the
      existing keybinds untouched
- [ ] Importing a config with `Mode=1` says Protean naming is not supported;
      one with `Mode=2` says nothing about it
- [ ] **Reset to defaults** replaces all 21 binds after confirmation
- [ ] **Refresh** on the EVE windows card picks up a client launched while
      the route was already open
- [ ] Config changes apply within 10s without losing root or used slots
- [ ] No console window flashes when the engine starts
- [ ] Killing Wingman via Task Manager leaves the engine running; restarting
      Wingman terminates it
- [ ] With the pid file pointing at an unrelated live process, starting
      Wingman does **not** kill it
- [ ] **A hung engine is reclaimed at startup even with the feature turned
      off.** Reclamation runs unconditionally, not from the enable path;
      otherwise disabling the feature stranded a live keyboard hook.
- [ ] **Enabling with the interpreter deleted shows the reason**, not a bare
      "Stopped" — and the reason survives the next poll tick a second later
      rather than being overwritten by it
- [ ] **At 125% and 150% Windows display scaling the EVE status segment
      hides** rather than crowding the progress bar. The window's 840px
      floor is physical pixels, so the CSS viewport is 672px and 560px
      respectively. Nobody has observed this; it is reasoning only
- [ ] `AutoHotkey-COPYING.txt` and `ffmpeg-COPYING.txt` are installed beside
      the application as **files**, not as directories containing a licence

## EVE client previews

Requires a Windows machine with at least two EVE clients running. None of
this is covered by pytest: the window, the pump, and DWM compositing all
need a real desktop.

Enable previews in Settings before starting.

- [ ] Two clients running gives two previews, each showing live video, not
      a frozen frame. A still image means the thumbnail registered but the
      source is minimised or occluded — check the log for
      `DwmRegisterThumbnail failed`.
- [ ] Each preview's label shows the character name, in Inter — not a
      blocky bitmap face. A bitmap face means the bundled font did not
      load; the log says so explicitly.
- [ ] Clicking a preview brings that client to the foreground. If nothing
      happens, the log has `Activation of 0x… did not take` at debug.
- [ ] Dragging a preview moves it. Dragging near another preview or a
      screen edge snaps it flush.
- [ ] Dragging the bottom-right corner resizes it, and the video follows
      the frame rather than staying its old size or spilling past the
      border.
- [ ] Dragging a preview smaller and smaller floors it instead of
      inverting. An inverted rect makes the video vanish silently.
- [ ] Restart Wingman: previews return to their saved positions and sizes.
- [ ] Close one EVE client. Its preview disappears within ~1s; the others
      keep rendering and do not flicker or jump.
- [ ] Close every EVE client. No previews remain, nothing crashes, and
      Wingman still responds.
- [ ] Start a client again with Wingman still running: a preview appears
      for it, at its saved position if that character had one.
- [ ] Log in a character that has never been previewed while others are
      already placed: it gets a free slot rather than landing on top of an
      existing preview.
- [ ] Disable previews in Settings. Every preview vanishes and the
      `wingman-preview` thread exits — check Task Manager shows no extra
      thread and the log has no "did not exit within" warning.
- [ ] Re-enable: previews come back, still in their saved positions.
- [ ] Quit Wingman with previews enabled. The process fully exits — it
      must not linger in Task Manager after leaving the tray.
- [ ] **Two monitors at different scale factors** (e.g. 100% and 200%):
      previews land where dropped on both, at the right size, and dragging
      one across the boundary does not halve or double it. This is the
      thread-local DPI work; it is the item most likely to fail and the
      hardest to notice on a single-monitor machine.
- [ ] Check the log for one line reporting the DPI override result, and no
      repeated warnings during an idle minute — the 700ms sweep must be
      silent when nothing changes.
- [ ] Frozen build only: run the packaged app and confirm labels still
      render in Inter. The font is a `datas` entry, and PyInstaller exits 0
      when one resolves to nothing.

## EVE client window layouts

Nothing below is covered by the suite: CI is ubuntu-latest and no Win32
call runs there. Each item is a claim reasoned from documentation.

- [ ] Two clients logged in, dragged somewhere deliberate. **Save current
      positions** reports the right count. Move both, press **Restore
      now** — they go back exactly, not approximately.
- [ ] A client at character select is not counted by Save and is not
      moved by Restore.
- [ ] A **maximized** client: Save, un-maximize and move it, Restore. It
      comes back maximized, and un-maximizing lands on the saved rect.
- [ ] **Maximized across monitors**: maximize a client on the SECONDARY
      monitor, Save, un-maximize it and drag it to the primary, then
      Restore. It must come back maximized on the **secondary** monitor.
      SetWindowPlacement resolves a maximized showCmd against
      ptMaxPosition, which apply_placement seeds from the window's current
      placement — so this is the case that decides whether that seeding is
      sufficient or whether ptMaxPosition needs deriving from the saved
      rect's monitor instead.
- [ ] A **minimized** client is never restored into minimized.
- [ ] **Mixed DPI**: put one client on a 100% monitor and one on a 150%
      or 200% monitor, Save, move both, Restore. Both land exactly. This
      is the check that the per-batch PMv2 scope actually works — on a
      single-monitor machine it passes whether or not the code is right.
- [ ] **Taskbar docked top or left**, then Save and Restore. Windows must
      not drift by the taskbar's height/width. Confirms the
      SPI_GETWORKAREA conversion is applied in both directions.
- [ ] **Borderless fullscreen** client: Save and Restore. Record what
      happens — accepted, ignored, or a mode switch. This one is
      genuinely unknown and many EVE users run fullscreen.
- [ ] Enable **restore on launch**, quit a client, relaunch it. It lands
      at its saved position once, and can then be **dragged and stays
      dragged** — the place-once rule.
- [ ] With restore-on-launch on, unplug a monitor holding a saved
      position, then relaunch that client. It is skipped, not deposited
      off-screen, and the log says why.
- [ ] Save a layout, hand-edit `settings.json` to corrupt one character's
      entry, relaunch. That character is dropped; the others survive.
- [ ] Save while a client is **still loading / not responding**. Wingman's
      window stays responsive — the WPF_ASYNCWINDOWPLACEMENT and
      non-marshalling-read claims.
- [ ] Previews **disabled**: Save and Restore still work. This is the
      whole point of the manager owning its own watcher.
- [ ] Toggle restore-on-launch twice quickly; exactly one watcher runs
      and quitting Wingman leaves no process in Task Manager.
