import json
import pytest
from obs_youtube_uploader import settings


def test_defaults_are_the_documented_values():
    assert settings.DEFAULTS == {
        "privacy": "private",
        "category": "20",
        "notify_mode": "toast",
        "recording_dir": None,
    }


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
    assert settings.load(p)["privacy"] == "private"


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
