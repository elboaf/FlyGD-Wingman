"""Read OBS's own configuration to pre-fill the recording directory.

This is what removes the last manual configuration step: rather than asking
the user where OBS records, read it from OBS.
"""
import configparser
import os
from pathlib import Path

# Section/key pairs in priority order. Simple output mode is the default in
# OBS and is what most users have.
_PATH_KEYS = [
    ("SimpleOutput", "FilePath"),
    ("AdvOut", "RecFilePath"),
]


def profiles_root(appdata: Path | None = None) -> Path | None:
    if appdata is None:
        raw = os.environ.get("APPDATA")
        if not raw:
            return None
        appdata = Path(raw)
    root = Path(appdata) / "obs-studio" / "basic" / "profiles"
    return root if root.is_dir() else None


def _read_path(ini: Path) -> Path | None:
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    try:
        parser.read(ini, encoding="utf-8-sig")
    except (configparser.Error, OSError, UnicodeDecodeError):
        return None
    for section, key in _PATH_KEYS:
        if parser.has_option(section, key):
            value = parser.get(section, key).strip()
            if value:
                return Path(value)
    return None


def find_recording_dir(appdata: Path | None = None) -> Path | None:
    """Recording directory from the most recently modified OBS profile.

    Returns None when OBS is absent, has no profiles, or no profile
    specifies a path — the caller falls back to asking the user.
    """
    root = profiles_root(appdata)
    if root is None:
        return None

    # Get ini files with mtimes, skipping any that vanish during stat.
    # This is defensive against files disappearing between glob and stat.
    inis_with_times = []
    for p in root.glob("*/basic.ini"):
        if p.is_file():
            try:
                mtime = p.stat().st_mtime
                inis_with_times.append((mtime, p))
            except OSError:
                # File vanished between glob and stat
                continue

    # Sort by mtime (newest first)
    inis_with_times.sort(key=lambda x: x[0], reverse=True)

    for mtime, ini in inis_with_times:
        found = _read_path(ini)
        if found is not None:
            return found
    return None
