"""The eve_bookmarks values drive a file that registers keyboard hooks, so
load() has to be defensive about them in a way a title string never needed.
"""
import json
import pytest
from obs_youtube_uploader import bookmarks, settings


def test_defaults_carry_every_bind(tmp_path):
    data = settings.load(tmp_path / "missing.json")
    assert data["eve_bookmarks"]["enabled"] is False
    assert data["eve_bookmarks"]["keybinds"] == bookmarks.DEFAULT_BINDS
    assert data["eve_bookmarks"]["windows"] == {}


def test_nested_defaults_are_not_shared_with_the_module_global(tmp_path):
    """load() starts from dict(DEFAULTS) (settings.py:260-262), a SHALLOW copy.
    Fine while every default is a scalar; with a nested dict the returned
    settings would alias DEFAULTS and the first in-place edit would corrupt
    it for the rest of the process -- silently, and for every later load().
    """
    first = settings.load(tmp_path / "missing.json")
    first["eve_bookmarks"]["keybinds"]["FinH"] = "^h"
    first["eve_bookmarks"]["windows"]["EVE - Pilot"] = True

    second = settings.load(tmp_path / "missing.json")
    assert second["eve_bookmarks"]["keybinds"]["FinH"] == ""
    assert second["eve_bookmarks"]["windows"] == {}
    assert bookmarks.DEFAULT_BINDS["FinH"] == ""


def test_roundtrip(tmp_path):
    path = tmp_path / "s.json"
    data = settings.load(path)
    data["eve_bookmarks"]["enabled"] = True
    data["eve_bookmarks"]["keybinds"]["FinH"] = "^h"
    data["eve_bookmarks"]["windows"]["EVE - Pilot"] = True
    settings.save(data, path)

    loaded = settings.load(path)
    assert loaded["eve_bookmarks"]["enabled"] is True
    assert loaded["eve_bookmarks"]["keybinds"]["FinH"] == "^h"
    assert loaded["eve_bookmarks"]["windows"] == {"EVE - Pilot": True}


@pytest.mark.parametrize("bad", [7, "yes", None, [], {"a": 1}])
def test_bad_enabled_falls_back_to_off(tmp_path, bad):
    """Failing closed matters here: the wrong answer starts a keyboard
    hook the user did not ask for."""
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"eve_bookmarks": {"enabled": bad}}))
    assert settings.load(path)["eve_bookmarks"]["enabled"] is False


def test_unknown_bind_ids_are_dropped_and_missing_ones_defaulted(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"eve_bookmarks": {
        "keybinds": {"FinH": "^h", "Nonsense": "^x"}}}))
    binds = settings.load(path)["eve_bookmarks"]["keybinds"]
    assert binds["FinH"] == "^h"
    assert "Nonsense" not in binds
    assert binds["ConvertScout"] == "^+s"
    assert set(binds) == set(bookmarks.BIND_IDS)


def test_a_settings_file_from_before_the_naming_removal_is_cleaned_up(tmp_path):
    """The upgrade path. An existing install's settings.json still carries
    the three naming keys and the two clipboard binds; both are dropped
    rather than carried forward, so nothing keeps steering behaviour that
    has no control left."""
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"eve_bookmarks": {
        "keybinds": {"Copy": "^j", "Paste": "^k", "FinH": "^h"},
        "home_zero": True,
        "preface_return": False,
        "return_preface": "@"}}))
    section = settings.load(path)["eve_bookmarks"]
    assert section["keybinds"]["FinH"] == "^h"
    assert "Copy" not in section["keybinds"]
    assert "Paste" not in section["keybinds"]
    for key in ("home_zero", "preface_return", "return_preface"):
        assert key not in section
    # And the INI the engine actually reads is unmoved by any of it.
    text = bookmarks.generate_ini(section)
    assert "HomeZeroIs0=0" in text
    assert "PrefaceReturn=0" in text
    assert "ReturnPreface=!\r\n" in text


@pytest.mark.parametrize("bad", [7, None, [], {"x": 1}])
def test_non_string_bind_value_falls_back(tmp_path, bad):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"eve_bookmarks": {"keybinds": {"FinH": bad}}}))
    assert settings.load(path)["eve_bookmarks"]["keybinds"]["FinH"] == ""


def test_window_map_coerces_to_bool_and_drops_non_string_keys(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"eve_bookmarks": {
        "windows": {"EVE - Pilot": 1, "EVE - Alt": 0}}}))
    assert settings.load(path)["eve_bookmarks"]["windows"] == {
        "EVE - Pilot": True, "EVE - Alt": False}


@pytest.mark.parametrize("bad", [7, "x", None, []])
def test_whole_section_of_wrong_type_falls_back(tmp_path, bad):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"eve_bookmarks": bad}))
    section = settings.load(path)["eve_bookmarks"]
    assert section["enabled"] is False
    assert section["keybinds"] == bookmarks.DEFAULT_BINDS
