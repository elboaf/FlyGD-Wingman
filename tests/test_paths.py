from pathlib import Path
from obs_youtube_uploader import paths


def test_state_dir_uses_localappdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert paths.state_dir() == tmp_path / "OBSYouTubeUploader"


def test_state_dir_falls_back_when_localappdata_absent(monkeypatch, tmp_path):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert paths.state_dir() == tmp_path / ".local" / "share" / "OBSYouTubeUploader"


def test_named_files_live_under_state_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    root = tmp_path / "OBSYouTubeUploader"
    assert paths.settings_file() == root / "settings.json"
    assert paths.token_file() == root / "token.json"
    assert paths.seen_file() == root / "seen.json"
    assert paths.durations_file() == root / "durations.json"
    assert paths.log_dir() == root / "logs"
    assert paths.tmp_dir() == root / "tmp"


def test_ensure_dirs_creates_everything(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    paths.ensure_dirs()
    assert paths.state_dir().is_dir()
    assert paths.log_dir().is_dir()
    assert paths.tmp_dir().is_dir()


def test_ensure_dirs_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    paths.ensure_dirs()
    paths.ensure_dirs()
    assert paths.state_dir().is_dir()


def test_bundle_dir_prefers_meipass(monkeypatch, tmp_path):
    monkeypatch.setattr(paths.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert paths.bundle_dir() == tmp_path
