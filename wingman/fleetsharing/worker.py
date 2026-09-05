"""Non-blocking coalescing publisher between the coordinator and the relay.

`TelemetryCoordinator.subscribe_fleet` delivers every completed
`FleetSnapshot` on its OWN dispatcher thread, and that thread also owns the
one-second cadence every other consumer (Preview, Alerts, the Fleet Bar
window) depends on. `FleetSharingWorker.submit` is the only thing the
coordinator ever calls: it swaps an immutable "latest" reference under a
small lock and sets an `Event`, nothing else -- no HTTP, no signing, no
DPAPI, no disk read. A relay that is slow, down, or blocked mid-request
therefore costs this worker's own publication, never the coordinator's
cadence or local DPS decay.

Everything that actually touches the network -- device-state loading, key
unwrapping, catalogue refresh, sparse projection, revision allocation,
signing (inside `wingman.fleetsharing.client.FleetRelayClient`), and
retry/backoff -- runs on this module's OWN non-daemon worker thread, one
iteration at a time, serialized against the deterministic `iterate_once`
test seam by `_iteration_lock` (mirroring
`TelemetryCoordinator._dispatch_lock`/`dispatch_once`).

Revision handling
------------------
Every signed request this worker sends -- both `fetch_catalogue` and
`publish_snapshot` -- consumes a freshly incremented revision, whether or
not the attempt succeeds. A retry after a failed or uncertain attempt
therefore always carries a NEW revision and a freshly signed request; it
never resends the previous attempt's exact signed bytes, matching
`client.py`'s own reasoning for never retrying a publish internally (a
signed publish's revision is strictly increasing, so replaying an
unknown-delivery request risks a duplicate write). The revision sequence
restarts at zero only when the device session id itself changes (a fresh
pairing), matching "a new session starts a new revision sequence" from the
design.

Coalescing
----------
`submit` overwrites a single mutable "latest" slot -- there is no queue of
snapshots, so three rapid submissions collapse to whichever was latest by
the time the worker thread is free to look. The projected publish rows
are also compared against the last rows this worker actually sent: an
unchanged projection is never re-sent, but any change -- including a
transition to an empty row list -- is sent immediately, so a normal local
omission withdraws its remote row promptly rather than waiting out a
cadence.

Status
------
`status()` reports one of `SharingStatus.state`'s six values, updated by
this worker's own thread as it moves through a pass: `"stopped"` while
unpaired, `"connecting"` on a session's first-ever contact attempt,
`"verifying"` on a later periodic catalogue refresh, `"active"` once the
catalogue is current and any owed publish has succeeded, `"refused"` after
a `forbidden`/`unauthorized` relay response (eligibility or the device
session itself may be gone -- the cached catalogue is discarded so the
next successful contact re-verifies it from scratch), and `"error"` for
every other relay/transport/protocol failure. Every failure enters a
bounded exponential backoff with jitter before the next attempt; a success
resets it.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from ..telemetry.model import FleetSnapshot
from . import projection
from . import state as state_mod
from .client import FleetRelayClient, FleetRelayError
from .model import FleetCatalogue, PublishRow

logger = logging.getLogger(__name__)

# Bounded exponential backoff (with jitter) for any failed relay contact --
# a 429, a 403/401, a network failure, or a malformed/protocol-mismatched
# response are all paced identically here: none of them expose a
# server-supplied Retry-After value to this layer (`client.py`'s
# `FleetRelayError` deliberately carries only a coarse `.code`, never
# response headers or body), so this worker paces every failure class with
# its own ladder rather than trusting a value it cannot safely read.
BASE_BACKOFF_S = 1.0
MAX_BACKOFF_S = 30.0

# The design's own "bounded one-second cadence" for a healthy poll/publish
# loop -- also the idle wake interval so a catalogue-refresh interval or a
# newly-unpaired transition is noticed promptly even with no new submit().
IDLE_POLL_S = 1.0

# How often an established session refreshes its device catalogue even
# with no relay-side push to signal a change (a linked-character add,
# rename, or removal). The design calls this refresh mandatory ("a
# catalogue revision change ... forces a refresh") but names no cadence;
# one minute bounds how long a stale link can misroute or drop a row
# without hammering the relay every publish cycle.
CATALOGUE_REFRESH_INTERVAL_S = 60.0


@dataclass(frozen=True)
class SharingStatus:
    """The sharing worker's current, UI-facing state.

    `detail` is always a fixed classification string (a `FleetRelayError`
    `.code`, or a short fixed phrase) -- never a raw response body, a
    session id, or anything else server-controlled, matching every other
    redacted-error posture in this subpackage.
    """

    state: Literal["stopped", "connecting", "active", "verifying", "refused", "error"]
    detail: str | None = None


def _noop_thread_factory(
    *, target: Callable, args: tuple, name: str, daemon: bool
) -> threading.Thread:
    """Test seam: return a Thread-shaped object that never starts."""

    class _NoopThread:
        def __init__(self) -> None:
            self.daemon = daemon

        def start(self) -> None:
            pass

        def is_alive(self) -> bool:
            return False

        def join(self, timeout: float | None = None) -> None:
            pass

    return _NoopThread()  # type: ignore[return-value]


def _real_thread_factory(
    *, target: Callable, args: tuple, name: str, daemon: bool
) -> threading.Thread:
    return threading.Thread(target=target, args=args, name=name, daemon=daemon)


class FleetSharingWorker:
    """One device's non-blocking publisher.

    Public interface:
        submit(snapshot) -> None      -- non-blocking, coordinator callback
        start() -> bool
        stop(timeout=5.0) -> bool
        status() -> SharingStatus
        iterate_once()                -- deterministic test seam

    *load_state* is read live on every iteration (never captured), matching
    every other settings/state read in this codebase: a future pairing
    feature can populate `wingman.fleetsharing.state`'s document at any
    time, and this worker must notice on its very next pass rather than on
    a restart. *client_factory(origin) -> relay client* builds the signed
    transport for the paired relay origin; production wiring supplies
    `FleetRelayClient` itself, tests supply a fake. *unwrap_private_key*
    defaults to `wingman.fleetsharing.state.unwrap_private_key` (the DPAPI
    seam); it is only ever reached once a persisted device identity
    actually exists, which no code path in this tracer writes yet.
    """

    def __init__(
        self,
        *,
        load_state: Callable[[], state_mod.SharingState],
        client_factory: Callable[[str], object] = FleetRelayClient,
        unwrap_private_key: Callable[
            [str], bytes | None
        ] = state_mod.unwrap_private_key,
        _thread_factory: Callable[..., threading.Thread] = _real_thread_factory,
        _clock: Callable[[], float] = time.monotonic,
        _jitter: Callable[[], float] = random.random,
    ) -> None:
        self._load_state = load_state
        self._client_factory = client_factory
        self._unwrap_private_key = unwrap_private_key
        self._thread_factory = _thread_factory
        self._clock = _clock
        self._jitter = _jitter

        # submit()'s one-slot mailbox. Never touched by anything but
        # submit() and the read inside _iterate(): no network, crypto, or
        # DPAPI call may ever happen under this lock.
        self._lock = threading.Lock()
        self._latest: FleetSnapshot | None = None
        self._pending = threading.Event()

        self._status_lock = threading.Lock()
        self._status = SharingStatus(state="stopped")

        # Dispatcher-thread-only state (serialized by _iteration_lock
        # against the real worker and the iterate_once() test seam, never
        # touched by submit()).
        self._iteration_lock = threading.Lock()
        self._session_id: str | None = None
        self._revision = 0
        self._catalogue: FleetCatalogue | None = None
        self._catalogue_refreshed_at: float | None = None
        self._last_published: tuple[PublishRow, ...] = ()
        self._backoff = 0.0
        self._client = None
        self._client_origin: str | None = None

        self._lifecycle_lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._running = False
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Coordinator-facing callback
    # ------------------------------------------------------------------

    def submit(self, snapshot: FleetSnapshot) -> None:
        """Record the newest fleet snapshot and wake the worker.

        Called on `TelemetryCoordinator`'s own dispatcher thread. Must
        never block: swapping a reference and setting an `Event` is the
        entire cost, so a relay stuck mid-request never stalls the
        coordinator's one-second cadence for anyone else.
        """
        with self._lock:
            self._latest = snapshot
        self._pending.set()

    def status(self) -> SharingStatus:
        with self._status_lock:
            return self._status

    def _set_status(self, status: SharingStatus) -> None:
        with self._status_lock:
            self._status = status

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> bool:
        """Start the non-daemon worker thread. Idempotent.

        Refuses with `False` while a previous timed-out `stop()`'s worker
        is still alive, mirroring `GameLogStream.start`/
        `TelemetryCoordinator._start_dispatcher`.
        """
        with self._lifecycle_lock:
            if self._running:
                return True
            if self._worker is not None and self._worker.is_alive():
                return False
            self._running = True
            self._stop_event = threading.Event()
            stop_ev = self._stop_event
            try:
                worker = self._thread_factory(
                    target=self._run,
                    args=(stop_ev,),
                    name="fleet-sharing-worker",
                    daemon=False,
                )
                self._worker = worker
                worker.start()
            except Exception:
                logger.exception("Could not start fleet sharing worker")
                self._running = False
                self._worker = None
                return False
            return True

    def stop(self, timeout: float = 5.0) -> bool:
        """Stop the worker and report bounded completion.

        A request already in flight cannot be interrupted -- there is no
        way to cancel a blocking `urllib` call -- so a timed-out join
        leaves the worker reference intact for a caller to retry, exactly
        like `TelemetryCoordinator.stop`/`GameLogStream.stop`. `False`
        here must never be treated as "sharing stopped".
        """
        with self._lifecycle_lock:
            worker = self._worker
            stop_ev = self._stop_event
            self._running = False
        if worker is None:
            return True
        stop_ev.set()
        # Wakes an idle wait immediately; a request already blocked inside
        # the relay client cannot be woken by this, which is exactly what
        # makes the bound below observable instead of silent.
        self._pending.set()
        worker.join(timeout)
        with self._lifecycle_lock:
            if worker.is_alive():
                return False
            self._worker = None
        return True

    def _run(self, stop_event: threading.Event) -> None:
        wait_s = 0.0
        while not stop_event.is_set():
            self._pending.wait(wait_s)
            if stop_event.is_set():
                return
            self._pending.clear()
            with self._iteration_lock:
                wait_s = self._iterate()

    def iterate_once(self) -> None:
        """Drive one iteration synchronously. Deterministic test seam.

        Mirrors `TelemetryCoordinator.dispatch_once`: refuses to run
        beside a live worker thread, since both would mutate revision/
        catalogue state concurrently.
        """
        with self._lifecycle_lock:
            worker_alive = self._worker is not None and self._worker.is_alive()
        if worker_alive:
            raise RuntimeError("iterate_once cannot run beside the sharing worker")
        with self._iteration_lock:
            self._iterate()

    # ------------------------------------------------------------------
    # One pass: caller owns _iteration_lock
    # ------------------------------------------------------------------

    def _iterate(self) -> float:
        sharing_state = self._safe_load_state()
        if not self._is_paired(sharing_state):
            self._enter_stopped()
            return IDLE_POLL_S

        private_key = self._safe_unwrap(
            sharing_state.identity.protected_private_key_b64
        )
        if private_key is None:
            self._set_status(
                SharingStatus(state="error", detail="device key unavailable")
            )
            return self._enter_backoff()

        if sharing_state.session_id != self._session_id:
            # A fresh pairing (or a first-ever load): the revision sequence
            # and any cached catalogue/published rows belong to no session
            # this worker has ever authenticated as.
            self._begin_session(sharing_state.session_id)

        client = self._client_for(sharing_state.relay_origin)

        if self._catalogue_needs_refresh() and not self._refresh_catalogue(
            client, sharing_state.session_id, private_key
        ):
            return self._enter_backoff()

        with self._lock:
            latest = self._latest

        if latest is not None:
            rows = projection.project_snapshot(latest, self._catalogue)
            if rows != self._last_published:
                if not self._publish(
                    client, sharing_state.session_id, private_key, rows
                ):
                    return self._enter_backoff()
                self._last_published = rows

        self._set_status(SharingStatus(state="active"))
        self._backoff = 0.0
        return IDLE_POLL_S

    @staticmethod
    def _is_paired(sharing_state: state_mod.SharingState | None) -> bool:
        return (
            sharing_state is not None
            and sharing_state.identity is not None
            and bool(sharing_state.relay_origin)
            and bool(sharing_state.session_id)
        )

    def _enter_stopped(self) -> None:
        if self._session_id is not None:
            self._begin_session(None)
        self._set_status(SharingStatus(state="stopped"))
        self._backoff = 0.0

    def _begin_session(self, session_id: str | None) -> None:
        self._session_id = session_id
        self._revision = 0
        self._catalogue = None
        self._catalogue_refreshed_at = None
        # () rather than None: a fresh session has no rows on the relay to
        # withdraw yet, so an equally-empty first projection must not cost
        # a network call. Any NON-empty first projection still counts as
        # "changed" against this baseline and is sent immediately.
        self._last_published = ()

    def _client_for(self, origin: str):
        if self._client is None or self._client_origin != origin:
            self._client = self._client_factory(origin)
            self._client_origin = origin
        return self._client

    def _catalogue_needs_refresh(self) -> bool:
        if self._catalogue is None or self._catalogue_refreshed_at is None:
            return True
        return (
            self._clock() - self._catalogue_refreshed_at
        ) >= CATALOGUE_REFRESH_INTERVAL_S

    def _refresh_catalogue(self, client, session_id: str, private_key: bytes) -> bool:
        # "verifying" for a periodic re-check of an already-established
        # session; "connecting" the first time this session has ever
        # reached the relay (no catalogue yet at all).
        self._set_status(
            SharingStatus(
                state="verifying" if self._catalogue is not None else "connecting"
            )
        )
        self._revision += 1
        try:
            catalogue = client.fetch_catalogue(
                session_id=session_id, private_key=private_key, revision=self._revision
            )
        except FleetRelayError as exc:
            self._handle_relay_error(exc)
            return False
        except Exception:
            logger.exception("Fleet sharing catalogue fetch failed unexpectedly")
            self._set_status(SharingStatus(state="error", detail="unexpected failure"))
            return False
        self._catalogue = catalogue
        self._catalogue_refreshed_at = self._clock()
        return True

    def _publish(
        self,
        client,
        session_id: str,
        private_key: bytes,
        rows: tuple[PublishRow, ...],
    ) -> bool:
        self._revision += 1
        try:
            client.publish_snapshot(
                session_id=session_id,
                private_key=private_key,
                revision=self._revision,
                rows=rows,
            )
        except FleetRelayError as exc:
            self._handle_relay_error(exc)
            return False
        except Exception:
            logger.exception("Fleet sharing publish failed unexpectedly")
            self._set_status(SharingStatus(state="error", detail="unexpected failure"))
            return False
        return True

    def _handle_relay_error(self, exc: FleetRelayError) -> None:
        logger.warning("Fleet sharing relay request failed: %s", exc.code)
        if exc.code in ("forbidden", "unauthorized"):
            self._set_status(SharingStatus(state="refused", detail=exc.code))
            # Eligibility or the device session itself may be gone; a
            # stale catalogue must not keep matching rows against links
            # that no longer hold, so the next successful contact
            # re-verifies it from scratch rather than trusting the cache.
            self._catalogue = None
            self._catalogue_refreshed_at = None
        else:
            self._set_status(SharingStatus(state="error", detail=exc.code))

    def _enter_backoff(self) -> float:
        self._backoff = min(
            MAX_BACKOFF_S, self._backoff * 2 if self._backoff else BASE_BACKOFF_S
        )
        return self._backoff + self._jitter() * BASE_BACKOFF_S

    def _safe_load_state(self) -> state_mod.SharingState | None:
        try:
            return self._load_state()
        except Exception:
            logger.exception("Could not load fleet sharing state")
            return None

    def _safe_unwrap(self, blob: str) -> bytes | None:
        try:
            return self._unwrap_private_key(blob)
        except Exception:
            logger.exception("Could not unwrap the fleet sharing device key")
            return None


__all__ = ["FleetSharingWorker", "SharingStatus"]
