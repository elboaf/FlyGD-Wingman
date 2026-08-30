"""Filesystem locations for application state and bundled resources.

State never lives next to the executable: the installer targets Program
Files, which is read-only for non-admin users.
"""

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "FlyGD Wingman"

# Where 3.x kept everything. Read only by migrate_state_dir() and by the
# fallback below; nothing else may reach for it.
LEGACY_APP_NAME = "OBSYouTubeUploader"

# Set only by migrate_state_dir(), and only when the rename was refused.
# A flag rather than a cached path on purpose: tests/conftest.py redirects
# LOCALAPPDATA per test and every path derives from that live read, so
# caching the resolved directory here would break the suite wholesale.
_use_legacy = False


def state_dir() -> Path:
    """Per-user writable directory for settings, token, logs, and temp files."""
    name = LEGACY_APP_NAME if _use_legacy else APP_NAME
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / name
    # Non-Windows fallback so tests and development work off-platform.
    return Path.home() / ".local" / "share" / name


def _legacy_state_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / LEGACY_APP_NAME
    return Path.home() / ".local" / "share" / LEGACY_APP_NAME


def migrate_state_dir() -> str:
    """Move 3.x state to the 4.0 directory. Returns a status for logging.

    MUST be called before ensure_dirs(). ensure_dirs() creates state_dir()
    unconditionally, so running after it means this function finds a
    freshly created empty target, takes the "already migrated" branch, and
    strands the user's real settings and YouTube token forever.

    Both directories live under %LOCALAPPDATA%, so the rename is
    same-volume and atomic: there is no partial-migration state to recover
    from. A refusal leaves everything where it was and is retried next
    launch.

    Returns rather than logs because logging is not configured this early.
    """
    global _use_legacy
    legacy = _legacy_state_dir()
    current = state_dir()
    if current.exists():
        return "state directory already current"
    if not legacy.exists():
        return "no legacy state directory to migrate"
    try:
        legacy.rename(current)
    except OSError as exc:
        _use_legacy = True
        return f"state migration deferred, still using {LEGACY_APP_NAME}: {exc}"
    return f"state migrated from {LEGACY_APP_NAME} to {APP_NAME}"


def settings_file() -> Path:
    return state_dir() / "settings.json"


def token_file() -> Path:
    return state_dir() / "token.json"


def seen_file() -> Path:
    return state_dir() / "seen.json"


def durations_file() -> Path:
    """Cache of ffprobe durations. Deleting it costs a one-off re-probe."""
    return state_dir() / "durations.json"


def links_file() -> Path:
    """Which recordings have already been uploaded, and to what URL.

    Beside durations.json and keyed the same way, but NOT the same kind of
    file: deleting this one costs something that cannot be recomputed. The
    Link column is the only record the app keeps of an upload, so a lost
    store means the user has to search YouTube to answer "did I already
    upload this fight?".
    """
    return state_dir() / "links.json"


def eve_settings_backup_dir() -> Path:
    """Where EVE settings backups live.

    Beside settings.json and the token, never inside the EVE tree: that
    directory belongs to CCP, and writing archives into it risks confusing
    the launcher and losing every backup to a reinstall.
    """
    return state_dir() / "eve-settings-backups"


def eve_skills_file() -> Path:
    """Roster, snapshots, skill queue, ETags, and DPAPI-wrapped tokens.

    One document holds all of it, which is what makes forgetting a
    character a single atomic write. TriffView splits tokens into
    Windows Credential Manager and cannot update the two together; its
    own error strings record the cost ("Forget was rolled back because
    state could not be saved"). A .bak sibling is kept beside this file
    by the controller, because merging the tokens in moved the one
    non-rebuildable thing into a file that had no backup tier.
    """
    return state_dir() / "eve_skills.json"


def eve_skills_cache_file() -> Path:
    """Skill name -> type id. Deleting it costs a re-resolve over ESI."""
    return state_dir() / "eve_skills_cache.json"


