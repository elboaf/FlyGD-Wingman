from __future__ import annotations

import queue
import shutil
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.node_scenario_worker import (
    NodeScenarioCrash,
    NodeScenarioFailure,
    NodeScenarioTimeout,
    NodeScenarioWorker,
)

WORKER_CJS = r"""
const readline = require('node:readline');

const rl = readline.createInterface({
  input: process.stdin,
  crlfDelay: Infinity,
});

let exitOnNextRequest = null;

function reply(request, fields) {
  process.stdout.write(JSON.stringify(Object.assign({
    id: request.id,
    scenario: request.scenario,
    ok: true,
    duration_ms: 1.5,
    error: '',
    stack: ''
  }, fields)) + '\n');
}

rl.on('line', (line) => {
  const request = JSON.parse(line);

  if (exitOnNextRequest) {
    const pending = exitOnNextRequest;
    exitOnNextRequest = null;
    process.stderr.write(
      'synthetic late EOF after ' + pending.scenario + '\n',
      () => process.exit(pending.code)
    );
    return;
  }

  if (request.scenario === 'echo' || request.scenario === 'echo-after-restart'
      || request.scenario === 'echo-after-mismatch') {
    reply(request, {
      text: request.payload && request.payload.text,
      request_env: process.env.NODE_SCENARIO_REQUEST_ENV || ''
    });
    return;
  }

  if (request.scenario === 'fail') {
    reply(request, {
      ok: false,
      error: 'synthetic failure',
      stack: 'AssertionError [ERR_ASSERTION]: synthetic failure\n    at syntheticScenario (scenario-worker.cjs:42:7)'
    });
    return;
  }

  if (request.scenario === 'timeout') {
    setTimeout(() => {
      reply(request, {
        text: 'too late',
        request_env: process.env.NODE_SCENARIO_REQUEST_ENV || ''
      });
    }, 200);
    return;
  }

  if (request.scenario === 'ok-then-exit-on-next-eof') {
    exitOnNextRequest = {code: 27, scenario: request.scenario};
    reply(request, {});
    return;
  }

  if (request.scenario === 'ok-then-exit-close') {
    process.stdout.write(JSON.stringify({
      id: request.id,
      scenario: request.scenario,
      ok: true,
      duration_ms: 0.5,
      error: '',
      stack: ''
    }) + '\n', () => {
      process.stderr.write('synthetic late exit for ' + request.scenario + '\n', () => {
        process.exit(29);
      });
    });
    return;
  }

  if (request.scenario === 'crash') {
    process.stderr.write('synthetic crash stderr\n');
    process.exit(23);
  }

  if (request.scenario === 'wrong-id') {
    process.stderr.write('synthetic wrong-id stderr\n');
    process.stdout.write(JSON.stringify({
      id: request.id + 1,
      scenario: request.scenario,
      ok: true,
      duration_ms: 0.5,
      error: '',
      stack: ''
    }) + '\n');
    return;
  }

  if (request.scenario === 'bad-schema') {
    process.stderr.write('synthetic schema stderr\n');
    process.stdout.write(JSON.stringify(request.payload.reply) + '\n');
    return;
  }

  if (request.scenario === 'malformed') {
    process.stderr.write('synthetic malformed stderr\n');
    process.stdout.write('{"id":\n');
    return;
  }

  reply(request, {
    ok: false,
    error: 'unknown scenario: ' + request.scenario,
    stack: 'Error: unknown scenario'
  });
});
""".strip()


@pytest.fixture
def node_worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    monkeypatch.setenv("NODE_SCENARIO_REQUEST_ENV", "present")
    script = tmp_path / "scenario-worker.cjs"
    script.write_text(WORKER_CJS, encoding="utf-8")
    worker = NodeScenarioWorker([node, str(script)], cwd=tmp_path)
    try:
        yield worker
    finally:
        proc = getattr(worker, "_proc", None)
        worker.close()
        worker.close()
        if proc is not None:
            proc.wait(timeout=5)
            assert proc.poll() is not None


