import configparser
import os
from pathlib import Path
from unittest.mock import patch

from wingman import obsconfig


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
    _profile(
        tmp_path,
        "Both",
        "[SimpleOutput]\nFilePath=C:/simple\n[AdvOut]\nRecFilePath=C:/adv\n",
    )
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

    # See tests/test_library.py's stat_with_race: on CPython 3.13 pathlib
    # passes follow_symlinks= into stat(), so the fake must accept and
    # forward it or it raises TypeError from is_dir()/exists().
    def stat_with_race(self, *args, **kwargs):
        if "Vanish" in str(self):
            raise FileNotFoundError("File vanished during stat")
        return original_stat(self, *args, **kwargs)

    with patch.object(Path, "stat", stat_with_race):
        # Should skip the vanished profile and find the good one
        assert obsconfig.find_recording_dir(tmp_path) == Path("C:/good")


def test_profiles_root_returns_path_when_present(tmp_path):
    root = tmp_path / "obs-studio" / "basic" / "profiles"
    root.mkdir(parents=True)
    assert obsconfig.profiles_root(tmp_path) == root


def test_profiles_root_returns_none_when_not_a_directory(tmp_path):
    assert obsconfig.profiles_root(tmp_path / "nope") is None


def test_profiles_root_uses_appdata_env_when_set(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    root = tmp_path / "obs-studio" / "basic" / "profiles"
    root.mkdir(parents=True)
    assert obsconfig.profiles_root() == root


def test_profiles_root_returns_none_when_appdata_unset(monkeypatch):
    monkeypatch.delenv("APPDATA", raising=False)
    assert obsconfig.profiles_root() is None


def test_read_path_returns_none_on_os_error(monkeypatch, tmp_path):
    """configparser.read() silently swallows per-file OSErrors internally,
    so this defensive branch can't be triggered through the real filesystem;
    exercise it directly by making read() itself raise."""

    def _raise(self, *a, **kw):
        raise OSError("simulated read failure")

    monkeypatch.setattr(configparser.ConfigParser, "read", _raise)
    assert obsconfig._read_path(tmp_path / "basic.ini") is None


def test_read_path_returns_none_on_bad_encoding(tmp_path):
    ini = tmp_path / "basic.ini"
    ini.write_bytes(b"\xff\xfe\x00\x01invalid")
    assert obsconfig._read_path(ini) is None


def test_glob_match_that_is_a_directory_is_skipped(tmp_path):
    """A stray directory named basic.ini must not be opened as a file."""
    d = tmp_path / "obs-studio" / "basic" / "profiles" / "Weird" / "basic.ini"
    d.mkdir(parents=True)
    assert obsconfig.find_recording_dir(tmp_path) is None


def test_returns_none_when_adv_out_present_but_key_missing(tmp_path):
    _profile(tmp_path, "Adv", "[AdvOut]\nSomeOtherKey=x\n")
    assert obsconfig.find_recording_dir(tmp_path) is None


def _global_ini(root: Path, profile_dir: str, extra: str = "") -> Path:
    d = root / "obs-studio"
    d.mkdir(parents=True, exist_ok=True)
    ini = d / "global.ini"
    ini.write_text(
        f"[Basic]\nProfileDir={profile_dir}\nProfile=Display Name\n{extra}",
        encoding="utf-8",
    )
    return ini


def test_active_profile_from_global_ini_wins_over_newer_profile(tmp_path):
    """global.ini names the active profile; that must win even when a
    different profile's basic.ini was touched more recently."""
    _profile(tmp_path, "Active", "[SimpleOutput]\nFilePath=C:/active\n", mtime=1000)
    _profile(tmp_path, "OtherNewer", "[SimpleOutput]\nFilePath=C:/other\n", mtime=9000)
    _global_ini(tmp_path, "Active")
    assert obsconfig.find_recording_dir(tmp_path) == Path("C:/active")


def test_global_ini_naming_nonexistent_profile_falls_back(tmp_path):
    _profile(tmp_path, "Real", "[SimpleOutput]\nFilePath=C:/real\n", mtime=1000)
    _global_ini(tmp_path, "DoesNotExist")
    assert obsconfig.find_recording_dir(tmp_path) == Path("C:/real")


def test_missing_global_ini_falls_back_to_mtime_scan(tmp_path):
    _profile(tmp_path, "Old", "[SimpleOutput]\nFilePath=C:/old\n", mtime=1000)
    _profile(tmp_path, "New", "[SimpleOutput]\nFilePath=C:/new\n", mtime=2000)
    # No global.ini written at all.
    assert obsconfig.find_recording_dir(tmp_path) == Path("C:/new")


def test_malformed_global_ini_falls_back_to_mtime_scan(tmp_path):
    _profile(tmp_path, "Old", "[SimpleOutput]\nFilePath=C:/old\n", mtime=1000)
    _profile(tmp_path, "New", "[SimpleOutput]\nFilePath=C:/new\n", mtime=2000)
    d = tmp_path / "obs-studio"
    d.mkdir(parents=True, exist_ok=True)
    (d / "global.ini").write_text("!!!not an ini###\n", encoding="utf-8")
    assert obsconfig.find_recording_dir(tmp_path) == Path("C:/new")


def test_active_profile_named_but_has_no_usable_path_falls_back(tmp_path):
    _profile(tmp_path, "ActiveEmpty", "[SimpleOutput]\nRecFormat=mkv\n", mtime=1000)
    _profile(tmp_path, "Fallback", "[SimpleOutput]\nFilePath=C:/fallback\n", mtime=2000)
    _global_ini(tmp_path, "ActiveEmpty")
    assert obsconfig.find_recording_dir(tmp_path) == Path("C:/fallback")


def test_active_profile_dir_name_returns_none_without_global_ini(tmp_path):
    assert obsconfig._active_profile_dir_name(tmp_path) is None


def test_active_profile_dir_name_returns_none_without_profiledir_key(tmp_path):
    d = tmp_path / "obs-studio"
    d.mkdir(parents=True)
    (d / "global.ini").write_text("[Basic]\nProfile=Display Name\n", encoding="utf-8")
    assert obsconfig._active_profile_dir_name(tmp_path) is None


def test_advanced_mode_prefers_adv_out_path(tmp_path):
    """The user's actual bug: Mode=Advanced with both sections populated
    must return AdvOut's path, not the stale SimpleOutput default. Fails
    against the fixed-priority-order logic, which always returned
    SimpleOutput's C:/Videos here instead of the real D:/Videos."""
    _profile(
        tmp_path,
        "OnlyProfile",
        "[Output]\nMode=Advanced\n"
        "[SimpleOutput]\nFilePath=C:/Videos\n"
        "[AdvOut]\nRecFilePath=D:/Videos\n",
    )
    assert obsconfig.find_recording_dir(tmp_path) == Path("D:/Videos")


def test_simple_mode_prefers_simple_output_path(tmp_path):
    _profile(
        tmp_path,
        "OnlyProfile",
        "[Output]\nMode=Simple\n"
        "[SimpleOutput]\nFilePath=C:/Videos\n"
        "[AdvOut]\nRecFilePath=D:/Videos\n",
    )
    assert obsconfig.find_recording_dir(tmp_path) == Path("C:/Videos")


def test_missing_output_section_defaults_to_simple(tmp_path):
    _profile(
        tmp_path,
        "OnlyProfile",
        "[SimpleOutput]\nFilePath=C:/Videos\n[AdvOut]\nRecFilePath=D:/Videos\n",
    )
    assert obsconfig.find_recording_dir(tmp_path) == Path("C:/Videos")


def test_unrecognised_mode_value_defaults_to_simple(tmp_path):
    _profile(
        tmp_path,
        "OnlyProfile",
        "[Output]\nMode=Streaming\n"
        "[SimpleOutput]\nFilePath=C:/Videos\n"
        "[AdvOut]\nRecFilePath=D:/Videos\n",
    )
    assert obsconfig.find_recording_dir(tmp_path) == Path("C:/Videos")


def test_advanced_mode_falls_back_to_simple_when_adv_out_missing(tmp_path):
    _profile(
        tmp_path,
        "OnlyProfile",
        "[Output]\nMode=Advanced\n[SimpleOutput]\nFilePath=C:/Videos\n",
    )
    assert obsconfig.find_recording_dir(tmp_path) == Path("C:/Videos")


def test_simple_mode_falls_back_to_advanced_when_simple_output_empty(tmp_path):
    _profile(
        tmp_path,
        "OnlyProfile",
        "[Output]\nMode=Simple\n"
        "[SimpleOutput]\nFilePath=\n"
        "[AdvOut]\nRecFilePath=D:/Videos\n",
    )
    assert obsconfig.find_recording_dir(tmp_path) == Path("D:/Videos")


def test_advanced_mode_is_case_insensitive(tmp_path):
    _profile(
        tmp_path,
        "OnlyProfile",
        "[Output]\nMode=ADVANCED\n"
        "[SimpleOutput]\nFilePath=C:/Videos\n"
        "[AdvOut]\nRecFilePath=D:/Videos\n",
    )
    assert obsconfig.find_recording_dir(tmp_path) == Path("D:/Videos")
