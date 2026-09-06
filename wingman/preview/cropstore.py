"""Committed crop authority and a lazy, single-worker settings dispatcher.

The metadata condition never encloses disk I/O or a Future callback. Admission
is the only place the settings lock nests it (settings -> metadata), so a pump
can fence waiting work without waiting for an unrelated settings transaction.
"""

import logging
from collections import OrderedDict, deque
from concurrent.futures import Future
from dataclasses import dataclass, field, replace
from threading import Condition
from time import monotonic

from wingman.telemetry.model import ClientSessionId, RosterSnapshot

from .crops import CropDefinition, CropToken, CropWriteResult, serialize
from .geometry import Rect

RECENT_RESULT_LIMIT = 32
logger = logging.getLogger(__name__)


class _Refused(Exception):
    """Abort the transaction, including its normal-exit save."""


@dataclass
class _Operation:
    token: CropToken
    future: Future = field(default_factory=Future)
    action: str | None = None
    value: object = None
    admitted: bool = False
    result: CropWriteResult | None = None
    geometry_sequence: int = -1


@dataclass
class _Barrier:
    future: Future
    closing: bool = False


@dataclass
class _Geometry:
    generation: int
    sequence: int
    rect: Rect
    deadline: float | None


@dataclass
class _GeometryFlush:
    names: tuple[str, ...]


