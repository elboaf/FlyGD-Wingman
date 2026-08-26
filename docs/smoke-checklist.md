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
- [ ] **Upgrading from a pre-4.0 build replaces it rather than leaving two
      copies.** Install a pre-rename build (product name "OBS YouTube
      Uploader"), sign in and change a setting, then run the 4.0 installer
      over it. Expected: Add/Remove Programs lists exactly ONE entry, now
      named FlyGD Wingman; `%LOCALAPPDATA%\FlyGD Wingman\settings.json` and
      `token.json` exist with the same preferences, and
      `%LOCALAPPDATA%\OBSYouTubeUploader\` is gone. This is no longer a
      same-AppId upgrade the way the 2024 rebrand was: `AppId` itself
      changed to `FlyGD Wingman` in 4.0, so `RemovePredecessor()` in
      installer.iss uninstalls the old install by its old
      `AppId=OBS YouTube Uploader` first, and `paths.migrate_state_dir()`
      renames the state directory on first launch. If two entries appear,
      or the old state directory is still there afterward, one of those two
      steps is broken.
- [ ] **Upgrading resets the "start at login" task to checked, even if the
      3.x user had turned it off.** Because `AppId` changed in 4.0, Inno
      treats the install as fresh and does not carry forward [Tasks]
      selections from the predecessor; `startup` has no `unchecked` flag, so
      it defaults ticked on every install, upgrade included. Expected and
      not a bug: install 3.x, untick start-at-login (or turn it off in
      Settings), then upgrade to 4.0 without touching the wizard's task
      list. Start at login is back ON afterward. Call this out in the 4.0
      release notes so a user who wants it off knows to untick it in the
      wizard or turn it off again in Settings.
- [ ] **Upgrade from 3.x with the old build running.** Install 3.5.1, launch
      it, and leave it in the tray. Install 4.0.0 and launch it. Expected: it
      exits immediately without a window. Close the 3.x tray icon, launch
      again. Expected: it starts, `%LOCALAPPDATA%\FlyGD Wingman\` exists,
      `%LOCALAPPDATA%\OBSYouTubeUploader\` is gone, and you are still signed
      in to YouTube.
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

**Check what tree the launcher points at before you check anything else.**
`run-first-run.bat` ends with a `cd /d` to the tree it runs, and for an
unknown period it pointed at `.claude/worktrees/nav-restructure` — six
commits behind main — so every hand verification of the first-run screen
through it verified the screen that had already been replaced. Fixed
2026-08-25; the old line is kept in `run-first-run.bat.bak` with the
reason in a comment above the replacement. The launcher's target tree is
part of what these items depend on, so it is part of what you check.

**The cheap tell:** if the card has a `Set this up later` link beside
`Continue`, you are on main. If it does not, the launcher is pointed
somewhere stale and nothing on that screen is worth reviewing.
(`run-test-build.bat` points at the repository root and is unaffected.)

- [ ] Recording folder is pre-filled from OBS config without being asked
- [ ] With OBS absent, the in-app first-run folder screen appears instead of
      a bare OS dialog — see the LOAD-BEARING first-run item under
      Settings > Folder dialogs for the full check.
      **How to actually get here**, since deleting settings.json is not
      enough: `resolve_recording_dir` tries the stored setting, then OBS's
      OWN config, and only returns None when BOTH fail. On a machine with
      OBS installed, detection succeeds and first run is skipped — which is
      correct, and is why this item goes unchecked unless it says how.
      Clear the stored setting and point `APPDATA` at an empty folder;
      `obsconfig.profiles_root` reads `%APPDATA%\obs-studio\basic\profiles`
      and finds nothing. Both are per-process, so a real install is
      untouched.
- [ ] **The first-run screen asks ONLY for the recording folder.** It does
      not ask about the EVE tools: those are on for everyone, because in
      practice the people who install this play EVE. Someone who wants the
      plain uploader turns them off in Settings > General, which is checked
      under The Settings rail.
- [ ] **Set this up later leaves the screen.** With the first-run screen
      showing (the recipe above), click **Set this up later**. Expected:
      the Uploader opens, the title-bar destinations and the gear are back,
      and the Uploader shows its empty state rather than a blank list — an
      empty list with no rows and no empty state is the inert screen that
      reads as broken. Confirm `"first_run_skipped": true` is in
      settings.json before doing anything else.
      A recording folder configures the UPLOADER half, and the two halves
      are meant to be independent — someone here for previews and bookmark
      keybinds must not be gated on it every launch.
- [ ] **…and the EVE half genuinely works from there.** After skipping,
      open Settings > Bookmarks and Settings > Previews and confirm both
      are usable with no recording folder configured. This is the whole
      reason the skip exists; a skip that reaches an unusable app is the
      same gate one screen further in.
- [ ] **A skipped first run is not asked again.** Quit and relaunch with
      `APPDATA` still pointing at the empty folder. Expected: the first-run
      screen does NOT appear.
      Then choose a folder in Settings > Folders and confirm
      `first_run_skipped` returns to `false` in settings.json: choosing a
      folder answers the question the skip deferred.
- [ ] **The screen says what Wingman is.** Read the two paragraphs above
      the field as a new user would. They must name the EVE half — previews
      and bookmark keybinds — before asking for an OBS folder, and say the
      folder can be set up later. This is the only place in the app that
      introduces the product, and it is what makes the skip read as an
      offer rather than as a way to break the setup.
- [ ] **Detect says so when it finds nothing.** With `APPDATA` pointed at
      an empty folder, press **Detect**. Expected: the note under the field
      changes to say Detect could not find a recording folder and to use
      Browse. It must not sit there unchanged — a silent Detect and a dead
      button look identical, and this is the screen with no way out.
- [ ] **The note comes back after an error.** Type a path that does not
      exist and press **Continue**. Expected: the note is replaced by the
      refusal, in the error colour. Now type one more character in the
      field. Expected: the note returns to explaining Detect. Losing that
      explanation for the rest of the session is the behaviour this
      replaces.
- [ ] **Cancelling Browse keeps the path already found.** Press Detect or
      Browse until the field holds a path, then press **Browse…** again and
      cancel the picker. Expected: the field still holds the path and
      Continue is still enabled.
- [ ] **The placeholder is an example.** With the field empty, it reads
      like a Windows path rather than reporting that no folder is chosen.
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
- [ ] **The window drags by its logo.** Press and hold on the round emblem
      at the far left of the title bar and move the pointer. Expected: the
      window moves, exactly as it does from the empty space beside
      "WINGMAN". The mark is an `<img>` inside the drag region and images
      are natively draggable, so the failure mode is that dragging there
      picks up a ghost of the image instead of the window -- making the one
      spot users aim at most look like dead surface. `style.css` sets
      `pointer-events: none` and `-webkit-user-drag: none` to prevent it;
      this is the only check that would catch either being dropped.
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
      updating with them. The minimum resolves in LOGICAL units, so this is
      840x625 CSS px at every display scaling, not 840/scale — see
      `DESIGN.md`. Verified at 200%: the floor capture is 839x621 CSS.
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
      Stitch, the no-webhook note, the summary (select a row first — it is
      hidden while nothing is selected) and Upload all fully visible with
      nothing clipped. Title and Description must both fill the card's
      full width and match each other; they were 198px and 177px of a
      286px box until round 5's U3. (Retry is absent until a failure —
      see The list and Upload. The combat-log CHECKBOX is gone — logs are
      unconditional now and a configured webhook is what decides the post;
      what remains is the sentence.) The upload panel is deliberately
      narrower below 840 CSS px — 248px — so check the longest prose in
      it wraps rather than being cut off at the panel edge: clear the
      webhook first so the two-line no-webhook note is showing, which is
      the longest string the panel ever holds. NOTE: the viewport floor is
      840 CSS px at every scaling. (The 220px step is gone — it lived in a
      `max-width: 607px` block that could never fire.) 248px is
      reachable only at SOME scalings: `max-width: 839px` matches at 200%,
      where DPI rounding puts the floor at 839 CSS, and not at 100%, where
      it is 840. Expect the panel at 320px at 100% and 248px at 200%, at
      the same window size. That is a known defect (`DESIGN.md`), not
      something to verify as correct — record which you saw.
- [ ] **Nothing is clipped at the minimum window size, and Upload is above
      the fold.** Drag the window down to its floor (840x625 logical) with
      the webhook CLEARED and every row selected — that is the tallest the
      panel ever gets. Expected: no scrollbar inside the panel at all, and
      **Upload fully visible with its label**, not a sliver of accent at
      the pane's bottom edge. It used to be clipped there: the panel was
      two cards, and the most-pressed control in the app was last in a
      stack of a title, a 96px description, two checkboxes, a three-line
      webhook explanation, a summary, a second card heading and a line of
      prose. It is one card now, and **Delete selected** has moved to the
      list footer beside Select all / Select none, where the files it
      deletes are.
- [ ] **Settings rows stay usable at the window floor.** With the window at
      its floor, open Settings > Folders and Settings > Discord. Expected:
      the path and the masked webhook are both wide enough to read, with
      their buttons still beside them on the row.
      **This item used to read "at 150% scaling, with the window at its
      floor (560 CSS px)" and could not be performed.** The floor is 840
      CSS px at EVERY scaling, so a 560px viewport does not exist and
      neither does the stacked-label collapse it was checking: the
      `max-width: 720px` block that moves each label above its field
      cannot fire through the window. The labels are always in their
      shared 118px column. If you need to see the collapsed state, it is
      reachable only through the `?dev=1` harness in a resizable browser
      — and whether a rule that the window can never reach should still
      exist is the owning lane's call, not this checklist's.
- [ ] **Profiles matches Settings at the floor.** Still at the floor, open
      Profiles. Its rows carry `class="settings"` as well, so whatever
      Settings does they must do — the shared label column exists so the
      two screens line up, and a rule that reached only one of them would
      be worse than reaching neither. Check the inline hint under a field
      and any refusal message line up with the field. (This item used to
      check a stacked collapse that the window cannot reach; see above.)
- [ ] **The bind rows are stacked, and the two lists agree.** Open Settings >
      Bookmarks and read the keybind list, then Settings > Previews. Expected:
      each action or character name on its own line with its keybind button,
      Clear and Edit... on the line below — "Convert EvE-Scout Bookmarks" and
      "Finisher: C13 (shattered)" readable in one line each. Then check the
      thing this item exists for: **the keybind button starts at the same
      distance from the card's left edge in both sections**, as do Clear and
      Edit.... Do it at the floor AND at a comfortable width; the geometry
      must not change with either.
      Round 3's B1 is why. Each list was its own grid whose first column was
      sized to that list's own longest label, so Bookmarks put the button
      103.4 CSS px further right than Previews — and Previews' offset moved
      between sessions, because it tracked whichever characters were logged
      in. Stacking is the only shape that depends on no content. It is also
      no longer conditional: it used to live in a `max-width: 720px` block
      that the window can never reach (the floor is 840), so on the two
      lists that most needed it the collapse never fired at all.
      Round 5's C8 added a SECOND shape to the Bookmarks list and did not
      change this rule: the ten finishers and the four tags now render in a
      two-column block under a group heading, so their bind buttons sit at
      two x-positions rather than one. Check that both are content-
      INDEPENDENT — column one starts at the card's left edge, exactly
      where Previews' does, and column two is offset by a fixed 256px track
      that no label can move. The four rows above `FINISHERS` are still the
      original one-per-line shape and are the ones to compare against
      Previews directly.
      tests/test_page_conventions.py now requires the two grids to declare
      the same columns and both names to take their own line, so a drift
      fails the suite rather than waiting for a screenshot.

### The list
- [ ] **Clicking ANYWHERE on a row toggles it,** not just the checkbox cell.
      Rows accumulate — clicking a second must not clear the first.
- [ ] **Select all and Select none repaint every checkbox,** not just the
      summary. The two must never disagree.
- [ ] **The recording count sits beside `Select all` / `Select none`** in
      the list footer, with `Open folder` and `Delete selected` grouped at
      the right. At the 840x625 floor the footer wraps and `Delete
      selected` takes a second line, right-aligned — check it is reachable
      and does not overlap the row above.
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
- [ ] **Sorting by Length puts an hour-long recording above a 59-minute
      one.** Needs at least one recording over an hour, so it renders
      `1:03:09` rather than `17:07`. list.js sorts this column by parsing
      its own rendered cell, so a format it cannot parse does not fail
      loudly — those rows silently sort as "not measured", down with the
      `?` and `…` ones. Round 3 gave the format its hours field and
      widened the parser in the same change; this is what notices if they
      ever come apart again.

      **Run this on a COLD folder**, i.e. with `durations.json` deleted, and
      then again on a warm one. The two used to be different products and
      that is exactly what the item is now for: until round 5 `onDuration`
      pushed a raw float, so a cell filled in by a probe completing during
      the run read `3789` while the same recording read `1:03:09` after a
      restart — and the sort, which parses the cell, did nothing at all on
      a cold folder. Warm-only runs are what hid it for four rounds, so a
      cold run is the load-bearing half now.
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
- [ ] **Three Length glyphs, three different sentences.** Hover a `?`, a
      `—` and a `…` cell. `?` blames the FILE ("ffprobe could not open this
      file"); `—` blames the INSTALL ("ffprobe was not found", with
      reinstalling as the way out); `…` says "Measuring length…". The first
      two shared the `?` glyph until round 2, so a build with no ffprobe
      accused every recording in the folder of being unreadable.
      **To see `—` on purpose:** run from a source checkout with no
      `packaging/bin/ffprobe.exe` fetched and no ffprobe on PATH. Every row
      shows `—`, and the selection summary reads `0:00+` — the `+` is
      required, because without it the line states a confident zero for a
      108.8 MB recording.
- [ ] **Hovering the link glyph explains both gestures,** and no tooltip
      appears over an empty Link cell, a filename, a header, or empty space.
- [ ] **The list at the minimum window width.** Drag the window to its
      floor. Expected: **five** columns — check, Filename, Size, Length,
      Link — with **Modified absent**, and the filename shown WHOLE, with
      no ellipsis. Widen the window past ~932 CSS px and Modified comes
      back.
      **Modified giving way at the floor is the point, not a defect.** At
      840 the six-column layout put the Filename track on a 120px floor
      while an OBS filename measures 205px, so the column carrying the
      row's identity was truncated to "Fight 2026-08-24 17-57-…" — losing
      the seconds, the only characters that tell one row from another —
      while Modified sat intact beside it carrying the same timestamp in a
      friendlier form. The name floor is 212px now and Modified is what
      yields. If you see six columns at the floor, or an ellipsis in a
      filename, that is the regression.
      **This item used to demand three checks at three viewports (840 at
      100%, 672 at 125%, 560 at 150%) and two of them do not exist.** The
      floor is 840 CSS px at every scaling, so there is one width to
      check, not three, and the tier below the floor (`max-width: 767px`,
      dropping Size and Length) cannot be reached by resizing the window
      at any scaling.
      Do still restart at each scaling for the reasons in the Display
      scaling item — apparent size, sharpness, clipping — but the CSS
      width does not move.
      In every case: NO horizontal scrollbar, no column cut in half at the
      pane edge, and the header sits over the right column — a header that
      has kept a cell its rows have dropped is the specific failure the
      shared grid template exists to prevent.
      Widen the window back up and confirm the columns come back.
- [ ] **The Modified column reads as relative time, not a timestamp.**
      Widen the window past ~932 CSS px first — Modified is not rendered at
      the floor any more (see the item above). It
      must say "just now" / "23h ago" / "yesterday" / "4d ago" for the last
      week, and a bare date ("Aug 13", or "2025 Nov 02" outside this year)
      beyond it. It shows the file's MTIME, which is why it must not look
      like the recording timestamp already in the filename: for a copied or
      remuxed recording the two legitimately differ by minutes or hours,
      and printing both as clock times made the app look like it was
      contradicting itself. The header must read **Modified**, not "Date".
- [ ] **Sorting by Modified still orders newest-first.** Widen the window
      until Modified is showing, then click it.
      The order must follow the underlying mtime, NOT the rendered text — a
      text sort would put "2d ago" before "3h ago" and "Aug" before "Dec".
      Check with a folder holding both a recording from today and one over
      a week old.
- [ ] **The filename column does not swallow the window.** Widen the window
      well past the default. Filename must stop growing once it fits its
      text, keeping Modified/Size/Length/Link near it, rather than
      stretching and pushing them to the far edge with a gap in the middle.
- [ ] **The empty state names the folder it watched.** Point the app at a
      folder with no recordings in it. Expected: "No recordings in
      &lt;the full path&gt;." with the path in the monospace face, and a second
      line offering Open folder and Settings › Folders. It must name the
      actual folder, not "the watched folder" — this is the screen a
      first-run user lands on straight after nominating one, so it is where
      a wrong pick shows up, and it was the one place that did not say
      which folder it meant.
      Then check the other half: with NO folder configured at all (the
      skipped first run recipe under First run), it must read "No recording
      folder is set yet." and point at Settings rather than naming an empty
      path.
      At 150%, confirm a long path wraps inside the pane instead of running
      off the edge — a Windows path has no spaces to break at.
- [ ] **The panel's empty-folder note reads as its own paragraph.** Same
      empty folder, now look at the PANEL. Expected: "There are no
      recordings in this folder yet…" with a clear blank line between it
      and the `Title` label below. It used to sit exactly one line-pitch
      above the label — measured 0px of margin — so `Title` read as the
      paragraph's third line. The form stays rendered and typeable on
      purpose (typing a title is an action that can be carried out); this
      is spacing only.
- [ ] **Neither field repeats its own label.** Look at `Title` and
      `Description` with the panel empty. Expected: no placeholder text
      inside either box. `Title` used to hold "Title for this upload"
      under a card headed "This upload" and a label reading "Title" —
      the same word three times. Optionality now sits on the
      `Description (optional)` label, where it survives the field being
      typed in.
- [ ] **The stitch checkbox explains itself by being greyed out.** Select
      one recording. Expected: `Stitch selected into one video` is greyed
      and there is NO sentence under it. The old two-line hint sat between
      the last field typed and the button clicked, stating a precondition
      the greyed label already shows. With two selected the checkbox goes
      live and there is still no sentence.
- [ ] **Open folder opens the watched folder.** Press it in the list footer
      with a folder configured: Explorer opens on that folder. This is the
      only affordance on this screen that reaches the FILES — double-click
      and both context-menu entries all act on the YouTube link.
      Then the two refusals, which report on the status strip and must NOT
      raise a dialog: with no folder set, "No recording folder is set.
      Choose one in Settings."; with the configured folder renamed or
      deleted while the app runs, "That folder is gone: &lt;path&gt;".

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
- [ ] A non-numeric category is rejected with a warning
- [ ] **The category row does not ask for a YouTube API number.** Settings >
      Uploads. Expected: the label reads "YouTube category", and the line
      under the row says what the number is and that 20 is the one to leave
      it on. It used to read "Category ID" with "(20 = Gaming)" beside it —
      one disclosed value out of a list this screen will not show, for an
      audience defined by wormhole multiboxing rather than by fluency in the
      YouTube Data API.
- [ ] **The webhook is still masked after a route change.** Open Settings
      with a webhook saved, tick **Show**, navigate back to the list, then
      return. Expected: masked again. A revealed credential that survives
      navigation is a leak — the mockup's cleartext webhook is exactly the
      regression this port must not reintroduce.
- [ ] **…and after a SECTION change.** Same, but instead of leaving
      Settings, click **Folders** in the rail and come back to Discord.
      Expected: masked again. Leaving the section fires no route change at
      all, so this is a separate path from the one above.
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
      value, not blank and not the dialog's starting directory, and nothing
      is written.
- [ ] **Browse and Detect COMMIT the folder.** There is no Save button;
      picking a folder applies it. Confirm `settings.json` has the new path
      before touching anything else.
- [ ] **Typing a folder does NOT commit on blur.** Type a path into
      Recordings and click away WITHOUT pressing Enter. Expected: the text
      stays, and a line appears saying to press Enter. Nothing is written.
      This is deliberate and load-bearing: committing a half-typed path
      that happens to name a real directory rebinds the watcher, and
      `Watcher.rebind` marks every file already in that folder as seen —
      silently suppressing the announcement for every recording that
      arrived this session, then doing it again to the right folder on the
      corrective commit. It cannot be undone from the UI.
- [ ] **Enter commits it.** Press Enter in the same field. Expected: the
      message clears and the path is written.
- [ ] **Detect fills in the recording folder from OBS's own config,** and a
      second press with the field already at that path says it is already
      set rather than silently re-filling it.
- [ ] **Detect fills in the Gamelogs folder,** with the same already-set
      behaviour. With no EVE install, Detect says so rather than leaving the
      field blank with no explanation.
- [ ] **A changed recording folder rebinds the live watcher.** Change it
      (Browse, or type and press Enter) without restarting. New recordings
      in the NEW folder are announced and the old folder is ignored.
      Persisting without rebinding is the specific failure to watch for —
      it looks correct until the next recording.
- [ ] **Re-committing the SAME folder does not rebind.** Press Enter in the
      Recordings field without changing it. Expected: nothing happens.
      A rebind here would re-baseline `seen` and swallow anything recorded
      since launch that has not yet been polled.
- [ ] **LOAD-BEARING: the first-run folder screen.** Delete
      `%LOCALAPPDATA%\FlyGD Wingman\settings.json` and launch with OBS
      absent. Expected: the window opens and shows an in-app "choose your
      recording folder" screen, from which Browse opens the native picker
      and choosing proceeds to the normal list. This is a deliberate
      behaviour change: there is no longer a bare OS dialog before any
      window exists. It CAN be left without choosing — "Set this up later"
      is deliberate, and is checked under First run — but confirm that
      leaving it that way lands on the Uploader's empty state and not on a
      blank list.

## Video list and durations
These cover the duration cache and the background probe. Do them against a
folder with a realistic number of recordings (30+); the whole point is
behavior that only shows up at size.

- [ ] **The column headers sit over their own data — with the list long
      enough to scroll.** Fill the folder with 30+ recordings so a
      scrollbar appears, then compare each header's text with the column
      under it. Expected: `Size` and `Length` right-align with their
      numbers, and `Filename` with its names, to within about 2px (that 2
      is `.list-row`'s own transparent left border, which is also what
      marks a selected row).
      **A short list is not a test of this.** The bug was the scrollbar
      narrowing the scroller while the header, which sits outside it, kept
      the full width — so with fewer rows than fill the pane it did not
      reproduce at all, which is how a previous round measured it away.
      Check both: the columns must not shift sideways as the folder grows
      past the fold either.
- [ ] **And at a wide window.** Same list, window dragged out to 1300px or
      more. Expected: still aligned. This is a different cause with the
      same symptom — the name column's cap is measured in `ch`, which
      resolves per font, so a header set in a smaller face computed a
      different maximum and parted company with its data only once the
      column got wide enough to reach that cap.
- [ ] **There is no `Modified` column at any width.** Expected: five
      columns — the tick, `Filename`, `Size`, `Length`, `Link` — at every
      window size, wide or at the floor. The recording's timestamp is in
      its filename; the column printed it twice. Note what goes with it:
      there is no longer a way to sort by file mtime, and the list's
      default order (newest first) is what that control used to restore.
- [ ] **Hovering an unreadable Length explains it.** Find a row showing `?`
      in the Length column and rest the pointer on that cell. Expected: a
      tooltip appears after a short delay saying ffprobe could not open the
      file and combat-log upload is unavailable for it. Hover a row showing
      `…` and confirm it reads "Measuring length…" instead — the two glyphs
      mean opposite things and both were previously unexplained.
- [ ] **A build with no ffprobe says so, and does not blame the files.**
      Run from a source checkout with no `packaging/bin/ffprobe.exe` and no
      ffprobe on PATH. Expected: every row shows `—`, NOT `?`, and hovering
      one says ffprobe was not found and that reinstalling restores
      lengths. Select a row: the summary must read `0:00+` — with the
      `+`. Both halves shipped wrong until round 2, because a probe that
      reached no verdict was rendered identically to one that read the
      file and failed: every row accused its own recording, and the
      summary stated a confident zero for a 108.8 MB file.
- [ ] **Hovering the ↗ link glyph explains both gestures.** Rest the pointer
      on a filled Link cell. Expected: a tooltip naming double-click to open
      and right-click to copy. Confirm no tooltip appears over an empty Link
      cell, over a filename, over the column headers, or over the empty
      space below the last row.
- [ ] **Tooltips follow the theme.** With a tooltip showing, confirm it uses
      the app's colours in both Light and Dark rather than a Tk-default
      yellow, and that it disappears on click and when the pointer leaves
      the list.
- [ ] **Retry is not on screen at all until something has failed.** On a
      fresh start, the panel's single card shows **Upload** and nothing
      under it but the destination line — no greyed Retry. Retry is
      enabled only after a failure in this session, which for most users is
      never. It is hidden, not greyed: there is no tooltip to hover, and
      tabbing through the panel must skip it entirely.
      (**Delete selected** is no longer beside it. It deletes files from
      disk, so it moved to the list footer beside Select all / Select none,
      where the files it acts on are.)

- [ ] **The window opens immediately on a large folder.** Launch with 30+
      recordings and no `durations.json` (delete it from
      `%LOCALAPPDATA%\FlyGD Wingman\` first). Expected: the list
      appears at once with every row present, Length reading "…", and
      the values filling in over the next few seconds. The window must be
      draggable and scrollable the whole time — never a frozen white
      rectangle.
- [ ] **A second launch is instant.** Restart the app without changing the
      folder. Expected: durations are already filled in on first paint, no
      "…" at all, and no visible ffprobe activity.
- [ ] **Changing a setting does not re-freeze the list.** With the same
      large folder, open Settings and change privacy. Expected: the list
      refreshes instantly with durations still shown; no pause. Each field
      writes only its own key now, so nothing here should trigger the
      ffprobe sweep that the whole-document save used to run on every
      Save.
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
      fresh install), select a recording, and press **Upload**. Expected:
      the VIDEO uploads normally and the status strip finishes on a green
      `Uploaded "<your title>" to YouTube.` and **nothing about logs at
      all**. There is NO dialog, no amber strip, and the video half is
      never blocked by the Discord half being unconfigured — that
      regression is the whole reason the two buttons could be merged.
      The silence is deliberate and `Api._post_combat_logs` says why: with
      the checkbox gone nobody *asked* for logs on this run, so reporting
      them as "skipped" would put a warning on every upload a webhook-less
      install ever performs. The fact belongs on the panel note, where it
      is true all the time.
      Configured-and-broken is the other half of that rule and does earn a
      strip — `Uploaded "…" to YouTube. Combat logs skipped: … Set it up in
      Settings.` in amber. Reaching it by hand needs a settings.json edited
      outside the app, because the field below now refuses to store a
      webhook that does not parse; `test_a_webhook_that_does_not_parse_
      still_warns` is what actually holds that branch.
      (This item used to claim the amber line for the EMPTY case and to
      name a checkbox removed by Uploader 8. Both were wrong; corrected in
      round 3's L7 while rewriting the string it quoted.)
- [ ] **An invalid webhook URL is refused.** In Settings > Discord, paste
      a URL that is not a Discord webhook (e.g. `https://example.com/hook`,
      or `https://discord.com.evil.example/api/webhooks/1/x`) and press
      **Enter**. Expected: an INLINE message under the field naming the
      problem — not a modal dialog — and NOTHING written to
      `settings.json`. Reopen Settings and confirm the old value is still
      there. `parse_webhook` has unit tests; the wiring that calls it does
      not, so this is the only check that a refusal is honored.
