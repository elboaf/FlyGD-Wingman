"""Strict preference persistence, committed hydration and no refused effects."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from tests.test_api import make_api
from tests.test_preview_wiring import FakeHost
from wingman import settings


@pytest.mark.parametrize("raw", [None, 0, 1, "true", "false", [], {}, ""])
def test_malformed_active_preference_normalizes_off(raw):
    assert (
        settings.validated_preview({"hide_active_preview": raw})["hide_active_preview"]
        is False
    )


def test_active_preference_defaults_off_and_roundtrips_without_disturbing_neighbors(
    tmp_path,
):
    path = tmp_path / "settings.json"
    document = settings.load(path)
    assert document["preview"]["hide_active_preview"] is False
    before = document["preview"].copy()
    with settings.update(document, path) as cfg:
        cfg["preview"]["hide_active_preview"] = True
    assert settings.load(path)["preview"] == {**before, "hide_active_preview": True}


@pytest.mark.parametrize("raw", [None, 0, 1, "true", [], {}])
def test_endpoint_refuses_non_bool_without_save_or_restyle(tmp_path, monkeypatch, raw):
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    monkeypatch.setattr(
        settings, "_save_locked", lambda *args: pytest.fail("invalid input saved")
    )
    result = api.set_preview_hide_active_preview(raw)
    assert result["applied"] is result["persisted"] is False
    assert result["error"]
    assert host.restyles == 0


@pytest.mark.parametrize("with_host", [False, True])
def test_setting_while_off_persists_and_hydrates_without_starting(tmp_path, with_host):
    host = FakeHost() if with_host else None
    api = make_api(tmp_path, preview_host=host)
    api._state.settings["preview"] = {"enabled": False}
    assert api.set_preview_hide_active_preview(True) == {
        "applied": True,
        "persisted": True,
        "error": None,
    }
    assert api.get_settings()["preview_hide_active_preview"] is True
    assert api.get_settings()["settings"]["preview"]["hide_active_preview"] is True
    if host:
        assert host.restyles == 1
        assert host.started == host.stopped == 0


@pytest.mark.parametrize("fail", [False, True])
def test_save_barrier_keeps_policy_committed_and_refusal_has_no_effect(
    tmp_path, monkeypatch, fail
):
    host = FakeHost()
    api = make_api(tmp_path, preview_host=host)
    # make_api deliberately starts with a minimal legacy settings document.
    # Publish normalization before testing an actual boolean change.
    with settings.update(api._state.settings):
        pass
    reader = settings.committed_preview(api._state.settings)
    entered, release = Event(), Event()
    original = settings._save_locked

    def save(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        if fail:
            raise OSError("read-only")
        original(*args, **kwargs)

    monkeypatch.setattr(settings, "_save_locked", save)
    with ThreadPoolExecutor() as pool:
        write = pool.submit(api.set_preview_hide_active_preview, True)
        try:
            assert entered.wait(5)
            assert pool.submit(reader.get, "hide_active_preview").result(1) is False
            assert host.restyles == 0
        finally:
            release.set()
        result = write.result(5)
    assert result["persisted"] is (not fail)
    assert result["applied"] is (not fail)
    assert reader.get("hide_active_preview") is (not fail)
    assert host.restyles == (0 if fail else 1)
