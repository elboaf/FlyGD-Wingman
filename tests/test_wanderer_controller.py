"""Committed transactions and real retained owners; no timing sleeps."""

import json
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from tests.test_wanderer_worker import (
    FIRST,
    HIDDEN,
    Client,
    Clock,
    ObservedCondition,
    success,
)
from wingman import settings
from wingman.wanderer.credentials import CredentialStore
from wingman.wanderer.worker import WandererWorker

BASE = "https://wanderer.example/prefix"
TOKEN = "private-controller-token"


@pytest.mark.parametrize("raw", [None, [], "yes", {"enabled": 1}, {"enabled": "true"}])
def test_settings_upgrade_is_default_off_and_drops_secret(raw):
    normalize = getattr(settings, "validated_wanderer", None)
    assert normalize is not None
    assert normalize(raw) == {"enabled": False, "base_url": "", "map_identifier": ""}
    assert normalize(
        {"token": TOKEN, "base_url": "http://unsafe", "map_identifier": "../bad"}
    ) == {"enabled": False, "base_url": "", "map_identifier": ""}


def test_settings_save_load_normalizes_additive_section(tmp_path):
    path = tmp_path / "settings.json"
    cfg = settings.load(path)
    assert cfg.get("wanderer") == {
        "enabled": False,
        "base_url": "",
        "map_identifier": "",
    }
    cfg["wanderer"] = {
        "enabled": True,
        "base_url": "https://WANDERER.example:443/prefix/",
        "map_identifier": "map",
        "token": TOKEN,
    }
    settings.save(cfg, path)
    assert settings.load(path)["wanderer"] == {
        "enabled": True,
        "base_url": BASE,
        "map_identifier": "map",
    }
    assert TOKEN not in path.read_text()
    assert settings.load(tmp_path / "other.json")["wanderer"]["enabled"] is False


class Host:
    def __init__(self):
        self.callback = None
        self.revision = 0
        self.sessions = frozenset({FIRST, HIDDEN})
        self.available = True
        self.generation = 0
        self.closed = False
        self.values = {}
        self.cv = threading.Condition()

    def subscribe(self, callback):
        self.callback = callback
        if callback:
            callback(self.revision, self.sessions, self.available)

    def notify(self, revision, sessions, available):
        self.revision, self.sessions, self.available = revision, sessions, available
        if self.callback:
            self.callback(revision, sessions, available)

    def fence(self, generation):
        with self.cv:
            if not self.closed:
                assert generation > self.generation
                self.generation = generation
                self.values.clear()
            self.cv.notify_all()

    def publish(self, generation, values):
        with self.cv:
            if generation == self.generation and not self.closed:
                self.values.update(
                    {s: v for s, v in values.items() if s in self.sessions}
                )
            self.cv.notify_all()

    def close(self):
        self.closed = True
        self.values.clear()


class Rig:
    def __init__(
        self, tmp_path, *, enabled=True, previews=True, delivery=None, section=None
    ):
        from wingman.wanderer.controller import WandererController, WandererPorts

        self.cfg = settings.load()
        self.cfg["wanderer"] = (
            section
            if section is not None
            else {
                "enabled": enabled,
                "base_url": BASE,
                "map_identifier": "map",
            }
        )
        self.host = Host()
        self.store = CredentialStore(
            tmp_path / "credential",
            protect=lambda b: b[::-1],
            unprotect=lambda b: b[::-1],
        )
        self.store.replace(BASE, "map", TOKEN)
        self.clock = Clock()
        self.worker_cv = ObservedCondition()
        self.client = Client()
        self.delivered = []
        self.delivery_cv = threading.Condition()

        def publish(payload):
            if delivery:
                delivery(payload)
            with self.delivery_cv:
                self.delivered.append(payload)
                self.delivery_cv.notify_all()

        def factory(client, publish):
            self.worker = WandererWorker(
                client, publish, clock=self.clock, condition=self.worker_cv
            )
            return self.worker

        self.controller = WandererController(
            self.cfg["wanderer"],
            previews_enabled=previews,
            credentials=self.store,
            client=self.client,
            worker_factory=factory,
            ports=WandererPorts(
                update_settings=lambda: settings.update(self.cfg),
                set_metadata_callback=self.host.subscribe,
                set_metadata_generation=self.host.fence,
                submit_metadata=self.host.publish,
                close_metadata_admission=self.host.close,
                publish_state=publish,
                describe_status=lambda status, error: status,
            ),
        )

    def start(self):
        assert self.controller.start()

    def wait(self, predicate):
        with self.worker_cv:
            assert self.worker_cv.wait_for(
                lambda: predicate(self.controller.state()), 2
            ), self.controller.state()
        return self.controller.state()

    def close(self):
        self.controller.close_admission()
        with self.client.cv:
            for call in self.client.calls:
                call.reply(success())
        assert self.controller.stop(2)


