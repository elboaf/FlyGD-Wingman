"""A serialized HTTP owner and an independent monotonic expiry owner.

Only the nonblocking semantic host mailbox is callable on expiry. Health is a
cached value read by the controller's separate delivery path, never a callback.
One instance has one lifetime: close admission before joining, and never replace
it while either retained daemon owner is live.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, Protocol

from ..telemetry.model import ClientSessionId
from .client import MAX_RETRY_AFTER, ErrorCode, Failure, FetchResult, Success, Unchanged
from .credentials import validate_token
from .model import (
    Snapshot,
    normalize_base_url,
    normalize_character_name,
    normalize_map_identifier,
)

POLL_INTERVAL = 2.0
MAX_BACKOFF = 60.0
MetadataPublisher = Callable[[int, Mapping[ClientSessionId, str | None]], None]
WorkerStatus = Literal[
    "off",
    "setup_incomplete",
    "previews_unavailable",
    "connecting",
    "connected",
    "stale",
    "error",
    "stopped",
    "worker_failed",
]


class SnapshotClient(Protocol):
    def fetch(
        self, base: str, map: str, token: str, etag: str | None = None
    ) -> FetchResult: ...


@dataclass(frozen=True)
class WorkerConfig:
    enabled: bool = False
    previews_enabled: bool = False
    host_available: bool = False
    base_url: str = ""
    map_identifier: str = ""
    token: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        # Incomplete setup is ordinary; nonempty fields must already be usable.
        if self.base_url:
            object.__setattr__(self, "base_url", normalize_base_url(self.base_url))
        if self.map_identifier:
            object.__setattr__(
                self, "map_identifier", normalize_map_identifier(self.map_identifier)
            )
        if self.token is not None:
            validate_token(self.token)

    @property
    def connection_ready(self) -> bool:
        return bool(self.base_url and self.map_identifier and self.token)

    @property
    def automatic_ready(self) -> bool:
        return (
            self.connection_ready
            and self.enabled
            and self.previews_enabled
            and self.host_available
        )


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
    test_result: Literal["success"] | ErrorCode | None
    last_success_monotonic: float | None
    next_request_monotonic: float | None
    previewed: int
    matched: int
    available: int
    stale: int


class WandererWorker:
    def __init__(
        self,
        client: SnapshotClient,
        publish: MetadataPublisher,
        *,
        clock: Callable[[], float] = time.monotonic,
        condition: threading.Condition | None = None,
        thread_factory: Callable[..., threading.Thread] = threading.Thread,
    ) -> None:
        self._client = client
        self._publish: MetadataPublisher | None = publish
        self._clock = clock
        self._condition = condition if condition is not None else threading.Condition()
        self._thread_factory = thread_factory
        self._request_thread: threading.Thread | None = None
        self._scheduler_thread: threading.Thread | None = None
        self._closed = self._faulted = False
        self._config = WorkerConfig()
        self._generation = 0
        self._sessions: dict[ClientSessionId, str | None] = {}
        self._published: dict[ClientSessionId, str | None] = {}
        self._snapshot: Snapshot | None = None
        self._etag: str | None = None
        self._error: ErrorCode | None = None
        self._last_success: float | None = None
        self._paused = False
        self._failures = 0
        self._next_allowed = 0.0
        self._in_flight = False
        self._test_in_flight = False
        self._test_pending = False
        self._test_result: Literal["success"] | ErrorCode | None = None
        self._health = self._state_locked(self._clock())

    def configure(self, config: WorkerConfig, *, generation: int) -> bool:
        """Admit an externally fenced generation, without I/O or joins.

        Controller calls host.set_metadata_generation(generation) FIRST, then
        this method. Repeated identical configuration at the same generation is
        harmless; a changed configuration needs a strictly larger generation.
        Readiness/credential changes invalidate snapshots and queued Tests, but
        never cancel/replace a live owner or bypass that lane's rate restriction.
        """
        with self._condition:
            if self._closed or generation < self._generation:
                return False
            if generation == self._generation:
                return config == self._config
            same_connection = (
                config.base_url == self._config.base_url
                and config.map_identifier == self._config.map_identifier
                and config.token == self._config.token
            )
            # Readiness flaps are not renewed authorization. Only a changed
            # connection or successful explicit Test can undo an auth pause.
            self._paused = self._paused and same_connection
            self._error = self._error if self._paused else None
            self._generation, self._config = generation, config
            self._snapshot = self._etag = None
            self._last_success = self._test_result = None
            self._test_pending = False
            self._failures = 0
            # A new host generation has cleared its mailbox even if text matches.
            self._published.clear()
            if config.automatic_ready and not self._start_locked():
                return False
            self._refresh_locked()
            return True

    def set_sessions(self, sessions: Iterable[ClientSessionId]) -> None:
        """Cheap detached roster handoff; no settings/credential/native work.

        The host admits only created primary previews and clears departed labels
        itself. Never publish old-session clears into a new session's HWND.
        """
        normalized = {}
        for session in sessions:
            try:
                normalized[session] = normalize_character_name(session.character)
            except ValueError:
                normalized[session] = None
        with self._condition:
            if self._closed:
                return
            self._sessions = normalized
            self._published = {
                s: v for s, v in self._published.items() if s in normalized
            }
            self._refresh_locked()

    def test_connection(self) -> bool:
        """Queue at most one explicit request, including while automatic use is Off.

        Returns admission, not the HTTP outcome. Read test_result from state()
        off the scheduler. A queued Test waits behind both in-flight HTTP and
        cadence/backoff; successful Test unpauses automatic work only if enabled.
        """
        with self._condition:
            if (
                self._closed
                or not self._config.connection_ready
                or self._test_pending
                or self._test_in_flight
            ):
                return False
            if not self._start_locked():
                return False
            self._test_pending = True
            self._test_result = None
            self._refresh_locked()
            return True

    def state(self) -> WorkerState:
        with self._condition:
            return self._health

    def close_admission(self) -> None:
        """Detach before any joins; already captured mailbox calls are host-fenced.

        The controller closes host metadata admission before this method on
        shutdown. We do not wait on an entered callback or entered socket read.
        """
        with self._condition:
            self._closed = True
            self._publish = None
            self._config = WorkerConfig()
            self._snapshot = self._etag = None
            self._sessions.clear()
            self._published.clear()
            self._test_pending = False
            self._refresh_locked()

    def stop(self, timeout: float = 1.0) -> bool:
        self.close_admission()
        # Real join budget, intentionally independent of injected freshness time.
        deadline = time.monotonic() + max(0.0, timeout)
        for owner in (self._scheduler_thread, self._request_thread):
            if (
                owner is not None
                and owner.ident is not None
                and owner is not threading.current_thread()
            ):
                owner.join(max(0.0, deadline - time.monotonic()))
        return all(
            owner is None or not owner.is_alive()
            for owner in (self._scheduler_thread, self._request_thread)
        )

    def _start_locked(self) -> bool:
        if self._request_thread is not None or self._scheduler_thread is not None:
            return not self._closed
        try:
            self._scheduler_thread = self._thread_factory(
                target=self._run_scheduler, name="wanderer-expiry", daemon=True
            )
            self._request_thread = self._thread_factory(
                target=self._run_requests, name="wanderer-http", daemon=True
            )
            self._scheduler_thread.start()
            self._request_thread.start()
        except Exception:  # noqa: BLE001 — startup must fail closed without external exception text.
            self._fail_locked()
            return False
        return True

    def _fail_locked(self) -> None:
        self._faulted = True
        self.close_admission()

    def _request_due_locked(self) -> float | None:
        if self._closed:
            return None
        if self._test_pending or (self._config.automatic_ready and not self._paused):
            return self._next_allowed
        return None

    def _projection_locked(self, now: float):
        visible = {}
        matched = stale = 0
        deadline = None
        for session, name in self._sessions.items():
            record = self._snapshot.by_name.get(name) if self._snapshot else None
            visible[session] = None
            if record is None:
                continue
            matched += 1
            expires = record.deadline_monotonic
            if expires is not None:
                if expires <= now:
                    stale += 1
                else:
                    deadline = expires if deadline is None else min(deadline, expires)
            if self._config.automatic_ready:
                visible[session] = record.display_at(now)
        return visible, matched, stale, deadline

    def _state_locked(self, now: float) -> WorkerState:
        visible, matched, stale, _ = self._projection_locked(now)
        available = sum(v is not None for v in visible.values())
        if self._faulted:
            status: WorkerStatus = "worker_failed"
        elif self._closed:
            status = "stopped"
        elif self._error is not None:
            status = "error"
        elif self._last_success is not None:
            status = "stale" if stale and not available else "connected"
        elif self._test_pending or self._test_in_flight:
            status = "connecting"
        elif not self._config.enabled:
            status = "off"
        elif not self._config.connection_ready:
            status = "setup_incomplete"
        elif not self._config.automatic_ready:
            status = "previews_unavailable"
        else:
            status = "connecting"
        return WorkerState(
            self._generation,
            self._config.enabled,
            self._config.automatic_ready,
            status,
            self._error,
            self._paused,
            self._in_flight,
            self._test_pending,
            self._test_result,
            self._last_success,
            self._request_due_locked(),
            len(self._sessions),
            matched,
            available,
            stale,
        )

    def _refresh_locked(self) -> None:
        self._health = self._state_locked(self._clock())
        self._condition.notify_all()

    def _run_requests(self) -> None:
        while True:
            with self._condition:
                while not self._closed:
                    due = self._request_due_locked()
                    now = self._clock()
                    if due is not None and due <= now:
                        break
                    self._condition.wait(None if due is None else due - now)
                if self._closed:
                    return
                config, generation = self._config, self._generation
                etag = self._etag
                is_test = self._test_pending
                self._test_pending = False
                self._test_in_flight = is_test
                self._in_flight = True
                self._refresh_locked()
            try:
                result = self._client.fetch(
                    config.base_url, config.map_identifier, config.token, etag
                )
            except Exception:  # noqa: BLE001 — an injected/broken transport cannot leak a token or kill expiry.
                result = Failure("transport_error")
            with self._condition:
                self._in_flight = self._test_in_flight = False
                now = self._clock()
                current = not self._closed and generation == self._generation
                if current:
                    result = self._accept_locked(result, now, is_test)
                # Even superseded requests consume the lane's cadence. A setting
                # edit or queued Test must not let a 429 turn into a request storm.
                delay = POLL_INTERVAL
                if isinstance(result, Failure):
                    if current:
                        self._failures = min(self._failures + 1, 5)
                    delay = max(
                        min(MAX_BACKOFF, POLL_INTERVAL * 2**self._failures),
                        min(MAX_RETRY_AFTER, result.retry_after),
                    )
                self._next_allowed = max(self._next_allowed, now + delay)
                self._refresh_locked()

    def _accept_locked(
        self, result: FetchResult, now: float, is_test: bool
    ) -> FetchResult:
        if isinstance(result, Unchanged) and (
            self._snapshot is None or self._etag != result.etag
        ):
            result = Failure("invalid_response", 304)
        if isinstance(result, Failure):
            self._error = result.code
            if result.authentication_failed:
                # User override: invalidate now, not at the old 15-second expiry.
                self._snapshot = self._etag = None
                self._paused = True
            if is_test:
                self._test_result = result.code
            return result
        if isinstance(result, Success):
            self._snapshot, self._etag = result.snapshot, result.etag
        self._last_success = now
        self._error = None
        self._paused = False
        self._failures = 0
        if is_test:
            self._test_result = "success"
        return result

    def _run_scheduler(self) -> None:
        while True:
            with self._condition:
                if self._closed:
                    return
                now = self._clock()
                visible, _, _, deadline = self._projection_locked(now)
                health = self._state_locked(now)
                if health != self._health:
                    self._health = health
                    self._condition.notify_all()
                updates = {
                    s: v
                    for s, v in visible.items()
                    if s not in self._published or self._published[s] != v
                }
                if not updates:
                    self._condition.wait(
                        None if deadline is None else max(0.0, deadline - now)
                    )
                    continue
                generation = self._generation
                publish = self._publish
                self._published = visible
            # Only a coalescing host mailbox belongs here. No health/UI callbacks,
            # native drawing, HTTP, DPAPI or disk I/O. The host fences captured
            # generations/sessions if configuration/discovery changes in this gap.
            try:
                if publish is not None:
                    publish(generation, MappingProxyType(updates))
            except Exception:  # noqa: BLE001 — a failed mailbox is fatal, never a raw logged exception.
                with self._condition:
                    self._fail_locked()
                return
