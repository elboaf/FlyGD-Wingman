from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from collections import deque
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

_STOP_TIMEOUT_S = 1.0
_KILL_TIMEOUT_S = 1.0
_STDERR_TAIL_LINES = 40
_STDERR_LINE_LIMIT = 400

_EOF = object()


class NodeScenarioError(RuntimeError):
    """Base class for scenario protocol failures."""

    def __init__(
        self,
        scenario: str,
        message: str,
        *,
        stderr: str = "",
        stack: str = "",
        reply: Mapping[str, object] | None = None,
    ) -> None:
        self.scenario = scenario
        self.stderr = stderr
        self.stack = stack
        self.reply = dict(reply) if reply is not None else None
        detail = f"Node scenario {scenario!r}: {message}"
        if stderr:
            detail = f"{detail} [stderr: {stderr}]"
        super().__init__(detail)


class NodeScenarioFailure(NodeScenarioError):
    """The worker returned an assertion-style failure."""


class NodeScenarioTimeout(NodeScenarioError):
    """The worker did not answer before the request timeout."""


class NodeScenarioCrash(NodeScenarioError):
    """The worker process exited or broke the request/reply contract."""


class _ProtocolError(RuntimeError):
    pass


class _StderrTail:
    """Keep only the most recent stderr lines so diagnostics stay bounded."""

    def __init__(self, *, max_lines: int = _STDERR_TAIL_LINES) -> None:
        self._lines: deque[str] = deque(maxlen=max_lines)
        self._lock = threading.Lock()

    def append(self, line: str) -> None:
        clipped = line.rstrip("\r\n")
        if len(clipped) > _STDERR_LINE_LIMIT:
            clipped = clipped[: _STDERR_LINE_LIMIT - 1] + "…"
        with self._lock:
            self._lines.append(clipped)

    def text(self) -> str:
        with self._lock:
            return "\n".join(line for line in self._lines if line)


@dataclass
class _ProcessState:
    proc: subprocess.Popen[str]
    replies: queue.Queue[object]
    stderr_tail: _StderrTail
    stdout_thread: threading.Thread
    stderr_thread: threading.Thread
    stdout_started: threading.Event
    stderr_started: threading.Event


