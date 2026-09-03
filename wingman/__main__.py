"""Entry point: single-instance tray application."""

import contextlib
import logging
import os
import sys
import threading
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import combatlog, discord, hotkeys, obsconfig, paths, stitch, watcher
from . import settings as settings_mod
from .ui import api as api_mod
from .ui import preflight
from .ui import window as window_mod
from .ui.scheduler import Scheduler

logger = logging.getLogger(__name__)

MUTEX_NAME = "Global\\FlyGDWingman"

# 3.x owns this name. 4.0 contends with it deliberately: Inno cannot close
# a resident tray app, so an upgrade can leave 3.5.1 running while the user
# launches 4.0. Both would then write the same state -- and settings.save()
# projects the COMPLETE document from DEFAULTS, so two writers lose each
# other's keys entirely (settings.py:543-548 documents the same hazard for
# two threads sharing one lock; two processes share nothing).
#
# Removable once no 3.x installs remain in the wild. Not before 5.0, and
# not without checking download stats -- an undated "remove later" never
# gets removed.
LEGACY_MUTEX_NAME = "Global\\OBSYouTubeUploader"
POLL_SECONDS = 3.0
FAILURE_NOTIFY_THRESHOLD = 5  # ~15s of consecutive poll failures at POLL_SECONDS

# Exit code for "the WebView2 runtime is not usable". Non-zero on purpose:
# pywebview's own behaviour in that situation is to log, return from
# start(), and exit 0, which is a silent no-op for the user and a false
# success for anything watching the process.
EXIT_NO_WEBVIEW2 = 2


def _log_level() -> int:
    """Root log level, overridable with WINGMAN_LOG_LEVEL.

    INFO is right for normal running. It is wrong when the preview
    subsystem misbehaves in the field: that half is Windows-only, verified
    by a manual checklist rather than by pytest, so the log is the only
    evidence anyone has. Several of its load-bearing diagnostics are
    logger.debug -- whether WM_HOTKEY reached the message-only window,
    whether the thread's DPI override was accepted, why a placement read
    failed -- and INFO discards all of them. One checklist item asks the
    reader to "check the log for the DPI override result", which was not
    possible to do at all before this existed.

    An unrecognised name falls back to INFO rather than raising:
    logging.getLevelName returns the string "Level BANANAS" for an unknown
    name instead of failing, and handing that to setLevel would take
    logging down at startup over a typo in an environment variable.

    Raising this to DEBUG is safe with respect to secrets: the redaction
    filter is attached to the HANDLER below, so library records that only
    appear at DEBUG pass through it too. pywebview's own DEBUG chatter is
    silenced separately in ui/window.py.
    """
    raw = os.environ.get("WINGMAN_LOG_LEVEL", "").strip().upper()
    if not raw:
        return logging.INFO
    level = logging.getLevelName(raw)
    return level if isinstance(level, int) else logging.INFO


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
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )

        # Redaction is enforced here, not at call sites. This handler is
        # attached to the ROOT logger, so every library logger inherits it --
        # an HTTP transport logging its request URL at DEBUG would otherwise
        # write a webhook token to disk without passing through our code.
        # The callable re-reads settings so a webhook configured after
        # startup is still redacted.
        def _current_webhook():
            hook, _ = discord.parse_webhook(settings_mod.load().get("discord_webhook"))
            return hook

        handler.addFilter(discord.RedactingFilter(_current_webhook))
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        root_logger.setLevel(_log_level())
    except OSError:
        pass  # Logging is best-effort; must never block startup.


