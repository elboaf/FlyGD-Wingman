"""Entry point: single-instance tray application."""
import logging
import sys
import threading
import tkinter as tk
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tkinter import filedialog, messagebox

from . import app as app_mod
from . import discord, obsconfig, paths, settings as settings_mod, stitch, theme, watcher

logger = logging.getLogger(__name__)

MUTEX_NAME = "Global\\OBSYouTubeUploader"
POLL_SECONDS = 3.0
FAILURE_NOTIFY_THRESHOLD = 5  # ~15s of consecutive poll failures at POLL_SECONDS


def configure_logging() -> None:
    """Attach a rotating file handler so warnings land somewhere durable.

    Without this, every `logger.warning(...)` in this module and in
    watcher.py falls through to logging's lastResort handler -> stderr ->
    nowhere at all in a `console=False` PyInstaller build. That silently
    defeats the watcher's OSError degradation and the poll loop's failure
    logging, and leaves `__main__.py`'s own "check the log" message
    pointing at a file that was never created.

    Rotation matters: a persistent poll failure logs a warning every
    POLL_SECONDS forever, and an unbounded file would eventually fill the
    disk. A few MB with a couple of backups is plenty for debugging.

    Wrapped in its own try/except: a failure to open the log file (e.g. a
    read-only or full disk) must not prevent the app from starting.
    """
    try:
        handler = RotatingFileHandler(
            paths.log_dir() / "uploader_debug.log",
            maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"))
        # Redaction is enforced here, not at call sites. This handler is
        # attached to the ROOT logger, so every library logger inherits it --
        # an HTTP transport logging its request URL at DEBUG would otherwise
        # write a webhook token to disk without passing through our code.
        # The callable re-reads settings so a webhook configured after
        # startup is still redacted.
        def _current_webhook():
            hook, _ = discord.parse_webhook(
                settings_mod.load().get("discord_webhook"))
            return hook

        handler.addFilter(discord.RedactingFilter(_current_webhook))
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)
    except OSError:
        pass  # Logging is best-effort; must never block startup.


def acquire_single_instance():
    """Return a handle if this is the only instance, else None.

    Run-at-login plus a Start Menu shortcut makes double-launch likely, and
    two watchers means duplicate notifications and concurrent uploads of the
    same file. Worse, `stitch.sweep_orphans()` deletes files matching the
    stitch prefix on startup, so a second instance could sweep a merged file
    the first is actively uploading — this mutex is what prevents that.

    A second instance exits quietly rather than surfacing the first one's
    window: doing that properly needs cross-process IPC (a named pipe or
    WM_COPYDATA), which is disproportionate here — the tray icon is already
    visible and is the intended way to open the window.
    """
    if sys.platform != "win32":
        return object()  # No enforcement off-Windows; development only.
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, wintypes.BOOL(True), MUTEX_NAME)
    ERROR_ALREADY_EXISTS = 183
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        return None
    # Intentionally never closed: the mutex must be held for the app's
    # entire lifetime to enforce single-instance. The OS reclaims it on
    # process exit — do not "fix" this by adding a CloseHandle call, that
    # would release the mutex early and silently disable the protection.
    return handle


def set_dpi_awareness() -> None:
    """PROCESS_SYSTEM_DPI_AWARE, not Per-Monitor V2.

    System-DPI-aware is correct for a single-window tray utility and avoids
    handling WM_DPICHANGED when the window is dragged between monitors of
    different scale. Guarded exactly as acquire_single_instance() guards its
    Win32 call: off-Windows the process simply stays DPI-unaware, which only
    matters for local development.
    """
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # PROCESS_SYSTEM_DPI_AWARE
    except (AttributeError, OSError):
        pass  # shcore.dll predates Windows 8.1; nothing to do on older hosts.


def get_system_dpi() -> int:
    """96 (100%) is the correct fallback off-Windows or on very old hosts."""
    if sys.platform != "win32":
        return 96
    import ctypes
    try:
        dpi = ctypes.windll.user32.GetDpiForSystem()
    except (AttributeError, OSError):
        return 96
    # Floor, not just an exception guard: GetDpiForSystem returns 0 on
    # failure rather than raising, so the except above structurally cannot
    # catch it — and `tk scaling 0.0` would silently collapse every
    # point-sized font in the app.
    return dpi if dpi >= 96 else 96


def resolve_recording_dir(cfg: dict, ask=filedialog.askdirectory) -> Path | None:
    """Stored setting, then OBS's own config, then ask the user.

    Must be called after a Tk root exists (and has been withdrawn) so
    ``askdirectory`` has a real root to parent itself to instead of
    creating a stray default one.

    ``ask`` is injectable (defaults to ``filedialog.askdirectory``) purely
    so tests can exercise the stored/detected precedence above without a
    display; it is not meant to be overridden in production.
    """
    stored = cfg.get("recording_dir")
    if stored and Path(stored).is_dir():
        return Path(stored)
    detected = obsconfig.find_recording_dir()
    if detected and detected.is_dir():
        return detected
    chosen = ask(title="Where does OBS save your recordings?")
    return Path(chosen) if chosen else None


