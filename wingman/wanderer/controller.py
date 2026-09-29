"""Committed connection authority and off-pump runtime/health handoff.

The mutation lock may cover disk/DPAPI. The callback condition never does.
Runtime handoff has its own serial lane; WebView delivery has a separate owner,
so neither slow settings nor a stuck page can delay roster admission or expiry.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass

from .. import paths
from ..settings import validated_wanderer
from ..telemetry.model import ClientSessionId
from .client import WandererClient
from .credentials import CredentialStore, validate_token
from .model import PrimeIdentity, parse_map_url
from .staging import Staged, StagingClient, StagingFailure, build_prime_record
from .worker import MetadataPublisher, WandererWorker, WorkerConfig

logger = logging.getLogger(__name__)

MetadataCallback = Callable[[int, frozenset[ClientSessionId], bool, int], None]
HEALTH_INTERVAL = 0.25
STAGING_ATTEMPTS = 3
STAGING_BACKOFF_SECONDS = 0.5
# Transport-shaped outcomes deserve their budget; a declared denial does not.
_STAGING_RETRYABLE = frozenset(
    {"timeout", "transport_error", "tls_error", "service_unavailable"}
)
PERSISTENCE_ERROR = (
    "Could not restore the saved Wanderer connection. Names are stopped; "
    "restart Wingman and re-enter the connection."
)


@dataclass(frozen=True)
class WandererPorts:
    """Only update_settings may do persistence; metadata effects are mailboxes.

    set_metadata_callback delivers its initial snapshot synchronously. Status
    description is pure; publish_state alone may touch the page and is invoked
    exclusively by the retained health owner, never by the expiry scheduler.
    """

    update_settings: Callable[[], AbstractContextManager[dict]]
    set_metadata_callback: Callable[[MetadataCallback | None], None]
    set_metadata_generation: Callable[[int, int], bool]
    submit_metadata: MetadataPublisher
    close_metadata_admission: Callable[[], None]
    publish_state: Callable[[dict], None]
    describe_status: Callable[[str, str | None], str]


class WandererController:
    def __init__(
        self,
        initial,
        *,
        ports: WandererPorts,
        previews_enabled: bool = False,
        credentials: CredentialStore | None = None,
        client=None,
        worker_factory=WandererWorker,
        thread_factory=threading.Thread,
        staging=None,
        prime_credentials: CredentialStore | None = None,
    ) -> None:
        self._ports = ports
        self._credentials = (
            credentials if credentials is not None else CredentialStore()
        )
        self._prime_credentials = (
            prime_credentials
            if prime_credentials is not None
            else CredentialStore(
                path=paths.state_dir() / "wanderer_prime_credentials.json"
            )
        )
        self._staging = staging if staging is not None else StagingClient()
        self._mutation_lock = threading.Lock()
        self._handoff_lock = threading.RLock()
        self._lifecycle_lock = threading.Lock()
        self._condition = threading.Condition()
        self._health_wake = threading.Event()
        self._thread_factory = thread_factory
        self._runtime_thread = self._health_thread = None
        self._started = self._closed = self._faulted = False
        self._section = validated_wanderer(initial)
        self._revision = 0
        self._previews_enabled = previews_enabled
        self._token = None
        self._credential_error = False
        self._persistence_error = False
        try:
            self._token = self._load(self._section)
        except OSError:
            self._credential_error = True
        self._credential_present = self._token is not None
        self._prime_credential_present = False
        self._host_revision = -1
        self._host_epoch = 0
        self._sessions: frozenset[ClientSessionId] = frozenset()
        self._available = False
        self._pending = False
        self._generation = 0
        self._applied_key = None
        self._worker = worker_factory(
            client if client is not None else WandererClient(), ports.submit_metadata
        )
        # ---- Prime staging (#297): a second credential and its own lane ----
        self._prime_token = None
        self._prime_credential_error = False
        self._prime_credential_present = False
        try:
            self._prime_token = self._load_prime(self._section)
        except OSError:
            self._prime_credential_error = True
        # The main token does this for its own flag above; the prime flag must
        # too, or a restart shows "No prime token stored" while the loaded
        # credential keeps staging (#297 field report: the state flipped to
        # "no prime token" across an app restart).
        self._prime_credential_present = self._prime_token is not None
        # Events already staged by this controller instance. Bounded: at most
        # one prime exists until the engine overwrites it, and replacement
        # stages a new event, so a small ring is a whole history.
        self._staged_events = deque(maxlen=8)
        self._staging_state = threading.Lock()
        self._staging_thread: threading.Thread | None = None
        self._staging_pending: tuple | None = None

    def _load_prime(self, section) -> str | None:
        if section["base_url"] and section["map_identifier"]:
            return self._prime_credentials.load(
                section["base_url"], section["map_identifier"]
            )
        return None

    def _load(self, section) -> str | None:
        if section["base_url"] and section["map_identifier"]:
            return self._credentials.load(
                section["base_url"], section["map_identifier"]
            )
        return None

    def start(self) -> bool:
        """Bind before native host start; never replace a retained owner."""
        failed = False
        with self._lifecycle_lock:
            with self._condition:
                if self._closed:
                    return False
                if self._started:
                    return True
                self._started = True
            try:
                self._ports.set_metadata_callback(self.metadata_changed)
                self._apply_runtime()
                self._runtime_thread = self._thread_factory(
                    target=self._run_runtime, name="wanderer-handoff", daemon=True
                )
                self._health_thread = self._thread_factory(
                    target=self._run_health, name="wanderer-health", daemon=True
                )
                self._runtime_thread.start()
                self._health_thread.start()
            except Exception:  # noqa: BLE001 — optional owner startup fails closed without exception text.
                failed = True
                self._faulted = True
        if failed:
            self.close_admission()
        return not failed

    def metadata_changed(
        self,
        revision: int,
        sessions: frozenset[ClientSessionId],
        available: bool,
        eve_epoch: int,
    ) -> None:
        """Host-thread ingress: cache newest detached snapshot and wake only."""
        with self._condition:
            if self._closed or revision <= self._host_revision:
                return
            # Actual EVE lifetime provenance survives coalesced/reordered
            # callbacks. Pump and companion changes are not metadata changes.
            self._host_epoch = eve_epoch
            self._host_revision = revision
            self._sessions, self._available = sessions, available
            self._pending = True
            self._condition.notify_all()

    def set_previews_enabled(self, enabled: bool) -> None:
        """The existing master transaction calls this only after persistence."""
        with self._condition:
            if self._closed:
                return
            self._previews_enabled = enabled
        self._apply_runtime()

    def _apply_runtime(self) -> bool:
        with self._handoff_lock:
            with self._condition:
                if self._closed or not self._started:
                    return False
                config = WorkerConfig(
                    **self._section,
                    token=self._token,
                    previews_enabled=self._previews_enabled,
                    host_available=self._available,
                )
                eve_epoch = self._host_epoch
                key = (config, eve_epoch, self._revision)
                sessions = self._sessions
                self._pending = False
                changed = key != self._applied_key
                if changed:
                    self._generation += 1
                generation = self._generation
            # No callback condition is held across host or worker effects.
            # Host fences first: even an immediately completing request cannot
            # publish into the previous runtime's metadata admission.
            if changed:
                if not self._ports.set_metadata_generation(generation, eve_epoch):
                    # A newer host callback owns the next handoff. Do not start
                    # HTTP from the rejected old epoch or spin on this snapshot.
                    return False
                if not self._worker.configure(config, generation=generation):
                    return False
                with self._condition:
                    if not self._closed:
                        self._applied_key = key
            self._worker.set_sessions(sessions)
        self._health_wake.set()
        return True

    def _run_runtime(self) -> None:
        try:
            while True:
                with self._condition:
                    self._condition.wait_for(lambda: self._closed or self._pending)
                    if self._closed:
                        return
                self._apply_runtime()
        except Exception:  # noqa: BLE001 — mailbox failure must not leak collaborator exception text.
            self._faulted = True
            self.close_admission()

    def _acknowledged_locked(self) -> dict:
        return {
            **self._section,
            "revision": self._revision,
            "credential_present": self._credential_present,
            "credential_error": self._credential_error,
            "persistence_error": self._persistence_error,
            "prime_credential_present": self._prime_credential_present,
        }

    def state(self) -> dict:
        while True:
            with self._condition:
                acknowledged = self._acknowledged_locked()
                previews, available = self._previews_enabled, self._available
                faulted = self._faulted
            worker_state = self._worker.state()
            # Never pair an old acknowledgement with a newly configured worker:
            # the page would spend that generation under the previous binding.
            # Retry without nesting the callback and worker locks. The opposite
            # handoff (new acknowledgement, old worker) remains safely fenced
            # by the page until runtime applies the committed configuration.
            with self._condition:
                if acknowledged["revision"] == self._revision and (
                    previews,
                    available,
                    faulted,
                ) == (self._previews_enabled, self._available, self._faulted):
                    break
        # Only WorkerState is safe to serialize. WorkerConfig contains a secret.
        payload = {
            **asdict(worker_state),
            **acknowledged,
            "previews_enabled": previews,
            "host_available": available,
        }
        if acknowledged["persistence_error"]:
            payload["status"] = "persistence_error"
        elif faulted:
            payload["status"] = "worker_failed"
        elif payload["status"] != "stopped" and acknowledged["credential_error"]:
            payload["status"] = "credential_error"
        payload["status_text"] = self._ports.describe_status(
            payload["status"], payload["error_code"]
        )
        result = payload["test_result"]
        payload["test_result_text"] = (
            self._ports.describe_status(
                "connected" if result == "success" else "error",
                None if result == "success" else result,
            )
            if result is not None
            else ""
        )
        return payload

    def _run_health(self) -> None:
        previous = None
        while True:
            self._health_wake.wait(HEALTH_INTERVAL)
            self._health_wake.clear()
            with self._condition:
                if self._closed:
                    return
            payload = self.state()
            if payload == previous:
                continue
            with self._condition:
                if self._closed:
                    return
            try:
                self._ports.publish_state(payload)
            except Exception:  # noqa: BLE001, S112 — a missing/closed page must not terminate runtime or expose payload context.
                continue
            previous = payload

    def prime_identity(self, session) -> PrimeIdentity | None:
        """The map's identity for this client session, or None (#296).

        One-line facade over the worker's snapshot join. Read-only: it
        never configures, publishes or admits anything, so it is safe on
        any thread the staging slice calls it from, and a closed runtime
        answers None rather than raising.
        """
        return self._worker.prime_identity(session)

    def stage_prime(self, prime, identity) -> bool:
        """Stage one captured prime for the saved map, or silently do nothing.

        The Api relay calls this with the engine's prime and the focused
        client's map identity (#296). Inert — answering False, staging
        nothing — unless a prime token is stored for exactly the saved
        binding and the identity is a mapped character on that map. The
        return says whether an outbound attempt was started or accepted;
        staging failures are silent by design (ADR 0001: never disturb the
        clipboard, preview or settings flows).

        One outbound lane carries the newest prime: while an attempt run is
        in flight, a newly captured event replaces any pending one (the
        server keeps one active prime per character — newest wins) and is
        staged when the lane drains.
        """
        with self._staging_state:
            if self._closed:
                return False
            binding = (self._section["base_url"], self._section["map_identifier"])
            token = self._prime_token
            if (
                not binding[0]
                or not binding[1]
                or token is None
                or identity is None
                or identity.solar_system_id is None
            ):
                return False
            try:
                record = build_prime_record(prime, identity, *binding)
            except ValueError:
                return False
            event = prime.event
            if event in self._staged_events:
                return False
            self._staged_events.append(event)
            self._staging_pending = (binding, token, record)
            thread = self._staging_thread
            if thread is not None and thread.is_alive():
                # The live lane drains the newest pending record itself.
                return True
            if self._closed:
                self._staging_pending = None
                return False
            # Allocation is inside the lock so two callers can never both
            # conclude the lane is free; start() stays outside it.
            try:
                thread = self._thread_factory(
                    target=self._run_staging,
                    name="wanderer-prime-staging",
                    daemon=True,
                )
            except Exception:
                logger.debug("Prime staging could not start", exc_info=True)
                self._staging_pending = None
                return False
            self._staging_thread = thread
        thread.start()
        return True

    def _run_staging(self) -> None:
        while True:
            with self._staging_state:
                pending = self._staging_pending
                self._staging_pending = None
                closed = self._closed
            if pending is None or closed:
                return
            base, map_identifier = pending[0]
            token, record = pending[1], pending[2]
            for attempt in range(STAGING_ATTEMPTS):
                result = self._staging.stage(base, map_identifier, token, record)
                if isinstance(result, Staged):
                    break
                failure = result if isinstance(result, StagingFailure) else None
                code = failure.code if failure is not None else "transport_error"
                if failure is not None and failure.authentication_failed:
                    # A denied credential must not keep POSTing it; the token
                    # is wrong, revoked, or out of scope. Silent give-up;
                    # removing or replacing the token re-enables staging.
                    break
                if code not in _STAGING_RETRYABLE:
                    break
                if attempt + 1 < STAGING_ATTEMPTS:
                    time.sleep(STAGING_BACKOFF_SECONDS)
            # Budget exhausted: silent give-up. A newer pending record, if
            # any, is drained by the loop above; otherwise the lane retires.

    def _result(self, applied: bool, error: str | None = None) -> dict:
        with self._condition:
            return {
                "applied": applied,
                "persisted": applied,
                "error": error,
                "acknowledged": self._acknowledged_locked(),
            }

    def _closed_result(self) -> dict | None:
        with self._condition:
            if self._closed:
                return self._result(
                    False,
                    PERSISTENCE_ERROR
                    if self._persistence_error
                    else "Wingman is shutting down.",
                )
        return None

    def _commit(self, section, token, credential_error=False) -> None:
        # A changed binding re-scopes the prime credential: a prime token
        # belongs to the map it was provisioned for, so an empty or new
        # binding reloads it (an old-map document answers None). An unchanged
        # binding keeps the in-memory token — no redundant DPAPI round trip.
        with self._condition:
            old_binding = (
                self._section["base_url"],
                self._section["map_identifier"],
            )
            self._section = section
            self._credential_present = token is not None
            self._credential_error = credential_error
            self._token = None if self._closed else token
            self._revision += 1
        binding = (section["base_url"], section["map_identifier"])
        if binding != old_binding or binding == ("", ""):
            prime_token = None
            try:
                prime_token = self._load_prime(section) if not self._closed else None
            except OSError:
                with self._condition:
                    self._prime_credential_error = True
            with self._condition:
                self._prime_token = prime_token
                self._prime_credential_present = prime_token is not None
        self._apply_runtime()
        self._health_wake.set()

    def set_prime_token(self, token) -> dict:
        """Save or clear the prime credential; the empty string is the off switch.

        The second protected document, written with the same two-document
        care as the read credential: the protected store leads, the settings
        write follows (here only as the revision bump that republishes
        state), and a failed write refuses without touching the prior
        credential. The token never reaches the settings store, the page,
        logs or telemetry.
        """
        with self._mutation_lock:
            refusal = self._closed_result()
            if refusal:
                return refusal
            if not isinstance(token, str):
                return self._result(
                    False, "Enter a Bookmark API token or leave the field empty."
                )
            with self._condition:
                section = dict(self._section)
            if not section["base_url"] or not section["map_identifier"]:
                return self._result(
                    False,
                    "Save and test the map connection before adding a Bookmark API token.",
                )
            try:
                candidate = validate_token(token) if token != "" else None
            except OSError:
                return self._result(False, "That Bookmark API token is not valid.")
            if candidate == self._prime_token:
                return self._result(True)
            try:
                if candidate is None:
                    self._prime_credentials.remove()
                else:
                    self._prime_credentials.replace(
                        section["base_url"], section["map_identifier"], candidate
                    )
            except Exception:  # noqa: BLE001 — protected-store failure: fixed context only.
                return self._result(
                    False, "Could not save the Bookmark API token on this PC."
                )
            with self._condition:
                self._prime_token = candidate
                self._prime_credential_present = candidate is not None
                self._prime_credential_error = False
                self._revision += 1
            self._health_wake.set()
            return self._result(True)

    def set_enabled(self, enabled) -> dict:
        with self._mutation_lock:
            refusal = self._closed_result()
            if refusal:
                return refusal
            if not isinstance(enabled, bool):
                return self._result(False, "Choose On or Off.")
            with self._condition:
                section, token = dict(self._section), self._token
                credential_error = self._credential_error
            if section["enabled"] == enabled:
                return self._result(True)
            section["enabled"] = enabled
            try:
                with self._ports.update_settings() as cfg:
                    cfg["wanderer"] = section
            except Exception:  # noqa: BLE001 — storage boundary: never expose paths, token material or exception context to the bridge.
                return self._result(False, "Could not save the Wanderer preference.")
            self._commit(section, token, credential_error)
            return self._result(True)

    def _save_connection(self, section, token) -> dict:
        """Mutation-owned multi-document write, with bounded compensation.

        This is not crash-atomic. Until all documents succeed, runtime keeps
        the old in-memory connection. No candidate credential reaches a
        worker. The prime credential (added #297) joins the transaction: it
        is bound to the map, so a removed or re-bound connection removes the
        prime document first and compensates it on failure.
        """
        with self._condition:
            previous_binding = (
                self._section["base_url"],
                self._section["map_identifier"],
            )
            prime_removed = (section["base_url"], section["map_identifier"]) != (
                previous_binding
            )
        prime_snapshot = None
        try:
            previous = self._credentials.snapshot()
            prime_snapshot = (
                self._prime_credentials.snapshot() if prime_removed else None
            )
            if token is None:
                self._credentials.remove()
            else:
                self._credentials.replace(
                    section["base_url"], section["map_identifier"], token
                )
            if prime_removed:
                self._prime_credentials.remove()
        except Exception:  # noqa: BLE001 — protected-store failures leave prior bytes intact; expose only fixed context.
            return self._result(
                False, "Could not save the protected Wanderer connection."
            )
        try:
            with self._ports.update_settings() as cfg:
                cfg["wanderer"] = section
        except Exception:  # noqa: BLE001 — settings.update restores settings; compensate only the protected documents.
            try:
                self._credentials.restore(previous)
                if prime_removed:
                    self._prime_credentials.restore(prime_snapshot)
            except Exception:  # noqa: BLE001 — uncertain persistence must stop admission, not claim successful rollback.
                with self._condition:
                    self._persistence_error = True
                    self._credential_error = True
                    self._credential_present = False
                    self._revision += 1
                self.close_admission()
                return self._result(False, PERSISTENCE_ERROR)
            return self._result(False, "Could not save the Wanderer connection.")
        self._commit(section, token)
        return self._result(True)

    def remove_connection(self, revision) -> dict:
        with self._mutation_lock:
            refusal = self._closed_result()
            if refusal:
                return refusal
            with self._condition:
                if type(revision) is not int or revision != self._revision:
                    return self._result(
                        False, "The connection changed. Confirm removal again."
                    )
                section = {**self._section, "base_url": "", "map_identifier": ""}
            return self._save_connection(section, None)

    def test_connection(self, map_url, token) -> dict:
        """Save the submitted connection, then request Test on the existing lane.

        applied/persisted describe configuration, never asynchronous admission.
        An empty password reuses only the currently acknowledged binding — not
        an older file that happens to match another submitted URL or map.
        """
        with self._mutation_lock:
            result = self._closed_result()
            if result is None:
                try:
                    base, map = parse_map_url(map_url)
                    if token != "":
                        token = validate_token(token)
                except (ValueError, OSError):
                    result = self._result(
                        False, "Enter a valid HTTPS map URL and token."
                    )
            if result is None:
                with self._condition:
                    section, saved_token = dict(self._section), self._token
                if token == "":
                    if (base, map) != (
                        section["base_url"],
                        section["map_identifier"],
                    ) or saved_token is None:
                        result = self._result(False, "Enter a token for this map URL.")
                    else:
                        # Already saved: do not rewrite/reconfigure or cancel an
                        # admitted Test simply because its binding was re-entered.
                        result = self._result(True)
                else:
                    section.update(base_url=base, map_identifier=map)
                    result = self._save_connection(section, token)
            accepted, generation, test_error = False, None, None
            if result["persisted"]:
                if not self.start():
                    test_error = "Connection saved, but Wanderer cannot test now. Restart Wingman to retry."
                else:
                    with self._handoff_lock:
                        # A refused epoch handoff has not configured the saved
                        # binding. Never test the previous worker connection.
                        if self._apply_runtime():
                            accepted = self._worker.test_connection()
                        generation = self._generation
                    if not accepted:
                        test_error = "Connection saved, but Test could not start. Wait for the current request or restart Wingman."
                self._health_wake.set()
            return {
                **result,
                "test_accepted": accepted,
                "test_error": test_error,
                "test_generation": generation,
            }

    def close_admission(self) -> None:
        # Gate callbacks before detach, without taking mutation/handoff locks
        # or waiting on persistence, the page or worker joins.
        with self._condition:
            self._closed = True
            self._token = None
            self._prime_token = None
            self._applied_key = None
            self._sessions = frozenset()
            self._available = False
            self._condition.notify_all()
        with self._lifecycle_lock:
            if self._started:
                self._ports.set_metadata_callback(None)
                self._ports.close_metadata_admission()
        self._worker.close_admission()
        self._health_wake.set()

    def stop(self, timeout: float = 1.0) -> bool:
        self.close_admission()
        deadline = time.monotonic() + max(0.0, timeout)
        stopped = self._worker.stop(max(0.0, deadline - time.monotonic()))
        for owner in (self._runtime_thread, self._health_thread):
            if (
                owner is not None
                and owner.ident is not None
                and owner is not threading.current_thread()
            ):
                owner.join(max(0.0, deadline - time.monotonic()))
        return stopped and all(
            owner is None or not owner.is_alive()
            for owner in (self._runtime_thread, self._health_thread)
        )
