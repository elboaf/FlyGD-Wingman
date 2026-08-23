"""Identify and terminate a process by PID, on Windows.

Split out of hotkeys.py for the reason ui/chrome.py is split out of
ui/window.py (window-resize-plan.md:130-140): this is the only module that
touches Win32, so hotkeys.py stays importable and testable on Linux.

Every function is a no-op returning None/False off Windows.
"""
import logging
import subprocess
import sys

logger = logging.getLogger(__name__)

_NO_WINDOW_KWARGS = (
    {"creationflags": subprocess.CREATE_NO_WINDOW}
    if sys.platform == "win32" else {}
)


def describe(pid: int, runner=subprocess.run) -> dict | None:
    """Return {"image", "cmdline"} for *pid*, or None if it is not running.

    Uses a CIM/WMI query via PowerShell rather than adding psutil: the
    dependency list is deliberately short, and this is one call on one
    code path.
    """
    if sys.platform != "win32":
        return None
    script = (
        f"$p = Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}';"
        "if ($p) { $p.ExecutablePath; $p.CommandLine }"
    )
    try:
        done = runner(["powershell", "-NoProfile", "-Command", script],
                      capture_output=True, text=True, timeout=10,
                      **_NO_WINDOW_KWARGS)
    except (OSError, subprocess.SubprocessError):
        logger.exception("Could not query process %s", pid)
        return None
    lines = [ln.strip() for ln in (done.stdout or "").splitlines() if ln.strip()]
    if not lines:
        return None
    return {"image": lines[0], "cmdline": lines[-1]}


def terminate(pid: int, runner=subprocess.run) -> bool:
    if sys.platform != "win32":
        return False
    try:
        runner(["taskkill", "/PID", str(int(pid)), "/F"],
               capture_output=True, text=True, timeout=10,
               **_NO_WINDOW_KWARGS)
        return True
    except (OSError, subprocess.SubprocessError):
        logger.exception("Could not terminate process %s", pid)
        return False
