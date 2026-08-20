# Standalone Repackaging Design

**Date:** 2026-08-20
**Status:** Approved, pending implementation plan

## Problem

The tool works, but installing it takes six manual steps across three
different systems, and one of those steps is a seven-step detour through the
Google Cloud console. In practice this means almost nobody who would benefit
from the tool successfully installs it.

Current install burden:

| # | Step | Addressed by this design |
|---|------|--------------------------|
| 1 | Install Python 3.11 | Eliminated — frozen binary |
| 2 | `pip install -r requirements.txt` | Eliminated — frozen binary |
| 3 | Obtain `ffmpeg.exe` / `ffprobe.exe` | Eliminated — bundled |
| 4 | Copy both `.py` files to a folder | Eliminated — installer |
| 5 | Add script in OBS; set recording dir and `pythonw.exe` path | Eliminated — OBS integration removed |
| 6 | Create Google Cloud project, OAuth client, allowlist self, place `client_secrets.json` | Eliminated — shared embedded credentials |

Target: **one step.** Download the installer, run it. See "Release gating"
below — this target is only met for the general public once OAuth
verification has cleared.

## Goals

- Reduce installation to running a single Windows installer.
- Remove the dependency on OBS's Python scripting runtime entirely.
- Preserve all existing functionality: browse, select, stitch, upload.
- Introduce testable seams so the project can have automated tests at all.

## Non-goals

Explicitly out of scope, to prevent scope drift during implementation:

- Rewriting the UI (Tkinter stays).
- macOS or Linux support (OBS FightRecorder is Windows-only; so is the audience).
- Auto-update.
- Code signing (see "SmartScreen" below).
- A "bring your own Google credentials" wizard (see "Quota" below).
- Changing stitching behavior or output naming.
- OAuth verification paperwork — a console task for the maintainer, not a code change.

## Key decisions

### Credentials: shared, embedded, initially unverified

Each user creating their own Google Cloud project is the single largest
install barrier and cannot be fixed by packaging. Instead a single OAuth
desktop client is embedded in the release; users click "Connect Google
Account" and never see the console.

The embedded client secret is extractable from the binary. This is expected
and explicitly sanctioned by Google for installed applications — the desktop
flow's security derives from the loopback redirect and the user's own
consent, not from the secret being confidential. This is documented here so
it is not later mistaken for a vulnerability.

**Two independent Google gates apply, and they are frequently conflated:**

- **Gate 1 — OAuth verification.** Clearing it removes the "unverified app"
  interstitial, the 100-test-user allowlist, and the 7-day refresh-token
  expiry. Requires a privacy policy URL, a homepage, and a demo video.
  Achievable; being pursued in parallel with implementation. Flipping the
  console from testing to production requires **no code change**.
- **Gate 2 — YouTube API Services compliance audit.** Required to exceed the
  default allocation of **100 `videos.insert` calls per day, shared across
  every user of the project**. Framed by Google as being for "large
  projects," with no published turnaround.

**Decision on Gate 2: accept the 100/day ceiling.** Expected usage for a
niche EVE tool sits well below it. The BYO-credentials escape hatch is
deliberately deferred (YAGNI) — but the `403 quotaExceeded` error is handled
gracefully regardless, because a hard ceiling that produces a traceback is a
crash, not a limit.

While unverified, **refresh tokens expire every 7 days.** Re-authentication
is therefore a routine weekly path, not an edge case, and must be seamless.

### Release gating

**Public release is gated on Gate 1 clearing.** This is not a soft
preference. While the project is in testing mode, Google permits *only*
manually allowlisted test users to complete the OAuth flow at all — a
non-allowlisted user does not see a warning they can dismiss, they receive
`Error 403: access_denied` and cannot authenticate. The "one step" install
promise is therefore false for the general public until verification lands.

Consequences for sequencing:

- Implementation can proceed in full before verification clears; nothing in
  the code depends on it.
- Pre-verification builds may be shared only with allowlisted testers, and
  release notes must say so explicitly.
- The general-availability announcement waits for Gate 1.

If verification is ultimately denied, the fallback is the deferred
BYO-credentials wizard, which is the only other way an arbitrary user can
authenticate. That path is not built now, but denial is the trigger for
building it.

