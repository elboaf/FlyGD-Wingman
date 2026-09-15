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
from typing import TYPE_CHECKING

# Safe to import at module scope, unlike webview: chrome.py builds its
# Win32 types lazily so it imports cleanly off Windows (see its docstring).
from wingman.ui import chrome

if TYPE_CHECKING:  # pragma: no cover - the import is real only to type checkers
    import webview

TITLE = "FlyGD Wingman"

# Two panes plus a status strip. Wide enough that filename, date, size and
# length do not fight for the list's columns at 100% scaling.
WIDTH = 1040
HEIGHT = 680

# The floor the layout can still render at, MEASURED rather than derived --
# neither number could be computed on paper. The width depends on `52ch` in
# the list grid (style.css:233) resolved against the bundled Inter face, and
# the height is a judgement about how much of the two-pane layout has to
# stay visible, not an arithmetic result.
#
# Read off the real page at 840x625, approached from both
# directions. Both provisional estimates were wrong in OPPOSITE directions:
# 880 was 41px too generous, and 560 was 65px too SMALL -- that one would
# have let a user drag the window into a state where part of the layout is
# not viewable, which nothing in the test suite could have caught.
#
# These are LOGICAL pixels, and the CSS viewport floor is ~840x625 at EVERY
# scaling. An earlier revision of this comment claimed the opposite -- that
# WinForms MinimumSize is device pixels under this app's system-DPI
# awareness, so the viewport would be 840/scale, 672px at 125% and 560px at
# 150% -- and instructed the reader not to "correct" it to logical. That was
# wrong, and measurement settles it: at 200% scaling the window at its floor
# captures 839x621 CSS px, which is these two numbers unscaled rather than
# halved. Nothing in web/style.css should be sized against a 560px or 672px
# viewport, because neither can occur; the media queries written against
# them cannot fire.
#
# Width rounded up by 1 to an even number; the height is used as measured,
# since it is the constraint that actually bites.
MIN_WIDTH = 840
MIN_HEIGHT = 625

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


def _system_scale() -> float:
    """System DPI as a scale factor, without needing a window.

    Deliberately the SYSTEM DPI, not the DPI of any particular monitor:
    the process is PROCESS_SYSTEM_DPI_AWARE, and this is the same number
    pywebview's own _scale uses to convert the geometry it is handed.
    `chrome._scale_for` makes the same choice for the same reason, but it
    needs an hwnd -- and placement is computed before a window exists.
    """
    if sys.platform != "win32":
        return 1.0
    import ctypes

    try:
        user32 = ctypes.windll.user32
        get_dpi = getattr(user32, "GetDpiForSystem", None)
        if get_dpi is None:
            return 1.0  # Predates Windows 10 1607.
        dpi = get_dpi()
        return (dpi / 96.0) if dpi else 1.0
    except (AttributeError, OSError):
        return 1.0


def _placement(
    width: int, height: int, metrics=_screen_size, scale=_system_scale
) -> tuple[int, int]:
    """Centre the window, clamped at the top-left corner.

    Frameless windows get NO sensible default placement from pywebview --
    the spike's opened somewhere not visible on the primary screen -- so
    x/y are mandatory, not a nicety.

    Returned in LOGICAL units, because that is what pywebview expects and
    what WIDTH/HEIGHT are already expressed in: it applies the DPI scale
    to the geometry it is handed. `metrics` reports PHYSICAL pixels, since
    GetSystemMetrics is unvirtualized for the primary under
    PROCESS_SYSTEM_DPI_AWARE, so it has to be divided down first.

    Skipping that division is a bug that hides at 100%, where the two
    units are the same number. At 200% it doubled the centred coordinate:
    a 3840x2160 primary put the window at x=2800, hanging 1014px past the
    right edge with half of it on the next monitor.

    The clamp matters more than centring does: a negative x is legal on
    Windows and would put the custom title bar off the left edge, and a
    frameless window with no reachable drag region cannot be moved back.
    """
    screen_w, screen_h = metrics()
    factor = scale() or 1.0  # A reported DPI of 0 must not divide.
    screen_w = int(screen_w / factor)
    screen_h = int(screen_h / factor)
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


def create(api, hidden: bool = False) -> "webview.Window":
    """Build the main window and hand *api* its back-reference.

    `hidden` builds the window without showing it, for the login launch
    (M3): the app is tray-resident, and a start-on-login that raises a
    window at every boot is worse than no setting at all. The window is
    fully constructed either way -- only its visibility differs -- so the
    tray's Open item (__main__.on_open, which calls window.show()) needs no
    special case for it.

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
        # Without this the floor is pywebview's default 200x100
        # (winforms.py:210), and now that the window can be resized a user
        # can drag it down to a size the layout cannot render at all.
        min_size=(MIN_WIDTH, MIN_HEIGHT),
        hidden=hidden,
    )
    api._window = window

    # Deferred to `shown` because window.native does not exist until the
    # form is created (winforms.py:195), and the resize border is attached
    # to that form's handle.
    window.events.shown += lambda: chrome.enable_resize(window)
    return window


def run(func=None) -> None:
    """Hand the main thread to pywebview. Returns when the window is destroyed.

    *func* is startup work that needs the page to exist. pywebview runs it
    on its own thread immediately before it creates the window, so a
    `_push` from there waits on the real `_pywebviewready` event instead of
    a guessed delay -- and it waits on a thread nobody is looking at.

    That parameter is not a convenience. Every `Window.evaluate_js` in
    pywebview 6.2.1 is wrapped in `event.wait(20)` on `_pywebviewready`,
    an event that cannot be set before start() has run. A push issued on
    the main thread ahead of this call therefore blocks the whole launch
    for twenty seconds, then raises, then has its exception swallowed by
    Api._push -- an invisible window AND a lost message.

    Nothing this returns can be trusted as a success signal: when the
    WebView2 runtime is missing, pywebview logs the failure, start()
    returns normally, and the process exits 0. That is why __main__
    pre-flights the runtime before calling this.
    """
    _silence_pywebview_logging()
    import webview

    webview.start(func=func, gui=GUI_BACKEND)
