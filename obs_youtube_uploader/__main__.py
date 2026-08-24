"""Entry point: single-instance tray application."""
import logging
import sys
import threading
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import discord, hotkeys, obsconfig, paths, settings as settings_mod, stitch, watcher
from .ui import api as api_mod, preflight, window as window_mod
from .ui.scheduler import Scheduler

logger = logging.getLogger(__name__)

MUTEX_NAME = "Global\\OBSYouTubeUploader"
POLL_SECONDS = 3.0
FAILURE_NOTIFY_THRESHOLD = 5  # ~15s of consecutive poll failures at POLL_SECONDS

# Exit code for "the WebView2 runtime is not usable". Non-zero on purpose:
# pywebview's own behaviour in that situation is to log, return from
# start(), and exit 0, which is a silent no-op for the user and a false
# success for anything watching the process.
EXIT_NO_WEBVIEW2 = 2


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


def resolve_recording_dir(cfg: dict) -> Path | None:
    """Stored setting, then OBS's own config. No third option.

    The `ask` fallback is gone, and this is the one deliberate behaviour
    change in the replatform. pywebview's create_file_dialog is a method on
    a window, so no dialog can exist before webview.start() -- there is
    nothing to parent it to and nothing to run its modal loop. Returning
    None now means "the page must render its first-run route", which calls
    pick_folder once a window does exist.

    Existing installations have recording_dir persisted and never reach it.
    """
    stored = cfg.get("recording_dir")
    if stored and Path(stored).is_dir():
        return Path(stored)
    detected = obsconfig.find_recording_dir()
    if detected and detected.is_dir():
        return detected
    return None


def build_tray(on_open, on_quit):
    """Tray icon backed by the bundled .ico, generated art as a fallback."""
    import pystray
    from PIL import Image, ImageDraw

    icon_path = paths.icon_file()
    image = None
    if icon_path is not None:
        try:
            image = Image.open(icon_path)
        except OSError:
            image = None

    if image is None:
        # Fallback only: keeps the tray icon present per the codebase's
        # degrade-don't-block policy for optional presentation capabilities.
        image = Image.new("RGB", (64, 64), "#1f1f1f")
        draw = ImageDraw.Draw(image)
        draw.ellipse((10, 10, 54, 54), fill="#ff0000")
        draw.polygon([(27, 22), (27, 42), (45, 32)], fill="#ffffff")

    menu = pystray.Menu(
        pystray.MenuItem("Open uploader", lambda *_: on_open(), default=True),
        pystray.MenuItem("Quit", lambda *_: on_quit()),
    )
    return pystray.Icon("obs_youtube_uploader", image, "FlyGD Wingman", menu)


def notify(icon, message: str) -> None:
    """Best-effort tray notification.

    Swallowed on purpose: there may be no toast service, notifications may
    be disabled by policy, or the shell may simply refuse. None of that is
    a reason to break a watcher tick.
    """
    try:
        icon.notify(message, "FlyGD Wingman")
    except Exception:
        pass


@dataclass
class PollState:
    """The two flags the tick carries between runs.

    A mutable object rather than nonlocals, so poll_tick can be a
    module-level function with a test harness. Under Tk this state lived in
    closure cells that nothing outside main() could reach.
    """
    consecutive_failures: int = 0
    refresh_deferred: bool = False


def poll_tick(w, api, icon, window, state: PollState) -> None:
    """One watcher tick. Runs on the Scheduler's thread, never the UI thread.

    Reaches the page only through the Api, which pushes; it never touches
    the DOM and never calls into pywebview except for window.show(), which
    spike Q6 proved is safe from a non-main thread.

    Must not raise. Scheduler reschedules regardless, but the failure
    counter and the one-shot "having trouble" notification live here and
    would be lost along with the exception.
    """
    try:
        api._push_eve_status()
    except Exception:
        # Its own guard: a status-push failure must not count against the
        # recording watcher's failure counter or skip poll_once.
        logger.exception("Engine status push failed.")
    try:
        ready = w.poll_once()
        uploading = api._busy()
        if ready:
            if uploading:
                # A full rebuild would wipe the links and progress of the
                # upload currently running. Defer it until that finishes --
                # but still tell the user recordings arrived.
                state.refresh_deferred = True
                notify(icon, f"{len(ready)} new recording(s) ready to upload")
            else:
                # A set of Path: RowSnapshot.rebuild matches preselect
                # against info.path, so strings would never match.
                api.list_rows(preselect=set(ready))
                # Live settings, not a snapshot taken at startup: Settings is
                # a route in this same window now and can change mid-run.
                if api._state.settings.get("notify_mode", "toast") == "popup":
                    window.show()
                else:
                    notify(icon, f"{len(ready)} new recording(s) ready to upload")
                state.refresh_deferred = False
        elif state.refresh_deferred and not uploading:
            # The upload that blocked the deferred rebuild has since
            # finished; catch the list up even though this tick found
            # nothing new.
            api.list_rows()
            state.refresh_deferred = False
        state.consecutive_failures = 0
    except Exception:
        # A single failure looks identical to "nothing new to upload," which
        # is fine for a blip but not for a persistent problem (unreachable
        # folder, permissions, a repeatedly failing seen-file write). Always
        # log it, and after enough consecutive failures surface exactly one
        # notification. The counter resets on any clean tick, so a long
        # outage produces one message rather than a stream.
        logger.warning("Poll tick failed", exc_info=True)
        state.consecutive_failures += 1
        if state.consecutive_failures == FAILURE_NOTIFY_THRESHOLD:
            notify(icon, "The recording watcher is having trouble — check the log")


