"""Independent always-on-top Fleet DPS/EWAR display.

Like the sig bar, this is a second frameless pywebview window rather than a
child of the main app. It stays alive while disabled so a quick toggle does
not rebuild WebView2, and its page persists drag position on mouseup rather
than attaching Python window-event handlers that can deadlock WinForms.
"""

import ctypes
import logging
import secrets
import sys

from wingman import bookmarks
from wingman import settings as settings_mod
from wingman.ui import chrome
from wingman.ui import sigbar as sigbar_mod
from wingman.ui import window as window_mod

logger = logging.getLogger(__name__)

WIDTH = settings_mod.FLEET_BAR_DEFAULT_PREFERRED_CONTENT_WIDTH
HEIGHT = 90
MIN_SIZE = (1, 1)
DEFAULT_MARGIN = 60
ZERO_INSETS = chrome.ResizeInsets(0, 0, 0, 0)
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x80
WS_EX_NOACTIVATE = 0x08000000


def _default_placement() -> tuple[int, int]:
    """Top-left leaves room for a roster that grows downward after boot."""
    return (DEFAULT_MARGIN, DEFAULT_MARGIN)


def _user32(user32=None):
    if user32 is not None:
        return user32
    if sys.platform != "win32":
        return None
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    user32.SetWindowLongW.restype = ctypes.c_long
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    return user32


def window_hwnd(window) -> int | None:
    """The window HWND as an int, or None when it cannot be read."""
    try:
        native = getattr(window, "native", None)
        if native is None:
            return None
        handle = native.Handle
        if hasattr(handle, "ToInt64"):
            return int(handle.ToInt64())
        return int(handle.ToInt32())
    except Exception:  # noqa: BLE001 -- WinForms handle access fails for the same reasons the sig-bar helper documents: no native yet or torn down mid-call both mean "no HWND".
        return None


def main_window_hwnd(window) -> int | None:
    return window_hwnd(window)


def outer_width_for_content(content_width, insets) -> int:
    return int(content_width) + (insets.horizontal if insets is not None else 0)


def content_width_for_outer(outer_width, insets) -> int:
    return max(0, int(outer_width) - (insets.horizontal if insets is not None else 0))


def clamp_rect_to_work_area(x, y, width, height, work_area):
    if work_area is None:
        return int(x), int(y), int(width), int(height)
    left, top, right, bottom = (int(value) for value in work_area)
    width = max(1, min(int(width), max(1, right - left)))
    height = max(1, min(int(height), max(1, bottom - top)))
    x = min(max(int(x), left), right - width)
    y = min(max(int(y), top), bottom - height)
    return x, y, width, height


def current_work_area(bar):
    work_area = getattr(bar, "work_area", None)
    if (
        isinstance(work_area, tuple)
        and len(work_area) == 4
        and all(isinstance(value, int) for value in work_area)
    ):
        return work_area
    if sys.platform != "win32":
        return None

    native = getattr(bar, "native", None)
    if native is None:
        return None

    try:
        user32, _set_ptr, _wndproc, MONITORINFO, _minmaxinfo, wintypes = chrome._win32()
        handle = wintypes.HWND(native.Handle.ToInt64())
        monitor = user32.MonitorFromWindow(handle, chrome.MONITOR_DEFAULTTONEAREST)
        if not monitor:
            return None
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None
        scale = chrome._scale_for(user32, handle) or 1.0
        work = info.rcWork
        return (
            round(work.left / scale),
            round(work.top / scale),
            round(work.right / scale),
            round(work.bottom / scale),
        )
    except Exception:
        logger.debug("Could not read the Fleet Bar work area", exc_info=True)
        return None


def apply_geometry(bar, x, y, width, height) -> None:
    current_width = getattr(bar, "width", None)
    current_height = getattr(bar, "height", None)
    if current_width != width or current_height != height:
        bar.resize(width, height)

    current_x = getattr(bar, "x", None)
    current_y = getattr(bar, "y", None)
    if current_x != x or current_y != y:
        bar.move(x, y)


def set_bar_clickable(bar, clickable: bool, *, user32=None) -> bool:
    user32 = _user32(user32)
    handle = window_hwnd(bar)
    if user32 is None or handle is None:
        return False
    style = int(user32.GetWindowLongW(handle, GWL_EXSTYLE))
    wanted = style & ~WS_EX_NOACTIVATE if clickable else style | WS_EX_NOACTIVATE
    if wanted == style:
        return True
    user32.SetWindowLongW(handle, GWL_EXSTYLE, wanted)
    return True


def _window_text(user32, hwnd) -> str:
    length = int(user32.GetWindowTextLengthW(hwnd))
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def eve_title_predicate(title: str) -> bool:
    return bool(title and bookmarks.is_engine_window_title(title))


