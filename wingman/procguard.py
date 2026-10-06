"""One child process, guarded: spawn, job object, pid record, orphan
recovery (issue #317; extracted from hotkeys.py, which now composes it --
the engine's own test files are the regression net).

Windows-only at runtime, imports and tests cleanly on Linux: ctypes only
inside the job factory, subprocess seams injected. Every consumer gives
the same three promises the engine made:

- the child dies with us (kernel Job object, kill-on-close), so a crashed
  Wingman cannot leave the child holding global state forever;
- the child is always findable (pid record with a run token), so recovery
  can tell our orphan from a reused pid or someone else's process;
- the record never outlives the knowledge in it (cleared in stop()'s
  finally, resolved before every start).
"""

import json
import logging
import subprocess
import sys
import uuid
from pathlib import Path, PureWindowsPath

from . import atomicio, procid

logger = logging.getLogger(__name__)

# CREATE_NO_WINDOW doesn't exist off Windows, and the tests inject a fake
# spawner -- same shape as stitch.py:27 and library.py:19.
NO_WINDOW_KWARGS = (
    {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
)

# KILL_ON_JOB_CLOSE: when the last handle to the job goes away -- which the
# kernel does even for a terminated process -- every process in the job is
# killed. This is the belt to stop()'s braces. Value from
# JOBOBJECT_EXTENDED_LIMIT_INFORMATION, winbase.h.
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


def default_job():
    """A kernel job object to bind the child's life to ours, or None.

    Wingman holds the job handle for the child's whole lifetime: if this
    process dies, the kernel empties the job, and the child -- which may
    hold a global keyboard hook (the engine) or a pinned stream window
    (the mirror) -- dies with it. None off Windows and on any failure:
    callers fall back to stop()-only cleanup.
    """
    import ctypes

    kernel32 = ctypes.windll.kernel32

    class _BasicLimitInfo(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.POINTER(ctypes.c_uint64)),
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class _ExtendedLimitInfo(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimitInfo),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    try:
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            return None
        info = _ExtendedLimitInfo()
        info.BasicLimitInformation.LimitFlags = (
            0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        if not kernel32.SetInformationJobObject(
            handle,
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            kernel32.CloseHandle(handle)
            return None
        return KernelJob(kernel32, handle)
    except Exception:
        # A job is belt-and-braces on top of stop(); any failure here must
        # never block a start.
        logger.warning("Job object unavailable; falling back to stop().", exc_info=True)
        return None


class KernelJob:
    """The ctypes-bound job handle, narrowed to the two operations used."""

    def __init__(self, kernel32, handle):
        self._kernel32 = kernel32
        self._handle = handle

    def assign(self, handle):
        """Put the child in the job. False is non-fatal (fall back)."""
        return bool(self._kernel32.AssignProcessToJobObject(self._handle, handle))

    def close(self):
        self._kernel32.CloseHandle(self._handle)


class ProcGuard:
    """Own one child process: spawn with a run token, bind to a job,
    record the pid, recover orphans, stop cleanly.

    A record left behind by a crashed session is deliberately not cleaned
    up except through recover_orphan(): this class can only reason about a
    process it spawned itself, so deciding whether an on-disk record names
    a live child, a dead one, or a pid Windows has since reused belongs to
    recovery, which verifies the process image and the run token before
    terminating anything.
    """

    def __init__(
        self,
        exe,
        state_dir,
        *,
        pid_name,
        image_name,
        spawner=subprocess.Popen,
        token_factory=lambda: uuid.uuid4().hex,
        job_factory=default_job,
        procid_module=procid,
        no_window_kwargs=None,
    ):
        self._exe = exe
        self._state_dir = Path(state_dir)
        self._pid_name = pid_name
        self._image_name = image_name.lower()
        self._spawner = spawner
        self._token_factory = token_factory
        self._job_factory = job_factory
        self.procid = procid_module
        # Read-at-construction, not at-call: consumers re-export the
        # constant and tests patch the re-export (hotkeys._NO_WINDOW_KWARGS);
        # binding here is what makes their patch reach the spawn.
        self._no_window_kwargs = (
            NO_WINDOW_KWARGS if no_window_kwargs is None else no_window_kwargs
        )
        self._proc = None
        self._token = None
        self._job = None
        self.last_error = None

    # -- lifecycle ---------------------------------------------------
    def launch(
        self, argv_builder, *, required_paths=(), missing_message, failure_message=None
    ) -> bool:
        """Start the child: recover any orphan, check requirements, spawn
        with a fresh run token, bind the job, write the record.

        ``argv_builder`` receives the token and returns the full command
        line -- the engine passes its script, the mirror its flags, and
        neither is this class's business. ``missing_message`` is the
        last_error for a missing exe/requirement; ``failure_message`` (a
        short "could not start" sentence) prefixes spawn and record-write
        errors. Every path that used to leave a child running unrecorded
        stops the child instead: a live process nobody can address is
        worse than the one disruptive kill.
        """
        if self.is_running():
            return True
        self.recover_orphan()
        # A None entry (the engine's "no script configured") is missing
        # by definition -- Path(None) must never be evaluated.
        missing = [str(p) for p in required_paths if p is None or not Path(p).exists()]
        if not self._exe or missing:
            self.last_error = missing_message
            logger.error("Child not started: exe=%r missing=%s", self._exe, missing)
            return False

        self._token = self._token_factory()
        argv = argv_builder(self._token)
        fail = failure_message or missing_message.split(".")[0]
        try:
            self._proc = self._spawner(
                argv, cwd=str(self._state_dir), **self._no_window_kwargs
            )
        except OSError as exc:
            self.last_error = f"{fail}: {exc}"
            logger.exception("Child spawn failed")
            self._proc = None
            return False

        # Bind the child's life to ours before anything else can fail:
        # every path after this point that used to leave it running now at
        # worst leaves it in a job the kernel empties when we die. A None
        # or failed assignment falls back to the stop()-only cleanup,
        # never blocks the start.
        try:
            self._job = self._job_factory()
            # The child's process handle is Popen._handle on Windows. No
            # public `handle` exists on any Python 3 -- that spelling died
            # with py2, so reading it raised on EVERY real launch and the
            # job silently never bound while the test doubles (which had
            # invented .handle) kept the tests green. Field log
            # 2026-10-06: one "Job object setup failed" per start since
            # the extraction shipped. AttributeError still covers doubles
            # that carry no handle attribute at all.
            if self._job is not None and not self._job.assign(self._proc._handle):
                logger.warning("Could not assign the child to its job object.")
                self._job.close()
                self._job = None
        except (OSError, AttributeError):
            logger.warning(
                "Job object setup failed; falling back to stop().", exc_info=True
            )
            self._job = None

        try:
            atomicio.write_atomic(
                self.pid_path(),
                json.dumps({"pid": self._proc.pid, "token": self._token}),
            )
        except OSError as exc:
            # The record is what makes this process findable: without it,
            # is_running() would still report the child alive (self._proc
            # is a real, running Popen) while orphan recovery -- and this
            # session's own stop() on a later attempt -- has no PID to act
            # on. Stop the child now rather than leave it running
            # unrecorded; that also clears self._proc, so is_running()
            # agrees with the False this returns.
            self.last_error = f"{fail}: {exc}"
            logger.exception("Could not persist the child PID record")
            self.stop()
            return False
        self.last_error = None
        return True

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the child and clear its PID record.

        The record clear is in a finally: a process-control call that
        raises would otherwise leave a record naming a dead pid on disk,
        which is precisely the ambiguity orphan recovery then has to
        resolve.
        """
        proc, self._proc = self._proc, None
        job, self._job = self._job, None
        try:
            if proc is None or proc.poll() is not None:
                return
            try:
                proc.terminate()
            except ProcessLookupError:
                # Genuinely gone between the poll above and here.
                logger.debug("Child had already exited before terminate.")
                return
            except OSError:
                # terminate() FAILED -- the process is still there. Fall
                # through to the kill escalation rather than reporting a
                # clean stop while it still holds global state.
                logger.warning("terminate() failed; escalating to kill.")
                try:
                    proc.kill()
                    proc.wait(timeout=timeout)
                except (OSError, subprocess.TimeoutExpired):
                    logger.exception("Child could not be killed.")
                return
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                # A hung child still holds whatever it held. Killing it is
                # the lesser harm.
                logger.warning("Child ignored terminate; killing it.")
                try:
                    proc.kill()
                    proc.wait(timeout=timeout)
                except (OSError, subprocess.TimeoutExpired):
                    logger.exception("Child could not be killed.")
            except OSError:
                logger.exception("Could not wait on the child process.")
        finally:
            if job is not None:
                try:
                    job.close()
                except OSError:
                    # Closing a dead handle must not report a failed stop;
                    # the kill-on-close still fired when the kernel tore
                    # the handle down with us.
                    logger.debug("Child job handle already closed.")
            self._clear_pid_record()

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # -- orphan recovery ----------------------------------------------
    def recover_orphan(self) -> bool:
        """Terminate a child left behind by a crashed Wingman.

        Identity is the image name AND the run token from the command
        line. The PID alone is not identity -- Windows reuses PIDs and
        this runs after an unclean shutdown -- and the image alone is not
        either, because a general interpreter (AutoHotkey) or a common exe
        name could be running someone else's workload. Anything that fails
        either check is treated as a stale record and discarded rather
        than killed. The one exception is a failed *lookup* (procid
        .describe raising, or a failed kill): there we do not know the
        record is stale, so it is kept for the next start rather than
        thrown away.

        This only ever runs at the next start. The job object binds the
        child to this process -- a dead Wingman takes the child with it --
        so recovery is mainly a fallback for records left by sessions that
        predate the job or where the job could not be created; clean
        shutdown remains what covers the common case.
        """
        try:
            # atomicio.write_atomic writes UTF-8; say so on the way back
            # in rather than inheriting the locale's codec.
            record = json.loads(self.pid_path().read_text(encoding="utf-8"))
            pid = int(record["pid"])
            token = str(record["token"])
        except (OSError, ValueError, KeyError, TypeError):
            self._clear_pid_record()
            return False

        try:
            info = self.procid.describe(pid)
        except Exception:
            # describe() feeds a code path that must never prevent the
            # child starting. We could not determine liveness/identity,
            # so leave the record for the next start rather than discard
            # it -- if we do not know it is stale, deleting it would lose
            # our only handle on a still-live orphan.
            logger.exception("Orphan lookup failed; leaving the record alone.")
            return False
        if not info:
            self._clear_pid_record()
            return False

        image_ok = (
            PureWindowsPath(info.get("image") or "").name.lower() == self._image_name
        )
        token_ok = token and token in (info.get("cmdline") or "")
        if not (image_ok and token_ok):
            logger.info("PID %s is not our child; leaving it alone.", pid)
            self._clear_pid_record()
            return False

        logger.warning("Terminating orphaned child %s", pid)
        try:
            killed = self.procid.terminate(pid)
        except Exception:
            logger.exception("Could not terminate orphaned child %s", pid)
            return False
        if not killed:
            # Keep the record: it is the only handle for trying again.
            logger.error("Orphaned child %s could not be terminated.", pid)
            return False
        self._clear_pid_record()
        return True

    # -- paths ---------------------------------------------------------
    def pid_path(self) -> Path:
        return self._state_dir / self._pid_name

    def exe_path(self):
        """The configured exe, for consumers building argv (this class
        owns the record and the job; the argv shape is the caller's)."""
        return self._exe

    def _clear_pid_record(self) -> None:
        try:
            self.pid_path().unlink()
        except OSError as exc:
            # Non-fatal on purpose: every caller is a path that must reach
            # its own outcome whether or not the record went away, and the
            # next recover_orphan clears it anyway once the pid is dead. It
            # is logged rather than passed over because a record that
            # repeatedly cannot be removed means something holds it -- an
            # AV scanner, a permissions change -- and that is invisible
            # from the outside otherwise.
            logger.warning("Could not remove the child PID record: %s", exc)
