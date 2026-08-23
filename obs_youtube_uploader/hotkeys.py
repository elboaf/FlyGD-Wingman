"""Supervise the EVE bookmark hotkey engine.

AutoHotkey is confined to this module: nothing in its public interface
names it. That is deliberate -- the naming logic may later be reimplemented
in Python, and this boundary is what makes that a swap rather than a
rewrite of the integration.

Windows-only at runtime, importable and testable everywhere: the process is
reached only through an injected spawner.
"""
import json
import logging
import subprocess
import sys
import uuid
from pathlib import Path

from . import atomicio, bookmarks, paths

logger = logging.getLogger(__name__)

# CREATE_NO_WINDOW doesn't exist off Windows, and the tests inject a fake
# spawner -- same shape as stitch.py:27 and library.py:19.
_NO_WINDOW_KWARGS = (
    {"creationflags": subprocess.CREATE_NO_WINDOW}
    if sys.platform == "win32" else {}
)

_MISSING = ("The bookmark engine is missing from this installation. "
            "Reinstall FlyGD Wingman to restore it.")


class HotkeyEngine:
    """Own the engine process and the files it reads.

    A record left behind by a crashed session is deliberately not cleaned up
    here: this class can only reason about a process it spawned itself, so
    deciding whether an on-disk record names a live engine, a dead one, or a
    pid Windows has since reused belongs to orphan recovery, which verifies
    the process image and a run token before terminating anything.
    """

    def __init__(self, exe, script, state_dir, *,
                 spawner=subprocess.Popen,
                 token_factory=lambda: uuid.uuid4().hex):
        self._exe = exe
        self._script = Path(script) if script else None
        self._state_dir = Path(state_dir)
        self._spawner = spawner
        self._token_factory = token_factory
        self._proc = None
        self._token = None
        self.last_error: str | None = None

    # -- config ------------------------------------------------------
    def apply(self, section: dict) -> None:
        """Regenerate the INI the engine reads.

        The engine picks this up on its own 10s timer, so there is no need
        to restart it and lose in-flight state (root system, used slots).
        """
        atomicio.write_atomic(self._ini_path(),
                              bookmarks.generate_ini(section))

    # -- lifecycle ---------------------------------------------------
    def start(self) -> bool:
        if self.is_running():
            return True
        if not self._exe or not self._script or not self._script.exists():
            self.last_error = _MISSING
            logger.error("Engine not started: exe=%r script=%r",
                         self._exe, self._script)
            return False

        self._token = self._token_factory()
        argv = [str(self._exe), str(self._script), "/token", self._token]
        try:
            self._proc = self._spawner(
                argv, cwd=str(self._state_dir), **_NO_WINDOW_KWARGS)
        except OSError as exc:
            self.last_error = f"The bookmark engine could not start: {exc}"
            logger.exception("Engine spawn failed")
            self._proc = None
            return False

        atomicio.write_atomic(
            self._pid_path(),
            json.dumps({"pid": self._proc.pid, "token": self._token}))
        self.last_error = None
        return True

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the engine and clear its PID record.

        The record clear is in a finally: a process-control call that raises
        would otherwise leave a record naming a dead pid on disk, which is
        precisely the ambiguity orphan recovery then has to resolve.
        """
        proc, self._proc = self._proc, None
        try:
            if proc is None or proc.poll() is not None:
                return
            try:
                proc.terminate()
            except OSError:
                # Already gone between the poll and here. Not an error.
                logger.debug("Engine had already exited before terminate.")
                return
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                # A hung engine still holds a keyboard hook. Killing it is
                # the lesser harm.
                logger.warning("Engine ignored terminate; killing it.")
                try:
                    proc.kill()
                    proc.wait(timeout=timeout)
                except (OSError, subprocess.TimeoutExpired):
                    logger.exception("Engine could not be killed.")
            except OSError:
                logger.exception("Could not wait on the engine process.")
        finally:
            self._clear_pid_record()

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # -- paths -------------------------------------------------------
    def _ini_path(self) -> Path:
        return self._state_dir / paths.engine_ini_file().name

    def _pid_path(self) -> Path:
        return self._state_dir / paths.engine_pid_file().name

    def _clear_pid_record(self) -> None:
        try:
            self._pid_path().unlink()
        except OSError:
            pass
