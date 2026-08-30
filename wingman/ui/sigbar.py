"""The floating sig bar: a tiny always-on-top clone of the status strip.

A second pywebview window, not a widget of the main one -- the whole point
is that it floats over OTHER applications (OBS, EVE itself), which no
child of the main window can do. It is frameless like the main window
(ui/window.py) and feeds from the same onEveStatus push, so there is no
second timer and no second reader of the engine's status file.

pywebview is imported lazily inside each function, for the same two
reasons ui/window.py does it that way: __main__ pre-flights the WebView2
runtime before pywebview is touched, and tests inject a stub module.

The window is created HIDDEN and kept for the process lifetime, shown and
hidden on toggle rather than destroyed: building a WebView2 environment is
hundreds of milliseconds, and a user flipping the bar on and off while
placing it would pay that every time. The cost of keeping it is one idle
WebView2 host, which the already-running previews subsystem dwarfs.
"""

import logging
import sys
import threading

from wingman.ui import window as window_mod

logger = logging.getLogger(__name__)

# Height is not fixed in Python: sigbar.js measures its own content and
# calls Api.fit_sig_bar with both dimensions, so this is only the size the
# window opens at before the first measurement lands.
WIDTH = 360
HEIGHT = 40

# Where the bar opens when no position is stored: bottom-left of the
# primary screen, raised clear of a taskbar. Logical units, like every
# geometry pywebview is handed.
DEFAULT_MARGIN = 60
DEFAULT_BOTTOM_GAP = 90

# The drag-end debounce. window.events.moved fires continuously while the
# bar is dragged; each fire would otherwise be a settings write, and a
# drag is dozens of fires. One trailing timer, replaced on every move.
_POS_SAVE_DEBOUNCE_S = 0.5


def _default_placement(scale) -> tuple[int, int]:
    """Bottom-left corner of the primary screen, in logical units.

    Same unit story as window_mod._placement: metrics reports PHYSICAL
    pixels under PROCESS_SYSTEM_DPI_AWARE and pywebview wants LOGICAL, so
    the metrics are divided by the system scale before use.
    """
    screen_w, screen_h = window_mod._screen_size()
    factor = scale() or 1.0
    return (
        DEFAULT_MARGIN,
        max(0, int(screen_h / factor) - HEIGHT - DEFAULT_BOTTOM_GAP),
    )


def create(api, hidden: bool = True):
    """Build the bar window and hand *api* its back-reference.

    Mirrors ui.window.create's invariant: the `api._sigbar_window` MUST be
    assigned via the underscore name AFTER create_window, for the same
    RecursionError reason documented there (pywebview's js_api proxy walk
    over public attributes).

    `on_top=True` is pywebview's own pinned flag. On the WinForms backend
    it sets the form's TopMost at creation, which is the whole feature;
    `on_shown` below re-asserts it natively in case a backend revision
    drops or reorders that.
    """
    import webview

    section = api._state.settings["sig_bar"]
    x, y = section["x"], section["y"]
    if x is None or y is None:
        x, y = _default_placement(window_mod._system_scale)

    bar = webview.create_window(
        "Wingman sig bar",
        str(window_mod._web_dir() / "sigbar.html"),
        js_api=api,
        width=WIDTH,
        height=HEIGHT,
        x=x,
        y=y,
        frameless=True,
        # The page marks its whole body as the drag region; nothing on the
        # bar is clickable, so easy_drag=False stays honest here exactly as
        # it does on the main window.
        easy_drag=False,
        on_top=True,
        # The native surface paints before the first HTML frame; a mismatch
        # is a white flash, same as the main window's BACKGROUND note.
        background_color=window_mod.BACKGROUND,
        hidden=hidden,
    )
    api._sigbar_window = bar
    bar.events.shown += lambda: on_shown(bar)
    # `moved` postdates some pywebview lines; a backend without it would
    # raise here and kill the toggle. Position saving degrades to "the bar
    # reopens at the default spot", which is the tolerable half.
    moved = getattr(bar.events, "moved", None)
    if moved is not None:
        moved += lambda: on_moved(api)
    return bar


def on_shown(bar) -> None:
    """Re-assert topmost on the native form, once it exists.

    window.native does not exist until the WinForms form is built -- the
    same ordering chrome.enable_resize works around on the main window.
    Off-Windows (tests, development) there is no native, and a pinned
    bar is untestable anyway, so the whole body is guarded.
    """
    if sys.platform != "win32":
        return
    try:
        bar.native.TopMost = True
    except Exception:
        # A bar that is not pinned is degraded, not broken: log it and
        # leave the window up.
        logger.exception("Could not pin the sig bar window")


def on_moved(api) -> None:
    """Schedule a debounced persist of the bar's last drag position."""
    timer = getattr(api, "_sigbar_pos_timer", None)
    if timer is not None:
        timer.cancel()
    api._sigbar_pos_timer = threading.Timer(
        _POS_SAVE_DEBOUNCE_S, _save_position, args=(api,)
    )
    api._sigbar_pos_timer.daemon = True
    api._sigbar_pos_timer.start()


def _save_position(api) -> None:
    bar = api._sigbar_window
    if bar is None:
        return
    try:
        x, y = bar.x, bar.y
    except Exception:
        logger.debug("sig bar position unreadable", exc_info=True)
        return
    try:
        api.save_sig_bar_pos(x, y)
    except Exception:
        logger.exception("sig bar position save failed")


def restore(api) -> None:
    """Create the bar window at launch if the user left it enabled.

    Called from the startup func handed to window_mod.run(), so pywebview's
    event loop is already up and create_window is legal. Created hidden and
    shown only after the first style render, so the bar never flashes at
    the default placement before its stored style applies.
    """
    if not api._state.settings["sig_bar"]["enabled"]:
        return
    try:
        bar = create(api, hidden=True)
    except Exception:
        logger.exception("sig bar window could not be created")
        return

    def reveal() -> None:
        try:
            bar.show()
        except Exception:
            logger.exception("sig bar window could not be shown")

    threading.Timer(0.3, reveal).start()