def reclaim_orphaned_engine(engine) -> None:
    """Terminate an engine left behind by a crashed session.

    Runs at startup regardless of whether the feature is enabled, and that
    is the whole point. stop() clears the pid record even when it could not
    confirm the process died, and recover_orphan() otherwise runs only from
    start(), which runs only when enabled. So a hung engine would survive
    indefinitely the moment a user turned the feature off: a global keyboard
    hook, with nothing left in the application able to reclaim it and no UI
    that mentions it. Each of those choices is defensible on its own; the
    hole is in their combination.

    Never raises: a failure to reclaim must not stop the app starting.
    """
    if engine is None:
        return
    try:
        engine.recover_orphan()
    except Exception:
        logger.exception("Orphan reclamation failed; continuing startup.")


def start_engine_if_enabled(engine, section) -> None:
    """Start the hotkey engine only when the user has turned it on.

    Opt-in is the whole point: enabling installs a global keyboard hook, and
    an upgrading user must not acquire one by upgrading.
    """
    if engine is None or not section.get("enabled"):
        return
    if engine.start():
        engine.sync_sequence()


def build_preview_host(state):
    """The EVE preview host, or None where it cannot run.

    Windows-only, and constructed even when the feature is disabled: it
    starts no thread until Api.start_previews_if_enabled() or the settings
    toggle asks it to. Returning None off Windows keeps every call site in
    api.py a plain no-op rather than a platform check.
    """
    if sys.platform != "win32":
        return None
    try:
        from .preview import layout as preview_layout
        from .preview.host import PreviewHost
        from .preview.store import LayoutStore

        store = LayoutStore(
            save_settings=settings_mod.save,
            read_settings=lambda: state.settings)
        section = state.settings.get("preview", {})

        def on_layout_changed(stable_key, rect, locked):
            # Nameless clients (character select) have no stable identity,
            # so persisting a position against them would hand it to
            # whichever client next sits at that screen.
            if stable_key.startswith("hwnd:"):
                return
            store.record(stable_key, preview_layout.Entry(rect, locked))

        return PreviewHost(
            on_layout_changed=on_layout_changed,
            saved_layouts=preview_layout.deserialize(section.get("layouts")),
            size=(section.get("width", 320), section.get("height", 210)),
            # A bound method, never a lambda wrapping one: a name resolved
            # lazily inside a lambda is not checked when this function
            # runs, and tests/test_preview_wiring.py records what that cost
            # last time.
            flush_layouts=store.flush)
    except Exception:
        # Previews are secondary to the upload workflow. A failure to
        # construct them must not stop Wingman launching.
        logger.exception("Preview subsystem unavailable")
        return None


def build_client_layout_manager(state):
    """The EVE client window layout manager, or None where it cannot run.

    Shaped like build_preview_host above, and for the same reasons:
    Windows-only, None elsewhere so every call site stays a plain no-op,
    and construction failures are swallowed because this is secondary to
    the upload workflow.

    NOT gated on preview.enabled. This moves the client windows
    themselves; it shares a settings section and a tab with previews and
    nothing else.
    """
    if sys.platform != "win32":
        return None
    try:
        from .preview import clientwin32, discovery, geometry
        from .preview import win32 as preview_win32
        from .preview.clientlayout import ClientLayoutManager

        def screen():
            # Re-read per batch, not cached: monitors get plugged in and
            # rearranged while Wingman runs, and a stale origin makes the
            # reachability check answer about a desktop that is gone.
            libs = preview_win32.bind()
            return geometry.virtual_desktop(libs.user32.GetSystemMetrics)

        return ClientLayoutManager(
            read_settings=lambda: state.settings,
            # settings.update, not settings.save: the read must happen
            # inside _SAVE_LOCK or a concurrent writer is reverted.
            update_settings=settings_mod.update,
            list_clients=discovery.list_clients,
            read_placement=clientwin32.read_placement,
            apply_placement=clientwin32.apply_placement,
            work_area_origin=clientwin32.work_area_origin,
            screen=screen,
            dpi_context=clientwin32.dpi_context)
    except Exception:
        logger.exception("Client layout manager unavailable")
        return None


def shutdown_engine(engine) -> None:
    """Stop the engine on the way out, whatever else has gone wrong.

    An engine that outlives Wingman keeps a keyboard hook alive with nothing
    left to disable it, so this must never be the thing that raises.
    """
    if engine is None:
        return
    try:
        engine.stop()
    except Exception:
        logger.exception("Engine did not stop cleanly")


