"""Theme tokens, OS dark/light detection, and the single apply() entry point.

sv-ttk restyles ttk widgets only. Everything else in this app - directly
assigned widget colours, Treeview row tags, the classic tk.Text box, and the
generated checkbox images - must be re-themed explicitly, and a live OS theme
switch means re-doing it to widgets that already exist. apply() is therefore
the one place that owns re-theming: it sets the sv-ttk theme and then walks
every registered consumer. Nothing else re-themes itself ad hoc, or a live
switch produces a half-themed window.
"""
import logging
import sys
from typing import Callable

log = logging.getLogger(__name__)

Mode = str  # "light" | "dark"

try:
    import sv_ttk
except ImportError:  # pragma: no cover - exercised via monkeypatch, not absence
    sv_ttk = None


def read_apps_use_light_theme() -> int | None:
    """Read HKCU...Personalize\\AppsUseLightTheme. None on any failure or
    off-Windows - this is an optional presentation capability, not a
    startup requirement, so it degrades rather than raises."""
    if sys.platform != "win32":
        return None
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        try:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        finally:
            winreg.CloseKey(key)
        return int(value)
    except Exception:
        return None


def detect_mode(reader=read_apps_use_light_theme) -> Mode:
    """reader is injectable so this is testable off-Windows, mirroring
    library.py's runner= convention for subprocess.run."""
    if reader() == 0:
        return "dark"
    return "light"


# Declared here (ahead of register()/apply() in Step 6) because
# tests/test_theme.py's autouse _clear_consumers fixture reads/mutates this
# from Step 1 onward - controller ruling, see task-2-report.md.
_consumers: list[Callable[[Mode], None]] = []
