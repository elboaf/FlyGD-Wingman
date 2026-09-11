"""Committed connection authority and off-pump runtime/health handoff.

The mutation lock may cover disk/DPAPI. The callback condition never does.
Runtime handoff has its own serial lane; WebView delivery has a separate owner,
so neither slow settings nor a stuck page can delay roster admission or expiry.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass

from ..settings import validated_wanderer
from ..telemetry.model import ClientSessionId
from .client import WandererClient
from .credentials import CredentialStore, validate_token
from .model import normalize_base_url, normalize_map_identifier
from .worker import MetadataPublisher, WandererWorker, WorkerConfig

MetadataCallback = Callable[[int, frozenset[ClientSessionId], bool], None]
HEALTH_INTERVAL = 0.25
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
    set_metadata_generation: Callable[[int], None]
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
    ) -> None:
        self._ports = ports
        self._credentials = (
            credentials if credentials is not None else CredentialStore()
        )
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
        self, revision: int, sessions: frozenset[ClientSessionId], available: bool
    ) -> None:
        """Host-thread ingress: cache newest detached snapshot and wake only."""
        with self._condition:
            if self._closed or revision <= self._host_revision:
                return
            # A gap can conceal unavailable -> available, including an older
            # detached callback arriving after the newer ready snapshot. Fence
            # conservatively even if the final configuration compares equal.
            if available != self._available or revision > self._host_revision + 1:
                self._host_epoch += 1
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

    def _apply_runtime(self) -> None:
        with self._handoff_lock:
            with self._condition:
                if self._closed or not self._started:
                    return
                config = WorkerConfig(
                    **self._section,
                    token=self._token,
                    previews_enabled=self._previews_enabled,
                    host_available=self._available,
                )
                key = (config, self._host_epoch, self._revision)
                sessions = self._sessions
                self._pending = False
                changed = key != self._applied_key
                if changed:
                    self._generation += 1
                    self._applied_key = key
                generation = self._generation
            # No callback condition is held across host or worker effects.
            # Host fences first: even an immediately completing request cannot
            # publish into the previous runtime's metadata admission.
            if changed:
                self._ports.set_metadata_generation(generation)
                self._worker.configure(config, generation=generation)
            self._worker.set_sessions(sessions)
        self._health_wake.set()

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
        with self._condition:
            self._section = section
            self._credential_present = token is not None
            self._credential_error = credential_error
            self._token = None if self._closed else token
            self._revision += 1
        self._apply_runtime()
        self._health_wake.set()

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
        """Mutation-owned two-document write, with bounded ciphertext compensation.

        This is not crash-atomic. Until both documents succeed, runtime keeps
        the old in-memory connection. No candidate credential reaches a worker.
        """
        try:
            previous = self._credentials.snapshot()
            if token is None:
                self._credentials.remove()
            else:
                self._credentials.replace(
                    section["base_url"], section["map_identifier"], token
                )
        except Exception:  # noqa: BLE001 — protected-store failures leave its prior bytes intact; expose only fixed context.
            return self._result(
                False, "Could not save the protected Wanderer connection."
            )
        try:
            with self._ports.update_settings() as cfg:
                cfg["wanderer"] = section
        except Exception:  # noqa: BLE001 — settings.update restores settings; compensate only the protected document.
            try:
                self._credentials.restore(previous)
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

    def test_connection(self, base, map, token) -> dict:
        """Save the submitted connection, then request Test on the existing lane.

        applied/persisted describe configuration, never asynchronous admission.
        An empty password reuses only the currently acknowledged binding — not
        an older file that happens to match another submitted URL or map.
        """
        with self._mutation_lock:
            result = self._closed_result()
            if result is None:
                try:
                    base, map = normalize_base_url(base), normalize_map_identifier(map)
                    if token != "":
                        token = validate_token(token)
                except (ValueError, OSError):
                    result = self._result(False, "Enter a valid URL, map and token.")
            if result is None:
                with self._condition:
                    section, saved_token = dict(self._section), self._token
                if token == "":
                    if (base, map) != (
                        section["base_url"],
                        section["map_identifier"],
                    ) or saved_token is None:
                        result = self._result(
                            False, "Enter a token for this URL and map."
                        )
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
                        self._apply_runtime()
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
