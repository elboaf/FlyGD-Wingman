"""Pure operation selection for FleetSharingWorker, not another owner or timer.

All signed operations consume the same revision; publication alone has a separate
cadence bucket. Completion deadlines include failures and obsolete replies. Two
ordinary controls at most may overtake the oldest overdue periodic class.
"""

from dataclasses import dataclass
from types import MappingProxyType

SIGNED_INTERVAL_S = 0.5

OPERATIONS = MappingProxyType(
    {
        "publish_snapshot": "publication",
        "fetch_device": "read",
        "acknowledge_capabilities": "read",
        "set_participation": "read",
        "fetch_sources": "read",
        "control_source": "read",
        "fetch_catalogue": "read",
        "fetch_eligibility": "read",
        "read_snapshot": "read",
        "renew_session": "read",
        "begin_pairing": "bootstrap",
        "complete_pairing": "bootstrap",
        "begin_recovery": "bootstrap",
        "complete_recovery": "bootstrap",
    }
)


@dataclass(frozen=True)
class Work:
    operation: str
    key: str
    due: float = 0.0
    priority: int = 2
    periodic: bool = False
    payload: object = None


class Scheduler:
    def __init__(self):
        self.deadlines = dict.fromkeys(set(OPERATIONS.values()), 0.0)
        self.retry_at: dict[str, float] = {}
        self.failures: dict[str, int] = {}
        self._controls = 0
        self._served: dict[str, float] = {}

    def retain(self, prefix: str, keys: set[str]):
        """Retire command-owned history without erasing shared bucket deadlines."""
        for metadata in (self.retry_at, self.failures, self._served):
            for key in tuple(metadata):
                if key.startswith(prefix) and key not in keys:
                    del metadata[key]

    def choose(self, work: tuple[Work, ...], now: float) -> Work | None:
        ready = [
            w
            for w in work
            if now
            >= max(
                w.due,
                self.deadlines[OPERATIONS[w.operation]],
                self.retry_at.get(w.key, 0),
            )
        ]
        if not ready:
            return None
        critical = [w for w in ready if w.priority < 2]
        if critical:
            return min(critical, key=lambda w: (w.priority, w.due))
        periodic = [w for w in ready if w.periodic]
        controls = [w for w in ready if not w.periodic]
        if periodic and (self._controls >= 2 or not controls):
            return min(periodic, key=lambda w: (w.due, self._served.get(w.key, 0)))
        return min(controls, key=lambda w: w.due)

    def completed(
        self, work: Work, now: float, *, failed: bool = False, jitter: float = 0
    ):
        bucket = OPERATIONS[work.operation]
        self.deadlines[bucket] = now + (
            1.0 if bucket == "bootstrap" else SIGNED_INTERVAL_S
        )
        if failed:
            count = min(6, self.failures.get(work.key, 0) + 1)
            self.failures[work.key] = count
            delay = min(30.0, 2.0 ** (count - 1)) + jitter
            self.retry_at[work.key] = now + delay
            # 429 has no Retry-After. Isolate to this work/bucket, never stall
            # publication behind a source capacity refusal or read cadence.
            self.deadlines[bucket] = max(
                self.deadlines[bucket], now + SIGNED_INTERVAL_S
            )
        else:
            self.failures.pop(work.key, None)
            self.retry_at.pop(work.key, None)
        if work.periodic:
            self._served[work.key] = now
        # A publication opportunity is independent of read-slot fairness. In
        # particular it must not reset the budget and let an endless control
        # burst starve overdue catalogue/eligibility/read classes.
        if bucket == "read":
            if work.periodic:
                self._controls = 0
            elif work.priority >= 2:
                self._controls += 1
