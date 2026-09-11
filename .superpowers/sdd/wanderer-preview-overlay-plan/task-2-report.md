# Task 2 implementation report

## Scope and authority

Worked only in `/mnt/c/dev/flygd-wingman/.worktrees/wanderer-overlay`, starting at
`e0eb28e3` (Task 1). Read AGENTS, Task 2 brief, global plan, Task 1 report and the
approved sibling design. Read the deployed Wanderer documentation and executing
serializer/controller using `git show 2ddff24516c27ecde7b175991fcd74d608a35932:...`
in `/home/tng/workspace/wanderer`; its checkout HEAD was not used as authority.
No plan/ledger, UI/host/controller, settings, dependencies or version changes.

Implementation commits:

- `6ee37323` — make hidden-system fixture upstream-coherent.
- `51bddd09` — bounded single-attempt HTTPS client.
- `d40a8722` — serialized polling and independent expiry owners.
- `7869ba7d` — early auth-denial fence and explicit Test activity in cached health.

Final Python/test verification below is against **`7869ba7d`**. This report is a
subsequent documentation-only commit.

## Discovery and scoped self-review

- Per-read socket timeouts do not bound a trickling HTTP body, chunk-size line or
  trailer. A deadline-aware raw reader below `HTTPResponse` buffering enforces
  the response budget, including headers/chunk framing.
- A 401/403 is known before its error body finishes. Waiting for the body would
  violate immediate auth invalidation. The client now has an optional **early
  auth signal**, and the worker binds it to the captured generation. It only
  updates cached state and wakes expiry; it is not a publication/UI callback.
- Host/previews readiness flaps must not undo an auth pause for the same
  base/map/token. Only a changed connection or a successful explicit Test does.
- HTTP and expiry cannot share an execution owner. The scheduler invokes only
  the nonblocking semantic mailbox; all network/JSON parsing lives on HTTP.
  Health is immutable cached state, read externally, with no delivery callback.
- Generation fencing must happen on the host **before** worker configuration.
  Configuration and roster handoffs do no persistence, DPAPI or network I/O.
- A 304 without a retained snapshot, or with another ETag, is an error. It cannot
  establish successful communication or manufacture freshness.
- The supplied fixture had contradictory map visibility for one system in a
  single snapshot. Hidden Pilot now uses real raw system **30002187 / Amarr**;
  visible First Pilot remains **30000142 / Jita / HOME**. Only the affected
  fixture and literal model expectations changed.

Scoped local `polish-core --fix` was performed against the Task 2 diff only;
subagents and broad review were explicitly forbidden. Reviewed transport cleanup,
error/privacy boundaries, lock ownership, configuration/auth/roster races and
shutdown. Applied Ruff layout/import fixes and a clarifying projection return
annotation. Correctness discoveries were reproduced with RED tests before fixes;
additional regression/mutation checks are recorded below. No known unresolved
Task 2 correctness finding remains.

## Exact client API

`wingman.wanderer.client`:

```python
ErrorCode = Literal[
    "invalid_configuration", "invalid_response", "unsupported_version",
    "redirect_refused", "timeout", "tls_error", "transport_error",
    "invalid_request", "invalid_token", "forbidden", "scope_forbidden",
    "wrong_map", "disabled", "subscription_required", "map_not_found",
    "not_acceptable", "rate_limited", "invalid_snapshot", "service_unavailable",
]

@dataclass(frozen=True)
class Success:
    snapshot: Snapshot
    etag: str

@dataclass(frozen=True)
class Unchanged:
    etag: str

@dataclass(frozen=True)
class Failure:
    code: ErrorCode
    status: int | None = None
    retry_after: float = 0.0

    @property
    def authentication_failed(self) -> bool: ...  # status in (401, 403)

FetchResult = Success | Unchanged | Failure
AuthFailureCallback = Callable[[Failure], None]
ConnectionFactory = Callable[[str, int, float], http.client.HTTPConnection]

class WandererClient:
    def __init__(
        self, *,
        connection_factory: ConnectionFactory = _connection,
        clock: Callable[[], float] = time.monotonic,
    ) -> None: ...

    def fetch(
        self, base: str, map: str, token: str, etag: str | None = None, *,
        on_authentication_failure: AuthFailureCallback | None = None,
    ) -> FetchResult: ...
```

