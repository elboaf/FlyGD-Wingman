"""Start Wingman when the user signs in to Windows.

M3, argued from PRODUCT.md rather than from convenience. The product calls
itself "A tray app that starts hidden" and names bookmark keybinds as "the
only feature that runs continuously in the background". Keybinds fire only
while Wingman is running, so start-on-login serves a co-primary feature --
which makes its absence an omission rather than an addition. Nothing in
"What it must not become" is touched: no telemetry, no account, no gameplay
automation, no EVE window handling.

**The registry is the state.** There is deliberately no `start_on_login`
key in settings.json. A stored copy would be a second answer to a question
the registry already answers, and the two drift the moment a user deletes
the entry from Task Manager's Startup tab -- which is the supported way to
turn this off and the one the walkthrough asked for an answer to. Reading
HKCU live cannot disagree with what Windows will actually do at boot.
DESIGN.md's "State that must not be retyped", applied to state that lives
outside the app entirely.

**HKCU, never HKLM.** A per-user key needs no elevation and cannot affect
anyone else who signs in to the same machine. Nothing here writes outside
the current user's own hive.

The registered command carries `--hidden`, because a login that raises a
window every boot is worse than no setting at all.

Importable on Linux: `winreg` is bound lazily through `_winreg()`, which is
also the seam the tests inject a fake through. Every entry point degrades
rather than raising ImportError, so a non-Windows import of this module --
which the whole test suite does -- costs nothing.
"""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)

# HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

# What the user sees in Task Manager's Startup tab, so it is the product
# name and not the package name. Changing it orphans every existing entry:
# the old value keeps launching the app and nothing here can find it to
# report or remove it, so the checkbox would read "off" on an install that
# still starts at login. If it ever has to change, the new build has to
# delete the old name before writing the new one.
VALUE_NAME = "FlyGD Wingman"


def _winreg():
    """The winreg module, or None off Windows.

    A function rather than a module-level import so this file imports on
    Linux, where the entire test suite runs.
    """
    if sys.platform != "win32":
        return None
    import winreg

    return winreg


def command() -> str:
    """The command line Windows should run at login.

    Two shapes, because a frozen build and a source checkout do not launch
    the same way:

      * frozen -- sys.frozen is set and sys.executable IS Wingman, so the
        exe runs itself;
      * source -- sys.executable is python.exe, which knows nothing about
        this package, so the command has to name the module.

    Quoted unconditionally. "C:\\Program Files\\..." is the normal install
    location and an unquoted path containing a space is read by the shell
    as a command plus arguments -- it would launch "C:\\Program" at every
    login, forever, with no error anyone would see.
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --hidden'
    module = __name__.split(".")[0]
    return f'"{sys.executable}" -m {module} --hidden'


def is_enabled() -> bool:
    """Whether a login entry exists for Wingman right now.

    Reports the presence of the VALUE, not whether its command matches the
    one `command()` would write today. That is deliberate and it is the
    conservative reading: the value that exists is what Windows will run,
    so reporting it as "on" is true even when the path is stale from a
    reinstall to a different folder. Comparing commands would flip the
    checkbox to "off" after such a move, telling a user their app does not
    start at login while it demonstrably still does.

    Re-enabling rewrites the command, so the repair is one toggle away.

    Never raises. A read that cannot answer is answered "off": this feeds
    a checkbox rendered at load, and a settings screen that fails to open
    because a registry read threw would be a worse failure than a checkbox
    that starts unticked.
    """
    winreg = _winreg()
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        # The Run key itself, or our value under it. Both mean "off", and
        # neither is an error worth logging on every settings render.
        return False
    except OSError:
        # Policy or permissions. Logged because unlike the above it is a
        # genuine surprise, and a user reporting "the checkbox will not
        # stay ticked" needs this in the log to be diagnosable.
        logger.exception("Could not read the login entry")
        return False
    return bool(str(value).strip())


def enable() -> None:
    """Register the login entry, overwriting any existing one.

    Overwrites rather than checking first, which is what makes re-ticking
    the box the repair for a stale path after a reinstall.

    Raises OSError when the write is refused -- by policy, by a locked
    hive, or because this is not Windows. The caller turns that into a
    message; it must not be swallowed here, because a checkbox that
    silently fails to take is exactly the outcome DESIGN.md's commit
    contract exists to prevent.
    """
    winreg = _winreg()
    if winreg is None:
        raise OSError("Start on login is only available on Windows.")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())


def disable() -> None:
    """Remove the login entry. Already-absent is success, not an error.

    Idempotent on purpose: the user can delete this from Task Manager's
    Startup tab, and unticking a box that is already off must not report a
    failure for having nothing to do.
    """
    winreg = _winreg()
    if winreg is None:
        raise OSError("Start on login is only available on Windows.")
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except FileNotFoundError:
        return


def installed_command() -> str:
    """The registered command, or "" -- for diagnostics and tests only.

    Not shown in the UI. Returns the raw stored string rather than a parsed
    path, because that is what Windows stores and what a bug report needs to
    quote verbatim.
    """
    winreg = _winreg()
    if winreg is None:
        return ""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, VALUE_NAME)
    except OSError:
        return ""
    return str(value)


__all__ = [
    "VALUE_NAME",
    "command",
    "disable",
    "enable",
    "installed_command",
    "is_enabled",
]
