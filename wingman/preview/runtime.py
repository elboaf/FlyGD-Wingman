"""One retained, serialized owner of the preview pump and its family demands.

Settings producers own independent revisions. The host owns native epochs and
reports facts only; this owner derives public state and never joins under its
lock. Selection is temporary pump demand, not permission to activate a family.
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .host import PreviewHost

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FamilyDemand:
    revision: int
    eve: bool
    companions: bool


@dataclass(frozen=True)
class HostAck:
    pump_epoch: int
    eve_epoch: int
    companion_epoch: int
    outcome: str


@dataclass(frozen=True)
class SelectionLease:
    operation_id: int
    pump_epoch: int


@dataclass(frozen=True)
class RuntimeState:
    revision: int
    pump_epoch: int
    eve_epoch: int
    companion_epoch: int
    pump: str
    eve: str
    companions: str
    selection_pending: bool
    error: str | None


class PreviewRuntime:
    def __init__(self, host: "PreviewHost | None"):
        self._host = host
        self._condition = threading.Condition()
        self._worker = None
        self._done = threading.Event()
        self._dirty = False
        self._closed = False
        self._shutdown = False
        self._final_attempted = False
        self._callback = None
        self._published = None
        self._revision = 0
        self._demand = FamilyDemand(0, False, False)
        self._producer_revisions = {"eve": -1, "companions": -1}
        self._epochs = {"eve": 0, "companions": 0}
        self._minimum_active = {"eve": 1, "companions": 1}
        self._facts = {"eve": "stopped", "companions": "stopped"}
        self._failed_families = set()
        self._pump_epoch = 0
        self._pump = "stopped"
        self._owned = False
        self._stop_waiting = False
        self._stop_ack = False
        self._retry = False
        self._lease = None
        self._error = None
        if host is not None:
            # Retained-owner identity is in the closure, never supplied by a
            # native callback or reconstructed from an HWND.
            host.set_lifecycle_callback(lambda ack: self._ack(host, ack))

    def _wake(self):
        # Caller holds the condition. Only one worker is ever constructed,
        # including after a timed-out shutdown or failed native startup.
        self._dirty = True
        if self._worker is None and self._host is not None:
            self._worker = threading.Thread(
                target=self._run, name="wingman-preview-runtime", daemon=True
            )
            self._worker.start()
        self._condition.notify_all()

    def _needed(self):
        return not self._closed and (
            self._demand.eve or self._demand.companions or self._lease is not None
        )

    def _family_state(self, family):
        wanted = not self._closed and getattr(self._demand, family)
        fact = self._facts[family]
        if wanted:
            if (
                self._host is None
                or self._pump == "failed"
                or family in self._failed_families
            ):
                return "failed"
            if (
                fact == "active"
                and self._epochs[family] >= self._minimum_active[family]
            ):
                return "active"
            return "starting"
        return "stopping" if fact in ("active", "stopping") else "stopped"

    def _snapshot(self):
        return RuntimeState(
            self._revision,
            self._pump_epoch,
            self._epochs["eve"],
            self._epochs["companions"],
            self._pump,
            self._family_state("eve"),
            self._family_state("companions"),
            self._lease is not None,
            self._error,
        )

    def snapshot(self) -> RuntimeState:
        with self._condition:
            return self._snapshot()

    def set_state_callback(self, callback: Callable[[RuntimeState], None]) -> None:
        with self._condition:
            if not self._closed:
                self._callback = callback
                self._published = None
                if self._worker is not None:
                    self._wake()

    def _set(self, family, enabled, revision):
        with self._condition:
            previous_revision = self._producer_revisions[family]
            previous = getattr(self._demand, family)
            if (
                self._closed
                or revision < previous_revision
                or (revision == previous_revision and enabled != previous)
            ):
                return self._snapshot()
            changed = previous != enabled
            if revision > previous_revision:
                self._producer_revisions[family] = revision
                self._demand = FamilyDemand(
                    self._demand.revision + 1,
                    enabled if family == "eve" else self._demand.eve,
                    enabled if family == "companions" else self._demand.companions,
                )
            if changed and not enabled:
                # An off/on cannot re-use an old active acknowledgment while
                # the intervening native cleanup is still in flight.
                self._minimum_active[family] = max(
                    self._minimum_active[family], self._epochs[family] + 2
                )
            self._retry = self._retry or (enabled and self._pump == "failed")
            if self._host is None and enabled:
                self._pump = "failed"
                self._error = "Previews are unavailable"
            self._revision += 1
            demand = self._demand
        # set_families is admission-only. In particular, revocation must not
        # wait behind a startup/stop join on the transition executor.
        if self._host is not None:
            self._host.set_families(demand)
        with self._condition:
            self._wake()
            return self._snapshot()

    def set_eve(self, enabled: bool, revision: int) -> RuntimeState:
        return self._set("eve", enabled, revision)

    def set_companions(self, enabled: bool, revision: int) -> RuntimeState:
        return self._set("companions", enabled, revision)

    def acquire_selection(self, operation_id: int) -> SelectionLease | None:
        with self._condition:
            if (
                self._closed
                or self._host is None
                or self._lease is not None
                or self._stop_waiting
                or (self._owned and self._pump == "failed")
            ):
                return None
            # Reserve the epoch before returning the lease. Native work must
            # still wait for pump-started with this exact epoch.
            epoch = self._pump_epoch if self._owned else self._pump_epoch + 1
            self._lease = SelectionLease(operation_id, epoch)
            self._retry = self._pump == "failed"
            self._revision += 1
            self._wake()
            return self._lease

    def release_selection(self, lease: SelectionLease) -> None:
        with self._condition:
            if lease != self._lease:
                return
            self._lease = None
            self._revision += 1
            self._wake()

    def close_admission(self) -> None:
        with self._condition:
            if self._closed:
                return
            self._closed = True
            self._callback = None
            self._lease = None
            self._revision += 1
        if self._host is not None:
            self._host.close_admission()
        with self._condition:
            self._wake()

    def shutdown(self, timeout: float = 5.0) -> bool:
        self.close_admission()
        if self._host is None:
            return True
        with self._condition:
            self._shutdown = True
            self._wake()
            worker = self._worker
        if worker is threading.current_thread():
            return False
        return self._done.wait(timeout)

    def _ack(self, owner, ack):
        with self._condition:
            if (
                owner is not self._host
                or ack.pump_epoch != self._pump_epoch
                or not self._owned
            ):
                return
            family, _, outcome = ack.outcome.partition("-")
            if family == "pump":
                if outcome == "started":
                    if self._stop_waiting or self._pump != "starting":
                        return
                    self._pump = "active"
                    self._error = None
                elif outcome in ("stopped", "failed"):
                    # The lease authorizes this pump epoch only. Revoke it at
                    # the outcome boundary, but retain the host until stop()
                    # proves cleanup; no selection may enter that retirement.
                    self._lease = None
                    self._stop_waiting = True
                    self._stop_ack = True
                    self._pump = "failed" if outcome == "failed" else "stopping"
                    if outcome == "failed":
                        self._error = "Preview pump could not start"
                else:
                    return
            elif family in self._facts:
                epoch = ack.eve_epoch if family == "eve" else ack.companion_epoch
                if epoch < self._epochs[family] or outcome not in (
                    "active",
                    "stopped",
                    "failed",
                ):
                    return
                if outcome == "active" and epoch < self._minimum_active[family]:
                    return
                self._epochs[family] = epoch
                self._facts[family] = outcome
                if outcome == "failed":
                    self._failed_families.add(family)
                    self._error = "Preview family could not start"
                elif outcome == "active":
                    self._failed_families.discard(family)
                    if not self._failed_families:
                        self._error = None
            else:
                return
            self._revision += 1
            self._wake()

    def _publish(self):
        with self._condition:
            state = self._snapshot()
            callback = self._callback
            if callback is None or state == self._published:
                return
            self._published = state
        try:
            callback(state)
        except Exception:
            # A telemetry/page consumer cannot kill the sole transition owner.
            logger.exception("Preview runtime state callback failed")

    def _action(self):
        # Caller holds the condition. A timed-out stop is retried only after
        # actual host completion, or once to upgrade it to final storage close.
        if self._closed and not self._shutdown:
            return None
        if self._shutdown and not self._final_attempted:
            self._final_attempted = True
            self._stop_waiting = True
            self._pump = "stopping"
            return "stop", True
        if self._stop_ack:
            self._stop_ack = False
            self._stop_waiting = True
            return "stop", self._shutdown
        if self._stop_waiting:
            return None
        if self._owned and not self._needed():
            self._stop_waiting = True
            self._pump = "stopping"
            return "stop", self._shutdown
        if (
            not self._owned
            and self._needed()
            and (self._pump != "failed" or self._retry)
        ):
            self._retry = False
            self._owned = True
            self._pump_epoch += 1
            self._pump = "starting"
            return "start", False
        return None

    def _run(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._dirty)
                self._dirty = False
                action = self._action()
            self._publish()
            if action is not None:
                kind, final = action
                try:
                    if kind == "start":
                        self._host.start()
                    else:
                        stopped = self._host.stop(final=final)
                        with self._condition:
                            if stopped:
                                failed = self._pump == "failed"
                                self._owned = False
                                self._stop_waiting = False
                                self._stop_ack = False
                                self._pump = "failed" if failed else "stopped"
                                self._facts = {
                                    "eve": "stopped",
                                    "companions": "stopped",
                                }
                                self._revision += 1
                                self._dirty = True
                except Exception:
                    logger.exception("Preview runtime %s failed", kind)
                    with self._condition:
                        self._pump = "failed" if kind == "start" else "stopping"
                        self._error = "Preview runtime transition failed"
                        # Retain ownership after exceptions: native/storage
                        # cleanup is not proven just because a call raised.
                        self._revision += 1
            self._publish()
            with self._condition:
                if (
                    self._shutdown
                    and self._final_attempted
                    and not self._owned
                    and not self._stop_waiting
                ):
                    self._done.set()
                    return
