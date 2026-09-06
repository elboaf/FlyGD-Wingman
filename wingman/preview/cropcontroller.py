"""Pump-owned crop resources; committed settings and native authority are separate.

The store alone writes settings. Its completion callback only posts immutable
results to the host mailbox; native work resumes in ``complete`` on the pump.
"""

import logging
from collections import deque
from concurrent.futures import Future
from dataclasses import dataclass

from ..telemetry.model import RosterClient, RosterSnapshot
from .crops import (
    MAX_LIVE_CROPS,
    CropDefinition,
    CropSource,
    CropToken,
    CropWriteResult,
    deserialize,
    eligible_names,
    source_from_pixels,
    source_to_pixels,
)
from .cropwindow import CropWindow
from .geometry import clamp_to_monitors, default_stack

logger = logging.getLogger(__name__)


@dataclass
class _Live:
    client: RosterClient
    generation: int
    source: CropSource
    window: CropWindow | None = None
    failed: bool = False
    failure_status: str = "native-failed"


@dataclass
class _Request:
    action: str
    name: str
    value: object
    token: CropToken
    submitted: bool = False
    candidate: _Live | None = None
    definition: CropDefinition | None = None


class CropController:
    def __init__(
        self,
        libs,
        store,
        *,
        epoch,
        create_crop,
        create_picker,
        read_client_size,
        monitors,
        activate,
        is_locked,
        publish,
        post_complete,
        next_geometry_sequence,
    ) -> None:
        self._libs, self._store = libs, store
        self._epoch = epoch
        self._create_crop, self._create_picker = create_crop, create_picker
        self._read_client_size, self._monitors = read_client_size, monitors
        self._activate, self._is_locked = activate, is_locked
        self._publish, self._post_complete = publish, post_complete
        # Retained by PreviewHost, not reset when a new pump is constructed.
        self._next_geometry_sequence = next_geometry_sequence
        self.live: dict[str, _Live] = {}
        self.sessions: dict[str, RosterClient] = {}
        self.picker = None
        self._temporary = None
        self._active = {}
        self._waiting = {}
        self._degraded = {}
        self._hidden = False
        self._stopping = False
        self._stop_future = None
        self._roster_generation = -1

    def reconcile(self, snapshot: RosterSnapshot) -> None:
        if snapshot.generation < self._roster_generation:
            return
        self._roster_generation = snapshot.generation
        self.sessions = {
            c.character: c
            for c in snapshot.clients
            if c.character and c.session is not None
        }
        op = self._temporary
        if op is not None and not self._authorized(op):
            self._cancel_native(op)
        self._reconcile()

    def _eligible(self, definitions):
        if self._stopping:
            return set()
        # Held committed windows count until pump completion, even if a worker
        # has published their disable already. Reserve the eventual selected
        # slot too: neither an arrival nor another edit can steal its capacity.
        pinned = {
            name
            for name, op in self._active.items()
            if op.submitted
            and name in self.live
            and name in self.sessions
            and self.live[name].client.session == self.sessions[name].session
        }
        op = self._temporary
        if op is not None:
            pinned.add(op.name)
        others = {n: d for n, d in definitions.items() if n not in pinned}
        desired = set(
            eligible_names(others, self.sessions, MAX_LIVE_CROPS - len(pinned))
        )
        desired.update(name for name in pinned if name in self.live)
        if (
            op is not None
            and op.name in definitions
            and definitions[op.name].enabled
            and op.name in self.sessions
        ):
            desired.add(op.name)
        return desired

    def _refresh_source(self, name, live):
        source = source_to_pixels(
            live.source, self._read_client_size(live.client) or (0, 0)
        )
        if source is None:
            live.failed = True
            live.failure_status = "invalid-source"
            live.window.close()
            if self.live.get(name) is live:
                self.live.pop(name)
                self._degraded[name] = (
                    live.client.session,
                    live.generation,
                    live.failure_status,
                )
            return False
        live.window.set_source_rect(source)
        return not live.failed

    def _reconcile(self):
        if self._stopping:
            self._emit()
            return
        state = self._store.snapshot()
        definitions = deserialize(state["definitions"])
        desired = self._eligible(definitions)
        for name, live in list(self.live.items()):
            current = self.sessions.get(name)
            # An admitted replacement may already be published by the worker.
            # Preserve its old live window until this pump processes completion.
            held = name in self._active and self._active[name].submitted
            if (
                current is None
                or current.session != live.client.session
                or (
                    not held
                    and (
                        name not in desired
                        or state["generations"].get(name) != live.generation
                    )
                )
            ):
                self.live.pop(name).window.close()
            else:
                self._refresh_source(name, live)
        op = self._temporary
        if (
            op is not None
            and op.candidate is not None
            and not self._refresh_source(op.name, op.candidate)
        ):
            self._cancel_native(op)
        self._degraded = {
            name: episode
            for name, episode in self._degraded.items()
            if name in self.sessions
            and name in definitions
            and episode[:2] == (self.sessions[name].session, state["generations"][name])
        }
        for name in sorted(desired):
            if name in self._degraded or (
                name in self._active and self._active[name].submitted
            ):
                continue
            definition = definitions[name]
            client = self.sessions[name]
            generation = state["generations"][name]
            size = self._read_client_size(client)
            source = source_to_pixels(definition.source, size or (0, 0))
            if source is None:
                self._degraded[name] = (client.session, generation, "invalid-source")
                live = self.live.pop(name, None)
                if live is not None:
                    live.window.close()
                continue
            live = self.live.get(name)
            if live is not None:
                live.window.set_source_rect(source)
            else:
                live = _Live(client, generation, definition.source)
                rect = clamp_to_monitors(definition.window, self._monitors())
                self._make_window(name, live, source, rect, hidden=self._hidden)
                if live.window is not None and not live.failed:
                    self.live[name] = live
        self._emit()

    def _make_window(self, name, live, source, rect, *, hidden, candidate=False):
        # The reservation exists before create: failure can call back before
        # the returned window has been assigned, even on initial registration.
        def failed(_reason):
            live.failed = True
            was_live = self.live.get(name) is live
            if was_live:
                self.live.pop(name)
            if not candidate or was_live:
                self._degraded[name] = (
                    live.client.session,
                    live.generation,
                    "native-failed",
                )
            # CropWindow already logged context, including HWNDs. Never send
            # that internal diagnostic through the semantic state event.
            self._emit()

        live.window = self._create_crop(
            self._libs,
            live.client,
            source,
            rect,
            hidden=hidden,
            locked=self._is_locked(name),
            on_activate=lambda _client: self._activate_current(name),
            on_rect_changed=lambda rect: self._geometry(name, live, rect),
            on_disable=lambda: self._disable(name),
            on_failure=failed,
        )
        if live.window is None:
            failed(None)

    def _activate_current(self, name):
        current = self.sessions.get(name)
        if current is not None and not self._stopping:
            self._activate(current)

    def _geometry(self, name, live, rect):
        if not self._stopping and self.live.get(name) is live:
            sequence = self._next_geometry_sequence()
            self._store.record_geometry(name, live.generation, sequence, rect)
            op = self._active.get(name)
            if op is not None and op.action == "select" and op.submitted:
                committed = self._store.snapshot()["generations"].get(name)
                if committed == op.token.generation:
                    # Publication can race the first record. Read its committed
                    # generation AFTER recording: either the store accepted and
                    # rebased the first delta, or this second call preserves it.
                    # The same sequence makes acceptance idempotent. This also
                    # works if source loss closes the old window before swap.
                    self._store.record_geometry(name, committed, sequence, rect)

    def _disable(self, name):
        if not self._stopping:
            live = self.live.get(name)
            if live is not None:
                token = self._store.begin(name, epoch=0, session=None)
                self.request("enabled", name, False, token)

    def _authorized(self, op):
        client = self.sessions.get(op.name)
        return (
            not self._stopping
            and op.token.epoch == self._epoch
            and client is not None
            and client.session == op.token.session
        )

    def request(self, action: str, name: str, value, token: CropToken) -> dict:
        """Accept a host-issued token on the pump; later same-owner edits wait."""
        op = _Request(action, name, value, token)
        if self._stopping:
            self._cancel_token(token)
            return self._receipt(token, "Previews are stopping")
        active = self._active.get(name)
        if active is not None:
            waiting = self._waiting.setdefault(name, deque())
            if action == "remove" or (action == "enabled" and not value):
                # A newer disable/remove supersedes selections that have not
                # reached admission, including ones held behind this picker.
                for earlier in list(waiting):
                    if earlier.action == "select":
                        self._cancel_token(earlier.token)
                        waiting.remove(earlier)
            waiting.append(op)
            if not active.submitted and (
                action == "remove" or (action == "enabled" and not value)
            ):
                self._cancel_native(active)
        else:
            self._start(op)
        self._emit()
        return self._receipt(token)

    def _receipt(self, token, error=None):
        result = dict(self._store.snapshot()["operations"][token.operation_id])
        result.pop("name")
        result.pop("revision")
        if error is not None:
            result["error"] = error
        return result

    def _start(self, op):
        self._active[op.name] = op
        if op.action != "select":
            self._submit(op)
            return
        if (
            not self._authorized(op)
            or self._temporary is not None
            or (op.name not in self.live and len(self.live) >= MAX_LIVE_CROPS)
        ):
            self._discard_prepared(op)
            return
        monitors = self._monitors()
        if not monitors:
            self._discard_prepared(op)
            return
        self._temporary = op
        picker = self._create_picker(
            self._libs,
            self.sessions[op.name],
            monitors[0],
            on_confirm=lambda client, rect, size: self._confirm(op, client, rect, size),
            on_cancel=lambda _reason: self._picker_canceled(op),
        )
        # Failure/cancel is synchronous, including from inside create().
        if self._temporary is op:
            self.picker = picker
            if picker is None:
                self._discard_prepared(op)

    def _picker_canceled(self, op):
        if self._temporary is op:
            self.picker = None
            self._discard_prepared(op)

    def _confirm(self, op, client, rect, size):
        if self._temporary is not op:
            return
        self.picker = None  # callback proves the ENTIRE picker bundle is closed
        if (
            not self._authorized(op)
            or client.session != op.token.session
            or self._read_client_size(client) != size
            or (op.name not in self.live and len(self.live) >= MAX_LIVE_CROPS)
        ):
            self._discard_prepared(op)
            return
        try:
            source = source_from_pixels(rect, size)
        except ValueError:
            self._discard_prepared(op)
            return
        definitions = deserialize(self._store.snapshot()["definitions"])
        old = self.live.get(op.name)
        destination = (
            old.window.rect
            if old
            else definitions[op.name].window
            if op.name in definitions
            else default_stack(
                0, self._monitors()[0], (320, max(1, round(320 * rect.h / rect.w)))
            )
        )
        destination = clamp_to_monitors(destination, self._monitors())
        op.definition = CropDefinition(source, destination)
        op.candidate = _Live(client, op.token.generation, source)
        self._make_window(
            op.name, op.candidate, rect, destination, hidden=True, candidate=True
        )
        if op.candidate.failed or not self._authorized(op):
            self._discard_prepared(op)
            return
        self._submit(op)
        self._emit()

    def _submit(self, op):
        op.submitted = True
        if op.action == "select":
            future = self._store.put(op.token, op.definition)
        elif op.action == "enabled":
            future = self._store.set_enabled(op.token, op.value)
        else:
            future = self._store.remove(op.token)
        future.add_done_callback(lambda done: self._post_complete(done.result()))

    def _close_candidate(self, op):
        if op.candidate is not None and op.candidate.window is not None:
            op.candidate.window.close()

    def _cancel_token(self, token):
        try:
            self._store.cancel(token)
        except ValueError:
            # All tokens here were issued by this store. It only forgets
            # terminal outcomes, never pending work; ingress may have canceled
            # and aged one out while this pump still retained its picker.
            logger.debug(
                "Crop cancellation outcome already retired: %s", token.operation_id
            )

    def _cancel_native(self, op):
        if self._temporary is op and self.picker is not None:
            self.picker.cancel("source-expired")
            return
        self._close_candidate(op)
        if op.submitted:
            # cancel() refuses an admitted write. Either way, wait for its
            # queued completion before admitting a later same-character edit.
            self._cancel_token(op.token)
            if self._temporary is op:
                self._temporary = None
        else:
            self._discard_prepared(op)

    def _discard_prepared(self, op):
        self._cancel_token(op.token)
        self._close_candidate(op)
        if self._temporary is op:
            self._temporary = None
        if self._active.get(op.name) is op:
            self._active.pop(op.name)
        self._advance(op.name)
        self._reconcile()

    def _advance(self, name):
        waiting = self._waiting.get(name)
        if waiting and not self._stopping:
            op = waiting.popleft()
            if not waiting:
                self._waiting.pop(name)
            self._start(op)

    def complete(self, result: CropWriteResult) -> None:
        op = self._active.get(result.token.name)
        if op is None or op.token != result.token:
            self._emit()  # e.g. configuration submitted during stop
            return
        state = self._store.snapshot()
        definition = deserialize(state["definitions"]).get(op.name)
        candidate = op.candidate
        if (
            result.persisted
            and candidate is not None
            and not candidate.failed
            and candidate.window.hwnd is not None
            and self._authorized(op)
            and definition is not None
            and definition.enabled
            and state["generations"].get(op.name) == op.token.generation
        ):
            source = source_to_pixels(
                definition.source,
                self._read_client_size(self.sessions[op.name]) or (0, 0),
            )
            if source is not None:
                old = self.live.get(op.name)
                # The actual native destination is newer than the worker's
                # publication if the old crop moved while saving or delivering.
                destination = old.window.rect if old is not None else definition.window
                candidate.window.move(destination)
                candidate.window.set_source_rect(source)
                if not candidate.failed:
                    if old is not None:
                        old.window.close()
                    self.live[op.name] = candidate
                    self._degraded.pop(op.name, None)
                    if destination != definition.window:
                        self._store.record_geometry(
                            op.name,
                            candidate.generation,
                            self._next_geometry_sequence(),
                            destination,
                        )
                    candidate.window.set_hidden(self._hidden)
            else:
                candidate.failure_status = "invalid-source"
        if candidate is not None and self.live.get(op.name) is not candidate:
            self._close_candidate(op)
            if result.persisted and self._authorized(op):
                self._degraded[op.name] = (
                    op.token.session,
                    op.token.generation,
                    candidate.failure_status,
                )
        if self._temporary is op:
            self._temporary = None
        self._active.pop(op.name)
        self._advance(op.name)
        self._reconcile()

    def _emit(self):
        state = self._store.snapshot()
        definitions = deserialize(state["definitions"])
        state.pop("generations")
        statuses = {
            name: "disabled"
            if not definition.enabled
            else "stopped"
            if self._stopping
            else "offline"
            if name not in self.sessions
            else self._degraded[name][2]
            if name in self._degraded
            else "live"
            if name in self.live
            else "suppressed"
            for name, definition in definitions.items()
        }
        if self._temporary is not None:
            statuses[self._temporary.name] = (
                "saving" if self._temporary.submitted else "selecting"
            )
        state.update(
            statuses=statuses,
            live_count=len(self.live),
            cap=MAX_LIVE_CROPS,
            runtime_enabled=not self._stopping,
            busy=bool(self._active or self._waiting),
        )
        try:
            self._publish(state)
        except Exception:
            # An outward notification must not strand native ownership or FIFO.
            logger.exception("Could not publish crop state")

    def process_dialog_message(self, message) -> bool:
        picker = self.picker
        return picker.process_dialog_message(message) if picker is not None else False

    def set_hidden(self, hidden: bool) -> None:
        hidden = self._stopping or hidden
        self._hidden = hidden
        for live in list(self.live.values()):
            live.window.set_hidden(hidden)
        # A candidate is always hidden, independent of host visibility.

    def restyle(self) -> None:
        for name, live in list(self.live.items()):
            live.window.set_locked(self._stopping or self._is_locked(name))
        op = self._temporary
        if op is not None and op.candidate is not None:
            op.candidate.window.set_locked(self._stopping or self._is_locked(op.name))

    def begin_stop(self, epoch: int) -> Future[bool]:
        if self._stop_future is not None:
            return self._stop_future
        # Every successful native movement was recorded by _geometry. Do not
        # manufacture deltas for unchanged windows (notably monitor rescues).
        self._stopping = True
        self._store.fence_epoch(epoch)
        if self._temporary is not None:
            self._cancel_native(self._temporary)
        # Later configuration intents were accepted while an earlier native
        # completion was pending. Queue them BEFORE the drain, never drop them.
        waiting = sorted(
            (op for queue in self._waiting.values() for op in queue),
            key=lambda op: op.token.operation_id,
        )
        self._waiting.clear()
        for op in waiting:
            if op.action == "select":
                self._cancel_token(op.token)
            else:
                self._submit(op)
        self.restyle()
        self.set_hidden(True)
        self._stop_future = self._store.drain()
        self._emit()
        return self._stop_future

    def close_native(self) -> None:
        """Release resources on the pump, after begin_stop's drain completes."""
        if self._temporary is not None:
            self._cancel_native(self._temporary)
        for live in list(self.live.values()):
            live.window.close()
        self.live.clear()
        self._emit()