def _create_mutex(name: str) -> tuple[int, bool]:
    """Create a named mutex; return (handle, it_already_existed).

    Split out purely as the single Windows seam, so the two-name logic in
    acquire_single_instance() is testable off-platform. There is no other
    reason for this to be a separate function.
    """
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, wintypes.BOOL(True), name)
    ERROR_ALREADY_EXISTS = 183
    return handle, kernel32.GetLastError() == ERROR_ALREADY_EXISTS


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

    # Legacy FIRST and short-circuiting: if 3.x is up, stop before creating
    # anything, so this process never appears to be the owner of either name.
    # The handle is discarded here on purpose too, same as the one below:
    # holding it open for the process lifetime is what stops a 3.x launched
    # LATER from starting, and it works only because the raw HANDLE is an
    # int Python never closes.
    _, legacy_running = _create_mutex(LEGACY_MUTEX_NAME)
    if legacy_running:
        return None

    handle, already_running = _create_mutex(MUTEX_NAME)
    if already_running:
        return None
    # Intentionally never closed: both mutexes must be held for the app's
    # entire lifetime to enforce single-instance. The OS reclaims them on
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

    # shcore.dll predates Windows 8.1; nothing to do on older hosts.
    with contextlib.suppress(AttributeError, OSError):
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # PROCESS_SYSTEM_DPI_AWARE


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
        pystray.MenuItem("Open Wingman", lambda *_: on_open(), default=True),
        pystray.MenuItem("Quit", lambda *_: on_quit()),
    )
    return pystray.Icon("wingman", image, "FlyGD Wingman", menu)


def notify(icon, message: str) -> None:
    """Best-effort tray notification.

    Swallowed on purpose: there may be no toast service, notifications may
    be disabled by policy, or the shell may simply refuse. None of that is
    a reason to break a watcher tick.
    """
    with contextlib.suppress(Exception):
        icon.notify(message, "FlyGD Wingman")


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
    engine.start()