class CropStore:
    def __init__(
        self,
        update_settings,
        initial,
        *,
        executor_factory,
        debounce_s=1.0,
        flush_primary=None,
    ):
        self._update_settings = update_settings
        self._definitions = dict(initial)
        self._generations = dict.fromkeys(initial, 0)
        self._reserved = dict(self._generations)
        self._executor_factory = executor_factory
        self._executor = None
        self._debounce_s = debounce_s
        self._flush_primary = flush_primary
        self._condition = Condition()
        self._queue = deque()
        self._operations = {}
        self._recent = OrderedDict()
        self._next_id = 0
        self._revision = 0
        self._close_future = None
        self._epoch = None
        self._fenced = True
        self._roster_generation = -1
        self._sessions = {}
        self._dirty = {}
        self._sequences = {}
        self._flush_ok = True

    def open_epoch(self, epoch: int) -> None:
        with self._condition:
            if self._close_future is not None or (
                self._epoch is not None and epoch <= self._epoch
            ):
                return
            self._epoch, self._fenced = epoch, False
            self._roster_generation = -1
            self._sessions = {}
            canceled = self._cancel_stale_locked()
        self._deliver(canceled)

    def observe_roster(self, epoch: int, snapshot: RosterSnapshot) -> None:
        with self._condition:
            if (
                epoch != self._epoch
                or self._fenced
                or snapshot.generation <= self._roster_generation
            ):
                return
            self._roster_generation = snapshot.generation
            self._sessions = {
                client.character: client.session
                for client in snapshot.clients
                if client.character and client.session is not None
            }
            canceled = self._cancel_stale_locked()
        self._deliver(canceled)

    def fence_epoch(self, epoch: int) -> None:
        with self._condition:
            if epoch != self._epoch:
                return
            self._fenced = True
            canceled = self._cancel_stale_locked()
        self._deliver(canceled)

    def _authorized_locked(self, token):
        return token.session is None or (
            token.epoch == self._epoch
            and not self._fenced
            and self._sessions.get(token.name) == token.session
        )

    def _cancel_stale_locked(self):
        canceled = []
        for op in list(self._operations.values()):
            if (
                not op.admitted
                and op.result is None
                and not self._authorized_locked(op.token)
            ):
                canceled.append(
                    (op.future, self._finish_locked(op, "Crop source expired"))
                )
        return canceled

    @staticmethod
    def _deliver(completions):
        for future, result in completions:
            future.set_result(result)

    def begin(
        self, name: str, *, epoch: int, session: ClientSessionId | None
    ) -> CropToken:
        with self._condition:
            if self._close_future is not None:
                raise RuntimeError("Crop store is closed")
            self._next_id += 1
            generation = self._reserved.get(name, 0) + 1
            self._reserved[name] = generation
            token = CropToken(self._next_id, name, epoch, generation, session)
            operation = _Operation(token)
            dirty = self._dirty.get(name)
            # A movement not yet committed when selection starts must still
            # win if its debounce finishes before the later put is admitted.
            operation.geometry_sequence = (
                dirty.sequence - 1 if dirty else self._sequences.get(name, -1)
            )
            # Cancellation is admission-aware through cancel(token), not through
            # Future.cancel(), which cannot describe an admitted disk write.
            operation.future.set_running_or_notify_cancel()
            self._operations[token.operation_id] = operation
            self._revision += 1
            return token

    def put(
        self, token: CropToken, definition: CropDefinition
    ) -> Future[CropWriteResult]:
        return self._submit(token, "put", definition)

    def set_enabled(self, token: CropToken, enabled: bool) -> Future[CropWriteResult]:
        return self._submit(token, "enabled", enabled)

    def remove(self, token: CropToken) -> Future[CropWriteResult]:
        return self._submit(token, "remove", None)

    def _submit(self, token, action, value):
        with self._condition:
            operation = self._operation(token)
            if operation.action is None and operation.result is None:
                operation.action, operation.value = action, value
                self._enqueue_due_locked()
                self._queue.append(operation)
                self._start_locked()
            return operation.future

    def _operation(self, token):
        operation = self._operations.get(token.operation_id)
        if operation is None or operation.token != token:
            raise ValueError("Unknown crop operation")
        return operation

    def cancel(self, token: CropToken) -> bool:
        with self._condition:
            operation = self._operation(token)
            if operation.admitted or operation.result is not None:
                return False
            result = self._finish_locked(operation, "Crop operation canceled")
        operation.future.set_result(result)
        return True

    def record_geometry(
        self, name: str, generation: int, sequence: int, rect: Rect
    ) -> None:
        """Record only current, enabled geometry; sequences increase per name.

        A reservation is deliberately irrelevant here. The old window remains
        authoritative until the replacement actually saves successfully.
        """
        with self._condition:
            definition = self._definitions.get(name)
            if (
                self._close_future is not None
                or definition is None
                or not definition.enabled
                or self._generations[name] != generation
                or sequence <= self._sequences.get(name, -1)
            ):
                return
            self._sequences[name] = sequence
            self._dirty[name] = _Geometry(
                generation, sequence, rect, monotonic() + self._debounce_s
            )
            self._start_locked()

    def snapshot(self) -> dict:
        with self._condition:
            return {
                "revision": self._revision,
                "definitions": serialize(self._definitions),
                "generations": dict(self._generations),
                "operations": {
                    key: {
                        "operation_id": key,
                        "name": op.token.name,
                        "pending": op.result is None,
                        "applied": op.result.applied if op.result else False,
                        "persisted": op.result.persisted if op.result else False,
                        "error": op.result.error if op.result else None,
                        "revision": op.result.revision if op.result else None,
                    }
                    for key, op in self._operations.items()
                },
            }

    def drain(self) -> Future[bool]:
        """Flush earlier work; False reports geometry/primary failures since the
        previous barrier. Definition outcomes have their own result futures.
        """
        with self._condition:
            if self._close_future is not None:
                return self._close_future
            future = Future()
            future.set_running_or_notify_cancel()
            idle = self._executor is None and self._flush_primary is None
            if not idle:
                self._queue.append(_Barrier(future))
                self._start_locked()
        if idle:
            future.set_result(True)
        return future

    def close(self) -> Future[bool]:
        """Finish queued configuration, cancel unadmitted source/selection work,
        flush geometry, and request executor shutdown without a self-join.
        """
        with self._condition:
            if self._close_future is not None:
                return self._close_future
            future = self._close_future = Future()
            future.set_running_or_notify_cancel()
            self._fenced = True
            canceled = []
            for op in list(self._operations.values()):
                if (
                    not op.admitted
                    and op.result is None
                    and (op.action is None or op.token.session is not None)
                ):
                    canceled.append(
                        (op.future, self._finish_locked(op, "Crop store closed"))
                    )
        self._deliver(canceled)
        with self._condition:
            idle = self._executor is None and self._flush_primary is None
            if not idle:
                self._queue.append(_Barrier(future, closing=True))
                self._start_locked()
        if idle:
            future.set_result(True)
        return future

    def _start_locked(self):
        if self._executor is None:
            self._executor = self._executor_factory()
            self._executor.submit(self._run)
        self._condition.notify()

    def _finish_locked(self, operation, error=None):
        self._revision += 1
        result = CropWriteResult(
            operation.token, error is None, error is None, error, self._revision
        )
        operation.result = result
        self._recent[operation.token.operation_id] = None
        while len(self._recent) > RECENT_RESULT_LIMIT:
            key, _ = self._recent.popitem(last=False)
            del self._operations[key]
        return result

    def _enqueue_due_locked(self):
        now = monotonic()
        names = tuple(
            name
            for name, delta in self._dirty.items()
            if delta.deadline is not None and delta.deadline <= now
        )
        if names:
            for name in names:
                self._dirty[name].deadline = None
            self._queue.append(_GeometryFlush(names))

    def _run(self):
        while True:
            with self._condition:
                self._enqueue_due_locked()
                while not self._queue:
                    deadlines = [
                        delta.deadline
                        for delta in self._dirty.values()
                        if delta.deadline is not None
                    ]
                    timeout = (
                        max(0, min(deadlines) - monotonic()) if deadlines else None
                    )
                    self._condition.wait(timeout)
                    self._enqueue_due_locked()
                item = self._queue.popleft()
            if isinstance(item, _Barrier):
                # Resolve dirty names here, not when the barrier was queued:
                # an earlier replacement may have rebased their generations.
                with self._condition:
                    names = tuple(self._dirty)
                self._flush_geometry(names)
                try:
                    if self._flush_primary is not None:
                        self._flush_primary()
                except Exception:
                    # A failing external flush must resolve shutdown, not strand it.
                    logger.exception("Could not flush primary preview layouts")
                    self._flush_ok = False
                ok, self._flush_ok = self._flush_ok, True
                if item.closing:
                    # This is the executor's own worker. Joining it would fail
                    # (and waiting for a second submitted job would deadlock).
                    self._executor.shutdown(wait=False)
                item.future.set_result(ok)
                if item.closing:
                    return
            elif isinstance(item, _GeometryFlush):
                self._flush_geometry(item.names)
            else:
                self._write(item)

    def _flush_geometry(self, names):
        for name in names:
            delta = None
            try:
                with self._update_settings() as live:
                    with self._condition:
                        delta = self._dirty.get(name)
                        previous = self._definitions.get(name)
                        if (
                            delta is None
                            or previous is None
                            or not previous.enabled
                            or delta.generation != self._generations[name]
                        ):
                            raise _Refused("Geometry no longer current")
                        definition = replace(previous, window=delta.rect)
                    crops = dict(live["preview"].get("crops", {}))
                    crops.update(serialize({name: definition}))
                    live["preview"]["crops"] = crops
            except _Refused:
                continue
            except Exception:
                # Retain dirty geometry for a later drain, without a hot retry loop.
                logger.exception("Could not persist crop geometry for %s", name)
                self._flush_ok = False
                with self._condition:
                    if delta is not None and self._dirty.get(name) is delta:
                        delta.deadline = None
                continue
            with self._condition:
                self._definitions[name] = definition
                self._revision += 1
                if self._dirty.get(name) is delta:
                    del self._dirty[name]

    def _write(self, operation):
        error = None
        try:
            with self._update_settings() as live:
                with self._condition:
                    if operation.result is not None:
                        raise _Refused("Crop operation canceled")
                    if not self._authorized_locked(operation.token):
                        raise _Refused("Crop source expired")
                    name = operation.token.name
                    previous = self._definitions.get(name)
                    if operation.action == "put":
                        definition = operation.value
                        if (
                            previous is not None
                            and previous.enabled
                            and self._sequences.get(name, -1)
                            > operation.geometry_sequence
                        ):
                            definition = replace(definition, window=previous.window)
                    elif operation.action == "enabled":
                        if previous is None:
                            raise _Refused("No saved crop for this character")
                        definition = replace(previous, enabled=operation.value)
                    else:
                        definition = None
                    geometry = self._dirty.get(name)
                    if definition is not None and geometry is not None:
                        definition = replace(definition, window=geometry.rect)
                    operation.admitted = True
                crops = dict(live["preview"].get("crops", {}))
                if definition is None:
                    crops.pop(name, None)
                else:
                    crops.update(serialize({name: definition}))
                live["preview"]["crops"] = crops
        except Exception as exc:  # noqa: BLE001 -- failed persistence must resolve its receipt, not kill the worker.
            error = str(exc) or type(exc).__name__
        with self._condition:
            if operation.result is not None:
                return
            if error is None:
                if definition is None:
                    self._definitions.pop(name, None)
                else:
                    self._definitions[name] = definition
                self._generations[name] = operation.token.generation
                pending = self._dirty.get(name)
                if pending is not None:
                    if (
                        definition is None
                        or not definition.enabled
                        or pending is geometry
                    ):
                        del self._dirty[name]
                    else:
                        # Movement arriving during I/O belongs to the replacement
                        # only after success. Failure leaves its old authority.
                        pending.generation = operation.token.generation
            result = self._finish_locked(operation, error)
        operation.future.set_result(result)
