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


# Declared here (ahead of register()/apply()) because tests/test_theme.py's
# autouse _clear_consumers fixture reads and mutates this list, so it has to
# exist at import time regardless of where the functions using it sit.
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


# DWMWA_USE_IMMERSIVE_DARK_MODE. The attribute was renumbered in Windows 10
# 20H1: 20 on 20H1 and later, 19 on 1809-1909. Both are tried because the
# older value is silently REJECTED on new builds and vice versa - there is no
# version query cheaper or more reliable than asking DWM itself.
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_USE_IMMERSIVE_DARK_MODE_PRE_20H1 = 19


def _dwm_set_window_attribute(hwnd: int, attr: int, value: int) -> int:
    """Returns the raw HRESULT rather than a bool: apply_titlebar keys its
    fallback off a FAILING result, and DwmSetWindowAttribute reports an
    unrecognised attribute by returning E_INVALIDARG, not by raising."""
    import ctypes

    val = ctypes.c_int(value)
    return int(ctypes.windll.dwmapi.DwmSetWindowAttribute(
        ctypes.c_void_p(hwnd), ctypes.c_uint(attr),
        ctypes.byref(val), ctypes.sizeof(val)))


def apply_titlebar(window, mode: Mode, setter=None) -> None:
    """Paint *window*'s OS title bar to match *mode*.

    sv-ttk restyles the client area only, so a dark window kept a light title
    bar - visibly wrong beside the themed content, and worst on the Settings
    dialog sitting over the dark main window.

    `setter` is injectable for the same reason detect_mode takes `reader=`:
    the real call is Windows-only, and the suite runs on Linux. When it is
    omitted the platform guard fires FIRST, before `window` is touched at all
    - wm_frame() off Windows returns an X11 id that means nothing to DWM.

    Never raises, for the same reason apply() never does: this is an optional
    presentation capability, and it is called from window constructors and
    from theme consumers, neither of which can absorb a failure.
    """
    if setter is None:
        if sys.platform != "win32":
            return
        setter = _dwm_set_window_attribute

    try:
        # wm_frame() returns the id of the window's OS-level frame, and only
        # once the toplevel has actually been realised - before that there is
        # no HWND to hand DWM. Callers must map the window first.
        hwnd = int(window.wm_frame(), 16)
        enabled = 1 if mode == "dark" else 0
        if setter(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, enabled) != 0:
            setter(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE_PRE_20H1, enabled)
    except Exception:
        log.warning("applying the %r title bar failed", mode, exc_info=True)


# Every named font sv-ttk's sv.tcl declares. Absent names are skipped, so
# this stays correct across sv-ttk versions that add or drop one.
_SV_FONT_NAMES = (
    "SunValleyCaptionFont",
    "SunValleyBodyFont",
    "SunValleyBodyStrongFont",
    "SunValleyBodyLargeFont",
    "SunValleySubtitleFont",
    "SunValleyTitleFont",
    "SunValleyTitleLargeFont",
    "SunValleyDisplayFont",
)

# sv-ttk's declared (unscaled) size per font name, captured the first time
# that font is seen and never re-read, and stored SIGNED. _rescale_sv_fonts
# always derives the new size from this base rather than from the font's
# current size, so calling apply() repeatedly - which happens on every live
# theme switch - cannot compound the scaling.
_sv_font_base_sizes: dict[str, int] = {}


def _rescale_sv_fonts(root) -> None:
    """Make sv-ttk's ttk fonts follow `tk scaling` like everything else.

    sv.tcl declares its fonts with a NEGATIVE -size (e.g. -14), which in Tk
    means "absolute pixels" - a size `tk scaling` never touches. So once the
    process is DPI-aware, every scaled dimension in the app grows while ttk
    text stays pinned at its 96-DPI pixel height: at 200% the text renders
    at roughly half its intended apparent size. (app._apply_row_height()
    works around the same root cause for Treeview row height alone.)

    The scale factor is computed here rather than imported because app.py
    imports theme.py, so theme.py must not import app. It is deliberately
    the same expression as app.dpi_scale(), ROUNDING INCLUDED - the two are
    halves of one contract and have to change together. See that function
    for why the round() is needed: Tcl's 5-significant-figure formatting
    makes the round-trip lossy, so 96 DPI comes back as 0.99982.

    The DECLARED SIGN is preserved rather than forced negative. Every font
    in sv-ttk 2.6.1 is declared in pixels, but _SV_FONT_NAMES is otherwise
    written to tolerate version drift, and a future release declaring a
    font in points would have it silently reinterpreted as pixels - roughly
    a 25% shrink at 96 DPI. Scaling a positive (points) size is still
    correct: `tk scaling` would apply on top, but so would the DPI factor
    we compute from it, and the sign is what says which unit was meant.
    """
    scale = round(float(root.tk.call("tk", "scaling")) / (96.0 / 72.0), 2)
    # splitlist, not iteration: `font names` returns a Tcl list, and if Tk
    # ever handed it back as a plain string this would iterate CHARACTERS,
    # match nothing, and silently no-op with no exception to log.
    existing = {str(name) for name in root.tk.splitlist(
        root.tk.call("font", "names"))}
    for name in _SV_FONT_NAMES:
        if name not in existing:
            continue
        base = _sv_font_base_sizes.get(name)
        if base is None:
            base = int(root.tk.call("font", "configure", name, "-size"))
            _sv_font_base_sizes[name] = base
        scaled = max(1, round(abs(base) * scale))
        root.tk.call("font", "configure", name, "-size",
                     -scaled if base < 0 else scaled)


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
        else:
            # Inline here rather than a registered consumer: set_theme
            # re-asserts sv-ttk's styles, and the consumers below (notably
            # app's _apply_row_height, which measures font metrics) must
            # observe the already-corrected fonts. Wrapped for the same
            # reason set_theme is - apply() must never raise.
            try:
                _rescale_sv_fonts(root)
            except Exception:
                log.warning("rescaling sv-ttk fonts to the DPI scale failed",
                            exc_info=True)

    for consumer in _consumers:
        try:
            consumer(mode)
        except Exception:
            log.warning(
                "theme consumer %r raised while applying mode %r",
                consumer, mode, exc_info=True,
            )
