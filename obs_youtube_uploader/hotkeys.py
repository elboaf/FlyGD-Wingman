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
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath

from . import atomicio, bookmarks, paths, procid

logger = logging.getLogger(__name__)

# The engine republishes every 2s (111unified.ahk:77). Three missed ticks
# is a deliberate margin: one missed write on a busy machine is normal, a
# sustained gap means it is alive but not working.
STALE_AFTER_S = 6.0

# CREATE_NO_WINDOW doesn't exist off Windows, and the tests inject a fake
# spawner -- same shape as stitch.py:27 and library.py:19.
_NO_WINDOW_KWARGS = (
    {"creationflags": subprocess.CREATE_NO_WINDOW}
    if sys.platform == "win32" else {}
)

_MISSING = ("The bookmark engine is missing from this installation. "
            "Reinstall FlyGD Wingman to restore it.")

# Basename match, not a substring: a folder merely containing "autohotkey"
# (e.g. AutoHotkeyBackup\notepad.exe) must not look like the engine.
_ENGINE_IMAGE_NAME = "autohotkeyu64.exe"

# The only operations the channel carries. Adding to this list should be a
# deliberate decision: the channel exists because two GUI buttons had no
# other route, not as a general RPC mechanism.
COMMANDS = frozenset({"set_root", "clear_root"})


@dataclass
class EngineStatus:
    """What the UI renders. `state` is authoritative; the values are only
    populated when state == "running"."""
    state: str = "off"
    sig: str | None = None
    root: str | None = None
    next_num: str | None = None
    next_alpha: str | None = None
    # "" | "home" | "active". The standalone GUI's Root Mode readout
    # (111unified.ahk:208,214). Absent from an older engine's status file, and
    # its absence must NOT force the whole status to stale -- an engine
    # binary that predates this field is degraded, not broken.
    root_mode: str = ""
    failed_binds: list = field(default_factory=list)
    consumed_seq: int = 0
    last_error: str | None = None