### Delivery: PyInstaller one-folder + Inno Setup installer

Rejected alternatives:

- **One-file portable `.exe`** — unpacks to temp on every launch (slow with
  ffmpeg bundled), offers no natural home for a "start with Windows" option,
  and trips antivirus heuristics markedly more often than one-folder builds.
  May ship later as a secondary download.
- **Bootstrap script around embedded Python** — smallest change and smallest
  download, but preserves every current failure mode (network failures
  mid-install, pip resolution errors, tracebacks in a console window). Moves
  the pain rather than removing it.

The installer provides a Start Menu shortcut, a "run at login" checkbox, and
clean uninstall. Run-at-login matters specifically because the tray watcher
is useless if the user forgets to start it.

### OBS integration: removed entirely

`obs_trigger.py` is deleted. It existed only to notice "recording stopped"
and launch a GUI with a folder path — which a folder watcher does with zero
OBS configuration. Removing it eliminates install steps 4 and 5 and drops
the dependency on OBS's bundled Python, a well-known compatibility swamp.

Side benefit: the tool becomes useful to anyone recording anything, not only
EVE players running FightRecorder.

### FFmpeg: bundled

`ffmpeg.exe` and `ffprobe.exe` add roughly 80–160 MB. Neither is strictly
required for the app to start: `ffprobe` produces the duration column, and
when it is absent or fails the duration degrades to `"?"`
(`youtube_uploader.py:115-131`); `ffmpeg` is required only for stitching.
Bundling both is preferred over fetch-on-demand: a one-time large download
beats a runtime network dependency that fails at the moment the user wants
to upload.

**Degradation behavior, stated explicitly.** Current code disables stitching
unless *both* binaries are present (`youtube_uploader.py:96-97`,
`:394-397`), even though stitching invokes only `ffmpeg`
(`:484-496`). That coupling is incidental, not intended. The new behavior:

| Present | Result |
|---------|--------|
| Both | Full functionality |
| `ffmpeg` only | Stitching works; duration column shows `?` |
| `ffprobe` only | Stitching disabled with an explanatory tooltip; durations shown |
| Neither | App still runs; stitching disabled, durations show `?` |

The app never refuses to start over a missing binary. Since both are
bundled, this matters only when antivirus quarantines one of them — which is
exactly when a clear message beats a hard failure.

### SmartScreen: accepted and documented

An unsigned executable downloaded from GitHub triggers Windows' full-screen
"Windows protected your PC" warning, with "Run anyway" hidden behind a "More
info" link. An OV certificate costs roughly $200–400/year and still requires
reputation-building before the warning quiets; EV clears it immediately but
costs more and needs a hardware token.

For a community tool whose users already trust the author enough to run an
OBS plugin, the warning is accepted and documented in the README with a
screenshot. Revisit if adoption grows.

## Architecture

One process, six units, split so that five of them are testable without
OBS, without Google, and without a GUI. Today the entire tool is one
630-line module that can only be exercised by running it.

| Unit | Responsibility | Depends on |
|------|----------------|------------|
| `obsconfig.py` | Locate and parse OBS `basic.ini` -> recording folder | filesystem |
| `watcher.py` | Poll folder, decide when a file is settled, emit ready-events | filesystem |
| `library.py` | Video discovery by extension, metadata probing, sorting, deletion | filesystem, ffprobe |
| `stitch.py` | Ordering, ffmpeg invocation, output naming, temp-file lifecycle | ffmpeg |
| `uploader.py` | OAuth, resumable upload with retry, title suffixes, returned video IDs, error classification | Google APIs |
| `app.py` | Tray icon, notifications, Tk window, link column, wiring | all of the above |

Six units rather than four. The original four-way split left substantial
existing behavior implicitly inside `app.py`, which would have undermined
the testability the split exists to provide. Each item below is behavior
that exists today and must be preserved, now with an explicit owner.

Line references are against `youtube_uploader.py` at `b04c3a7`:

