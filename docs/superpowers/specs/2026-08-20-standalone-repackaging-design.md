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

Target: **one step.** Download the installer, run it.

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

`ffmpeg.exe` and `ffprobe.exe` add roughly 80–160 MB. `ffprobe` is required
for the main screen (it produces the duration column); `ffmpeg` only for
stitching. Bundling both is preferred over fetch-on-demand: a one-time large
download beats a runtime network dependency that fails at the moment the
user wants to upload.

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

One process, four units, split so that three of them are testable without
OBS, without Google, and without a GUI. Today the entire tool is one
531-line module that can only be exercised by running it.

| Unit | Responsibility | Depends on |
|------|----------------|------------|
| `obsconfig.py` | Locate and parse OBS `basic.ini` -> recording folder | filesystem |
| `watcher.py` | Poll folder, decide when a file is settled, emit ready-events | filesystem |
| `uploader.py` | OAuth, resumable upload, error classification | Google APIs |
| `app.py` | Tray icon, notifications, Tk window, wiring | all of the above |

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

## Notification behavior

Two modes, user-configurable, defaulting to toast:

- **Toast (default)** — tray notification; nothing steals focus. Chosen
  because in EVE the user may still be undocked and flying when a recording
  finishes, and a window stealing focus mid-fight is actively harmful.
- **Popup** — window raised immediately, matching current behavior, retained
  as a setting so the existing workflow is not felt as a regression.

Persisted in `settings.json` as `notify_mode`, alongside the existing
`privacy` and `category_id` settings, which are carried over unchanged.

## Configuration and state

**Behavior change.** Today `youtube_token.json`, `uploader_settings.json`,
and `client_secrets.json` live in `SCRIPT_DIR` alongside the script. This
breaks as soon as the app is installed into `Program Files`, which is not
writable by a non-admin user.

| File | New location |
|------|--------------|
| `uploader_settings.json` | `%LOCALAPPDATA%\OBSYouTubeUploader\settings.json` |
| `youtube_token.json` | `%LOCALAPPDATA%\OBSYouTubeUploader\token.json` |
| `client_secrets.json` | Removed — embedded in binary |
| `uploader.log` | `%LOCALAPPDATA%\OBSYouTubeUploader\logs\` |
| `ffmpeg.exe`, `ffprobe.exe` | Install dir, resolved via `sys._MEIPASS` |

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
| Refresh token expired or revoked | Silently re-run OAuth; dialog only if that also fails. Weekly path while unverified — must be seamless. |
| Recording folder missing / OBS never configured | First-run wizard prompts for folder instead of failing |
| ffmpeg missing (e.g. antivirus quarantine) | Stitching checkbox disables itself with an explanatory tooltip |
| Network failure mid-upload | Resumable chunks already handle this; surface a Retry button rather than discarding progress |

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
- **OBS ini parser** — fixture ini files, including missing file, malformed
  file, and multiple profiles.
- **Error classifier** — fixture Google API error payloads mapping to the
  table above.

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

## Risks and open items

| Risk | Mitigation |
|------|------------|
| OAuth verification (Gate 1) is delayed or denied | Tool remains fully functional in testing mode; cost is the unverified warning and weekly re-auth |
| Usage exceeds 100 uploads/day (Gate 2) | Accepted. Graceful error message; BYO-credentials wizard is the known escape if it ever binds |
| Antivirus false positives on the PyInstaller build | One-folder build already reduces this vs one-file; document a VirusTotal link if reports arrive |
| Installer size (~150 MB) deters downloads | Accepted as the cost of removing the Python and FFmpeg prerequisites |
