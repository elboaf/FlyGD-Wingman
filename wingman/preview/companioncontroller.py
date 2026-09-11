"""One bounded off-pump writer for companion proposals, receipts and geometry.

The metadata condition never protects disk/native/publication calls. Settings
transactions take the settings lock first, briefly recheck admission, then save
without holding metadata. Once admitted, a successful save remains real even if
shutdown or source loss arrives during IO; only native promotion is revocable.
"""

import copy
import logging
import ntpath
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from concurrent.futures import Future
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass, replace
from uuid import uuid4

from .companions import (
    EXECUTABLE_PATH_MAX_CHARS,
    LABEL_MAX_CHARS,
    MAX_DEFINITIONS,
    MAX_ENABLED,
    MAX_SOURCES,
    SOURCE_TTL_SECONDS,
    TITLE_MAX_CHARS,
    WINDOW_CLASS_MAX_CHARS,
    CompanionCommand,
    CompanionDefinition,
    CompanionEvent,
    CompanionSpec,
    CompanionToken,
    GeometryDelta,
    PickerRequest,
    PreparedCompanion,
    RegionSelection,
    SourceBinding,
    bounded_text,
    matching_sources,
    serialize_definitions,
    valid_rect,
    validate_definitions,
    validate_descriptor,
)
from .layout import Rect
from .runtime import PreviewRuntime, RuntimeState

logger = logging.getLogger(__name__)
MAX_OPERATIONS = 32
GEOMETRY_DEBOUNCE = 1.0


@dataclass(frozen=True)
class CompanionPorts:
    update_settings: Callable[[], AbstractContextManager[dict]]
    runtime: PreviewRuntime
    submit_native: Callable[[CompanionCommand], bool]
    publish_state: Callable[[dict], None]


@dataclass
class _Operation:
    receipt: dict
    action: str
    expected: int | None
    proposal: CompanionDefinition | bool | None = None
    binding: SourceBinding | None = None
    token: CompanionToken | None = None
    phase: str = "queued"
    admitted: bool = False
    native: bool = False
    deadline: float = 0.0
    failure: str | None = None


class _Refused(Exception):
    pass