@pytest.fixture
def rig(tmp_path):
    value = Rig(tmp_path)
    try:
        yield value
    finally:
        value.close()


def test_host_generation_is_fenced_before_each_worker_configuration(rig, monkeypatch):
    configure = rig.worker.configure
    observed = []

    def configure_after_fence(config, *, generation):
        assert rig.host.generation == generation
        observed.append(generation)
        return configure(config, generation=generation)

    monkeypatch.setattr(rig.worker, "configure", configure_after_fence)
    rig.start()
    rig.client.call(1).reply(success())
    rig.wait(lambda s: not s["in_flight"])
    assert rig.controller.set_enabled(False)["persisted"]
    assert len(observed) == 2 and observed[1] > observed[0]


def test_polling_handoff_and_health_are_nonsecret_current_session_counts(rig):
    rig.start()
    call = rig.client.call(1)
    assert call.args == (BASE, "map", TOKEN, None)
    call.reply(success())
    state = rig.wait(lambda s: s["status"] == "connected")
    assert (
        state["previewed"],
        state["matched"],
        state["available"],
        state["stale"],
    ) == (2, 2, 2, 0)
    assert state["credential_present"] is True
    assert TOKEN not in json.dumps(state)
    assert "First Pilot" not in json.dumps(state)
    with rig.delivery_cv:
        assert rig.delivery_cv.wait_for(
            lambda: any(s["status"] == "connected" for s in rig.delivered), 2
        )
    assert all(TOKEN not in json.dumps(s) for s in rig.delivered)


