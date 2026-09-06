"""Non-blocking coalescing publisher between the coordinator and the relay.

`TelemetryCoordinator.subscribe_fleet` delivers every completed
`FleetSnapshot` on its OWN dispatcher thread, and that thread also owns the
one-second cadence every other consumer (Preview, Alerts, the Fleet Bar
window) depends on. `FleetSharingWorker.submit` is the only thing the
coordinator ever calls: it swaps an immutable "latest" reference (with its
own submission timestamp) under a small lock and sets an `Event`, nothing
else -- no HTTP, no signing, no DPAPI, no disk read. A relay that is slow,
down, or blocked mid-request therefore costs this worker's own
publication, never the coordinator's cadence or local DPS decay.

Everything that actually touches the network -- device-state loading, key
unwrapping, catalogue refresh, sparse projection, revision allocation,
signing (inside `wingman.fleetsharing.client.FleetRelayClient`), and
retry/backoff -- runs on this module's OWN non-daemon worker thread, one
iteration at a time, serialized against the deterministic `iterate_once`
test seam by `_iteration_lock` (mirroring
`TelemetryCoordinator._dispatch_lock`/`dispatch_once`).

Gating
------
`sharing_enabled()` is read live, fail-closed, before anything else this
worker's own thread does: a raised exception or a `False` result skips
`load_state()` entirely (no disk stat/read at all) and enters the same
inert "stopped" state an unpaired device reports, at a slow
`INERT_POLL_S` cadence rather than the healthy one-second poll. Production
wiring (`wingman.__main__.build_fleet_sharing_worker`) additionally never
calls `start()` at all while the setting is off, so a disabled install
never spawns this thread in the first place; the live predicate here is
defence in depth for whatever calls `start()` anyway (every existing test
that constructs this worker directly, and any future toggle that flips
the setting without a restart).

Revision handling
------------------
Every signed request this worker sends -- `fetch_catalogue`,
`publish_snapshot`, AND `renew_session` alike -- consumes a freshly
incremented revision, whether or not the attempt succeeds, and that new
revision is PERSISTED (via `save_state`, into
`wingman.fleetsharing.state.SharingState.last_revision`) BEFORE the
network call is ever made -- never after. All three draw from the exact
SAME sequence, never one each: authGD's own fleet-v1 protocol shares one
monotonic `last_revision` counter per session across every signed request
kind, and a client that let two of them race in flight at once could see
its own strictly-increasing revision refused purely by commit order
(`docs/fleet-protocol.md`, authGD repo) -- which is exactly why this
worker's single `_iterate()` pass runs catalogue refresh, session
renewal, and publish strictly one at a time, serialized by
`_iteration_lock`, rather than any two of them ever running concurrently.
A crash between the persisted write and the network reply can only waste
one revision number, never reuse one authGD may already have seen;
persisting only after a reply would risk exactly that reuse across a
restart. A retry after a failed or uncertain attempt therefore always
carries a NEW revision and a freshly signed request; it never resends the
previous attempt's exact signed bytes, matching `client.py`'s own
reasoning for never retrying a publish internally. The in-memory sequence
resumes from the persisted `last_revision` the first time THIS PROCESS
observes a given session id (a genuine restart with the same still-valid
session), and restarts at zero only when the session id actually changes
during THIS process's own lifetime (a fresh pairing), matching "a new
session starts a new revision sequence" from the design. If persisting the
new revision fails, the network call is skipped entirely for that pass and
the failure is treated like any other relay error (status `"error"`,
bounded backoff) rather than proceeding with an unpersisted revision.

Session renewal
----------------
`PUT /api/fleet/v1/session` extends this device's OWN session in place
without a new browser approval, on a fixed `SESSION_RENEWAL_INTERVAL_S`
cadence checked every pass (`_session_needs_renewal`) -- comfortably under
authGD's own 30-minute session TTL, so a healthy device never sees that
cliff. This worker never tracks the `expires_at` authGD's response
reports: like `CATALOGUE_REFRESH_INTERVAL_S`, renewal runs on its own
fixed schedule rather than one derived from a server-reported value, which
would need this worker to trust its own clock against authGD's. Checked
(and, if due, sent) BEFORE catalogue refresh and publish in every pass --
still just one more sequential step in the same single-file pass every
other signed request already goes through, never a concurrent one.

Coalescing, staleness, and heartbeats
--------------------------------------
`submit` overwrites a single mutable "latest" slot together with the
monotonic time it was submitted -- there is no queue of snapshots, so
three rapid submissions collapse to whichever was latest by the time the
worker thread is free to look. A submission older than
`MAX_SNAPSHOT_AGE_S` by the time this worker gets to it is dropped rather
than published: local combat state moves fast (a `SCRAM/POINT` or a
non-zero DPS reading can end within a second), and this worker's own
publish cadence can lag behind submission (backoff, an inert poll while
unpaired) for far longer than that -- publishing a snapshot that old would
risk re-arming a remote row with a value nobody currently believes is
true. A dropped snapshot is simply treated as "nothing new to publish"
this pass, exactly like an idle cycle with no submission at all; it never
forces a withdrawal either, matching the design's own "a network loss does
not [clear rows]" posture generalized to a local data gap.

The projected publish rows are also compared against the last rows this
worker actually sent: an unchanged projection is not re-sent on every
pass, but any CHANGE -- including a transition to an empty row list -- is
sent immediately, so a normal local omission withdraws its remote row
promptly rather than waiting out a cadence. An UNCHANGED but NON-EMPTY
projection is still re-sent as a heartbeat at least every
`HEARTBEAT_INTERVAL_S` (safely under authGD's own three-second staleness
boundary): the design's server-clock liveness rule ages a row to `stale`
by three seconds of receive-time inactivity even when nothing about the
underlying combat state has changed, so a steady, unchanging fight would
otherwise flicker stale/live under readers' own eyes for no reason. An
empty (already-withdrawn) projection never needs a heartbeat -- there is
nothing left on the relay to keep alive.

Status
------
`status()` reports one of `SharingStatus.state`'s six values, updated by
this worker's own thread as it moves through a pass: `"stopped"` while
disabled or unpaired, `"connecting"` on a session's first-ever contact
attempt, `"verifying"` on a later periodic catalogue refresh, `"refused"`
after a `forbidden`/`unauthorized` relay response (eligibility or the
device session itself may be gone -- the cached catalogue is discarded so
the next successful contact re-verifies it from scratch), and `"error"`
for every other relay/transport/protocol failure, INCLUDING a relay
client that could not even be constructed for the paired origin (a
corrupted or malformed `relay_origin` reports `"error"` and backs off; it
never raises out of this worker's own loop). `"active"` is reported ONLY
immediately following a pass that made real, successful relay contact
(a catalogue fetch or a publish/heartbeat) -- never asserted merely
because a pass happened to raise no exception. A pass that had nothing
due (catalogue fresh, nothing changed, no heartbeat owed) makes no status
claim of its own and simply leaves whatever was last reported in place.
Every failure enters a bounded exponential backoff with jitter before the
next attempt, and that backoff (like the inert disabled/unpaired poll) is
enforced against an actual wall-clock deadline: a steady stream of
`submit()` calls during backoff wakes the loop but does not let it
retry early, only a genuinely elapsed deadline (or `stop()`) does.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
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
# newly-paired transition is noticed promptly even with no new submit().
IDLE_POLL_S = 1.0

# While disabled (fleet_sharing.enabled is false) or unpaired: there is
# nothing useful this worker can do but watch for that to change, and
# doing so every second forever -- a disk stat/read on every single pass,
# for the overwhelming majority of real installs, which ship no pairing UI
# at all -- is needless work this worker does not need to perform that
# often. Slower than IDLE_POLL_S, but still bounded so a future pairing
# completing (or the setting being turned on) is noticed within seconds,
# not forgotten.
INERT_POLL_S = 15.0

# How often an established session refreshes its device catalogue even
# with no relay-side push to signal a change (a linked-character add,
# rename, or removal). The design calls this refresh mandatory ("a
# catalogue revision change ... forces a refresh") but names no cadence;
# one minute bounds how long a stale link can misroute or drop a row
# without hammering the relay every publish cycle.
CATALOGUE_REFRESH_INTERVAL_S = 60.0

# How often an established session renews itself in place (`PUT
# /api/fleet/v1/session`) without waiting for a browser to re-approve it.
# authGD's own session TTL (`DEVICE_SESSION_TTL_MS`, fleet-pairing.ts) is
# 30 minutes; ten comfortably clears that with margin to spare for a
# missed cycle or two (backoff, a slow relay) before the session would
# actually lapse. Renewal counts as real relay contact for `_iterate_inner`'s
# "active" status rule, and consumes a revision from the SAME shared
# sequence catalogue/publish already use (`docs/fleet-protocol.md`, authGD
# repo) -- never a sequence of its own.
SESSION_RENEWAL_INTERVAL_S = 600.0

# A submitted snapshot older than this by the time this worker gets around
# to it is never published -- see the module docstring's "Coalescing,
# staleness, and heartbeats" section. Comfortably above IDLE_POLL_S (a
# submission arrives roughly every second in healthy operation, so this
# never fires under ordinary conditions) and comfortably below authGD's
# own ten-second hard-expiry, so a snapshot old enough to be refused here
# would already be close to expiring server-side even if it had been sent.
MAX_SNAPSHOT_AGE_S = 5.0

# An unchanged, non-empty publication is re-sent no less often than this,
# safely under authGD's own three-second stale boundary (design: "live for
# the first 3 seconds, stale through 10 seconds"). Two full idle-poll
# cycles of slack rather than an exact 2.9s -- this only needs to beat the
# server's OWN clock, not this worker's.
HEARTBEAT_INTERVAL_S = 2.0


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


def _no_op_save_state(_state: state_mod.SharingState) -> None:
    """Default `save_state`: revision persistence becomes a no-op.

    Production wiring always supplies a real writer
    (`wingman.fleetsharing.state.save`, bound to
    `paths.fleet_sharing_file()`); tests that do not care about
    cross-restart revision recovery can omit it entirely and keep their
    existing construction unchanged.
    """


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
    a restart. *save_state* is the symmetric write seam used to persist an
    about-to-be-used revision before it is ever sent (see the module
    docstring's "Revision handling"). *client_factory(origin) -> relay
    client* builds the signed transport for the paired relay origin;
    production wiring supplies `FleetRelayClient` itself, tests supply a
    fake -- a `client_factory` that raises for a malformed origin reports
    `"error"` status and backs off rather than propagating out of this
    worker's loop. *unwrap_private_key* defaults to
    `wingman.fleetsharing.state.unwrap_private_key` (the DPAPI seam); it is
    only ever reached once a persisted device identity actually exists.
    *sharing_enabled* defaults to always-true, matching every existing
    caller's expectations; production wiring supplies a live
    `fleet_sharing.enabled` settings read.
    """

    def __init__(
        self,
        *,
        load_state: Callable[[], state_mod.SharingState],
        client_factory: Callable[[str], object] = FleetRelayClient,
        unwrap_private_key: Callable[
            [str], bytes | None
        ] = state_mod.unwrap_private_key,
        sharing_enabled: Callable[[], bool] = lambda: True,
        save_state: Callable[[state_mod.SharingState], None] = _no_op_save_state,
        _thread_factory: Callable[..., threading.Thread] = _real_thread_factory,
        _clock: Callable[[], float] = time.monotonic,
        _jitter: Callable[[], float] = random.random,
    ) -> None:
        self._load_state = load_state
        self._client_factory = client_factory
        self._unwrap_private_key = unwrap_private_key
        self._sharing_enabled = sharing_enabled
        self._save_state = save_state
        self._thread_factory = _thread_factory
        self._clock = _clock
        self._jitter = _jitter

        # submit()'s one-slot mailbox: (snapshot, submitted-at monotonic
        # time). Never touched by anything but submit() and the read
        # inside _iterate(): no network, crypto, or DPAPI call may ever
        # happen under this lock.
        self._lock = threading.Lock()
        self._latest: tuple[FleetSnapshot, float] | None = None
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
        self._session_renewed_at: float | None = None
        self._last_published: tuple[PublishRow, ...] = ()
        self._last_publish_at: float | None = None
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
            self._latest = (snapshot, self._clock())
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
        # Wakes an idle/backoff/inert wait immediately regardless of the
        # deadline it is honouring; a request already blocked inside the
        # relay client cannot be woken by this, which is exactly what
        # makes the bound below observable instead of silent.
        self._pending.set()
        worker.join(timeout)
        with self._lifecycle_lock:
            if worker.is_alive():
                return False
            self._worker = None
        return True

    def _run(self, stop_event: threading.Event) -> None:
        deadline = self._clock()
        interruptible = True
        while not stop_event.is_set():
            remaining = deadline - self._clock()
            while remaining > 0 and not stop_event.is_set():
                woke = self._pending.wait(remaining)
                if stop_event.is_set():
                    return
                if woke:
                    self._pending.clear()
                    if interruptible:
                        # A healthy idle-poll wait: a fresh submission is
                        # itself the reason to look again right away.
                        remaining = 0.0
                        break
                    # A backoff or inert (disabled/unpaired) wait: a
                    # steady stream of submissions must not collapse this
                    # deadline to zero -- keep waiting out what is left.
                remaining = deadline - self._clock()
            if stop_event.is_set():
                return
            self._pending.clear()
            with self._iteration_lock:
                wait_s, interruptible = self._iterate()
            deadline = self._clock() + wait_s

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

    def _iterate(self) -> tuple[float, bool]:
        """Run one pass, converting any unexpected exception into a bounded
        backoff rather than letting it kill this worker's own thread --
        the same "a corrupted or unreachable relay costs a retry, not a
        crash" posture already applied to every specific failure below,
        extended here as a last-resort net around the whole pass (a
        malformed `relay_origin` reaching `_client_factory`, in
        particular, is exactly the kind of failure this net exists for).
        """
        try:
            return self._iterate_inner()
        except Exception:
            logger.exception("Fleet sharing worker iteration failed unexpectedly")
            self._set_status(SharingStatus(state="error", detail="unexpected failure"))
            return self._enter_backoff()

    def _iterate_inner(self) -> tuple[float, bool]:
        if not self._safe_sharing_enabled():
            self._enter_stopped()
            return INERT_POLL_S, False

        sharing_state = self._safe_load_state()
        if not self._is_paired(sharing_state):
            self._enter_stopped()
            return INERT_POLL_S, False

        private_key = self._safe_unwrap(
            sharing_state.identity.protected_private_key_b64
        )
        if private_key is None:
            self._set_status(
                SharingStatus(state="error", detail="device key unavailable")
            )
            return self._enter_backoff()

        if sharing_state.session_id != self._session_id:
            # self._session_id is None either on this process's very
            # first observation of any session (in which case resuming
            # from the persisted last_revision is safe and required -- see
            # the module docstring's "Revision handling") or after this
            # worker has explicitly forgotten a session (_enter_stopped);
            # a session actually changing while one was already tracked in
            # memory is a genuinely new pairing, which starts its own
            # revision sequence at zero.
            last_revision = (
                sharing_state.last_revision if self._session_id is None else 0
            )
            self._begin_session(sharing_state.session_id, last_revision=last_revision)

        client = self._client_for(sharing_state.relay_origin)
        if client is None:
            self._set_status(
                SharingStatus(state="error", detail="invalid relay origin")
            )
            return self._enter_backoff()

        contacted = False

        if self._session_needs_renewal():
            if not self._renew_session(client, sharing_state, private_key):
                return self._enter_backoff()
            contacted = True

        if self._catalogue_needs_refresh():
            if not self._refresh_catalogue(client, sharing_state, private_key):
                return self._enter_backoff()
            contacted = True

        with self._lock:
            latest = self._latest
            if latest is not None and (self._clock() - latest[1]) > MAX_SNAPSHOT_AGE_S:
                # Too old to trust by the time this worker got to it --
                # dropped, not published; see "Coalescing, staleness, and
                # heartbeats" above. Consumed here so a stale value is not
                # re-evaluated (and re-logged) on every subsequent pass.
                self._latest = None
                latest = None

        if latest is not None:
            snapshot, _submitted_at = latest
            rows = projection.project_snapshot(snapshot, self._catalogue)
            changed = rows != self._last_published
            due_for_heartbeat = (
                not changed
                and rows
                and (
                    self._last_publish_at is None
                    or (self._clock() - self._last_publish_at) >= HEARTBEAT_INTERVAL_S
                )
            )
            if changed or due_for_heartbeat:
                if not self._publish(client, sharing_state, private_key, rows):
                    return self._enter_backoff()
                self._last_published = rows
                self._last_publish_at = self._clock()
                contacted = True

        if contacted:
            # "active" is asserted ONLY immediately following a pass that
            # actually made successful relay contact -- never merely
            # because nothing raised. A pass with nothing due leaves
            # whatever status was last reported untouched.
            self._set_status(SharingStatus(state="active"))
            self._backoff = 0.0
        return IDLE_POLL_S, True

    def _safe_sharing_enabled(self) -> bool:
        try:
            return bool(self._sharing_enabled())
        except Exception:
            logger.exception("Could not read the fleet sharing enabled predicate")
            return False

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

    def _begin_session(self, session_id: str | None, *, last_revision: int = 0) -> None:
        self._session_id = session_id
        self._revision = last_revision
        self._catalogue = None
        self._catalogue_refreshed_at = None
        # `self._clock()`, not `None`: unlike the catalogue (which genuinely
        # has no in-memory data yet either way), this worker has no way to
        # learn how much of authGD's 30-minute session TTL was already spent
        # before this process observed this session id (a fresh pairing, or
        # an already-live session resumed across a restart) -- treating
        # "just observed" as the renewal baseline avoids forcing an
        # unconditional extra network call on every single session
        # observation, at the cost of not renewing a resumed, near-expiry
        # session as promptly as a freshly-paired one. If that session has
        # in fact already lapsed, the next signed request of any kind simply
        # reports the same `unauthorized`/`forbidden` refusal a revoked
        # device would (`_handle_relay_error`) -- never a crash, and no
        # worse than this worker's pre-renewal behaviour.
        self._session_renewed_at = self._clock()
        # () rather than None: a fresh session has no rows on the relay to
        # withdraw yet, so an equally-empty first projection must not cost
        # a network call. Any NON-empty first projection still counts as
        # "changed" against this baseline and is sent immediately.
        self._last_published = ()
        self._last_publish_at = None

    def _client_for(self, origin: str):
        if self._client is not None and self._client_origin == origin:
            return self._client
        try:
            client = self._client_factory(origin)
        except Exception:
            # A corrupted/malformed persisted relay_origin (or any other
            # construction failure) must cost this pass a bounded backoff,
            # never this worker's own thread -- see the module docstring's
            # "Gating"/"_iterate" note and the class docstring's
            # `client_factory` paragraph.
            logger.exception(
                "Could not build a fleet relay client for the paired origin"
            )
            self._client = None
            self._client_origin = None
            return None
        self._client = client
        self._client_origin = origin
        return client

    def _catalogue_needs_refresh(self) -> bool:
        if self._catalogue is None or self._catalogue_refreshed_at is None:
            return True
        return (
            self._clock() - self._catalogue_refreshed_at
        ) >= CATALOGUE_REFRESH_INTERVAL_S

    def _session_needs_renewal(self) -> bool:
        return (
            self._session_renewed_at is None
            or (self._clock() - self._session_renewed_at) >= SESSION_RENEWAL_INTERVAL_S
        )

    def _renew_session(
        self, client, sharing_state: state_mod.SharingState, private_key: bytes
    ) -> bool:
        revision = self._next_revision(sharing_state)
        if revision is None:
            return False
        try:
            client.renew_session(
                session_id=sharing_state.session_id,
                private_key=private_key,
                revision=revision,
            )
        except FleetRelayError as exc:
            self._handle_relay_error(exc)
            return False
        except Exception:
            logger.exception("Fleet sharing session renewal failed unexpectedly")
            self._set_status(SharingStatus(state="error", detail="unexpected failure"))
            return False
        self._session_renewed_at = self._clock()
        return True

    def _refresh_catalogue(
        self, client, sharing_state: state_mod.SharingState, private_key: bytes
    ) -> bool:
        # "verifying" for a periodic re-check of an already-established
        # session; "connecting" the first time this session has ever
        # reached the relay (no catalogue yet at all).
        self._set_status(
            SharingStatus(
                state="verifying" if self._catalogue is not None else "connecting"
            )
        )
        revision = self._next_revision(sharing_state)
        if revision is None:
            return False
        try:
            catalogue = client.fetch_catalogue(
                session_id=sharing_state.session_id,
                private_key=private_key,
                revision=revision,
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
        sharing_state: state_mod.SharingState,
        private_key: bytes,
        rows: tuple[PublishRow, ...],
    ) -> bool:
        revision = self._next_revision(sharing_state)
        if revision is None:
            return False
        try:
            client.publish_snapshot(
                session_id=sharing_state.session_id,
                private_key=private_key,
                revision=revision,
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

    def _next_revision(self, sharing_state: state_mod.SharingState) -> int | None:
        """Increment and PERSIST the revision before returning it -- never
        after the network call. `None` if persistence itself fails; the
        caller must then skip the network call entirely for this pass
        rather than send an unpersisted revision (see the module
        docstring's "Revision handling").
        """
        candidate = self._revision + 1
        try:
            self._save_state(replace(sharing_state, last_revision=candidate))
        except Exception:
            logger.exception("Could not persist the fleet sharing device revision")
            self._set_status(
                SharingStatus(state="error", detail="revision persistence failed")
            )
            return None
        self._revision = candidate
        return candidate

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

    def _enter_backoff(self) -> tuple[float, bool]:
        self._backoff = min(
            MAX_BACKOFF_S, self._backoff * 2 if self._backoff else BASE_BACKOFF_S
        )
        # Not interruptible: a steady stream of submit() calls must not
        # collapse this wait -- only the deadline elapsing (or stop())
        # ends it. See the module docstring's "Status" paragraph and
        # _run()'s own handling of the returned flag.
        return self._backoff + self._jitter() * BASE_BACKOFF_S, False

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
