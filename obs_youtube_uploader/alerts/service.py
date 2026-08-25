"""Between the tailer and the preview thread.

Owns the cooldown map, the NPC filter, sound, and the polling thread's
lifecycle. Everything it decides lives in _handle, which takes `now` and
returns what it dispatched -- so the decision layer is covered on
ubuntu-latest and the thread stays thin enough not to need covering.

Settings arrive through a CALLABLE, never a captured dict.
settings._normalize reassigns data["preview"] wholesale on every call
(settings.py:373-378), so a subtree captured at construction is orphaned
after the first write and this would silently run on stale config.
"""

import datetime
import logging
import threading
import time
from pathlib import Path
from typing import NamedTuple

from .. import paths
from . import patterns, tailer

logger = logging.getLogger(__name__)

UTC = datetime.UTC

POLL_INTERVAL_S = 1.0
RESCAN_INTERVAL_S = 5.0


class Health(NamedTuple):
    running: bool
    last_poll: float | None
    last_error: str | None
    characters: tuple[str, ...]


class AlertService:
    def __init__(self, config, folder, on_alert, *, sound=None, clock=time.monotonic):
        self._config = config
        self._folder = folder
        self._on_alert = on_alert
        self._sound = sound if sound is not None else play_sound
        self._clock = clock

        self._thread = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._tailer = None
        # (character, event) -> when it last dispatched.
        self._cooldowns = {}
        self._last_poll = None
        self._last_error = None

    # ---- lifecycle -----------------------------------------------------

    def _resolved_folder(self) -> Path | None:
        """The gamelogs folder as a Path, or None if alerts should not run.

        None whenever alerts are off, no folder is configured, or the
        configured folder no longer resolves to a real directory -- a
        folder that was valid and stopped being one (an unmounted drive,
        an unlinked OneDrive folder, a settings.json carried from another
        machine) must not read as "watching": Path.glob on a missing
        directory yields nothing and raises nothing, so a stale folder
        would otherwise look healthy forever. Called once per reconcile
        pass and cached by the caller, so a folder that becomes None
        between two reads of the callable cannot be seen valid here and
        then raise TypeError(None) in the caller a moment later.
        """
        cfg = self._config() or {}
        if not bool(cfg.get("enabled")):
            return None
        folder = self._folder()
        if folder is None:
            return None
        path = Path(folder)
        return path if path.is_dir() else None

    def _wanted(self) -> bool:
        """Running iff alerts are on and a folder resolves to a real
        directory.

        `folder` is composed by the caller to return None unless previews
        are also on, so this callable's answer already carries that gate.
        """
        return self._resolved_folder() is not None

    def reconcile(self) -> None:
        """Bring the thread in line with settings. Idempotent, any thread.

        Called from every setting that can change the answer, including
        the Gamelogs folder -- api.set_folder's gamelogs branch drives no
        watcher of its own, and the docstring above it records the bug
        that costs: a folder that persisted while the window looked
        healthy and nothing ever polled.
        """
        folder = self._resolved_folder()
        if folder is None:
            self.stop()
            return
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                if self._tailer is not None and self._tailer.folder == folder:
                    return
                # The folder moved. Tear down and rebuild rather than
                # repoint, so file positions cannot carry across.
                self._stop.set()
                thread = self._thread
                self._thread = None
            else:
                thread = None
        if thread is not None:
            thread.join(timeout=POLL_INTERVAL_S * 3)
            if thread.is_alive():
                # Wedged in a slow poll -- a OneDrive-redirected or network
                # Gamelogs path (combatlog.py:82-85) can make a single
                # readlines() call outlast this join. Do NOT build a
                # replacement: the old generation still owns its Tailer
                # (captured as a parameter in its _run call, not read off
                # self._tailer), so starting a second thread here would
                # have two threads polling -- one the old folder via its
                # captured Tailer, one whatever this call resolves next --
                # racing _cooldowns regardless. Restore self._thread so
                # the old generation stays authoritative and the next
                # reconcile() tries the join again, rather than believing
                # no thread is running at all.
                logger.warning(
                    "Alert poll thread did not exit within %.1fs; "
                    "leaving the previous generation running",
                    POLL_INTERVAL_S * 3,
                )
                with self._lock:
                    if self._thread is None:
                        self._thread = thread
                return
        with self._lock:
            stop_event = threading.Event()
            self._stop = stop_event
            new_tailer = tailer.Tailer(folder)
            self._tailer = new_tailer
            self._cooldowns.clear()
            self._thread = threading.Thread(
                target=self._run,
                args=(stop_event, new_tailer),
                name="wingman-alerts",
                daemon=False,
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            thread, self._thread = self._thread, None
            stop_event = self._stop
            stop_event.set()
        if thread is not None:
            thread.join(timeout=POLL_INTERVAL_S * 3)
            if thread.is_alive():
                logger.warning(
                    "Alert poll thread did not exit within %.1fs",
                    POLL_INTERVAL_S * 3,
                )

    def health(self) -> Health:
        with self._lock:
            alive = self._thread is not None and self._thread.is_alive()
            names = tuple(self._tailer.characters()) if self._tailer else ()
            return Health(alive, self._last_poll, self._last_error, names)

    def _record_error(self, exc: BaseException) -> None:
        with self._lock:
            self._last_error = f"{type(exc).__name__}: {exc}"

    # ---- the thread ----------------------------------------------------

    def _run(self, stop_event: threading.Event, tailer_: tailer.Tailer) -> None:
        """Poll until *stop_event*, against *tailer_* -- both passed in,
        neither read off the instance.

        reconcile() REPLACES self._stop AND self._tailer with a fresh Event
        and a fresh Tailer when it rebuilds the thread (above), after a
        join() whose timeout it does not treat as fatal. If this loop
        re-read either off self._stop/self._tailer on every iteration, a
        thread wedged past that join's timeout (a OneDrive-redirected or
        network Gamelogs path can make one readlines() call outlast it --
        combatlog.py:82-85) would wake, see the NEW generation's event
        unset and the NEW generation's Tailer installed, and keep polling
        THAT folder: two threads on one tailer, splitting file positions
        and racing _cooldowns. Capturing both as parameters makes that
        impossible regardless of what self._stop/self._tailer are
        reassigned to by the time they are checked -- this thread only
        ever touches the generation it was started with.
        """
        last_rescan = 0.0
        while not stop_event.is_set():
            try:
                now = self._clock()
                if now - last_rescan >= RESCAN_INTERVAL_S:
                    tailer_.rescan(datetime.datetime.now(UTC))
                    last_rescan = now
                self._handle(tailer_.poll(), now)
                with self._lock:
                    self._last_poll = now
            except Exception as exc:
                # Guarded deliberately: one unreadable file, a folder that
                # went away, or a decode surprise must cost one poll, not
                # the feature for the session. Recorded so the card can
                # say so -- silence is this feature's worst failure mode.
                logger.exception("Alert poll failed")
                self._record_error(exc)
            stop_event.wait(POLL_INTERVAL_S)

    # ---- the decision core -----------------------------------------------

    def _handle(self, events, now: float) -> list[tuple[str, str, str]]:
        """Filter, apply cooldowns, play sound, dispatch.

        Returns the dispatched (character, event, colour) triples, which is
        what the tests assert on.
        """
        cfg = self._config() or {}
        table = cfg.get("events") or {}
        pve = bool(cfg.get("pve_filter"))
        dispatched = []
        for event in events:
            spec = table.get(event.event)
            if not spec or not spec.get("enabled"):
                continue
            if (
                pve
                and event.event in patterns.FILTERED_EVENTS
                and patterns.is_likely_npc(event.source)
            ):
                continue
            key = (event.character, event.event)
            last = self._cooldowns.get(key)
            if last is not None and now - last < spec.get("cooldown_s", 0):
                # Checked before anything else happens: a suppressed event
                # is invisible everywhere, sound included.
                continue
            self._cooldowns[key] = now
            sound = spec.get("sound") or "none"
            if sound != "none":
                self._sound(sound)
            # persist_until_selected is global but travels merged into the
            # per-event spec, so PreviewWindow.arm_alert reads one dict and
            # the host does not have to know the section's shape.
            payload = dict(spec)
            payload["persist_until_selected"] = bool(cfg.get("persist_until_selected"))
            self._on_alert(event.character, event.event, payload)
            dispatched.append((event.character, event.event, spec.get("color")))
        return dispatched


def sound_path(sound_id: str) -> Path | None:
    """Resolve a sound id to a file, or None.

    Two cases, mirroring paths.icon_file() and window._web_dir(): a frozen
    build collects assets/sounds to the bundle root via uploader.spec's
    `datas` entry, so `bundle_dir() / "assets" / "sounds"` is correct there.
    A source checkout has no such collection step, so bundle_dir() (the
    repo root) is wrong; the real files live under the package's own
    assets/ folder instead. Deliberately NOT Path(__file__).parent alone:
    chrome.py's font does that and its destination in uploader.spec does
    not match, which is very likely why it is broken in the frozen build --
    do not copy that pattern.
    """
    if sound_id in (None, "", "none"):
        return None
    frozen_candidate = paths.bundle_dir() / "assets" / "sounds" / f"{sound_id}.wav"
    if frozen_candidate.is_file():
        return frozen_candidate
    source_candidate = (
        Path(__file__).resolve().parent.parent / "assets" / "sounds" / f"{sound_id}.wav"
    )
    if source_candidate.is_file():
        return source_candidate
    return None


def play_sound(sound_id: str) -> None:
    path = sound_path(sound_id)
    if path is None:
        # Logged, not silent: a missing file looks exactly like a broken
        # alert from the user's side.
        logger.warning("No sound file for id %r; alert will be silent", sound_id)
        return
    try:
        import winsound  # Deferred: CI is ubuntu-latest.
    except ImportError:
        return
    try:
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
    except RuntimeError:
        logger.exception("Could not play alert sound %s", path)
