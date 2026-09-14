"""Primary geometry/visibility ownership, independent of native pump liveness.

No callbacks run under this condition. A timeout or final fence cannot retire
work: only its completion owner can finish the exact lease it was handed.
"""

from dataclasses import dataclass
from threading import Condition


@dataclass(frozen=True)
class PrimaryLayoutLease:
    operation_id: int
    exclusive: bool


@dataclass(frozen=True)
class AdmissionState:
    closed: bool
    shared_count: int
    exclusive: bool


class PrimaryLayoutAdmission:
    def __init__(self):
        self._condition = Condition()
        self._closed = False
        self._next_id = 0
        self._leases: dict[int, PrimaryLayoutLease] = {}

    def try_begin(self, *, exclusive: bool) -> PrimaryLayoutLease | None:
        with self._condition:
            if (
                self._closed
                or (exclusive and self._leases)
                or any(lease.exclusive for lease in self._leases.values())
            ):
                return None
            self._next_id += 1
            lease = PrimaryLayoutLease(self._next_id, exclusive)
            self._leases[lease.operation_id] = lease
            return lease

    def owns(self, lease: PrimaryLayoutLease) -> bool:
        with self._condition:
            return self._leases.get(lease.operation_id) is lease

    def finish(self, lease: PrimaryLayoutLease) -> None:
        with self._condition:
            # Identity prevents another owner's numerically equal token from
            # finishing this operation; IDs only claim uniqueness per owner.
            if self._leases.get(lease.operation_id) is lease:
                del self._leases[lease.operation_id]
                self._condition.notify_all()

    def close(self) -> None:
        with self._condition:
            self._closed = True

    def wait_idle(self, timeout: float | None = None) -> bool:
        with self._condition:
            return self._condition.wait_for(lambda: not self._leases, timeout)

    def snapshot(self) -> AdmissionState:
        with self._condition:
            exclusive = any(lease.exclusive for lease in self._leases.values())
            return AdmissionState(
                self._closed, len(self._leases) - int(exclusive), exclusive
            )
