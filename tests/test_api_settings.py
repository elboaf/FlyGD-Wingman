"""Settings across the bridge.

The dialog is gone; what survives is the behaviour 2.2.0 put into it -- a
masked webhook that reports parse errors, an account control that tracks
four states, two independent Detect actions, and a Save that reaches the
live watcher and not just the settings file.
"""
import types

import pytest

from obs_youtube_uploader import uploader
from obs_youtube_uploader.ui import api as api_mod
from obs_youtube_uploader.ui import copy as copy_mod
from tests import fakes


def test_connected_offers_to_switch_rather_than_to_connect():
    """The button read "Connect Google Account" while the line above it read
    "Connected", which gave no clue what pressing it would do -- and it is
    exactly the control someone reaches for when they suspect the wrong
    account is signed in."""
    message, label, enabled = copy_mod.auth_state("connected")
    assert (message, label, enabled) == ("Connected", "Switch account", True)


def test_disconnected_asks_for_sign_in():
    assert copy_mod.auth_state("disconnected") == (
        "Not connected", "Sign in with Google", True)


def test_both_transient_states_disable_the_button():
    """A second press during the lookup races it, and during the browser
    flow it starts a second OAuth flow on top of the first."""
    for state in ("connecting", "revoking"):
        _message, _label, enabled = copy_mod.auth_state(state)
        assert enabled is False, state


def test_an_unknown_state_stays_usable():
    """Nothing should be able to leave the user with a dead button."""
    assert copy_mod.auth_state("nonsense") == (
        "Not connected", "Sign in with Google", True)


def test_the_page_can_read_the_whole_label_table_in_one_call(tmp_path):
    """Kept in Python, where it is tested, rather than duplicated in JS."""
    api, _window = fakes.build_api(tmp_path)
    table = api.auth_labels()
    assert table["connected"] == {"message": "Connected",
                                  "label": "Switch account", "enabled": True}
    assert set(table) == {"disconnected", "connecting", "connected", "revoking"}



HOOK = "https://discord.com/api/webhooks/1538615213203656754/tok"


def settings_api(tmp_path, monkeypatch, watcher=None, **kw):
    saved = {}
    api, window = fakes.build_api(tmp_path, watcher=watcher, **kw)
    api._alert = fakes.Alerts()
    api.list_rows = lambda preselect=None: None
    monkeypatch.setattr(api_mod.settings_mod, "save",
                        lambda cfg, path=None: saved.update(cfg))
    monkeypatch.setattr(api_mod.settings_mod, "load", lambda path=None: dict(saved))
    return api, window, saved


def values(tmp_path, **kw):
    payload = {"privacy": "public", "category": "20", "notify_mode": "toast",
               "recording_dir": str(tmp_path), "discord_webhook": "",
               "gamelogs_dir": None}
    payload.update(kw)
    return payload


def test_saving_persists_and_reloads_the_canonical_settings(monkeypatch, tmp_path):
    api, _window, saved = settings_api(tmp_path, monkeypatch)
    sent = fakes.record_pushes(api)

    assert api.save_settings(values(tmp_path)) is True

    assert saved["privacy"] == "public"
    assert api._state.settings["privacy"] == "public"
    pushed, = fakes.payloads(sent, "onSettings")
    assert pushed["settings"]["privacy"] == "public"


def test_saving_a_new_recording_folder_rebinds_the_live_watcher(monkeypatch, tmp_path):
    """Persisting the setting alone leaves the watcher polling the old
    folder, so new recordings in the new one are never noticed."""
    new_dir = tmp_path / "elsewhere"
    new_dir.mkdir()
    watcher = fakes.FakeWatcher(tmp_path)
    api, _window, _saved = settings_api(tmp_path, monkeypatch, watcher=watcher)

    api.save_settings(values(tmp_path, recording_dir=str(new_dir)))

    assert watcher.rebound == [new_dir]
    assert api._state.recording_dir == new_dir


def test_saving_the_same_folder_does_not_rebind(monkeypatch, tmp_path):
    """rebind() re-baselines `seen`; doing it on every Save would be work
    with a chance of announcing existing files as new."""
    watcher = fakes.FakeWatcher(tmp_path)
    api, _window, _saved = settings_api(tmp_path, monkeypatch, watcher=watcher)
    api.save_settings(values(tmp_path))
    assert watcher.rebound == []


def test_a_non_numeric_category_is_refused_before_anything_is_written(monkeypatch, tmp_path):
    api, _window, saved = settings_api(tmp_path, monkeypatch)
    assert api.save_settings(values(tmp_path, category="gaming")) is False
    assert saved == {}
    assert api._alert.titles() == ["Invalid category"]


def test_an_invalid_webhook_is_refused_with_the_parse_error(monkeypatch, tmp_path):
    api, _window, saved = settings_api(tmp_path, monkeypatch)
    assert api.save_settings(
        values(tmp_path, discord_webhook="http://discord.com/api/webhooks/1/2")) is False
    assert saved == {}
    kind, title, body = api._alert.raised[0]
    assert title == "Invalid webhook"
    assert "https" in body.lower()


