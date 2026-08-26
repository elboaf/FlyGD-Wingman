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
    assert paths.links_file() == root / "links.json"
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


def test_resolve_binary_prefers_the_bundled_copy(tmp_path, monkeypatch):
    """The frozen layout: bundle_dir()/bin/<name>.exe."""
    from obs_youtube_uploader import paths as paths_mod

    binaries = tmp_path / "bin"
    binaries.mkdir()
    (binaries / "ffmpeg.exe").write_bytes(b"")
    monkeypatch.setattr(paths_mod, "bundle_dir", lambda: tmp_path)

    assert paths_mod.resolve_binary("ffmpeg") == str(binaries / "ffmpeg.exe")


def test_resolve_binary_finds_the_source_checkout_copy(tmp_path, monkeypatch):
    """packaging/fetch_ffmpeg.py writes to packaging/bin, not <repo>/bin.
    Without this lookup, running from source silently falls back to PATH
    and ignores the ffmpeg the build script just fetched."""
    from obs_youtube_uploader import paths as paths_mod

    packaging_bin = tmp_path / "packaging" / "bin"
    packaging_bin.mkdir(parents=True)
    (packaging_bin / "ffprobe.exe").write_bytes(b"")
    monkeypatch.setattr(paths_mod, "bundle_dir", lambda: tmp_path)
    monkeypatch.delattr(paths_mod.sys, "_MEIPASS", raising=False)

    assert paths_mod.resolve_binary("ffprobe") == str(packaging_bin / "ffprobe.exe")


def test_resolve_binary_falls_back_to_path(tmp_path, monkeypatch):
    from obs_youtube_uploader import paths as paths_mod

    monkeypatch.setattr(paths_mod, "bundle_dir", lambda: tmp_path)
    monkeypatch.setattr(paths_mod.shutil, "which", lambda name: "/usr/bin/" + name)

    assert paths_mod.resolve_binary("ffmpeg") == "/usr/bin/ffmpeg"
