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
from . import patterns, sound, tailer

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
    def __init__(
        self,
        config,
        folder,
        on_alert,
        *,
        sound=None,
        focused=None,
        clock=time.monotonic,
    ):
        self._config = config
        self._folder = folder
        self._on_alert = on_alert
        self._sound = sound if sound is not None else play_sound
        # Which character owns the foreground RIGHT NOW, or None. A
        # callable for the same reason `config` is one -- it answers from
        # the preview thread's live state, which this thread must never
        # cache -- and defaulted to "nobody" so a build with no host (off
        # Windows, and every test that does not care) behaves as it always
        # did.
        self._focused = focused if focused is not None else lambda: None
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
                # Same rationale as reconcile()'s wedged-join branch above:
                # a thread that outlives this join is still running, and
                # forgetting it here (self._thread already cleared above)
                # would let the next reconcile() start a second poller
                # alongside it. Restore it as authoritative so reconcile()
                # keeps deferring until it actually exits.
                with self._lock:
                    if self._thread is None:
                        self._thread = thread

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

    def _focused_character(self):
        """The foreground client's character, or None if it cannot be had.

        Guarded because it crosses to the preview host: a raise here would
        cost the whole poll -- every alert in it, for every character --
        to spare one client a sound it did not need. Swallowed at debug
        level rather than warning: this runs once a second, and a host
        that has gone away would otherwise fill the log a user sends us
        with the least interesting line in it.
        """
        try:
            return self._focused()
        except Exception:
            # Caught broadly on purpose (no noqa needed -- logging the
            # exception satisfies BLE001, the same way alertframes.push
            # does it): losing the suppression is recoverable, losing the
            # poll is not.
            logger.debug("Could not read the focused client", exc_info=True)
            return None

    def _handle(self, events, now: float) -> list[tuple[str, str, str]]:
        """Filter, apply cooldowns, play sound, dispatch.

        Returns the dispatched (character, event, colour) triples, which is
        what the tests assert on.
        """
        cfg = self._config() or {}
        table = cfg.get("events") or {}
        pve = bool(cfg.get("pve_filter"))
        # Absent means full volume: an upgrading install's settings.json
        # predates the key, and defaulting to anything else would silence
        # alerts for everyone who already had them.
        volume = cfg.get("volume", 100)
        # Read once per poll rather than once per event. A poll's events
        # were all read from the log in the same tick, so one answer for
        # the batch is as true as any other -- and this crosses to the
        # preview thread, which is not something to do per line.
        focused = self._focused_character()
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
            sound_id = spec.get("sound") or "none"
            # The client you are already looking at gets the flash and not
            # the noise. The sound is the part that INTERRUPTS, and there
            # is nothing to interrupt you from when the fight is already
            # filling your screen -- while the ring is free, is where the
            # event happened, and is what tells you which of the three
            # things just fired.
            silent = event.character == focused
            if sound_id != "none" and not silent:
                self._sound(sound_id, volume)
            # persist_until_selected is global but travels merged into the
            # per-event spec, so PreviewWindow.arm_alert reads one dict and
            # the host does not have to know the section's shape.
            payload = dict(spec)
            persist = bool(cfg.get("persist_until_selected"))
            if silent:
                # Silent implies timed, decided HERE rather than left to
                # arm_alert's own `focused` read. The two run on different
                # threads with a queue between them, so a client that lost
                # the foreground in that gap would otherwise get the worst
                # pairing available: no sound, because this thread saw it
                # focused, AND a ring that pulses until acknowledged,
                # because the preview thread saw it was not. One decision,
                # taken once, keeps "you are looking at it" meaning the
                # same thing to both halves of the alert.
                persist = False
            payload["persist_until_selected"] = persist
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


def _play_file(path) -> None:
    """Hand a WAV file to the audio device. Windows only.

    SND_FILENAME | SND_ASYNC, unchanged from what shipped before volume
    existed, and NOT the SND_MEMORY the scaled bytes would suggest:
    winsound refuses `SND_MEMORY | SND_ASYNC` with RuntimeError ("this
    module does not support playing from a memory image asynchronously"),
    and the synchronous form would block the alert poll thread for the
    length of the sound -- 1.5s for `obey`, against a 1s poll. So the
    scaled audio is a file (sound.playable_path) and this call is the one
    it always was.
    """
    try:
        import winsound  # Deferred: CI is ubuntu-latest.
    except ImportError:
        return
    try:
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
    except RuntimeError:
        logger.exception("Could not play alert sound %s", path)


def play_sound(sound_id: str, volume: int = 100) -> None:
    """Play *sound_id* at *volume* (0-100).

    Volume 0 returns before resolving anything at all. A silent buffer
    would still open the device and still cost a scale, for a setting
    whose entire meaning is "make no noise" -- and PlaySound replaces
    whatever is still playing, so a silent buffer would also cut short an
    alert raised a moment earlier at an audible volume.

    The default is 100 so every caller that does not care about volume --
    and every test double that never did -- keeps working unchanged.
    """
    if volume <= 0:
        return
    path = sound_path(sound_id)
    if path is None:
        # Logged, not silent: a missing file looks exactly like a broken
        # alert from the user's side.
        logger.warning("No sound file for id %r; alert will be silent", sound_id)
        return
    _play_file(sound.playable_path(sound_id, path, volume))
