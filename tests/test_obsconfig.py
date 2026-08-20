import os
from pathlib import Path
from unittest.mock import patch

from obs_youtube_uploader import obsconfig


def _profile(root: Path, name: str, body: str, mtime: float | None = None) -> Path:
    d = root / "obs-studio" / "basic" / "profiles" / name
    d.mkdir(parents=True)
    ini = d / "basic.ini"
    ini.write_text(body, encoding="utf-8")
    if mtime is not None:
        os.utime(ini, (mtime, mtime))
    return ini


def test_finds_simple_output_path(tmp_path):
    _profile(tmp_path, "Untitled", "[SimpleOutput]\nFilePath=C:/rec\n")
    assert obsconfig.find_recording_dir(tmp_path) == Path("C:/rec")


def test_finds_advanced_output_path(tmp_path):
    _profile(tmp_path, "Adv", "[AdvOut]\nRecFilePath=C:/adv\n")
    assert obsconfig.find_recording_dir(tmp_path) == Path("C:/adv")


def test_simple_output_wins_when_both_present(tmp_path):
    _profile(tmp_path, "Both", "[SimpleOutput]\nFilePath=C:/simple\n[AdvOut]\nRecFilePath=C:/adv\n")
    assert obsconfig.find_recording_dir(tmp_path) == Path("C:/simple")


def test_picks_most_recently_modified_profile(tmp_path):
    _profile(tmp_path, "Old", "[SimpleOutput]\nFilePath=C:/old\n", mtime=1000)
    _profile(tmp_path, "New", "[SimpleOutput]\nFilePath=C:/new\n", mtime=2000)
    assert obsconfig.find_recording_dir(tmp_path) == Path("C:/new")


def test_returns_none_when_obs_not_installed(tmp_path):
    assert obsconfig.find_recording_dir(tmp_path) is None


def test_returns_none_when_no_profiles_exist(tmp_path):
    (tmp_path / "obs-studio" / "basic" / "profiles").mkdir(parents=True)
    assert obsconfig.find_recording_dir(tmp_path) is None


def test_returns_none_when_path_key_missing(tmp_path):
    _profile(tmp_path, "Empty", "[SimpleOutput]\nRecFormat=mkv\n")
    assert obsconfig.find_recording_dir(tmp_path) is None


def test_survives_malformed_ini(tmp_path):
    _profile(tmp_path, "Bad", "this is not an ini file\n===\n")
    assert obsconfig.find_recording_dir(tmp_path) is None


def test_skips_malformed_profile_and_uses_valid_older_one(tmp_path):
    _profile(tmp_path, "Good", "[SimpleOutput]\nFilePath=C:/good\n", mtime=1000)
    _profile(tmp_path, "Bad", "!!!broken\n", mtime=2000)
    assert obsconfig.find_recording_dir(tmp_path) == Path("C:/good")


def test_ignores_blank_path_value(tmp_path):
    _profile(tmp_path, "Blank", "[SimpleOutput]\nFilePath=\n")
    assert obsconfig.find_recording_dir(tmp_path) is None


def test_handles_utf8_bom_in_ini_file(tmp_path):
    d = tmp_path / "obs-studio" / "basic" / "profiles" / "WithBOM"
    d.mkdir(parents=True)
    ini = d / "basic.ini"
    # Write with UTF-8 BOM marker followed by normal INI content
    ini.write_bytes(b"\xef\xbb\xbf[SimpleOutput]\nFilePath=C:/rec\n")
    assert obsconfig.find_recording_dir(tmp_path) == Path("C:/rec")


def test_survives_stat_race_when_file_vanishes(tmp_path):
    _profile(tmp_path, "Good", "[SimpleOutput]\nFilePath=C:/good\n")
    _profile(tmp_path, "Vanish", "[SimpleOutput]\nFilePath=C:/vanish\n")

    # Monkeypatch Path.stat to raise FileNotFoundError for the "Vanish" profile
    original_stat = Path.stat

    def stat_with_race(self):
        if "Vanish" in str(self):
            raise FileNotFoundError("File vanished during stat")
        return original_stat(self)

    with patch.object(Path, "stat", stat_with_race):
        # Should skip the vanished profile and find the good one
        assert obsconfig.find_recording_dir(tmp_path) == Path("C:/good")

