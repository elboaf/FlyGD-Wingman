"""Entry point: single-instance tray application."""
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from . import app as app_mod
from . import obsconfig, paths, settings as settings_mod, stitch, watcher

MUTEX_NAME = "Global\\OBSYouTubeUploader"
POLL_SECONDS = 3.0


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
    return handle


def resolve_recording_dir(cfg: dict) -> Path | None:
    """Stored setting, then OBS's own config, then ask the user.

    Must be called after a Tk root exists (and has been withdrawn) so
    ``askdirectory`` has a real root to parent itself to instead of
    creating a stray default one.
    """
    stored = cfg.get("recording_dir")
    if stored and Path(stored).is_dir():
        return Path(stored)
    detected = obsconfig.find_recording_dir()
    if detected and detected.is_dir():
        return detected
    chosen = filedialog.askdirectory(title="Where does OBS save your recordings?")
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
    handle = acquire_single_instance()
    if handle is None:
        return 0  # Another instance owns the tray; nothing to do.

    paths.ensure_dirs()
    stitch.sweep_orphans(paths.tmp_dir())
    cfg = settings_mod.load()

    root = tk.Tk()
    root.withdraw()  # Created on the main thread up front, shown on demand.

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
        try:
            ready = w.poll_once()
            if ready:
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
        except Exception:
            pass
        finally:
            root.after(int(POLL_SECONDS * 1000), poll)

    root.after(int(POLL_SECONDS * 1000), poll)
    root.mainloop()
    icon.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
