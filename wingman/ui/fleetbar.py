"""Independent always-on-top Fleet DPS/EWAR display.

Like the sig bar, this is a second frameless pywebview window rather than a
child of the main app. It stays alive while disabled so a quick toggle does
not rebuild WebView2, and its page persists drag position on mouseup rather
than attaching Python window-event handlers that can deadlock WinForms.
"""

import logging
import threading

from wingman.ui import window as window_mod

logger = logging.getLogger(__name__)

WIDTH = 380
HEIGHT = 90
MIN_SIZE = (1, 1)
DEFAULT_MARGIN = 60


def _default_placement() -> tuple[int, int]:
    """Top-left leaves room for a roster that grows downward after boot."""
    return (DEFAULT_MARGIN, DEFAULT_MARGIN)


def create(api, hidden: bool = True):
    """Create the pinned display and assign its private Api back-reference."""
    import webview

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
        background_color=window_mod.BACKGROUND,
        min_size=MIN_SIZE,
        hidden=hidden,
    )
    api._fleetbar_window = bar
    return bar


def restore(api) -> None:
    """Restore the bar after the main WebView2 window is shown."""
    section = api._state.settings.get("fleet_bar") or {}
    if not section.get("enabled") or api._fleetbar_window is not None:
        return
    try:
        bar = create(api, hidden=True)
    except Exception:
        logger.exception("Fleet Bar window could not be created")
        # Enabled means visible for this display-only feature. Keep persisted
        # state and both main-page controls honest, and let the next click
        # retry the same construction path.
        api.toggle_fleet_bar(False)
        return

    def reveal() -> None:
        try:
            bar.show()
            api._push_fleet_snapshot()
        except Exception:
            logger.exception("Fleet Bar window could not be shown")
            api.toggle_fleet_bar(False)

    threading.Timer(0.3, reveal).start()
