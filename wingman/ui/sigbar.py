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

# The opening guess only: sigbar.js measures the laid-out text and calls
# Api.fit_sig_bar with both dimensions, so these never bound the real size.
# Tight guesses just keep the first paint from flashing oversized.
WIDTH = 260
HEIGHT = 32

# Where the bar opens when no position is stored: bottom-left of the
# primary screen, raised clear of a taskbar. Logical units, like every
# geometry pywebview is handed.
DEFAULT_MARGIN = 60
DEFAULT_BOTTOM_GAP = 90

# pywebview's default minimum is (200, 100) -- sized for a real window,
# and fatal here twice over: the 100px floor turns the strip into a tall
# empty slab, and once the page's measured size drops below 200 wide the
# overflow:hidden page clips the text entirely. The page is the only thing
# that knows its own size, so the floor belongs to it.
MIN_SIZE = (1, 1)


def _default_placement(scale) -> tuple[int, int]:
    """Bottom-left corner of the primary screen, in logical units.

    Same unit story as window_mod._placement: metrics reports PHYSICAL
    pixels under PROCESS_SYSTEM_DPI_AWARE and pywebview wants LOGICAL, so
    the metrics are divided by the system scale before use.
    """
    # Only the height is used: the bar opens at a fixed left margin, so
    # the screen width never enters the arithmetic.
    _screen_w, screen_h = window_mod._screen_size()
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

    `on_top=True` is pywebview's own pinned flag: the WinForms backend sets
    TopMost on the form at creation, on the UI thread, which is the whole
    feature. There is deliberately NO handler on `shown` or `moved` here --
    see the comment at the bottom of the file for the deadlock that taught
    this module to leave pywebview's event threads alone.
    """
    import webview

    section = api._state.settings.get("sig_bar") or {}
    x, y = section.get("x"), section.get("y")
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
        # The bar is dragged by its body and must never steal focus from
        # the client being flown. focus=False also buys the style-patch
        # moment below: pywebview itself patches ex-styles after creation
        # in its `not focus` branch, so a post-creation SetWindowLongW is
        # an established shape in this backend, not a hack of ours.
        focus=False,
        # The native surface paints before the first HTML frame; a mismatch
        # is a white flash, same as the main window's BACKGROUND note.
        background_color=window_mod.BACKGROUND,
        min_size=MIN_SIZE,
        hidden=hidden,
    )
    api._sigbar_window = bar

    # WS_EX_TOOLWINDOW, applied after creation. pywebview's WinForms
    # backend sets no ex-styles of its own, so the bar shipped with a
    # taskbar button and an aero preview: a second "window" beside
    # Wingman for what is chrome on the strip's behalf, and an aero X
    # whose close destroyed the form while the GUI kept reporting it
    # enabled. The tool-window style removes the taskbar button, the
    # aero preview and the X together -- what floating chrome is
    # supposed to be. NOACTIVATE rides along so hovering can never
    # activate the bar either. The handle only exists once the form is
    # materialised on the UI thread, hence the timer -- the same cadence
    # restore() uses for its reveal.
    if sys.platform == "win32":
        threading.Timer(0.3, lambda: _apply_tool_style(bar)).start()
    return bar


def _apply_tool_style(bar) -> None:
    """Add WS_EX_TOOLWINDOW|WS_EX_NOACTIVATE to the bar's window.

    Runs on a timer thread, but SetWindowLongW is safe from any thread
    (it does not pump, unlike the property sets that hung the drag --
    see the block comment at the bottom of this file). Logged, not
    raised: a bar without the style is the old cosmetic bug, not a
    reason to lose the bar.
    """
    from ctypes import windll

    try:
        handle = bar.native.Handle.ToInt32()
        GWL_EXSTYLE = -20
        WS_EX_TOOLWINDOW = 0x80
        WS_EX_NOACTIVATE = 0x08000000
        style = windll.user32.GetWindowLongW(handle, GWL_EXSTYLE)
        windll.user32.SetWindowLongW(
            handle, GWL_EXSTYLE, style | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        )
    except Exception:
        logger.exception("sig bar tool-window style could not be applied")


def restore(api) -> None:
    """Create the bar window at launch if the user left it enabled.

    Called from the main window's `shown` hook (__main__.py), so pywebview's
    event loop is already up and create_window is legal. Created hidden and
    shown only after the first style render, so the bar never flashes at
    the default placement before its stored style applies.
    """
    # .get, not ["sig_bar"]: the startup tests' settings fake is a partial
    # dict, and a bar that stays closed is the correct reading of "no
    # sig_bar section" (missing means off, the shipped default).
    section = api._state.settings.get("sig_bar") or {}
    if not section.get("enabled"):
        return
    try:
        bar = create(api, hidden=True)
    except Exception:
        logger.exception("sig bar window could not be created")
        return

    def reveal() -> None:
        try:
            bar.show()
            # Same instant-content rule as Api.toggle_sig_bar: the poll is
            # up to 3s away and an empty bar reads as broken.
            api._push_eve_status()
        except Exception:
            logger.exception("sig bar window could not be shown")

    threading.Timer(0.3, reveal).start()


# WHY NO `shown`/`moved` HANDLERS (the drag hang, reproduced and caught
# with faulthandler):
#
# The first revision subscribed to `shown` to re-assert TopMost
# (`bar.native.TopMost = True`) and to `moved` to debounce-persist the
# drag position. pywebview's Event.set() runs each handler on a freshly
# spawned thread, and on the WinForms backend it fires `shown` from the
# UI thread in the middle of window creation (winforms.py on_shown, under
# BrowserView.create) -- blocking that thread in Thread.start() until the
# handler thread has bootstrapped. The reproduced deadlock:
#
#   UI thread:      events.shown.set() -> Thread.start() -> waiting
#   handler thread: bar.native.TopMost = True -> SendMessage that needs
#                   the UI thread to pump
#
# ...and neither can proceed. The same shape is what hung the bar on its
# first drag in the field: any handler pywebview has to babysit from the
# UI thread turns every WM_MOVE into a UI-thread wait on a Python thread
# that may itself be waiting on the UI thread.
#
# The rule this module now follows: the bar's drag must look to pywebview
# exactly like the main window's, which has shipped for years -- ZERO
# Python handlers on window events. TopMost comes from `on_top=True` at
# creation; the position is persisted by sigbar.js, which reads
# window.screenX/screenY on mouseup and calls save_sig_bar_pos once per
# drag. No Python code runs per mouse-move.