| Existing behavior | Current location | New owner |
|---|---|---|
| `VIDEO_EXTS` and folder discovery | `:27`, `:348-357` | `library.py` |
| ffprobe duration/size metadata | `:102-131` | `library.py` |
| **Delete selected files from disk** | `:582-604` | `library.py` |
| Stitch ordering (by mtime, earliest first), `filter_complex` concat, output path | `:470-501` | `stitch.py` |
| Temp-file cleanup for stitched output | `:457-458` | `stitch.py` |
| `(1/3)` title suffixes for multi-upload | `:503-516` | `uploader.py` |
| Privacy / category applied to upload body | `:436-443` | `uploader.py` |
| **Returning the uploaded video ID** | `:527-530` | `uploader.py` |
| **YouTube link column and Copy button** | `:311`, `:366-372`, `:539-580` | `app.py` |

`library.py` and `stitch.py` are both testable without a GUI and without
network access, which is the point of naming them.

### Upstream changes absorbed (commit `b04c3a7`, 2026-08-20)

The maintainer shipped new work after this design was first written. All of
it is behavior the port must preserve, and one part changes a decision.

**1. YouTube link column.** Each row now carries a read-only entry showing
the uploaded video's URL, plus a per-row Copy button (`:311`, `:366-372`,
`:539-580`). `_upload_one` returns the video ID to make this possible
(`:503`, `:527-530`).

This interacts with the retry design below: **retry must preserve the
returned video ID.** A resumed upload still yields a response containing
`id`, but a retry implementation that swallows and re-issues the request
would lose it, silently breaking the link column. The retry tests assert the
ID survives a mid-upload failure.

In stitch mode the single resulting URL is applied to every selected row
(`:553-562`); otherwise IDs are zipped positionally against the selection
(`:563-572`).

**2. Delete Selected.** A button permanently removes selected files from
disk after a confirmation dialog (`:582-604`). Note this **contradicts the
current README**, which states that original recordings are "never modified
or deleted" — the README is now wrong and is corrected as part of this work.

Two consequences for the new architecture:

- Deletion moves into `library.py` so it is testable against a temp
  directory rather than only by clicking the button.
- **The watcher must be told.** Deleting a file the watcher has recorded in
  `seen.json` leaves a stale entry; if OBS later writes a new recording to
  the same path, the size/mtime comparison decides correctly, but the
  cleaner behavior is to drop the entry at delete time. `library.py`
  emits a deletion event that `watcher.py` consumes.

Deletion remains a permanent `unlink()` rather than a Recycle Bin move,
matching current behavior. This is worth revisiting — a mis-click destroys
unrecoverable footage — but changing it is out of scope here and is recorded
as a follow-up rather than silently altered.

**3. Credential model already moved.** The Settings help text was rewritten
from the eight-step Google Cloud walkthrough to four steps that assume
credentials are already present, including "Accept the unverified
application warning" (`:177-186`). This **confirms the shared-credential
direction of this design** — the maintainer arrived at the same conclusion
independently.

It also leaves a gap this design closes: the help text now promises no
setup, but `_connect` still hard-fails when `client_secrets.json` is absent
(`:213-217`), and that file is not in the repository. In the current
distribution a user following the new instructions gets a "Missing File"
error with no way to resolve it. Embedding the credentials at build time
(see "Build and release") is what makes the new help text true.

**4. Interpreter diagnostics become dead code.** The import-failure dialog
now reports `sys.executable` and a matching `pip install` command
(`:204-215`) — a targeted fix for users who pip-installed into a different
interpreter than the one OBS invokes. The frozen build removes that failure
mode entirely, so this code is **intentionally dropped** rather than ported.
It is listed here so its removal is not mistaken for an oversight.

**5. Defaults emptied.** Title and description now default to empty strings
rather than "EVE Online Recording" and a FightRecorder boilerplate
(`:292`, `:298`). This aligns with the generalization noted under "OBS
integration" and is preserved as-is; the existing `or "Untitled"` fallback
(`:506`) still guards empty titles.

### Defects observed in the upstream commit

Found while reviewing `b04c3a7`. None block this design; all are recorded so
the port does not faithfully reproduce them.

- **Unreachable duplicate block** at `:531-534` — `_upload_one` returns at
  `:530`, then repeats the same four lines. Harmless, clearly a paste error,
  dropped in the port.
