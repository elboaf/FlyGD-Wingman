"""Grouped connection persistence — real settings/store/controller/HTTP owner."""

import json
import threading

import pytest

from tests.test_wanderer_controller import BASE, TOKEN, Rig
from tests.test_wanderer_worker import success
from wingman import paths, settings


@pytest.fixture
def rig(tmp_path):
    value = Rig(tmp_path, enabled=False, previews=False)
    try:
        yield value
    finally:
        value.close()


def test_first_setup_protects_binding_then_saves_before_single_runtime_commit(
    tmp_path, monkeypatch
):
    rig = Rig(
        tmp_path,
        previews=False,
        section={"enabled": False, "base_url": "", "map_identifier": ""},
    )
    rig.store.remove()
    original = settings._save_locked
    observed = []

    def save(*args):
        assert rig.store.load(BASE, "map") == TOKEN
        assert rig.worker._request_thread is None
        observed.append(rig.controller.state()["revision"])
        original(*args)

    monkeypatch.setattr(settings, "_save_locked", save)
    try:
        result = rig.controller.test_connection(
            " HTTPS://WANDERER.example:443/prefix/ ", " map ", TOKEN
        )
        assert result["applied"] and result["persisted"] and result["test_accepted"]
        assert result["test_error"] is None
        assert observed == [0]
        assert result["acknowledged"]["revision"] == 1
        assert settings.load()["wanderer"] == {
            "enabled": False,
            "base_url": BASE,
            "map_identifier": "map",
        }
        assert rig.client.call(1).args == (BASE, "map", TOKEN, None)
        assert result["test_generation"] == rig.controller.state()["generation"]
        assert TOKEN not in json.dumps(result)
    finally:
        rig.close()


def test_blank_token_reuses_only_current_normalized_binding_without_disk_reload(
    rig, monkeypatch
):
    def forbidden(*args):
        pytest.fail(
            "Unchanged saved connection must not reload or replace a credential"
        )

    monkeypatch.setattr(rig.store, "load", forbidden)
    monkeypatch.setattr(rig.store, "replace", forbidden)
    result = rig.controller.test_connection(
        " https://WANDERER.example:443/prefix/ ", " map ", ""
    )
    assert result["test_accepted"]
    assert result["acknowledged"]["revision"] == 0
    assert rig.client.call(1).args == (BASE, "map", TOKEN, None)


@pytest.mark.parametrize(
    "base,map_id", [("https://other.example", "map"), (BASE, "other")]
)
def test_changed_binding_blank_token_refused_even_if_old_file_matches(
    rig, base, map_id
):
    rig.store.replace(base, map_id, "stranded-token")
    before = rig.store.snapshot()
    result = rig.controller.test_connection(base, map_id, "")
    assert (
        not result["applied"]
        and not result["persisted"]
        and not result["test_accepted"]
    )
    assert result["acknowledged"]["base_url"] == BASE
    assert result["acknowledged"]["map_identifier"] == "map"
    assert rig.store.snapshot() == before
    assert rig.worker._request_thread is None


@pytest.mark.parametrize("operation", ["test", "remove"])
@pytest.mark.parametrize("active", [False, True])
def test_failed_settings_compensates_exact_ciphertext_without_runtime_admission(
    rig, monkeypatch, operation, active
):
    if active:
        assert rig.controller.set_enabled(True)["persisted"]
        rig.controller.set_previews_enabled(True)
        rig.start()
        rig.client.call(1).reply(success())
        rig.wait(lambda s: s["status"] == "connected")
    before = rig.store.snapshot()
    state = rig.controller.state()
    owner = rig.worker._request_thread
    staged = []

    def fail(*args):
        staged.append(
            rig.store.load("https://new.example", "new-map")
            if operation == "test"
            else rig.store.snapshot()
        )
        raise OSError(TOKEN)

    monkeypatch.setattr(settings, "_save_locked", fail)
    result = (
        rig.controller.test_connection("https://new.example", "new-map", "candidate")
        if operation == "test"
        else rig.controller.remove_connection(state["revision"])
    )
    assert not result["applied"] and not result["persisted"]
    assert rig.store.snapshot() == before
    assert rig.store.load(BASE, "map") == TOKEN
    assert rig.controller.state() == state
    assert rig.cfg["wanderer"]["base_url"] == BASE
    assert staged == (["candidate"] if operation == "test" else [None])
    assert rig.worker._request_thread is owner
    assert len(rig.client.calls) == int(active)
    assert TOKEN not in json.dumps(result)


def test_first_setup_failed_save_restores_absent_credential(tmp_path, monkeypatch):
    rig = Rig(
        tmp_path, section={"enabled": False, "base_url": "", "map_identifier": ""}
    )
    rig.store.remove()

    def fail(*args):
        raise OSError(TOKEN)

    monkeypatch.setattr(settings, "_save_locked", fail)
    try:
        result = rig.controller.test_connection(BASE, "map", TOKEN)
        assert not result["persisted"]
        assert rig.store.snapshot() is None
        assert not result["acknowledged"]["credential_present"]
        assert rig.worker._request_thread is None
    finally:
        rig.close()


