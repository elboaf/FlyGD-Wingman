"""Real settings transactions with only the Discord HTTP boundary replaced."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests import fakes
from tests.test_discord_identity import Response
from wingman import discord, paths, settings

OLD = "https://discord.com/api/webhooks/1111111111/old-secret-token"
NEW = "https://discord.com/api/webhooks/2222222222/new-secret-token"
WARNING = "Webhook saved, but its name could not be identified."


@pytest.fixture
def api(tmp_path, monkeypatch):
    def unavailable(request, timeout=None):
        raise TimeoutError("No live webhook requests in tests")

    monkeypatch.setattr(discord, "_default_transport", unavailable)
    instance, _ = fakes.build_api(
        tmp_path, settings={"discord_webhook": OLD, "discord_webhook_name": "Old name"}
    )
    settings.save(instance._state.settings)
    return instance


def identify_as(monkeypatch, name):
    def transport(request, timeout=None):
        webhook_id = request.full_url.split("/")[-2]
        return Response(json.dumps({"id": webhook_id, "name": name}).encode())

    monkeypatch.setattr(discord, "_default_transport", transport)


def pair(document):
    return document["discord_webhook"], document["discord_webhook_name"]


def test_save_identifies_and_atomically_persists_url_and_name(api, monkeypatch):
    identify_as(monkeypatch, "Combat logs")
    result = api.set_discord_webhook("  " + NEW + "  ")
    assert result["applied"] is True and result["persisted"] is True
    assert result["error"] is None and not result.get("warning")
    assert result["webhook_status"] == "Webhook: Combat logs"
    assert result["webhook_name"] == "Combat logs"
    assert pair(api._state.settings) == pair(settings.load()) == (NEW, "Combat logs")
    assert api._window.calls == []


def test_failed_lookup_saves_replacement_without_old_name(api):
    result = api.set_discord_webhook(NEW)
    assert result["applied"] is True and result["persisted"] is True
    assert result["error"] is None and result["warning"] == WARNING
    assert result["webhook_name"] == ""
    assert result["webhook_status"] == "Webhook saved · name unavailable"
    assert pair(api._state.settings) == pair(settings.load()) == (NEW, "")


def test_identify_updates_saved_identity(api, monkeypatch):
    identify_as(monkeypatch, "Renamed webhook")
    result = api.identify_discord_webhook()
    assert result["applied"] is True and result["persisted"] is True
    assert result["webhook_name"] == "Renamed webhook"
    assert pair(settings.load()) == (OLD, "Renamed webhook")


def test_failed_identify_leaves_existing_identity_and_file_untouched(api):
    before = paths.settings_file().read_bytes()
    result = api.identify_discord_webhook()
    assert result["applied"] is False and result["persisted"] is False
    assert result["error"] and "webhook_status" not in result
    assert pair(api._state.settings) == (OLD, "Old name")
    assert paths.settings_file().read_bytes() == before


def test_remove_clears_both_and_returns_absence(api):
    result = api.clear_discord_webhook()
    assert result["applied"] is True and result["persisted"] is True
    assert result["webhook_status"] == "No Discord webhook saved"
    assert result["webhook_name"] == ""
    assert pair(api._state.settings) == pair(settings.load()) == ("", "")


@pytest.mark.parametrize("operation", ["save", "identify", "remove"])
def test_persist_failure_rolls_back_pair_and_never_logs_secret(
    api, monkeypatch, caplog, operation
):
    identify_as(monkeypatch, "Changed name")
    before = paths.settings_file().read_bytes()

    def fail(data, path=None):
        raise OSError(NEW)

    monkeypatch.setattr(settings, "_save_locked", fail)
    if operation == "save":
        result = api.set_discord_webhook(NEW)
    elif operation == "identify":
        result = api.identify_discord_webhook()
    else:
        result = api.clear_discord_webhook()
    assert result["applied"] is False and result["persisted"] is False
    assert "webhook_status" not in result
    assert pair(api._state.settings) == (OLD, "Old name")
    assert paths.settings_file().read_bytes() == before
    assert "new-secret-token" not in json.dumps(result) + caplog.text


@pytest.mark.parametrize("old_operation", ["save", "identify"])
@pytest.mark.parametrize(
    "new_operation",
    [
        "save",
        "replacement-save",
        "identify",
        "remove",
        "failed-identify",
        "invalid-save",
    ],
)
def test_newer_webhook_admission_fences_older_reply_even_for_same_url(
    api, monkeypatch, old_operation, new_operation
):
    started, release = threading.Event(), threading.Event()
    calls = 0

    def transport(request, timeout=None):
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            assert release.wait(5)
            name = "Stale name"
        elif new_operation == "failed-identify":
            raise TimeoutError("offline")
        else:
            name = "Newest name"
        return Response(
            json.dumps({"id": request.full_url.split("/")[-2], "name": name}).encode()
        )

    monkeypatch.setattr(discord, "_default_transport", transport)
    with ThreadPoolExecutor(max_workers=2) as pool:
        old = (
            pool.submit(api.set_discord_webhook, OLD)
            if old_operation == "save"
            else pool.submit(api.identify_discord_webhook)
        )
        try:
            assert started.wait(5)
            # This also proves the global settings lock is free during HTTP.
            assert pool.submit(api.set_category, "22").result(timeout=5)["applied"]
            if new_operation in ("save", "replacement-save"):
                newer = pool.submit(
                    api.set_discord_webhook,
                    NEW if new_operation == "replacement-save" else OLD,
                )
            elif new_operation in ("identify", "failed-identify"):
                newer = pool.submit(api.identify_discord_webhook)
            elif new_operation == "invalid-save":
                newer = pool.submit(api.set_discord_webhook, "invalid")
            else:
                newer = pool.submit(api.clear_discord_webhook)
            newest = newer.result(timeout=5)
            # A wedged optional owner is retained rather than replaced. Save
            # may still commit its URL without a name; Identify refuses.
            assert calls == 1
        finally:
            release.set()
        result = old.result(timeout=5)
    assert result["applied"] is False and "webhook_status" not in result
    if new_operation == "remove":
        expected = ("", "")
    elif new_operation in ("save", "replacement-save"):
        assert newest["applied"] is True and newest["warning"] == WARNING
        expected = (NEW if new_operation == "replacement-save" else OLD, "")
    else:
        assert newest["applied"] is False
        expected = (OLD, "Old name")
    assert pair(api._state.settings) == pair(settings.load()) == expected
    assert settings.load()["category"] == "22"


@pytest.mark.parametrize("operation", ["save", "identify"])
def test_transaction_rechecks_snapshot_against_other_settings_writers(
    api, monkeypatch, operation
):
    def transport(request, timeout=None):
        with settings.update(api._state.settings) as doc:
            doc["discord_webhook"] = NEW
            doc["discord_webhook_name"] = "External writer"
        return Response(b'{"id":"1111111111","name":"Stale"}')

    monkeypatch.setattr(discord, "_default_transport", transport)
    result = (
        api.set_discord_webhook(OLD)
        if operation == "save"
        else api.identify_discord_webhook()
    )
    assert result["applied"] is False
    assert (
        pair(api._state.settings) == pair(settings.load()) == (NEW, "External writer")
    )


@pytest.mark.parametrize("new_operation", ["save", "identify"])
def test_remove_admitted_before_newer_identity_cannot_clear_it(
    api, monkeypatch, new_operation
):
    started, release = threading.Event(), threading.Event()
    commit = api._commit_webhook

    def paused_commit(generation, previous, url, name):
        if url == "":
            started.set()
            assert release.wait(5)
        return commit(generation, previous, url, name)

    monkeypatch.setattr(api, "_commit_webhook", paused_commit)
    identify_as(monkeypatch, "Newest name")
    with ThreadPoolExecutor(max_workers=2) as pool:
        remove = pool.submit(api.clear_discord_webhook)
        try:
            assert started.wait(5)
            newer = (
                pool.submit(api.set_discord_webhook, NEW)
                if new_operation == "save"
                else pool.submit(api.identify_discord_webhook)
            )
            assert newer.result(timeout=5)["applied"] is True
        finally:
            release.set()
        assert remove.result(timeout=5)["applied"] is False
    assert pair(settings.load()) == (
        NEW if new_operation == "save" else OLD,
        "Newest name",
    )


def test_hydration_is_local_and_has_saved_identity(api, monkeypatch):
    requests = []
    monkeypatch.setattr(
        discord, "_default_transport", lambda *a, **k: requests.append(a)
    )
    for _ in range(3):
        payload = api.get_settings()
        assert payload["webhook_status"] == "Webhook: Old name"
        assert payload["settings"]["discord_webhook_name"] == "Old name"
    assert requests == []


@pytest.mark.parametrize(
    "raw",
    ["", "https://old-secret-token.evil.example/api/webhooks/1/old-secret-token", 42],
)
def test_invalid_saved_webhook_identify_is_safe_and_local(
    api, monkeypatch, caplog, raw
):
    api._state.settings["discord_webhook"] = raw
    requests = []
    monkeypatch.setattr(
        discord, "_default_transport", lambda *a, **k: requests.append(a)
    )
    result = api.identify_discord_webhook()
    assert result["applied"] is False and result["error"]
    assert requests == []
    assert "old-secret-token" not in json.dumps(result) + caplog.text


@pytest.mark.parametrize("operation", ["save", "identify", "remove"])
def test_hydration_revision_precedes_newer_committed_webhook_pair(
    api, monkeypatch, operation
):
    from wingman.ui import api as api_mod

    identify_as(monkeypatch, "Newest name")
    receipts = []

    def during_detection():
        if not receipts:
            receipts.append(
                api.set_discord_webhook(NEW)
                if operation == "save"
                else api.identify_discord_webhook()
                if operation == "identify"
                else api.clear_discord_webhook()
            )

    monkeypatch.setattr(api_mod.obsconfig, "find_recording_dir", during_detection)
    old = api.get_settings()
    current = api.get_settings()
    assert old["settings"]["discord_webhook_name"] == "Old name"
    assert old.get("webhook_revision", -1) < receipts[0].get("webhook_revision", -1)
    assert current["webhook_revision"] == receipts[0]["webhook_revision"]
    assert current["webhook_status"] == receipts[0]["webhook_status"]


def test_hydration_during_lookup_does_not_share_the_future_commit_revision(
    api, monkeypatch
):
    captured = []

    def transport(request, timeout=None):
        captured.append(api.get_settings())
        return Response(b'{"id":"1111111111","name":"Newest name"}')

    monkeypatch.setattr(discord, "_default_transport", transport)
    receipt = api.identify_discord_webhook()
    assert captured[0].get("webhook_revision", -1) < receipt.get("webhook_revision", -1)


def test_echoed_name_is_not_persisted_or_returned(api, monkeypatch, caplog):
    identify_as(monkeypatch, "new-secret-token")
    result = api.set_discord_webhook(NEW)
    assert result["warning"] == WARNING
    assert pair(settings.load()) == (NEW, "")
    assert "new-secret-token" not in json.dumps(result) + caplog.text


def test_timed_out_save_persists_url_without_a_late_name(tmp_path):
    entered = threading.Event()
    release = threading.Event()

    def blocked_lookup(webhook):
        entered.set()
        assert release.wait(5)
        return "Late name"

    lane = discord.WebhookLookupLane(blocked_lookup, deadline_s=0.01)
    api, _ = fakes.build_api(
        tmp_path,
        settings={"discord_webhook": OLD, "discord_webhook_name": "Old name"},
        webhook_lookup=lane,
    )
    settings.save(api._state.settings)
    try:
        result = api.set_discord_webhook(NEW)
        assert entered.wait(1)
        assert result["applied"] and result["warning"] == WARNING
        assert pair(settings.load()) == (NEW, "")
    finally:
        release.set()
        lane.close()
    assert lane.wait_idle(1)
    assert pair(settings.load()) == (NEW, "")


def test_timed_out_identify_refuses_without_persisting(tmp_path):
    entered = threading.Event()
    release = threading.Event()

    def blocked_lookup(webhook):
        entered.set()
        assert release.wait(5)
        return "Late name"

    lane = discord.WebhookLookupLane(blocked_lookup, deadline_s=0.01)
    api, _ = fakes.build_api(
        tmp_path,
        settings={"discord_webhook": OLD, "discord_webhook_name": "Old name"},
        webhook_lookup=lane,
    )
    settings.save(api._state.settings)
    before = paths.settings_file().read_bytes()
    try:
        result = api.identify_discord_webhook()
        assert entered.wait(1)
        assert result["applied"] is False
        assert result["error"] == "Could not identify this webhook. Try again."
        assert paths.settings_file().read_bytes() == before
    finally:
        release.set()
        lane.close()
    assert lane.wait_idle(1)
    assert pair(settings.load()) == (OLD, "Old name")


def test_remove_supersedes_a_timed_out_lookup_without_late_resurrection(tmp_path):
    entered = threading.Event()
    release = threading.Event()

    def blocked_lookup(webhook):
        entered.set()
        assert release.wait(5)
        return "Late name"

    lane = discord.WebhookLookupLane(blocked_lookup, deadline_s=0.05)
    api, _ = fakes.build_api(
        tmp_path,
        settings={"discord_webhook": OLD, "discord_webhook_name": "Old name"},
        webhook_lookup=lane,
    )
    settings.save(api._state.settings)
    with ThreadPoolExecutor(max_workers=2) as pool:
        save = pool.submit(api.set_discord_webhook, NEW)
        assert entered.wait(1)
        removed = api.clear_discord_webhook()
        assert removed["applied"] is True
        assert pair(settings.load()) == ("", "")
        assert save.result(timeout=1)["applied"] is False
    release.set()
    assert lane.wait_idle(1)
    assert pair(settings.load()) == ("", "")


def test_shutdown_fences_a_save_while_lookup_admission_is_closing(tmp_path):
    entered = threading.Event()
    release_identify = threading.Event()
    close_entered = threading.Event()
    release_close = threading.Event()

    class ClosingLane:
        def identify(self, webhook):
            entered.set()
            assert release_identify.wait(1)
            return "Late name"

        def close(self):
            close_entered.set()
            assert release_close.wait(1)
            return False

    api, _ = fakes.build_api(
        tmp_path,
        settings={"discord_webhook": OLD, "discord_webhook_name": "Old name"},
        webhook_lookup=ClosingLane(),
    )
    settings.save(api._state.settings)
    with ThreadPoolExecutor(max_workers=2) as pool:
        save = pool.submit(api.set_discord_webhook, NEW)
        assert entered.wait(1)
        shutdown = pool.submit(api._shutdown_webhook_lookup)
        assert close_entered.wait(1)
        release_identify.set()
        # Closing admission must also own the generation fence, so a result
        # already returning from Identify cannot commit through this gap.
        assert pair(settings.load()) == (OLD, "Old name")
        release_close.set()
        shutdown.result(timeout=1)
        assert save.result(timeout=1)["applied"] is False
    assert pair(settings.load()) == (OLD, "Old name")


def test_shutdown_closes_lookup_admission_without_waiting_for_dns(tmp_path):
    entered = threading.Event()
    release = threading.Event()

    def blocked_lookup(webhook):
        entered.set()
        assert release.wait(5)
        return "Late name"

    lane = discord.WebhookLookupLane(blocked_lookup, deadline_s=0.05)
    api, _ = fakes.build_api(
        tmp_path,
        settings={"discord_webhook": OLD, "discord_webhook_name": "Old name"},
        webhook_lookup=lane,
    )
    settings.save(api._state.settings)
    with ThreadPoolExecutor(max_workers=1) as pool:
        save = pool.submit(api.set_discord_webhook, NEW)
        assert entered.wait(1)
        # This may not join the DNS owner, and closes its generation before
        # the bounded caller attempts a transaction.
        api._shutdown_webhook_lookup()
        assert save.result(timeout=1)["applied"] is False
    assert pair(settings.load()) == (OLD, "Old name")
    release.set()
    assert lane.wait_idle(1)
    assert pair(settings.load()) == (OLD, "Old name")


def test_busy_lookup_does_not_block_save_b_or_an_unrelated_setting(tmp_path):
    entered = threading.Event()
    release = threading.Event()

    def blocked_lookup(webhook):
        entered.set()
        assert release.wait(5)
        return "Late name"

    lane = discord.WebhookLookupLane(blocked_lookup, deadline_s=0.05)
    api, _ = fakes.build_api(
        tmp_path,
        settings={"discord_webhook": OLD, "discord_webhook_name": "Old name"},
        webhook_lookup=lane,
    )
    settings.save(api._state.settings)
    with ThreadPoolExecutor(max_workers=2) as pool:
        save_a = pool.submit(api.set_discord_webhook, OLD)
        assert entered.wait(1)
        # The occupied optional lane is an immediate empty-name result: Save B
        # admits and persists instead of waiting for A's DNS owner.
        save_b = api.set_discord_webhook(NEW)
        assert save_b["applied"] and save_b["warning"] == WARNING
        assert api.set_category("22")["applied"]
        assert save_a.result(timeout=1)["applied"] is False
    release.set()
    assert lane.wait_idle(1)
    assert pair(settings.load()) == (NEW, "")
    assert settings.load()["category"] == "22"