The optional keyword is the only extension to the brief's four-argument fetch.
**Worker client doubles must accept this keyword.** The worker supplies it; the
controller must not supply a UI callback. It runs synchronously on the HTTP owner
as soon as complete 401/403 headers are parsed, before error-body reads. It carries
only a safe `Failure` (`invalid_token` or coarse `forbidden`, status and bounded
retry delay). Final return may refine 403 into `wrong_map`, `disabled`, etc. Slow,
oversized, malformed or failing error bodies cannot undo that denial.

Transport behavior:

- Production factory creates a certificate-verified `HTTPSConnection` with
  hostname checking. URL normalization is always HTTPS-only, even with a test
  seam. Loopback HTTP tests inject a connection; no HTTP configuration escape.
- One GET, no retries, redirects, proxy discovery, cookies, query credentials or
  ESI calls. The canonical application path prefix is retained.
- `CONNECT_TIMEOUT=5.0`, `READ_TIMEOUT=5.0`, `BODY_DEADLINE=10.0`. The latter starts
  before reading response headers and bounds every subsequent raw receive,
  including chunk framing; each receive uses min(read timeout, remaining budget).
- Success body is capped at 1 MiB; errors at 2 KiB, with one overflow-detection
  byte and fixed-size buffering. Length/framing/encoding mismatches reject.
- Success requires one version `1`, JSON content type and one bounded deployed
  weak ETag. A 200 ETag must agree with the opaque body revision. A 304 must agree
  with the supplied conditional; it returns no new snapshot.
- Known error codes are status-bound and exact-schema parsed. Unknown/non-JSON
  bodies use safe coarse status classifications; no raw body/message/exception
  or token escapes. Cleanup failures do not replace a safe result.
- Deployed delta-seconds Retry-After only, bounded to `MAX_RETRY_AFTER=300.0`.
  Invalid/date/list/overlong hints become zero; the worker still enforces cadence.

## Exact worker/configuration/publication APIs

`wingman.wanderer.worker` imports `ClientSessionId` from `telemetry.model` and no
UI/preview/host module. ClientSessionId retains all four identity fields:
`hwnd`, `pid`, `character`, `first_seen_generation`.

```python
MetadataPublisher = Callable[[int, Mapping[ClientSessionId, str | None]], None]
WorkerStatus = Literal[
    "off", "setup_incomplete", "previews_unavailable", "connecting",
    "connected", "stale", "error", "stopped", "worker_failed",
]

class SnapshotClient(Protocol):
    def fetch(
        self, base: str, map: str, token: str, etag: str | None = None, *,
        on_authentication_failure: AuthFailureCallback | None = None,
    ) -> FetchResult: ...

@dataclass(frozen=True)
class WorkerConfig:
    enabled: bool = False
    previews_enabled: bool = False
    host_available: bool = False
    base_url: str = ""
    map_identifier: str = ""
    token: str | None = field(default=None, repr=False)

    @property
    def connection_ready(self) -> bool: ...
    @property
    def automatic_ready(self) -> bool: ...

@dataclass(frozen=True)
class WorkerState:
    generation: int
    enabled: bool
    automatic_ready: bool
    status: WorkerStatus
    error_code: ErrorCode | None
    paused: bool
    in_flight: bool
    test_pending: bool
    test_in_flight: bool
    test_result: Literal["success"] | ErrorCode | None
    last_success_monotonic: float | None
    next_request_monotonic: float | None
    previewed: int
    matched: int
    available: int
    stale: int

class WandererWorker:
    def __init__(
        self, client: SnapshotClient, publish: MetadataPublisher, *,
        clock: Callable[[], float] = time.monotonic,
        condition: threading.Condition | None = None,
        thread_factory: Callable[..., threading.Thread] = threading.Thread,
    ) -> None: ...
    def configure(self, config: WorkerConfig, *, generation: int) -> bool: ...
    def set_sessions(self, sessions: Iterable[ClientSessionId]) -> None: ...
    def test_connection(self) -> bool: ...
    def state(self) -> WorkerState: ...
    def close_admission(self) -> None: ...
    def stop(self, timeout: float = 1.0) -> bool: ...
```

