"""Supervise the stream mirror process (issue #317).

Engine-pattern guardianship (``procguard.ProcGuard``) plus what the
mirror specifically needs: bounded restarts when the child dies
out-of-band, and a liveness-driven status the Streaming card can show.
The mirror is on-demand -- nothing here starts it because Wingman
launched; a user or launch-restore asks, and this class keeps that
promise alive across ordinary deaths without becoming an always-on
watchdog loop: callers poll (the settings scheduler's existing cadence),
the way engine status is polled.

Clock and seams are injected; Linux-runnable with the engine's own fake
harness. No status file of the engine's kind yet: the mirror is a window,
not a reporter -- state derives from the child handle, never from disk
(the engine's own lesson: the file outlives the process that wrote it).
"""

import logging
import subprocess
import time
import uuid
from dataclasses import dataclass

from . import procid
from .procguard import ProcGuard, default_job

logger = logging.getLogger(__name__)

_MISSING = (
    "The stream mirror is missing from this installation. "
    "Reinstall FlyGD Wingman to restore it."
)

_GAVE_UP = (
    "The stream mirror kept stopping, so restarts were paused. "
    "Start it again from the Streaming card."
)

# Burst guard, not a lifetime cap: N quick deaths in a row mean something
# is wrong that restarting cannot fix (a broken exe, a DLL conflict).
# Deaths spread wider than the window are independent failures and re-arm
# the budget. Same shape as every other bounded-retry in the house.
RESTART_LIMIT = 3
RESTART_WINDOW_S = 60.0


@dataclass(frozen=True)
class MirrorStatus:
    """What the Streaming card row shows. States: ``off`` (user turned it
    off), ``stopped`` (should run, is not, no budget spent), ``running``,
    ``given-up`` (restart budget spent -- the card's error row)."""

    state: str
    last_error: str | None = None


class MirrorSupervisor:
    """Own the wingman-mirror.exe child process and the user's intent
    that it run."""

    def __init__(
        self,
        exe,
        state_dir,
        *,
        spawner=subprocess.Popen,
        token_factory=lambda: uuid.uuid4().hex,
        job_factory=default_job,
        procid_module=procid,
        restart_limit=RESTART_LIMIT,
        restart_window_s=RESTART_WINDOW_S,
        clock=time.time,
    ):
        self._guard = ProcGuard(
            exe,
            state_dir,
            pid_name="wingman_mirror.pid",
            image_name="wingman-mirror.exe",
            spawner=spawner,
            token_factory=token_factory,
            job_factory=job_factory,
            procid_module=procid_module,
        )
        self._restart_limit = restart_limit
        self._restart_window_s = restart_window_s
        self._clock = clock
        self._deaths = []  # timestamps of out-of-band deaths in the window
        self.gave_up = False

    # -- public surface (the card and the launcher) ---------------------
    @property
    def exe_path(self):
        """The exe this supervisor was built for (paths.mirror_exe()'s
        resolution, or None) -- the setup ceremony's registration path,
        shown on the card because the installed location (_internal\\bin)
        is not one a user could guess (#321)."""
        return self._guard.exe_path()

    @property
    def last_error(self):
        return self._guard.last_error

    def start(self) -> bool:
        """The user (or launch restore) asked for the mirror. Resets any
        earlier gave-up state: a fresh explicit ask is a fresh budget."""
        self.gave_up = False
        self._deaths.clear()
        return self._spawn()

    def stop(self, timeout: float = 5.0) -> None:
        self.gave_up = False
        self._deaths.clear()
        self._guard.stop(timeout=timeout)

    def ensure_running(self, now: float | None = None) -> bool:
        """Keep the user's promise alive across out-of-band deaths,
        within the burst budget. Pollers call this; it never starts a
        mirror the user did not ask for -- the caller checks the setting.

        Returns True when the mirror is (or was just again made) alive.
        """
        if self._guard.is_running():
            return True
        if self.gave_up:
            return False
        now = self._clock() if now is None else now
        window_start = now - self._restart_window_s
        self._deaths = [t for t in self._deaths if t >= window_start]
        if len(self._deaths) >= self._restart_limit:
            self.gave_up = True
            self._guard.last_error = _GAVE_UP
            logger.warning("Mirror restart budget spent; giving up until asked.")
            return False
        self._deaths.append(now)
        return self._spawn()

    def is_running(self) -> bool:
        return self._guard.is_running()

    def status(self, enabled: bool) -> MirrorStatus:
        """Driven by liveness, never by the pid record on disk -- the
        record outlives the process that wrote it (the engine lesson)."""
        if not enabled:
            return MirrorStatus(state="off")
        if self._guard.is_running():
            return MirrorStatus(state="running")
        if self.gave_up:
            return MirrorStatus(state="given-up", last_error=self._guard.last_error)
        return MirrorStatus(state="stopped", last_error=self._guard.last_error)

    # -- passthrough for launch wiring (orphan reclaim at startup) ------
    def recover_orphan(self) -> bool:
        return self._guard.recover_orphan()

    # -- internals -------------------------------------------------------
    def _spawn(self) -> bool:
        exe = str(self._guard.exe_path())
        return self._guard.launch(
            lambda token: [exe, "--token", token],
            required_paths=(exe,),
            missing_message=_MISSING,
        )
