"""EVE Settings section validation. Mirrors test_settings_preview.py."""

import json

import pytest

from wingman import paths, settings


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
    assert (
        settings.validated_eve_settings({"auto_keep": given})["auto_keep"] == expected
    )


def test_booleans_are_not_accepted_as_auto_keep():
    """bool is an int in Python; True would silently become a keep depth."""
    out = settings.validated_eve_settings({"auto_keep": True})
    assert out["auto_keep"] == settings._eve_settings_defaults()["auto_keep"]


def test_account_names_are_trimmed_bounded_and_casefold_unique():
    out = settings.validated_eve_settings(
        {
            "account_names": {
                "10": "  LoginName  ",
                "11": "loginname",
                "12": "x" * 100,
                "bad": "ignored",
            }
        }
    )
    assert out["account_names"] == {"10": "LoginName", "12": "x" * 80}


def test_links_require_a_name_and_keep_first_three_valid_unclaimed_ids():
    out = settings.validated_eve_settings(
        {
            "account_names": {"10": "First", "11": "Second"},
            "account_characters": {
                "10": ["20", "20", "bad", "21", "22", "23"],
                "11": ["20", "24", "25", "26"],
                "12": ["27"],
            },
        }
    )
    assert out["account_characters"] == {
        "10": ["20", "21", "22"],
        "11": ["24", "25", "26"],
    }


def test_unreleased_alias_key_is_dropped():
    out = settings.validated_eve_settings(
        {"account_aliases": {"10": "Old"}, "account_characters": {"10": ["20"]}}
    )
    assert out["account_names"] == {}
    assert out["account_characters"] == {}


def test_named_account_without_links_is_retained():
    out = settings.validated_eve_settings({"account_names": {"10": "Solo"}})
    assert out["account_names"] == {"10": "Solo"}
    assert out["account_characters"] == {}


def test_account_identity_maps_are_fresh_defaults():
    first = settings._eve_settings_defaults()
    first["account_names"]["10"] = "changed"
    first["account_characters"]["10"] = ["20"]
    assert settings._eve_settings_defaults()["account_names"] == {}
    assert settings._eve_settings_defaults()["account_characters"] == {}


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

    live = settings.update_section(data, "eve_settings", {"root": "C:\\EVE"}, target)

    assert live is data
    assert data["eve_settings"]["root"] == "C:\\EVE"
    assert settings.load(target)["eve_settings"]["root"] == "C:\\EVE"


def test_a_corrupt_section_does_not_take_the_file_down(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text(json.dumps({"eve_settings": "garbage", "privacy": "public"}))
    loaded = settings.load(target)
    assert loaded["eve_settings"] == settings._eve_settings_defaults()
    assert loaded["privacy"] == "public"


def test_backup_dir_sits_beside_the_other_state(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert paths.eve_settings_backup_dir().parent == paths.state_dir()


def test_the_public_surface_returns_the_same_defaults(tmp_path):
    """ui/api.py's _eve_section() builds the section through
    validated_eve_settings rather than reaching across the module boundary
    for the private _eve_settings_defaults. This pins the two together, so
    the public entry point cannot quietly stop being equivalent."""
    assert settings.validated_eve_settings({}) == settings._eve_settings_defaults()
    first = settings.validated_eve_settings({})
    first["root"] = "/tmp/mutated"
    assert settings.validated_eve_settings({})["root"] is None, (
        "a fresh dict per call, never the module global"
    )