### Configuration and generation handshake

- Construct one worker for the runtime and retain it across configuration,
  enabled/preview/host readiness changes and Test actions. Owners start lazily
  when automatic readiness or explicit Test first requires them; they park when
  gated off. Do not use terminal `stop()` as a normal toggle operation.
- Worker starts at generation 0. Controller owns a strictly increasing generation
  counter (normally first configuration is 1). After successful persistence and
  credential handling, **first** call `host.set_metadata_generation(generation)`,
  **then** `worker.configure(config, generation=generation)`. No publication for
  that generation can precede configure. `state().generation` is the admitted
  stable value. Same generation + identical config is an idempotent no-op;
  lower generation or changed config at the same generation returns false.
- `configure` normalizes no disk state: WorkerConfig already canonicalizes
  nonempty URL/map and validates any supplied token through Task 1 primitives.
  Empty URL/map and `token=None` represent incomplete setup. Invalid nonempty
  values raise their existing fixed ValueError/CredentialError at construction.
- `connection_ready` requires canonical base, map and token. `automatic_ready`
  additionally requires enabled, previews_enabled and host_available. Session
  count is not a hidden readiness cap. Configuration changes clear snapshots,
  ETags, previous Test outcome and queued old Test, without overlapping HTTP or
  resetting the retained lane's next-allowed time. Same-connection readiness
  flaps preserve an auth pause. Late final results and early auth signals are
  generation-fenced, including callbacks retained beyond their original fetch.
- WorkerConfig is **Python-only and contains a token** despite repr redaction.
  Never serialize/asdict it to the page. WorkerState contains no credentials,
  raw errors, snapshots or unrelated character roster.

### Host roster and mailbox contract

Wire `publish(generation, updates)` directly to the host semantic metadata ingress
(e.g. `host.submit_metadata`), not to a native window or `_push`/evaluate_js. It
receives a detached read-only mapping of current sessions to system text; `None`
means clear. Only changed session values are published. The scheduler never
calls health delivery, persistence, DPAPI, HTTP or native rendering.

Use `worker.set_sessions(host.metadata_sessions())` initially and hand off the
host's detached session changes through this method. Only successfully created
primary preview sessions belong in that roster. The host callback can also admit
cached availability changes through configure; it must not take persistence
locks or reload DPAPI. Retain a Python-side acknowledged config/token for those
cheap runtime handoffs.

The live roster has no 64-name cap. The worker prunes its metadata cache to the
admitted roster and never emits departed-session clears; the host itself clears
removed/replaced sessions at discovery admission. The host must drop unknown
sessions and stale generations, including a publication captured immediately
before configure/close. Existing host fencing is the final application guard.

### Test, health, cadence and shutdown

- `test_connection()` is asynchronous **admission**, not the HTTP result. False
  means closed/unready/another Test already pending or executing/start failure.
  True queues at most one explicit one-shot. It works while Off or previews are
  unavailable and never changes enabled. `test_pending` distinguishes a queued
  Test from `test_in_flight`; `in_flight` covers any HTTP request. A queued Test
  waits behind polling and all existing backoff/Retry-After restrictions.
- Read `test_result` off the expiry path. It resets on Test admission/configure,
  becomes `success` or a safe ErrorCode at completion, and is not overwritten by
  subsequent automatic polls. A successful Test unpauses polling only if the
  acknowledged config is automatically ready. Off Test never publishes names.