def test_a_recording_folder_that_is_not_a_folder_is_refused(monkeypatch, tmp_path):
    api, _window, saved = settings_api(tmp_path, monkeypatch)
    assert api.save_settings(
        values(tmp_path, recording_dir=str(tmp_path / "nope"))) is False
    assert saved == {}
    assert api._alert.titles() == ["Invalid folder"]


def test_a_settings_file_that_cannot_be_written_leaves_state_untouched(monkeypatch, tmp_path):
    """State and disk must never diverge: bail out before touching memory
    and tell the user, so their edits can be retried."""
    api, _window, _saved = settings_api(tmp_path, monkeypatch)

    def boom(cfg, path=None):
        raise OSError("disk full")

    monkeypatch.setattr(api_mod.settings_mod, "save", boom)

    assert api.save_settings(values(tmp_path)) is False
    assert api._state.settings["privacy"] == "unlisted"
    assert api._alert.titles() == ["Could not save settings"]


def test_the_pushed_settings_describe_the_webhook_without_its_token(monkeypatch, tmp_path):
    """The field is masked in the page, so this line is the only
    confirmation of WHICH webhook is stored. Top-level key, not nested."""
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    sent = fakes.record_pushes(api)
    api.save_settings(values(tmp_path, discord_webhook=HOOK))
    pushed, = fakes.payloads(sent, "onSettings")
    assert "1538615213203656754" in pushed["webhook_status"]
    assert "tok" not in pushed["webhook_status"].split("/")[-1]



def test_browse_opens_a_native_folder_dialog_at_the_current_folder(monkeypatch, tmp_path):
    api, window, _saved = settings_api(tmp_path, monkeypatch)
    monkeypatch.setattr(api_mod, "_folder_dialog_kind", lambda: "FOLDER")
    window.dialog_result = (str(tmp_path / "picked"),)

    assert api.pick_folder("recording") == str(tmp_path / "picked")
    assert window.dialogs == [("FOLDER", str(tmp_path))]


def test_cancelling_the_folder_dialog_returns_nothing(monkeypatch, tmp_path):
    api, window, _saved = settings_api(tmp_path, monkeypatch)
    monkeypatch.setattr(api_mod, "_folder_dialog_kind", lambda: "FOLDER")
    window.dialog_result = None
    assert api.pick_folder("gamelogs") == ""


def test_detect_re_runs_obs_config_for_the_recording_folder(monkeypatch, tmp_path):
    """The recovery path for a bad stored recording_dir: the stored value
    normally outranks detection, so nothing else ever re-runs the guess."""
    found = tmp_path / "obs"
    found.mkdir()
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    monkeypatch.setattr(api_mod.obsconfig, "find_recording_dir", lambda: found)

    assert api.detect_folder("recording", current=str(tmp_path)) == str(found)
    assert api._alert.raised == []


def test_detect_for_gamelogs_is_a_separate_search(monkeypatch, tmp_path):
    found = tmp_path / "Gamelogs"
    found.mkdir()
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    monkeypatch.setattr(api_mod.combatlog, "find_gamelogs_dir", lambda: found)

    assert api.detect_folder("gamelogs", current="") == str(found)


def test_detect_says_when_it_cannot_find_the_recording_folder(monkeypatch, tmp_path):
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    monkeypatch.setattr(api_mod.obsconfig, "find_recording_dir", lambda: None)

    assert api.detect_folder("recording") == ""
    kind, title, body = api._alert.raised[0]
    assert (kind, title) == ("info", "Detect recording folder")
    assert "OBS" in body


def test_detect_says_when_it_cannot_find_the_gamelogs_folder(monkeypatch, tmp_path):
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    monkeypatch.setattr(api_mod.combatlog, "find_gamelogs_dir", lambda: None)

    assert api.detect_folder("gamelogs") == ""
    assert api._alert.titles() == ["Gamelogs not found"]


def test_detect_that_agrees_with_the_field_says_so_rather_than_nothing(monkeypatch, tmp_path):
    """Silently rewriting the field with the value already in it looks like
    a dead button."""
    found = tmp_path / "obs"
    found.mkdir()
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    monkeypatch.setattr(api_mod.obsconfig, "find_recording_dir", lambda: found)

    assert api.detect_folder("recording", current=str(found)) == ""
    assert "Already set" in api._alert.raised[0][2]



def test_connecting_announces_the_transient_state_before_the_browser_opens(monkeypatch, tmp_path):
    """The state, not just the outcome: the page disables the control while
    it is connecting so a second press cannot start a second OAuth flow."""
    api, _window = fakes.build_api(tmp_path)
    api._alert = fakes.Alerts()
    sent = fakes.record_pushes(api)
    monkeypatch.setattr(uploader, "run_oauth_flow",
                        lambda: types.SimpleNamespace(valid=True))
    monkeypatch.setattr(uploader, "save_credentials", lambda c, p: None)

    api.connect_google()
    api._auth_thread.join(timeout=5)

    states = [p["state"] for p in fakes.payloads(sent, "onAuthState")]
    assert states == ["connecting", "connected"]
    assert fakes.payloads(sent, "onAuthState")[0]["message"] == "Waiting for browser…"


