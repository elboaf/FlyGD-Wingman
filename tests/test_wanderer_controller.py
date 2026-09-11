"""Committed transactions and real retained owners; no timing sleeps."""

import json
import threading

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
    def __init__(self, tmp_path, *, enabled=True, previews=True, delivery=None):
        from wingman.wanderer.controller import WandererController, WandererPorts

        self.cfg = settings.load()
        self.cfg["wanderer"] = {
            "enabled": enabled,
            "base_url": BASE,
            "map_identifier": "map",
        }
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


def test_failed_save_retains_committed_generation_and_acknowledgement(rig, monkeypatch):
    rig.start()
    rig.client.call(1).reply(success())
    before = rig.wait(lambda s: s["status"] == "connected")

    def fail(*args):
        raise OSError(TOKEN)

    monkeypatch.setattr(settings, "_save_locked", fail)
    for method, value in (
        ("set_enabled", False),
        ("set_url", "https://other.example"),
        ("set_map", "other"),
    ):
        result = getattr(rig.controller, method)(value)
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


def test_binding_edits_never_rebind_token_and_stale_submission_is_refused(rig):
    rig.start()
    rig.client.call(1).reply(success())
    rig.wait(lambda s: not s["in_flight"])
    result = rig.controller.set_map("other")
    assert result["applied"] and result["persisted"]
    assert not result["acknowledged"]["credential_present"]
    assert rig.store.load(BASE, "map") == TOKEN
    assert rig.store.load(BASE, "other") is None
    refused = rig.controller.replace_token("new-token", BASE, "map")
    assert not refused["applied"]
    assert refused["acknowledged"]["map_identifier"] == "other"
    assert rig.store.load(BASE, "map") == TOKEN
    assert rig.controller.replace_token("new-token", BASE, "other")["persisted"]
    assert rig.store.load(BASE, "other") == "new-token"


def test_failed_credential_replace_and_remove_retain_runtime(rig, monkeypatch):
    rig.start()
    rig.client.call(1).reply(success())
    before = rig.wait(lambda s: s["status"] == "connected")

    def fail(*args):
        raise OSError(TOKEN)

    monkeypatch.setattr(rig.store, "replace", fail)
    monkeypatch.setattr(rig.store, "remove", fail)
    for result in (
        rig.controller.replace_token("new-token", BASE, "map"),
        rig.controller.remove_connection(),
    ):
        assert not result["applied"] and not result["persisted"]
        assert result["acknowledged"]["credential_present"]
        assert TOKEN not in json.dumps(result)
    assert rig.controller.state()["generation"] == before["generation"]


def test_explicit_remove_only_deletes_credential(rig, monkeypatch):
    rig.start()
    rig.client.call(1).reply(success())
    rig.wait(lambda s: not s["in_flight"])
    before = dict(rig.cfg["wanderer"])

    def fail(*args):
        pytest.fail("Remove must not write the settings document")

    monkeypatch.setattr(settings, "_save_locked", fail)
    result = rig.controller.remove_connection()
    assert result["applied"] and result["persisted"]
    assert rig.cfg["wanderer"] == before
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


def test_off_test_is_async_does_not_enable_and_shutdown_retains_owners(tmp_path):
    rig = Rig(tmp_path, enabled=False, previews=False)
    try:
        rig.start()
        result = rig.controller.test_connection()
        assert result["applied"] and result["persisted"]
        assert not result["acknowledged"]["enabled"]
        call = rig.client.call(1)
        assert rig.controller.state()["test_in_flight"]
        assert not rig.controller.test_connection()["applied"]
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
        rig.host.notify(1, frozenset({FIRST}), False)
        rig.wait(lambda s: not s["automatic_ready"])
        assert not any(rig.host.values.values())
        assert not rig.controller.stop(0)
    finally:
        release.set()
        rig.close()