def test_state_retries_reverse_handoff_and_page_recovers_coverage(rig, monkeypatch):
    rig.start()
    rig.client.call(1).reply(success())
    before = rig.wait(lambda s: s["status"] == "connected")
    worker_state = rig.worker.state
    entered, release = threading.Event(), threading.Event()
    sampled = []
    reader = threading.Thread(target=lambda: sampled.append(rig.controller.state()))

    def gated_state():
        if threading.current_thread() is reader:
            entered.set()
            assert release.wait(3)
        return worker_state()

    monkeypatch.setattr(rig.worker, "state", gated_state)
    reader.start()
    try:
        assert entered.wait(2)
        # The read has captured old acknowledgement. Commit/reconfigure and
        # finish a new snapshot before allowing its worker sample to continue.
        assert rig.controller.test_connection(BASE, "map", TOKEN)["applied"]
        with rig.worker_cv:
            rig.clock.now = 102
            rig.worker_cv.notify_all()
        rig.client.call(2).reply(success(102))
        settled = rig.wait(lambda s: s["status"] == "connected")
    finally:
        release.set()
        reader.join(3)
    assert not reader.is_alive()
    node = shutil.which("node")
    assert node, "Node is required for the real Wanderer handoff trace"
    run = subprocess.run(
        [
            node,
            str(
                Path(__file__).resolve().parents[1] / "scripts/test_wanderer_runtime.js"
            ),
            "--handoff-trace",
            json.dumps([before, sampled[0], settled]),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    assert "controller reverse-handoff trace recovers connected coverage" in run.stdout
    assert sampled[0]["revision"] == settled["revision"] > before["revision"]
    assert sampled[0]["generation"] == settled["generation"] > before["generation"]


@pytest.mark.parametrize("change", ["previews", "host"])
def test_state_retries_readiness_change_during_worker_sample(rig, monkeypatch, change):
    rig.start()
    rig.client.call(1).reply(success())
    before = rig.wait(lambda s: s["status"] == "connected")
    worker_state = rig.worker.state
    entered, release = threading.Event(), threading.Event()
    sampled = []
    reader = threading.Thread(target=lambda: sampled.append(rig.controller.state()))

    def gated_state():
        if threading.current_thread() is reader:
            entered.set()
            assert release.wait(3)
        return worker_state()

    monkeypatch.setattr(rig.worker, "state", gated_state)
    reader.start()
    try:
        assert entered.wait(2)
        if change == "previews":
            rig.controller.set_previews_enabled(False)
        else:
            rig.host.notify(1, rig.host.sessions, False)
            rig.wait(lambda s: not s["automatic_ready"])
    finally:
        release.set()
        reader.join(3)
    assert not reader.is_alive()
    snapshot = sampled[0]
    assert (
        snapshot["previews_enabled" if change == "previews" else "host_available"]
        is False
    )
    assert snapshot["generation"] > before["generation"]
    assert snapshot["revision"] == before["revision"]
    assert snapshot["available"] == 0


def test_failed_save_retains_committed_generation_and_acknowledgement(rig, monkeypatch):
    rig.start()
    rig.client.call(1).reply(success())
    before = rig.wait(lambda s: s["status"] == "connected")

    def fail(*args):
        raise OSError(TOKEN)

    monkeypatch.setattr(settings, "_save_locked", fail)
    result = rig.controller.set_enabled(False)
    assert result["applied"] is result["persisted"] is False
    assert TOKEN not in json.dumps(result)
    assert result["acknowledged"]["base_url"] == BASE
    assert result["acknowledged"]["enabled"] is True
    assert rig.controller.state()["generation"] == before["generation"]
    assert rig.cfg["wanderer"] == {
        "enabled": True,
        "base_url": BASE,
        "map_identifier": "map",
    }


def test_failed_credential_replace_and_remove_retain_runtime(rig, monkeypatch):
    rig.start()
    rig.client.call(1).reply(success())
    before = rig.wait(lambda s: s["status"] == "connected")

    def fail(*args):
        raise OSError(TOKEN)

    monkeypatch.setattr(rig.store, "replace", fail)
    monkeypatch.setattr(rig.store, "remove", fail)
    for result in (
        rig.controller.test_connection(BASE, "map", "new-token"),
        rig.controller.remove_connection(rig.controller.state()["revision"]),
    ):
        assert not result["applied"] and not result["persisted"]
        assert result["acknowledged"]["credential_present"]
        assert TOKEN not in json.dumps(result)
    assert rig.controller.state()["generation"] == before["generation"]


def test_explicit_remove_clears_connection_and_retains_enable(rig):
    rig.start()
    rig.client.call(1).reply(success())
    rig.wait(lambda s: not s["in_flight"])
    result = rig.controller.remove_connection(rig.controller.state()["revision"])
    assert result["applied"] and result["persisted"]
    assert rig.cfg["wanderer"] == {
        "enabled": True,
        "base_url": "",
        "map_identifier": "",
    }
    assert settings.load()["wanderer"] == rig.cfg["wanderer"]
    assert rig.store.load(BASE, "map") is None
    assert not rig.controller.state()["credential_present"]
    assert not any(rig.host.values.values())


def test_callback_never_waits_for_save_and_ignores_old_revisions(rig, monkeypatch):
    rig.start()
    rig.client.call(1).reply(success())
    rig.wait(lambda s: s["status"] == "connected")
    entered, release, returned = threading.Event(), threading.Event(), threading.Event()

    def save(*args):
        entered.set()
        assert release.wait(3)
        raise OSError(TOKEN)

    monkeypatch.setattr(settings, "_save_locked", save)
    mutation = threading.Thread(target=lambda: rig.controller.set_enabled(False))
    callback = rig.host.callback
    mutation.start()
    assert entered.wait(2)

    def notify():
        callback(3, frozenset({FIRST}), False)
        callback(2, frozenset({HIDDEN}), True)
        returned.set()

    owner = threading.Thread(target=notify)
    owner.start()
    try:
        assert returned.wait(1), "callback blocked behind settings persistence"
        state = rig.wait(lambda s: s["previewed"] == 1 and not s["host_available"])
        assert state["enabled"] is True
    finally:
        release.set()
        mutation.join(3)
        owner.join(3)


def test_coalesced_host_restart_with_same_configuration_gets_new_generation(rig):
    rig.start()
    rig.client.call(1).reply(success())
    before = rig.wait(lambda s: s["status"] == "connected")["generation"]
    # Hold only the handoff lane, not callback admission, to force coalescing.
    with rig.controller._handoff_lock:
        rig.host.notify(1, frozenset(), False)
        rig.host.notify(2, frozenset({FIRST, HIDDEN}), True)
    state = rig.wait(lambda s: s["generation"] > before)
    assert state["host_available"]
    assert rig.host.generation == state["generation"]


def test_out_of_order_host_restart_cannot_reuse_equal_ready_generation(rig):
    rig.start()
    rig.client.call(1).reply(success())
    before = rig.wait(lambda s: s["status"] == "connected")["generation"]
    with rig.controller._handoff_lock:
        rig.host.callback(2, frozenset({FIRST, HIDDEN}), True)
        rig.host.callback(1, frozenset(), False)
    state = rig.wait(lambda s: s["generation"] > before)
    assert state["host_available"] and state["previewed"] == 2


def test_off_test_is_async_does_not_enable_and_shutdown_retains_owners(tmp_path):
    rig = Rig(tmp_path, enabled=False, previews=False)
    try:
        rig.start()
        result = rig.controller.test_connection(BASE, "map", "")
        assert result["applied"] and result["persisted"] and result["test_accepted"]
        assert not result["acknowledged"]["enabled"]
        call = rig.client.call(1)
        assert rig.controller.state()["test_in_flight"]
        refused = rig.controller.test_connection(BASE, "map", "")
        assert refused["applied"] and refused["persisted"]
        assert not refused["test_accepted"] and refused["test_error"]
        worker = rig.worker
        callback = rig.host.callback
        assert not rig.controller.stop(0)
        assert rig.host.callback is None and rig.host.closed
        assert not rig.controller.start()
        callback(100, frozenset({FIRST}), True)
        assert rig.worker is worker
        assert rig.controller.state()["status"] == "stopped"
        assert not rig.controller.set_enabled(True)["applied"]
        call.reply(success())
    finally:
        rig.close()


def test_blocked_health_delivery_does_not_block_handoff_or_expiry(tmp_path):
    entered, release = threading.Event(), threading.Event()

    def delivery(payload):
        if payload["status"] == "connected":
            entered.set()
            assert release.wait(3)

    rig = Rig(tmp_path, delivery=delivery)
    try:
        rig.start()
        rig.client.call(1).reply(success())
        assert entered.wait(2)
        with rig.worker_cv:
            rig.clock.now = 116
            rig.worker_cv.notify_all()
        rig.wait(lambda s: s["stale"] == 2 and s["available"] == 0)
        with rig.host.cv:
            assert rig.host.cv.wait_for(lambda: not any(rig.host.values.values()), 2)
        rig.host.notify(1, frozenset({FIRST}), False)
        rig.wait(lambda s: not s["automatic_ready"])
        assert not any(rig.host.values.values())
        assert not rig.controller.stop(0)
    finally:
        release.set()
        rig.close()


@pytest.mark.parametrize("operation", ["settings", "replace", "remove"])
def test_unexpected_storage_exception_never_reaches_bridge(rig, monkeypatch, operation):
    def fail(*args):
        raise RuntimeError(TOKEN)

    if operation == "settings":
        monkeypatch.setattr(settings, "_save_locked", fail)

        def call():
            return rig.controller.test_connection(BASE, "other", "new-token")
    elif operation == "replace":
        monkeypatch.setattr(rig.store, "replace", fail)

        def call():
            return rig.controller.test_connection(BASE, "map", "new-token")
    else:
        monkeypatch.setattr(rig.store, "remove", fail)

        def call():
            return rig.controller.remove_connection(rig.controller.state()["revision"])

    result = call()
    assert not result["applied"] and not result["persisted"]
    assert result["acknowledged"]["credential_present"]
    assert result["acknowledged"]["map_identifier"] == "map"
    assert TOKEN not in json.dumps(result)


def test_close_during_admitted_save_never_reopens_runtime_or_retains_cached_token(
    rig, monkeypatch
):
    rig.start()
    rig.client.call(1).reply(success())
    rig.wait(lambda s: not s["in_flight"])
    entered, release = threading.Event(), threading.Event()
    original = settings._save_locked
    results = []

    def save(*args):
        entered.set()
        assert release.wait(3)
        original(*args)

    monkeypatch.setattr(settings, "_save_locked", save)
    owner = threading.Thread(
        target=lambda: results.append(rig.controller.set_enabled(False))
    )
    owner.start()
    assert entered.wait(2)
    try:
        rig.controller.close_admission()
        assert rig.host.callback is None and rig.host.closed
        assert rig.controller.state()["status"] == "stopped"
        assert TOKEN not in repr(rig.controller._applied_key)
        assert rig.controller._applied_key is None
    finally:
        release.set()
        owner.join(3)
    assert results[0]["persisted"]
    assert not rig.controller.state()["enabled"]
    assert rig.controller._token is None
    assert rig.controller.state()["status"] == "stopped"


@pytest.mark.parametrize(
    "gate", ["off", "previews", "host", "url", "map", "credential"]
)
def test_every_automatic_gate_prevents_network_but_test_does_not_enable(tmp_path, gate):
    section = {
        "enabled": gate != "off",
        "base_url": "" if gate == "url" else BASE,
        "map_identifier": "" if gate == "map" else "map",
    }
    rig = Rig(tmp_path, section=section, previews=gate != "previews")
    try:
        if gate == "host":
            rig.host.available = False
        if gate == "credential":
            assert rig.controller.remove_connection(rig.controller.state()["revision"])[
                "persisted"
            ]
        rig.start()
        assert not rig.controller.state()["automatic_ready"]
        assert rig.worker._request_thread is None
        before = rig.controller.state()["enabled"]
        current = rig.controller.state()
        result = rig.controller.test_connection(
            current["base_url"], current["map_identifier"], ""
        )
        assert result["test_accepted"] is (gate in {"off", "previews", "host"})
        assert rig.controller.state()["enabled"] is before
        if result["applied"]:
            rig.client.call(1).reply(success())
            state = rig.wait(lambda s: s["test_result"] == "success")
            assert state["available"] == 0
    finally:
        rig.close()


def test_test_admission_waits_behind_poll_on_one_http_lane(rig):
    rig.start()
    poll = rig.client.call(1)
    assert rig.controller.test_connection(BASE, "map", "")["test_accepted"]
    assert rig.controller.state()["test_pending"]
    assert not rig.controller.state()["test_in_flight"]
    poll.reply(success())
    rig.wait(lambda s: not s["in_flight"])
    with rig.worker_cv:
        rig.clock.now = 102
        rig.worker_cv.notify_all()
    test = rig.client.call(2)
    assert rig.controller.state()["test_in_flight"]
    test.reply(success(102))
    state = rig.wait(lambda s: s["test_result"] == "success")
    assert not state["test_pending"] and not state["test_in_flight"]
    assert rig.client.maximum_active == 1


def test_callback_never_waits_for_credential_protection(rig, monkeypatch):
    rig.start()
    entered, release, returned = threading.Event(), threading.Event(), threading.Event()
    replace = rig.store.replace

    def protect(*args):
        entered.set()
        assert release.wait(3)
        replace(*args)

    monkeypatch.setattr(rig.store, "replace", protect)
    owner = threading.Thread(
        target=lambda: rig.controller.test_connection(BASE, "map", "new-token")
    )
    owner.start()
    assert entered.wait(2)

    def notify():
        rig.host.notify(5, frozenset({FIRST}), False)
        returned.set()

    callback = threading.Thread(target=notify)
    callback.start()
    try:
        assert returned.wait(1)
        rig.wait(lambda s: not s["automatic_ready"] and s["previewed"] == 1)
    finally:
        release.set()
        owner.join(3)
        callback.join(3)


@pytest.mark.parametrize("code,status", [("invalid_token", 401), ("wrong_map", 403)])
def test_early_auth_denial_clears_names_before_final_http_result(rig, code, status):
    from wingman.wanderer.client import Failure

    rig.start()
    rig.client.call(1).reply(success())
    rig.wait(lambda s: s["available"] == 2)
    with rig.worker_cv:
        rig.clock.now = 102
        rig.worker_cv.notify_all()
    call = rig.client.call(2)
    call.on_authentication_failure(Failure(code, status))
    state = rig.wait(lambda s: s["paused"])
    assert state["available"] == state["matched"] == 0
    assert state["in_flight"]
    with rig.host.cv:
        assert rig.host.cv.wait_for(lambda: not any(rig.host.values.values()), 2)
    call.reply(Failure(code, status))


def test_inert_startup_credential_failure_is_safe_and_explicit_remove_recovers(
    tmp_path, monkeypatch
):
    from wingman.wanderer.controller import WandererController

    rig = Rig(tmp_path)
    original = rig.controller
    original.close_admission()

    def fail(*args):
        raise OSError(TOKEN)

    monkeypatch.setattr(rig.store, "load", fail)
    rig.controller = WandererController(
        rig.cfg["wanderer"], ports=original._ports, credentials=rig.store
    )
    try:
        state = rig.controller.state()
        assert state["credential_error"] and not state["credential_present"]
        assert state["status"] == "credential_error"
        assert TOKEN not in json.dumps(state)
        assert rig.controller.remove_connection(rig.controller.state()["revision"])[
            "persisted"
        ]
        assert not rig.controller.state()["credential_error"]
    finally:
        rig.close()


def test_closed_health_takes_precedence_over_saved_credential_error(
    tmp_path, monkeypatch
):
    from wingman.wanderer.controller import WandererController

    rig = Rig(tmp_path)
    rig.controller.close_admission()

    def fail(*args):
        raise OSError(TOKEN)

    monkeypatch.setattr(rig.store, "load", fail)
    rig.controller = WandererController(
        rig.cfg["wanderer"], ports=rig.controller._ports, credentials=rig.store
    )
    try:
        rig.controller.close_admission()
        assert rig.controller.state()["credential_error"]
        assert rig.controller.state()["status"] == "stopped"
    finally:
        rig.close()


def test_test_outcome_text_does_not_change_when_next_automatic_request_fails(rig):
    from wingman.wanderer.client import Failure

    rig.start()
    rig.client.call(1).reply(success())
    rig.wait(lambda s: not s["in_flight"])
    assert rig.controller.test_connection(BASE, "map", "")["test_accepted"]
    with rig.worker_cv:
        rig.clock.now = 102
        rig.worker_cv.notify_all()
    rig.client.call(2).reply(success(102))
    rig.wait(lambda s: s["test_result"] == "success")
    with rig.worker_cv:
        rig.clock.now = 104
        rig.worker_cv.notify_all()
    rig.client.call(3).reply(Failure("timeout"))
    state = rig.wait(lambda s: s["error_code"] == "timeout")
    assert state["status_text"] == "error"
    assert state["test_result"] == "success"
    assert state["test_result_text"] == "connected"


def test_partial_owner_start_failure_is_terminal_and_safe(tmp_path):
    from wingman.wanderer.controller import WandererController

    rig = Rig(tmp_path, enabled=False)
    original = rig.controller
    original.close_admission()
    created = []

    def spawn(**kwargs):
        if created:
            raise RuntimeError(TOKEN)
        owner = threading.Thread(**kwargs)
        created.append(owner)
        return owner

    rig.controller = WandererController(
        rig.cfg["wanderer"],
        ports=original._ports,
        credentials=rig.store,
        thread_factory=spawn,
    )
    try:
        assert not rig.controller.start()
        assert rig.controller.state()["status"] == "worker_failed"
        assert TOKEN not in json.dumps(rig.controller.state())
        assert not rig.controller.start()
        assert len(created) == 1
        assert rig.host.closed and rig.host.callback is None
    finally:
        rig.close()