- [ ] **The message is inline, and does not stack.** Type a partial URL and
      press Enter several times. Expected: one message that updates in
      place. The old path routed refusals through the modal dialog QUEUE,
      so repeated failures piled dialogs on top of each other.
- [ ] **Clearing the field does NOT wipe a configured webhook.** With a
      webhook saved, select all, Delete, then click away. Expected: nothing
      is written and the stored webhook survives — reopen and confirm. This
      is the guard that replaced the old "empty means unconfigured"
      behaviour: with no Cancel button and no pre-edit copy anywhere on the
      page, a stray edit used to destroy a credential with no way back.
- [ ] **Remove clears it.** Press **Remove** next to the field. Expected:
      the webhook is cleared and the status line says not configured.
      Removal is an explicit action now, never a side effect.
- [ ] **The webhook summary label tracks what you type.** In Settings, with
      a webhook already configured, paste a *different* valid webhook URL
      over it. Expected: the summary line underneath updates immediately to
      the new webhook's id — it must not keep describing the previous one.
      Type something invalid and it reads "not configured"; clear the field
      and it reads "not configured" too. At no point does the label show the
      token portion of the URL.
- [ ] **Gamelogs folder not found.** Rename your `Gamelogs` folder (or run
      from an account with no EVE install) with no `gamelogs_dir` set in
      Settings, then press **Upload**. Expected:
      the video uploads, and the strip finishes amber on "…combat logs
      skipped: your EVE Gamelogs folder was not found. Set it in Settings."
      No dialog. Then open Settings → **Detect** next to Gamelogs
      with the real folder present: it fills in the entry. Click **Detect**
      again with the field already set to that path: a dialog says it's
      already set to the detected folder, rather than silently re-filling it.