def skill_plans_dir() -> Path:
    """User-owned folder of plan .txt files, plus a seeded starter.

    A directory rather than a section of a state document on purpose:
    the user edits these in Notepad, and `Open plans folder` is the
    whole authoring workflow.
    """
    return state_dir() / "skill_plans"


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


def resolve_binary(name: str) -> str | None:
    """Find a bundled binary, falling back to PATH.

    In a frozen build, `bundle_dir()` is `sys._MEIPASS` and the bundled
    binary lives at its `bin/` subfolder — that path is verified correct
    and left untouched. In a source checkout, `bundle_dir()` is the repo
    root, but `packaging/fetch_ffmpeg.py` writes into `packaging/bin`, not
    `<repo>/bin`. Without this extra lookup, running from source never
    finds the fetched ffmpeg and silently falls back to PATH.
    """
    exe = f"{name}.exe"
    candidate = bundle_dir() / "bin" / exe
    if candidate.exists():
        return str(candidate)
    candidate = bundle_dir() / exe
    if candidate.exists():
        return str(candidate)
    if not hasattr(sys, "_MEIPASS"):
        candidate = bundle_dir() / "packaging" / "bin" / exe
        if candidate.exists():
            return str(candidate)
    return shutil.which(name)


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


def engine_ini_file() -> Path:
    """Config the engine reads. Generated by Wingman, never hand-edited.

    The name matches the standalone script's IniFile (111unified.ahk:71),
    which is relative -- so spawning the engine with cwd=state_dir() is what
    makes it resolve here with no edit to the script.
    """
    return state_dir() / "eve_bookmark_helper.ini"


def engine_status_file() -> Path:
    """Runtime state the engine publishes. Wingman never writes this."""
    return state_dir() / "eve_status.json"


def engine_pid_file() -> Path:
    """PID plus run token of the last spawned engine, for orphan recovery."""
    return state_dir() / "eve_engine.pid"


def _package_dir() -> Path:
    return Path(__file__).resolve().parent


def engine_script() -> Path | None:
    """Locate the vendored .ahk, or None if it is not present.

    Mirrors icon_file()'s two-case handling of bundle_dir(): a frozen build
    collects the script via uploader.spec's datas entry, a source checkout
    has it inside the package.
    """
    frozen = bundle_dir() / "engine" / "eve_bookmarks.ahk"
    if frozen.exists():
        return frozen
    source = _package_dir() / "engine" / "eve_bookmarks.ahk"
    if source.exists():
        return source
    return None


def engine_exe() -> str | None:
    """Locate the bundled AutoHotkey interpreter. Bundled only.

    Deliberately NOT resolve_binary(): its shutil.which() fallback is
    correct for ffmpeg and dangerous here. AutoHotkey v2 is a different,
    incompatible language, and a v2 interpreter on PATH handed our v1
    script fails with parse errors that read like a bug in the script.
    Better to report a missing engine and have the user reinstall.
    """
    name = "AutoHotkeyU64.exe"
    candidate = bundle_dir() / "bin" / name
    if candidate.exists():
        return str(candidate)
    if not hasattr(sys, "_MEIPASS"):
        candidate = bundle_dir() / "packaging" / "bin" / name
        if candidate.exists():
            return str(candidate)
    return None


CODEC_NAME = "wingman-settings-codec"


def codec_exe() -> str | None:
    """Path to the bundled EVE settings codec, or None when it is not bundled.

    Same shape as engine_exe(), and for the same reason NOT resolve_binary():
    its shutil.which() fallback would let an unrelated program of the same
    name on PATH rewrite a user's settings file. Absent here means the
    formation editor hides itself; nothing else in Profiles depends on it.
    """
    exe = CODEC_NAME + (".exe" if sys.platform == "win32" else "")
    frozen = bundle_dir() / "bin" / exe
    if frozen.is_file():
        return str(frozen)
    if not hasattr(sys, "_MEIPASS"):
        dev = bundle_dir() / "packaging" / "bin" / exe
        if dev.is_file():
            return str(dev)
    return None


def ensure_dirs() -> None:
    for d in (state_dir(), log_dir(), tmp_dir()):
        d.mkdir(parents=True, exist_ok=True)