def build_preview_host(state, api_box):
    """The EVE preview host, or None where it cannot run.

    Windows-only, and constructed even when the feature is disabled: it
    starts no thread until Api.start_previews_if_enabled() or the settings
    toggle asks it to. Returning None off Windows keeps every call site in
    api.py a plain no-op rather than a platform check.

    `api_box` is a late-bound holder for the Api instance: the host is
    constructed as an argument to Api(...), so the name `api` does not
    exist yet when the callbacks below are defined. A plain dict rather
    than a closure over `api` for the same reason.
    """
    if sys.platform != "win32":
        return None
    try:
        from .preview import layout as preview_layout
        from .preview.host import PreviewHost
        from .preview.store import LayoutStore

        store = LayoutStore(update_settings=lambda: settings_mod.update(state.settings))
        section = state.settings.get("preview", {})

        def on_layout_changed(stable_key, rect, locked):
            # Nameless clients (character select) have no stable identity,
            # so persisting a position against them would hand it to
            # whichever client next sits at that screen.
            if stable_key.startswith("hwnd:"):
                return
            store.record(stable_key, preview_layout.Entry(rect, locked))

        def on_clients_changed(characters):
            for name in characters:
                store.record_character(name)
            # Fires on PreviewHost's own thread, possibly before api_box
            # is populated below -- degrade to a no-op rather than raise.
            api = api_box.get("api")
            if api is not None:
                api.push_preview_hotkeys()

        def on_layouts_changed():
            api = api_box.get("api")
            if api is not None:
                api.push_preview_hotkeys()

        def on_hotkey_status(status):
            api = api_box.get("api")
            if api is not None:
                api.push_preview_hotkeys(status)

        def on_bind_captured(gesture):
            # Same shape and same reason as on_hotkey_status above: fires
            # on the preview thread, and api_box may not be populated yet.
            api = api_box.get("api")
            if api is not None:
                api.push_bind_captured(gesture)

        def restore_positions():
            # Read per placement, never captured. The toggle changes
            # mid-session, and settings._normalize replaces the whole
            # preview section object on every write -- so this reads
            # through `state`, which keeps its identity, rather than
            # holding the section.
            #
            # Absent means on: an upgrading user's file predates the key,
            # and defaulting to off would silently discard every position
            # they have.
            return bool(
                state.settings.get("preview", {}).get("restore_preview_positions", True)
            )

        def show_labels():
            # Same reasoning as restore_positions above: read through
            # `state` on every call, never captured. Absent means on --
            # it is what shipped, and defaulting off would silently
            # restyle every existing install's previews.
            return bool(state.settings.get("preview", {}).get("show_labels", True))

        def opacity():
            return int(state.settings.get("preview", {}).get("opacity", 255))

        def minimize_inactive_clients():
            # Absent means off: minimizing a real EVE client window must
            # be asked for, never assumed by an upgrading install.
            return bool(
                state.settings.get("preview", {}).get(
                    "minimize_inactive_clients", False
                )
            )

        def hide_on_lost_focus():
            # Absent means off, and for a related reason to
            # minimize_inactive_clients above: taking every preview off
            # the screen is a change a user has to ask for, not one an
            # upgrading install is given.
            return bool(
                state.settings.get("preview", {}).get("hide_on_lost_focus", False)
            )

        def never_minimize():
            # A character-name list, not a per-character flag -- see
            # PreviewHost._is_never_minimize. Read live for the same
            # reason as restore_positions: the roster is edited while
            # previews are running.
            return list(state.settings.get("preview", {}).get("never_minimize", []))

        def locked():
            # Same shape as never_minimize, and for the same reason: a
            # per-character callable would need the character key at
            # construction time, which this function does not have.
            return list(state.settings.get("preview", {}).get("locked", []))

        def excluded():
            # Same shape and same live read as the two rosters above. The
            # default is an EMPTY list rather than anything cleverer: a
            # settings file predating this key must leave every character's
            # preview working, not blank the screen on upgrade.
            return list(state.settings.get("preview", {}).get("excluded", []))

        def snap():
            # Read live for the same reason as restore_positions: the
            # setting is changed while previews are running.
            return state.settings.get("preview", {}).get("snap", True) is not False

        def lock_aspect():
            # Live, same as snap: the checkbox must reach an open preview.
            return (
                state.settings.get("preview", {}).get("lock_aspect", True) is not False
            )

        def selection_color():
            # Live, same as snap: the picker must recolour an open
            # preview's ring through _restyle, not on a restart.
            return state.settings.get("preview", {}).get("selection_color", "#00c8dc")

        def lock_default():
            # Live, same as the roster it modifies. False when absent, so a
            # settings file predating the key resolves _is_locked to plain
            # membership -- the behaviour that shipped.
            return state.settings.get("preview", {}).get("lock_default", False) is True

        def default_size():
            # THE ONE SETTING HERE THAT WAS NOT LIVE. preview.width/height
            # were read once, into `size=` below, so the pair a preview
            # opens at could only change by restarting the app -- and they
            # had no user interface at all, so nothing ever asked them to.
            # Giving them a field made the staleness reachable, so they
            # join every other preview setting instead: a callable, read at
            # the moment a rect is resolved.
            #
            # The floors are settings.py's (120x90, validated_preview), not
            # restated here -- this only has to survive a section that
            # predates the keys.
            section_now = state.settings.get("preview", {})
            return (section_now.get("width", 320), section_now.get("height", 210))

        return PreviewHost(
            on_layout_changed=on_layout_changed,
            saved_layouts=preview_layout.deserialize(section.get("layouts")),
            # A bound method, never a lambda wrapping one: a name resolved
            # lazily inside a lambda is not checked when this function
            # runs, and tests/test_preview_wiring.py records what that cost
            # last time.
            flush_layouts=store.flush,
            # Same reasoning as flush_layouts above: bound methods, never
            # lambdas wrapping them.
            clear_layouts=store.clear,
            replace_layout=store.replace,
            on_clients_changed=on_clients_changed,
            on_layouts_changed=on_layouts_changed,
            on_hotkey_status=on_hotkey_status,
            on_bind_captured=on_bind_captured,
            restore_positions=restore_positions,
            show_labels=show_labels,
            opacity=opacity,
            minimize_inactive_clients=minimize_inactive_clients,
            never_minimize=never_minimize,
            hide_on_lost_focus=hide_on_lost_focus,
            size=default_size,
            locked=locked,
            lock_default=lock_default,
            excluded=excluded,
            snap=snap,
            lock_aspect=lock_aspect,
            selection_color=selection_color,
        )
    except Exception:
        # Previews are secondary to the upload workflow. A failure to
        # construct them must not stop Wingman launching.
        logger.exception("Preview subsystem unavailable")
        return None


