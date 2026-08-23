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
                      errors="replace", **_NO_WINDOW_KWARGS)
    except Exception:
        # Deliberately broad: this feeds a code path that must never
        # prevent the engine starting. UnicodeDecodeError in particular is
        # a ValueError, not an OSError, and a single foreign-locale process
        # on the machine would otherwise crash startup.
        logger.exception("Could not query process %s", pid)
        return None
    lines = [ln.strip() for ln in (done.stdout or "").splitlines() if ln.strip()]
    if len(lines) != 2:
        # PowerShell emits no line for a null property, so a short result
        # means one of the two identity signals is missing -- and taking
        # lines[0]/lines[-1] anyway would compare the same string twice.
        return None
    return {"image": lines[0], "cmdline": lines[1]}


def terminate(pid: int, runner=subprocess.run) -> bool:
    if sys.platform != "win32":
        return False
    try:
        done = runner(["taskkill", "/PID", str(int(pid)), "/F"],
                      capture_output=True, text=True, timeout=10,
                      errors="replace", **_NO_WINDOW_KWARGS)
    except Exception:
        logger.exception("Could not terminate process %s", pid)
        return False
    if done.returncode != 0:
        # taskkill exits non-zero for "process not found" and "access
        # denied" alike, and not raising on either. Reporting success here
        # regardless is what let recover_orphan discard a live orphan's PID
        # record after a kill that never happened.
        logger.error("taskkill of pid %s failed (rc=%s): %s",
                     pid, done.returncode, (done.stderr or "").strip())
        return False
    return True
