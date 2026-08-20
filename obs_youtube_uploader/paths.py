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


def ensure_dirs() -> None:
    for d in (state_dir(), log_dir(), tmp_dir()):
        d.mkdir(parents=True, exist_ok=True)