def test_a_failed_sign_in_reports_it_and_returns_to_disconnected(monkeypatch, tmp_path):
    api, _window = fakes.build_api(tmp_path)
    api._alert = fakes.Alerts()
    sent = fakes.record_pushes(api)

    def boom():
        raise RuntimeError("the user closed the browser")

    monkeypatch.setattr(uploader, "run_oauth_flow", boom)

    api.connect_google()
    api._auth_thread.join(timeout=5)

    assert [p["state"] for p in fakes.payloads(sent, "onAuthState")] == [
        "connecting", "disconnected"]
    kind, title, body = api._alert.raised[0]
    assert (kind, title) == ("error", "Connection failed")
    assert "browser" in body


def test_a_second_press_while_connecting_is_ignored(monkeypatch, tmp_path):
    """The button is disabled in the page, but the guard lives here too:
    two concurrent OAuth flows would fight over the loopback port."""
    import threading as _threading

    gate = _threading.Event()
    api, _window = fakes.build_api(tmp_path)
    api._alert = fakes.Alerts()
    monkeypatch.setattr(uploader, "run_oauth_flow",
                        lambda: (gate.wait(5), types.SimpleNamespace(valid=True))[1])
    monkeypatch.setattr(uploader, "save_credentials", lambda c, p: None)

    api.connect_google()
    first = api._auth_thread
    api.connect_google()
    assert api._auth_thread is first
    gate.set()
    first.join(timeout=5)


def test_the_startup_check_resolves_the_state_off_the_bridge_thread(monkeypatch, tmp_path):
    """load_credentials drags in google.auth, requests and cryptography;
    off a PyInstaller build's disk that is a visible pause."""
    api, _window = fakes.build_api(tmp_path)
    sent = fakes.record_pushes(api)
    monkeypatch.setattr(uploader, "load_credentials",
                        lambda p: types.SimpleNamespace(valid=True))
    monkeypatch.setattr(uploader, "needs_reauth", lambda c: False)

    api.refresh_auth()
    api._auth_thread.join(timeout=5)

    assert [p["state"] for p in fakes.payloads(sent, "onAuthState")] == [
        "connecting", "connected"]


def test_an_unreadable_token_reads_as_not_connected(monkeypatch, tmp_path):
    """Never leave the control stuck mid-check: an unreadable token is
    indistinguishable from not being connected, and that is exactly what
    the user needs to be told."""
    api, _window = fakes.build_api(tmp_path)
    sent = fakes.record_pushes(api)

    def boom(path):
        raise OSError("token unreadable")

    monkeypatch.setattr(uploader, "load_credentials", boom)

    api.refresh_auth()
    api._auth_thread.join(timeout=5)

    assert fakes.payloads(sent, "onAuthState")[-1]["state"] == "disconnected"


def test_first_run_persists_the_folder_and_starts_the_watcher(monkeypatch, tmp_path):
    folder = tmp_path / "recordings"
    folder.mkdir()
    api, _window, saved = settings_api(tmp_path, monkeypatch)
    started = []
    api._on_recording_dir_ready = started.append

    assert api.set_recording_dir(str(folder)) is True

    assert saved["recording_dir"] == str(folder)
    assert api._state.recording_dir == folder
    assert started == [folder], "the watcher was never started"


def test_first_run_refuses_a_folder_that_is_not_one(monkeypatch, tmp_path):
    """Returning False is what keeps the first-run screen up. Dropping the
    user into an empty list with no explanation is the failure mode."""
    api, _window, saved = settings_api(tmp_path, monkeypatch)
    started = []
    api._on_recording_dir_ready = started.append

    assert api.set_recording_dir(str(tmp_path / "nope")) is False
    assert saved == {}
    assert started == []
    assert api._alert.titles() == ["Invalid folder"]


def test_first_run_leaves_state_untouched_when_the_save_fails(monkeypatch, tmp_path):
    """State and disk must never diverge, the same guarantee save_settings
    gives. Mutating before the write means a failed first-run save leaves
    the app believing it has a recording folder it never persisted."""
    folder = tmp_path / "recordings"
    folder.mkdir()
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    started = []
    api._on_recording_dir_ready = started.append
    before = dict(api._state.settings)

    def boom(cfg, path=None):
        raise OSError("disk full")

    monkeypatch.setattr(api_mod.settings_mod, "save", boom)

    assert api.set_recording_dir(str(folder)) is False
    assert api._state.settings == before, "in-memory settings were mutated"
    assert api._state.recording_dir != folder
    assert started == [], "the watcher was started despite a failed save"
    assert api._alert.titles() == ["Could not save settings"]