def build_alert_service(state, host):
    """The gamelog alert poller, or None where it has nowhere to render.

    `host` is the PreviewHost build_preview_host just returned, or None.
    Alerts dispatch through `host.raise_alert` -- a None host (off
    Windows, or when preview construction itself failed) has no window to
    ring, so there is nothing this subsystem could do; return None rather
    than build a poller whose on_alert callback would be missing.

    Constructed unconditionally otherwise, alerts-enabled or not: like
    PreviewHost, reconcile() -- not construction -- is what starts its
    thread, called from Api once previews decide their own live state.
    """
    if host is None:
        return None
    from .alerts.service import AlertService

    def folder():
        # None unless previews are actually running AND a Gamelogs folder
        # resolves. AlertService._wanted() has no way to see preview state
        # on its own, so this composition is the whole of "no previews, no
        # polling thread" -- and it is why shutdown_previews's reconcile()
        # call (api.py) tears this down too: host.stop() flips
        # host.is_running false before that reconcile() runs.
        #
        # host.is_running, not the persisted preview.enabled setting: the
        # two agree everywhere except the moment of shutdown, and it is
        # exactly that moment reconcile() has to answer correctly.
        if not host.is_running:
            return None
        gamelogs = state.settings.get("gamelogs_dir")
        return Path(gamelogs) if gamelogs else combatlog.find_gamelogs_dir()

    try:
        return AlertService(
            config=lambda: state.settings.get("preview", {}).get("alerts", {}),
            folder=folder,
            on_alert=host.raise_alert,
            # What makes an alert on the client you are already looking at
            # silent. Read live, never captured: the foreground changes
            # constantly and the host is the only thing that knows.
            focused=host.focused_character,
        )
    except Exception:
        # Same posture as build_preview_host: alerts are secondary, and a
        # failure to construct the poller must not stop Wingman launching.
        logger.exception("Alert subsystem unavailable")
        return None


def migrate_eve_authority():
    """Run the one-way credential split before constructing EVE controllers."""
    from .eveauth.migration import migrate_legacy_skills

    return migrate_legacy_skills(
        paths.eve_skills_file(),
        paths.eve_authority_file(),
    )


def build_authority_controller(api, migration):
    """Build shared authority only from a completed, non-lossy migration."""
    if not migration.completed or migration.authority is None:
        return None
    try:
        from .eveauth.controller import AuthorityController

        return AuthorityController(
            state_path=paths.eve_authority_file(),
            authority=migration.authority,
            alert=api._alert,
            changed=api._eve_authority_changed,
        )
    except Exception:
        logger.exception("EVE authority subsystem unavailable")
        return None


def build_skills_controller(api, authority, *, startup_warnings=()):
    """The EVE skills controller, or None where it cannot be built.

    NOT Windows-gated, unlike build_preview_host: twelve of the thirteen
    modules in the subpackage are pure or filesystem-only, and the one
    Windows-only piece (dpapi) is reached through an injected seam inside
    tokens.py. Gating here would make the route dead in development and
    would take the entire Linux test surface with it.

    Takes the Api rather than the AppState because `push` and `_alert` are
    bound methods of the Api -- and it is constructed after it for the same
    chicken-and-egg reason ui/window.py assigns `api._window` after
    create_window().

    The imports are inside the function so a broken or missing subpackage
    costs the Skills route and nothing else; the whole body is wrapped for
    the same reason previews are.
    """
    try:
        from .eveskills.controller import SkillsController

        if authority is None:
            return None
        return SkillsController(
            state_path=paths.eve_skills_file(),
            cache_path=paths.eve_skills_cache_file(),
            plans_dir=paths.skill_plans_dir(),
            # Bound methods, never lambdas wrapping them: a name resolved
            # lazily inside a lambda is not checked when this function
            # runs, and tests/test_preview_wiring.py records what that cost
            # last time.
            #
            # _push_skills, not _push: the skills payload carries a rendered
            # `fetched_label` that only ui/ knows how to build, and the raw
            # _push is what left every render after the first one unlabelled
            # (D3/S6). Its docstring holds the whole account.
            push=api._push_skills,
            alert=api._alert,
            authority=authority,
            startup_warnings=startup_warnings,
        )
    except Exception:
        # Skills are secondary to the upload workflow. A failure to
        # construct them must not stop Wingman launching.
        logger.exception("EVE skills subsystem unavailable")
        return None