def test_real_node_worker_reuses_utf8_process_then_recovers_from_failure_timeout_and_crash(
    node_worker: NodeScenarioWorker,
):
    first = node_worker.request("echo", {"text": "Étiquette 𐐀"})
    first_pid = node_worker._proc.pid

    assert first["ok"] is True
    assert first["text"] == "Étiquette 𐐀"
    assert first["request_env"] == "present"
    assert first["id"] == 1

    with pytest.raises(NodeScenarioFailure, match="synthetic failure") as failure:
        node_worker.request("fail")
    assert failure.value.scenario == "fail"
    assert "synthetic failure" in failure.value.stack

    timeout_proc = node_worker._proc
    with pytest.raises(NodeScenarioTimeout, match="timeout") as timed_out:
        node_worker.request("timeout", timeout=0.05)
    assert timed_out.value.scenario == "timeout"
    assert timeout_proc is not None
    timeout_proc.wait(timeout=5)
    assert timeout_proc.poll() is not None

    with pytest.raises(NodeScenarioCrash, match="crash") as crashed:
        node_worker.request("crash")
    assert crashed.value.scenario == "crash"
    assert "synthetic crash stderr" in crashed.value.stderr

    restarted = node_worker.request("echo-after-restart", {"text": "fresh"})
    final_proc = node_worker._proc

    assert restarted["ok"] is True
    assert restarted["text"] == "fresh"
    assert restarted["id"] == 5
    assert final_proc is not None
    assert final_proc.pid != first_pid

    node_worker.close()
    node_worker.close()
    final_proc.wait(timeout=5)
    assert final_proc.poll() is not None


def test_immediate_request_after_ok_reports_late_eof_context_and_recovers(
    node_worker: NodeScenarioWorker,
):
    successful_scenario = "ok-then-exit-on-next-eof"
    reply = node_worker.request(successful_scenario)
    exited = node_worker._proc

    assert reply["ok"] is True
    assert exited is not None

    with pytest.raises(NodeScenarioCrash, match=r"status 27") as crashed:
        node_worker.request("echo-after-restart", {"text": "not silently restarted"})

    rendered = str(crashed.value)
    assert crashed.value.scenario == "echo-after-restart"
    assert "before replying to the next request" in rendered
    assert f"for {successful_scenario!r} (request 1)" in rendered
    assert "synthetic late EOF after ok-then-exit-on-next-eof" in crashed.value.stderr
    assert node_worker._proc is None

    recovered = node_worker.request("echo-after-restart", {"text": "fresh"})

    assert recovered["text"] == "fresh"
    assert recovered["id"] == 3
    assert node_worker._proc is not None
    assert node_worker._proc.pid != exited.pid


# A child cannot observe the parent's broken write to trigger its own exit.
# Script the pipe and reap instead of coupling this branch to a timer race.
class _BreakOnSecondWrite:
    def __init__(self) -> None:
        self._writes = 0

    def write(self, text: str) -> int:
        self._writes += 1
        if self._writes == 2:
            raise BrokenPipeError("synthetic broken pipe")
        return len(text)

    def flush(self) -> None:
        return None


class _ExitWhenReaped:
    def __init__(self) -> None:
        self.stdin = _BreakOnSecondWrite()
        self._status: int | None = None
        self.wait_timeouts: list[float | None] = []

    def poll(self) -> int | None:
        return self._status

    def wait(self, timeout: float | None = None) -> int:
        self.wait_timeouts.append(timeout)
        if self._status is None:
            self._status = 28
        return self._status

    def terminate(self) -> None:
        self._status = -15

    def kill(self) -> None:
        self._status = -9


def test_broken_write_after_ok_reaps_status_and_prior_context(tmp_path: Path):
    replies: queue.Queue[object] = queue.Queue()
    replies.put(
        {
            "id": 1,
            "scenario": "successful-before-broken-write",
            "ok": True,
            "duration_ms": 0.5,
            "error": "",
            "stack": "",
        }
    )
    proc = _ExitWhenReaped()
    state = SimpleNamespace(
        proc=proc,
        replies=replies,
        stderr_tail=SimpleNamespace(text=lambda: "synthetic late broken-write stderr"),
        stdout_thread=threading.Thread(),
        stderr_thread=threading.Thread(),
        last_successful_scenario=None,
        last_successful_request_id=None,
    )
    worker = NodeScenarioWorker(["unused"], cwd=tmp_path)
    worker._state = state
    worker._proc = proc

    first = worker.request("successful-before-broken-write")

    assert first["ok"] is True
    with pytest.raises(NodeScenarioCrash, match=r"status 28") as crashed:
        worker.request("request-with-broken-write")

    rendered = str(crashed.value)
    assert crashed.value.scenario == "request-with-broken-write"
    assert "while sending the next request" in rendered
    assert "for 'successful-before-broken-write' (request 1)" in rendered
    assert crashed.value.stderr == "synthetic late broken-write stderr"
    assert len(proc.wait_timeouts) == 1
    assert proc.wait_timeouts[0] is not None
    assert 0 < proc.wait_timeouts[0] <= 0.25
    assert worker._proc is None


