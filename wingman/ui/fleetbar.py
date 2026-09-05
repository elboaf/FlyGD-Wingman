"""Independent always-on-top Fleet DPS/EWAR display.

Like the sig bar, this is a second frameless pywebview window rather than a
child of the main app. It stays alive while disabled so a quick toggle does
not rebuild WebView2, and its page persists drag position on mouseup rather
than attaching Python window-event handlers that can deadlock WinForms.
"""

import logging
import sys

from wingman.ui import sigbar as sigbar_mod
from wingman.ui import window as window_mod

logger = logging.getLogger(__name__)

WIDTH = 420
HEIGHT = 90
MIN_SIZE = (1, 1)
DEFAULT_MARGIN = 60


def _default_placement() -> tuple[int, int]:
    """Top-left leaves room for a roster that grows downward after boot."""
    return (DEFAULT_MARGIN, DEFAULT_MARGIN)


def create(api, hidden: bool = True):
    """Create hidden and publish only inside the shutdown lifecycle gate."""
    import webview

    with api._fleetbar_lifecycle_lock:
        if api._fleetbar_quitting:
            return None
        section = api._state.settings.get("fleet_bar") or {}
        x, y = section.get("x"), section.get("y")
        if x is None or y is None:
            x, y = _default_placement()

        bar = webview.create_window(
            "Wingman Fleet Bar",
            str(window_mod._web_dir() / "fleetbar.html"),
            js_api=api,
            width=WIDTH,
            height=HEIGHT,
            x=x,
            y=y,
            frameless=True,
            easy_drag=False,
            on_top=True,
            focus=False,
            background_color=window_mod.BACKGROUND,
            min_size=MIN_SIZE,
            # Tool-window styling must land before the first show or Windows
            # can retain a taskbar button and Aero preview for the process.
            hidden=True,
        )
        api._fleetbar_window = bar
        if sys.platform == "win32":
            sigbar_mod._apply_tool_style(bar)
        return bar


def is_alive(bar) -> bool:
    if sys.platform == "win32":
        return sigbar_mod.is_alive(bar)
    return bar is not None and getattr(bar, "alive", True)


def reveal_bar(bar) -> None:
    if sys.platform == "win32":
        sigbar_mod.reveal_bar(bar)
    elif bar is not None:
        bar.show()


def hide_bar(bar) -> None:
    if sys.platform == "win32":
        sigbar_mod.hide_bar(bar)
    elif bar is not None:
        bar.hide()


def restore(api) -> None:
    """Create hidden; the page reveals itself after its first render and fit."""
    failed = False
    with api._fleetbar_lifecycle_lock:
        section = api._state.settings.get("fleet_bar") or {}
        if (
            api._fleetbar_quitting
            or not section.get("enabled")
            or is_alive(api._fleetbar_window)
        ):
            return
        try:
            api._fleetbar_ready = False
            create(api, hidden=True)
        except Exception:
            logger.exception("Fleet Bar window could not be created")
            failed = True
    if failed:
        # Enabled means visible for this display-only feature. Keep persisted
        # state and both controls honest; the next click retries construction.
        api.toggle_fleet_bar(False)
