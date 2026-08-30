import sys
from pathlib import Path

from wingman import paths


def test_state_dir_uses_localappdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert paths.state_dir() == tmp_path / "FlyGD Wingman"


def test_state_dir_falls_back_when_localappdata_absent(monkeypatch, tmp_path):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert paths.state_dir() == tmp_path / ".local" / "share" / "FlyGD Wingman"


def test_named_files_live_under_state_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    root = tmp_path / "FlyGD Wingman"
    assert paths.settings_file() == root / "settings.json"
    assert paths.token_file() == root / "token.json"
    assert paths.seen_file() == root / "seen.json"
    assert paths.durations_file() == root / "durations.json"
    assert paths.links_file() == root / "links.json"
    assert paths.log_dir() == root / "logs"
    assert paths.tmp_dir() == root / "tmp"


def test_migration_renames_the_legacy_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    legacy = tmp_path / "OBSYouTubeUploader"
    legacy.mkdir()
    (legacy / "token.json").write_text("signed-in")

    paths.migrate_state_dir()

    assert not legacy.exists()
    assert (tmp_path / "FlyGD Wingman" / "token.json").read_text() == "signed-in"


def test_migration_is_a_no_op_when_nothing_to_migrate(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    paths.migrate_state_dir()
    assert not (tmp_path / "FlyGD Wingman").exists(), (
        "migration must not create the directory; ensure_dirs() owns that"
    )


def test_migration_leaves_an_existing_new_directory_alone(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    legacy = tmp_path / "OBSYouTubeUploader"
    legacy.mkdir()
    (legacy / "token.json").write_text("stale")
    current = tmp_path / "FlyGD Wingman"
    current.mkdir()
    (current / "token.json").write_text("current")

    paths.migrate_state_dir()

    assert (current / "token.json").read_text() == "current"
    assert legacy.exists(), "an already-migrated install must not be clobbered"


def test_a_locked_legacy_directory_falls_back_instead_of_losing_state(
    monkeypatch, tmp_path
):
    """Windows blocks renaming a directory that is some process's cwd.

    An orphaned AutoHotkey engine from the previous session holds exactly
    that lock, and recover_orphan() runs far too late to help. Falling back
    keeps the user's data reachable; retrying next launch costs nothing.
    """
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    legacy = tmp_path / "OBSYouTubeUploader"
    legacy.mkdir()
    (legacy / "token.json").write_text("signed-in")

    def refuse(self, target):
        raise OSError(32, "The process cannot access the file")

    monkeypatch.setattr(Path, "rename", refuse)

    paths.migrate_state_dir()

    assert paths.state_dir() == legacy
    assert paths.token_file().read_text() == "signed-in"


def test_the_legacy_flag_does_not_leak_between_tests(monkeypatch, tmp_path):
    """Guards the conftest reset. If this fails, an unrelated test that
    triggered the fallback has silently redirected every later test."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert paths.state_dir() == tmp_path / "FlyGD Wingman"


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
    from wingman import paths as paths_mod

    binaries = tmp_path / "bin"
    binaries.mkdir()
    (binaries / "ffmpeg.exe").write_bytes(b"")
    monkeypatch.setattr(paths_mod, "bundle_dir", lambda: tmp_path)

    assert paths_mod.resolve_binary("ffmpeg") == str(binaries / "ffmpeg.exe")


def test_resolve_binary_finds_the_source_checkout_copy(tmp_path, monkeypatch):
    """packaging/fetch_ffmpeg.py writes to packaging/bin, not <repo>/bin.
    Without this lookup, running from source silently falls back to PATH
    and ignores the ffmpeg the build script just fetched."""
    from wingman import paths as paths_mod

    packaging_bin = tmp_path / "packaging" / "bin"
    packaging_bin.mkdir(parents=True)
    (packaging_bin / "ffprobe.exe").write_bytes(b"")
    monkeypatch.setattr(paths_mod, "bundle_dir", lambda: tmp_path)
    monkeypatch.delattr(paths_mod.sys, "_MEIPASS", raising=False)

    assert paths_mod.resolve_binary("ffprobe") == str(packaging_bin / "ffprobe.exe")


def test_resolve_binary_falls_back_to_path(tmp_path, monkeypatch):
    from wingman import paths as paths_mod

    monkeypatch.setattr(paths_mod, "bundle_dir", lambda: tmp_path)
    monkeypatch.setattr(paths_mod.shutil, "which", lambda name: "/usr/bin/" + name)

    assert paths_mod.resolve_binary("ffmpeg") == "/usr/bin/ffmpeg"


def _codec_name():
    return (
        "wingman-settings-codec.exe"
        if sys.platform == "win32"
        else "wingman-settings-codec"
    )


def test_codec_exe_finds_the_frozen_copy(tmp_path, monkeypatch):
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / _codec_name()).write_bytes(b"")
    monkeypatch.setattr(paths, "bundle_dir", lambda: tmp_path)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert paths.codec_exe() == str(tmp_path / "bin" / _codec_name())


def test_codec_exe_finds_the_source_checkout_copy(tmp_path, monkeypatch):
    (tmp_path / "packaging" / "bin").mkdir(parents=True)
    (tmp_path / "packaging" / "bin" / _codec_name()).write_bytes(b"")
    monkeypatch.setattr(paths, "bundle_dir", lambda: tmp_path)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    assert paths.codec_exe() == str(tmp_path / "packaging" / "bin" / _codec_name())


def test_codec_exe_never_falls_back_to_path(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "bundle_dir", lambda: tmp_path)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(paths.shutil, "which", lambda name: "/usr/bin/" + name)
    assert paths.codec_exe() is None