def test_close_reports_exit_after_last_ok_reply_and_worker_remains_recoverable(
    node_worker: NodeScenarioWorker,
):
    reply = node_worker.request("ok-then-exit-close")

    assert reply["ok"] is True
    with pytest.raises(NodeScenarioCrash, match="status 29") as crashed:
        node_worker.close()

    assert crashed.value.scenario == "ok-then-exit-close"
    assert "before close" in str(crashed.value)
    assert "for 'ok-then-exit-close' (request 1)" in str(crashed.value)
    assert "synthetic late exit for ok-then-exit-close" in crashed.value.stderr
    assert node_worker._proc is None

    recovered = node_worker.request("echo-after-restart", {"text": "fresh"})

    assert recovered["text"] == "fresh"
    assert recovered["id"] == 2


def test_failure_renders_javascript_stack_in_pytest_diagnostics(node_worker):
    with pytest.raises(NodeScenarioFailure) as failure:
        node_worker.request("fail")

    rendered = str(failure.getrepr(style="short"))
    assert "synthetic failure" in rendered
    assert "at syntheticScenario (scenario-worker.cjs:42:7)" in rendered


def test_reply_ids_cannot_cross_requests_or_poison_the_next_restart(
    node_worker: NodeScenarioWorker,
):
    first = node_worker.request("echo", {"text": "before mismatch"})

    assert first["id"] == 1
    assert first["text"] == "before mismatch"

    with pytest.raises(NodeScenarioCrash, match="id") as crashed:
        node_worker.request("wrong-id")
    assert crashed.value.scenario == "wrong-id"
    assert "synthetic wrong-id stderr" in crashed.value.stderr

    restarted = node_worker.request(
        "echo-after-mismatch", {"text": "fresh after mismatch"}
    )

    assert restarted["ok"] is True
    assert restarted["text"] == "fresh after mismatch"
    assert restarted["id"] == 3


@pytest.mark.parametrize(
    "reply",
    [
        None,
        {},
        {
            "id": 2,
            "scenario": "bad-schema",
            "ok": "true",
            "duration_ms": 1.0,
            "error": "",
            "stack": "",
        },
        {
            "id": 2,
            "scenario": "bad-schema",
            "ok": True,
            "duration_ms": True,
            "error": "",
            "stack": "",
        },
    ],
    ids=["not-object", "missing-fields", "wrong-ok-type", "wrong-duration-type"],
)
def test_invalid_reply_schema_discards_process_with_context_and_restarts(
    node_worker: NodeScenarioWorker, reply
):
    node_worker.request("echo")
    process = node_worker._proc

    with pytest.raises(NodeScenarioCrash, match="reply") as crashed:
        node_worker.request("bad-schema", {"reply": reply})

    assert crashed.value.scenario == "bad-schema"
    assert "synthetic schema stderr" in crashed.value.stderr
    assert process.poll() is not None
    assert node_worker._proc is None
    restarted = node_worker.request("echo-after-restart", {"text": "fresh"})
    assert restarted["text"] == "fresh"
    assert restarted["id"] == 3
    assert node_worker._proc.pid != process.pid


def test_startup_failure_names_the_calling_scenario(tmp_path: Path):
    worker = NodeScenarioWorker([str(tmp_path / "missing-node-binary")], cwd=tmp_path)

    with pytest.raises(NodeScenarioCrash, match="startup") as crashed:
        worker.request("startup-failure")

    assert crashed.value.scenario == "startup-failure"
    assert worker._proc is None
    worker.close()


def test_malformed_reply_crashes_the_worker_and_the_next_request_restarts_cleanly(
    node_worker: NodeScenarioWorker,
):
    first = node_worker.request("echo", {"text": "before malformed"})
    malformed_proc = node_worker._proc

    assert first["id"] == 1
    assert first["text"] == "before malformed"

    with pytest.raises(NodeScenarioCrash, match="malformed") as crashed:
        node_worker.request("malformed")

    assert crashed.value.scenario == "malformed"
    assert "synthetic malformed stderr" in crashed.value.stderr
    assert malformed_proc is not None
    malformed_proc.wait(timeout=5)
    assert malformed_proc.poll() is not None

    restarted = node_worker.request("echo-after-restart", {"text": "after malformed"})

    assert restarted["ok"] is True
    assert restarted["text"] == "after malformed"
    assert restarted["id"] == 3
    assert node_worker._proc is not None
    assert node_worker._proc.pid != malformed_proc.pid
