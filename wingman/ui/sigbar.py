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


def create(api):
    """Build the bar window, hidden, and hand *api* its back-reference.

    Mirrors ui.window.create's invariant: the `api._sigbar_window` MUST be
    assigned via the underscore name AFTER create_window, for the same
    RecursionError reason documented there (pywebview's js_api proxy walk
    over public attributes).

    Always created hidden and shown by reveal_bar: the taskbar button is
    created at a window's first show, so the tool-window style below has
    to land while it is still hidden or the button (and its aero
    preview) can persist past the style change. The synchronous style
    patch is safe because a secondary pywebview window's form is built
    on the UI thread through a synchronous Invoke -- the handle exists
    by the time create_window returns.

    `on_top=True` is pywebview's own pinned flag: the WinForms backend
    sets TopMost on the form at creation, on the UI thread, which is the
    whole feature. There is deliberately NO handler on `shown` or
    `moved` here -- see the comment at the bottom of the file for the
    deadlock that taught this module to leave pywebview's event threads
    alone.

    Returns None when the app is quitting: the guided-update flow tears
    the bar down before restarting, and a create racing that teardown
    would leak a WebView2 window into the relaunch.
    """
    import webview

    # Covers the native create AND publication. Shutdown taking the same lock
    # either waits and destroys this exact bar, or wins first and closes the
    # lifecycle before WebView2 can allocate another window.
    with api._sigbar_lifecycle_lock:
        if api._sigbar_quitting:
            return None
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
            # The bar is dragged by its body and must never steal focus
            # from the client being flown.
            focus=False,
            # True per-pixel transparency: pywebview's WinForms+EdgeChromium
            # path sets SupportsTransparentBackColor and makes the WebView2
            # background Color.Transparent, so the page's rounded shell is
            # the WINDOW's shape -- without it the form's own square
            # background paints behind the CSS border-radius corners.
            # background_color is ignored on this path, which is fine: the
            # first paint risk it covers is hidden-at-creation.
            transparent=True,
            # The native surface paints before the first HTML frame; a
            # mismatch is a white flash, same as the main window's note.
            background_color=window_mod.BACKGROUND,
            min_size=MIN_SIZE,
            # ALWAYS hidden at creation, including the first enable -- see
            # the docstring. reveal_bar does the showing.
            hidden=True,
        )
        api._sigbar_window = bar
        if sys.platform == "win32":
            _apply_tool_style(bar)
        return bar


def recreate(api, size=None):
    """Rebuild the bar window instead of resizing it in place.

    The field result that motivated this: resizing a VISIBLE transparent
    window leaves its backing painted (white or stale) until the window
    is toggled off and on -- i.e. until the native surface is rebuilt.
    So a shape change rebuilds by design: destroy, create hidden at the
    stored position, apply the measured size WHILE STILL HIDDEN (the
    moment a resize is safe), then reveal. The cost is one WebView2
    window build (~a few hundred ms) on the rare ticks where the text
    width actually changes -- cheaper than shipping a permanently
    miscomposited bar.

    `size` is the (width, height) the page measured. Best-effort: if the
    hidden resize fails the bar still comes back at its opening guess
    and the next shape change tries again. Returns the new bar, or None
    (refused: quitting, or creation failed).
    """
    with api._sigbar_lifecycle_lock:
        if api._sigbar_quitting:
            return None
        old = api._sigbar_window
        if old is not None:
            try:
                old.destroy()
            except Exception:
                logger.exception("sig bar destroy during refit failed")
        api._sigbar_window = None
        bar = create(api)  # re-enters this lock; RLock by design
        if bar is None:
            return None
        if size is not None:
            try:
                width, height = (int(size[0]), int(size[1]))
                if width > 0 and height > 0:
                    bar.resize(width, height)
            except Exception:
                logger.debug("sig bar refit resize failed", exc_info=True)
        reveal_bar(bar)
        return bar