def build_fittings_controller(api, authority):
    """Build the local fitting owner without performing any ESI request."""
    try:
        from .evefittings.controller import FittingsController

        if authority is None:
            return None
        return FittingsController(
            state_path=paths.eve_fittings_file(),
            names_path=paths.eve_fittings_names_file(),
            authority=authority,
            alert=api._alert,
        )
    except Exception:
        # Fittings are additive. Corrupt or unavailable local state must not
        # prevent recording uploads or Skills from launching.
        logger.exception("EVE fittings subsystem unavailable")
        return None


def wire_eve_controllers(api):
    """Migrate, compose, then register both EVE feature participants."""
    try:
        migration = migrate_eve_authority()
    except Exception as exc:
        logger.exception("EVE authority migration failed unexpectedly")
        api._authority_warnings = [
            f"EVE identity migration could not run ({exc}). Restart Wingman to retry."
        ]
        return None, None

    startup_warnings = list(migration.warnings)
    if not migration.completed:
        startup_warnings.append(
            migration.error
            or "EVE identity migration did not complete. Restart Wingman to retry."
        )
        api._authority_warnings = startup_warnings
        return None, None

    authority = build_authority_controller(api, migration)
    if authority is None:
        startup_warnings.append(
            "Shared EVE authority is unavailable. Restart Wingman to retry."
        )
        api._authority_warnings = startup_warnings
        return None, None

    api._authority = authority
    skills = build_skills_controller(api, authority, startup_warnings=startup_warnings)
    if skills is None:
        api._authority_warnings = [
            *startup_warnings,
            "The EVE skills subsystem is unavailable.",
        ]
    else:
        api._skills = skills
        authority.register_participant(skills)

    fittings = build_fittings_controller(api, authority)
    if fittings is not None:
        api._fittings = fittings
        authority.register_participant(fittings)
    return authority, skills