def main() -> int:
    set_dpi_awareness()
    handle = acquire_single_instance()
    if handle is None:
        return 0  # Another instance owns the tray; nothing to do.

    paths.ensure_dirs()
    configure_logging()
    stitch.sweep_orphans(paths.tmp_dir())
    cfg = settings_mod.load()

    # BEFORE anything touches pywebview. When the runtime is absent,
    # pywebview logs the failure, webview.start() returns normally, and the
    # process exits 0 -- no window, no error, no crash dialog, and a
    # success exit code, with no console in a windowed build to show the
    # diagnostic. This check is the only thing standing between that and a
    # user who thinks the app is broken for no reason.
    if not preflight.require_webview2():
        return EXIT_NO_WEBVIEW2

    rec_dir = resolve_recording_dir(cfg)
    state = api_mod.AppState(
        # None until first run completes. NOT Path.home(): a fallback there
        # would send list_rows() scanning the user's entire home directory
        # for .mkv files on first launch, which is slow, alarming, and
        # produces a list that looks like a bug rather than an empty state.
        recording_dir=rec_dir,
        settings=cfg,
        ffmpeg_bin=paths.resolve_binary("ffmpeg"),
        ffprobe_bin=paths.resolve_binary("ffprobe"),
    )
    engine = hotkeys.HotkeyEngine(paths.engine_exe(), paths.engine_script(),
                                  paths.state_dir())
    state.engine = engine
    engine.apply(state.settings["eve_bookmarks"])
    # Unconditional, and before the enabled check: an engine orphaned by a
    # crashed session must be reclaimed even if the user has since turned
    # the feature off, or nothing ever will.
    reclaim_orphaned_engine(engine)
    start_engine_if_enabled(engine, state.settings["eve_bookmarks"])

    api = api_mod.Api(state, preview_host=build_preview_host(state),
                      client_layouts=build_client_layout_manager(state))

    w = None
    scheduler = None
    window = None
    poll_state = PollState()

    def on_open() -> None:
        # Called on the pystray thread. show() and destroy() are safe from
        # there (spike Q6, confirmed twice); no marshalling needed, and
        # there is no event loop left to marshal onto anyway.
        #
        # The None guard is not paranoia: the tray thread is started before
        # create() returns, so a very fast click can land in the gap.
        if window is not None:
            window.show()

    def on_quit() -> None:
        if window is not None:
            window.destroy()  # unblocks window_mod.run() below

    icon = build_tray(on_open=on_open, on_quit=on_quit)
    threading.Thread(target=icon.run, daemon=True, name="pystray").start()

    # Before the window, not after: window_mod.run() below blocks until the
    # window is destroyed, so anything started after it never runs until
    # the app is already quitting. No-op unless the user enabled previews.
    api.start_previews_if_enabled()

    # Same reason as the line above: window_mod.run() below blocks, so
    # anything started after it never runs until the app is quitting.
    api.start_client_layouts_if_enabled()

    window = window_mod.create(api)

    def start_watching(directory) -> None:
        """Create the watcher and start the poll loop. Idempotent.

        Called once the recording directory is known: at startup when it is
        already stored or detected, or later from the page's first-run
        route once the user picks one.
        """
        nonlocal w, scheduler
        if scheduler is not None:
            return
        w = watcher.Watcher(Path(directory), paths.seen_file())
        w.baseline()  # Prunes stale `seen` entries left by out-of-band deletes.
        # The Api holds the watcher directly: save_settings rebinds it when
        # the recording folder changes, and delete_selected forgets what it
        # actually removed. No callback indirection.
        api._watcher = w
        scheduler = Scheduler(POLL_SECONDS,
                              lambda: poll_tick(w, api, icon, window, poll_state))
        scheduler.start()

    api._on_recording_dir_ready = start_watching

    if rec_dir is not None:
        cfg["recording_dir"] = str(rec_dir)
        settings_mod.save(cfg)
        # Started before run() rather than from a page-loaded event: the
        # first tick is POLL_SECONDS away and the page asks for its own
        # state on load, so an early push has nothing to race with.
        start_watching(rec_dir)
    else:
        # First run, or a stored folder that has since disappeared. The page
        # cannot infer this state -- an unconfigured folder and an empty one
        # look identical from there -- so it is pushed explicitly. Deferred
        # until the page is up, because a push before app.js has registered
        # its handlers is logged and dropped (see Api._push).
        api._push_first_run_when_ready()

    # Resolve the account state off the bridge thread so the Settings route
    # is correct the first time it is opened rather than after a click.
    #
    # Handed to run() rather than called here. refresh_auth's first act is
    # a push, and a push before webview.start() blocks the MAIN thread on
    # pywebview's twenty-second readiness timeout -- an invisible window on
    # every launch, and the push lost to _push's bare except when the
    # timeout finally raises. pywebview runs this on its own thread once
    # the GUI loop owns the main one.
    window_mod.run(api.refresh_auth)  # Blocks until the window is destroyed.

    icon.stop()
    if scheduler is not None:
        scheduler.stop()
    shutdown_engine(engine)
    # Last, and unconditional: a preview thread that outlives the window
    # still owns HWNDs, and Wingman leaves the tray but stays in Task
    # Manager.
    api.shutdown_previews()
    api.shutdown_client_layouts()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
