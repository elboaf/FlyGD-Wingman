"""Per-field settings writes.

The Settings screen commits one field at a time and has no Save button, so
these endpoints carry the guards the old whole-document `save_settings`
got for free from an explicit commit. Each one is a guard that a blur or a
stray change must not be able to walk through.

The harness is `test_api_settings.settings_api`, reused rather than
rebuilt: it fakes only `_save_locked`, so the real lock-and-rollback
machinery in `settings.update` stays in the loop.
"""
import pytest

from obs_youtube_uploader.ui import api as api_mod
from tests import fakes
from tests.test_api_settings import settings_api


# ---- shape ------------------------------------------------------------

def test_a_refusal_is_distinguishable_from_a_failed_write(monkeypatch, tmp_path):
    """Three outcomes, not two. A bare bool would collapse "we rejected
    what you typed" and "it took effect but did not reach the disk" into
    one answer, and the page has to say something different for each."""
    api, _window, _saved = settings_api(tmp_path, monkeypatch)

    refused = api.set_category("gaming")
    assert refused["applied"] is False
    assert refused["persisted"] is False
    assert refused["error"]

    ok = api.set_category("22")
    assert ok == {"applied": True, "persisted": True, "error": None}


def test_an_unwritable_settings_file_still_applies_the_change(monkeypatch, tmp_path):
    """A settings file that cannot be written must not stop the setting
    taking effect -- but the page has to be able to say it is not saved,
    or the control shows a choice the next restart discards."""
    api, _window, _saved = settings_api(tmp_path, monkeypatch)

    def boom(data, path=None):
        raise OSError("read-only")

    monkeypatch.setattr(api_mod.settings_mod, "_save_locked", boom)
    result = api.set_privacy("public")

    assert result["applied"] is True
    assert result["persisted"] is False


# ---- the no-op guard --------------------------------------------------

def test_rewriting_the_same_value_does_not_touch_the_file(monkeypatch, tmp_path):
    """settings.save projects the COMPLETE document, so a no-op write is a
    full rewrite -- and an immediate-save page re-emits on every render.
    save_settings had no such guard and also re-ran OBS detection and a
    whole list_rows() ffprobe sweep each time."""
    api, _window, saved = settings_api(tmp_path, monkeypatch)
    api.set_privacy("public")
    assert saved["privacy"] == "public"

    saved.clear()
    result = api.set_privacy("public")

    assert result["applied"] is True
    assert saved == {}, "a no-op write reached _save_locked"


# ---- scalars ----------------------------------------------------------

@pytest.mark.parametrize("value", ["private", "unlisted", "public"])
def test_every_privacy_the_select_offers_is_accepted(monkeypatch, tmp_path, value):
    # Asserted on the live settings, not on what reached the disk: the
    # harness starts at "unlisted", and that case is a no-op write by
    # design (see the guard test above). Both paths must still leave the
    # setting at the requested value.
    api, _window, _saved = settings_api(tmp_path, monkeypatch)
    assert api.set_privacy(value)["applied"] is True
    assert api._state.settings["privacy"] == value


def test_a_bogus_privacy_is_refused_rather_than_silently_coerced(monkeypatch, tmp_path):
    """settings._normalize would quietly turn this into the default, which
    on an immediate-save screen means the user watches their choice snap
    back with no explanation."""
    api, _window, saved = settings_api(tmp_path, monkeypatch)
    assert api.set_privacy("secret")["applied"] is False
    assert saved == {}


def test_a_non_numeric_category_is_refused(monkeypatch, tmp_path):
    api, _window, saved = settings_api(tmp_path, monkeypatch)
    assert api.set_category("gaming")["applied"] is False
    assert saved == {}


def test_a_category_is_stripped_before_it_is_stored(monkeypatch, tmp_path):
    api, _window, saved = settings_api(tmp_path, monkeypatch)
    assert api.set_category("  22  ")["applied"] is True
    assert saved["category"] == "22"


def test_a_bogus_notify_mode_is_refused(monkeypatch, tmp_path):
    api, _window, saved = settings_api(tmp_path, monkeypatch)
    assert api.set_notify_mode("carrier-pigeon")["applied"] is False
    assert saved == {}


# ---- the webhook ------------------------------------------------------

def test_an_empty_webhook_is_refused_rather_than_treated_as_a_clear(monkeypatch, tmp_path):
    """THE wipe guard. save_settings skips validation entirely when the
    value is empty and writes "", so under immediate-save a select-all,
    Delete, then look away would destroy a configured secret -- with no
    Cancel to take it back and no pre-edit copy anywhere on the page."""
    api, _window, saved = settings_api(
        tmp_path, monkeypatch,
        settings={"discord_webhook": "https://discord.com/api/webhooks/1/abc"})

    result = api.set_discord_webhook("")

    assert result["applied"] is False
    assert saved == {}
    assert api._state.settings["discord_webhook"] == (
        "https://discord.com/api/webhooks/1/abc")


