# OBS YouTube Uploader

Watches your OBS recording folder and lets you select, optionally stitch,
and upload recordings to YouTube. Pairs well with
[obs-fightrecorder](https://github.com/JesseSwale/obs-fightrecorder), but
works with any OBS recording.

## Install

1. Download the latest `OBS-YouTube-Uploader-Setup-*.exe` from
   [Releases](https://github.com/elboaf/OBS-YouTube-Uploader/releases).
2. Run it.

That's it. Python, FFmpeg, and Google credentials are all bundled — there
is no separate script to install in OBS, and no Google Cloud project to set
up yourself.

**Windows will warn you** that it "protected your PC" — the installer and
the app are unsigned. Click **More info** → **Run anyway**. This is
expected and happens once per machine, both for the installer and the
first launch of the app.

**Currently in pre-release:** Google has not finished verifying the app, so
only approved testers can sign in. Anyone else who tries **Connect Google
Account** sees `Error 403: access_denied` — not a warning, a hard stop.
Open an issue to be added as a tester.

## Use

The app lives in your system tray and starts with Windows. When a recording
finishes you get a notification; **click the tray icon** to open the
uploader.

- **Select** one or more recordings with the checkboxes.
- **Stitch** merges the selection into one video, earliest first.
- **Upload Selected** uploads them, then fills in the **YouTube Link**
  column for each row. Use **Copy** or **Open** on any row once it has a
  link.
- **Delete Selected** permanently deletes the selected files from disk
  after a confirmation dialog. This cannot be undone.

## Settings

| Setting | Default | Notes |
|---|---|---|
| Privacy | `private` | `private`, `unlisted`, or `public` |
| Category | `20` (Gaming) | [Category IDs](https://developers.google.com/youtube/v3/docs/videoCategories/list) |
| Notification | `toast` | `toast` for a tray notification, `popup` to raise the window |

Stored in `%LOCALAPPDATA%\OBSYouTubeUploader\settings.json`.

## Limits

Uploads are capped at **100 per day, shared across every user of the
app** — this is YouTube's default per-project quota, not a per-account
limit, so heavy use by one person can exhaust the quota for everyone else
until it resets. If you hit it, wait until tomorrow.

## Upgrading from 1.x

1. In OBS, go to **Tools → Scripts** and remove the old script (`obs_trigger.py`
   or similar). It's no longer used — the tray app watches the recording
   folder directly.
2. Uninstall or delete your old checkout; it isn't needed once the tray app
   is installed.
3. After installing, open **Settings → Connect Google Account** and sign in
   once. Your old `client_secrets.json` and token file are not reused —
   there is no migration of stored credentials or settings.

## Building from source

```bash
python -m pip install -e ".[dev]"
python -m pytest tests/
python -m obs_youtube_uploader
```

Running from source needs your own Google OAuth desktop credentials in
`obs_youtube_uploader/credentials.py`; releases have them injected at build
time and never checked into the repository.

## License

Personal tool, use at your own risk. Not affiliated with OBS Studio, CCP
Games, or Google/YouTube.
