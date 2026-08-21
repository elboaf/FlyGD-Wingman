"""Window construction and lifecycle.

pywebview is imported lazily inside create() and run(), not at module
scope. Two reasons:

  * __main__ pre-flights the WebView2 runtime before touching pywebview at
    all. Importing it up here would run its import-time setup on a machine
    we have already decided cannot host a webview.
  * it lets tests inject a stub `webview` module, so this file's flags and
    placement are covered on a headless Linux box.

The flags below are not cosmetic. Every one of them was paid for by the
spike; see the comments at each.
"""
import logging
import sys
from pathlib import Path

TITLE = "FlyGD Wingman"

# Two panes plus a status strip. Wide enough that filename, date, size and
# length do not fight for the list's columns at 100% scaling.
WIDTH = 1040
HEIGHT = 680

# --bg from the token table. This paints the NATIVE surface, before the
# first frame of HTML exists; a mismatch here is a white flash on launch.
BACKGROUND = "#0c0d10"

# Pinned, never autodetected: a silent fallback to another backend would
# mean a "passing" run that proves nothing about the shipped product.
GUI_BACKEND = "edgechromium"


def _web_dir() -> Path:
    """Locate the bundled page, mirroring paths.icon_file()'s two cases.

    Frozen builds collect web/ at the bundle root via uploader.spec's
    `datas` entry; a source checkout has no such step and the real files
    live inside the package, next to ui/.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "web"
    return Path(__file__).resolve().parent.parent / "web"


def _screen_size() -> tuple[int, int]:
    """Primary screen size in pixels; a plausible default off-Windows.

    Guarded exactly as __main__.set_dpi_awareness() guards its Win32 call:
    off-Windows this is development only, and a wrong-but-sane number beats
    an import error at startup.
    """
    if sys.platform != "win32":
        return (1920, 1080)
    import ctypes
    try:
        user32 = ctypes.windll.user32
        return (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
    except (AttributeError, OSError):
        return (1920, 1080)


def _placement(width: int, height: int, metrics=_screen_size) -> tuple[int, int]:
    """Centre the window, clamped at the top-left corner.

    Frameless windows get NO sensible default placement from pywebview --
    the spike's opened somewhere not visible on the primary screen -- so
    x/y are mandatory, not a nicety.

    The clamp matters more than centring does: a negative x is legal on
    Windows and would put the custom title bar off the left edge, and a
    frameless window with no reachable drag region cannot be moved back.
    """
    screen_w, screen_h = metrics()
    return (max(0, (screen_w - width) // 2), max(0, (screen_h - height) // 2))


def _silence_pywebview_logging() -> None:
    """Stop pywebview writing its native-object property walk to stderr.

    It logs an unbounded walk of WinForms objects at DEBUG. Invisible in a
    windowed build, but stderr is redirected into the log file in some
    launch paths and this would swamp it.

    propagate is left ON deliberately: real warnings and errors must still
    reach the rotating file handler configure_logging() attached to the
    root logger. Only pywebview's own handlers and its DEBUG chatter go.
    """
    log = logging.getLogger("pywebview")
    log.setLevel(logging.WARNING)
    for handler in list(log.handlers):
        log.removeHandler(handler)
    log.propagate = True


def create(api) -> "webview.Window":
    """Build the main window and hand *api* its back-reference.

    The `api._window = window` assignment MUST use the underscore name and
    MUST stay a separate step:

      * separate, because create_window() needs js_api before a window
        object exists to assign;
      * underscore, because pywebview builds its JS proxy by walking the
        js_api object's PUBLIC attributes. A public attribute holding a
        webview.Window sends that walk into WinForms, where
        Rectangle.Empty returns itself, and it recurses until
        RecursionError kills the process about eight seconds after launch.

    tests/test_window.py asserts that invariant. Do not relax it.
    """
    import webview

    x, y = _placement(WIDTH, HEIGHT)
    window = webview.create_window(
        TITLE,
        str(_web_dir() / "index.html"),
        js_api=api,
        width=WIDTH,
        height=HEIGHT,
        x=x,
        y=y,
        frameless=True,
        # easy_drag would move the window on any mousedown in the body,
        # so every button, row, and text field would drag it. The page
        # marks its own title bar with `pywebview-drag-region`; that is
        # the whole drag surface, by design.
        easy_drag=False,
        background_color=BACKGROUND,
    )
    api._window = window
    return window


def run() -> None:
    """Hand the main thread to pywebview. Returns when the window is destroyed.

    Nothing this returns can be trusted as a success signal: when the
    WebView2 runtime is missing, pywebview logs the failure, start()
    returns normally, and the process exits 0. That is why __main__
    pre-flights the runtime before calling this.
    """
    _silence_pywebview_logging()
    import webview

    webview.start(gui=GUI_BACKEND)