- **Missing newline** in the Settings help text at `:183` — step 3's string
  has no trailing `\n`, so it renders as
  `...warning!!4. Grant permission...`. Fixed in the port.
- **Positional zip misalignment** at `:563` — `video_ids` only receives
  entries for uploads returning an ID (`:450-452`), so a successful upload
  with a missing ID shifts every subsequent row's link by one. Low
  likelihood, but the port keys links by source file rather than by
  position, which removes the class of bug rather than the instance.

### Threading

Tkinter owns the main thread via a **hidden root window created at startup**
and `deiconify()`d on demand. Creating the Tk root lazily from a callback,
or off the main thread, is the classic crash source in this design and is
avoided by construction.

The tray icon, the folder watcher, and uploads each run on worker threads.
Workers communicate with the UI through a queue drained by the Tk main loop
on a timer. Workers never touch widgets directly.

### New dependencies

- `pystray` — tray icon and native Windows notifications.
- `Pillow` — required by `pystray` for the icon image.

## Data flow

```
OBS finishes writing a recording
        |
watcher polls folder every 3s, sees a new or changed file
        |
size + mtime unchanged across 3 consecutive polls -> "settled"
        |
debounce 5s (FightRecorder's merge writes a second "Fight *.mkv" after clips)
        |
    +---------------+---------------+
notify_mode = toast        notify_mode = popup
        |                          |
tray notification          window raised directly
"2 new recordings ready"
        |
user clicks -> window opens, newest first, pre-selected
```

### Why polling rather than filesystem events

`watchdog` would be another dependency; native change events do not fire
reliably on network or mapped drives; and a 3-second poll of a single
directory is negligible. Polling also makes settled-detection testable with
an injected clock.

### Why settled-detection is required

A file appearing in the directory does not mean it has finished being
written. Additionally, FightRecorder's optional merge step writes a *second*
file after the individual clips, so a naive watcher fires twice for one
fight. Hence stability polling plus a debounce window.

### Watcher lifecycle

Left undefined, a folder watcher has two failure modes that only appear
after the first happy-path demo. Both are specified here.

**Startup baseline.** On launch the watcher enumerates the recording folder
and records every existing file as already-seen *without* notifying. Without
this, every launch — including the automatic one at login — would announce
the user's entire back catalogue of recordings.

The seen-set persists to `%LOCALAPPDATA%\OBSYouTubeUploader\seen.json` as
`{path: (size, mtime)}`. Persistence matters because the app is set to run
at login: an in-memory-only baseline would treat everything recorded while
the app was closed as pre-existing, silently swallowing genuinely new
recordings from an OBS session run without the uploader open. On startup,
files present but absent from the persisted set are treated as new and
notified once.

Entries whose file no longer exists are pruned on each startup so the set
does not grow without bound.

**Single-instance enforcement.** The installer's run-at-login option plus a
Start Menu shortcut make double-launch easy and likely. Two instances mean
two watchers, duplicate notifications, and — worst — two concurrent uploads
of the same recording, since today's concurrency guard
(`youtube_uploader.py:398-400`) only prevents a second upload *within* one
process.

A named Windows mutex (`Global\OBSYouTubeUploader`) is acquired at startup.
If it is already held, the second instance surfaces the existing window and
exits rather than starting a second watcher.

## Notification behavior

Two modes, user-configurable, defaulting to toast:

- **Toast (default)** — tray notification; nothing steals focus. Chosen
  because in EVE the user may still be undocked and flying when a recording
  finishes, and a window stealing focus mid-fight is actively harmful.
- **Popup** — window raised immediately, matching current behavior, retained
  as a setting so the existing workflow is not felt as a regression.

Persisted in `settings.json` as `notify_mode`, alongside the existing
`privacy` and `category` keys. See "Settings schema" for the exact key
names and the default resolved there.

## Configuration and state

**Behavior change.** Today `youtube_token.json`, `uploader_settings.json`,
and `client_secrets.json` live in `SCRIPT_DIR` alongside the script. This
breaks as soon as the app is installed into `Program Files`, which is not
writable by a non-admin user.

