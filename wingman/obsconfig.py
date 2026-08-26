"""Read OBS's own configuration to pre-fill the recording directory.

This is what removes the last manual configuration step: rather than asking
the user where OBS records, read it from OBS.
"""

import configparser
import os
from pathlib import Path

# (section, key) holding the recording path for each output mode.
_SIMPLE_PATH_KEY = ("SimpleOutput", "FilePath")
_ADVANCED_PATH_KEY = ("AdvOut", "RecFilePath")


def _resolve_appdata(appdata: Path | None) -> Path | None:
    if appdata is None:
        raw = os.environ.get("APPDATA")
        if not raw:
            return None
        return Path(raw)
    return Path(appdata)


def profiles_root(appdata: Path | None = None) -> Path | None:
    resolved = _resolve_appdata(appdata)
    if resolved is None:
        return None
    root = resolved / "obs-studio" / "basic" / "profiles"
    return root if root.is_dir() else None


def _read_path(ini: Path) -> Path | None:
    """Recording path from one profile's basic.ini, honoring output mode.

    A profile's basic.ini almost always has both a [SimpleOutput] FilePath
    and an [AdvOut] RecFilePath -- the inactive one is typically just OBS's
    untouched default (e.g. "C:/Videos"), not the folder the user actually
    records to. Picking a fixed section order silently returns that stale
    default for every user in the other mode. [Output] Mode states which
    section OBS is actually using, so read that first and prefer its
    section; only fall back to the other section if the chosen one turns
    out to have no usable value.
    """
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    try:
        parser.read(ini, encoding="utf-8-sig")
    except (configparser.Error, OSError, UnicodeDecodeError):
        return None

    mode = "simple"
    # Any other value (including "simple" or something unrecognised)
    # keeps the default -- Simple is also OBS's own default mode.
    if (
        parser.has_option("Output", "Mode")
        and parser.get("Output", "Mode").strip().lower() == "advanced"
    ):
        mode = "advanced"

    primary, secondary = (
        (_ADVANCED_PATH_KEY, _SIMPLE_PATH_KEY)
        if mode == "advanced"
        else (_SIMPLE_PATH_KEY, _ADVANCED_PATH_KEY)
    )
    for section, key in (primary, secondary):
        if parser.has_option(section, key):
            value = parser.get(section, key).strip()
            if value:
                return Path(value)
    return None


def _active_profile_dir_name(appdata: Path | None) -> str | None:
    """Read the active profile's directory name from OBS's global.ini.

    global.ini's [Basic] section records ``ProfileDir=<directory name>``,
    naming the profile actually in use. This is authoritative -- unlike a
    most-recently-modified heuristic, it can't be fooled by OBS touching a
    profile that isn't the active one, or by a user with several profiles.
    Returns None (never raises) when global.ini is absent, malformed, or
    doesn't specify a profile directory, so the caller can fall back.
    """
    resolved = _resolve_appdata(appdata)
    if resolved is None:
        return None
    global_ini = resolved / "obs-studio" / "global.ini"
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    try:
        read_files = parser.read(global_ini, encoding="utf-8-sig")
    except (configparser.Error, OSError, UnicodeDecodeError):
        return None
    if not read_files:
        # global.ini doesn't exist (or couldn't be opened) -- fall back.
        return None
    if parser.has_option("Basic", "ProfileDir"):
        value = parser.get("Basic", "ProfileDir").strip()
        return value or None
    return None


def find_recording_dir(appdata: Path | None = None) -> Path | None:
    """Recording directory for the OBS profile currently in use.

    Prefers the profile named as active in global.ini's
    ``[Basic] ProfileDir``. Falls back to the most recently modified
    profile's basic.ini when global.ini is absent/malformed, when it names a
    profile directory that doesn't exist, or when that profile has no usable
    path.

    Returns None when OBS is absent, has no profiles, or no profile
    specifies a path -- the caller falls back to asking the user.
    """
    root = profiles_root(appdata)
    if root is None:
        return None

    active_dir_name = _active_profile_dir_name(appdata)
    if active_dir_name is not None:
        active_ini = root / active_dir_name / "basic.ini"
        try:
            active_is_file = active_ini.is_file()
        except OSError:
            # Unreadable active profile must fall through to the scan below,
            # not abort detection and send the user to the folder picker.
            active_is_file = False
        if active_is_file:
            found = _read_path(active_ini)
            if found is not None:
                return found

    # Fall back to the most recently modified profile. Walk the profile
    # directories ourselves rather than using glob("*/basic.ini"): glob
    # stats internally, and an entry that raises there escapes the loop and
    # takes the whole detection with it. Doing it by hand keeps one bad
    # profile from hiding every other one.
    inis_with_times = []
    try:
        profile_dirs = list(root.iterdir())
    except OSError:
        profile_dirs = []
    for prof in profile_dirs:
        ini = prof / "basic.ini"
        try:
            if not ini.is_file():
                continue
            mtime = ini.stat().st_mtime
        except OSError:
            # Vanished or unreadable between listing and stat -- skip it.
            continue
        inis_with_times.append((mtime, ini))

    # Sort by mtime (newest first)
    inis_with_times.sort(key=lambda x: x[0], reverse=True)

    for mtime, ini in inis_with_times:
        found = _read_path(ini)
        if found is not None:
            return found
    return None
