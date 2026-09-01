"""FightRecorder (the OBS plugin) — locate it, check it, update it.

Wingman watches the folder FightRecorder records into, so a stale or
missing plugin silently breaks the upload half of the app. Everything
here is user-initiated (a Settings button), never a background poll:
the only network call is the GitHub releases lookup, and it runs when
the user asks for it.

Importable on Linux -- winreg is bound lazily through _winreg(), and
the elevation helper degrades to a refusal, because the whole test
suite runs on ubuntu-latest.
"""

import contextlib
import ctypes
import hashlib
import json
import logging
import os
import sys
import urllib.request

logger = logging.getLogger(__name__)

# The one plugin this feature knows about. The DLL ships from a separate
# repository and lands in OBS's standard 64-bit plugin directory.
RELEASES_API = "https://api.github.com/repos/elboaf/obs-fightrecorder/releases/latest"
DLL_NAME = "obs-fightrecorder.dll"

# Why digest, not pinned sha256: the release moves under a stable URL
# family, and a pin here would go stale with every upstream release --
# the same reasoning fetch_webview2.py documents for the bootstrapper.
# The digest we compare against comes FROM the release metadata itself,
# so "up to date" means "identical to what upstream just shipped".


def _winreg():
    """The winreg module, or None off Windows (see autostart._winreg)."""
    if sys.platform != "win32":
        return None
    import winreg

    return winreg


def _registry_install_location():
    """OBS's InstallLocation from the registry, or None.

    The OBS Studio installer writes it under HKLM; read with the 64-bit
    view explicitly, because a 32-bit Python would otherwise see the
    WOW6432Node view where the key does not exist.
    """
    winreg = _winreg()
    if winreg is None:
        return None
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\OBS Studio",
                0,
                winreg.KEY_READ | view,
            ) as key:
                value, _ = winreg.QueryValueEx(key, "InstallLocation")
                location = os.path.normpath(value.strip('" '))
                if location and os.path.isdir(location):
                    return location
        except OSError:
            continue
    return None


def _default_install_location():
    """The OBS installer's default directory, when it exists."""
    for env in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env)
        if base and os.path.isdir(os.path.join(base, "obs-studio")):
            return os.path.join(base, "obs-studio")
    return None


def find_obs_plugin_dir():
    """The directory FightRecorder's DLL belongs in, or None.

    Validated by the obs-plugins directory existing: a registry entry
    pointing at an uninstalled location must not cause us to create
    directories under Program Files on a machine without OBS. The 64bit
    subdirectory is created when only obs-plugins exists -- it is OBS's
    own standard layout, and a fresh enough install may not have it yet.
    """
    location = _registry_install_location() or _default_install_location()
    if location is None:
        return None
    plugins = os.path.join(location, "obs-plugins")
    if not os.path.isdir(plugins):
        return None
    plugin_dir = os.path.join(plugins, "64bit")
    if not os.path.isdir(plugin_dir):
        try:
            os.mkdir(plugin_dir)
        except OSError:
            logger.exception("Could not create %s", plugin_dir)
            return None
    return plugin_dir


def dll_path():
    """Where the DLL is installed, or None when it is not."""
    plugin_dir = find_obs_plugin_dir()
    if plugin_dir is None:
        return None
    path = os.path.join(plugin_dir, DLL_NAME)
    return path if os.path.isfile(path) else None


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def latest_release() -> dict:
    """The newest release's tag, DLL URL and sha256 digest.

    Raises on network failure -- the caller turns that into a status
    line, and "offline" is a routine state for a user-initiated check,
    not an error worth a dialog.
    """
    request = urllib.request.Request(
        RELEASES_API,
        headers={
            "Accept": "application/vnd.github+json",
            # GitHub rejects a bare urllib user agent outright.
            "User-Agent": "FlyGD-Wingman",
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.load(response)
    for asset in payload.get("assets", []):
        if asset.get("name") == DLL_NAME:
            return {
                "tag": payload.get("tag_name", ""),
                "url": asset.get("browser_download_url", ""),
                "digest": (asset.get("digest") or "").removeprefix("sha256:"),
            }
    raise LookupError(f"{DLL_NAME} is not an asset of the latest release")


def download_latest(url: str, digest: str, staged: str) -> str:
    """Fetch the release DLL to *staged*, verified against *digest*.

    Returns "" on success, else a user-facing reason. A missing digest
    fails rather than shipping an unverified binary: unlike the WebView2
    bootstrapper (where a rotating URL makes pinning impossible and a
    signature check exists instead), there is no second gate here, so
    the digest is the whole guarantee and its absence is disqualifying.
    """
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "FlyGD-Wingman"})
        with (
            urllib.request.urlopen(request, timeout=60) as response,
            open(staged, "wb") as f,
        ):
            f.write(response.read())
    except OSError:
        logger.exception("Could not download %s", url)
        return "Could not download the update -- check your internet."
    if not digest or sha256_file(staged) != digest:
        with contextlib.suppress(OSError):
            os.unlink(staged)
        return "The download did not match the release checksum -- not installed."
    return ""


