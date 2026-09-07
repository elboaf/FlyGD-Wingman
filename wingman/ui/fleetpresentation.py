"""One coalescing presentation owner, independent of telemetry's dispatcher.

The wakeup is a bit, not a task queue. Api owns the latest display and folds
roster transitions separately, so a stalled WebView costs neither telemetry's
cadence nor the names from intermediate rosters. No native lifecycle operation
belongs on this thread.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from ..settings import validated_fleet_bar

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FleetDelivery:
    """Concrete targets and local ordering captured before any blocking stage."""

    activation: int
    revision: int
    main: object
    sigbar: object
    fleetbar: object


@dataclass(frozen=True)
class RosterWrite:
    version: int
    priority: tuple[str, ...]
    pending: tuple[str, ...]


class RosterMemory:
    """Fold transitions, not snapshots; caller holds Api's presentation lock.

    Within an unacknowledged batch, current names move to the front, sorted
    within each transition. Fold the existing seen normalization at every
    transition: cap overflow has pending priority on the NEXT transition,
    ahead of that logical seen tier. Separately, actual failed/cap-excluded
    names remain in insertion-ordered pending memory, ahead of persisted
    memory on retry. There are no fictional disk successes for skipped
    writes: only an actual successful candidate acknowledges pending names.
    Its existing uncapped configurability is intentional; storage grows with
    distinct unacknowledged names, never with the number of snapshots.

    Admission versions protect a name seen again during an in-flight save:
    that older candidate cannot acknowledge the new admission, even if it
    happened to contain the same spelling.
    """

    def __init__(self) -> None:
        self.pending: dict[str, int] = {}
        self._priority: dict[str, int] = {}
        self._overflow: dict[str, int] = {}
        self._version = 0
        self._dirty = False

    def admit(self, names: Iterable[str]) -> None:
        self._version += 1
        names = tuple(names)
        current = set(names)
        for name in names:
            self.pending[name] = self._version
        waiting = dict.fromkeys([*self._overflow, *names])
        priority = validated_fleet_bar(
            {
                "seen": list(
                    dict.fromkeys(
                        [
                            *sorted(current, key=lambda name: (name.casefold(), name)),
                            *waiting,
                            *self._priority,
                        ]
                    )
                )
            }
        )["seen"]
        # Priority age is NOT admission age: cap overflow can be promoted
        # by a later empty roster without admitting that name again. An older
        # save may acknowledge membership, but cannot erase that promotion.
        self._priority = {
            name: self._version if name in waiting else self._priority[name]
            for name in priority
        }
        self._overflow = {
            name: self.pending[name] for name in waiting if name not in self._priority
        }
        self._dirty = True

    def take(self) -> RosterWrite | None:
        if not self._dirty:
            return None
        self._dirty = False
        return RosterWrite(self._version, tuple(self._priority), tuple(self.pending))

    def acknowledge(self, write: RosterWrite, saved: list[str] | None) -> None:
        self._priority = {
            name: version
            for name, version in self._priority.items()
            if version > write.version
        }
        if saved is not None:
            retained = set(saved)
            self.pending = {
                name: version
                for name, version in self.pending.items()
                if name not in retained or version > write.version
            }
        # Only a real acknowledgement resets the batch's retry tier. Logical
        # cap folding above never removes a name from actual pending memory.
        self._overflow = {
            name: version
            for name, version in self.pending.items()
            if name not in self._priority
        }


class FleetPresentationWorker:
    """Single daemon worker with bounded stop and retained timed-out ownership.

    An entered WebView call cannot be cancelled. Api invalidates delivery and
    detaches before stop(); the daemon lets process exit proceed if native
    code never returns. A timeout is NOT completion or permission to start a
    second owner. No callback or join runs under the worker lifecycle lock.
    """

    def __init__(
        self,
        present: Callable[[], None],
        *,
        thread_factory: Callable[..., threading.Thread] = threading.Thread,
    ) -> None:
        self._present = present
        self._thread_factory = thread_factory
        self._lock = threading.Lock()
        self._iteration_lock = threading.Lock()
        self._pending = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._running = False

    def notify(self) -> None:
        self._pending.set()

    def start(self) -> bool:
        with self._lock:
            if self._running:
                return True
            if self._thread is not None and self._thread.is_alive():
                return False
            stop = threading.Event()
            self._stop = stop
            try:
                thread = self._thread_factory(
                    target=self._run,
                    args=(stop,),
                    name="fleet-presentation",
                    daemon=True,
                )
                self._thread = thread
                thread.start()
            except Exception:
                logger.exception("Could not start Fleet presentation worker")
                self._thread = None
                return False
            self._running = True
            return True

    def stop(self, timeout: float = 1.0) -> bool:
        with self._lock:
            thread = self._thread
            self._running = False
            self._stop.set()
            self._pending.set()
        if thread is None:
            return True
        thread.join(timeout)
        with self._lock:
            if thread.is_alive():
                return False
            # A concurrent starter after this thread exited owns its own
            # reference; an older stop must not erase it.
            if self._thread is thread:
                self._thread = None
            return True

    def _run(self, stop: threading.Event) -> None:
        while True:
            self._pending.wait()
            if stop.is_set():
                return
            with self._iteration_lock:
                self._iterate()

    def _iterate(self) -> None:
        if not self._pending.is_set():
            return
        self._pending.clear()
        try:
            self._present()
        except Exception:
            logger.exception("Fleet presentation failed")

    def iterate_once(self) -> None:
        """Deterministic drain, like FleetSharingWorker.iterate_once()."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError("iterate_once cannot run beside Fleet presentation")
        with self._iteration_lock:
            self._iterate()