class NodeScenarioWorker:
    def __init__(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        startup_timeout: float = 10.0,
    ) -> None:
        self._argv = tuple(str(part) for part in argv)
        self._cwd = Path(cwd)
        self._startup_timeout = float(startup_timeout)
        self._request_lock = threading.Lock()
        self._next_id = 1
        self._state: _ProcessState | None = None
        self._proc: subprocess.Popen[str] | None = None

    def request(
        self,
        scenario: str,
        payload: Mapping[str, object] | None = None,
        *,
        timeout: float = 60.0,
    ) -> dict[str, object]:
        with self._request_lock:
            request_id = self._next_id
            self._next_id += 1
            state = self._ensure_started()
            request = {"id": request_id, "scenario": scenario, "payload": payload}
            try:
                state.proc.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
                state.proc.stdin.flush()
            except (AttributeError, BrokenPipeError, OSError, ValueError) as error:
                stderr = self._discard_process(reason="request write failed")
                raise NodeScenarioCrash(
                    scenario,
                    f"worker crash while sending request: {error}",
                    stderr=stderr,
                ) from error
            deadline = time.monotonic() + float(timeout)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    stderr = self._discard_process(reason="request timed out")
                    raise NodeScenarioTimeout(
                        scenario,
                        f"timeout after {timeout:.2f}s",
                        stderr=stderr,
                    )
                try:
                    item = state.replies.get(timeout=remaining)
                except queue.Empty:
                    stderr = self._discard_process(reason="request timed out")
                    raise NodeScenarioTimeout(
                        scenario,
                        f"timeout after {timeout:.2f}s",
                        stderr=stderr,
                    )
                if item is _EOF:
                    stderr = self._discard_process(
                        reason="worker exited before replying"
                    )
                    raise NodeScenarioCrash(
                        scenario,
                        "worker crash before reply",
                        stderr=stderr,
                    )
                if isinstance(item, _ProtocolError):
                    stderr = self._discard_process(reason="malformed reply")
                    raise NodeScenarioCrash(
                        scenario,
                        str(item),
                        stderr=stderr,
                    )
                reply = self._validate_reply(item)
                if reply["id"] != request_id:
                    stderr = self._discard_process(reason="reply id mismatch")
                    raise NodeScenarioCrash(
                        scenario,
                        f"reply id mismatch: expected {request_id}, got {reply['id']}",
                        stderr=stderr,
                        reply=reply,
                    )
                if reply["scenario"] != scenario:
                    stderr = self._discard_process(reason="reply scenario mismatch")
                    raise NodeScenarioCrash(
                        scenario,
                        "reply scenario mismatch",
                        stderr=stderr,
                        reply=reply,
                    )
                if reply["ok"]:
                    return reply
                raise NodeScenarioFailure(
                    scenario,
                    str(reply["error"] or "worker reported failure"),
                    stderr=self._stderr_text(state),
                    stack=str(reply["stack"]),
                    reply=reply,
                )

    def close(self) -> None:
        with self._request_lock:
            self._discard_process(reason="close requested")

    def _ensure_started(self) -> _ProcessState:
        state = self._state
        if state is not None and state.proc.poll() is None:
            return state
        if state is not None:
            self._discard_process(reason="stale process state")
        replies: queue.Queue[object] = queue.Queue()
        stderr_tail = _StderrTail()
        stdout_started = threading.Event()
        stderr_started = threading.Event()
        try:
            proc = subprocess.Popen(
                self._argv,
                cwd=self._cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                shell=False,
            )
        except OSError as error:
            raise NodeScenarioCrash(
                "<startup>", f"worker crash on startup: {error}"
            ) from error
        stdout_thread = threading.Thread(
            target=self._stdout_reader,
            args=(proc, replies, stdout_started),
            name="node-scenario-stdout",
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=self._stderr_reader,
            args=(proc, stderr_tail, stderr_started),
            name="node-scenario-stderr",
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()
        deadline = time.monotonic() + self._startup_timeout
        for event in (stdout_started, stderr_started):
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not event.wait(remaining):
                state = _ProcessState(
                    proc=proc,
                    replies=replies,
                    stderr_tail=stderr_tail,
                    stdout_thread=stdout_thread,
                    stderr_thread=stderr_thread,
                    stdout_started=stdout_started,
                    stderr_started=stderr_started,
                )
                self._state = state
                self._proc = proc
                stderr = self._discard_process(reason="reader startup timeout")
                raise NodeScenarioCrash(
                    "<startup>",
                    f"worker crash during startup timeout after {self._startup_timeout:.2f}s",
                    stderr=stderr,
                )
        state = _ProcessState(
            proc=proc,
            replies=replies,
            stderr_tail=stderr_tail,
            stdout_thread=stdout_thread,
            stderr_thread=stderr_thread,
            stdout_started=stdout_started,
            stderr_started=stderr_started,
        )
        self._state = state
        self._proc = proc
        return state

    def _discard_process(self, *, reason: str) -> str:
        state, self._state, self._proc = self._state, None, None
        if state is None:
            return ""
        self._stop_process(state.proc)
        self._join_reader(state.stdout_thread, _STOP_TIMEOUT_S)
        self._join_reader(state.stderr_thread, _STOP_TIMEOUT_S)
        stderr = state.stderr_tail.text()
        if stderr:
            return stderr
        code = state.proc.poll()
        return "" if code is None else f"worker exited with code {code} after {reason}"

    def _stderr_text(self, state: _ProcessState) -> str:
        return state.stderr_tail.text()

    def _stop_process(self, proc: subprocess.Popen[str]) -> None:
        if proc.poll() is not None:
            return
        try:
            proc.terminate()
        except ProcessLookupError:
            return
        except OSError:
            self._kill_process(proc)
            return
        try:
            proc.wait(timeout=_STOP_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            self._kill_process(proc)
        except OSError:
            self._kill_process(proc)

    def _kill_process(self, proc: subprocess.Popen[str]) -> None:
        if proc.poll() is not None:
            return
        try:
            proc.kill()
            proc.wait(timeout=_KILL_TIMEOUT_S)
        except (OSError, ProcessLookupError, subprocess.TimeoutExpired):
            return

    def _join_reader(self, thread: threading.Thread, timeout: float) -> None:
        if thread.is_alive():
            thread.join(timeout=timeout)

    def _stdout_reader(
        self,
        proc: subprocess.Popen[str],
        replies: queue.Queue[object],
        started: threading.Event,
    ) -> None:
        started.set()
        stream = proc.stdout
        if stream is None:
            replies.put(_ProtocolError("stdout pipe was not created"))
            return
        try:
            while True:
                line = stream.readline()
                if line == "":
                    replies.put(_EOF)
                    return
                try:
                    payload = json.loads(line)
                except ValueError as error:
                    replies.put(_ProtocolError(f"malformed reply JSON: {error}"))
                    continue
                replies.put(payload)
        finally:
            with suppress(OSError):
                stream.close()

    def _stderr_reader(
        self,
        proc: subprocess.Popen[str],
        stderr_tail: _StderrTail,
        started: threading.Event,
    ) -> None:
        started.set()
        stream = proc.stderr
        if stream is None:
            return
        try:
            while True:
                line = stream.readline()
                if line == "":
                    return
                stderr_tail.append(line)
        finally:
            with suppress(OSError):
                stream.close()

    def _validate_reply(self, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise _ProtocolError("reply was not a JSON object")
        required = {
            "id": int,
            "scenario": str,
            "ok": bool,
            "duration_ms": (int, float),
            "error": str,
            "stack": str,
        }
        for key, expected in required.items():
            if key not in payload:
                raise _ProtocolError(f"reply missing {key!r}")
            value = payload[key]
            if key == "duration_ms":
                if isinstance(value, bool) or not isinstance(value, expected):
                    raise _ProtocolError("reply field 'duration_ms' had the wrong type")
                continue
            if not isinstance(value, expected):
                raise _ProtocolError(f"reply field {key!r} had the wrong type")
        return dict(payload)