@pytest.mark.parametrize("operation", ["test", "remove"])
def test_failed_compensation_closes_admission_and_does_not_claim_healthy_rollback(
    rig, monkeypatch, operation
):
    rig.start()
    before = rig.controller.state()

    def fail(*args):
        raise OSError(TOKEN)

    monkeypatch.setattr(settings, "_save_locked", fail)
    monkeypatch.setattr(rig.store, "restore", fail)
    result = (
        rig.controller.test_connection(BASE, "map", "candidate")
        if operation == "test"
        else rig.controller.remove_connection(before["revision"])
    )
    assert not result["applied"] and not result["persisted"]
    assert result["acknowledged"]["persistence_error"]
    assert not result["acknowledged"]["credential_present"]
    assert result["acknowledged"]["revision"] > before["revision"]
    assert "restore" in result["error"].lower() and "restart" in result["error"].lower()
    assert rig.controller.state()["status"] == "persistence_error"
    assert not rig.controller.start()
    assert not rig.controller.test_connection(BASE, "map", "candidate")["test_accepted"]
    assert rig.host.closed and rig.host.callback is None
    assert rig.worker._request_thread is None
    assert rig.controller._token is None
    assert TOKEN not in json.dumps(result)


def test_snapshot_failure_refuses_before_any_protected_or_settings_write(
    rig, monkeypatch
):
    before = rig.controller.state()
    protected = rig.store.snapshot()

    def fail(*args):
        raise OSError(TOKEN)

    monkeypatch.setattr(rig.store, "snapshot", fail)
    result = rig.controller.test_connection(BASE, "new-map", "candidate")
    assert not result["persisted"] and not result["test_accepted"]
    assert rig.store._path.read_bytes() == protected
    assert rig.controller.state() == before
    assert not paths.settings_file().exists()
    assert TOKEN not in json.dumps(result)


def test_successful_save_survives_worker_owner_start_failure(rig, monkeypatch):
    def fail(**kwargs):
        raise RuntimeError(TOKEN)

    monkeypatch.setattr(rig.controller, "_thread_factory", fail)
    result = rig.controller.test_connection(
        "https://new.example", "new-map", "candidate"
    )
    assert result["applied"] and result["persisted"] and result["error"] is None
    assert not result["test_accepted"] and result["test_error"]
    assert settings.load()["wanderer"]["base_url"] == "https://new.example"
    assert rig.store.load("https://new.example", "new-map") == "candidate"
    assert rig.controller.state()["status"] == "worker_failed"
    assert rig.worker._request_thread is None
    assert TOKEN not in json.dumps(result)


def test_new_saved_configuration_is_distinct_from_busy_test_admission(rig):
    first = rig.controller.test_connection(BASE, "map", "")
    assert first["test_accepted"]
    call = rig.client.call(1)
    owner = rig.worker._request_thread
    result = rig.controller.test_connection("https://new.example", "new", "new-token")
    assert result["applied"] and result["persisted"]
    assert result["error"] is None
    assert not result["test_accepted"] and result["test_error"]
    assert result["acknowledged"]["base_url"] == "https://new.example"
    assert rig.store.load("https://new.example", "new") == "new-token"
    assert rig.worker._request_thread is owner
    call.reply(success())
    rig.wait(lambda s: not s["in_flight"])
    assert rig.controller.state()["test_result"] is None
    assert rig.client.maximum_active == 1


def test_remove_requires_current_confirmation_revision(rig):
    old = rig.controller.state()["revision"]
    assert rig.controller.set_enabled(True)["persisted"]
    result = rig.controller.remove_connection(old)
    assert not result["applied"]
    assert rig.store.load(BASE, "map") == TOKEN
    assert result["acknowledged"]["enabled"]


def test_shutdown_during_grouped_save_reports_persisted_but_no_test_or_cached_token(
    rig, monkeypatch
):
    entered, release = threading.Event(), threading.Event()
    original = settings._save_locked
    results = []

    def save(*args):
        entered.set()
        assert release.wait(3)
        original(*args)

    monkeypatch.setattr(settings, "_save_locked", save)
    owner = threading.Thread(
        target=lambda: results.append(
            rig.controller.test_connection(BASE, "new", "new-token")
        )
    )
    owner.start()
    try:
        assert entered.wait(2)
        rig.controller.close_admission()
    finally:
        release.set()
        owner.join(3)
    assert not owner.is_alive()
    result = results[0]
    assert result["applied"] and result["persisted"] and not result["test_accepted"]
    assert result["test_error"]
    assert settings.load()["wanderer"]["map_identifier"] == "new"
    assert rig.controller.state()["status"] == "stopped"
    assert rig.controller._token is None
    assert rig.worker._request_thread is None