def test_whitespace_alone_is_also_refused(monkeypatch, tmp_path):
    api, _window, saved = settings_api(tmp_path, monkeypatch)
    assert api.set_discord_webhook("   ")["applied"] is False
    assert saved == {}


def test_an_unparseable_webhook_is_refused_and_says_why(monkeypatch, tmp_path):
    """The parse error is returned for the field's own inline message.
    save_settings routed this through _alert, which QUEUES -- so a URL
    typed a character at a time stacked a pile of modal dialogs."""
    api, _window, saved = settings_api(tmp_path, monkeypatch)

    result = api.set_discord_webhook("https://example.com/not-a-webhook")

    assert result["applied"] is False
    assert result["error"]
    assert saved == {}


def test_clearing_a_webhook_is_its_own_explicit_action(monkeypatch, tmp_path):
    api, _window, saved = settings_api(
        tmp_path, monkeypatch,
        settings={"discord_webhook": "https://discord.com/api/webhooks/1/abc"})

    assert api.clear_discord_webhook()["applied"] is True
    assert saved["discord_webhook"] == ""


# ---- folders ----------------------------------------------------------

def test_a_new_recording_folder_rebinds_the_live_watcher(monkeypatch, tmp_path):
    new_dir = tmp_path / "elsewhere"
    new_dir.mkdir()
    watcher = fakes.FakeWatcher(tmp_path)
    api, _window, _saved = settings_api(tmp_path, monkeypatch, watcher=watcher)

    assert api.set_folder("recording", str(new_dir))["applied"] is True

    assert watcher.rebound == [new_dir]
    assert api._state.recording_dir == new_dir


def test_recommitting_the_same_folder_never_rebinds(monkeypatch, tmp_path):
    """THE re-baseline guard, and the reason free text commits on Enter
    rather than on blur. rebind() marks every file already in the folder
    as seen, so a redundant rebind silently suppresses the announcement
    for anything that landed since startup but has not yet been polled."""
    watcher = fakes.FakeWatcher(tmp_path)
    api, _window, _saved = settings_api(tmp_path, monkeypatch, watcher=watcher)

    api.set_folder("recording", str(tmp_path))

    assert watcher.rebound == []


def test_a_folder_that_does_not_exist_leaves_the_watcher_alone(monkeypatch, tmp_path):
    watcher = fakes.FakeWatcher(tmp_path)
    api, _window, saved = settings_api(tmp_path, monkeypatch, watcher=watcher)

    result = api.set_folder("recording", str(tmp_path / "nope"))

    assert result["applied"] is False
    assert watcher.rebound == []
    assert saved == {}
    assert api._state.recording_dir == tmp_path


def test_an_empty_recording_folder_does_not_blame_a_folder_called_None(monkeypatch, tmp_path):
    """save_settings mapped an empty field to Path("None") and told the
    user that "None is not a folder"."""
    api, _window, _saved = settings_api(tmp_path, monkeypatch)

    result = api.set_folder("recording", "")

    assert result["applied"] is False
    assert "None" not in result["error"]


def test_a_first_folder_starts_watching_instead_of_rebinding(monkeypatch, tmp_path):
    """The hole this endpoint closes. set_recording_dir could only CREATE
    a watcher and save_settings could only REPOINT one, so with _watcher
    None the folder persisted and list_rows un-gated -- the window looked
    healthy -- while nothing ever started polling."""
    new_dir = tmp_path / "elsewhere"
    new_dir.mkdir()
    api, _window, _saved = settings_api(tmp_path, monkeypatch, watcher=None)
    started = []
    api._on_recording_dir_ready = started.append

    assert api.set_folder("recording", str(new_dir))["applied"] is True

    assert started == [new_dir]


def test_an_empty_gamelogs_folder_is_stored_as_no_folder(monkeypatch, tmp_path):
    """Unlike the recording folder this drives no watcher, and empty
    legitimately means "I have no gamelogs folder"."""
    api, _window, saved = settings_api(
        tmp_path, monkeypatch, settings={"gamelogs_dir": str(tmp_path)})

    assert api.set_folder("gamelogs", "")["applied"] is True
    assert saved["gamelogs_dir"] is None


def test_a_gamelogs_folder_that_does_not_exist_is_refused(monkeypatch, tmp_path):
    """save_settings never validated this one at all, so every
    intermediate prefix of a typed path persisted silently."""
    api, _window, saved = settings_api(tmp_path, monkeypatch)

    assert api.set_folder("gamelogs", str(tmp_path / "nope"))["applied"] is False
    assert saved == {}
