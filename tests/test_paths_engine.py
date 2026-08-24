"""resolve_binary() falls back to PATH, which is right for ffmpeg and wrong
here: a user with AutoHotkey v2 installed would have their v2 interpreter
handed a v1 script and fail with parse errors that look like our bug."""
from obs_youtube_uploader import paths


def test_state_files_live_together(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "state_dir", lambda: tmp_path)
    assert paths.engine_ini_file() == tmp_path / "eve_bookmark_helper.ini"
    assert paths.engine_status_file() == tmp_path / "eve_status.json"
    assert paths.engine_pid_file() == tmp_path / "eve_engine.pid"


def test_engine_exe_never_falls_back_to_path(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "bundle_dir", lambda: tmp_path)
    monkeypatch.setattr(paths.shutil, "which",
                        lambda _n: "C:/Program Files/AutoHotkey/v2/AutoHotkey.exe")
    assert paths.engine_exe() is None


def test_engine_exe_finds_the_bundled_binary(monkeypatch, tmp_path):
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "AutoHotkeyU64.exe").write_text("")
    monkeypatch.setattr(paths, "bundle_dir", lambda: tmp_path)
    assert paths.engine_exe() == str(tmp_path / "bin" / "AutoHotkeyU64.exe")


def test_engine_exe_finds_the_source_checkout_copy(monkeypatch, tmp_path):
    """packaging/fetch_autohotkey.py writes into packaging/bin, not <repo>/bin,
    exactly as fetch_ffmpeg.py does (paths.py:63-79)."""
    target = tmp_path / "packaging" / "bin"
    target.mkdir(parents=True)
    (target / "AutoHotkeyU64.exe").write_text("")
    monkeypatch.setattr(paths, "bundle_dir", lambda: tmp_path)
    monkeypatch.delattr(paths.sys, "_MEIPASS", raising=False)
    assert paths.engine_exe() == str(target / "AutoHotkeyU64.exe")


def test_engine_script_prefers_the_frozen_location(monkeypatch, tmp_path):
    engine = tmp_path / "engine"
    engine.mkdir()
    (engine / "eve_bookmarks.ahk").write_text("")
    monkeypatch.setattr(paths, "bundle_dir", lambda: tmp_path)
    assert paths.engine_script() == engine / "eve_bookmarks.ahk"


def test_engine_script_returns_none_when_absent(monkeypatch, tmp_path):
    """Callers treat a missing engine as "reinstall", the same policy
    resolve_binary() and icon_file() use."""
    monkeypatch.setattr(paths, "bundle_dir", lambda: tmp_path)
    monkeypatch.setattr(paths, "_package_dir", lambda: tmp_path / "nope")
    assert paths.engine_script() is None
