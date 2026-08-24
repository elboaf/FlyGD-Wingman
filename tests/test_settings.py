import json
import pytest
from obs_youtube_uploader import bookmarks, settings


def test_defaults_are_the_documented_values():
    assert settings.DEFAULTS == {
        "privacy": "unlisted",
        "category": "20",
        "notify_mode": "toast",
        "recording_dir": None,
        "discord_webhook": "",
        "gamelogs_dir": None,
        "channel_id": "",
        "channel_title": "",
        "eve_bookmarks": {
            "enabled": False,
            "keybinds": bookmarks.DEFAULT_BINDS,
            "windows": {},
        },
        "preview": {
            # Off by default for the same reason eve_bookmarks is:
            # enabling it starts a thread, a 700ms discovery sweep and a
            # foreground hook, none of which a non-EVE user should pay.
            "enabled": False,
            "width": 320,
            "height": 210,
            "opacity": 235,
            "layouts": {},
            "restore_clients_on_launch": False,
            "client_layouts": {},
        },
        "eve_settings": {
            "root": None,
            "server": None,
            "profile": None,
            "auto_keep": 10,
        },
    }


def test_channel_identity_defaults_to_empty(tmp_path):
    """Empty, not None: it reaches a label, and "None" is not a channel."""
    data = settings.load(tmp_path / "missing.json")
    assert data["channel_id"] == ""
    assert data["channel_title"] == ""


def test_channel_identity_roundtrips(tmp_path):
    p = tmp_path / "s.json"
    settings.save({**settings.DEFAULTS, "channel_id": "UC123",
                   "channel_title": "Zoolanders"}, p)
    loaded = settings.load(p)
    assert loaded["channel_id"] == "UC123"
    assert loaded["channel_title"] == "Zoolanders"


@pytest.mark.parametrize("bad", [{"nope": 1}, 7, None, ["a"]])
def test_non_string_channel_identity_is_discarded(tmp_path, bad):
    """This value is read back from a YouTube API response and then rendered
    into a label; a dict or an int arriving from a hand-edited file must not
    reach the UI."""
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"channel_title": bad, "channel_id": bad}))
    loaded = settings.load(p)
    assert loaded["channel_title"] == ""
    assert loaded["channel_id"] == ""


def test_discord_webhook_roundtrips(tmp_path):
    p = tmp_path / "s.json"
    url = "https://discord.com/api/webhooks/123/tok"
    settings.save({**settings.DEFAULTS, "discord_webhook": url}, p)
    assert settings.load(p)["discord_webhook"] == url


def test_gamelogs_dir_roundtrips(tmp_path):
    p = tmp_path / "s.json"
    settings.save({**settings.DEFAULTS, "gamelogs_dir": "C:/logs"}, p)
    assert settings.load(p)["gamelogs_dir"] == "C:/logs"


def test_non_string_discord_webhook_is_coerced(tmp_path):
    """settings.json is a plain file a user can edit; save-time UI validation
    does not protect the load path."""
    import json
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"discord_webhook": 12345}))
    assert settings.load(p)["discord_webhook"] == ""


def test_non_string_gamelogs_dir_is_coerced(tmp_path):
    import json
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"gamelogs_dir": ["a", "b"]}))
    assert settings.load(p)["gamelogs_dir"] is None


def test_recording_dir_roundtrips(tmp_path):
    """Regression guard: save() projects onto DEFAULTS keys, so a key not
    declared there is silently dropped and the folder is re-picked every
    launch."""
    p = tmp_path / "s.json"
    settings.save({**settings.DEFAULTS, "recording_dir": "C:/rec"}, p)
    assert settings.load(p)["recording_dir"] == "C:/rec"


def test_recording_dir_defaults_to_none(tmp_path):
    assert settings.load(tmp_path / "nope.json")["recording_dir"] is None


def test_load_returns_defaults_when_file_missing(tmp_path):
    assert settings.load(tmp_path / "nope.json") == settings.DEFAULTS


def test_load_merges_partial_file_over_defaults(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"privacy": "unlisted"}))
    loaded = settings.load(p)
    assert loaded["privacy"] == "unlisted"
    assert loaded["category"] == "20"
    assert loaded["notify_mode"] == "toast"


def test_load_survives_corrupt_json(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{ not json")
    assert settings.load(p) == settings.DEFAULTS


def test_load_ignores_unknown_keys(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"privacy": "public", "bogus": 1}))
    assert "bogus" not in settings.load(p)


def test_save_then_load_roundtrips(tmp_path):
    p = tmp_path / "s.json"
    settings.save({"privacy": "public", "category": "22", "notify_mode": "popup"}, p)
    assert settings.load(p)["privacy"] == "public"
    assert settings.load(p)["notify_mode"] == "popup"
    assert settings.load(p)["category"] == "22"


def test_save_creates_parent_directory(tmp_path):
    p = tmp_path / "deep" / "s.json"
    settings.save(settings.DEFAULTS, p)
    assert p.exists()


@pytest.mark.parametrize("bad", ["", "sideways", None])
def test_load_rejects_invalid_privacy(tmp_path, bad):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"privacy": bad}))
    assert settings.load(p)["privacy"] == "unlisted"


@pytest.mark.parametrize("raw", ["[]", "42"])
def test_load_rejects_valid_json_of_the_wrong_shape(tmp_path, raw):
    """Valid JSON that isn't an object (a list, a bare number) must fall
    back to defaults rather than crashing on the `key in raw` checks."""
    p = tmp_path / "s.json"
    p.write_text(raw)
    assert settings.load(p) == settings.DEFAULTS


def test_load_rejects_category_supplied_as_an_int(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"category": 22}))
    assert settings.load(p)["category"] == settings.DEFAULTS["category"]


def test_load_rejects_recording_dir_supplied_as_a_non_string(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"recording_dir": 123}))
    assert settings.load(p)["recording_dir"] is None


def test_update_holds_the_save_lock_across_the_read(tmp_path):
    """The whole point: reading inside the lock is what stops another
    writer completing between our read and our save and being reverted."""
    path = tmp_path / "settings.json"
    seen = []

    def read():
        seen.append(settings._SAVE_LOCK.locked())
        return settings._fresh_defaults()

    settings.update(read, lambda doc: doc.__setitem__("privacy", "public"),
                    path=path)
    assert seen == [True]
    assert settings.load(path)["privacy"] == "public"


def test_update_writes_what_the_mutator_changed(tmp_path):
    path = tmp_path / "settings.json"
    settings.update(settings._fresh_defaults,
                    lambda doc: doc["preview"].__setitem__("enabled", True),
                    path=path)
    assert settings.load(path)["preview"]["enabled"] is True


def test_update_releases_the_lock_when_the_mutator_raises(tmp_path):
    """A mutator that throws must not wedge every other writer forever."""
    path = tmp_path / "settings.json"

    def boom(doc):
        raise ValueError("nope")

    with pytest.raises(ValueError):
        settings.update(settings._fresh_defaults, boom, path=path)
    assert not settings._SAVE_LOCK.locked()
