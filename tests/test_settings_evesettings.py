"""EVE Settings section validation. Mirrors test_settings_preview.py."""
import json

import pytest

from obs_youtube_uploader import paths, settings


@pytest.mark.parametrize("raw", [None, [], "nope", 3])
def test_whole_section_of_wrong_type_falls_back(raw):
    assert settings.validated_eve_settings(raw) == settings._eve_settings_defaults()


def test_unknown_keys_are_dropped():
    out = settings.validated_eve_settings({"root": "C:\\EVE", "nonsense": 1})
    assert "nonsense" not in out and out["root"] == "C:\\EVE"


def test_defaults_are_a_fresh_dict_every_call():
    """dict(DEFAULTS) is shallow; handing callers the module global would
    let one mutation leak into every later load."""
    first = settings._eve_settings_defaults()
    first["root"] = "mutated"
    assert settings._eve_settings_defaults()["root"] is None


def test_blank_paths_fall_back_to_none():
    out = settings.validated_eve_settings({"root": "   ", "server": ""})
    assert out["root"] is None and out["server"] is None


def test_non_string_paths_fall_back_to_none():
    out = settings.validated_eve_settings({"root": 7, "profile": ["x"]})
    assert out["root"] is None and out["profile"] is None


@pytest.mark.parametrize("given,expected", [(0, 1), (500, 100), (25, 25)])
def test_auto_keep_is_clamped_not_rejected(given, expected):
    assert settings.validated_eve_settings({"auto_keep": given})["auto_keep"] == expected


def test_booleans_are_not_accepted_as_auto_keep():
    """bool is an int in Python; True would silently become a keep depth."""
    out = settings.validated_eve_settings({"auto_keep": True})
    assert out["auto_keep"] == settings._eve_settings_defaults()["auto_keep"]


def test_section_survives_a_load_save_round_trip(tmp_path):
    target = tmp_path / "settings.json"
    data = settings.load(target)
    data["eve_settings"]["root"] = "C:\\EVE"
    settings.save(data, target)
    assert settings.load(target)["eve_settings"]["root"] == "C:\\EVE"


def test_update_section_does_not_drop_another_writers_key(tmp_path):
    """_SAVE_LOCK covers the write, not the surrounding read-modify-write.
    A writer that saves a snapshot it built earlier silently reverts keys
    another writer set in between."""
    target = tmp_path / "settings.json"
    data = settings.load(target)

    settings.update_section(data, "eve_settings", {"root": "C:\\EVE"}, target)
    settings.update_section(data, "eve_settings", {"server": "tq"}, target)

    live = settings.load(target)
    assert live["eve_settings"]["root"] == "C:\\EVE"
    assert live["eve_settings"]["server"] == "tq"


def test_update_section_mutates_the_live_document_in_place(tmp_path):
    """Identity is the point: update_section takes the caller's live dict
    and returns that same object, so nobody has to rebind AppState.settings
    afterwards. The rebind it replaced ran outside the lock and could
    orphan a concurrent writer's dict -- see settings.update_section."""
    target = tmp_path / "settings.json"
    data = settings.load(target)

    live = settings.update_section(data, "eve_settings",
                                   {"root": "C:\\EVE"}, target)

    assert live is data
    assert data["eve_settings"]["root"] == "C:\\EVE"
    assert settings.load(target)["eve_settings"]["root"] == "C:\\EVE"


def test_a_corrupt_section_does_not_take_the_file_down(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"eve_settings": "garbage",
                                  "privacy": "public"}))
    loaded = settings.load(target)
    assert loaded["eve_settings"] == settings._eve_settings_defaults()
    assert loaded["privacy"] == "public"


def test_backup_dir_sits_beside_the_other_state(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert paths.eve_settings_backup_dir().parent == paths.state_dir()