- State is cached. `previewed` counts current sessions, `matched` counts matching
  snapshot records, `available` counts permitted nonempty secondary lines, and
  `stale` counts expired matching locations. Counts include no unrelated names.
  After explicit Off Test, status may be connected/error while enabled remains
  false; the controller must not infer enablement from health.
- Healthy interval is 2 seconds **after completion** (never faster than required).
  Consecutive failures back off 4, 8, 16, 32, 60, 60... seconds; success resets the
  sequence. Retry-After can only increase delay, capped at 300 seconds. Even a
  superseded request consumes lane cadence and its bounded Retry-After.
- Valid 200 replaces the entire snapshot. Valid 304 retains the identical
  snapshot/deadlines and updates only communication health. Other errors retain
  last-good data only until its original deadlines. 401/403 invalidate cached
  snapshot/ETag at the **header signal**, pause auto work and wake immediate
  clear publication; final error diagnostics may arrive later.
- Before shutdown, close host metadata admission/detach roster notification,
  then `worker.close_admission()`, then `worker.stop(timeout)`. Join uses one real
  monotonic timeout budget across both owners, outside the state lock. Return
  false means at least one owner is alive: retain this worker and **both** thread
  references, do not construct a replacement. Both references remain retained
  even after eventual success. Closed instances never restart; replace only
  after proven completion if the runtime truly needs a new lifetime.
- The publication contract must remain nonblocking. An already entered bad
  callback is not cancellable, but close/state/stop remain nonblocking/bounded
  and retain owners. Callback or partial thread-start failure closes admission
  with safe `worker_failed` health rather than leaking exception text.
- Client and worker clocks must share the same monotonic domain. Production uses
  `time.monotonic` for both; integration tests injecting clocks must do likewise.

## RED / GREEN evidence

All commands below ran from the assigned worktree, using the requested venv.
No sleeps are used for test ordering. Worker tests use real threads/conditions,
manual monotonic time, request queues/events and observed re-parking barriers;
wall-clock waits are only bounded test-failure guards.

### Fixture correction

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync python -m pytest tests/test_wanderer_model.py -k deployed_fixture --basetemp=/tmp/wanderer-task2 -q --tb=line
```

RED: **1 failed, 191 deselected** (Jita versus expected Amarr). After correcting
only the hidden record and its literal expectations:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync python -m pytest tests/test_wanderer_model.py --basetemp=/tmp/wanderer-task2 -q -rs
```

GREEN: **192 passed**.

### Initial transport and worker

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync python -m pytest tests/test_wanderer_client.py --basetemp=/tmp/wanderer-task2 -q --tb=line
```

RED: **61 failed**, missing `wingman.wanderer.client`; raw ephemeral output
`/tmp/pi-bash-5a6c74f0bd55cd1d.log`. Initial GREEN after implementation:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync python -m pytest tests/test_wanderer_client.py tests/test_wanderer_model.py tests/test_wanderer_credentials.py --basetemp=/tmp/wanderer-task2 -q -rs
```

**298 passed** (61 transport + 237 Task 1).

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync python -m pytest tests/test_wanderer_worker.py --basetemp=/tmp/wanderer-task2 -q --tb=line
```

RED: **1 failed, 23 setup errors**, all missing `wingman.wanderer.worker` before
production implementation. Initial GREEN with `-q -rs`: **24 passed**.

### Self-review regressions

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync python -m pytest tests/test_wanderer_worker.py -k auth_pause_survives --basetemp=/tmp/wanderer-task2 -q --tb=short
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync python -m pytest tests/test_wanderer_worker.py -k cached_health_distinguishes --basetemp=/tmp/wanderer-task2 -q --tb=short
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync python -m pytest tests/test_wanderer_client.py tests/test_wanderer_worker.py -k 'auth_signal_precedes or auth_header_signal' --basetemp=/tmp/wanderer-task2 -q --tb=short
```