def shutdown_eve_controllers(api) -> None:
    """Stop feature workers before the authority they consume."""
    fittings = api._fittings
    if fittings is not None:
        try:
            fittings.shutdown()
        except Exception:
            logger.exception("EVE fittings subsystem did not stop cleanly")
    api.shutdown_skills()
    api.shutdown_authority()


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

    # BEFORE ensure_dirs(), which creates state_dir() and would otherwise
    # make the migration a no-op that strands 3.x state. The status is
    # returned rather than logged because logging is not up yet.
    migration_status = paths.migrate_state_dir()
    paths.ensure_dirs()
    configure_logging()
    logger.info("State directory: %s", migration_status)
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
    engine = hotkeys.HotkeyEngine(
        paths.engine_exe(), paths.engine_script(), paths.state_dir()
    )
    state.engine = engine
    engine.apply(state.settings["eve_bookmarks"])
    # Unconditional, and before the enabled check: an engine orphaned by a
    # crashed session must be reclaimed even if the user has since turned
    # the feature off, or nothing ever will.
    reclaim_orphaned_engine(engine)
    start_engine_if_enabled(engine, state.settings["eve_bookmarks"])

    api_box = {}
    preview_host = build_preview_host(state, api_box)
    api = api_mod.Api(
        state,
        preview_host=preview_host,
        alerts=build_alert_service(state, preview_host),
    )
    api_box["api"] = api
    # Migration and authority composition happen after Api construction so
    # warnings have a durable route payload and callbacks bind eagerly. They
    # still happen before the window starts and before any EVE feature work.
    wire_eve_controllers(api)

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
        if window is None:
            return
        # An upload runs on a daemon thread, so destroying the window here
        # kills it mid-chunk with nothing on screen -- a multi-gigabyte
        # transfer discarded by one menu click. The decision lives on Api
        # because it has to raise the hidden window and bound its own wait;
        # see _confirm_quit_if_busy. A refusal leaves the app running,
        # which is the recoverable half of the two failures.
        if not api._confirm_quit_if_busy():
            return
        # The sig bar must be destroyed FIRST. pywebview's WinForms loop is
        # Application.Run() with no context: it pumps until Application.
        # Exit(), which fires only when the LAST window is gone. Leaving
        # the bar alive parks the process inside window_mod.run() forever
        # after the user chose Quit -- reproduced, not theorised.
        bar = api._sigbar_window
        if bar is not None:
            try:
                bar.destroy()
                api._sigbar_window = None
            except Exception:
                logger.exception("Sig bar window did not destroy cleanly")
        window.destroy()  # unblocks window_mod.run() below

    icon = build_tray(on_open=on_open, on_quit=on_quit)
    threading.Thread(target=icon.run, daemon=True, name="pystray").start()

    # Before the window, not after: window_mod.run() below blocks until the
    # window is destroyed, so anything started after it never runs until
    # the app is already quitting. No-op unless the user enabled previews.
    api.start_previews_if_enabled()

    # M3: the login entry autostart.command() registers carries --hidden, so
    # the boot launch lands in the tray without raising a window. Read from
    # argv rather than from a setting: the flag describes HOW THIS PROCESS
    # was started, which no stored value can know -- the same binary opened
    # from the Start menu a minute later must show its window.
    #
    # Bare membership test rather than argparse. This is the only argument
    # the app takes, and argparse would exit(2) with a usage message on any
    # unrecognised one -- in a windowed build with no console, that is a
    # launch that dies with nothing on screen and nothing in the log.
    # Ignoring what we do not understand is the right failure here.
    window = window_mod.create(api, hidden="--hidden" in sys.argv[1:])

    # The floating sig bar reopens here, not in run()'s startup func:
    # test_startup pins that func to `api.refresh_auth` itself, and this
    # hook is the better home anyway -- `shown` fires on the GUI thread
    # (the same thread chrome.enable_resize rides), which is the thread a
    # second WebView2 window has to be built on. The events guard is for
    # the startup tests' window fake, which has no `events` attribute.
    shown = getattr(window, "events", None)
    if shown is not None:

        def _restore_sigbar(api=api):
            from .ui import sigbar

            sigbar.restore(api)

        shown.shown += _restore_sigbar

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
        # The Api holds the watcher directly: set_folder rebinds it when
        # the recording folder changes, and delete_selected forgets what it
        # actually removed. No callback indirection.
        api._watcher = w
        scheduler = Scheduler(
            POLL_SECONDS, lambda: poll_tick(w, api, icon, window, poll_state)
        )
        scheduler.start()

    api._on_recording_dir_ready = start_watching

    if rec_dir is not None:
        # Through update(), not save(): start_previews_if_enabled() above
        # may already have the preview store's debounce thread alive, so
        # this write races it the same way every other settings writer
        # does. cfg IS state.settings (passed in above), so mutating it in
        # place here keeps both in sync exactly as before.
        with settings_mod.update(cfg) as live:
            live["recording_dir"] = str(rec_dir)
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
    # Manager. A live loopback socket on the fixed redirect port would
    # likewise make the next launch's sign-in fail to bind, and the
    # redirect URI is registered with CCP so there is no fallback port to
    # move to -- so both teardowns run here, unconditionally, in order.
    api.shutdown_previews()
    shutdown_eve_controllers(api)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