| File | Current location | New location |
|------|------------------|--------------|
| `uploader_settings.json` | `SCRIPT_DIR` (`:25`) | `%LOCALAPPDATA%\OBSYouTubeUploader\settings.json` |
| `youtube_token.json` | `SCRIPT_DIR` (`:23`) | `%LOCALAPPDATA%\OBSYouTubeUploader\token.json` |
| `client_secrets.json` | `SCRIPT_DIR` (`:24`) | Removed — embedded in binary |
| `uploader_debug.log` | `SCRIPT_DIR` (`:26`) | `%LOCALAPPDATA%\OBSYouTubeUploader\logs\` |
| `obs_stitched_upload.mkv` | `%TEMP%`, fixed name (`:472-473`) | `%LOCALAPPDATA%\OBSYouTubeUploader\tmp\`, unique per run |
| `seen.json` (new) | — | `%LOCALAPPDATA%\OBSYouTubeUploader\seen.json` |
| `ffmpeg.exe`, `ffprobe.exe` | `SCRIPT_DIR` or PATH (`:60-85`) | Install dir, resolved via `sys._MEIPASS` |

The stitch artifact moves out of `%TEMP%` and gains a unique name for two
reasons. The current fixed filename means two runs collide, and cleanup sits
*inside* the `try` block after a successful upload (`:457-458`), so **a
failed upload leaks the file permanently** — potentially many GB. Cleanup
moves to a `finally` block, and orphaned files in the tmp directory are
swept on startup.

### Settings schema

The existing settings keys are `privacy` and `category` — note `category`,
not `category_id` (`youtube_uploader.py:193-194`, `:199-201`, `:442-443`).
Both are carried forward under their existing names.

One pre-existing inconsistency is resolved rather than ported: the privacy
default is `"unlisted"` when loading settings (`:193`) but `"private"` when
building the upload body (`:442`), while the README documents `private`.
**`private` wins** — it is the documented behavior and the safe default for
a tool that uploads automatically.

Since no migration code is written (see "Migration"), the single existing
user re-selects privacy and category once on first run. Their previous
`uploader_settings.json` is not read.

The token grants upload access to the user's channel, so it is written with
restrictive ACLs rather than inheriting directory defaults.

### Recording folder auto-detection

On first run the app reads OBS's own configuration at
`%APPDATA%\obs-studio\basic\profiles\<profile>\basic.ini` to pre-fill the
recording folder, so even that setting is a confirmable default rather than
something the user must locate. Falls back to a first-run wizard prompt when
OBS config is absent, unreadable, or ambiguous across multiple profiles.

## Error handling

The current failure mode is a traceback in a log file nobody reads. Each
case below produces a specific, plain-language dialog:

| Condition | Behavior |
|-----------|----------|
| `403 quotaExceeded` | "YouTube's daily upload limit for this app has been reached. Please try again tomorrow." |
| `403 access_denied` at sign-in | Pre-verification only: "This build is limited to approved testers." Distinguishes the Gate 1 case from a genuine auth failure. |
| Refresh token expired or revoked | Silently re-run OAuth; dialog only if that also fails. Weekly path while unverified — must be seamless. |
| Recording folder missing / OBS never configured | First-run wizard prompts for folder instead of failing |
| ffmpeg or ffprobe missing | Degrade per the FFmpeg table above; never block startup |
| Network failure mid-upload | Retry with backoff, resuming the existing session — see below |

### Upload retry is new work, not preserved behavior

**Correction to an earlier assumption.** `MediaFileUpload` is constructed
with `resumable=True` (`youtube_uploader.py:514`), which makes the
*protocol* resumable — but the code does not use that capability. The chunk
loop calls `next_chunk()` inside a bare `while` with no exception handling
(`:518-525`), so any transient network error propagates to the outer handler
(`:464-468`), which shows a dialog and discards the `request` object along
with all upload progress.

A "Retry" button bolted onto the current structure would therefore restart
the upload from zero, which for a multi-GB fight recording is the whole
problem rather than a fix.

Real retry means retaining the `request` object and looping on transient
failures:

- Retry on HTTP 500, 502, 503, 504 and on socket/connection errors.
- Exponential backoff with jitter, capped at a bounded number of attempts.
- Do **not** retry 4xx other than 408/429 — those are permanent and retrying
  wastes quota.
- Surface retry attempts in the status line so a stalled upload is visibly
  retrying rather than apparently frozen.
- On final failure, keep the partially-uploaded session ID so a manual
  Retry resumes rather than restarts.

This lives in `uploader.py` and is the one piece of genuinely new logic in
the otherwise behavior-preserving port.

## Build and release

GitHub Actions on tag push: PyInstaller one-folder build -> Inno Setup
compile -> attach installer to the GitHub release.

FFmpeg binaries are fetched at build time from a pinned release URL and
checksum-verified, rather than committed to git.

The embedded OAuth client secret is injected from a repository secret at
build time so it does not live in the source tree.

## Testing

Automated unit tests for the units that have no external dependencies:

- **Settled-file detector** — injected clock and fake filesystem; covers the
  still-being-written case and the FightRecorder double-write case.
- **Watcher baseline** — startup with an empty, stale, and current
  `seen.json`; confirms no notification for pre-existing files and exactly
  one for genuinely new ones.
- **OBS ini parser** — fixture ini files, including missing file, malformed
  file, and multiple profiles.
- **Error classifier** — fixture Google API error payloads mapping to the
  table above, including the retryable/permanent split.
- **Retry policy** — a fake transport that fails N times then succeeds;
  asserts the session resumes rather than restarting, that permanent 4xx
  errors are not retried, that the attempt cap holds, and that the returned
  video ID survives a mid-upload failure.
- **Video discovery and metadata** (`library.py`) — extension filtering,
  sorting, and the ffprobe-absent degradation to `"?"`.
- **Deletion** (`library.py`) — against a temp directory: confirms the
  selected files go, unselected files stay, per-file failures are counted
  rather than aborting the batch, and the watcher's seen-set entry is
  dropped.
- **Link mapping** — video IDs map to the correct source file in both stitch
  and non-stitch modes, including when an upload returns no ID.
- **Stitch planning** (`stitch.py`) — ordering by mtime and command
  construction, asserted without invoking ffmpeg.

The GUI and the live upload path remain manually verified via a smoke-test
checklist committed to the repo. This is a deliberate limit: automating a
real YouTube upload in CI would require live credentials and would consume
the very quota the design is constrained by.

## Migration

There is exactly one existing user, so no migration code is written. The PR
description and README carry two instructions:

1. Remove `obs_trigger.py` from OBS Tools -> Scripts; it is no longer used.
2. Re-authenticate once via Settings -> Connect Google Account.

The previous `client_secrets.json` and token file are ignored; the user
moves to the shared credentials. Writing legacy-import code for a single
person would create a code path to test and carry indefinitely for no
lasting benefit.

### README corrections required

The README has drifted from the code and must be updated alongside this
work, independently of the packaging changes:

- It states original recordings are "never modified or deleted." The Delete
  Selected button added in `b04c3a7` makes this false.
- It documents the whole eight-step Google Cloud setup, which the shared
  credentials remove.
- It documents the OBS script installation, which no longer exists.
- It does not mention the YouTube link column.
- Its stated `private` privacy default should match the resolved default
  under "Settings schema".

## Risks and open items

| Risk | Mitigation |
|------|------------|
| OAuth verification (Gate 1) is delayed | **Public release is blocked.** In testing mode only allowlisted testers can authenticate at all — non-allowlisted users get `403 access_denied`, not a dismissible warning. Implementation proceeds regardless; only the GA announcement waits. |
| OAuth verification (Gate 1) is denied | Build the deferred BYO-credentials wizard; it becomes the only route for arbitrary users |
| Usage exceeds 100 uploads/day (Gate 2) | Accepted. Graceful error message; BYO-credentials wizard is the known escape if it ever binds |
| Retry logic is new code on the critical path | Covered by unit tests against a fake transport; failure mode is no worse than today's abandon-on-error |
| Antivirus false positives on the PyInstaller build | One-folder build already reduces this vs one-file; document a VirusTotal link if reports arrive |
| Installer size (~150 MB) deters downloads | Accepted as the cost of removing the Python and FFmpeg prerequisites |