RED results respectively: **1 failed, 24 deselected** (readiness flap restarted
HTTP); **1 failed, 30 deselected** (missing Test activity field); **5 failed,
95 deselected** (no early auth signal/callback). Their fixes and all regressions
were GREEN together:

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync python -m pytest tests/test_wanderer_client.py tests/test_wanderer_worker.py --basetemp=/tmp/wanderer-task2 -q -rs
```

**100 passed** (65 client + 35 worker).

Additional regression coverage includes successful empty replacement, nearest
per-session deadlines, 91-session projection, no duplicate 304 publication,
queued/executing Test fencing, startup failure and both owners simultaneously
blocked across timed-out shutdown.

Two **in-memory-only mutation exercises** proved important negative assertions:
removing final auth cache clearing from `_accept_locked` made the three
`auth_clears_immediately` cases fail (**3 failed, 29 deselected**); replacing a
304 with records renewed to `now + 14` made `expiry_runs_while_next_http_request_is_blocked`
fail on available=2 versus zero (**1 failed, 31 deselected**). Production files
were not modified by these mutation runs. Those counts precede the five early-
auth regression additions; final unchanged production verification follows.

### Final fresh verification at 7869ba7d

```sh
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync ruff check wingman/wanderer tests/test_wanderer_model.py tests/test_wanderer_credentials.py tests/test_wanderer_client.py tests/test_wanderer_worker.py
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync ruff format --check wingman/wanderer tests/test_wanderer_model.py tests/test_wanderer_credentials.py tests/test_wanderer_client.py tests/test_wanderer_worker.py
UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync python -m pytest tests/test_wanderer_model.py tests/test_wanderer_credentials.py tests/test_wanderer_client.py tests/test_wanderer_worker.py tests/test_packaging_completeness.py --basetemp=/tmp/wanderer-task2-final -q -rs
git diff --check e0eb28e3..HEAD
```

Results: Ruff **all checks passed**, **9 files already formatted**; pytest
**425 passed in 8.70s**, no skips; whitespace check exit 0.

Repeated race/lifecycle verification:

```sh
for i in {1..10}; do UV_PROJECT_ENVIRONMENT=/tmp/wingman-wanderer-venv uv run --no-sync python -m pytest tests/test_wanderer_worker.py --basetemp=/tmp/wanderer-task2-stress -q --tb=short || exit; done
```

**10/10 runs passed, 35 tests each** (350 repeated executions, not 350 distinct
new tests). No thread warnings, sleep-based ordering or leaked owners observed.

## Remaining integration/acceptance boundaries

Full pytest remains parent-owned. Windows Python execution, native host/label
integration, frozen DPAPI/font and live Wanderer/EVE acceptance were **NOT RUN**
in this task; the parent may run Windows Python tests separately. Local HTTP and
scripted socket tests are not claims of deployed connectivity or live freshness.
No deployed URL/token was supplied.

The fixed socket connect timeout does not promise cancellation of OS DNS lookup;
the independent expiry owner and retained shutdown ownership cover a request
that outlives its join budget. Host mailbox nonblocking semantics, session and
generation admission remain the explicit Task 3 integration contract. Health
must be read/delivered on a separate controller/UI path, not by adding a callback
to the expiry scheduler. No companion-preview dependency was introduced.

Reviewer focus: early-auth versus final-error generation fences, raw-reader
response deadline, original 304 deadlines, shared Test/poll cadence and the
terminal retained-owner shutdown contract.

Knowledge check for controller/host integration:

1. Why must host generation fencing precede configure rather than follow it?
2. What does the early auth signal do while an error body remains blocked?
3. Why can a successful Off Test report connected without publishing a label?
4. Which two readiness changes must not undo an existing auth pause?
5. What does a false stop() result prohibit even if the other owner has exited?