def build_tray(on_open, on_quit):
    """Tray icon with a generated image so no asset file is required."""
    import pystray
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (64, 64), "#1f1f1f")
    draw = ImageDraw.Draw(image)
    draw.ellipse((10, 10, 54, 54), fill="#ff0000")
    draw.polygon([(27, 22), (27, 42), (45, 32)], fill="#ffffff")

    menu = pystray.Menu(
        pystray.MenuItem("Open uploader", lambda *_: on_open(), default=True),
        pystray.MenuItem("Quit", lambda *_: on_quit()),
    )
    return pystray.Icon("obs_youtube_uploader", image, "OBS → YouTube Uploader", menu)


def main() -> int:
    set_dpi_awareness()
    handle = acquire_single_instance()
    if handle is None:
        return 0  # Another instance owns the tray; nothing to do.

    paths.ensure_dirs()
    configure_logging()
    stitch.sweep_orphans(paths.tmp_dir())
    cfg = settings_mod.load()

    root = tk.Tk()
    root.withdraw()  # Created on the main thread up front, shown on demand.
    root.tk.call("tk", "scaling", get_system_dpi() / 72.0)  # points-per-pixel, not /96
    theme.apply(root, theme.detect_mode())

    rec_dir = resolve_recording_dir(cfg)
    if rec_dir is None:
        messagebox.showerror("No recording folder",
                              "A recording folder is required. Exiting.")
        return 1
    cfg["recording_dir"] = str(rec_dir)
    settings_mod.save(cfg)

    state = app_mod.AppState(recording_dir=rec_dir, settings=cfg)
    window = app_mod.UploaderWindow(root, state)

    w = watcher.Watcher(rec_dir, paths.seen_file())
    w.baseline()  # Prunes stale `seen` entries left by out-of-band deletes.
    window.on_deleted = w.forget  # Clears in-app deletions from `seen`.

    def on_settings_saved() -> None:
        """Settings changes must reach the watcher, not just AppState.

        SettingsWindow replaces state.settings with a fresh dict and may
        change state.recording_dir. Anything holding the original objects
        goes stale, so the poll loop below reads state.settings each tick
        rather than closing over cfg.
        """
        if Path(state.recording_dir) != w.directory:
            w.rebind(state.recording_dir)
        window.refresh()

    window.on_settings_saved = on_settings_saved

    icon = build_tray(on_open=lambda: root.after(0, window.show),
                       on_quit=lambda: root.after(0, root.quit))
    threading.Thread(target=icon.run, daemon=True).start()

    def poll() -> None:
        # Everything here is guarded by a single try/finally so the loop
        # always reschedules itself: a `poll_once()` error, or an error
        # raised while showing/refreshing the window, must not silently
        # and permanently kill the watcher with no error shown to the user.
        nonlocal consecutive_failures, refresh_deferred
        try:
            # Independent of the watcher block below: a failed registry
            # read is a theming problem, not a watcher problem, and must
            # never be counted toward FAILURE_NOTIFY_THRESHOLD.
            detected_mode = theme.detect_mode()
            if detected_mode != theme.current_mode():
                theme.apply(root, detected_mode)
        except Exception:
            logger.warning("Theme check failed", exc_info=True)
        try:
            ready = w.poll_once()
            uploading = window.upload_thread is not None and window.upload_thread.is_alive()
            if ready:
                if uploading:
                    # refresh()/show() destroy every row and rebuild the
                    # list from scratch, which would wipe out the links
                    # and progress of the upload currently running. Defer
                    # the rebuild until the upload finishes, but still let
                    # the user know new recordings showed up.
                    refresh_deferred = True
                    try:
                        icon.notify(f"{len(ready)} new recording(s) ready to upload",
                                    "OBS → YouTube Uploader")
                    except Exception:
                        pass  # Notifications are best-effort.
                else:
                    # Read the live settings, not a snapshot taken at startup.
                    if state.settings.get("notify_mode", "toast") == "popup":
                        window.show(preselect=set(ready))
                    else:
                        window.refresh(preselect=set(ready))
                        try:
                            icon.notify(f"{len(ready)} new recording(s) ready to upload",
                                        "OBS → YouTube Uploader")
                        except Exception:
                            pass  # Notifications are best-effort.
                    refresh_deferred = False
            elif refresh_deferred and not uploading:
                # The upload that blocked the deferred refresh above has
                # since finished; catch the list up now even though this
                # particular tick found nothing new.
                window.refresh()
                refresh_deferred = False
            consecutive_failures = 0
        except Exception:
            # A single failure looks identical to "nothing new to upload,"
            # which is fine for a blip but not for a persistent problem
            # (unreachable recording folder, permissions error, a repeatedly
            # failing seen-file write). Always log it — otherwise even the
            # log file has no record — and after enough consecutive
            # failures, surface exactly one notification so the user isn't
            # staring at a tray icon that looks healthy while doing nothing.
            # The counter resets on any tick that completes cleanly, so a
            # long outage produces one message rather than a stream.
            logger.warning("Poll tick failed", exc_info=True)
            consecutive_failures += 1
            if consecutive_failures == FAILURE_NOTIFY_THRESHOLD:
                try:
                    icon.notify("The recording watcher is having trouble — check the log",
                                "OBS → YouTube Uploader")
                except Exception:
                    pass  # Notifications are best-effort.
        finally:
            root.after(int(POLL_SECONDS * 1000), poll)

    consecutive_failures = 0
    refresh_deferred = False
    root.after(int(POLL_SECONDS * 1000), poll)
    root.mainloop()
    icon.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
