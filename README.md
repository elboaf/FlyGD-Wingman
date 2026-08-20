# OBS YouTube Uploader

A lightweight tool that automatically opens when OBS stops recording, letting you select, optionally stitch, and upload your EVE Online fight recordings directly to YouTube.

Designed to pair with [obs-fightrecorder](https://github.com/JesseSwale/obs-fightrecorder) — when FightRecorder triggers OBS to stop recording after a fight, this uploader pops up with your latest videos ready to go.

---

## Features

- **Auto-launch on recording stop** — triggered by an OBS script
- **Video browser** — lists all recordings with date, size, and duration
- **Checkbox selection** — pick one or many videos to upload
- **Optional stitching** — concatenate multiple fights into a single video (earliest → latest)
- **YouTube OAuth** — connect your Google account once, uploads are automatic after that
- **Resumable uploads** — 4MB chunks with progress bar; survives connection hiccups
- **Self-contained FFmpeg** — bundle `ffmpeg.exe` and `ffprobe.exe` alongside the script; no PATH editing required
- **Privacy & category defaults** — set once in Settings, applies to every upload

---

## Requirements

- **Python 3.10+** (Windows users: install from [python.org](https://www.python.org/downloads/))
- **OBS Studio** with Python scripting support enabled
- **FFmpeg** binaries (`ffmpeg.exe` and `ffprobe.exe` on Windows)
- A **Google Cloud project** with YouTube Data API v3 enabled

---

## Quick Start

### 1. Install Python and Dependencies

Install python-3.11 (included in release [here](https://github.com/elboaf/OBS-YouTube-Uploader/releases/tag/OBS-YouTube-Uploader))

```bash
pip install -r requirements.txt

# or, if you have multiple python versions already installed:

python3.11 -m pip install -r requirements.txt
```

### 2. Set Up YouTube API Access

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a **new project**
3. Enable **YouTube Data API v3** (APIs & Services → Library)
4. Go to **Credentials → Create Credentials → OAuth client ID**
   - Application type: **Desktop app**
   - Give it a name (e.g., "OBS YouTube Uploader")
   - Click **Create**
5. Download the JSON file and **rename it to `client_secrets.json`**
6. Go to **OAuth consent screen → Audience → Test users**
   - **Add your email address** as a test user
   - *Without this step, Google will block the auth flow with an error*
7. Place `client_secrets.json` in the same folder as `youtube_uploader.py`

### 4. Install the OBS Script

1. Copy `obs_trigger.py` and `youtube_uploader.py` into a folder together (e.g., `C:\obs-scripts\`)
2. In OBS, go to **Tools → Scripts**
3. Click the **+** button and add `obs_trigger.py`
4. In the script properties:
   - **Recording Directory**: your OBS output folder (where FightRecorder saves `Fight *.mkv` files)
   - **Python Executable**:
     - **Windows**: use the full path to `pythonw.exe` (e.g., `C:\Users\You\AppData\Local\Programs\Python\Python311\pythonw.exe`). This prevents a console window from flashing behind the GUI.
     - **Linux/macOS**: `python3`

### 5. First Run

1. Start a recording in OBS, then stop it (or let FightRecorder stop it)
2. The uploader window should pop up automatically
3. Click **Settings → Connect Google Account** and complete the browser OAuth flow
4. Select your videos, optionally check **Stitch**, set a title/description, and click **Upload Selected**

---

## How It Works

### Trigger Flow

```
FightRecorder detects fight end
        ↓
OBS stops recording
        ↓
obs_trigger.py catches RECORDING_STOPPED event
        ↓
Launches youtube_uploader.py <recording_dir>
        ↓
GUI opens with latest videos listed
```

### Stitching

When **Stitch selected videos** is checked:
1. Selected videos are sorted by timestamp (earliest first)
2. FFmpeg `filter_complex` concat merges them into a single file
3. The stitched file is uploaded, then auto-deleted
4. Original recordings are **never** modified or deleted

### Upload Behavior

- **Single video**: uploads with the title you entered
- **Multiple videos (no stitch)**: uploads each separately, appending `(1/3)`, `(2/3)`, etc. to the title
- **Multiple videos (stitch)**: uploads as one combined video

---

## Settings

Click **Settings** in the uploader to configure:

| Setting | Default | Description |
|---------|---------|-------------|
| **Privacy** | `private` | `private`, `unlisted`, or `public` |
| **Category ID** | `20` | `20` = Gaming. See [YouTube category IDs](https://developers.google.com/youtube/v3/docs/videoCategories/list) for others. |

These are saved to `uploader_settings.json` and persist across sessions.

---


## License

This is a personal tool. Use at your own risk. Not affiliated with OBS Studio, CCP Games, or Google/YouTube.
