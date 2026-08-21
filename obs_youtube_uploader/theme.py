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


TOKENS: dict[str, dict[str, str]] = {
    "light": {
        "SUCCESS": "#1a7f37",
        "ERROR": "#c0392b",
        "WARNING": "#b8860b",
        "MUTED": "#6c6c6c",
        "LINK": "#0645ad",
        # Neutral status foreground. Exists because _combat_log_worker sets
        # foreground="black" literally, which is invisible on a dark
        # background - a real bug, not just a suboptimal shade.
        "FG": "#1a1a1a",
        "ROW_ODD": "#ffffff",
        "ROW_EVEN": "#f5f5f5",
        "ROW_PRESELECT": "#fff3b0",
    },
    "dark": {
        "SUCCESS": "#3fb950",
        "ERROR": "#f85149",
        "WARNING": "#d29922",
        "MUTED": "#9198a1",
        "LINK": "#58a6ff",
        "FG": "#e6edf3",
        "ROW_ODD": "#1e1e1e",
        "ROW_EVEN": "#252526",
        "ROW_PRESELECT": "#3a3a1e",
    },
}

# Module-level "current" mode, mutated only by apply(). Seeded from a real
# detection at import time so token()/current_mode() are sensible even
# before __main__.py calls apply() once at startup.
_current_mode: Mode = detect_mode()


def current_mode() -> Mode:
    return _current_mode


def token(name: str, mode: Mode | None = None) -> str:
    """Raises KeyError for an unknown token name - a typo here should fail
    loudly in a test, not silently render as a missing colour."""
    return TOKENS[mode if mode is not None else current_mode()][name]


def register(consumer: Callable[[Mode], None]) -> None:
    """consumer is called with the active Mode on every apply(), both at
    startup and on a live OS theme switch. Windows register themselves here
    instead of re-theming ad hoc - see the module docstring."""
    _consumers.append(consumer)


def unregister(consumer: Callable[[Mode], None]) -> None:
    """Remove a consumer. Idempotent: removing one that was never
    registered is a no-op, not an error.

    SettingsWindow is rebuilt on every _open_settings() call, so without
    this each open would leave another consumer holding a destroyed
    Toplevel behind. apply() would then raise TclError once per stale
    window on every theme switch - caught and logged, but a real leak.
    """
    try:
        _consumers.remove(consumer)
    except ValueError:
        pass


def apply(root, mode: Mode) -> None:
    """The single owner of re-theming. Must never raise: a failure here is
    an optional presentation capability, not a startup requirement (unlike
    paths.ensure_dirs() or settings.save() in main()), so it is wrapped the
    same way resolve_binary/probe_duration/icon.notify are - degrade, don't
    crash the app or kill a live switch."""
    global _current_mode
    _current_mode = mode

    if sv_ttk is not None:
        try:
            sv_ttk.set_theme(mode, root=root)
        except Exception:
            log.warning("sv_ttk.set_theme(%r) failed", mode, exc_info=True)

    for consumer in _consumers:
        try:
            consumer(mode)
        except Exception:
            log.warning(
                "theme consumer %r raised while applying mode %r",
                consumer, mode, exc_info=True,
            )