- [ ] **A normal successful upload.** Select one or more recordings from a
      real fight and press **Upload**. Expected:
      the video uploads first, the strip says `Uploaded "<your title>" to
      YouTube.`, and then it steps through "Collecting combat logs…" →
      "Building archive…" → "Posting to Discord…" → a green
      `Uploaded "<your title>" to YouTube. Posted \<name\>.zip (N KB).`
      The upload line must NOT be the last thing said on its own — a user
      who reads it as the end will close the window mid-post — and the
      line that IS last still names the upload first (round 3, finding 13).
      In Discord, the message names the character(s) and file count, and
      the attached zip contains a `manifest.json` plus the `.txt` logs. The
      temp archive under `%LOCALAPPDATA%\...\tmp` is gone afterward.
- [ ] **~~Unticking the box uploads the video alone.~~ REMOVED — there is
      no box.** Uploader 8: the checkbox had no true second state ("there
      is no scenario where I don't want to upload logs also"), so logs are
      unconditional and a configured webhook is what decides the post. The
      way to get a video without logs is to have no webhook configured;
      that case is checked immediately below.
- [ ] **Selection spanning one fight in multiple clips posts ONE archive.**
      Select three clips that together cover one continuous fight. Expected:
      a single upload covering the earliest start to the latest end across
      all three — not three separate posts.
- [ ] **No readable duration (ffprobe missing/failed).** Rename
      `bin\ffprobe.exe` in the install directory, then select a recording and
      press **Upload**. Expected: the video
      uploads, then an amber "… Combat logs skipped: no readable duration for
      \<filename\>…" naming the specific recordings affected and mentioning
      ffprobe. No dialog. Restore the binary afterward.
- [ ] **Uploading before the durations finish loading.** Delete
      `durations.json`, launch against a large folder, and press **Upload**
      immediately, while rows still read "…".
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
- [ ] **Settings at 100% and 150% Windows display scaling.** Open Settings
      at each scale factor and walk every rail entry — Account, Uploads,
      Folders, Discord, Bookmarks, Previews, General. Confirm each
      section's content is fully visible with nothing clipped, and that the
      rail itself is never pushed off the top by a long section. A previous
      release shipped with a section clipped off the bottom at high DPI,
      back when this screen was one long column; the rail is what replaced
      that column, and the pane is the only thing that scrolls. See the
      "Look and feel > Display scaling" items above for the general scaling
      checks — this item covers the rail specifically, not a duplicate of
      those.
- [ ] **The Settings rail is as tall as its entries, and the ship fills the
      rest.** Round 5's G3-rail and G2. Open Settings on Account, Discord or
      General: the rail ends just below **General** rather than running to
      the status strip, and the space below and right of it is page wash
      with the ship watermark in the lower right — not a bordered box beside
      a void. Then click **Bookmarks** and **Previews**: those two scroll,
      so the watermark is **absent** on them by design. Scroll one of them
      to the bottom and confirm no part of the ship appears between the
      cards. The rail must still not scroll away at the top on any section.
- [ ] **One upload at a time, both halves included.** Start an upload with
      a webhook configured, and while the Discord half is still posting press
      **Upload** again. Expected: the "An upload is already in progress"
      warning. Both halves run on one worker thread, so the guard that
      always covered the video now covers the log post as well.
- [ ] **Combat-log status messages are legible in dark mode.** With Windows
      set to Dark, run an upload with logs and watch the status line through
      "Collecting combat logs…", "Building archive…", and "Posting to
      Discord…". All three must be readable. Before this refresh the first
      of them was hardcoded to black, which was invisible on a dark
      background — this item exists to catch that regressing.
- [ ] **There is no combat-log checkbox, and the fact is on the panel.**
      With a webhook configured, the panel's card holds Title, Description,
      Stitch, Upload — and, once something is selected, the selection
      summary above it — and nothing about logs.
      Clear the webhook in Settings › Discord: a note appears under Stitch
      reading "No Discord webhook is configured, so combat logs are not
      posted. Set one in Settings › Discord." Put the webhook back and the
      note goes, with no restart.
      **The note is load-bearing, not decoration.** With no checkbox,
      `Api._post_combat_logs` is deliberately SILENT on a webhook-less
      install — a "combat logs skipped" strip after every upload, forever,
      is the recurring-failure pattern it exists to avoid — so the panel
      note is the only place the fact is stated. If the note is missing,
      the feature fails without saying so anywhere.
      The note tests only whether a webhook is STORED. A webhook that is
      stored but does not parse gets no note here — the confirm dialog
      reports that case, and a genuine post failure still earns its WARNING
      strip. Checked under Upload.

## Upload
- [ ] **Upload confirms before publishing anything.** Select two
      recordings and press it. Expected: a dialog naming the destination
      channel, the privacy setting, the exact title(s) that will be sent
      (including the `(1/2)` … `(2/2)` numbering), the total size and
      duration, and — when a webhook is configured — a "Logs:" line saying
      combat logs will be posted to Discord afterwards, and a closing line
      naming BOTH as un-undoable. Clear the webhook and confirm both the
      Logs line and the Discord half of the closing line disappear: this
      dialog is the only disclosure that one press publishes to two places,
      and since the checkbox went it is the webhook alone that decides.
      Choose No and confirm nothing uploads. This is the app's
      only irreversible action, and deleting local files — which are
      recoverable — already confirmed.
- [ ] **With NO webhook configured, the confirm says the logs will be
      SKIPPED.** Clear the webhook in Settings > Discord and press Upload.
      Expected: the "Logs:" line reads "skipped — no Discord webhook is
      configured (set one in Settings)", and the closing line names
      YouTube ONLY. It must not promise a Discord post.
      This is the fresh-install state, and the dialog used to promise the
      post regardless — so every upload ended on a WARNING strip reading
      "combat logs skipped: …", which looks like a recurring failure
      rather than an unconfigured option. Also try a webhook that is
      not a valid Discord URL: the confirm parses it with the same
      function the upload half gates on, so a typo must read as skipped
      too, not as configured.
- [ ] **The confirm's five values line up.** Same dialog. Expected: the
      values after `Channel:`, `Privacy:`, `Title:`, `Total:` and `Logs:`
      all start at the SAME x, and the `(set one in Settings)` second line
      of the no-webhook branch starts there too. The separator is a tab,
      not spaces, so this is also the check that Inter actually loaded: the
      alignment rides on `tab-size` stops measured in the current font's
      space width, and under a fallback face `Channel:` crosses into the
      next stop and its value sits ~27 px right of the other four. A
      staircase here means the bundled font is missing (the failure #72
      fixed), not that the string is wrong.
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
      Settings.** Delete `%LOCALAPPDATA%\FlyGD Wingman\token.json`
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
- [ ] **The finished upload's link survives a RESTART.** After the above,
      quit from the tray and start the app again. Expected: that row still
      carries its ↗, double-click still opens the video, and right-click →
      Copy link still gives the same URL. Round 5's link-state: the link
      used to live only in `RowSnapshot._links`, so the column was empty on
      every launch and the question it exists to answer — *did I already
      upload this fight?* — was unanswerable in the normal case.
      `%LOCALAPPDATA%\FlyGD Wingman\links.json` is the store; deleting
      it must cost the links and nothing else, so try that too and confirm
      the list still renders with an empty Link column.
- [ ] **A re-recording at the same filename shows NO link — in the same
      session AND after a restart.** Upload a recording, then make OBS write
      a new file over that same name (or copy a different recording onto
      it). Expected: the Link cell is **empty**, not the old video, without
      restarting; then restart and confirm it is still empty. The store is
      keyed on `(size, mtime)` rather than the path precisely so this cannot
      serve the previous fight's link — the one failure here sends the user
      to the wrong video, which is why it is worth reproducing by hand.
      **Both halves, because they have different mechanisms and the
      same-session one nearly shipped broken:** across a restart the store
      is the only source, but within a session `RowSnapshot._links` is keyed
      by PATH and survives the rebuild, so the row would inherit the old
      link unless the refresh actively clears it.
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
- [ ] After exhausting retries, the Retry button APPEARS beside Delete
      selected, which gives up its full width to make room
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
      ABSENT, since retrying cannot help. This is a distinct code path
      from the "kill the network" case above — confirm Retry's state
      differs between the two.

- [ ] **Stopping an upload says how much of it landed.** Start a batch of
      three or four recordings and press **Cancel** while the second or
      third is going up. Expected: the strip reads
      `Stopped. 2 of 4 uploaded.` in amber, the bar stays where it got to
      rather than resetting to 0, and **Retry does not appear** — a stop is
      not a failure. Then check YouTube: the recordings that finished are
      still there, and their rows still carry their `↗`. This is the whole
      point of the wording. A message implying nothing happened would be
      the opposite of what is true on the channel, and there is nothing
      else on screen that says otherwise.
      The stop is noticed at a 4 MiB chunk boundary, so on a fast link a
      small file can finish before the cancel lands — use large recordings
      or a throttled connection, and expect a beat between the click and
      the strip changing.
- [ ] **Cancel appears only while the upload is actually going, and takes
      Retry's place.** Watch the slot beside **Upload** through a whole
      job. Expected: at rest, `Retry` (disabled) and no Cancel; during the
      upload, `Cancel` and no Retry; when it ends — successfully, by
      failure, or by being stopped — Cancel is gone again. The two are
      never on screen together.
- [ ] **Cancel is NOT offered while a stitch is running.** Select two or
      more recordings, tick **Stitch**, and press Upload. Expected: while
      the strip reads `Stitching with FFmpeg…` there is no Cancel; it
      appears only once the join is done and the upload of the merged file
      begins. ffmpeg has no interruption seam here, and a Cancel that did
      nothing for the minutes a join takes would be worse than none.
- [ ] **A finished upload stops looking like an armed one.** Upload a
      single recording and watch the PANEL, not the strip. Expected: the
      selection clears, the summary **disappears** (round 5's U4: with
      nothing selected it said "Nothing selected" directly above a greyed
      Upload, stating one fact twice in two treatments), and **Upload goes
      inert**. Before round 3 the post-success screen was
      near-identical to the pre-upload one — same `1 selected · … · …`
      above a live, saturated button — and the only evidence of success
      was a 14px grey arrow in the narrowest column. A stopped job must
      NOT do this: the selection stays, because which files went and which
      did not is exactly what matters then.

## Delete
- [ ] **`Delete selected` is visibly the destructive one.** Look at the
      four footer buttons together. Expected: `Delete selected` carries the
      red outline and label (`.btn.danger`), and the other three do not.
      It used to be pixel-identical to `Select all` beside it — four
      buttons of equal weight, one of which destroys recordings. Profiles'
      `Delete` is the reference; the two must match.
- [ ] **It still confirms exactly once.** The treatment is appearance only.
      Expected: one confirmation, naming every file, from Python's own
      dialog — not two, and not the page's `WM.confirm`.
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

- [ ] **No progress control is drawn at rest.** Round 5's G1. On a fresh
      launch the strip reads **Idle** with nothing to its right — no groove,
      no percentage. The bar appears when an upload or stitch starts and
      goes again when the strip clears. Then the error case, and **it must
      be a STITCH failure, not an upload one**: exhausted retries raise
      `UploadFailed`, which pushes no progress at all and leaves the bar
      frozen at its last percentage, so killing the network tests nothing
      here. Tick **Stitch** on two recordings and make ffmpeg fail (point
      `ffmpeg_bin` at a missing binary, or remove a source mid-join).
      That reaches the one push this item is about, and the red line must
      not be followed by an empty groove sitting at 0%.
- [ ] **Cancel before the first chunk leaves no empty bar.** The second
      state that reaches the same rule. Start an upload and press **Cancel**
      immediately, before any percentage appears: the strip says nothing was
      uploaded and draws no bar. Cancel *after* a percentage has shown and
      the bar must instead stay where it was — the ground the job covered is
      kept, and only zero ground means no bar.
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
      the retries are exhausted, Retry appears.
- [ ] **Status severity colours are distinguishable.** Force a red error, a
      green success and an ordinary status in one session. All three legible
      against the near-black ground and clearly different.
- [ ] **LOAD-BEARING: a finished job does not follow you around.** Round 3's
      finding 14: a green `Posted combatlogs-….zip (15 KB).` and a bar at
      100% were still on screen in a capture of a *different folder with
      zero recordings*, and again on Profiles and Skills. Complete one
      upload, then click Skills, Profiles and the gear. The strip must read
      **Idle** with no progress bar drawn at all and no percentage on each,
      and stay Idle
      when you come back. It clears on leaving the route, so the completion
      is still there while you are looking at the folder it was about.
- [ ] **LOAD-BEARING: a job still running is never cleared.** The opposite
      case, and the reason this is not just "clear on every route change".
      Mid-upload, click Skills and back: the percentage and the bar are
      exactly where they were, still counting. Then the harder one —
      **during a stitch**, which reports no progress at all and can go
      minutes between pushes, so a cleared strip would leave the app looking
      idle with nothing due to repaint it. Switch route mid-stitch: the bar
      must still be animating and the text must still say
      `Stitching with FFmpeg…`.
- [ ] **A successful upload is announced as one.** Round 3's finding 13: the
      strip used to end on `Posted combatlogs-….zip (15 KB).` — the words
      *uploaded*, the title and *YouTube* appeared nowhere on the app's one
      irreversible action. Upload one recording with a webhook configured:
      the last line reads `Uploaded "<your title>" to YouTube. Posted
      combatlogs-….zip (…).` Upload two without stitching: `Uploaded 2
      recordings to YouTube.` — no title, because build_body numbers them
      and there is no single name to give. With Stitch on, two recordings
      are one video and the title comes back.
- [ ] **A skipped log half still says the upload worked.** Point Gamelogs at
      nothing and upload: `Uploaded "…" to YouTube. Combat logs skipped: …`
      in amber, no dialog. The sentence must open with the upload.

## Release
- [ ] **`uv.lock` carries the new version.** It records this project's own
      version alongside its dependencies, and CI's version-consistency check
      covers only `pyproject.toml`, `__init__.py` and `installer.iss` — so a
      bump that misses the lockfile passes CI and ships a lock claiming the
      previous version. Run `uv lock` after bumping the three, confirm the
      `wingman` entry matches, and commit it with the bump.
      (It was last observed stale at `2.0.0` against `2.1.0`.)
- [ ] **Version-consistency check catches a mismatch.** Bump one of
      `pyproject.toml`, `wingman/__init__.py`, or
      `packaging/installer.iss`'s `AppVersion` (but not the other two),
      push, and confirm CI's "Check version consistency" step fails and
      names all three versions, including the mismatched one.
- [ ] **The app icon appears on the Start Menu shortcut and in Add/Remove
      Programs.** Run the built installer, then check the Start Menu entry's
      icon and `Settings > Apps > Installed apps`. Both should show the real
      icon rather than a generic exe icon, since `installer.iss`'s
      `UninstallDisplayIcon` reads the icon embedded by `uploader.spec`.

## The Settings rail

Bookmarks and Previews stopped being top-level destinations and became
sections here. Nothing in pytest executes the page, so the wiring below is
only ever checked by hand.

- [ ] **Settings opens on Account, not General.** Press the gear from any
      destination. Expected: the Account pane is showing and Account is the
      highlighted rail entry, on the FIRST open of a session.
      General's whole content is one checkbox for turning the EVE half off;
      it is a legitimate control and a poor first impression of the app's
      configuration surface. This is also the fact `WM.current_section`
      declares in app.js — the two disagreed, silently, and
      tests/test_page_conventions.py now holds them in step. If the pane
      and the highlight ever disagree with each other, that test has been
      bypassed rather than the markup being wrong.
- [ ] **Seven rail entries, General last** — Account, Uploads, Folders,
      Discord, Bookmarks, Previews, General — and clicking each shows its
      content with exactly one entry highlighted. Notifications was the
      eighth and is gone: its one radio pair now sits under Uploads as the
      second card, `When a recording finishes`. Check it is there and that
      picking an option still sticks across a restart.
      General is last because its only content is the switch that hides
      Bookmarks and Previews: untick it and the rail must lose its tail,
      not open a hole in its middle. If that count is wrong,
      trust the rail and fix this line: it said seven for exactly as long
      as it took to add General one commit later, which is the drift this
      checklist exists to catch elsewhere.
- [ ] **No card heading repeats the rail entry you just clicked.** Walk the
      rail and read the first heading in each pane. Folders and Discord both
      repeated themselves ("Folders" / "Folders", "Discord" / "Discord
      (combat logs)"), which DESIGN.md forbids in as many words and which
      spends the one line that could say what the card does. Expected now:
      "Where your recordings and gamelogs live" and "Where combat logs are
      posted". tests/test_settings_page.py holds this mechanically; what it
      cannot judge is whether the replacements read well at the window
      floor, where they wrap.
- [ ] **Bookmarks and Previews render their real data**, not empty shells:
      the keybind rows, the EVE window list, the per-character preview
      keybinds. Both used to load on entering their own route; they load on
      entering their SECTION now, and a mis-wired listener shows an empty
      pane with no error anywhere. That silence is the failure mode: a
      handler that throws mid-module takes every registration below it with
      it, and the route loads as an inert copy of itself.
- [ ] **An armed capture is purple-ringed, and its label is not purple.**
      Click a keybind button so it reads "Press a key…". Expected: a purple
      border and a lifted background, with the label in ordinary white
      text. The label used to be `--brand-text` too, which measures 4.16:1
      on that background and 3.99:1 with the pointer on it — both under
      4.5:1, on the one control in the app that is asking to be read.
      Pick a row with **no clash warning** first, then repeat on a
      **clashing** one — D7 gave the two states separate channels, so that
      row is expected to show the **purple** border with the label still in
      the clash **red**. Before D7 it took the clash red for both and the
      armed state was invisible, which is why this step used to say to
      avoid such a row.
- [ ] **A disabled control looks disabled and stays inert under the
      pointer.** Hover each control the page switches off: `Upload` with
      nothing selected, `Show` / `Remove` with no webhook configured,
      `Continue` on first run before a folder is chosen. Expected: dimmed
      to .45, no background lift, and the plain arrow cursor rather than
      the hand.
      Round 3's L5 moved four control classes onto one declaration; all
      three sites above are `.btn`, so this is a regression check on the
      one class that already had a treatment.
      `.linkbtn` and `.bindbtn` gained one here and have **no disabled site
      yet** — the first will be finding B2's `Clear` on a keybind reading
      `Not set`, which lane R4 applies. When that lands, hover it: before
      L5 those two classes had no disabled rule at all, so a dead one still
      lit up.
- [ ] **LOAD-BEARING: an armed keybind capture is disarmed by leaving the
      section.** Go to Settings > Bookmarks, click a keybind button so it
      reads "Press a key…", then WITHOUT pressing a key click **Folders** in
      the rail. Now type into the Recordings field. Expected: your text
      appears normally.
      If it is swallowed, the capture is still armed: its handler
      preventDefault()s EVERY key including Tab, and stopPropagation() does
      not stop previews.js's sibling listener on the same node. An escaped
      capture eats what you type and persists it as a keybind, off-screen.
      This used to be covered by leaving the ROUTE; switching sections
      fires no route change, which is why `wm:section` exists.
- [ ] **Same check leaving Settings entirely.** Arm a capture in Bookmarks,
      then click **Uploader** in the title bar. Return to Bookmarks: no
      capture is armed.
- [ ] **The gear returns you to where you were.** From Skills, open the
      gear, then press it again. Expected: back on Skills, not the
      Uploader.
- [ ] **Bookmarks is two cards, and the eighteen binds read as three
      groups.** Open Settings > Bookmarks. Expected: `EVE-FOCUSED KEYBINDS`
      first, holding `Register keybinds in EVE` and every bind; `EVE
      WINDOWS` second. There is no `BOOKMARK KEYBINDS` card any more
      (round 5's C7 — it was a titled card around one checkbox, and the
      third name for one idea in a single viewport).
      Then read the binds: four full-width rows, then `FINISHERS` over a
      two-column block of ten reading `HS (highsec)` … `C6`, then `TAGS`
      over four reading `e (end of life)` … `c (critical)`. The shared
      token belongs to the heading now, so no row should still say
      "Finisher:" or "Tag". If the whole list renders flat and unheaded,
      the payload lost its `groups` key — which is the designed fallback,
      not a crash, so nothing will be in the console.
- [ ] **A bookmark overridden by a Previews keybind says so.** Bind a
      Previews chord (Settings > Previews) and the same chord to a bookmark
      action. Expected on Bookmarks: that bind button is marked — red while
      previews are ON, dim while they are off — with a tooltip naming which
      set wins. Round 5's C6: this warning existed only on Previews, the
      screen that WINS the collision, so on the screen whose bind silently
      stops firing an overridden bind looked identical to a working one.
      Check the wording is stated ONCE too (C5): the full precedence rule
      belongs under Previews > Global keybinds, and Bookmarks carries only
      a pointer to it.
- [ ] **The EVE window list marks only what is not running.** Settings >
      Bookmarks > EVE WINDOWS with at least one client open. Expected:
      running clients carry no annotation at all and the card's own hint
      says "All of these are running unless marked otherwise"; a title that
      is enabled but whose client is closed reads `(not running)`.
      Round 3's R4 finding 5 annotated BOTH states, so thirteen clients
      printed "(running)" thirteen times; round 5's C9 keeps what R4 was
      protecting — silence has to be defined, not inferred — and defines it
      once in the hint instead.
- [ ] **Opacity is a percentage, and it still reaches the floor.**
      Settings > Previews. Expected: the readout reads `100%`, not `255`,
      and dragging the slider fully left reads `8%` rather than `20`.
      Round 5's C2: the control was showing a raw Win32 alpha byte, so its
      floor read "20" and every reader takes that for 20% when it is 7.8%.
      The stored value is still the 0-255 byte — at 40% the settings file
      must hold 102. If the readout is EMPTY, the module threw before its
      listeners registered; that is exactly the inert-screen failure this
      file's preamble describes, and it happened once while this lane was
      being written.
- [ ] **No dead Never-minimize checkboxes in the default state.** Settings >
      Previews with `Minimize a client's window while it is not the one you
      switched to` UNTICKED — the shipped default. Expected: each character
      row carries `Lock` and nothing else, and the row ends there with no
      trailing gap. Tick the toggle: a `Never minimize` checkbox appears on
      every character row, live, without a reload. Untick it: they all go.
      Round 5's C3 counted ~13 permanently disabled ones in the default
      state; D6 answered that the setting stays per-character but must not
      render where it can do nothing.
      **Watch the alignment when you toggle.** `#preview-binds` is a grid
      whose rows are `display: contents`, so the CSS track count and the
      number of cells previews.js appends have to move together — if they
      disagree by one, every row after the first is pulled into the
      previous row's leftover columns.
- [ ] **The minimize toggle is filed with the other window behaviour.** It
      is in `EVE CLIENT PREVIEWS`, next to `Reopen previews where you last
      put them` — not under `GLOBAL KEYBINDS`, where it was the one control
      that is not a keybind (round 5's C4).

## EVE bookmark hotkeys

Requires a Windows machine with EVE running. None of this is covered by
pytest — the engine is AutoHotkey.

- [ ] **The title bar holds exactly three destinations** — Uploader,
      Profiles, Skills — and the window still drags by the wordmark area.
      Bookmarks and Previews are NOT here: they are sections of Settings,
      reached through the gear. This item was written when there were two
      destinations and went unchecked while three more were added; the
      fifth pushed the bar past its width at 125% scaling. NOTE: that
      recorded reason does not survive the floor correction — at 840 CSS
      px the arithmetic says it should have fit. `DESIGN.md` carries it as
      an open question. The three-destination rule itself rests on
      `PRODUCT.md`'s destination-vs-configuration test and is unaffected.
- [ ] **The bar survives its own minimum at 150% scaling.** Set Windows
      display scaling to 150%, restart, drag the window to its floor. The
      three nav labels, the gear, minimize and close are ALL visible, and
      the wordmark area still drags. Nothing in the bar shrinks: the nav
      and the window buttons are flex:none and the drag region cannot go
      below the wordmark's own width, so an overflow here clips the close
      button off the right edge rather than compressing anything.
- [ ] With the feature off, the status bar shows no EVE segment
- [ ] Enabling starts the engine; the status bar segment appears
- [ ] Hotkeys fire in an enabled EVE window and do nothing in an unenabled one
- [ ] **All nineteen binds do nothing when a non-EVE window is focused.**
      Registration happens inside a function called while an `IfWinActive`
      criterion is active; if that criterion does not carry into the
      function, they register globally and fire everywhere. Nothing in the
      repository can test this; confirm it by hand.
- [ ] **Set Root does nothing outside an EVE window.** It is registered
      inside the per-window loop like everything else, and that registration
      is now the *only* thing scoping it — `DoSemi`'s own `IsEveWindow`
      re-check was dropped to track the helper author's script exactly. The
      one gap that guard covered is still real and cannot be tested from
      the repository: between un-ticking a window and the ~10s refresh that
      tears its binds down, a press in that window resets the root state.
      Confirm the normal case by hand; the gap is accepted.
- [ ] **THE ONE THIS RELEASE IS ABOUT — Set Root resumes numbering for home
      holes.** Make several home bookmarks whose first field is a single
      character plus a sig, e.g. `1-ABC`, `2-DEF`, `A-GHI`. Select all of
      them and press Set Root.
      Expected: root reads **Home/Zero**, and the next values are **3** and
      **B** — it resumes past the used slots.
      The bug: root read `1` and the next values were `11` / `1A`, because
      the parser mistook the single character for the root. `ZeroMode` was
      dead code in the script the port was made from; the re-vendored
      engine wires it up.
- [ ] **Grab Sig no longer uppercases what it captured.** The fork ran
      `StringUpper` over the three characters; the author's script does not,
      and the re-vendor follows the author. Finisher-generated names are
      unaffected (`FireRootFinisher` uppercases the whole result), so this
      shows only in the status bar's sig readout and in what Grab Sig puts
      on the clipboard for you to paste by hand. EVE displays signature IDs
      uppercase already, so in practice there should be nothing to see —
      check the sig readout looks right, and say so if it does not.
- [ ] **A Grab Sig that copies nothing says so.** Focus something with no
      selectable text — an empty area of the probe scanner, or a window with
      nothing selected — and press the Grab Sig bind.
      Expected: a tooltip reading "Grab Sig failed - nothing was copied",
      and the sig readout **unchanged** from before.
      The bug: the sig silently became the first three characters of
      whatever was already on the clipboard. Straight after a Set Root that
      is the root, so root `J214811` produced sig `-J21`, and the next
      finisher wrote it into a real bookmark with nothing flagging it.
      Then confirm the normal path still works — select a scanner row,
      Grab Sig, and check the readout shows that row's signature.
- [ ] **Set Root on an ENTIRE bookmark list fills gaps.** This is the
      "Entire bookmark list" row of `docs/bookmarks_reference.md`. Select
      the whole list of a scanned system — **including the system's own
      return bookmark**, the one whose prefix is the bare root — and press
      Set Root. With `1-ABC`, `12-GHI`, `13-MNO` (11 expired), expected:
      root `1`, next `11` — it refills the gap rather than continuing at 14.
      Including the return bookmark is what makes this work: DoSemi takes
      the first parseable line's prefix as the root, and EVE's alphabetical
      sort puts `1-ABC` ahead of `11-DEF` because "-" sorts before digits.
      Select only the numbered bookmarks and the root comes out `11` with
      no gap filling — that is the author's design, not a defect.
- [ ] **Set Root on a SINGLE bookmark starts fresh numbering.** The "Single
      bookmark" row of the reference. Select `1-ABC` alone: root `1`, next
      `11` / `1A`, and the root on the clipboard.
- [ ] **Set Root with NOTHING selected gives Home/Zero and touches nothing.**
      The "Nothing" row: fresh numbering at 1/A, and nothing moved to the
      clipboard.
- [ ] **The two keybind cards say which keybinds they are.** Settings >
      Bookmarks heads its card "EVE-focused keybinds"; Settings > Previews
      heads its card "Global keybinds". Each names the other set and where
      it lives. Both were headed "Keybinds", one rail item apart, for two
      systems that take each other's keys — bind the same combination in
      both and confirm the Previews row marks the collision.
- [ ] **There is no Copy or Paste row in the keybinds card**, and no key
      Wingman registers sends a bare `^c` or `^v`
- [ ] **Rebinding a window-scoped hotkey stops the old key firing** — the
      direct test of the teardown repair, and the bug that shipped for years
- [ ] Disabling a window stops its hotkeys firing, within ~10s
- [ ] Every finisher produces the correct Flygd/ABH name (Protean removal)
- [ ] **Tags are written lowercase: `e`, `/`, `f`, `c`.** The class
      finishers (`H`/`L`/`N`/`13`/`C1`-`C6`) are a different code path and
      stay uppercase
- [ ] **CapsLock lowercases the class finishers ONLY outside root mode.**
      New with the re-vendor: `DoY`/`DoP`/`DoDot` pick `h`/`l`/`n` when
      CapsLock is on. In root mode — the default state, and where you will
      be for every other item here — `FireRootFinisher` runs
      `StringUpper` over the whole result before pasting, so you will see
      `H`/`L`/`N` regardless. Seeing uppercase in root mode is correct, not
      a failure. The lowercase path is reachable only after a Set Root that
      found nothing parseable.
- [ ] **There is no medium-hole tag** — no `M` row in the keybinds card, and no key
      writes an ` M`
- [ ] **The frig tag writes `f`, not `S`.** Same bind and INI key (`FinS`),
      so an existing binding for it still works
- [ ] **Re-tagging a bookmark that already carries a legacy ` S` replaces
      it with ` f`** rather than leaving both on the line
- [ ] **There is no Bookmark naming card in the section** — home holes, the
      return-bookmark toggle and the preface field are all gone
- [ ] **The generated INI has no `[Settings]` section at all.** Open
      `%LOCALAPPDATA%\FlyGD Wingman\eve_bookmark_helper.ini`: it should
      contain `[Keybinds]` and `[Enabled]` and nothing else. The engine has
      no naming settings left to read, so writing them would be config that
      nothing consumes.
- [ ] **Home bookmarks start at `.1`** — now a property of the engine
      itself rather than of a value Wingman writes
- [ ] **Return bookmarks are NOT prefaced** — no `!`. There is no preface
      anywhere any more: not in the UI, not in settings.json, not in the
      INI, and not in the engine
- [ ] **There is no Root card in the section.** Root mode, the Set root box
      and the Clear button are gone. The status bar's ROOT / NEXT readouts
      are the only root display, and they still update as you use the
      hotkeys — check they do.
- [ ] **THE SILENT-NO-OP TRAP: enabled with nothing to register says so.**
      Tick Enable but leave every EVE window unticked. Expected: a line under
      the engine state reading "No hotkeys are registered — no EVE window is
      enabled below." Then tick a window but clear every keybind: the line
      reads "…no keybinds are set." With both wrong, it names both.
      Untick Enable and the line disappears entirely.
      The bug: `RegisterBind` ignores a blank key without recording a
      failure, and the per-window loop never runs with nothing ticked, so
      `failed_binds` stayed empty and the UI reported **Running** with no
      warning while every keypress did nothing — indistinguishable from the
      feature being broken. This is what a fresh install looks like before
      you configure it, so it is the first thing a new user would hit.
- [ ] Deliberately binding two actions to one key shows the collision warning
- [ ] Binding a key another application owns shows a registration failure,
      not a silently dead key
- [ ] **Importing a REAL `eve_bookmark_helper.ini` reproduces that setup.**
      AutoHotkey writes it as UTF-16 LE; reading it as UTF-8 parsed nothing
      and saved that nothing over the user's settings while reporting
      success. Use a file written by the standalone script, not one retyped
      in an editor — retyping it changes the encoding and hides the bug.
- [ ] Importing a file that is not a helper INI refuses and leaves the
      existing keybinds untouched
- [ ] Importing a config with `Mode=1` says Protean naming is not supported;
      one with `Mode=2` says nothing about it
- [ ] **Reset to defaults** replaces all 18 binds after confirmation,
      and the confirmation says 18 — bookmarks.py's BIND_IDS is the
      count, and three places used to disagree with it
- [ ] **Refresh** on the EVE windows card picks up a client launched while
      the section was already open
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
- [ ] ~~**At 125% and 150% Windows display scaling the EVE status segment
      hides** rather than crowding the progress bar.~~ **Not performable —
      do not check this.** It rested on the window's floor being 840
      physical pixels and the viewport therefore being 672px or 560px. The
      floor is 840 CSS px at every scaling, so `@media (max-width: 720px)
      { .evestat { display: none; } }` cannot fire through the window and
      the segment never hides. Nobody had observed it; it was reasoning
      only, from the wrong premise. What the strip does when it genuinely
      runs out of room — the EVE segment yields, upload progress does not
      — is still the recorded intent
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
- [ ] **The ring marks the client you last used, and stays there.** With
      two clients running, switch to one: its preview gains the cyan ring
      and the other loses it. Now click a browser, Discord, or Wingman's
      own window while that EVE client is still up. Expected: **the ring
      does not move and does not go out** — it is answering "which client
      are you flying", not "which window has the foreground". It moves
      only when the *other* client is switched to, and clears only when
      the ringed client exits. (It used to clear the moment focus left
      EVE; that was reported as unexpected and is what
      `PreviewHost._selected_key` being sticky fixes.)
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
- [ ] **Monitors whose tops do not line up** (e.g. a 4K panel spanning
      y 0..2160 beside a 1440p one starting at y 291): a never-previewed
      character gets a preview that is **on a display**, not in the gap
      above the shorter monitor. This found a real bug — the virtual
      desktop is the bounding RECTANGLE of all monitors, not their union,
      so the space above a shorter monitor is inside it and on no screen.
      A preview deposited there is invisible AND un-draggable, so it can
      never acquire the saved position that would rescue it: every new
      character would be lost permanently. Passes on a single monitor, and
      on any arrangement with aligned tops, whether or not the code is
      correct — so it has to be checked on staggered monitors specifically.
- [ ] Unplug a monitor that holds a saved preview position, then restart
      Wingman. That preview comes back **on a remaining display**, not at
      its saved coordinates in empty space. Same clamp as the item above,
      reached by the other route.
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

      The DPI line is `logger.debug`, so it is invisible at the default
      level. Start with `WINGMAN_LOG_LEVEL=DEBUG` to see it:

          Preview thread DPI override accepted: True

      Expect exactly one, at thread start. That variable also reveals the
      other preview diagnostics that INFO discards — whether `WM_HOTKEY`
      reached the host window, why a placement read failed, and the
      registration push that is swallowed at launch because previews start
      before the webview exists. Anything in this file that says "check
      the log" for a preview-thread detail needs it.

      From WSL, environment variables do not reach a Windows process
      unless exported: `WSLENV=WINGMAN_LOG_LEVEL WINGMAN_LOG_LEVEL=DEBUG`.
      Without `WSLENV` the app starts normally and logs nothing extra,
      which looks exactly like the feature not working.
- [ ] Frozen build only: run the packaged app and confirm labels still
      render in Inter. The font is a `datas` entry, and PyInstaller exits 0
      when one resolves to nothing.

### Reopen previews where you last put them

The checkbox on the previews card. It governs where a preview OPENS, at
launch and mid-session alike — a preview is created whenever its client
appears, so an item that only restarts the app tests half of it.

- [ ] On (the default): drag two previews somewhere deliberate, restart
      Wingman. Both come back exactly where they were.
- [ ] On: with Wingman already running, start a third client. Its preview
      appears at that character's saved position, not on the stack.
- [ ] Off: quit that client and start it again. Its preview opens in the
      default stack, ignoring the saved rect.
- [ ] Off: drag a preview, switch the checkbox back on, restart. The drag
      you made while it was off is where the preview returns — positions
      are recorded whatever the setting says.
- [ ] **Multiple monitors with staggered tops**, either setting: start a
      character that has never had a preview. It lands fully on a display,
      not in the dead zone above one. The clamp runs on both paths, and an
      arrangement with aligned tops hides a failure here completely.
- [ ] Make `settings.json` read-only and toggle the checkbox. The hint
      below it says the choice will not survive a restart. The box stays
      where you put it — the setting really did change for this session.
- [ ] Nothing at any point moves or resizes an EVE client. The log has no
      line about placing or restoring a client window.

### Preview configuration options

Four settings on the Previews card: Labels, per-character Lock, Opacity, and
Minimize inactive clients. None of this is covered by pytest — it needs a
real desktop and, for the minimize checks, two clients you can watch switch
foreground.

- [ ] Labels off reclaims the character-name band and the mirrored video
      grows into it; labels on restores the band. Both take effect on
      already-open previews without a restart.
- [ ] **LOAD-BEARING: a preview created while labels are OFF opens with the
      band already reclaimed.** With the Labels checkbox already off, start
      a new EVE client (or one that has never had a preview) so a preview is
      created fresh. `create()`'s thumbnail call site is the one
      `show_labels` site with no automated coverage — it needs a real
      `CreateWindowExW` and `Thumbnail.register` and cannot be reached from a
      Linux test. A band on a freshly created preview, with labels off, is
      the specific regression this item exists to catch.
- [ ] Opacity dims the mirrored video and leaves the border and label at
      full strength — drag the slider to its low end and confirm the chrome
      stays crisp while only the video fades.
- [ ] A locked preview refuses a left drag and accepts a right drag. Check
      this **on a character who has never dragged their preview**, not just
      one that already has a saved position — that is the case the lock's
      own storage list exists for, since `locked` cannot ride in
      `preview.layouts` without a saved rect.
- [ ] **LOAD-BEARING: click-to-focus still works, on every preview.**
      Activation ownership moved from the preview window into the host as
      part of this slice; this is a pure regression check on the
      subsystem's primary interaction, and nothing in the suite executes
      Win32 to catch it failing.
- [ ] Minimize-inactive: with the checkbox on, clicking a different preview
      minimizes the client you were on, the new client ends up foreground
      and stays there, and a character on the never-minimize list is skipped
      entirely.
- [ ] **LOAD-BEARING: minimize-inactive holds across REPEATED switches.**
      Cycle A -> B -> A -> B -> A, at least five switches, and confirm the
      outgoing client minimizes EVERY time. A single successful switch does
      not satisfy this item. `activate()` restores a minimized window with
      `ShowWindowAsync` — asynchronous — and then reads its verdict from
      `GetForegroundWindow()` a few instructions later; a False `ok`
      correctly skips the minimize, so switching BACK to a client this
      feature just minimized is exactly where the race lands. The
      user-visible shape is "works the first time, then intermittently",
      which the single-switch item above passes straight through.
- [ ] A failed activation leaves both clients exactly where they were — no
      minimize happens. Hard to force deliberately; watch for it rather than
      staging it.
- [ ] **LOAD-BEARING: a minimized client's preview keeps updating.** Minimize
      a client with visible motion — undocked, drones out, or the camera
      spinning. Do NOT use a docked ship on a static scene: it looks
      identical whether the thumbnail is live or frozen on its last frame,
      so that scene cannot tell you which one you saw. This is the check
      that decides whether minimize-inactive is compatible with the
      previews it sits beside.
- [ ] Watch whether the 10 ms settle before the minimize, and the 100 ms
      `SendMessageTimeoutW` ceiling, are enough on a real, possibly loaded
      client — both are ported constants that have never run outside this
      pass.
- [ ] Watch for a failed SECOND activation: the minimize succeeds but the
      re-activation after it is refused, leaving you on whatever Windows
      picked instead of the client you switched to. This is silent by
      design — there is no clean recovery — but should be observed rather
      than assumed absent.
- [ ] Reader's note, not a defect to file on its own: the Minimize-inactive
      checkbox and the never-minimize column sit in the card headed "Global
      keybinds" — right for their adjacency to that column, but that card's
      intro tells the user everything in it is a global keybind, and
      minimize-inactive is not one. Worth noticing during the walk.

### Opacity is translucency, not dimming

Nothing in CI renders a preview window, so this is the only place the fix
is observed. Put something with COLOUR behind a preview before you start —
a browser on a white page, not the desktop wallpaper. Against a dark
background dimming and translucency look identical, which is how the
original bug survived a smoke pass.

- [ ] Drag a preview over that bright window, then Settings > Previews and
      pull Opacity down to roughly half. Expected: the bright window shows
      THROUGH the game content. If the preview merely goes darker and the
      window behind never appears, the thumbnail is still blending against
      `chrome.render`'s interior fill and the hole is not being punched.
- [ ] At the same setting, click the preview's middle. It must still take
      the click and raise its client. `THUMBNAIL_ALPHA` is 1 rather than 0
      for exactly this reason, and 0 would look identical right up until
      the click lands in whatever is behind.
- [ ] With labels ON, look along the top edge of the game content at a low
      opacity. There must be no 1px dark seam between the label band and
      the thumbnail — the band ends on the row before the hole starts.
- [ ] Leave opacity at 255 and confirm nothing changed: the tile reads as
      solid, and an unselected preview still shows its thin near-black
      edge. That edge is chrome, not fill, and must survive at every
      opacity.
- [ ] Trigger an alert while opacity is low. The ring must still draw at
      full strength — chrome is painted over the hole, not under it.

### Preview sizing

Aspect-locked resize handles, a per-character `Size…` dialog, the snapping
toggle, and Reset previews. The lock exists because a DWM thumbnail does
not letterbox a shape that does not match its client — it stretches to
fill the destination rect, so a mismatched preview has always been
distorting the game rather than wasting pixels around it (see
`docs/preview-roadmap.md`'s corrections). Nothing here renders under
pytest.

- [ ] Drag a preview's resize handle. The picture stays undistorted against
      the client's shape — not merely squarish-looking — and both a
      mostly-horizontal and a mostly-vertical drag change the size; a
      handle that only tracks one axis is not this feature.
- [ ] **LOAD-BEARING: turn labels off in the Previews card, then drag the
      handle again.** The picture must still be undistorted with the label
      band gone. The window is the picture plus a fixed horizontal margin
      and a vertical margin that shrinks to just that margin once labels
      are off; a lock that assumes the band is always there is exactly
      the case the first draft of this design got wrong.
- [ ] **The handle must SHRINK, in both axes separately.** Drag a preview
      larger, release, then drag the handle back inward along X alone: the
      window gets smaller. Repeat along Y alone: smaller again. This is a
      regression guard, not a nicety — the first shipped lock believed
      whichever axis implied the larger picture, so on a rect already at
      the locked ratio (which is every rect after the first drag) an
      inward drag along one axis returned it byte-identical. Growing
      worked from either axis throughout, which is what made it read as a
      mystery rather than a limit.
- [ ] **Uncheck "Keep previews the same shape as their client", then drag
      the handle.** Each edge now moves freely and the picture visibly
      stretches — that is the documented cost, not a bug. Re-check it:
      the lock returns on the very next drag, with no restart. A preview
      already open when you flip it must obey, which is what the live
      restyle is for.
- [ ] Flip that checkbox in the MIDDLE of a resize drag (hold the handle,
      flip it with the other hand or a second monitor, keep dragging).
      The gesture in flight keeps the behaviour it started with; the
      change lands on the next drag. The flag is sampled at button-down
      on purpose.
- [ ] `Size…` on a running client: type `640x392`, confirm the preview
      resizes to it, and that the hint text named the client's own
      undistorted size before you typed anything.
- [ ] `Size…` on an offline character with a saved position: the size is
      accepted and applies the next time that client runs.
- [ ] `Size…` on a character with no saved position: refused, with the
      sentence telling you to start the client once first.
- [ ] Turn snapping off in the Previews card, then drag a preview next to
      another: no magnetism, it lands exactly where dropped. Turn it back
      on: magnetism returns immediately, without a restart.
- [ ] **Reset previews** — the `.btn.danger` button in the Previews card:
      a confirm dialog appears, accepting it returns every preview to the
      default stack, and locks, never-minimize and keybinds all survive
      the reset.
- [ ] Reset previews with previews switched off, then switch them back on:
      previews open at the default stack rather than any position they
      held before the reset.

## EVE preview hotkeys

- [ ] **LOAD-BEARING: `WM_HOTKEY` reaches the message-only host window.**
  Bind any chord and press it. If nothing happens while the log shows a
  successful registration, `HWND_MESSAGE` is not receiving the message and
  registration must move to `hWnd=NULL` with dispatch in the pump loop —
  see risk 4 in `docs/history/eve-preview-hotkeys-design.md`.
- [ ] A per-character chord switches to that client from another application
  (try it from a browser, not just from Wingman).
- [ ] **A state update mid-hotkey-capture does not orphan or hide the capture.**
  With the Previews tab open and a hotkey row showing "Press a key…", start
  or close an EVE client (which pushes new state from Python). Expected: the
  row stays armed and visibly capturing, typing fills in normally, and a
  pressed chord binds correctly. The original bug left the row armed but
  invisible, eating keystrokes and binding them silently.
- [ ] Cycle forward and back walk every running client in name order and wrap.
  **Try it with a browser focused, not just with an EVE client focused** —
  these are different branches of `_on_hotkey`: with an EVE client focused,
  cycling anchors on that client; with a browser (or anything else) focused,
  it falls back to the last-cycled target. The browser case is the one a
  multiboxer actually uses, so it must be checked, not just the EVE-focused
  case.
- [ ] **Holding a chord fires once, not at the key-repeat rate.** Hold it for
  three seconds; the client must not flicker through repeated activations.
- [ ] **A chord another application already owns is visible on the Previews
  tab**, not only in the log. Bind something a running app claims, restart
  Wingman, and check the tab BEFORE touching anything — this is the startup
  case where the push has no window to reach.
- [ ] Switching previews off releases the chords: they do nothing, and the
  application that owns them gets them back. Switching previews on reclaims
  them.
- [ ] **LOAD-BEARING: an existing bind can be overwritten IN PLACE, with
  previews running.** Bind `Ctrl+Alt+F1` to a character, leave previews on,
  then click that same row and press `Ctrl+Alt+F1` again — do NOT clear it
  first. Expected: the row takes the chord. What the bug looked like: the
  row sat on "Press a key…" and the foreground jumped to the bound client
  instead, because a registered chord is delivered to the preview window as
  `WM_HOTKEY` and never reaches WebView2 at all. Clearing first was the
  workaround users found, and it worked for exactly that reason — so
  testing this with a cleared row tests nothing.
- [ ] **The same, for a chord a DIFFERENT row owns.** Press character A's
  chord while character B's row is armed. Expected: B takes it, A keeps it,
  and both rows show it — that is now a legal shared bind, not a clash.
- [ ] **Escape and clicking another row still cancel an armed capture**, and
  after either, the preview hotkeys work normally again on the very next
  press. A capture that fails to disarm leaves the host eating the next
  chord (for 30s, then it expires on its own).
- [ ] **Previews off: capture still works.** With previews off nothing is
  registered, so every key reaches the page directly. Both paths have to
  bind the same chord to the same row.
- [ ] **With previews off, the Previews tab reads as off, not as live.** Open
  the tab while previews are switched off. Expected: the banner above the
  list says previews are off, and every chord renders as neither registered
  nor refused — a dashed outline, with a tooltip saying it is not
  registered right now. No chord may render as an ordinary, live binding.

  Rows are **not** dimmed while previews are off. Dimming means "this
  character is logged off", and it only says that by contrast with an
  undimmed row; with the host stopped Python sends no character list at
  all, so dimming every row made the tab indistinguishable from one where
  everybody really had logged out. That was reported as "I don't see
  anything that indicates they are online".

  Confirm independently rather than trusting the tab: from a separate
  probe process, `RegisterHotKey` must succeed for each of those chords.
  The original bug served the host's last snapshot after teardown; the
  2026-08-24 regression was the page reading an absent registration entry
  as a successful one. Both made the tab claim chords Windows did not hold.
- [ ] **A chord bound to a `Win+` combination never fires.** Windows owns a
  large share of `Win+`key and those chords cannot be taken by
  `RegisterHotKey`. Bind one (e.g. `Win+F1`) and press it: it must appear on
  the Previews tab as refused (same treatment as any other chord another
  application already owns), not as a chord that looks registered and
  silently never fires.
- [ ] **The character list updates when the Previews tab is opened.** While
  viewing another tab, start an EVE client. Switch to Previews. Expected: the
  new character appears in the list immediately without needing a restart or
  settings save.
- [ ] A binding made for a character survives a restart while that character
  is logged off, and still appears in the list.
- [ ] **Hotkey captures are tab-isolated.** Arm a bookmark hotkey on the
  Bookmarks tab, switch to Previews, arm a preview hotkey, press a chord.
  Expected: only the preview binding is written. Check the Bookmarks tab
  afterwards: the bookmark hotkey unchanged. The original bug wrote to both,
  leaving an off-screen binding the user never saw.
- [ ] With EVE bookmarks enabled and a window enabled, binding a preview chord
  that matches a bookmark bind shows the collision warning. With bookmarks
  disabled, it does not warn.
- [ ] **Dimmed rows are visibly less prominent than normal.** Find an offline
  character. Then create a latent collision: configure a preview chord that
  matches a bookmark chord, then disable EVE bookmarks (or un-tick every window
  in the Bookmarks tab's enabled-window list) so the collision is not active.
  Expected: both the offline character and the latent-collision row read
  noticeably quieter than normal rows, not more prominent. A visual regression
  here reverses the hierarchy.
- [ ] Quitting Wingman with chords bound leaves them released: the owning
  application gets them back without a reboot.

## Shared preview keybinds

- [ ] **One chord on several characters is accepted and NOT marked as a
  clash.** Bind `Ctrl+Alt+F1` to two characters. Expected: neither row goes
  clash-red; hovering either says it is shared with the other. (Before this
  change the second row was an error, and only the alphabetically-first
  character ever responded.)
- [ ] **It goes to whoever is logged in.** With only the second character
  running, press the shared chord. Expected: it switches to that character —
  not a silent no-op because the first one is offline.
- [ ] **With both running, a press always moves you.** Press it repeatedly
  from one of the two clients. Expected: it goes to the OTHER one rather
  than re-focusing the client already in front.
- [ ] **A character chord that collides with a cycle chord is still a
  clash.** Bind `Ctrl+Alt+Right` to a character while it is also Cycle
  forward. Expected: both rows go red and the tooltip says the cycle keybind
  is the one that loses — those two cannot share a registration.

## EVE preview alerts

When a player shoots, scrambles or decloaks one of your logged-in
characters, that client's preview pulses in a colour and a sound plays.
This subsystem is window and audio-only — nothing in it can be tested
headless.

### Verifiable now

- [ ] **With alerts off, no `wingman-alerts` thread exists.** Check Task
      Manager's process detail tab or run `threading.enumerate()` in a
      Python debug console. Expected: no thread named `wingman-alerts`.
      Turn alerts on in Settings > Previews and confirm the thread appears.
- [ ] **Turn alerts on with no Gamelogs folder set.** Open Settings >
      Previews and tick Enable alerts without setting a Gamelogs folder.
      Expected: the Alerts card displays "Your EVE Gamelogs folder is not
      set. Alerts cannot run without it — set it under Settings › Folders."
- [ ] **Set the folder.** Browse to your EVE Gamelogs folder in Settings
      > Folders, then return to the Alerts card. Expected: it reports the
      number of characters being watched — e.g. "Watching gamelogs — 3
      characters online."
- [ ] **Change the Gamelogs folder while running.** With the Alerts card
      open and showing a character list, change the path in Settings >
      Folders and return. Expected: the count re-derives from the new
      folder without restarting the app — the card updates to show the
      characters in the new Gamelogs.
- [ ] **Run a Sleeper site.** In a wormhole, start a Sleeper combat site
      with alerts active. Expected: no combat alerts fire — incoming attacks
      from NPCs are dropped by the PvE filter. Uncheck the PvE filter in the
      Alerts card and run another site. Expected: alerts fire normally.
- [ ] **Alt-tab between two logged-in clients repeatedly.** With both
      previews visible, switch focus between them. Expected: the selection
      ring (a thin outline marking the foreground client) follows the focused
      client, and the switch does not feel slower than it did before alerts
      were enabled.
- [ ] **Alt-tab to a browser or other non-EVE window.** With previews
      visible, switch focus away from EVE. Expected: every preview loses its
      selection ring (the thin outline marking the foreground client).
- [ ] **Confirm sounds play in the frozen build.** This is the only place
      the winsound module's packaging entry can be verified. Launch the
      installed build, trigger an alert, and confirm you hear the sound.
- [ ] **The colour input renders correctly in dark theme.** Open Settings >
      Previews and scroll to the Alerts card. Each event type (Combat, Warp
      scramble, Decloak) has a colour picker (`<input type="color">`).
      Expected: each appears as a clickable swatch matching your Windows
      theme (dark or light), not as a browser's native light-theme colour
      widget. You can also verify this with `?dev=1` appended to the URL
      (e.g., `http://localhost:…/?dev=1`) — `web/dev.js` carries a
      `preview.alerts` payload so the Alerts card renders. Click one to
      confirm the colour picker opens and works. If the colour input does not
      render, the documented fallback is three fixed swatches per event —
      verify that they are offered instead.

### The alert render path

`PreviewHost._apply_alerts` arms the named character's preview and starts an
80ms tick timer that runs only while something is armed. The eight items below
were blocked on that and are now live.

Two things decide what you should see, and they are easy to conflate:

- **Persistent alerts** (`Persist` on, the default) clear when you *switch to*
  that client — by clicking its preview, by a cycle keybind, or by plain
  alt-tab. All three land in `PreviewWindow.set_focused`, which is the
  foreground and **not** the ring: the ring is sticky and sitting on a client
  while you read Discord must never count as having seen its alert.
- **Timed alerts** (`Persist` off) run their configured duration and are
  **not** cut short by selecting the client. That is deliberate:
  `alerts/state.py:75-83` refuses to acknowledge a timed alert so selecting a
  client cannot kill a ring that has only just appeared.

- [ ] **Take fire from a player.** In a wormhole with your preview visible,
      have another player shoot your character with weapons. Expected: the
      preview pulses in the configured colour and keeps pulsing while you are
      focused on a different application (e.g. a browser). With `Persist` on,
      it stops when you switch back to that EVE client; with `Persist` off it
      stops on its own after the configured duration.
- [ ] **Change a setting while an alert is pulsing.** With a ring pulsing on
      some preview, go to Settings › Previews and move the opacity slider (or
      toggle labels, or lock that preview). Expected: the ring keeps its full
      6px width for the rest of the alert. If it thins to brackets at the
      sides and bottom, `_restyle` has re-pushed the thumbnail at `BORDER`
      instead of the window's live `_inset`.
- [ ] **Take fire on the client that is wearing the ring.** Same as above,
      but make sure the shot character is the one you most recently switched
      to, then tab out to a browser and leave it there. Expected: the alert
      is **persistent** — it keeps pulsing until you switch back or click it,
      exactly as for any other client. The ring being on it is not "you are
      looking at it". If it instead expires after ~1.2s, `arm_alert` is
      reading `selected` where it must read `focused`.
- [ ] **Click the pulsing preview to clear it.** While the preview is
      pulsing from a **persistent** alert, click anywhere on it. Expected: the
      ring clears immediately **even if the client does not come to the
      foreground** — clicking the preview is its own action. This is
      window.py:102-116's expected failure mode before a click goes through
      to EVE.
- [ ] **Drag an alerting preview.** Start a combat that generates alerts on a
      visible client, then drag its preview to a new position. Expected: the
      preview moves smoothly. **The pulse is expected to hold one frame for
      the duration of the drag** and resume in phase on release — `WM_TIMER`
      is synthesized only when the thread queue is empty, and a drag keeps it
      full at a measured 320 mouse-moves/s. A frozen ring here is correct
      behaviour, not a bug; a stuttering *window* is a bug.
- [ ] **Quit an EVE client mid-alert.** Start combat that generates alerts,
      then close that client's window while the preview is pulsing. Expected:
      no crash, and the alert timer stops (the preview disappears within ~1s
      as the client exits). The app remains responsive.
- [ ] **DPI scaling: on a 150% or 200% display, both rings are visible.**
      With a monitor at 150% or 200% Windows display scaling, arm an alert
      and observe the pulsing preview. Expected: both the normal 2px selection
      ring (outline of the focused client) and the 6px alert pulsing ring are
      clearly visible at their designed size, not bleeding together or
      becoming indistinct.
- [ ] **Alt-tab between clients with an active alert.** With a **timed**
      alert armed on one client, switch focus away and back to that client.
      Expected: the alert ring pulses regardless of which client is focused,
      and returning to the alerted client does **not** cut it short. Repeat
      with `Persist` on: returning to that client clears the ring, because
      selecting it is what acknowledges it. This is the contrast with the
      selection ring, which only ever appears on the foreground client.
- [ ] **Press Test on each event type.** In the Alerts card, for each of
      the three events (Combat, Warp scramble, Decloak), click its Test
      button. Expected: the ring pulses on a character's preview in the
      configured colour, a sound plays, and the ring stops on its own after
      a few seconds — a test alert is never persistent.
- [ ] **Resize a preview past 640x480 while alerting.** Start an alert that
      makes a preview pulse, then drag its bottom-right corner to enlarge it
      past 640x480 pixels. Expected: the pulse transitions from a six-step
      pulse to a two-step blink, nothing leaks outside the preview bounds,
      the window does **not** snap back to its pre-drag size, and the effect
      continues until the alert clears. Resize smaller than 640x480 again;
      the six-step pulse returns. The snap-back is the specific regression to
      watch for: `UpdateLayeredWindow` takes its size from the pushed image,
      so a stale frame cache resizes the window under the drag.

## Profiles (the EVE settings copier)

Named **EVE Settings** until it collided with the gear's own
"Settings". The route id is still `evesettings`, matching
evesettings.js and the `eve_settings_*` bridge methods.

The suite cannot exercise Windows file locking or a real `os.replace` retry,
so these are the checks that matter and only a Windows machine can run them.

- [ ] Choose the EVE folder. Servers and profiles populate; characters
      show names within a second or two of the route opening.
- [ ] **The folder card is one line on every visit after the first.** With a
      folder already chosen, open the route. Expected: the EVE settings
      folder card is a single row — `Folder`, the path, the server and
      profile, and a `Change…` button. The server and the profile each
      carry their noun, `Tranquility server · Default profile` (round 5's
      R5); bare, `Default` did not read as a profile name at all. Check the
      path still fits beside them at the floor with the default EVE root.
      And the Copy EVE settings card's
      target list is on screen without scrolling. Press `Change…`: the
      folder, Server and Profile controls appear. Leave the route and come
      back: it is one line again. This is deliberate and not a bug — the
      collapse is what puts the task on screen, so it is not remembered.
- [ ] **Neither folder path can be clicked into.** Open the route with a
      folder chosen, then press `Change…`. Expected: the path in both faces
      of the card is monospace text on the card's own left edge, with no
      fill, no border and no focus ring — click it and nothing happens and
      nothing is focused. Compare it against Settings › Folders, where the
      recording path in the same monospace face IS a text field you can
      type into: the two must not look alike. Drag the window to the floor
      with a deep root selected — the path ellipsises at its end and
      `Choose folder…` and `Detect` stay on the row.
- [ ] **`Copy from` is the widest control in its card.** With a folder
      chosen, look at the copy card. Expected: the `Copy from` dropdown
      spans the card's form measure — wider than the `Filter…` box below
      it, which shares its row with `Select all` and `Clear`. It decides
      what content overwrites every ticked character, and it used to be the
      narrowest control on the screen.
- [ ] **Widening the window adds roster columns, not gutter.** With a folder
      chosen and a few dozen characters, put the window at the floor and note
      how many columns of names the target list has and where `Copy to
      selected` sits. Now drag the window much wider. Expected: the names
      reflow into MORE columns and the button climbs; the folder card above
      keeps its width and its left edge stays flush with the copy card's.
      Round 3's P10 measured the opposite — every extra pixel became margin,
      because Profiles wraps its route in the same `.settings` 620px wrapper
      the eight Settings sections use, so the roster inherited a measure meant
      for a label/field pair. D1 lifted the cap for the roster's card only:
      the prose, the `Copy from` row and the filter row are all still held to
      the old 586px measure on purpose, so a filter row narrower than the
      roster beneath it is correct here, not a bug.
- [ ] **A folder that is not set, or cannot be read, opens the controls
      anyway.** Clear the folder (or point it at a directory you have no
      access to) and reopen the route. Expected: the full controls, not a
      summary of nothing, with the warning below them.
- [ ] **The EVE pill survives the collapse.** Start a client with the folder
      card collapsed. Expected: "EVE running" is showing at the right of the
      card's heading, in the pill's own case — not upper-cased and
      letter-spaced like the heading beside it. It is the warning for the
      copy below; it may not only appear when the card is expanded.
- [ ] **The settings-folder path is monospace and truncates.** Both faces of
      the card. Expected: the same monospace face as the webhook and the
      recordings folder, on the same label column as Server and Profile, and
      a long root ends in an ellipsis rather than pushing `Change…` or
      `Choose folder…` toward the right edge. Check at 150% scaling, where
      the card is narrower than its own 620px.
- [ ] **The Characters / Accounts switch says what it is.** Expected:
      `Settings for` in the label column in front of the two radios, on the
      same column as `Copy from` below it. It was the only unlabelled
      control on the screen, and it changes what the source dropdown, the
      target list and the filter all mean. **The word is no longer `Copy`**
      (round 5's R3): that made four labels in one card say `Copy` with
      three different meanings, and this was the one whose options —
      `Characters`, `Accounts` — already say what they select. The label
      itself must still be there; an unlabelled switch is the defect the
      label was added for.
- [ ] Pull the network cable and reopen the route — characters render as
      `Character <id>`, nothing errors.
- [ ] **The roster reads alphabetically, down each column** (round 5's
      R1/D4). With a few dozen characters, look at the target list and the
      `Copy from` dropdown. Expected: both are in NAME order, not in the
      order of the ids in the filenames, and because the roster is a
      `columns` layout the names run A-Z down column one, then continue
      down column two. The order is applied where the names are
      (`Api.eve_settings_state`), not in `evesettings.tree`, which has only
      file ids — so check it again a second after the route opens, once the
      real names have replaced `Character <id>`: the roster re-sorts when
      they land, and that push is the only thing that can produce the
      finished order.
- [ ] Point the folder picker at a `settings_*` directory. The root heals
      upward and the tree still populates.
- [ ] Create a junction inside the EVE settings folder pointing outside it
      (`mklink /J <root>\junction C:\SomewhereElse`), then try to select it as
      a settings set. It must be refused as outside the configured folder --
      containment resolves symlinks and junctions, and this is the one path
      Linux CI cannot exercise.
- [ ] **Confirm Copy names both ends of the copy.** Select a source and one
      target and press Copy, then read the dialog before answering.
      Expected: the first line names the SOURCE character — "Copy Guarzo
      Opper's settings onto 1 other character?" — and the line under it
      names the target. Check the names match what the roster shows for
      those two rows (both come from `Api._eve_label`, so a disagreement
      means two producers have grown back). Then select more than six
      targets: the dialog names the first six and says "and N more" — the
      overflow must be stated, never a truncated list that reads as
      complete. Choose No.
- [ ] Copy one character onto three others with EVE closed. All three
      update; three auto-backups appear.
- [ ] Copy with EVE running. It fails with "The file is in use. Close EVE
      and retry", and every target is left intact.
- [ ] Restore the pre-copy backup for one character. The original settings
      come back.
- [ ] Back up a settings set, delete a `.dat` from it, restore. The deleted
      file returns.
- [ ] Add a file to a settings set that was not in its backup, then restore.
      It is removed, and the pre-restore auto-backup contains it.
- [ ] Restore with EVE running. Like a copy, it must fail rather than write
      -- restore stages every file and publishes with the same replace-with-
      retry, so a live client blocks it. The settings set must be left
      exactly as it was: nothing deleted, no `.tmp` files behind.
- [ ] Delete a settings set entirely, then restore its backup. The folder is
      recreated and the files come back.
- [ ] Start a copy and immediately try a second one. The second is refused
      with the busy message rather than interleaving.
- [ ] **The copy confirmation counts what you ticked.** Select two
      characters and press Copy. Expected: "Copy these settings onto 2
      other characters?" — not "2 other file(s)". Switch the mode to
      Accounts, select one, and confirm it reads "1 other account?" with
      no "(s)". The noun is derived from the selected files, so the dialog
      cannot disagree with the switch.
      **Then let the copy finish and read the status strip**: it must say
      "Copied to 2 characters.", not "2 file(s)". The two sentences are a
      second apart on the same screen and share one noun deliberately —
      fixing only the dialog would have made them disagree.
- [ ] **The copy confirmation repeats the running-client warning.** With an
      EVE client OPEN (the "EVE running" pill is showing), start a copy.
      Expected: the dialog itself says EVE is running and to close every
      client first, above the "cannot be undone" line. The pill is
      advisory and easy to miss; this dialog is modal and is the last
      thing before the write. Close every client and confirm the sentence
      disappears — it is probed fresh each time the dialog is raised, not
      read from the pill.
- [ ] With `auto_keep` at its default, copy the same character eleven times.
      Ten auto-backups remain; the manual ones are untouched.
      **Read the retention note while you are there** — it sits UNDER
      `Back up this profile` and above the list, not under the heading
      (round 5's R2: a policy was the first thing the card said and the
      action it qualifies came second). It must say ten, and it must say the newest ten *of each* thing — the
      prune is per character, account or profile, so eleven copies onto
      eleven different characters prune nothing. The number comes off the
      payload, so setting `auto_keep` to 3 in `settings.json` and reopening
      the route must change the sentence.
- [ ] **The backup list is columns, and Delete does not look like Restore.**
      Make several backups of different things. Expected: the dates line up
      in a monospace column as `2026-08-24 14:03` — punctuated, not the
      raw `20260824-140300` the filename carries — and `Restore` and
      `Delete` sit at the same x on every row however long the name.
      `Delete` carries the red outline Skills uses for Forget character,
      and `Restore` does not. Every row says `automatic` or
      `manual` in full — no bare `(auto)` on half the rows and nothing on
      the other half.
- [ ] Check the packaged build: the Profiles route appears and the
      folder picker opens.

## EVE skill plan readiness

Requires a Windows machine, a real EVE account, and a registered EVE
application. Most of this subsystem IS covered by pytest — the parser, the
evaluator, the JWT verifier, the loopback parser, the ESI client, the state
normaliser and the skill-id cache all run headless on Linux in CI. What
follows is only what the suite structurally cannot reach: a live third-party
authorisation server, a browser, a Windows-only crypto API, and a frozen
bundle.

**Register the EVE application first.** Until someone creates it at
developers.eveonline.com, sets the redirect URI to
`http://127.0.0.1:51779/callback/`, requests the two read-only scopes, and
puts the client id in `wingman/eveskills/application.py`, none
of the SSO items below can run at all — `Add character` is disabled and says
so. Every module below the auth stack is testable with stubs before that
happens, which is why the rest of the feature can be built and merged
against a placeholder id; only these items are blocked on the registration.

### The SSO round trip

- [ ] **LOAD-BEARING: a real authorisation completes against CCP.** Click
      `Add character`. Expected: the default browser opens EVE's own login
      page, the consent screen names exactly the two scopes
      (`esi-skills.read_skills.v1` and `esi-skills.read_skillqueue.v1`) and
      no others, and after approving, **the browser tab shows Wingman's own
      completion page** rather than a connection error or a raw JSON blob.
      The character appears in the roster as `Unscored`. Nothing in the
      suite can reach login.eveonline.com, so this is the only proof the
      PKCE challenge, the state comparison, the loopback listener and the
      code exchange all agree with the live server.
- [ ] **The window stays responsive for the whole five minutes.** Start an
      authorisation and do not complete it. Drag the window, switch routes,
      scroll the recording list. If any of that freezes, the loopback wait
      is running on the bridge thread rather than a worker.
- [ ] **Cancel sign-in actually cancels.** Start an authorisation, click
      `Cancel sign-in`, then complete the login in the browser anyway. No
      character is added, and starting a second authorisation works — a
      listener that did not release port 51779 makes the second attempt
      fail to bind.
- [ ] **A second authorisation while one is in flight is refused, not
      queued.** Two would fight over the fixed port.

### DPAPI, on Windows only

- [ ] **LOAD-BEARING: the refresh token survives a restart.** Add a
      character, quit Wingman fully (tray Quit, not just closing the
      window), relaunch, and click `Refresh characters`. It refreshes
      without asking you to sign in again. This is the DPAPI round trip:
      `dpapi.py` is the one module CI never executes, because it is
      `CryptProtectData` and CI is Linux.
- [ ] **A token another user cannot read costs one character, not the
      file.** Open `%LOCALAPPDATA%\FlyGD Wingman\eve_skills.json`,
      corrupt one character's `refresh_token_blob` (change a few base64
      characters), and relaunch. Expected: that character shows
      `needs_reauth` with a re-authenticate banner; **every other character
      is untouched and still refreshes.** This is what keeping the roster
      metadata in plaintext beside the wrapped token buys.

### A live refresh

- [ ] **An account with more than one character refreshes all of them.**
      Add at least three, click `Refresh characters`, and watch the notices
      strip count `Refreshed 1 of 3`, `2 of 3`, `3 of 3` as it goes. A
      counter that jumps straight to the total means progress is being
      pushed after the loop rather than per character.
- [ ] **A failure isolates.** Disconnect the network mid-refresh. Expected:
      the characters already fetched keep their data and show no error; the
      rest carry a per-character error and a `Stale` badge if they had
      previous data. Nothing shows a `Stale` badge that never fetched
      successfully.
- [ ] **Last-good data survives.** Reconnect, refresh again, and confirm the
      errors clear and the badges disappear.
- [ ] **The readiness verdict matches the game.** Pick one character and one
      plan and check three requirements against the in-game skill sheet: one
      it has active, one it is training, one it lacks. The evaluator's
      precedence is unit-tested; that the *inputs* are the right ESI fields
      is not.

### Forget and re-add

- [ ] **Forget is one write and it sticks.** Expand a character, use
      `Forget character`, confirm. The row disappears. Quit and relaunch:
      it is still gone, and no orphaned token remains — grep the state file
      for its character id and find nothing.
- [ ] **A forgotten character can be added back.** Re-authorise the same
      character. It returns as a single row, `Unscored`, not a duplicate.
- [ ] **Forget during a refresh stays forgotten.** Start a refresh over
      several characters and forget one while it is in flight. It must not
      reappear when the refresh commits.

### Corruption recovery

- [ ] **A truncated state file recovers from `.bak`.** With at least two
      characters authorised and at least two refreshes done (so a `.bak`
      exists), quit Wingman, truncate `eve_skills.json` to a few bytes, and
      relaunch. Expected: the roster comes back from
      `eve_skills.json.bak`, a warning appears in the notices strip, the
      damaged file is preserved as `eve_skills.json.corrupt-<timestamp>`,
      and **the characters still refresh** — meaning the wrapped tokens came
      back with them. If they all need re-authenticating, the backup tier
      is not covering the tokens and the whole reason it exists is missing.
- [ ] **A corrupt skill-id cache costs a re-resolve, not a failure.** Delete
      `eve_skills_cache.json` and refresh. It rebuilds from ESI; readiness
      is unchanged afterwards.

### The Skills page itself

- [ ] **The two-pane layout renders sanely** on first open. The rail on the
      left, the roster on the right, no overlap, no horizontal scrollbar at
      the default window size.
- [ ] **No `unknown bridge handler` throws in the console.** Open devtools,
      click the Skills nav button, and watch the console while the page
      loads and while every button on it is clicked once. A throw here
      means a JS call names a handler the Python `Api` does not expose —
      `WM.handle`'s try/catch keeps that from crashing the page, but it
      should never fire at all in a build that matches its own bridge.
- [ ] **The counts line and the plan ratio agree, and the ratio is
      keyed.** With at least one character and one plan, confirm the rail's
      counts line reads `N characters added` — the whole roster, and
      scoped, because a group head 200px away says `3 characters` about a
      readiness group and the two used to be word-for-word identical
      (round 5's S3). Then confirm each plan row's ratio is `ready
      characters / all characters`, whose denominator is that same roster
      count, not a count of the plan's skills.
      The `READY` header sits over that column, and hovering a plan row
      spells both numbers out. The pane header's `N requirements` beside it
      counts the plan's skills and is a different quantity: with a roster
      and a plan of similar size the two are easy to read as one, which is
      what the header and the tooltip exist to prevent.
- [ ] **The plan-issues disclosure opens and closes.** A character not
      fully ready for a plan shows a collapsed `<details>` listing the
      missing requirements; expanding it does not shift the rest of the
      row list, and collapsing it again restores the original height.
- [ ] **Visual layout at the window floor.** Drag the window to its floor
      and check that long character and plan names ellipsise rather than
      overflowing, the rail's buttons do not clip their own labels, and
      there is no horizontal scrollbar. The rail is 214px and the roster
      keeps the rest.
      **This item used to send you to 150% scaling for "a 560px CSS
      viewport, where the rail narrows to 168px", and to 125% for 672px.**
      Neither viewport exists — the floor is 840 CSS px at every scaling —
      so the narrowed-rail states are unreachable through the window and
      840 is not "the one width where this layout was never in doubt", it
      is the only width there is.
- [ ] **The row separators stop at the answer, not at the pane edge.** Widen
      the window well past the floor and look at the character list. Expected:
      every status sits in one column, and the hairline under each row ends a
      short way past the longest status — the rest of the pane to its right
      is plain background, with no rule running across it. Expand a row: the
      requirement names and their states line up with the character names and
      statuses above, and the wider window does not push either column right.
      Round 3's S8: the pane is elastic and the content is not (the name
      column is capped at 240px on purpose, because that is what the longest
      EVE skill and character names need), so a full-width rule made the dead
      space read as an unfinished table rather than as margin. The list now
      takes its width from the row instead. If the statuses ever go ragged,
      the cause is the name column being sized by `max-width` rather than by
      `width` — the cap only aligns them while there happens to be room.
- [ ] **The rail's plan-file actions still work where they now sit.**
      `Open plans folder` and `Reload plans` are link-style actions at the
      foot of the Plans block rather than buttons in a block of their own.
      Both still do what they say; neither wraps off the rail at 150%
      scaling.
- [ ] **`What is a plan?` sits under the plans, not under the void**
      (round 5's S5). With two or three plans in the folder, look at the
      rail: the disclosure and the two plan-file actions follow the last
      plan row directly, and the rail's leftover space is BELOW them. It
      used to be the other way round — the list took the slack and pinned
      the only onboarding copy on the screen to the bottom of a ~620px
      gap.
- [ ] **`What is a plan?` opens without pushing anything off the rail.**
      Expand it. With few plans it simply pushes the actions down into the
      slack; with enough plans to fill the rail (eight or more) the plan
      list shrinks and scrolls instead, and the actions stay on screen.
      Check the second case at the window floor — that is the one the
      list's `min-height: 0` exists for. Collapse it again and the list
      returns to its height.
- [ ] **An empty roster names the control.** With no characters
      authorised, the roster reads `No characters yet. Press “Add
      character” to sign one in with EVE SSO.` — the name on the button,
      not a direction to look left.
- [ ] **The unscored group does not blame the wrong thing.** Empty the
      plans folder and reload plans. Every character collapses into one
      group; its heading is `Not scored yet` and the hint beside the roster
      says there are no local plans. The heading must NOT say the roster
      needs refreshing — refreshing is not what is missing, and it is the
      control the user would otherwise reach for.
- [ ] **Typing in the filter box narrows the roster live**, and the
      `Clear filter` action appears only while a filter is active and
      removes it when clicked.
- [ ] **A small roster opens expanded** (round 5's S1). With six or fewer
      characters, open Skills from cold. Expected: every row is already
      open, so `Forget character` and any re-authenticate banner — the
      only surface in the whole app for either — are on screen without
      hunting for a chevron, and the requirement lists fill a pane that
      was ~70% empty. Collapse a row, leave the route and come back: it
      stays collapsed. The expansion is one-shot, on the first payload
      that carries anyone; it must not re-open rows you closed.
- [ ] **A large roster does not.** With seven or more characters, the same
      cold open leaves every row collapsed — the cap is about how many
      requirement evaluations the page orders without being asked, and a
      fleet-sized roster did not ask for one each.
- [ ] **Expanding a row shows the right pieces together:** the `Stale`
      badge (if any), a re-authenticate banner placed above the
      requirements list (not interleaved with them), and the outstanding
      requirements list with any already-Active skills absent from it.
- [ ] **Every number on the screen says what it counts** (round 3, S1).
      A group head reads `Missing requirements   1 character`, not
      `Missing requirements   1`. That number counts CHARACTERS while the
      header names REQUIREMENTS, and the row below it and the plan heading
      above it both state requirement counts — three numbers in one
      vocabulary, previously two of them bare. Round 2's finding 2 renamed
      the words and left the numbers, so check the numbers.
- [ ] **No row repeats the heading it sits under** (round 3, S2). The rows
      are grouped BY status, so a `Ready` group's rows say only a name, and
      an `Untrained requirements` group's rows say only a name. The two
      that still carry a value carry something the heading cannot: a
      `Missing` row says `2 requirements` (which is also why its group
      sorts fewest-first) and a `Training` row says the ETA alone,
      `13h 25m` or `timing unknown`. The catch-all bucket is the deliberate
      exception — its rows show the raw readiness string, because the
      heading says `Unrecognised` for all of them.
- [ ] **`Forget character` is a red-outlined button, not red text**
      (round 3, S3/S4). It is the app's one destructive treatment, the same
      one Profiles' `Delete` wears. The inline two-step below it is
      unchanged and must stay: this row is the only place a character can
      be forgotten or re-authenticated, so a dialog would cover it.
- [ ] **LOAD-BEARING: a character's fetch line survives a second render**
      (round 3, D3/S6). Expand a character that HAS been refreshed and
      confirm it reads `Last fetched 5h ago`. Then cause any mutation that
      pushes fresh state — press `Refresh characters`, or select a
      different plan — and look again. It must still read a time. Until
      D3's fix, the label was added by the `skills_state` method only, the
      page asks for that on first entry only, and every render after the
      first push printed `Never fetched` for every character, beside queue
      timing from the same payload. Nothing in the suite renders the page
      and the bridge contract test checks handler names rather than payload
      shape, so this item is what stands between that and a release.
- [ ] **A character with no snapshot explains itself and offers the fix**
      (round 3, S6). Authorise a character and expand its row BEFORE any
      refresh has landed. Expected: a note saying Wingman has not read its
      skills from EVE yet, with a `Refresh characters` button in it — not a
      bare `Never fetched` with the nearest control 700px away in the rail.
      The requirement list under it must say `Not scored yet`, NOT `Nothing
      outstanding — every requirement is trained and active`: the evaluator
      returns an empty requirement list for a character it could not score,
      and that congratulation is what the empty list used to read as.
- [ ] **`Copy plan` puts the plan on the clipboard** (round 3, S7). With a
      plan selected, press `Copy plan` on the pane heading and paste into a
      text editor. Expected: one `Skill Name IV` line per requirement, in
      roman numerals, in plan order — and the status strip says it was
      copied. Then paste it into EVE's skill plan import and confirm the
      game accepts it and drops the skills already trained (that is why the
      whole plan is enough and no per-character diffing is done). With no
      plan selected the button is disabled rather than absent.
- [ ] **The two-step Forget cannot be triggered by one mis-click.** First
      click arms the control (it changes to a confirm state); a second,
      separate click is required to actually forget the character;
      clicking anywhere else first disarms it without forgetting anyone.
- [ ] **`?dev=1` with the catch-all bucket renders, including the
      unrecognised readiness value.** Launch with `?dev=1` appended to the
      URL. `dev.js`'s character id 9 has readiness `'Ascendant'`,
      deliberately a value the UI does not recognise. **This character MUST
      still render a row with a working Forget control** rather than being
      silently dropped or breaking the rest of the list — that is the
      lockout guard: an unrecognised readiness value from a future API
      change must degrade to an unstyled bucket, not vanish the row a user
      needs in order to remove a broken character.
- [ ] **`DEV.skillsAuth(true)` and `DEV.skillsProgress(3, 9)` behave in a
      live browser**, not just in reasoning: with `?dev=1` loaded, run each
      from devtools and confirm the roster and progress indicator update
      as their names imply.
- [ ] **`Reload plans` and `Open plans folder` both actually work.** Drop a
      new `.txt` plan file into the plans folder, click `Reload plans`, and
      confirm it appears in the rail with the right requirement count.
      Then click `Open plans folder` and confirm the OS shell opens the
      correct directory. This second check is in the same failure family
      as the WebView2 items above it: `os.startfile` cannot be exercised in
      CI at all, so nothing but a human clicking the button proves the
      folder that opens is the one plans actually load from.
- [ ] **Selecting a different plan actually re-targets everything.** With
      two plans present, select the plan that is not already selected.
      Expected: the roster regroups against the new plan's requirements,
      the ready ratio in the rail updates for the new plan, and — if a row
      was already expanded — its requirement list re-fetches and shows the
      **newly selected plan's** requirements, not the previous plan's. This
      last part is the one to watch closely: a stale in-flight fetch
      resolving after the switch and rendering under the wrong plan is a
      silent bug — the row looks populated and correct, but every
      requirement on it belongs to the plan you left.
- [ ] **LOAD-BEARING: the roster group order and the within-group sort are
      both exactly right.** Launch with `?dev=1` (it seeds one character
      per bucket) and confirm the groups appear top to bottom in this
      order: `Ready`, `Training`, `Locked`, `Missing`, `Unknown`,
      `Unscored`, then the catch-all bucket last. Within `Missing`, with
      more than one character in it, confirm the character with the
      **fewest** missing requirements sorts first. Nothing under `tests/`
      exercises this grouping or ordering at all — it lives entirely in
      `skills.js` — so this item is the only thing standing between a
      regression here and a release. A silent reorder or a resorted
      `Missing` group would not error or throw; it would just be wrong,
      and nothing else in this checklist or the suite would catch it.

### Frozen build

- [ ] **LOAD-BEARING: the installed build serves `skills.js`.** Install the
      built artifact, launch it, and click Skills. The rail renders, the
      buttons respond, and the roster fills. CI asserts the file exists at
      `_internal\web\skills.js`; only launching proves the page fetched and
      executed it. A route whose static markup renders and whose every
      control is inert is exactly what a missing script looks like —
      PyInstaller exits 0 when a `datas` entry resolves to nothing, and
      pywebview reports no error for a script that 404s.
- [ ] **The frozen build reaches only CCP.** With previews and the uploader
      idle, the only hosts this feature contacts are `login.eveonline.com`
      and `esi.evetech.net`.