# Native show/hide and the style patch all key off the HWND. ctypes calls
# are used instead of pywebview's show()/hide() on purpose: pywebview's
# show() ACTIVATES the form (focus steal from the client being flown) and
# both go through `shown`-event waits designed for windows that load
# content, which a chrome bar has no use for. ShowWindow and
# SetWindowLongW are safe from any thread and pump nothing -- unlike the
# property sets that hung the drag (see the block comment at the bottom).


def _hwnd(bar):
    """The bar's HWND as an int, or None when it cannot be read.

    Blind except on purpose: `native` and `Handle` are WinForms objects
    whose failure modes here (no native yet, handle not created, torn
    down mid-call) are all "there is no window", and every caller's
    next step for None is the same as for a dead window.
    """
    try:
        return bar.native.Handle.ToInt32()
    except Exception:  # noqa: BLE001
        return None


def _apply_tool_style(bar) -> None:
    """Add WS_EX_TOOLWINDOW|WS_EX_NOACTIVATE to the bar's window.

    Called right after create_window returns: a secondary window's form
    is built on the UI thread through a SYNCHRONOUS Invoke, so the
    handle already exists and no timer is needed -- the timer this
    replaced could also lose a race with the window's first show, which
    is how the bar shipped a taskbar button in the first release of
    this feature. Idempotent, and applied to a window that is still
    hidden, so the shell never creates the button.
    """
    from ctypes import windll

    handle = _hwnd(bar)
    if handle is None:
        logger.warning("sig bar handle unavailable; tool-window style skipped")
        return
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x80
    WS_EX_NOACTIVATE = 0x08000000
    style = windll.user32.GetWindowLongW(handle, GWL_EXSTYLE)
    windll.user32.SetWindowLongW(
        handle, GWL_EXSTYLE, style | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
    )


def is_alive(bar) -> bool:
    """Whether the bar's window still exists as an OS window.

    The close-an-aero-preview destruction path is gone with the aero
    preview itself, but IsWindow is a one-call answer that also covers
    any other teardown, and unlike pywebview's `closed` event it needs
    no attribute walk over a possibly-stubbed object.
    """
    from ctypes import windll

    if bar is None:
        return False
    handle = _hwnd(bar)
    return bool(handle and windll.user32.IsWindow(handle))


def is_visible(bar) -> bool:
    """Whether the bar is on screen. Used by Api.fit_sig_bar, whose
    resize would otherwise SHOW a hidden bar (pywebview's resize passes
    SWP_SHOWWINDOW) -- which is how a toggled-off bar kept coming back
    on the next status poll."""
    from ctypes import windll

    handle = _hwnd(bar)
    return bool(handle and windll.user32.IsWindowVisible(handle))


def reveal_bar(bar) -> None:
    """Show the bar without activating it."""
    from ctypes import windll

    handle = _hwnd(bar)
    if handle:
        # SW_SHOWNOACTIVATE: shown, but the foreground stays where it
        # is. Re-asserting the tool style costs one syscall and covers
        # a window whose creation somehow skipped it.
        _apply_tool_style(bar)
        windll.user32.ShowWindow(handle, 8)


def hide_bar(bar) -> None:
    """Hide the bar. Native, because pywebview's hide marshals an
    Invoke at a form that may be mid-teardown; SW_HIDE has no such
    dependency."""
    from ctypes import windll

    handle = _hwnd(bar)
    if handle:
        windll.user32.ShowWindow(handle, 0)


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
        bar = create(api)
    except Exception:
        logger.exception("sig bar window could not be created")
        return
    if bar is None:
        return

    def reveal() -> None:
        shown = False
        try:
            with api._sigbar_lifecycle_lock:
                # The timer belongs to this exact creation. A shutdown or a
                # replacement makes it stale; neither may resurrect the old
                # native window after teardown has begun.
                if api._sigbar_quitting or api._sigbar_window is not bar:
                    return
                reveal_bar(bar)
                shown = True
        except Exception:
            logger.exception("sig bar window could not be shown")
        if shown:
            # Same instant-content rule as Api.toggle_sig_bar: the poll is
            # up to 3s away and an empty bar reads as broken. The render
            # this triggers also re-fits the (now visible) bar.
            api._push_eve_status()

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