def activate_bar(bar, *, user32=None) -> tuple[bool, int | None]:
    user32 = _user32(user32)
    handle = window_hwnd(bar)
    if user32 is None or handle is None:
        return False, None
    previous = int(user32.GetForegroundWindow() or 0)
    if not set_bar_clickable(bar, True, user32=user32):
        return False, previous
    user32.SetForegroundWindow(handle)
    if int(user32.GetForegroundWindow() or 0) == handle:
        return True, previous
    set_bar_clickable(bar, False, user32=user32)
    return False, previous


def deactivate_bar(bar, return_hwnd, *, main_window=None, user32=None) -> bool:
    user32 = _user32(user32)
    if user32 is None:
        return False
    set_bar_clickable(bar, False, user32=user32)
    if not isinstance(return_hwnd, int) or return_hwnd <= 0:
        return False
    if not user32.IsWindow(return_hwnd):
        return False
    if return_hwnd == main_window_hwnd(main_window):
        user32.SetForegroundWindow(return_hwnd)
        return True
    if not eve_title_predicate(_window_text(user32, return_hwnd)):
        return False
    user32.SetForegroundWindow(return_hwnd)
    return True


def create(api, hidden: bool = True):
    """Create hidden and publish only inside the shutdown lifecycle gate."""
    import webview

    with api._fleetbar_lifecycle_lock:
        if api._fleetbar_quitting:
            return None
        api._retire_fleet_page_locked()
        section = api._state.settings.get("fleet_bar") or {}
        x, y = section.get("x"), section.get("y")
        if x is None or y is None:
            x, y = _default_placement()
        preferred_content_width = int(section.get("preferred_content_width", WIDTH))

        bar = None
        try:
            page_id = secrets.token_hex(32)
            bar = webview.create_window(
                "Fleet Bar",
                str(window_mod._web_dir() / "fleetbar.html") + "#fleet-page=" + page_id,
                js_api=api,
                width=preferred_content_width,
                height=HEIGHT,
                x=x,
                y=y,
                frameless=True,
                easy_drag=False,
                on_top=True,
                focus=False,
                # NOT transparent=True, for the same field reason as the sig
                # bar's: per-pixel window transparency mispaints the backing
                # on resize and move. Opaque dark window.
                background_color=window_mod.BACKGROUND,
                min_size=MIN_SIZE,
                # Tool-window styling must land before the first show or Windows
                # can retain a taskbar button and Aero preview for the process.
                hidden=hidden,
            )
            if bar is None:
                raise RuntimeError("Fleet Bar creation returned no window")

            resize_insets = ZERO_INSETS
            resize_enabled = False
            if sys.platform == "win32":
                sigbar_mod._apply_tool_style(bar)
                attached = chrome.enable_horizontal_resize(
                    bar,
                    min_content_width=settings_mod.FLEET_BAR_MIN_PREFERRED_CONTENT_WIDTH,
                    max_content_width=settings_mod.FLEET_BAR_MAX_PREFERRED_CONTENT_WIDTH,
                )
                if attached is not None:
                    resize_insets = attached
                    resize_enabled = True

            applied_x, applied_y, applied_outer_width, applied_outer_height = (
                clamp_rect_to_work_area(
                    x,
                    y,
                    outer_width_for_content(preferred_content_width, resize_insets),
                    HEIGHT,
                    current_work_area(bar),
                )
            )
            if not hidden:
                apply_geometry(
                    bar,
                    applied_x,
                    applied_y,
                    applied_outer_width,
                    applied_outer_height,
                )
            api._publish_fleet_page_locked(
                bar,
                page_id,
                resize_insets=resize_insets,
                resize_enabled=resize_enabled,
                applied_x=applied_x,
                applied_y=applied_y,
                applied_outer_width=applied_outer_width,
                applied_outer_height=applied_outer_height,
            )
            return bar
        except Exception:
            # Keep the candidate local until styled. Both restore and toggle
            # must revoke admission before cleanup, even after partial publication.
            api._retire_fleet_page_locked()
            if bar is not None:
                try:
                    bar.destroy()
                except Exception:
                    logger.debug("Failed Fleet Bar did not destroy", exc_info=True)
            raise


def is_alive(bar) -> bool:
    if sys.platform == "win32":
        return sigbar_mod.is_alive(bar)
    return bar is not None and getattr(bar, "alive", True)


def is_visible(bar, *, user32=None) -> bool:
    user32 = _user32(user32)
    if user32 is not None:
        handle = window_hwnd(bar)
        return bool(handle and user32.IsWindowVisible(handle))
    return bool(
        bar is not None
        and getattr(bar, "alive", True)
        and not getattr(bar, "hidden", False)
    )


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
            create(api, hidden=True)
        except Exception:
            logger.exception("Fleet Bar window could not be created")
            failed = True
    if failed:
        # Enabled means visible for this display-only feature. Keep persisted
        # state and both controls honest; the next click retries construction.
        api.toggle_fleet_bar(False)