def _text(value) -> str | None:
    """Coerce a status value for display, or None if it is empty.

    These reach a label; a dict or list from a corrupt file would otherwise
    be rendered as its repr. bool is excluded deliberately -- str(True) is
    "True", which would render as a root system named True.
    """
    if value is None or isinstance(value, (dict, list, bool)):
        return None
    text = str(value).strip()
    return text or None


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
        self._seq = 0
        self.last_error: str | None = None

    # -- config ------------------------------------------------------
    def apply(self, section: dict) -> None:
        """Regenerate the INI the engine reads.

        The engine picks this up on its own 10s timer, so there is no need
        to restart it and lose in-flight state (root system, used slots).
        """
        atomicio.write_atomic(self._ini_path(),
                              bookmarks.generate_ini(section))

    # -- commands ------------------------------------------------------
    def sync_sequence(self) -> None:
        """Adopt the sequence already on disk.

        Called after start(). Without it a restarted Wingman would resume
        from zero while a higher-numbered command file remained, and every
        command would be ignored as already-consumed until the counter
        caught up.
        """
        self._seq = 0
        try:
            # decode_ini_bytes, not read_text(): the engine is AutoHotkey
            # and IniWrite produces UTF-16 LE with a BOM on a Unicode
            # build (bookmarks.decode_ini_bytes documents the three
            # encodings this file turns up in). read_text() has no
            # encoding, so it used the locale default -- UTF-8 on Linux,
            # where a BOM decodes to U+FEFF and the lstrip below removes
            # it, but cp1252 on Windows, where the same bytes decode to
            # "ï»¿", nothing is stripped, the first line reads
            # "ï»¿[Command]" and no section ever matches. Wingman only
            # ships on Windows, so this was broken wherever it actually
            # runs: after a restart the engine resumed from zero and
            # ignored every command until the counter caught up, exactly
            # as the docstring above warns.
            raw = self._command_path().read_bytes()
            text = bookmarks.decode_ini_bytes(raw).lstrip("﻿")
            in_command = False
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("[") and stripped.endswith("]"):
                    in_command = stripped[1:-1].strip().lower() == "command"
                    continue
                if not in_command:
                    continue
                key, _, value = stripped.partition("=")
                if key.strip() == "Seq":
                    # Clamped: a negative sequence would make
                    # `consumed >= self._seq` true for every command and
                    # defeat the unconsumed-command guard outright.
                    self._seq = max(0, int(value.strip()))
                    return
        except (OSError, ValueError):
            self._seq = 0

    def pending_command(self, now: float | None = None) -> int | None:
        """The sequence awaiting acknowledgement, or None."""
        if not self._seq:
            return None
        consumed = self.status(enabled=True, now=now).consumed_seq
        return None if consumed >= self._seq else self._seq

    def send_command(self, name: str, argument: str = "",
                     now: float | None = None) -> bool:
        """Publish one operation for the engine to execute.

        Refuses while a previous command is unacknowledged: the file holds
        one slot and the engine polls every 2s, so overwriting would
        silently discard the earlier action.
        """
        if name not in COMMANDS:
            logger.error("Refusing unknown engine command %r", name)
            return False
        if not self.is_running():
            return False
        if self.pending_command(now=now) is not None:
            return False

        next_seq = self._seq + 1
        # INI, and sanitised: the argument is free text the user typed and
        # a newline in it would otherwise add a key to the section.
        body = ("[Command]\r\n"
                f"Seq={next_seq}\r\n"
                f"Name={name}\r\n"
                f"Argument={bookmarks.sanitise(argument)}\r\n")
        try:
            atomicio.write_atomic(self._command_path(), body)
        except OSError:
            # Advancing the counter without a file on disk would leave
            # pending_command() waiting forever on a command nothing can
            # acknowledge, refusing every later command for the session.
            logger.exception("Could not publish engine command %r", name)
            return False
        self._seq = next_seq
        return True

    # -- lifecycle ---------------------------------------------------
    def start(self) -> bool:
        if self.is_running():
            return True
        self.recover_orphan()
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

        try:
            atomicio.write_atomic(
                self._pid_path(),
                json.dumps({"pid": self._proc.pid, "token": self._token}))
        except OSError as exc:
            # The record is what makes this process findable: without it,
            # is_running() would still report the engine alive (self._proc
            # is a real, running Popen) while orphan recovery -- and this
            # session's own stop() on a later attempt -- has no PID to act
            # on. A live keyboard hook nobody can address is worse than the
            # one disruptive kill here, so stop() the child now rather than
            # leave it running unrecorded; that also clears self._proc, so
            # is_running() agrees with the False this returns.
            self.last_error = f"The bookmark engine could not start: {exc}"
            logger.exception("Could not persist engine PID record")
            self.stop()
            return False
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
            except ProcessLookupError:
                # Genuinely gone between the poll above and here.
                logger.debug("Engine had already exited before terminate.")
                return
            except OSError:
                # terminate() FAILED -- the process is still there. Fall
                # through to the kill escalation rather than reporting a
                # clean stop while a keyboard hook is still registered.
                logger.warning("terminate() failed; escalating to kill.")
                try:
                    proc.kill()
                    proc.wait(timeout=timeout)
                except (OSError, subprocess.TimeoutExpired):
                    logger.exception("Engine could not be killed.")
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

    def status(self, enabled: bool, now: float | None = None) -> EngineStatus:
        """Report engine state, driven by liveness rather than file contents.

        The status file outlives the process that wrote it. Reading values
        from it without first establishing that the engine is alive is how
        a dead root system gets displayed as the current one.

        consumed_seq is 0 in every state but "running". That can only make a
        command look still-pending, never falsely acknowledged, so it fails
        in the safe direction: the effect is that the action buttons stay
        disabled through a stale window, which is correct anyway, since a
        command to a non-responding engine should not be sent.
        """
        if not enabled:
            return EngineStatus(state="off")
        if not self.is_running():
            return EngineStatus(state="stopped", last_error=self.last_error)

        now = time.time() if now is None else now
        try:
            raw = json.loads(self._status_path().read_text(encoding="utf-8"))
            written = float(raw["written"])
        except (OSError, ValueError, KeyError, TypeError):
            return EngineStatus(state="stale")
        if now - written > STALE_AFTER_S:
            return EngineStatus(state="stale")

        failed = raw.get("failed_binds")
        if not isinstance(failed, list):
            # A wrong-typed field means the document is not trustworthy, and
            # there is no reason to believe `root` while disbelieving this.
            # Reporting [] would be worse than reporting nothing: it says
            # "every hotkey registered fine", which is exactly what we do
            # not know.
            logger.warning("Engine status has a malformed failed_binds.")
            return EngineStatus(state="stale")

        try:
            # As deliberately guarded as failed_binds above: a non-numeric
            # seq (string, list, dict) would otherwise raise out of status()
            # into pending_command, _push_eve_status, and get_bookmarks.
            consumed_seq = int(raw.get("seq") or 0)
        except (TypeError, ValueError):
            logger.warning("Engine status has a malformed seq.")
            return EngineStatus(state="stale")

        return EngineStatus(
            state="running",
            sig=_text(raw.get("sig")),
            root=_text(raw.get("root")),
            next_num=_text(raw.get("next_num")),
            next_alpha=_text(raw.get("next_alpha")),
            root_mode=_text(raw.get("root_mode")) or "",
            failed_binds=[str(b) for b in failed],
            consumed_seq=consumed_seq,
        )

    def recover_orphan(self) -> bool:
        """Terminate an engine left behind by a crashed Wingman.

        Identity is the image name AND the run token from the command line.
        The PID alone is not identity -- Windows reuses PIDs and this runs
        after an unclean shutdown -- and the image alone is not either,
        because the bundled interpreter could be running someone else's
        script. Anything that fails either check is treated as a stale
        record and discarded rather than killed. The one exception is a
        failed *lookup* (procid.describe raising, or a failed kill): there
        we do not know the record is stale, so it is kept for the next
        start rather than thrown away.

        Note this only ever runs at the next start. Neither this nor
        #SingleInstance Force helps a user who closes Wingman and never
        reopens it; clean shutdown is what covers the common case.
        """
        try:
            # atomicio.write_atomic writes UTF-8; say so on the way back
            # in rather than inheriting the locale's codec. The record is
            # ASCII today (a pid and a hex token) so this is not currently
            # a bug -- it is the same asymmetry that made sync_sequence
            # above fail on Windows, closed before it becomes one.
            record = json.loads(self._pid_path().read_text(encoding="utf-8"))
            pid = int(record["pid"])
            token = str(record["token"])
        except (OSError, ValueError, KeyError, TypeError):
            self._clear_pid_record()
            return False

        try:
            info = procid.describe(pid)
        except Exception:
            # describe() feeds a code path that must never prevent the
            # engine starting. We could not determine liveness/identity,
            # so leave the record for the next start rather than discard
            # it -- if we do not know it is stale, deleting it would lose
            # our only handle on a still-live orphan.
            logger.exception("Orphan lookup failed; leaving the record alone.")
            return False
        if not info:
            self._clear_pid_record()
            return False

        image_ok = PureWindowsPath(info.get("image") or "").name.lower() == _ENGINE_IMAGE_NAME
        token_ok = token and token in (info.get("cmdline") or "")
        if not (image_ok and token_ok):
            logger.info("PID %s is not our engine; leaving it alone.", pid)
            self._clear_pid_record()
            return False

        logger.warning("Terminating orphaned engine %s", pid)
        try:
            killed = procid.terminate(pid)
        except Exception:
            logger.exception("Could not terminate orphaned engine %s", pid)
            return False
        if not killed:
            # Keep the record: it is the only handle for trying again.
            logger.error("Orphaned engine %s could not be terminated.", pid)
            return False
        self._clear_pid_record()
        return True

    # -- paths -------------------------------------------------------
    def _ini_path(self) -> Path:
        return self._state_dir / paths.engine_ini_file().name

    def _pid_path(self) -> Path:
        return self._state_dir / paths.engine_pid_file().name

    def _status_path(self) -> Path:
        return self._state_dir / paths.engine_status_file().name

    def _command_path(self) -> Path:
        return self._state_dir / paths.engine_command_file().name

    def _clear_pid_record(self) -> None:
        try:
            self._pid_path().unlink()
        except OSError:
            pass
