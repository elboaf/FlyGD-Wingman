"""Filesystem locations for application state and bundled resources.

State never lives next to the executable: the installer targets Program
Files, which is read-only for non-admin users.
"""
import os
import sys
from pathlib import Path

APP_NAME = "OBSYouTubeUploader"


def state_dir() -> Path:
    """Per-user writable directory for settings, token, logs, and temp files."""
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / APP_NAME
    # Non-Windows fallback so tests and development work off-platform.
    return Path.home() / ".local" / "share" / APP_NAME


def settings_file() -> Path:
    return state_dir() / "settings.json"


def token_file() -> Path:
    return state_dir() / "token.json"


def seen_file() -> Path:
    return state_dir() / "seen.json"


def durations_file() -> Path:
    """Cache of ffprobe durations. Deleting it costs a one-off re-probe."""
    return state_dir() / "durations.json"


def log_dir() -> Path:
    return state_dir() / "logs"


def tmp_dir() -> Path:
    return state_dir() / "tmp"


def bundle_dir() -> Path:
    """Directory holding bundled binaries.

    PyInstaller unpacks to sys._MEIPASS; in a source checkout it is the
    repository root.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent.parent


def icon_file() -> Path | None:
    """Locate the bundled app icon, or None if it isn't present.

    Mirrors app.resolve_binary()'s two-case handling of bundle_dir():
    frozen builds collect the icon at the bundle root via uploader.spec's
    `datas` entry, so `bundle_dir() / "app.ico"` is correct there. A source
    checkout has no such collection step, so bundle_dir() (the repo root)
    is wrong; the real file lives under the package's own assets/ folder.
    Returning None rather than raising lets callers treat a missing icon as
    optional, the same policy resolve_binary() and configure_logging() use.
    """
    frozen_candidate = bundle_dir() / "app.ico"
    if frozen_candidate.exists():
        return frozen_candidate
    source_candidate = Path(__file__).resolve().parent / "assets" / "app.ico"
    if source_candidate.exists():
        return source_candidate
    return None


def ensure_dirs() -> None:
    for d in (state_dir(), log_dir(), tmp_dir()):
        d.mkdir(parents=True, exist_ok=True)