def apply_update(target_dir: str, staged: str) -> str:
    """Move a verified staged DLL into the plugin directory.

    Returns "" on success, else a user-facing reason. A PermissionError
    here is almost always OBS holding the loaded plugin open -- Windows
    locks a loaded DLL -- or the directory not being writable by this
    user; the caller offers the elevated path separately.
    """
    target = os.path.join(target_dir, DLL_NAME)
    try:
        with open(staged, "rb") as src, open(target, "wb") as dst:
            dst.write(src.read())
    except PermissionError:
        return "OBS may be running, or the folder needs admin rights."
    except OSError as exc:
        logger.exception("Could not write %s", target)
        return f"Could not write to {target_dir} ({exc.strerror})."
    return ""


# ShellExecuteExW flags: NOCLOSEPROCESS so the process handle comes back
# and we can wait for the elevated copy to finish; NOASYNC because we
# need that handle synchronously.
_SEE_MASK_NOASYNC = 0x00000100
_SEE_MASK_NOCLOSEPROCESS = 0x00000040
_ERROR_CANCELLED = 1223


class _SHELLEXECUTEINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint32),
        ("fMask", ctypes.c_uint32),
        ("hwnd", ctypes.c_void_p),
        ("lpVerb", ctypes.c_wchar_p),
        ("lpFile", ctypes.c_wchar_p),
        ("lpParameters", ctypes.c_wchar_p),
        ("lpDirectory", ctypes.c_wchar_p),
        ("nShow", ctypes.c_int32),
        ("hInstApp", ctypes.c_void_p),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", ctypes.c_wchar_p),
        ("hkeyClass", ctypes.c_void_p),
        ("dwHotKey", ctypes.c_uint32),
        ("hIconOrMonitor", ctypes.c_void_p),
        ("hProcess", ctypes.c_void_p),
    ]


def elevated_copy(target_dir: str, staged: str) -> str:
    """Copy via one UAC prompt, for OBS directories the user can't write.

    Returns "" on success, else a user-facing reason: declined prompt,
    locked target (OBS running), or the elevated copy failing. Waiting
    for the elevated process is what lets the caller re-verify the
    result rather than trusting the launch.
    """
    if sys.platform != "win32":
        return "This action needs Windows."
    target = os.path.join(target_dir, DLL_NAME)
    parameters = (
        "-NoProfile -ExecutionPolicy Bypass -Command "
        f"Copy-Item -Force -LiteralPath '{staged}' -Destination '{target}'"
    )
    info = _SHELLEXECUTEINFO()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = _SEE_MASK_NOASYNC | _SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = "powershell.exe"
    info.lpParameters = parameters
    info.nShow = 0  # SW_HIDE: the work is a silent file copy
    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):
        logger.exception("Elevation was refused for the FightRecorder copy")
        return "Could not start the elevated copy."
    if info.hProcess:
        ctypes.windll.kernel32.WaitForSingleObject(info.hProcess, 60000)
        ctypes.windll.kernel32.CloseHandle(info.hProcess)
    if not os.path.isfile(target):
        return (
            "The copy did not happen -- the UAC prompt was declined, or "
            "OBS Studio is still running."
        )
    return ""