class CompanionController:
    def __init__(self, ports: CompanionPorts, initial: dict, *, available: bool):
        self._ports = ports
        self._available = available
        self._condition = threading.Condition()
        self._definitions = {
            d.id: d for d in validate_definitions(initial.get("definitions"))
        }
        self._enabled = initial.get("enabled") is True
        self._generations = dict.fromkeys(self._definitions, 1)
        self._next_generations = dict(self._generations)
        self._rows = {identity: self._new_row() for identity in self._definitions}
        self._revision = 0
        self._operation_id = 0
        self._operations = OrderedDict()
        self._terminal = OrderedDict()
        self._busy = {}
        self._native_operation = None
        self._jobs = deque()
        self._events = OrderedDict()
        self._status_event = None
        self._geometry = {}
        self._physical = {}
        self._handoff_geometry = {}
        self._sequences = {}
        self._catalog = {}
        self._catalog_until = 0.0
        self._worker = None
        self._done = threading.Event()
        self._worker_failed = False
        self._closed = False
        self._publication_open = True
        self._subscribed = False
        self._publish_dirty = False
        self._shutdown = False
        self._barrier = None
        self._runtime = ports.runtime.snapshot()
        self._runtime_dirty = False
        self._started = False
        self._last_demand = None
        self._reconcile_dirty = False

    @staticmethod
    def _new_row():
        return {
            "binding_revision": 0,
            "status": "waiting",
            "error": None,
            "geometry_error": None,
            "binding": None,
        }

    def _wake_locked(self):
        if self._worker is None:
            self._worker = threading.Thread(
                target=self._run, name="wingman-companions", daemon=True
            )
            self._worker.start()
        self._condition.notify_all()

    def _changed_locked(self):
        self._revision += 1
        self._publish_dirty = True
        self._condition.notify_all()

    def _snapshot_locked(self):
        rows = []
        for definition in self._definitions.values():
            row = serialize_definitions((definition,))[0]
            native = self._rows[definition.id]
            status = native["status"]
            if self._closed:
                status = "stopping"
            elif not self._enabled:
                status = "off"
            elif not definition.enabled:
                status = "disabled"
            elif not self._available or self._runtime.pump == "failed":
                status = "source-unavailable"
            row.update(
                generation=self._generations[definition.id],
                binding_revision=native["binding_revision"],
                status=status,
                error=native["geometry_error"] or native["error"],
                pending_operation_id=self._busy.get(definition.id),
            )
            rows.append(row)
        return {
            "revision": self._revision,
            "runtime": asdict(self._runtime),
            "available": self._available and not self._closed,
            "enabled": self._enabled,
            "limits": {
                "definitions": MAX_DEFINITIONS,
                "enabled": MAX_ENABLED,
                "live_available": MAX_ENABLED,
                "reason": None,
                "label_max_chars": LABEL_MAX_CHARS,
                "title_hint_max_chars": TITLE_MAX_CHARS,
                "last_title_max_chars": TITLE_MAX_CHARS,
                "window_class_max_chars": WINDOW_CLASS_MAX_CHARS,
                "executable_path_max_chars": EXECUTABLE_PATH_MAX_CHARS,
            },
            "rows": rows,
            "operations": copy.deepcopy(
                list(self._terminal.values())
                + [
                    op.receipt
                    for op in self._operations.values()
                    if op.receipt["pending"]
                ]
            ),
        }

    def state(self) -> dict:
        with self._condition:
            self._subscribed = True
            return self._snapshot_locked()

    def start(self) -> None:
        """Seed committed demand only after host/controller composition is bound."""
        with self._condition:
            if self._closed:
                return
            self._started = True
            self._runtime_dirty = True
            self._reconcile_dirty = True
            self._wake_locked()

    def runtime_changed(self, state: RuntimeState) -> None:
        with self._condition:
            if self._done.is_set() or state.revision < self._runtime.revision:
                return
            self._runtime = state
            self._runtime_dirty = True
            self._reconcile_dirty = True
            self._changed_locked()
            self._wake_locked()

    def _refusal_locked(self, error, identity=None):
        return {
            "pending": False,
            "operation_id": None,
            "id": identity,
            "applied": False,
            "persisted": False,
            "error": str(error),
            "revision": self._revision,
        }

    def _reserve_locked(self, action, identity=None, expected=None, *, native=False):
        if self._closed:
            raise _Refused("Companion previews are stopping")
        if len(self._operations) >= MAX_OPERATIONS:
            raise _Refused(
                "Too many companion changes pending; wait for them to finish"
            )
        if identity is None and action in ("edit", "remove", "reset", "enable"):
            raise _Refused("Choose a saved companion")
        if identity is not None:
            if (
                not isinstance(identity, str)
                or identity not in self._definitions
                or type(expected) is not int
                or expected != self._generations[identity]
            ):
                raise _Refused("This companion changed; refresh and try again")
            if identity in self._busy:
                raise _Refused("A change to this companion is already pending")
        elif expected is not None:
            raise _Refused("A new companion cannot have an existing generation")
        if native and (not self._available or self._native_operation is not None):
            raise _Refused(
                "Another source selection is pending"
                if self._native_operation is not None
                else "Companion source capture is unavailable"
            )
        self._operation_id += 1
        receipt = {
            "pending": True,
            "operation_id": self._operation_id,
            "id": identity,
            "applied": False,
            "persisted": False,
            "error": None,
            "revision": self._revision,
        }
        op = _Operation(receipt, action, expected, native=native)
        self._operations[self._operation_id] = op
        if identity is not None:
            self._busy[identity] = self._operation_id
        if native:
            self._native_operation = self._operation_id
        return op

    def _queue_locked(self, op):
        self._jobs.append(op.receipt["operation_id"])
        self._changed_locked()
        op.receipt["revision"] = self._revision
        self._wake_locked()
        return dict(op.receipt)

    def sources(self) -> dict:
        with self._condition:
            try:
                return self._queue_locked(self._reserve_locked("sources", native=True))
            except _Refused as exc:
                return self._refusal_locked(exc)

    def set_master(self, enabled: bool) -> dict:
        with self._condition:
            try:
                if type(enabled) is not bool:
                    raise _Refused("Enabled must be true or false")
                if any(op.action == "master" for op in self._operations.values()):
                    raise _Refused("The companion switch is already being saved")
                op = self._reserve_locked("master")
                op.proposal = enabled
                return self._queue_locked(op)
            except _Refused as exc:
                return self._refusal_locked(exc)

    def _check_enabled_locked(self, identity=None):
        count = sum(d.enabled for d in self._definitions.values() if d.id != identity)
        # Prospective adds/enables reserve a slot without making them committed.
        count += sum(
            isinstance(op.proposal, CompanionDefinition)
            and op.proposal.enabled
            and op.receipt["id"] != identity
            and (
                op.receipt["id"] not in self._definitions
                or not self._definitions[op.receipt["id"]].enabled
            )
            for op in self._operations.values()
            if op.receipt["pending"]
        )
        if count >= MAX_ENABLED:
            raise _Refused(
                f"At most {MAX_ENABLED} companions can be enabled; disable one first"
            )

    def select(
        self,
        id: str | None,
        candidate_token: str,
        mode: str,
        label: str,
        title_mode: str,
        title_hint: str,
        expected_generation: int | None,
    ) -> dict:
        with self._condition:
            try:
                if id is not None and not isinstance(id, str):
                    raise _Refused("Choose a saved companion")
                if (
                    not isinstance(candidate_token, str)
                    or time.monotonic() >= self._catalog_until
                    or candidate_token not in self._catalog
                ):
                    raise _Refused("Source list expired; choose the source again")
                if mode not in ("whole", "region"):
                    raise _Refused("Choose whole window or selected region")
                label = bounded_text(label, LABEL_MAX_CHARS, "Label")
                binding = self._catalog[candidate_token]
                source = self._descriptor(binding, title_mode, title_hint)
                if not matching_sources(source, (binding,)):
                    raise _Refused("Title hint must match the selected window")
                if id is None:
                    if len(self._definitions) >= MAX_DEFINITIONS:
                        raise _Refused(
                            f"At most {MAX_DEFINITIONS} companions can be saved"
                        )
                    self._check_enabled_locked()
                elif id in self._definitions and self._definitions[id].enabled:
                    self._check_enabled_locked(id)
                op = self._reserve_locked(
                    "select", id, expected_generation, native=True
                )
                identity = id or uuid4().hex
                old = self._definitions.get(identity)
                op.receipt["id"] = identity
                self._busy[identity] = op.receipt["operation_id"]
                op.binding = binding
                window = self._physical.get(
                    identity, old.window if old else Rect(100, 100, 320, 210)
                )
                op.proposal = CompanionDefinition(
                    1,
                    identity,
                    label,
                    old.enabled if old else True,
                    mode,
                    source,
                    window,
                    None,
                )
                return self._queue_locked(op)
            except (ValueError, _Refused) as exc:
                return self._refusal_locked(exc, id)

    @staticmethod
    def _descriptor(binding, mode, hint):
        return validate_descriptor(
            {
                "executable_path": binding.executable_path,
                "executable_name": ntpath.basename(binding.executable_path),
                "window_class": binding.window_class,
                "title_hint": hint,
                "title_mode": mode,
                "last_title": binding.title,
            }
        )

    def reselect_region(self, id: str, expected_generation: int) -> dict:
        with self._condition:
            try:
                if not isinstance(id, str):
                    raise _Refused("Choose a saved companion")
                old = self._definitions.get(id)
                binding = self._rows.get(id, {}).get("binding")
                if old is None or old.mode != "region":
                    raise _Refused("Choose a saved region companion")
                if binding is None:
                    # A valid recent explicit chooser snapshot is also sufficient;
                    # the pump verifies it again before opening a picker.
                    matches = (
                        matching_sources(old.source, tuple(self._catalog.values()))
                        if time.monotonic() < self._catalog_until
                        else ()
                    )
                    binding = matches[0] if len(matches) == 1 else None
                if binding is None:
                    raise _Refused("Select its source window before selecting a region")
                op = self._reserve_locked(
                    "select", id, expected_generation, native=True
                )
                op.proposal = replace(old, window=self._physical.get(id, old.window))
                op.binding = binding
                return self._queue_locked(op)
            except _Refused as exc:
                return self._refusal_locked(exc, id)

    def set_enabled(self, id: str, enabled: bool, expected_generation: int) -> dict:
        with self._condition:
            try:
                if type(enabled) is not bool:
                    raise _Refused("Enabled must be true or false")
                if enabled:
                    self._check_enabled_locked(id)
                native = enabled and self._available
                op = self._reserve_locked(
                    "enable" if native else "edit",
                    id,
                    expected_generation,
                    native=native,
                )
                op.proposal = replace(self._definitions[id], enabled=enabled)
                return self._queue_locked(op)
            except _Refused as exc:
                return self._refusal_locked(exc, id)

    def edit(
        self,
        id: str,
        label: str,
        title_mode: str,
        title_hint: str,
        expected_generation: int,
    ) -> dict:
        with self._condition:
            try:
                label = bounded_text(label, LABEL_MAX_CHARS, "Label")
                if not isinstance(id, str):
                    raise _Refused("Choose a saved companion")
                old = self._definitions.get(id)
                if old is None:
                    raise _Refused("This companion no longer exists")
                source = validate_descriptor(
                    {
                        **asdict(old.source),
                        "title_mode": title_mode,
                        "title_hint": title_hint,
                    }
                )
                binding = self._rows[id]["binding"]
                if (
                    source != old.source
                    and binding is not None
                    and not matching_sources(source, (binding,))
                ):
                    raise _Refused("Title hint must match the current source window")
                op = self._reserve_locked("edit", id, expected_generation)
                op.proposal = replace(old, label=label, source=source)
                return self._queue_locked(op)
            except (ValueError, _Refused) as exc:
                return self._refusal_locked(exc, id)

    def remove(self, id: str, expected_generation: int) -> dict:
        with self._condition:
            try:
                return self._queue_locked(
                    self._reserve_locked("remove", id, expected_generation)
                )
            except _Refused as exc:
                return self._refusal_locked(exc, id)

    def reset_geometry(self, id: str, expected_generation: int) -> dict:
        with self._condition:
            try:
                op = self._reserve_locked("reset", id, expected_generation)
                old = self._definitions[id]
                size = self._rows[id]["binding"]
                w, h = size.client_size if size is not None else (320, 210)
                if old.region is not None:
                    w, h = (
                        old.region.w * old.region.original_client_w,
                        old.region.h * old.region.original_client_h,
                    )
                scale = min(320 / w, 210 / h)
                op.proposal = replace(
                    old,
                    window=Rect(
                        100, 100, max(1, round(w * scale)), max(1, round(h * scale))
                    ),
                )
                return self._queue_locked(op)
            except _Refused as exc:
                return self._refusal_locked(exc, id)

    def native_event(self, event: CompanionEvent) -> None:
        """Pump callback: bounded metadata only, even during an admitted save."""
        if not isinstance(event, CompanionEvent):
            return
        if event.kind == "geometry":
            self.record_geometry(event.payload)
            return
        with self._condition:
            if self._done.is_set():
                return
            if event.kind == "status":
                self._status_event = event
            elif event.kind in (
                "sources",
                "region-selected",
                "prepared",
                "failed",
                "closed",
            ):
                op = (
                    self._operations.get(event.token.operation_id)
                    if isinstance(event.token, CompanionToken)
                    else None
                )
                if op is None or event.token != op.token:
                    return
                if event.kind == "failed":
                    op.failure = str(event.payload)
                self._events[(event.token.operation_id, event.kind)] = event
            else:
                return
            self._wake_locked()

    def selection_valid(self, token: CompanionToken) -> bool:
        """Short pump authorization read; no settings/runtime/native calls."""
        with self._condition:
            op = self._operations.get(token.operation_id)
            return (
                not self._closed
                and op is not None
                and op.token == token
                and token.selection_lease is not None
                and self._native_operation == token.operation_id
                and op.failure is None
                and (
                    not op.receipt["persisted"]
                    or self._generations.get(token.id) == token.generation
                )
            )

    def record_geometry(self, delta: GeometryDelta) -> None:
        if (
            not isinstance(delta, GeometryDelta)
            or not valid_rect(delta.rect)
            or type(delta.sequence) is not int
        ):
            return
        with self._condition:
            row = self._rows.get(delta.id)
            key = (delta.id, delta.generation, delta.binding_revision)
            if (
                self._closed
                or row is None
                or self._generations.get(delta.id) != delta.generation
                or row["binding_revision"] != delta.binding_revision
                or delta.sequence <= self._sequences.get(key, 0)
            ):
                return
            self._sequences[key] = delta.sequence
            self._physical[delta.id] = delta.rect
            self._geometry[delta.id] = (delta, time.monotonic() + GEOMETRY_DEBOUNCE)
            self._wake_locked()

    def close_publication(self) -> None:
        with self._condition:
            self._publication_open = False
            self._publish_dirty = False

    def close_admission(self) -> None:
        with self._condition:
            self._closed = True
            if self._worker is not None:
                self._condition.notify_all()

    def drain(self) -> Future[bool]:
        with self._condition:
            if self._barrier is None:
                self._barrier = Future()
            future = self._barrier
            done = self._done.is_set()
            if done:
                self._barrier = None
                success = not self._geometry and not self._worker_failed
            else:
                self._wake_locked()
        if done:
            future.set_result(success)
        return future

    def shutdown(self, timeout: float = 5.0) -> bool:
        self.close_publication()
        self.close_admission()
        with self._condition:
            self._shutdown = True
            self._wake_locked()
            worker = self._worker
        return (
            worker is not threading.current_thread()
            and self._done.wait(timeout)
            and not self._worker_failed
        )

    def _valid_locked(self, op):
        identity = op.receipt["id"]
        return self._operations.get(op.receipt["operation_id"]) is op and (
            op.expected is None or self._generations.get(identity) == op.expected
        )

    def _finish(
        self,
        op,
        *,
        applied=False,
        persisted=False,
        error=None,
        sources=None,
        retain=False,
    ):
        with self._condition:
            if op.receipt["pending"]:
                self._changed_locked()
                op.receipt.update(
                    pending=False,
                    applied=applied,
                    persisted=persisted,
                    error=error,
                    revision=self._revision,
                )
                if sources is not None:
                    op.receipt["sources"] = sources
                self._terminal[op.receipt["operation_id"]] = dict(op.receipt)
                while len(self._terminal) > MAX_OPERATIONS:
                    self._terminal.popitem(last=False)
                identity = op.receipt["id"]
                if self._busy.get(identity) == op.receipt["operation_id"]:
                    self._busy.pop(identity, None)
            if retain:
                op.phase = "cleanup"
                return
        self._retire(op)

    def _retire(self, op):
        with self._condition:
            self._operations.pop(op.receipt["operation_id"], None)
            if self._native_operation == op.receipt["operation_id"]:
                self._native_operation = None
            token = op.token
            identity = op.receipt["id"]
            if identity not in self._definitions:
                self._next_generations.pop(identity, None)
        if token is not None and token.selection_lease is not None:
            self._ports.runtime.release_selection(token.selection_lease)

    def _discard(self, op, error):
        token = op.token
        if token is not None and op.phase not in ("queued", "starting"):
            self._ports.submit_native(CompanionCommand("discard", token, None))
            self._finish(op, error=error, retain=True)
        else:
            self._finish(op, error=error)

    def _begin_native(self, op):
        lease = self._ports.runtime.acquire_selection(op.receipt["operation_id"])
        if lease is None:
            self._finish(
                op,
                error="Another source selection is pending or the preview host is stopping",
            )
            return
        state = self._ports.runtime.snapshot()
        with self._condition:
            identity = op.receipt["id"] or ""
            generation = self._next_generations.get(identity, 0) + 1
            if identity:
                self._next_generations[identity] = generation
            op.token = CompanionToken(
                op.receipt["operation_id"],
                identity,
                lease.pump_epoch,
                state.companion_epoch,
                generation,
                lease,
            )
            op.phase = "starting"
            op.deadline = time.monotonic() + 15.0
        self._send_initial(op)

    def _send_initial(self, op):
        state = self._ports.runtime.snapshot()
        if state.pump != "active" or state.pump_epoch != op.token.pump_epoch:
            if state.pump == "failed" or time.monotonic() >= op.deadline:
                self._finish(op, error="Preview source capture could not start")
            return
        if op.action in ("sources", "enable"):
            command = CompanionCommand("enumerate", op.token, None)
        elif op.proposal.mode == "region":
            command = CompanionCommand(
                "pick-region", op.token, PickerRequest(op.binding, op.proposal.label)
            )
        else:
            command = CompanionCommand("prepare", op.token, (op.proposal, op.binding))
        op.phase = "native"
        if not self._ports.submit_native(command):
            self._finish(op, error="Preview source capture is busy; try again")

    def _save(self, op):
        try:
            with self._ports.update_settings() as data:
                state = self._ports.runtime.snapshot()
                with self._condition:
                    if op.failure is not None:
                        raise _Refused(op.failure)
                    if self._closed or not self._valid_locked(op):
                        raise _Refused("Companion change was cancelled before saving")
                    if (
                        op.token is not None
                        and op.phase == "prepared"
                        and (
                            not state.selection_pending
                            or state.pump_epoch != op.token.pump_epoch
                            or state.pump != "active"
                        )
                    ):
                        raise _Refused("Source capture ended before saving")
                    proposed = dict(self._definitions)
                    enabled = self._enabled
                    identity = op.receipt["id"]
                    if op.action == "master":
                        enabled = op.proposal
                    elif op.action == "remove":
                        proposed.pop(identity)
                    else:
                        if op.action in ("edit", "enable") and op.phase != "prepared":
                            # Geometry may have committed while this page edit
                            # waited in the same worker's queue. Its label/policy
                            # proposal owns no authority to restore an old rect.
                            op.proposal = replace(
                                op.proposal, window=self._definitions[identity].window
                            )
                        proposed[identity] = op.proposal
                    op.admitted = True
                data["companion_previews"] = {
                    "enabled": enabled,
                    "definitions": serialize_definitions(tuple(proposed.values())),
                }
            with self._condition:
                self._definitions = proposed
                self._enabled = enabled
                if op.action == "remove":
                    self._rows.pop(identity, None)
                    self._generations.pop(identity, None)
                    self._geometry.pop(identity, None)
                    self._physical.pop(identity, None)
                    self._handoff_geometry.pop(identity, None)
                    self._sequences = {
                        key: seq
                        for key, seq in self._sequences.items()
                        if key[0] != identity
                    }
                    # IDs are generated only at add admission, never supplied by
                    # the page; absent IDs reject callbacks without an unbounded
                    # permanent tombstone table.
                    self._next_generations.pop(identity, None)
                elif op.action != "master":
                    old_generation = self._generations.get(identity)
                    generation = (
                        op.token.generation
                        if op.token is not None
                        else self._next_generations.get(identity, 0) + 1
                    )
                    self._generations[identity] = generation
                    self._next_generations[identity] = generation
                    row = self._rows.setdefault(identity, self._new_row())
                    row["error"] = None
                    if op.action == "reset":
                        row["geometry_error"] = None
                        self._geometry.pop(identity, None)
                        self._physical[identity] = op.proposal.window
                    elif identity in self._geometry:
                        delta, deadline = self._geometry[identity]
                        if (
                            delta.generation == old_generation
                            and delta.binding_revision == row["binding_revision"]
                        ):
                            self._geometry[identity] = (
                                replace(delta, generation=generation),
                                deadline,
                            )
                            if op.phase == "prepared":
                                self._handoff_geometry[identity] = (
                                    generation,
                                    delta.binding_revision,
                                )
                    if op.phase == "prepared":
                        row["status"] = "waiting"
                        row["geometry_error"] = None
                self._started = True
                self._runtime_dirty = True
                self._reconcile_dirty = True
                self._changed_locked()
        except (OSError, ValueError, _Refused) as exc:
            if op.token is not None and op.phase == "prepared":
                self._discard(op, str(exc))
            else:
                self._finish(op, error=str(exc))
            return
        if op.token is not None and op.phase == "prepared":
            # Send the original epoch token, never re-authorize a stale candidate.
            sent = self._ports.submit_native(
                CompanionCommand("promote", op.token, None)
            )
            if not sent:
                self._ports.submit_native(CompanionCommand("discard", op.token, None))
            self._finish(op, applied=True, persisted=True, retain=True)
        else:
            if op.action == "reset":
                # Advance the native row's generation before delivering its
                # explicit move; reconciliation alone never persists rescue.
                self._sync_runtime()
                state = self._ports.runtime.snapshot()
                token = CompanionToken(
                    op.receipt["operation_id"],
                    identity,
                    state.pump_epoch,
                    state.companion_epoch,
                    self._generations[identity],
                    None,
                )
                self._ports.submit_native(
                    CompanionCommand("reset", token, op.proposal.window)
                )
            self._finish(op, applied=True, persisted=True)

    def _handle_sources(self, op, payload):
        try:
            rows, bindings = payload
            if (
                not isinstance(rows, (tuple, list))
                or not isinstance(bindings, dict)
                or len(rows) > MAX_SOURCES
                or len(bindings) > MAX_SOURCES
            ):
                raise ValueError("Source enumeration is incomplete")
            safe = []
            catalog = {}
            for row in rows:
                token = row["candidate_token"]
                if (
                    not isinstance(token, str)
                    or not token
                    or len(token) > 256
                    or token in catalog
                    or not isinstance(bindings.get(token), SourceBinding)
                ):
                    raise ValueError("Invalid source selection token")
                safe.append(
                    {
                        "candidate_token": token,
                        "application": bounded_text(
                            row["application"], WINDOW_CLASS_MAX_CHARS, "Application"
                        ),
                        "title": bounded_text(row["title"], TITLE_MAX_CHARS, "Title"),
                    }
                )
                catalog[token] = bindings[token]
            with self._condition:
                self._catalog = catalog
                self._catalog_until = time.monotonic() + SOURCE_TTL_SECONDS
            if op.action == "enable":
                matches = matching_sources(op.proposal.source, tuple(catalog.values()))
                if len(matches) != 1:
                    with self._condition:
                        self._rows[op.receipt["id"]]["status"] = (
                            "needs-selection" if matches else "waiting"
                        )
                    # Nothing native was allocated; enabling a missing source is
                    # a real saved preference, not failed capture.
                    self._save(op)
                else:
                    op.binding = matches[0]
                    op.phase = "native"
                    if not self._ports.submit_native(
                        CompanionCommand("prepare", op.token, (op.proposal, op.binding))
                    ):
                        self._finish(op, error="Source capture is busy; try again")
            else:
                self._finish(op, applied=True, sources=safe)
        except (KeyError, TypeError, ValueError) as exc:
            self._finish(op, error=str(exc))

    @staticmethod
    def _same_source(left, right):
        return (
            left.hwnd,
            left.pid,
            left.process_created,
            left.executable_path.casefold(),
            left.window_class,
        ) == (
            right.hwnd,
            right.pid,
            right.process_created,
            right.executable_path.casefold(),
            right.window_class,
        )

    def _handle_event(self, event):
        with self._condition:
            op = self._operations.get(event.token.operation_id)
            if op is None or op.token != event.token:
                return
            closed = self._closed
        if event.kind == "closed":
            if op.phase == "cleanup":
                with self._condition:
                    moved = self._physical.get(op.receipt["id"])
                    reset = (
                        op.receipt["persisted"]
                        and moved is not None
                        and moved != op.proposal.window
                        and self._generations.get(op.token.id) == op.token.generation
                    )
                if reset:
                    # Cleanup may have delayed promotion. Its acknowledgment,
                    # not queue timing, proves the new live generation exists.
                    # This move needs family authority, not the retiring lease.
                    self._ports.submit_native(
                        CompanionCommand(
                            "reset", replace(op.token, selection_lease=None), moved
                        )
                    )
                self._retire(op)
            return
        if event.kind == "failed":
            if op.receipt["persisted"]:
                with self._condition:
                    row = self._rows.get(op.receipt["id"])
                    if row is not None:
                        row.update(
                            status="source-unavailable",
                            error=str(event.payload),
                            binding=None,
                        )
                        self._changed_locked()
                self._retire(op)
            else:
                self._finish(op, error=str(event.payload))
            return
        if not op.receipt["pending"]:
            return
        if closed:
            self._discard(op, "Companion previews are stopping")
            return
        if event.kind == "sources":
            self._handle_sources(op, event.payload)
            return
        if event.kind == "region-selected":
            facts = event.payload
            if (
                not isinstance(facts, RegionSelection)
                or not self._same_source(facts.binding, op.binding)
                or facts.source_size != facts.binding.client_size
                or facts.source_size
                != (facts.region.original_client_w, facts.region.original_client_h)
            ):
                self._discard(
                    op, "Source changed during region selection; select it again"
                )
                return
            op.binding = facts.binding
            op.proposal = replace(op.proposal, region=facts.region)
            op.phase = "native"
            if not self._ports.submit_native(
                CompanionCommand("prepare", op.token, (op.proposal, op.binding))
            ):
                self._discard(op, "Source capture is busy; try again")
            return
        if event.kind == "prepared":
            facts = event.payload
            if (
                not isinstance(facts, PreparedCompanion)
                or not self._same_source(facts.binding, op.binding)
                or facts.source_size != facts.binding.client_size
                or facts.region != op.proposal.region
                or not valid_rect(facts.window)
                or (
                    op.action == "select"
                    and facts.region is not None
                    and facts.source_size
                    != (facts.region.original_client_w, facts.region.original_client_h)
                )
            ):
                self._discard(op, "Source changed during preparation; select it again")
                return
            if op.proposal.mode == "region" and op.proposal.region is None:
                self._discard(op, "Select a valid region before saving")
                return
            if op.expected is None:
                op.proposal = replace(op.proposal, window=facts.window)
            else:
                with self._condition:
                    op.proposal = replace(
                        op.proposal,
                        window=self._physical.get(op.receipt["id"], op.proposal.window),
                    )
            op.phase = "prepared"
            self._save(op)

    def _handle_status(self, event):
        if not isinstance(event.payload, (list, tuple)):
            return
        with self._condition:
            changed = False
            for value in event.payload[:MAX_DEFINITIONS]:
                if not isinstance(value, dict):
                    continue
                identity = value.get("id")
                row = self._rows.get(identity)
                revision = value.get("binding_revision")
                if (
                    row is None
                    or value.get("generation") != self._generations[identity]
                    or type(revision) is not int
                    or revision < row["binding_revision"]
                    or value.get("status")
                    not in (
                        "live",
                        "waiting",
                        "needs-selection",
                        "source-unavailable",
                        "stopping",
                        "disabled",
                        "off",
                    )
                ):
                    continue
                if revision > row["binding_revision"]:
                    handoff = self._handoff_geometry.pop(identity, None)
                    pending = self._geometry.get(identity)
                    if (
                        pending is not None
                        and handoff == (value["generation"], row["binding_revision"])
                        and value["status"] == "live"
                    ):
                        delta, deadline = pending
                        self._geometry[identity] = (
                            replace(delta, binding_revision=revision),
                            deadline,
                        )
                    else:
                        self._geometry.pop(identity, None)
                    self._sequences = {
                        key: seq
                        for key, seq in self._sequences.items()
                        if key[0] != identity
                    }
                binding = value.get("binding")
                updated = {
                    "binding_revision": revision,
                    "status": value["status"],
                    "error": value.get("error"),
                    "geometry_error": row["geometry_error"],
                    "binding": binding if isinstance(binding, SourceBinding) else None,
                }
                if row != updated:
                    self._rows[identity] = updated
                    changed = True
            if changed:
                self._changed_locked()

    def _flush_geometry(self, force=False):
        now = time.monotonic()
        with self._condition:
            selected = {
                identity: value
                for identity, value in self._geometry.items()
                if force or value[1] <= now
            }
        if not selected:
            return True
        try:
            with self._ports.update_settings() as data:
                with self._condition:
                    proposed = dict(self._definitions)
                    authorized = {}
                    for identity, (delta, deadline) in selected.items():
                        row = self._rows.get(identity)
                        if (
                            identity in proposed
                            and self._generations[identity] == delta.generation
                            and row["binding_revision"] == delta.binding_revision
                        ):
                            proposed[identity] = replace(
                                proposed[identity], window=delta.rect
                            )
                            authorized[identity] = (delta, deadline)
                    if not authorized:
                        raise _Refused("Geometry authority expired")
                    enabled = self._enabled
                data["companion_previews"] = {
                    "enabled": enabled,
                    "definitions": serialize_definitions(tuple(proposed.values())),
                }
            with self._condition:
                self._definitions = proposed
                for identity in authorized:
                    self._rows[identity]["geometry_error"] = None
                self._changed_locked()
            success = True
        except _Refused:
            success = True
        except (OSError, ValueError) as exc:
            with self._condition:
                for identity in selected:
                    if identity in self._rows:
                        self._rows[identity]["geometry_error"] = (
                            f"Position is session-only; could not save: {exc}"
                        )
                self._changed_locked()
            success = False
        with self._condition:
            for identity, value in selected.items():
                if self._geometry.get(identity) == value:
                    self._geometry.pop(identity, None)
        return success

    def _sync_runtime(self):
        with self._condition:
            self._runtime_dirty = False
            if not self._started or self._closed:
                return
            demand = (
                self._available
                and self._enabled
                and any(d.enabled for d in self._definitions.values())
            )
            changed = demand != self._last_demand
            self._last_demand = demand
            revision = self._revision
        if changed:
            self._ports.runtime.set_companions(demand, revision)
        state = self._ports.runtime.snapshot()
        with self._condition:
            self._runtime = state
            reconcile = (
                self._reconcile_dirty
                and demand
                and state.pump == "active"
                and state.companions == "active"
            )
            if reconcile:
                specs = tuple(
                    CompanionSpec(
                        d, self._generations[d.id], self._rows[d.id]["binding_revision"]
                    )
                    for d in self._definitions.values()
                )
        if reconcile and self._ports.submit_native(
            CompanionCommand("reconcile", None, (specs, state.companion_epoch))
        ):
            with self._condition:
                self._reconcile_dirty = False

    def _publish(self):
        with self._condition:
            if (
                not self._publish_dirty
                or not self._publication_open
                or not self._subscribed
            ):
                return
            self._publish_dirty = False
            snapshot = self._snapshot_locked()
        try:
            self._ports.publish_state(snapshot)
        except Exception:
            # A view failure cannot strand the sole persistence/cleanup owner.
            logger.exception("Companion state publication failed")

    def _run(self):
        try:
            while True:
                with self._condition:
                    event = (
                        self._events.popitem(last=False)[1] if self._events else None
                    )
                    status, self._status_event = self._status_event, None
                    op = (
                        self._operations.get(self._jobs.popleft())
                        if self._jobs and event is None
                        else None
                    )
                    closing = [
                        item
                        for item in self._operations.values()
                        if self._closed
                        and not item.admitted
                        and item.receipt["pending"]
                    ]
                    starting = [
                        item
                        for item in self._operations.values()
                        if item.phase == "starting"
                    ]
                for item in closing:
                    self._discard(item, "Companion previews are stopping")
                if event is not None:
                    self._handle_event(event)
                if status is not None:
                    self._handle_status(status)
                if op is not None and op.receipt["pending"]:
                    if op.native:
                        self._begin_native(op)
                    else:
                        self._save(op)
                for item in starting:
                    if item.receipt["pending"] and not self._closed:
                        self._send_initial(item)
                self._sync_runtime()
                with self._condition:
                    barrier = (
                        self._barrier if not self._jobs and not self._events else None
                    )
                    if barrier is not None:
                        self._barrier = None
                    final = self._shutdown and not self._jobs and not self._events
                success = self._flush_geometry(force=barrier is not None or final)
                if barrier is not None:
                    barrier.set_result(success)
                self._publish()
                if final:
                    return
                with self._condition:
                    if (
                        self._jobs
                        or self._events
                        or self._status_event is not None
                        or self._barrier is not None
                        or self._runtime_dirty
                    ):
                        continue
                    deadlines = [value[1] for value in self._geometry.values()]
                    if any(
                        item.phase == "starting" for item in self._operations.values()
                    ):
                        deadlines.append(time.monotonic() + 0.05)
                    delay = (
                        max(0, min(deadlines) - time.monotonic()) if deadlines else None
                    )
                    self._condition.wait(delay)
        except Exception:
            # Preserve the sole failed owner; never replace it over uncertain IO.
            logger.exception("Companion controller worker failed")
            with self._condition:
                self._closed = True
                self._worker_failed = True
        finally:
            with self._condition:
                # A drain may be admitted after the final flush decided to exit.
                # Publish done under the same fence and complete outside it.
                self._done.set()
                barrier, self._barrier = self._barrier, None
                success = not self._geometry and not self._worker_failed
            if barrier is not None:
                barrier.set_result(success)
