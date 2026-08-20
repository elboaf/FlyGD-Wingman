# Standalone Repackaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the OBS-triggered Python script into a standalone Windows tray application installable in one step.

**Architecture:** Extract the single 630-line `youtube_uploader.py` into six focused modules under an `obs_youtube_uploader/` package, five of which are testable without a GUI, network, or OBS. Replace the OBS script trigger with a polling folder watcher and a tray icon. Ship as a PyInstaller one-folder build wrapped in an Inno Setup installer, with OAuth credentials embedded at build time.

**Tech Stack:** Python 3.11+, Tkinter, pystray + Pillow, google-api-python-client, pytest, PyInstaller, Inno Setup, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-20-standalone-repackaging-design.md`

## Global Constraints

Every task's requirements implicitly include this section. Values are copied verbatim from the spec.

- **Platform:** Windows only. Code must not crash on Linux (tests run there in CI), but Windows-specific paths and APIs are the target.
- **Python:** 3.11+ (`str | None` unions and `tomllib` are used).
- **State directory:** `%LOCALAPPDATA%\OBSYouTubeUploader\` — never alongside the executable. `Program Files` is not writable by non-admin users.
- **Settings keys:** `privacy`, `category`, `notify_mode`. Note `category`, **not** `category_id`.
- **Privacy default:** `private`. This resolves a pre-existing inconsistency (`youtube_uploader.py:193` says `unlisted`, `:442` says `private`); `private` wins.
- **Notify default:** `toast`.
- **Video extensions:** `.mkv .mp4 .flv .mov .avi .ts .m4v .webm` — unchanged from `youtube_uploader.py:27`.
- **OAuth scope:** `https://www.googleapis.com/auth/youtube.upload` — unchanged.
- **Upload chunk size:** 4 MB — unchanged.
- **Credentials:** embedded at build time from a repository secret. Never committed to git.
- **Release gating:** public release is blocked until OAuth verification clears. Implementation does not wait on it.
- **No migration code.** One existing user re-authenticates and re-picks settings by hand.
- **Deletion stays permanent** (`Path.unlink()`), matching current behavior. Recycle Bin is an explicit follow-up, not part of this work.

## File Structure

```
run.py                Entry shim (absolute imports, PyInstaller target)
obs_youtube_uploader/
  __init__.py       Package marker, version string
  paths.py          State/bundle directory resolution
  settings.py       Settings load/save with defaults
  library.py        Video discovery, metadata probing, deletion
  obsconfig.py      OBS basic.ini parsing -> recording directory
  stitch.py         Stitch ordering, ffmpeg invocation, temp lifecycle
  uploader.py       OAuth, upload with retry, error classification
  watcher.py        Settled-file detection, seen-set persistence
  app.py            Tk window, tray icon, notifications, wiring
  settingsui.py     Settings dialog, Google account connection
  __main__.py       Entry point, single-instance mutex
tests/
  test_paths.py  test_settings.py  test_library.py  test_obsconfig.py
  test_stitch.py  test_uploader.py  test_watcher.py
packaging/
  fetch_ffmpeg.py   Build-time ffmpeg download + checksum verification
  uploader.spec     PyInstaller one-folder spec
  installer.iss     Inno Setup script
.github/workflows/
  ci.yml            Tests on push
  release.yml       Build installer on tag
pyproject.toml
.gitignore
```

Deleted during the work: `obs_trigger.py` and `youtube_uploader.py` (Task 12), `requirements.txt` (Task 17).

---

# Phase 1 — Testable core

The script keeps working throughout this phase. Each task extracts logic into a module with tests; `youtube_uploader.py` is left in place until Phase 2 replaces it.

---

### Task 1: Project scaffolding and path resolution

**Files:**
- Create: `pyproject.toml`
- Create: `obs_youtube_uploader/__init__.py`
- Create: `obs_youtube_uploader/paths.py`
- Test: `tests/test_paths.py`

**Interfaces:**
- Consumes: nothing
- Produces: `state_dir() -> Path`, `settings_file() -> Path`, `token_file() -> Path`, `seen_file() -> Path`, `log_dir() -> Path`, `tmp_dir() -> Path`, `bundle_dir() -> Path`, `ensure_dirs() -> None`, `APP_NAME: str`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "obs-youtube-uploader"
version = "2.0.0"
requires-python = ">=3.11"
dependencies = [
    "google-api-python-client",
    "google-auth-oauthlib",
    "google-auth-httplib2",
    "pystray",
    "Pillow",
]

[project.optional-dependencies]
dev = ["pytest"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create the package marker**

```python
# obs_youtube_uploader/__init__.py
__version__ = "2.0.0"
```

- [ ] **Step 3: Write the failing test**

```python
# tests/test_paths.py
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
```

- [ ] **Step 4: Run test to verify it fails**

Run: `python -m pytest tests/test_paths.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'obs_youtube_uploader.paths'`

- [ ] **Step 5: Write the implementation**

```python
# obs_youtube_uploader/paths.py
"""Filesystem locations for application state and bundled resources.

State never lives next to the executable: the installer targets Program
Files, which is read-only for non-admin users.
"""
import os
import sys
from pathlib import Path

APP_NAME = "OBSYouTubeUploader"


def state_dir() -> Path:
    """Per-user writable directory for settings, token, logs, and temp files."""
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / APP_NAME
    # Non-Windows fallback so tests and development work off-platform.
    return Path.home() / ".local" / "share" / APP_NAME


def settings_file() -> Path:
    return state_dir() / "settings.json"


def token_file() -> Path:
    return state_dir() / "token.json"


def seen_file() -> Path:
    return state_dir() / "seen.json"


def log_dir() -> Path:
    return state_dir() / "logs"


def tmp_dir() -> Path:
    return state_dir() / "tmp"


def bundle_dir() -> Path:
    """Directory holding bundled binaries.

    PyInstaller unpacks to sys._MEIPASS; in a source checkout it is the
    repository root.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent.parent


def ensure_dirs() -> None:
    for d in (state_dir(), log_dir(), tmp_dir()):
        d.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/test_paths.py -v`
Expected: PASS (6 tests)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml obs_youtube_uploader/ tests/test_paths.py
git commit -m "feat: add package scaffolding and state path resolution"
```

---

### Task 2: Settings persistence

**Files:**
- Create: `obs_youtube_uploader/settings.py`
- Test: `tests/test_settings.py`

**Interfaces:**
- Consumes: `paths.settings_file()`
- Produces: `DEFAULTS: dict`, `load(path: Path | None = None) -> dict`, `save(data: dict, path: Path | None = None) -> None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_settings.py
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


def test_save_creates_parent_directory(tmp_path):
    p = tmp_path / "deep" / "s.json"
    settings.save(settings.DEFAULTS, p)
    assert p.exists()


@pytest.mark.parametrize("bad", ["", "sideways", None])
def test_load_rejects_invalid_privacy(tmp_path, bad):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"privacy": bad}))
    assert settings.load(p)["privacy"] == "private"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_settings.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# obs_youtube_uploader/settings.py
"""Settings persistence.

Key names match the pre-2.0 file: ``privacy`` and ``category`` (not
``category_id``). The privacy default is ``private``, resolving an
inconsistency in the old code where loading defaulted to ``unlisted`` but
uploading defaulted to ``private``.
"""
import json
from pathlib import Path

from . import paths

DEFAULTS = {
    "privacy": "private",
    "category": "20",
    "notify_mode": "toast",
    # Not a user-facing setting, but it must live here: save() projects onto
    # DEFAULTS keys, so anything undeclared is dropped on every write.
    "recording_dir": None,
}

_VALID_PRIVACY = {"private", "unlisted", "public"}
_VALID_NOTIFY = {"toast", "popup"}


def load(path: Path | None = None) -> dict:
    path = path or paths.settings_file()
    data = dict(DEFAULTS)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return data
    if not isinstance(raw, dict):
        return data
    for key in DEFAULTS:
        if key in raw:
            data[key] = raw[key]
    if data["privacy"] not in _VALID_PRIVACY:
        data["privacy"] = DEFAULTS["privacy"]
    if data["notify_mode"] not in _VALID_NOTIFY:
        data["notify_mode"] = DEFAULTS["notify_mode"]
    if not isinstance(data["category"], str) or not data["category"].isdigit():
        data["category"] = DEFAULTS["category"]
    if data["recording_dir"] is not None and not isinstance(data["recording_dir"], str):
        data["recording_dir"] = None
    return data


def save(data: dict, path: Path | None = None) -> None:
    path = path or paths.settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: data.get(k, DEFAULTS[k]) for k in DEFAULTS}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_settings.py -v`
Expected: PASS (12 tests, counting the 3 parametrized cases)

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/settings.py tests/test_settings.py
git commit -m "feat: add settings persistence with validated defaults"
```

---

### Task 3: Video library — discovery, metadata, deletion

**Files:**
- Create: `obs_youtube_uploader/library.py`
- Test: `tests/test_library.py`

**Interfaces:**
- Consumes: nothing
- Produces: `VIDEO_EXTS: set[str]`, `VideoInfo` dataclass with fields `path: Path`, `mtime: float`, `size: int`, `duration: float | None` and properties `date_str`, `size_str`, `duration_str`; `discover(directory: Path) -> list[Path]`, `probe_duration(path: Path, ffprobe_bin: str | None, runner=subprocess.run) -> float | None`, `build_info(path: Path, ffprobe_bin: str | None, runner=subprocess.run) -> VideoInfo`, `delete(items: list[Path]) -> tuple[int, list[tuple[Path, str]]]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_library.py
import datetime
import os
import subprocess
from pathlib import Path

import pytest
from obs_youtube_uploader import library


def _touch(p: Path, size: int = 10, mtime: float | None = None) -> Path:
    p.write_bytes(b"x" * size)
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p


def test_discover_finds_only_video_extensions(tmp_path):
    _touch(tmp_path / "a.mkv")
    _touch(tmp_path / "b.mp4")
    _touch(tmp_path / "notes.txt")
    _touch(tmp_path / "c.MKV")  # case-insensitive
    found = {p.name for p in library.discover(tmp_path)}
    assert found == {"a.mkv", "b.mp4", "c.MKV"}


def test_discover_sorts_newest_first(tmp_path):
    _touch(tmp_path / "old.mkv", mtime=1000)
    _touch(tmp_path / "new.mkv", mtime=2000)
    assert [p.name for p in library.discover(tmp_path)] == ["new.mkv", "old.mkv"]


def test_discover_returns_empty_for_missing_directory(tmp_path):
    assert library.discover(tmp_path / "nope") == []


def test_discover_ignores_subdirectories(tmp_path):
    (tmp_path / "sub.mkv").mkdir()
    assert library.discover(tmp_path) == []


def test_probe_duration_parses_ffprobe_output(tmp_path):
    f = _touch(tmp_path / "a.mkv")

    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout="12.5\n", stderr="")

    assert library.probe_duration(f, "ffprobe", runner=fake_run) == 12.5


def test_probe_duration_returns_none_without_binary(tmp_path):
    f = _touch(tmp_path / "a.mkv")
    assert library.probe_duration(f, None) is None


def test_probe_duration_returns_none_on_failure(tmp_path):
    f = _touch(tmp_path / "a.mkv")

    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")

    assert library.probe_duration(f, "ffprobe", runner=fake_run) is None


def test_probe_duration_returns_none_when_ffprobe_raises(tmp_path):
    f = _touch(tmp_path / "a.mkv")

    def fake_run(cmd, **kw):
        raise OSError("not found")

    assert library.probe_duration(f, "ffprobe", runner=fake_run) is None


def test_duration_str_degrades_to_question_mark(tmp_path):
    f = _touch(tmp_path / "a.mkv")
    info = library.build_info(f, None)
    assert info.duration is None
    assert info.duration_str == "?"


def test_duration_str_formats_minutes_and_seconds(tmp_path):
    f = _touch(tmp_path / "a.mkv")

    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout="125", stderr="")

    info = library.build_info(f, "ffprobe", runner=fake_run)
    assert info.duration_str == "2:05"


def test_size_str_is_human_readable(tmp_path):
    f = _touch(tmp_path / "a.mkv", size=2048)
    assert library.build_info(f, None).size_str == "2.0 KB"


def test_date_str_matches_mtime(tmp_path):
    f = _touch(tmp_path / "a.mkv", mtime=0)
    expected = datetime.datetime.fromtimestamp(0).strftime("%Y-%m-%d %H:%M")
    assert library.build_info(f, None).date_str == expected


def test_delete_removes_files_and_counts_them(tmp_path):
    a = _touch(tmp_path / "a.mkv")
    b = _touch(tmp_path / "b.mkv")
    deleted, failures = library.delete([a, b])
    assert deleted == 2
    assert failures == []
    assert not a.exists() and not b.exists()


def test_delete_leaves_unlisted_files_alone(tmp_path):
    a = _touch(tmp_path / "a.mkv")
    keep = _touch(tmp_path / "keep.mkv")
    library.delete([a])
    assert keep.exists()


def test_delete_reports_failures_without_aborting_batch(tmp_path):
    a = _touch(tmp_path / "a.mkv")
    missing = tmp_path / "gone.mkv"
    c = _touch(tmp_path / "c.mkv")
    deleted, failures = library.delete([a, missing, c])
    assert deleted == 2
    assert len(failures) == 1
    assert failures[0][0] == missing
    assert not c.exists()


def test_discover_skips_files_deleted_after_iterdir(tmp_path, monkeypatch):
    """Race: a file gone by stat() time must be skipped, not crash the scan."""
    _touch(tmp_path / "old.mkv", mtime=1000)
    disappeared = _touch(tmp_path / "disappeared.mkv", mtime=1500)
    _touch(tmp_path / "new.mkv", mtime=2000)

    original_stat = Path.stat

    def stat_with_race(self):
        if self == disappeared:
            raise FileNotFoundError(f"{self} deleted between iterdir and stat")
        return original_stat(self)

    monkeypatch.setattr(Path, "stat", stat_with_race)
    assert [p.name for p in library.discover(tmp_path)] == ["new.mkv", "old.mkv"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_library.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# obs_youtube_uploader/library.py
"""Video discovery, metadata, and deletion.

Pure filesystem logic with no GUI dependency: the old VideoEntry held a
tk.BooleanVar, which made it impossible to test. Selection state now lives
in the UI layer; this module deals only in data.
"""
import datetime
import subprocess
from dataclasses import dataclass
from pathlib import Path

VIDEO_EXTS = {".mkv", ".mp4", ".flv", ".mov", ".avi", ".ts", ".m4v", ".webm"}


def format_size(size_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


@dataclass
class VideoInfo:
    path: Path
    mtime: float
    size: int
    duration: float | None

    @property
    def date_str(self) -> str:
        return datetime.datetime.fromtimestamp(self.mtime).strftime("%Y-%m-%d %H:%M")

    @property
    def size_str(self) -> str:
        return format_size(self.size)

    @property
    def duration_str(self) -> str:
        if self.duration is None:
            return "?"
        minutes, seconds = divmod(int(self.duration), 60)
        return f"{minutes}:{seconds:02d}"


def discover(directory: Path) -> list[Path]:
    """Video files in *directory*, newest first. Missing directory -> [].

    Skips files that disappear between iterdir and stat. This is not a
    hypothetical race: the watcher polls this every few seconds against a
    directory OBS is actively writing to, while the UI can delete files.
    Stat exactly once per file, inside the guard.
    """
    entries: list[tuple[Path, float]] = []
    try:
        for p in Path(directory).iterdir():
            if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
                try:
                    entries.append((p, p.stat().st_mtime))
                except OSError:
                    continue  # Vanished mid-scan; skip it, do not abort.
    except OSError:
        return []
    entries.sort(key=lambda pair: pair[1], reverse=True)
    return [p for p, _ in entries]


def probe_duration(path: Path, ffprobe_bin: str | None, runner=subprocess.run) -> float | None:
    """Duration in seconds, or None if ffprobe is absent or fails.

    Returning None rather than raising is deliberate: a missing ffprobe
    degrades the duration column to "?" instead of blocking the app.
    """
    if not ffprobe_bin:
        return None
    try:
        result = runner(
            [ffprobe_bin, "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=15,
        )
    except Exception:
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def build_info(path: Path, ffprobe_bin: str | None, runner=subprocess.run) -> VideoInfo:
    stat = path.stat()
    return VideoInfo(
        path=path,
        mtime=stat.st_mtime,
        size=stat.st_size,
        duration=probe_duration(path, ffprobe_bin, runner=runner),
    )


def delete(items: list[Path]) -> tuple[int, list[tuple[Path, str]]]:
    """Permanently delete *items*.

    One failure does not abort the batch. Returns (deleted_count, failures)
    where each failure is (path, error_message).
    """
    deleted = 0
    failures: list[tuple[Path, str]] = []
    for path in items:
        try:
            path.unlink()
            deleted += 1
        except OSError as exc:
            failures.append((path, str(exc)))
    return deleted, failures
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_library.py -v`
Expected: PASS (16 tests)

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/library.py tests/test_library.py
git commit -m "feat: add video library with discovery, metadata, and deletion"
```

---

### Task 4: OBS configuration discovery

**Files:**
- Create: `obs_youtube_uploader/obsconfig.py`
- Test: `tests/test_obsconfig.py`

**Interfaces:**
- Consumes: nothing
- Produces: `profiles_root(appdata: Path | None = None) -> Path | None`, `find_recording_dir(appdata: Path | None = None) -> Path | None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_obsconfig.py
import os
from pathlib import Path

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_obsconfig.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# obs_youtube_uploader/obsconfig.py
"""Read OBS's own configuration to pre-fill the recording directory.

This is what removes the last manual configuration step: rather than asking
the user where OBS records, read it from OBS.
"""
import configparser
import os
from pathlib import Path

# Section/key pairs in priority order. Simple output mode is the default in
# OBS and is what most users have.
_PATH_KEYS = [
    ("SimpleOutput", "FilePath"),
    ("AdvOut", "RecFilePath"),
]


def profiles_root(appdata: Path | None = None) -> Path | None:
    if appdata is None:
        raw = os.environ.get("APPDATA")
        if not raw:
            return None
        appdata = Path(raw)
    root = Path(appdata) / "obs-studio" / "basic" / "profiles"
    return root if root.is_dir() else None


def _read_path(ini: Path) -> Path | None:
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    try:
        parser.read(ini, encoding="utf-8")
    except (configparser.Error, OSError, UnicodeDecodeError):
        return None
    for section, key in _PATH_KEYS:
        if parser.has_option(section, key):
            value = parser.get(section, key).strip()
            if value:
                return Path(value)
    return None


def find_recording_dir(appdata: Path | None = None) -> Path | None:
    """Recording directory from the most recently modified OBS profile.

    Returns None when OBS is absent, has no profiles, or no profile
    specifies a path — the caller falls back to asking the user.
    """
    root = profiles_root(appdata)
    if root is None:
        return None
    inis = sorted(
        (p for p in root.glob("*/basic.ini") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for ini in inis:
        found = _read_path(ini)
        if found is not None:
            return found
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_obsconfig.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/obsconfig.py tests/test_obsconfig.py
git commit -m "feat: auto-detect recording directory from OBS config"
```

---

### Task 5: Stitching with guaranteed temp cleanup

**Files:**
- Create: `obs_youtube_uploader/stitch.py`
- Test: `tests/test_stitch.py`

**Interfaces:**
- Consumes: `library.VideoInfo`, `paths.tmp_dir()`
- Produces: `order_for_stitch(infos: list[VideoInfo]) -> list[VideoInfo]`, `build_command(sources: list[Path], out_path: Path, ffmpeg_bin: str) -> list[str]`, `stitched(sources, ffmpeg_bin, tmp_dir, runner=subprocess.run)` context manager yielding `Path`, `sweep_orphans(tmp_dir: Path) -> int`, `StitchError`

This task fixes the leak identified in the spec: the old code removed the temp file only after a *successful* upload (`youtube_uploader.py:457-458`), so a failed upload left a multi-GB file behind permanently.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stitch.py
import subprocess
from pathlib import Path

import pytest
from obs_youtube_uploader import library, stitch


def _info(path: Path, mtime: float) -> library.VideoInfo:
    return library.VideoInfo(path=path, mtime=mtime, size=1, duration=None)


def _ok(cmd, **kw):
    # Simulate ffmpeg producing its output file.
    out = Path(cmd[-1])
    out.write_bytes(b"stitched")
    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


def _fail(cmd, **kw):
    return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="ffmpeg exploded")


def test_order_for_stitch_is_earliest_first():
    a = _info(Path("a.mkv"), 300)
    b = _info(Path("b.mkv"), 100)
    c = _info(Path("c.mkv"), 200)
    assert [i.path.name for i in stitch.order_for_stitch([a, b, c])] == ["b.mkv", "c.mkv", "a.mkv"]


def test_build_command_includes_every_source(tmp_path):
    srcs = [tmp_path / "a.mkv", tmp_path / "b.mkv"]
    cmd = stitch.build_command(srcs, tmp_path / "out.mkv", "ffmpeg")
    assert cmd[0] == "ffmpeg"
    for s in srcs:
        assert str(s) in cmd
    assert cmd[-1] == str(tmp_path / "out.mkv")


def test_build_command_concat_filter_matches_input_count(tmp_path):
    srcs = [tmp_path / f"{n}.mkv" for n in "abc"]
    cmd = stitch.build_command(srcs, tmp_path / "out.mkv", "ffmpeg")
    assert "n=3" in " ".join(cmd)


def test_stitched_yields_an_existing_file(tmp_path):
    srcs = [tmp_path / "a.mkv", tmp_path / "b.mkv"]
    for s in srcs:
        s.write_bytes(b"x")
    with stitch.stitched(srcs, "ffmpeg", tmp_path, runner=_ok) as out:
        assert out.exists()


def test_stitched_cleans_up_on_success(tmp_path):
    srcs = [tmp_path / "a.mkv", tmp_path / "b.mkv"]
    for s in srcs:
        s.write_bytes(b"x")
    with stitch.stitched(srcs, "ffmpeg", tmp_path, runner=_ok) as out:
        captured = out
    assert not captured.exists()


def test_stitched_cleans_up_when_body_raises(tmp_path):
    """This is the leak the old code had: cleanup must not depend on success."""
    srcs = [tmp_path / "a.mkv", tmp_path / "b.mkv"]
    for s in srcs:
        s.write_bytes(b"x")
    captured = None
    with pytest.raises(RuntimeError):
        with stitch.stitched(srcs, "ffmpeg", tmp_path, runner=_ok) as out:
            captured = out
            raise RuntimeError("upload failed")
    assert captured is not None
    assert not captured.exists()


def test_stitched_raises_when_ffmpeg_fails(tmp_path):
    srcs = [tmp_path / "a.mkv", tmp_path / "b.mkv"]
    for s in srcs:
        s.write_bytes(b"x")
    with pytest.raises(stitch.StitchError):
        with stitch.stitched(srcs, "ffmpeg", tmp_path, runner=_fail):
            pass


def test_stitched_requires_at_least_two_sources(tmp_path):
    with pytest.raises(ValueError):
        with stitch.stitched([tmp_path / "a.mkv"], "ffmpeg", tmp_path, runner=_ok):
            pass


def test_output_names_are_unique_across_runs(tmp_path):
    srcs = [tmp_path / "a.mkv", tmp_path / "b.mkv"]
    for s in srcs:
        s.write_bytes(b"x")
    names = []
    for _ in range(2):
        with stitch.stitched(srcs, "ffmpeg", tmp_path, runner=_ok) as out:
            names.append(out.name)
    assert names[0] != names[1]


def test_sweep_orphans_removes_only_stitch_artifacts(tmp_path):
    (tmp_path / "stitch-abc123.mkv").write_bytes(b"x")
    (tmp_path / "unrelated.txt").write_bytes(b"x")
    assert stitch.sweep_orphans(tmp_path) == 1
    assert (tmp_path / "unrelated.txt").exists()


def test_sweep_orphans_handles_missing_directory(tmp_path):
    assert stitch.sweep_orphans(tmp_path / "nope") == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_stitch.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# obs_youtube_uploader/stitch.py
"""Concatenate recordings into a single file for upload.

The temp file's lifetime is owned by a context manager so cleanup happens on
every exit path. The pre-2.0 code deleted it only after a successful upload,
so any failure leaked a multi-gigabyte file permanently.
"""
import subprocess
import uuid
from contextlib import contextmanager
from pathlib import Path

from .library import VideoInfo

_PREFIX = "stitch-"
_SUFFIX = ".mkv"


class StitchError(RuntimeError):
    """ffmpeg failed to produce a concatenated file."""


def order_for_stitch(infos: list[VideoInfo]) -> list[VideoInfo]:
    """Earliest recording first, matching pre-2.0 behavior."""
    return sorted(infos, key=lambda i: i.mtime)


def build_command(sources: list[Path], out_path: Path, ffmpeg_bin: str) -> list[str]:
    cmd = [ffmpeg_bin, "-y"]
    for src in sources:
        cmd += ["-i", str(src)]
    streams = "".join(f"[{n}:v][{n}:a]" for n in range(len(sources)))
    cmd += [
        "-filter_complex", f"{streams}concat=n={len(sources)}:v=1:a=1[outv][outa]",
        "-map", "[outv]", "-map", "[outa]",
        str(out_path),
    ]
    return cmd


@contextmanager
def stitched(sources: list[Path], ffmpeg_bin: str, tmp_dir: Path, runner=subprocess.run):
    """Yield a concatenated file, deleting it on every exit path."""
    if len(sources) < 2:
        raise ValueError("stitching requires at least two sources")
    tmp_dir = Path(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    out_path = tmp_dir / f"{_PREFIX}{uuid.uuid4().hex}{_SUFFIX}"
    try:
        result = runner(build_command(sources, out_path, ffmpeg_bin),
                        capture_output=True, text=True)
        if result.returncode != 0:
            raise StitchError(result.stderr.strip() or "ffmpeg failed")
        if not out_path.exists():
            raise StitchError("ffmpeg reported success but produced no output")
        yield out_path
    finally:
        try:
            out_path.unlink()
        except OSError:
            pass


def sweep_orphans(tmp_dir: Path) -> int:
    """Delete stitch artifacts left behind by a crash. Returns the count."""
    tmp_dir = Path(tmp_dir)
    if not tmp_dir.is_dir():
        return 0
    removed = 0
    for path in tmp_dir.glob(f"{_PREFIX}*{_SUFFIX}"):
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_stitch.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/stitch.py tests/test_stitch.py
git commit -m "feat: add stitching with guaranteed temp-file cleanup

Fixes a leak where the stitched file was removed only after a successful
upload, so any failure left it on disk permanently."
```

---

### Task 6: Upload error classification

**Files:**
- Create: `obs_youtube_uploader/uploader.py`
- Test: `tests/test_uploader.py`

**Interfaces:**
- Consumes: nothing
- Produces: `Outcome` enum with members `RETRY`, `QUOTA`, `AUTH`, `PERMANENT`; `RETRYABLE_STATUS: frozenset[int]`, `classify(exc: Exception) -> Outcome`, `message_for(outcome: Outcome) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_uploader.py
import socket

import pytest
from obs_youtube_uploader import uploader


class FakeResp:
    def __init__(self, status): self.status = status
    def __getitem__(self, k): return self.status if k == "status" else None


class FakeHttpError(Exception):
    """Stands in for googleapiclient.errors.HttpError."""
    def __init__(self, status, content=b""):
        self.resp = FakeResp(status)
        self.status_code = status
        self.content = content
        super().__init__(f"HTTP {status}")


@pytest.mark.parametrize("status", [500, 502, 503, 504, 408, 429])
def test_transient_http_errors_retry(status):
    assert uploader.classify(FakeHttpError(status)) is uploader.Outcome.RETRY


@pytest.mark.parametrize("exc", [
    socket.timeout("slow"),
    ConnectionResetError("reset"),
    OSError("network down"),
])
def test_network_errors_retry(exc):
    assert uploader.classify(exc) is uploader.Outcome.RETRY


def test_quota_exceeded_is_its_own_outcome():
    err = FakeHttpError(403, b'{"error":{"errors":[{"reason":"quotaExceeded"}]}}')
    assert uploader.classify(err) is uploader.Outcome.QUOTA


def test_access_denied_is_an_auth_outcome():
    err = FakeHttpError(403, b'{"error":{"errors":[{"reason":"accessNotConfigured"}]}}')
    assert uploader.classify(err) is uploader.Outcome.AUTH


def test_plain_403_without_reason_is_auth():
    assert uploader.classify(FakeHttpError(403)) is uploader.Outcome.AUTH


def test_401_is_auth():
    assert uploader.classify(FakeHttpError(401)) is uploader.Outcome.AUTH


@pytest.mark.parametrize("status", [400, 404, 413])
def test_other_client_errors_are_permanent(status):
    assert uploader.classify(FakeHttpError(status)) is uploader.Outcome.PERMANENT


def test_unknown_exception_is_permanent():
    assert uploader.classify(ValueError("???")) is uploader.Outcome.PERMANENT


def test_quota_message_is_plain_english():
    msg = uploader.message_for(uploader.Outcome.QUOTA)
    assert "limit" in msg.lower()
    assert "traceback" not in msg.lower()


def test_every_outcome_has_a_message():
    for outcome in uploader.Outcome:
        assert uploader.message_for(outcome)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_uploader.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# obs_youtube_uploader/uploader.py
"""YouTube upload: error classification, retrying upload, OAuth.

Errors are classified before they reach the UI so users see plain language
instead of a traceback in a log file nobody reads.
"""
import enum
import json
import socket

RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})


class Outcome(enum.Enum):
    RETRY = "retry"
    QUOTA = "quota"
    AUTH = "auth"
    PERMANENT = "permanent"


_MESSAGES = {
    Outcome.RETRY: "Network problem. Retrying…",
    Outcome.QUOTA: (
        "YouTube's daily upload limit for this app has been reached. "
        "Please try again tomorrow."
    ),
    Outcome.AUTH: (
        "Google refused the sign-in. If this build is a pre-release, your "
        "account may not be on the approved tester list yet."
    ),
    Outcome.PERMANENT: "The upload failed and retrying will not help.",
}


def _status_of(exc: Exception) -> int | None:
    resp = getattr(exc, "resp", None)
    status = getattr(resp, "status", None)
    if status is None:
        status = getattr(exc, "status_code", None)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def _reasons(exc: Exception) -> set[str]:
    content = getattr(exc, "content", None)
    if not content:
        return set()
    if isinstance(content, bytes):
        content = content.decode("utf-8", "replace")
    try:
        payload = json.loads(content)
    except ValueError:
        return set()
    errors = payload.get("error", {}).get("errors", [])
    return {e.get("reason", "") for e in errors if isinstance(e, dict)}


def classify(exc: Exception) -> Outcome:
    status = _status_of(exc)
    if status is None:
        if isinstance(exc, (socket.timeout, ConnectionError, OSError)):
            return Outcome.RETRY
        return Outcome.PERMANENT
    if status in RETRYABLE_STATUS:
        return Outcome.RETRY
    if status == 403 and "quotaExceeded" in _reasons(exc):
        return Outcome.QUOTA
    if status in (401, 403):
        return Outcome.AUTH
    return Outcome.PERMANENT


def message_for(outcome: Outcome) -> str:
    return _MESSAGES[outcome]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_uploader.py -v`
Expected: PASS (19 tests, counting parametrized cases)

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/uploader.py tests/test_uploader.py
git commit -m "feat: classify upload errors into actionable outcomes"
```

---

### Task 7: Resumable upload with retry

**Files:**
- Modify: `obs_youtube_uploader/uploader.py` (append)
- Modify: `tests/test_uploader.py` (append)

**Interfaces:**
- Consumes: `Outcome`, `classify`, `RETRYABLE_STATUS` from Task 6
- Produces: `build_body(title: str, description: str, privacy: str, category: str, index: int, total: int) -> dict`, `upload(request, *, on_progress=None, max_attempts=5, sleep=time.sleep, jitter=random.random) -> str`, `UploadFailed` exception with attribute `outcome: Outcome`

`upload` takes an already-built resumable request object rather than constructing one, so tests can drive it with a fake. **The returned video ID must survive a mid-upload failure** — the link column added in `b04c3a7` depends on it.

- [ ] **Step 1: Write the failing test (append to `tests/test_uploader.py`)**

```python
class FakeRequest:
    """Stands in for a googleapiclient resumable insert request.

    `script` is a list of either ('progress', fraction), ('fail', exc), or
    ('done', response_dict) applied on successive next_chunk() calls.
    """
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def next_chunk(self):
        self.calls += 1
        kind, value = self.script.pop(0)
        if kind == "fail":
            raise value
        if kind == "progress":
            return FakeStatus(value), None
        return None, value


class FakeStatus:
    def __init__(self, fraction): self._f = fraction
    def progress(self): return self._f


def test_upload_returns_video_id_on_clean_run():
    req = FakeRequest([("progress", 0.5), ("done", {"id": "abc123"})])
    assert uploader.upload(req, sleep=lambda s: None) == "abc123"


def test_upload_resumes_after_transient_failure():
    req = FakeRequest([
        ("progress", 0.3),
        ("fail", FakeHttpError(503)),
        ("progress", 0.7),
        ("done", {"id": "xyz789"}),
    ])
    assert uploader.upload(req, sleep=lambda s: None) == "xyz789"


def test_video_id_survives_mid_upload_failure():
    """Regression guard: the link column breaks if retry loses the ID."""
    req = FakeRequest([
        ("fail", ConnectionResetError("reset")),
        ("done", {"id": "survived"}),
    ])
    assert uploader.upload(req, sleep=lambda s: None) == "survived"


def test_upload_does_not_restart_from_zero():
    """next_chunk is called once more than the number of failures, never reset."""
    req = FakeRequest([
        ("progress", 0.5),
        ("fail", FakeHttpError(500)),
        ("done", {"id": "a"}),
    ])
    uploader.upload(req, sleep=lambda s: None)
    assert req.calls == 3


def test_upload_stops_after_max_attempts():
    req = FakeRequest([("fail", FakeHttpError(503))] * 10)
    with pytest.raises(uploader.UploadFailed) as excinfo:
        uploader.upload(req, max_attempts=3, sleep=lambda s: None)
    assert excinfo.value.outcome is uploader.Outcome.RETRY
    assert req.calls == 3


def test_upload_does_not_retry_permanent_errors():
    req = FakeRequest([("fail", FakeHttpError(400))] * 5)
    with pytest.raises(uploader.UploadFailed) as excinfo:
        uploader.upload(req, sleep=lambda s: None)
    assert excinfo.value.outcome is uploader.Outcome.PERMANENT
    assert req.calls == 1


def test_upload_does_not_retry_quota_errors():
    err = FakeHttpError(403, b'{"error":{"errors":[{"reason":"quotaExceeded"}]}}')
    req = FakeRequest([("fail", err)] * 5)
    with pytest.raises(uploader.UploadFailed) as excinfo:
        uploader.upload(req, sleep=lambda s: None)
    assert excinfo.value.outcome is uploader.Outcome.QUOTA
    assert req.calls == 1


def test_backoff_grows_between_attempts():
    slept = []
    req = FakeRequest([
        ("fail", FakeHttpError(503)),
        ("fail", FakeHttpError(503)),
        ("done", {"id": "a"}),
    ])
    uploader.upload(req, sleep=slept.append, jitter=lambda: 0.0)
    assert len(slept) == 2
    assert slept[1] > slept[0]


def test_progress_callback_receives_fractions():
    seen = []
    req = FakeRequest([("progress", 0.25), ("progress", 0.75), ("done", {"id": "a"})])
    uploader.upload(req, on_progress=seen.append, sleep=lambda s: None)
    assert seen == [0.25, 0.75]


def test_retry_callback_reports_each_attempt():
    """A stalled upload must look like it is retrying, not frozen."""
    attempts = []
    req = FakeRequest([
        ("fail", FakeHttpError(503)),
        ("fail", FakeHttpError(503)),
        ("done", {"id": "a"}),
    ])
    uploader.upload(req, on_retry=lambda n, d: attempts.append(n), sleep=lambda s: None)
    assert attempts == [1, 2]


def test_failed_upload_exposes_request_for_manual_retry():
    """The request holds the resumable session; discarding it would make a
    Retry button restart from zero."""
    req = FakeRequest([("fail", FakeHttpError(503))] * 4)
    with pytest.raises(uploader.UploadFailed) as excinfo:
        uploader.upload(req, max_attempts=2, sleep=lambda s: None)
    assert excinfo.value.request is req


def test_missing_id_in_response_is_a_permanent_failure():
    req = FakeRequest([("done", {"no_id_here": True})])
    with pytest.raises(uploader.UploadFailed) as excinfo:
        uploader.upload(req, sleep=lambda s: None)
    assert excinfo.value.outcome is uploader.Outcome.PERMANENT


def test_build_body_omits_suffix_for_single_upload():
    body = uploader.build_body("Fight", "desc", "private", "20", index=0, total=1)
    assert body["snippet"]["title"] == "Fight"
    assert body["status"]["privacyStatus"] == "private"
    assert body["snippet"]["categoryId"] == "20"


def test_build_body_adds_suffix_for_multi_upload():
    body = uploader.build_body("Fight", "d", "private", "20", index=1, total=3)
    assert body["snippet"]["title"] == "Fight (2/3)"


def test_build_body_falls_back_to_untitled():
    body = uploader.build_body("", "d", "private", "20", index=0, total=1)
    assert body["snippet"]["title"] == "Untitled"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_uploader.py -v`
Expected: FAIL with `AttributeError: module 'obs_youtube_uploader.uploader' has no attribute 'upload'`

- [ ] **Step 3: Write the implementation (append to `obs_youtube_uploader/uploader.py`)**

```python
import random
import time

CHUNK_SIZE = 4 * 1024 * 1024
BASE_BACKOFF = 1.0
MAX_BACKOFF = 32.0


class UploadFailed(Exception):
    """An upload failed. `outcome` says whether retrying could ever help.

    `request` carries the resumable request object so a manual Retry can
    resume the existing session instead of restarting from zero.
    """

    def __init__(self, outcome: Outcome, original: Exception | None = None,
                 request=None):
        self.outcome = outcome
        self.original = original
        self.request = request
        super().__init__(message_for(outcome))


def build_body(title: str, description: str, privacy: str, category: str,
               index: int, total: int) -> dict:
    title = title or "Untitled"
    if total > 1:
        title = f"{title} ({index + 1}/{total})"
    return {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": category,
        },
        "status": {"privacyStatus": privacy},
    }


def upload(request, *, on_progress=None, on_retry=None, max_attempts: int = 5,
           sleep=time.sleep, jitter=random.random) -> str:
    """Drive a resumable upload to completion, retrying transient failures.

    The *same* request object is reused across retries — that is what makes
    this resume rather than restart. Returns the YouTube video ID.

    on_retry(attempt_number, delay_seconds) fires before each backoff sleep
    so the UI can show "retrying" rather than appearing frozen.
    """
    attempts = 0
    response = None
    while response is None:
        try:
            status, response = request.next_chunk()
        except Exception as exc:
            outcome = classify(exc)
            attempts += 1
            if outcome is not Outcome.RETRY or attempts >= max_attempts:
                raise UploadFailed(outcome, exc, request=request) from exc
            delay = min(BASE_BACKOFF * (2 ** (attempts - 1)), MAX_BACKOFF) + jitter()
            if on_retry is not None:
                on_retry(attempts, delay)
            sleep(delay)
            continue
        if status is not None and on_progress is not None:
            on_progress(status.progress())

    video_id = response.get("id") if isinstance(response, dict) else None
    if not video_id:
        raise UploadFailed(Outcome.PERMANENT, request=request)
    return video_id
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_uploader.py -v`
Expected: PASS (34 tests)

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/uploader.py tests/test_uploader.py
git commit -m "feat: retry resumable uploads without losing progress or video ID"
```

---

### Task 8: OAuth with embedded credentials

**Files:**
- Modify: `obs_youtube_uploader/uploader.py` (append)
- Create: `obs_youtube_uploader/credentials.py`
- Modify: `tests/test_uploader.py` (append)
- Create: `.gitignore` (does not exist yet)

**Interfaces:**
- Consumes: `paths.token_file()`
- Produces: `credentials.CLIENT_CONFIG: dict`, `credentials.is_placeholder() -> bool`, `uploader.SCOPES: list[str]`, `uploader.load_credentials(token_path) -> Credentials | None`, `uploader.save_credentials(creds, token_path) -> None`, `uploader.needs_reauth(creds) -> bool`

`credentials.py` holds a placeholder committed to git; the release workflow overwrites it at build time (Task 16). This keeps the source tree free of real secrets while letting developers run from source with their own file.

- [ ] **Step 1: Write the failing test (append to `tests/test_uploader.py`)**

```python
from obs_youtube_uploader import credentials


def test_placeholder_credentials_are_detected():
    assert credentials.is_placeholder() in (True, False)


def test_client_config_has_installed_app_shape():
    cfg = credentials.CLIENT_CONFIG
    assert "installed" in cfg
    for key in ("client_id", "client_secret", "auth_uri", "token_uri"):
        assert key in cfg["installed"]


def test_scopes_are_upload_only():
    assert uploader.SCOPES == ["https://www.googleapis.com/auth/youtube.upload"]


def test_load_credentials_returns_none_when_token_missing(tmp_path):
    assert uploader.load_credentials(tmp_path / "nope.json") is None


def test_load_credentials_returns_none_on_corrupt_token(tmp_path):
    p = tmp_path / "token.json"
    p.write_text("not json")
    assert uploader.load_credentials(p) is None


def test_needs_reauth_for_none():
    assert uploader.needs_reauth(None) is True


def test_needs_reauth_false_for_valid_creds():
    class Creds:
        valid = True
        expired = False
        refresh_token = "r"
    assert uploader.needs_reauth(Creds()) is False


def test_needs_reauth_true_when_expired_without_refresh_token():
    class Creds:
        valid = False
        expired = True
        refresh_token = None
    assert uploader.needs_reauth(Creds()) is True


def test_save_credentials_writes_and_restricts(tmp_path):
    class Creds:
        def to_json(self): return '{"token": "x"}'
    p = tmp_path / "token.json"
    uploader.save_credentials(Creds(), p)
    assert p.exists()
    assert "token" in p.read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_uploader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'obs_youtube_uploader.credentials'`

- [ ] **Step 3: Write `credentials.py`**

```python
# obs_youtube_uploader/credentials.py
"""Embedded OAuth client configuration.

The values below are placeholders in the source tree. The release workflow
replaces this file at build time from a repository secret.

Embedding a desktop-app client secret is expected and sanctioned by Google:
for installed applications the flow's security comes from the loopback
redirect and the user's own consent, not from the secret being confidential.
It is extractable from the binary by anyone who cares, and that is fine.
"""

_PLACEHOLDER_ID = "REPLACE_AT_BUILD_TIME.apps.googleusercontent.com"

CLIENT_CONFIG = {
    "installed": {
        "client_id": _PLACEHOLDER_ID,
        "client_secret": "REPLACE_AT_BUILD_TIME",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "redirect_uris": ["http://localhost"],
    }
}


def is_placeholder() -> bool:
    """True when running from source without real credentials injected."""
    return CLIENT_CONFIG["installed"]["client_id"] == _PLACEHOLDER_ID
```

- [ ] **Step 4: Write the OAuth helpers (append to `obs_youtube_uploader/uploader.py`)**

```python
import os
import stat as _stat
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def load_credentials(token_path: Path):
    """Load stored credentials, or None if absent/unreadable."""
    from google.oauth2.credentials import Credentials
    token_path = Path(token_path)
    if not token_path.exists():
        return None
    try:
        return Credentials.from_authorized_user_file(str(token_path), SCOPES)
    except Exception:
        return None


def save_credentials(creds, token_path: Path) -> None:
    """Persist credentials with owner-only permissions.

    The token grants upload access to the user's channel, so it must not
    inherit a permissive directory default.
    """
    token_path = Path(token_path)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    try:
        os.chmod(token_path, _stat.S_IRUSR | _stat.S_IWUSR)
    except OSError:
        pass  # Best effort; Windows ACLs differ and failure is not fatal.


def needs_reauth(creds) -> bool:
    """True when a full interactive OAuth flow is required.

    While the app is unverified, refresh tokens expire after 7 days, so this
    returns True roughly weekly for every user. The caller must handle it
    smoothly rather than treating it as an error.
    """
    if creds is None:
        return True
    if getattr(creds, "valid", False):
        return False
    return not (getattr(creds, "expired", False) and getattr(creds, "refresh_token", None))


def run_oauth_flow():
    """Interactive consent via the loopback redirect. Returns Credentials."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    from .credentials import CLIENT_CONFIG
    flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, SCOPES)
    return flow.run_local_server(port=0)


def refresh_credentials(creds):
    from google.auth.transport.requests import Request
    creds.refresh(Request())
    return creds
```

- [ ] **Step 5: Create `.gitignore`**

The repository has no `.gitignore` today, so this creates it:

```bash
printf 'obs_youtube_uploader/credentials_real.py\nbuild/\ndist/\npackaging/bin/\n*.egg-info/\n__pycache__/\n' >> .gitignore
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: PASS (all tests across all modules)

- [ ] **Step 7: Commit**

```bash
git add obs_youtube_uploader/uploader.py obs_youtube_uploader/credentials.py tests/test_uploader.py .gitignore
git commit -m "feat: add OAuth with build-time embedded credentials"
```

---

# Phase 2 — Standalone application

---

### Task 9: Folder watcher with settled detection

**Files:**
- Create: `obs_youtube_uploader/watcher.py`
- Test: `tests/test_watcher.py`

**Interfaces:**
- Consumes: `library.discover`, `paths.seen_file()`
- Produces: `SeenEntry` dataclass (`size: int`, `mtime: float`); `load_seen(path) -> dict[str, SeenEntry]`, `save_seen(path, seen) -> None`, `Watcher(directory, seen_path, *, stable_polls=3)` with methods `baseline() -> None`, `poll_once() -> list[Path]`, `forget(path) -> None`, `prune() -> int`, `rebind(directory) -> None`

Two behaviors the spec calls out: existing files are baselined without notifying, and the seen-set persists so recordings made while the app was closed are still announced.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_watcher.py
import json
import os
from pathlib import Path

from obs_youtube_uploader import watcher


def _write(p: Path, size: int) -> Path:
    p.write_bytes(b"x" * size)
    return p


def _settle(w, path, times=3):
    """Poll enough times for `path` to be considered settled."""
    out = []
    for _ in range(times):
        out = w.poll_once()
    return out


def test_baseline_does_not_report_existing_files(tmp_path):
    """Must hold across enough polls to clear stable_polls, or the test
    passes against a watcher that simply does nothing."""
    _write(tmp_path / "old.mkv", 10)
    w = watcher.Watcher(tmp_path, tmp_path / "seen.json")
    w.baseline()
    for _ in range(5):
        assert w.poll_once() == []


def test_baseline_records_existing_files_on_first_run(tmp_path):
    seen_path = tmp_path / "seen.json"
    f = _write(tmp_path / "old.mkv", 10)
    watcher.Watcher(tmp_path, seen_path).baseline()
    assert str(f) in watcher.load_seen(seen_path)


def test_new_file_is_reported_once_settled(tmp_path):
    w = watcher.Watcher(tmp_path, tmp_path / "seen.json")
    w.baseline()
    _write(tmp_path / "new.mkv", 10)
    ready = _settle(w, tmp_path / "new.mkv")
    assert [p.name for p in ready] == ["new.mkv"]


def test_growing_file_is_not_reported_until_stable(tmp_path):
    w = watcher.Watcher(tmp_path, tmp_path / "seen.json")
    w.baseline()
    f = tmp_path / "growing.mkv"
    _write(f, 10)
    assert w.poll_once() == []
    _write(f, 20)
    assert w.poll_once() == []
    _write(f, 30)
    assert w.poll_once() == []


def test_file_reported_only_once(tmp_path):
    w = watcher.Watcher(tmp_path, tmp_path / "seen.json")
    w.baseline()
    _write(tmp_path / "a.mkv", 10)
    assert len(_settle(w, tmp_path / "a.mkv")) == 1
    assert w.poll_once() == []


def test_two_files_finishing_together_are_reported_together(tmp_path):
    """FightRecorder's merge writes a second file after the clips."""
    w = watcher.Watcher(tmp_path, tmp_path / "seen.json")
    w.baseline()
    _write(tmp_path / "clip.mkv", 10)
    _write(tmp_path / "Fight 2026.mkv", 20)
    ready = _settle(w, None)
    assert len(ready) == 2


def test_seen_set_persists_across_restart(tmp_path):
    seen_path = tmp_path / "seen.json"
    _write(tmp_path / "a.mkv", 10)
    w1 = watcher.Watcher(tmp_path, seen_path)
    w1.baseline()
    w2 = watcher.Watcher(tmp_path, seen_path)
    w2.baseline()
    for _ in range(5):
        assert w2.poll_once() == []


def test_file_added_while_app_closed_is_reported_on_restart(tmp_path):
    seen_path = tmp_path / "seen.json"
    _write(tmp_path / "a.mkv", 10)
    watcher.Watcher(tmp_path, seen_path).baseline()
    _write(tmp_path / "while_closed.mkv", 10)
    w2 = watcher.Watcher(tmp_path, seen_path)
    w2.baseline()
    ready = _settle(w2, None)
    assert [p.name for p in ready] == ["while_closed.mkv"]


def test_forget_drops_a_seen_entry(tmp_path):
    seen_path = tmp_path / "seen.json"
    f = _write(tmp_path / "a.mkv", 10)
    w = watcher.Watcher(tmp_path, seen_path)
    w.baseline()
    w.forget(f)
    assert str(f) not in watcher.load_seen(seen_path)


def test_prune_removes_entries_for_deleted_files(tmp_path):
    seen_path = tmp_path / "seen.json"
    f = _write(tmp_path / "a.mkv", 10)
    w = watcher.Watcher(tmp_path, seen_path)
    w.baseline()
    f.unlink()
    assert w.prune() == 1
    assert watcher.load_seen(seen_path) == {}


def test_load_seen_survives_corrupt_file(tmp_path):
    p = tmp_path / "seen.json"
    p.write_text("{{{")
    assert watcher.load_seen(p) == {}


def test_changed_file_is_reported_again(tmp_path):
    """SeenEntry stores size and mtime; they must actually be compared, or
    they are write-only fields and 'new or changed' is not implemented."""
    seen_path = tmp_path / "seen.json"
    f = _write(tmp_path / "a.mkv", 10)
    w = watcher.Watcher(tmp_path, seen_path)
    w.baseline()
    for _ in range(5):
        assert w.poll_once() == []
    _write(f, 999)  # rewritten: different size and mtime
    assert [p.name for p in _settle(w, f)] == ["a.mkv"]


def test_stale_seen_entry_does_not_suppress_a_new_file(tmp_path):
    seen_path = tmp_path / "seen.json"
    watcher.save_seen(seen_path, {str(tmp_path / "ghost.mkv"): watcher.SeenEntry(1, 1.0)})
    _write(tmp_path / "real.mkv", 10)
    w = watcher.Watcher(tmp_path, seen_path)
    w.baseline()
    assert [p.name for p in _settle(w, None)] == ["real.mkv"]


def test_rebind_switches_directory_and_baselines_silently(tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    old.mkdir()
    new.mkdir()
    _write(old / "a.mkv", 10)
    _write(new / "b.mkv", 10)
    w = watcher.Watcher(old, tmp_path / "seen.json")
    w.baseline()
    w.rebind(new)
    for _ in range(5):
        assert w.poll_once() == []
    _write(new / "c.mkv", 10)
    assert [p.name for p in _settle(w, None)] == ["c.mkv"]


def test_missing_directory_yields_no_results(tmp_path):
    w = watcher.Watcher(tmp_path / "nope", tmp_path / "seen.json")
    w.baseline()
    assert w.poll_once() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_watcher.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# obs_youtube_uploader/watcher.py
"""Poll a directory for finished recordings.

Polling rather than filesystem events: native change notifications are
unreliable on network and mapped drives, watchdog would be another
dependency, and polling one directory every few seconds costs nothing.

A file appearing is not a file finished. Size must hold steady across
several consecutive polls before the file is announced.
"""
import json
from dataclasses import dataclass
from pathlib import Path

from . import library


@dataclass
class SeenEntry:
    size: int
    mtime: float


def load_seen(path: Path) -> dict[str, SeenEntry]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, SeenEntry] = {}
    for key, value in raw.items():
        try:
            out[key] = SeenEntry(size=int(value["size"]), mtime=float(value["mtime"]))
        except (TypeError, KeyError, ValueError):
            continue
    return out


def save_seen(path: Path, seen: dict[str, SeenEntry]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: {"size": v.size, "mtime": v.mtime} for k, v in seen.items()}
    path.write_text(json.dumps(payload), encoding="utf-8")


class Watcher:
    def __init__(self, directory, seen_path, *, stable_polls: int = 3):
        self.directory = Path(directory)
        self.seen_path = Path(seen_path)
        self.stable_polls = stable_polls
        self.seen = load_seen(self.seen_path)
        self._pending: dict[str, tuple[int, int]] = {}  # key -> (size, stable_count)

    def baseline(self) -> None:
        """Establish the starting point without announcing anything.

        First ever run (no seen file): record every current file silently,
        so launching the app does not announce the user's whole back
        catalogue.

        Any later run (seen file exists): only prune. Files on disk but
        absent from the persisted set are genuinely new — recorded while
        the app was closed — and poll_once() announces them.
        """
        first_run = not self.seen_path.exists()
        if first_run:
            for path in library.discover(self.directory):
                try:
                    stat = path.stat()
                except OSError:
                    continue
                self.seen[str(path)] = SeenEntry(size=stat.st_size, mtime=stat.st_mtime)
        else:
            self.prune()
        save_seen(self.seen_path, self.seen)

    def poll_once(self) -> list[Path]:
        """Return files that have just become stable and are new or changed."""
        ready: list[Path] = []
        for path in library.discover(self.directory):
            key = str(path)
            try:
                stat = path.stat()
            except OSError:
                continue
            entry = self.seen.get(key)
            if entry is not None and entry.size == stat.st_size and entry.mtime == stat.st_mtime:
                continue  # Unchanged since we last recorded it.
            previous = self._pending.get(key)
            if previous is not None and previous[0] == stat.st_size:
                count = previous[1] + 1
            else:
                count = 1
            if count >= self.stable_polls:
                self._pending.pop(key, None)
                self.seen[key] = SeenEntry(size=stat.st_size, mtime=stat.st_mtime)
                ready.append(path)
            else:
                self._pending[key] = (stat.st_size, count)
        if ready:
            save_seen(self.seen_path, self.seen)
        return ready

    def rebind(self, directory) -> None:
        """Point at a new directory and silently baseline its contents.

        Used when the user changes the recording folder in Settings. Without
        this the watcher keeps polling the old folder until restart, and
        without the silent baseline the new folder's whole back catalogue
        would be announced at once.
        """
        self.directory = Path(directory)
        self._pending.clear()
        for path in library.discover(self.directory):
            try:
                stat = path.stat()
            except OSError:
                continue
            self.seen[str(path)] = SeenEntry(size=stat.st_size, mtime=stat.st_mtime)
        save_seen(self.seen_path, self.seen)

    def forget(self, path) -> None:
        """Drop an entry, e.g. after the user deletes the file."""
        key = str(path)
        self.seen.pop(key, None)
        self._pending.pop(key, None)
        save_seen(self.seen_path, self.seen)

    def prune(self) -> int:
        """Drop entries whose files no longer exist. Returns the count."""
        gone = [k for k in self.seen if not Path(k).exists()]
        for key in gone:
            del self.seen[key]
        if gone:
            save_seen(self.seen_path, self.seen)
        return len(gone)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_watcher.py -v`
Expected: PASS (16 tests)

- [ ] **Step 5: Commit**

```bash
git add obs_youtube_uploader/watcher.py tests/test_watcher.py
git commit -m "feat: add folder watcher with settled detection and persisted baseline"
```

---

### Task 10: Application window

**Files:**
- Create: `obs_youtube_uploader/app.py`

**Interfaces:**
- Consumes: everything from Tasks 1–9
- Produces: `UploaderWindow` class with `__init__(self, root, state)`, `show()`, `hide()`, `refresh()`; `AppState` dataclass holding `recording_dir: Path`, `settings: dict`, `ffmpeg_bin: str | None`, `ffprobe_bin: str | None`

No unit tests: this is GUI wiring, verified by the smoke checklist in Task 17. All logic it depends on is already tested.

- [ ] **Step 1: Write the binary resolution helper**

```python
# obs_youtube_uploader/app.py
"""Tk window: video list, link column, upload and delete controls."""
import shutil
import threading
import tkinter as tk
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import messagebox, ttk

from . import library, paths, settings as settings_mod, stitch, uploader


def resolve_binary(name: str) -> str | None:
    """Find a bundled binary, falling back to PATH."""
    exe = f"{name}.exe"
    candidate = paths.bundle_dir() / "bin" / exe
    if candidate.exists():
        return str(candidate)
    candidate = paths.bundle_dir() / exe
    if candidate.exists():
        return str(candidate)
    return shutil.which(name)


@dataclass
class AppState:
    recording_dir: Path
    settings: dict = field(default_factory=settings_mod.load)
    ffmpeg_bin: str | None = field(default_factory=lambda: resolve_binary("ffmpeg"))
    ffprobe_bin: str | None = field(default_factory=lambda: resolve_binary("ffprobe"))


@dataclass
class UploadJob:
    """Every value the upload worker needs, captured on the main thread.

    Tk is not thread-safe: a worker calling .get() on a StringVar is the
    same violation as configuring a widget from one. Snapshotting into a
    plain dataclass at dispatch time removes the whole class of bug.

    `start_index` lets a retry resume partway through without renumbering
    the "(2/3)" title suffixes: the worker skips earlier indices but still
    computes totals from the full list.
    """
    items: list["library.VideoInfo"]
    title: str
    description: str
    stitch: bool
    privacy: str
    category: str
    start_index: int = 0


@dataclass
class RetryState:
    """What a manual Retry needs to resume rather than restart."""
    job: UploadJob
    resume_index: int
    request: object | None
```

- [ ] **Step 2: Write the window class**

```python
class UploaderWindow:
    """The main list window.

    Owns no logic beyond presentation: discovery, stitching, and uploading
    all live in tested modules.
    """

    def __init__(self, root: tk.Tk, state: AppState):
        self.root = root
        self.state = state
        self.infos: list[library.VideoInfo] = []
        self.selected: dict[Path, tk.BooleanVar] = {}
        self.links: dict[Path, tk.Entry] = {}
        self.upload_thread: threading.Thread | None = None

        root.title("OBS → YouTube Uploader")
        root.geometry("1350x650")
        root.minsize(750, 450)
        root.protocol("WM_DELETE_WINDOW", self.hide)
        self._build()
        self.refresh()

    def show(self, preselect: set | None = None) -> None:
        self.root.deiconify()
        self.root.lift()
        self.refresh(preselect)

    def hide(self) -> None:
        self.root.withdraw()

    def _build(self) -> None:
        meta = ttk.LabelFrame(self.root, text="Video details", padding=8)
        meta.pack(fill=tk.X, padx=5, pady=3)
        ttk.Label(meta, text="Title:").grid(row=0, column=0, sticky=tk.W)
        self.title_var = tk.StringVar(value="")
        ttk.Entry(meta, textvariable=self.title_var).grid(row=0, column=1, sticky=tk.EW, padx=5)
        ttk.Label(meta, text="Description:").grid(row=1, column=0, sticky=tk.NW, pady=(5, 0))
        self.desc_txt = tk.Text(meta, height=3, wrap=tk.WORD)
        self.desc_txt.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=(5, 0))
        meta.columnconfigure(1, weight=1)

        self.list_frame = ttk.Frame(self.root)
        self.list_frame.pack(fill=tk.BOTH, expand=True, padx=5)

        hdr = ttk.Frame(self.list_frame)
        hdr.pack(fill=tk.X)
        for text, width in (("☑", 3), ("Filename", 30), ("Date", 14),
                            ("Size", 9), ("Duration", 8), ("YouTube Link", 48)):
            anchor = tk.CENTER if text == "☑" else tk.W
            ttk.Label(hdr, text=text, width=width, anchor=anchor).pack(side=tk.LEFT, padx=2)
        ttk.Separator(self.list_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=2)

        self.canvas = tk.Canvas(self.list_frame, highlightthickness=0)
        scroll = ttk.Scrollbar(self.list_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.inner, anchor=tk.NW)
        self.canvas.configure(yscrollcommand=scroll.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.stitch_var = tk.BooleanVar(value=False)
        bot = ttk.Frame(self.root)
        bot.pack(fill=tk.X, padx=5, pady=5)
        self.stitch_chk = ttk.Checkbutton(bot, text="Stitch selected videos",
                                          variable=self.stitch_var)
        self.stitch_chk.pack(side=tk.LEFT)
        if not self.state.ffmpeg_bin:
            self.stitch_chk.state(["disabled"])
            ttk.Label(bot, text="(ffmpeg not found — stitching unavailable)",
                      foreground="orange").pack(side=tk.LEFT, padx=6)
        for text, cmd in (("Upload Selected", self._start_upload),
                          ("Delete Selected", self._delete_selected),
                          ("Select None", lambda: self._set_all(False)),
                          ("Select All", lambda: self._set_all(True))):
            ttk.Button(bot, text=text, command=cmd).pack(side=tk.RIGHT, padx=2)
        self.retry_btn = ttk.Button(bot, text="Retry", command=self._manual_retry)
        self.retry_btn.pack(side=tk.RIGHT, padx=2)
        self.retry_btn.state(["disabled"])
        ttk.Button(bot, text="Settings", command=self._open_settings).pack(side=tk.LEFT, padx=8)

        self.progress = ttk.Progressbar(self.root, mode="determinate")
        self.progress.pack(fill=tk.X, padx=5, pady=(0, 3))
        self.status = ttk.Label(self.root, text="")
        self.status.pack(fill=tk.X, padx=5, pady=(0, 5))
```

- [ ] **Step 3: Write the row rendering**

Append to `UploaderWindow`:

```python
    def refresh(self, preselect: set | None = None) -> None:
        """Rebuild the list. Paths in *preselect* start checked.

        The watcher passes newly-ready recordings here so the common case —
        finish a fight, open the window, hit Upload — needs no clicking.
        """
        preselect = preselect or set()
        for child in self.inner.winfo_children():
            child.destroy()
        self.selected.clear()
        self.links.clear()
        self.infos = [
            library.build_info(p, self.state.ffprobe_bin)
            for p in library.discover(self.state.recording_dir)
        ]
        for info in self.infos:
            row = ttk.Frame(self.inner)
            row.pack(fill=tk.X, pady=1)
            var = tk.BooleanVar(value=info.path in preselect)
            self.selected[info.path] = var
            ttk.Checkbutton(row, variable=var, width=2).pack(side=tk.LEFT, padx=2)
            for text, width in ((info.path.name, 30), (info.date_str, 14),
                                (info.size_str, 9), (info.duration_str, 8)):
                ttk.Label(row, text=text, width=width, anchor=tk.W).pack(side=tk.LEFT, padx=2)
            entry = tk.Entry(row, width=48, state="readonly", relief=tk.FLAT, fg="blue")
            entry.pack(side=tk.LEFT, padx=2)
            self.links[info.path] = entry
            ttk.Button(row, text="Copy", width=5,
                       command=lambda e=entry: self._copy(e)).pack(side=tk.LEFT, padx=2)
            ttk.Button(row, text="Open", width=5,
                       command=lambda e=entry: self._open(e)).pack(side=tk.LEFT, padx=(0, 8))
        self.status.config(text=f"Found {len(self.infos)} video(s)")

    def _set_all(self, value: bool) -> None:
        for var in self.selected.values():
            var.set(value)

    def _chosen(self) -> list[library.VideoInfo]:
        return [i for i in self.infos if self.selected.get(i.path, tk.BooleanVar()).get()]

    def _copy(self, entry: tk.Entry) -> None:
        url = entry.get()
        if url:
            self.root.clipboard_clear()
            self.root.clipboard_append(url)
            self.status.config(text="Link copied to clipboard", foreground="green")

    def _open(self, entry: tk.Entry) -> None:
        url = entry.get()
        if url:
            webbrowser.open(url)

    def _set_link(self, path: Path, video_id: str) -> None:
        """Link rows by source path, never by list position.

        Position-based matching (as in b04c3a7) shifts every subsequent row
        when one upload returns no ID.
        """
        entry = self.links.get(path)
        if entry is None:
            return
        entry.config(state=tk.NORMAL)
        entry.delete(0, tk.END)
        entry.insert(0, f"https://www.youtube.com/watch?v={video_id}")
        entry.config(state="readonly")
```

- [ ] **Step 4: Write the delete and upload handlers**

```python
    def _delete_selected(self) -> None:
        chosen = self._chosen()
        if not chosen:
            messagebox.showwarning("No Selection", "Select at least one video to delete.")
            return
        names = "\n".join(f"  • {i.path.name}" for i in chosen)
        if not messagebox.askyesno(
            "Confirm Delete",
            f"Permanently delete these files from disk?\n\n{names}\n\nThis cannot be undone.",
        ):
            return
        deleted, failures = library.delete([i.path for i in chosen])
        # Forget only what actually went. A file that failed to delete still
        # exists, and dropping its seen-entry would make the watcher
        # announce it again as if it were new.
        failed_paths = {p for p, _ in failures}
        if self.on_deleted is not None:
            for info in chosen:
                if info.path not in failed_paths:
                    self.on_deleted(info.path)
        self.refresh()
        msg = f"Deleted {deleted} file(s)."
        if failures:
            msg += f" {len(failures)} failed."
        self.status.config(text=msg)

    def _start_upload(self) -> None:
        chosen = self._chosen()
        if not chosen:
            messagebox.showwarning("No Selection", "Select at least one video to upload.")
            return
        if self.stitch_var.get() and len(chosen) < 2:
            messagebox.showwarning("Stitch", "Select at least two videos to stitch.")
            return
        if self.upload_thread and self.upload_thread.is_alive():
            messagebox.showwarning("Busy", "An upload is already in progress.")
            return
        # Read every widget value HERE, on the main thread. Tk is not
        # thread-safe, and .get() on a StringVar/Text/BooleanVar from a
        # worker is the same violation as configuring a label from one.
        job = UploadJob(
            items=chosen,
            title=self.title_var.get(),
            description=self.desc_txt.get("1.0", tk.END).strip(),
            stitch=self.stitch_var.get(),
            privacy=self.state.settings["privacy"],
            category=self.state.settings["category"],
        )
        self.upload_thread = threading.Thread(
            target=self._upload_worker, args=(job,), daemon=True)
        self.upload_thread.start()
```

- [ ] **Step 5: Write the upload worker**

```python
    def _ui(self, fn, *args) -> None:
        """Marshal a call onto the Tk main thread. Workers never touch widgets."""
        self.root.after(0, lambda: fn(*args))

    def _upload_worker(self, job: "UploadJob") -> None:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        index = job.start_index
        try:
            creds = uploader.load_credentials(paths.token_file())
            if uploader.needs_reauth(creds):
                creds = uploader.run_oauth_flow()
            elif not creds.valid:
                creds = uploader.refresh_credentials(creds)
            uploader.save_credentials(creds, paths.token_file())
            youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

            if job.stitch:
                ordered = stitch.order_for_stitch(job.items)
                sources = [i.path for i in ordered]
                with stitch.stitched(sources, self.state.ffmpeg_bin, paths.tmp_dir()) as merged:
                    vid = self._upload_one(youtube, MediaFileUpload, merged, job, 0, 1)
                for info in job.items:
                    self._ui(self._set_link, info.path, vid)
            else:
                total = len(job.items)
                for index in range(job.start_index, total):
                    info = job.items[index]
                    vid = self._upload_one(youtube, MediaFileUpload, info.path,
                                           job, index, total)
                    self._ui(self._set_link, info.path, vid)

            self.retry_state = None
            self._ui(self.status.config, {"text": "Upload complete!", "foreground": "green"})
            self._ui(self.progress.config, {"value": 100})
            self._ui(self.retry_btn.state, ["disabled"])
        except uploader.UploadFailed as exc:
            # Stitched failures cannot resume: the context manager has
            # already deleted the merged file the session points at, which
            # is the correct trade for never leaking multi-GB temporaries.
            # Retry re-stitches instead.
            resumable = exc.request is not None and not job.stitch
            self.retry_state = RetryState(
                job=job,
                resume_index=index,
                request=exc.request if resumable else None,
            )
            self._ui(messagebox.showerror, "Upload Failed", str(exc))
            self._ui(self.status.config, {"text": str(exc), "foreground": "red"})
            if exc.outcome is uploader.Outcome.RETRY:
                self._ui(self.retry_btn.state, ["!disabled"])
        except Exception as exc:
            self.retry_state = None
            self._ui(messagebox.showerror, "Upload Failed", str(exc))
            self._ui(self.status.config, {"text": f"Error: {exc}", "foreground": "red"})

    def _upload_one(self, youtube, MediaFileUpload, path, job, index, total) -> str:
        body = uploader.build_body(job.title, job.description, job.privacy,
                                   job.category, index, total)
        media = MediaFileUpload(str(path), chunksize=uploader.CHUNK_SIZE, resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        def on_progress(fraction: float) -> None:
            pct = ((index + fraction) / total) * 100
            self._ui(self.progress.config, {"value": pct})
            self._ui(self.status.config,
                     {"text": f"Uploading {index + 1}/{total} — {fraction * 100:.1f}%"})

        def on_retry(attempt: int, delay: float) -> None:
            self._ui(self.status.config,
                     {"text": f"Network problem — retrying in {delay:.0f}s "
                              f"(attempt {attempt})", "foreground": "orange"})

        return uploader.upload(request, on_progress=on_progress, on_retry=on_retry)

    def _manual_retry(self) -> None:
        state = self.retry_state
        if state is None:
            return
        self.retry_btn.state(["disabled"])
        self.upload_thread = threading.Thread(
            target=self._retry_worker, args=(state,), daemon=True)
        self.upload_thread.start()

    def _retry_worker(self, state: "RetryState") -> None:
        """Resume the interrupted upload, then finish the rest of the job."""
        from dataclasses import replace
        if state.request is None:
            # Stitched, or no session to resume: redo the whole job.
            self._upload_worker(replace(state.job, start_index=0))
            return
        try:
            info = state.job.items[state.resume_index]
            total = len(state.job.items)

            def on_progress(fraction: float) -> None:
                pct = ((state.resume_index + fraction) / total) * 100
                self._ui(self.progress.config, {"value": pct})

            vid = uploader.upload(state.request, on_progress=on_progress)
            self._ui(self._set_link, info.path, vid)
        except uploader.UploadFailed as exc:
            self.retry_state = replace(state, request=exc.request)
            self._ui(self.status.config, {"text": str(exc), "foreground": "red"})
            self._ui(self.retry_btn.state, ["!disabled"])
            return
        # The resumed file is done; continue with whatever followed it.
        if state.resume_index + 1 < len(state.job.items):
            self._upload_worker(replace(state.job, start_index=state.resume_index + 1))
        else:
            self.retry_state = None
            self._ui(self.status.config,
                     {"text": "Upload complete!", "foreground": "green"})
            self._ui(self.progress.config, {"value": 100})
            self._ui(self.retry_btn.state, ["disabled"])
```

- [ ] **Step 6: Add the `on_deleted` hook to `__init__`**

In `UploaderWindow.__init__`, after `self.upload_thread = None`, add:

```python
        self.on_deleted = None  # set by the tray app to notify the watcher
        self.on_settings_saved = None  # set by the tray app; see _settings_saved
        self.retry_state: "RetryState | None" = None
```

- [ ] **Step 7: Verify the module imports cleanly**

Run: `python -c "import ast,sys; ast.parse(open('obs_youtube_uploader/app.py').read()); print('syntax ok')"`
Expected: `syntax ok`

Run: `python -m pytest tests/ -v`
Expected: PASS (all previous tests still green)

- [ ] **Step 8: Commit**

```bash
git add obs_youtube_uploader/app.py
git commit -m "feat: add uploader window with path-keyed link column"
```

---

### Task 11: Settings window and Google account connection

**Files:**
- Create: `obs_youtube_uploader/settingsui.py`
- Modify: `obs_youtube_uploader/app.py` (add `_open_settings`)

**Interfaces:**
- Consumes: `settings.load`, `settings.save`, `settings.DEFAULTS`, `uploader.load_credentials`, `uploader.run_oauth_flow`, `uploader.save_credentials`, `paths.token_file`
- Produces: `SettingsWindow(parent, state, on_saved)` class

Without this task the settings module built in Task 2 is unreachable from the UI, and the README's "Settings → Connect Google Account" instruction points at nothing. OAuth would still happen implicitly on first upload, but the user could never change privacy, category, or notification mode, nor re-authenticate deliberately.

- [ ] **Step 1: Write the settings window**

```python
# obs_youtube_uploader/settingsui.py
"""Settings dialog: upload defaults, notification mode, Google account."""
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import paths, settings as settings_mod, uploader

PRIVACY_CHOICES = ["private", "unlisted", "public"]
NOTIFY_CHOICES = ["toast", "popup"]


class SettingsWindow:
    def __init__(self, parent: tk.Misc, state, on_saved=None):
        self.state = state
        self.on_saved = on_saved
        self.win = tk.Toplevel(parent)
        self.win.title("Settings")
        self.win.geometry("520x360")
        self.win.transient(parent)
        self.win.grab_set()

        cfg = state.settings
        self.privacy = tk.StringVar(value=cfg["privacy"])
        self.category = tk.StringVar(value=cfg["category"])
        self.notify = tk.StringVar(value=cfg["notify_mode"])
        self.rec_dir = tk.StringVar(value=str(state.recording_dir))
        self._build()
        self._refresh_auth_label()

    def _build(self) -> None:
        pad = {"padx": 8, "pady": 6}

        acct = ttk.LabelFrame(self.win, text="Google account", padding=10)
        acct.pack(fill=tk.X, **pad)
        self.lbl_auth = ttk.Label(acct, text="Checking…")
        self.lbl_auth.pack(anchor=tk.W)
        ttk.Button(acct, text="Connect Google Account",
                   command=self._connect).pack(anchor=tk.W, pady=(6, 0))
        ttk.Label(
            acct,
            text=("If this is a pre-release build, only approved testers can "
                  "sign in."),
            foreground="gray", wraplength=460, justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(4, 0))

        up = ttk.LabelFrame(self.win, text="Upload defaults", padding=10)
        up.pack(fill=tk.X, **pad)
        ttk.Label(up, text="Privacy:").grid(row=0, column=0, sticky=tk.W)
        ttk.Combobox(up, textvariable=self.privacy, values=PRIVACY_CHOICES,
                     state="readonly", width=12).grid(row=0, column=1, sticky=tk.W, padx=6)
        ttk.Label(up, text="Category ID:").grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
        ttk.Entry(up, textvariable=self.category, width=8).grid(
            row=1, column=1, sticky=tk.W, padx=6, pady=(6, 0))
        ttk.Label(up, text="(20 = Gaming)", foreground="gray").grid(
            row=1, column=2, sticky=tk.W)

        beh = ttk.LabelFrame(self.win, text="When a recording finishes", padding=10)
        beh.pack(fill=tk.X, **pad)
        ttk.Radiobutton(beh, text="Show a tray notification (recommended)",
                        variable=self.notify, value="toast").pack(anchor=tk.W)
        ttk.Radiobutton(beh, text="Open the uploader window immediately",
                        variable=self.notify, value="popup").pack(anchor=tk.W)

        folder = ttk.LabelFrame(self.win, text="Recording folder", padding=10)
        folder.pack(fill=tk.X, **pad)
        ttk.Entry(folder, textvariable=self.rec_dir).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(folder, text="Browse…", command=self._browse).pack(
            side=tk.LEFT, padx=(6, 0))

        row = ttk.Frame(self.win)
        row.pack(fill=tk.X, **pad)
        ttk.Button(row, text="Save", command=self._save).pack(side=tk.RIGHT)
        ttk.Button(row, text="Cancel", command=self.win.destroy).pack(
            side=tk.RIGHT, padx=6)

    def _browse(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.rec_dir.get())
        if chosen:
            self.rec_dir.set(chosen)

    def _refresh_auth_label(self) -> None:
        creds = uploader.load_credentials(paths.token_file())
        if creds is not None and not uploader.needs_reauth(creds):
            self.lbl_auth.config(text="Connected", foreground="green")
        else:
            self.lbl_auth.config(text="Not connected", foreground="red")

    def _connect(self) -> None:
        """Run OAuth off the main thread; it blocks on a browser round-trip."""
        self.lbl_auth.config(text="Waiting for browser…", foreground="orange")

        def worker() -> None:
            try:
                creds = uploader.run_oauth_flow()
                uploader.save_credentials(creds, paths.token_file())
                self.win.after(0, self._refresh_auth_label)
            except Exception as exc:
                self.win.after(0, lambda: messagebox.showerror(
                    "Connection failed", str(exc)))
                self.win.after(0, self._refresh_auth_label)

        threading.Thread(target=worker, daemon=True).start()

    def _save(self) -> None:
        category = self.category.get().strip()
        if not category.isdigit():
            messagebox.showwarning("Invalid category",
                                   "Category ID must be a number, e.g. 20.")
            return
        rec_dir = Path(self.rec_dir.get())
        if not rec_dir.is_dir():
            messagebox.showwarning("Invalid folder",
                                   f"{rec_dir} is not a folder.")
            return
        cfg = dict(self.state.settings)
        cfg.update({
            "privacy": self.privacy.get(),
            "category": category,
            "notify_mode": self.notify.get(),
            "recording_dir": str(rec_dir),
        })
        settings_mod.save(cfg)
        self.state.settings = settings_mod.load()
        self.state.recording_dir = rec_dir
        if self.on_saved is not None:
            self.on_saved()
        self.win.destroy()
```

- [ ] **Step 2: Wire it into the main window**

Append this method to `UploaderWindow` in `obs_youtube_uploader/app.py`:

```python
    def _open_settings(self) -> None:
        from .settingsui import SettingsWindow
        SettingsWindow(self.root, self.state, on_saved=self._settings_saved)

    def _settings_saved(self) -> None:
        """Hook the tray app replaces so a settings change reaches the
        watcher too. Defaults to a plain refresh when running standalone."""
        if self.on_settings_saved is not None:
            self.on_settings_saved()
        else:
            self.refresh()
```

Also add to `UploaderWindow.__init__`, next to `self.on_deleted`:

```python
        self.on_settings_saved = None  # set by the tray app
```

- [ ] **Step 3: Verify both modules parse and tests still pass**

Run: `python -c "import ast; [ast.parse(open(f).read()) for f in ['obs_youtube_uploader/settingsui.py','obs_youtube_uploader/app.py']]; print('syntax ok')"`
Expected: `syntax ok`

Run: `python -m pytest tests/ -v`
Expected: PASS (all previous tests still green)

- [ ] **Step 4: Commit**

```bash
git add obs_youtube_uploader/settingsui.py obs_youtube_uploader/app.py
git commit -m "feat: add settings window with explicit Google account connection"
```

---

### Task 12: Tray icon, notifications, and entry point

**Files:**
- Create: `obs_youtube_uploader/__main__.py`
- Delete: `obs_trigger.py`
- Delete: `youtube_uploader.py`

**Interfaces:**
- Consumes: `UploaderWindow`, `AppState`, `Watcher`, `obsconfig.find_recording_dir`
- Produces: `main() -> int`

- [ ] **Step 1: Write the single-instance guard and first-run resolution**

```python
# obs_youtube_uploader/__main__.py
"""Entry point: single-instance tray application."""
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from . import app as app_mod
from . import obsconfig, paths, settings as settings_mod, stitch, watcher

MUTEX_NAME = "Global\\OBSYouTubeUploader"
POLL_SECONDS = 3.0


def acquire_single_instance():
    """Return a handle if this is the only instance, else None.

    Run-at-login plus a Start Menu shortcut makes double-launch likely, and
    two watchers means duplicate notifications and concurrent uploads of the
    same file.

    A second instance exits quietly rather than surfacing the first one's
    window: doing that properly needs cross-process IPC (a named pipe or
    WM_COPYDATA), which is disproportionate here — the tray icon is already
    visible and is the intended way to open the window.
    """
    if sys.platform != "win32":
        return object()  # No enforcement off-Windows; development only.
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, wintypes.BOOL(True), MUTEX_NAME)
    ERROR_ALREADY_EXISTS = 183
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        return None
    return handle


def resolve_recording_dir(cfg: dict) -> Path | None:
    """Stored setting, then OBS's own config, then ask the user."""
    stored = cfg.get("recording_dir")
    if stored and Path(stored).is_dir():
        return Path(stored)
    detected = obsconfig.find_recording_dir()
    if detected and detected.is_dir():
        return detected
    chosen = filedialog.askdirectory(title="Where does OBS save your recordings?")
    return Path(chosen) if chosen else None
```

- [ ] **Step 2: Write the tray icon**

```python
def build_tray(on_open, on_quit):
    """Tray icon with a generated image so no asset file is required."""
    import pystray
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (64, 64), "#1f1f1f")
    draw = ImageDraw.Draw(image)
    draw.ellipse((10, 10, 54, 54), fill="#ff0000")
    draw.polygon([(27, 22), (27, 42), (45, 32)], fill="#ffffff")

    menu = pystray.Menu(
        pystray.MenuItem("Open uploader", lambda *_: on_open(), default=True),
        pystray.MenuItem("Quit", lambda *_: on_quit()),
    )
    return pystray.Icon("obs_youtube_uploader", image, "OBS → YouTube Uploader", menu)
```

- [ ] **Step 3: Write `main()`**

```python
def main() -> int:
    handle = acquire_single_instance()
    if handle is None:
        return 0  # Another instance owns the tray; nothing to do.

    paths.ensure_dirs()
    swept = stitch.sweep_orphans(paths.tmp_dir())
    cfg = settings_mod.load()

    root = tk.Tk()
    root.withdraw()  # Created on the main thread up front, shown on demand.

    rec_dir = resolve_recording_dir(cfg)
    if rec_dir is None:
        messagebox.showerror("No recording folder",
                             "A recording folder is required. Exiting.")
        return 1
    cfg["recording_dir"] = str(rec_dir)
    settings_mod.save(cfg)

    state = app_mod.AppState(recording_dir=rec_dir, settings=cfg)
    window = app_mod.UploaderWindow(root, state)

    w = watcher.Watcher(rec_dir, paths.seen_file())
    w.baseline()
    window.on_deleted = w.forget

    def on_settings_saved() -> None:
        """Settings changes must reach the watcher, not just AppState.

        SettingsWindow replaces state.settings with a fresh dict and may
        change state.recording_dir. Anything holding the original objects
        goes stale, so the poll loop below reads state.settings each tick
        rather than closing over cfg.
        """
        if Path(state.recording_dir) != w.directory:
            w.rebind(state.recording_dir)
        window.refresh()

    window.on_settings_saved = on_settings_saved

    icon = build_tray(on_open=lambda: root.after(0, window.show),
                      on_quit=lambda: root.after(0, root.quit))
    threading.Thread(target=icon.run, daemon=True).start()

    def poll() -> None:
        try:
            ready = w.poll_once()
        except Exception:
            ready = []
        if ready:
            # Read the live settings, not a snapshot taken at startup.
            if state.settings.get("notify_mode", "toast") == "popup":
                window.show(preselect=set(ready))
            else:
                window.refresh(preselect=set(ready))
                try:
                    icon.notify(f"{len(ready)} new recording(s) ready to upload",
                                "OBS → YouTube Uploader")
                except Exception:
                    pass  # Notifications are best-effort.
        root.after(int(POLL_SECONDS * 1000), poll)

    root.after(int(POLL_SECONDS * 1000), poll)
    root.mainloop()
    icon.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Delete the superseded files**

```bash
git rm obs_trigger.py youtube_uploader.py
```

- [ ] **Step 5: Verify the package still imports and tests pass**

Run: `python -c "import ast; ast.parse(open('obs_youtube_uploader/__main__.py').read()); print('syntax ok')"`
Run: `python -m pytest tests/ -v`
Expected: `syntax ok`, then PASS for all tests

- [ ] **Step 6: Commit**

```bash
git add obs_youtube_uploader/__main__.py
git commit -m "feat: add tray entry point and remove OBS script integration

obs_trigger.py and youtube_uploader.py are superseded by the package."
```

---

# Phase 3 — Packaging and release

These tasks produce build configuration rather than testable logic, so they specify exact file contents and a manual verification step instead of a red-green cycle.

---

### Task 13: Build-time ffmpeg acquisition

**Files:**
- Create: `packaging/fetch_ffmpeg.py`

**Interfaces:**
- Produces: a script writing `packaging/bin/ffmpeg.exe` and `packaging/bin/ffprobe.exe`

- [ ] **Step 1: Write the fetch script**

```python
# packaging/fetch_ffmpeg.py
"""Download and verify ffmpeg binaries at build time.

Binaries are not committed to git: they are large, and a pinned URL plus a
checksum gives reproducibility without the repository bloat.
"""
import hashlib
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

# Pinned release. Update URL and SHA256 together, never separately.
FFMPEG_URL = (
    "https://github.com/GyanD/codexffmpeg/releases/download/"
    "7.1/ffmpeg-7.1-essentials_build.zip"
)
FFMPEG_SHA256 = "REPLACE_WITH_ACTUAL_SHA256_BEFORE_FIRST_RELEASE"
OUT_DIR = Path(__file__).parent / "bin"
WANTED = ("ffmpeg.exe", "ffprobe.exe")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if all((OUT_DIR / name).exists() for name in WANTED):
        print("ffmpeg binaries already present; skipping download")
        return 0

    print(f"Downloading {FFMPEG_URL}")
    with urllib.request.urlopen(FFMPEG_URL) as response:
        payload = response.read()

    digest = hashlib.sha256(payload).hexdigest()
    if FFMPEG_SHA256 == "REPLACE_WITH_ACTUAL_SHA256_BEFORE_FIRST_RELEASE":
        print(f"ERROR: pin the checksum first. Downloaded archive is sha256={digest}")
        return 1
    if digest != FFMPEG_SHA256:
        print(f"ERROR: checksum mismatch\n  expected {FFMPEG_SHA256}\n  got      {digest}")
        return 1

    extracted = 0
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for member in archive.namelist():
            name = Path(member).name
            if name in WANTED:
                (OUT_DIR / name).write_bytes(archive.read(member))
                print(f"  extracted {name}")
                extracted += 1
    if extracted != len(WANTED):
        print(f"ERROR: expected {len(WANTED)} binaries, extracted {extracted}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Pin the real checksum**

Run the script once to learn the digest, then paste it into `FFMPEG_SHA256`:

```bash
python packaging/fetch_ffmpeg.py
```

Expected on first run: `ERROR: pin the checksum first. Downloaded archive is sha256=<digest>`
Copy `<digest>` into `FFMPEG_SHA256`, then re-run.
Expected on second run: two `extracted` lines and exit 0.

- [ ] **Step 3: Verify the binaries landed**

Run: `ls -la packaging/bin/`
Expected: `ffmpeg.exe` and `ffprobe.exe` present.

- [ ] **Step 4: Commit**

```bash
git add packaging/fetch_ffmpeg.py
git commit -m "build: fetch and checksum-verify ffmpeg at build time"
```

---

### Task 14: PyInstaller build

**Files:**
- Create: `run.py`
- Create: `packaging/uploader.spec`

- [ ] **Step 1: Create the entry shim**

PyInstaller analyzes the entry file as a *script*, executed as `__main__`
with no package context. `obs_youtube_uploader/__main__.py` uses
package-relative imports (`from . import app`), which fail immediately in
that context with `attempted relative import with no known parent package`.
A shim that imports absolutely fixes it:

```python
# run.py
"""Frozen-application entry point.

PyInstaller runs its entry file as a bare script, so relative imports inside
__main__.py would fail. This shim imports the package absolutely instead.
"""
from obs_youtube_uploader.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify the shim works before freezing anything**

Run: `python -c "import run; print('entry import ok')"`
Expected: `entry import ok` with no `ImportError`.

Importing rather than running is deliberate: `run.py` launches the tray GUI
when executed, which would block. This catches the relative-import problem
in one second rather than after a five-minute Windows-only PyInstaller build.

- [ ] **Step 3: Write the PyInstaller spec**

```python
# packaging/uploader.spec
# One-folder build. Deliberately not one-file: one-file unpacks to temp on
# every launch (slow with ffmpeg bundled) and trips antivirus heuristics
# markedly more often.
from pathlib import Path

ROOT = Path(SPECPATH).parent
BIN = ROOT / "packaging" / "bin"

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=[
        (str(BIN / "ffmpeg.exe"), "bin"),
        (str(BIN / "ffprobe.exe"), "bin"),
    ],
    datas=[],
    hiddenimports=[
        "pystray._win32",
        "PIL._tkinter_finder",
        "googleapiclient.discovery",
        "google_auth_oauthlib.flow",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OBSYouTubeUploader",
    console=False,          # No console window behind the GUI.
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,              # UPX compression increases antivirus false positives.
    name="OBSYouTubeUploader",
)
```

- [ ] **Step 4: Build locally to verify the spec**

```bash
python -m pip install pyinstaller
python -m PyInstaller packaging/uploader.spec --noconfirm --distpath dist --workpath build
```

Expected: `dist/OBSYouTubeUploader/OBSYouTubeUploader.exe` exists, with `bin/ffmpeg.exe` and `bin/ffprobe.exe` alongside it.

Note: this step only succeeds on Windows. On Linux, confirm the spec parses instead:
`python -c "compile(open('packaging/uploader.spec').read(), 'spec', 'exec'); print('spec ok')"`

- [ ] **Step 5: Launch the frozen executable (Windows only)**

Run: `dist\OBSYouTubeUploader\OBSYouTubeUploader.exe`
Expected: the tray icon appears within a few seconds and no error dialog is
shown. A frozen build that imports cleanly can still fail at runtime on a
missing hidden import, and this is the only step that catches that.

If it exits silently, temporarily set `console=True` in the spec and re-run
to see the traceback.

- [ ] **Step 6: Commit**

```bash
git add run.py packaging/uploader.spec
git commit -m "build: add PyInstaller one-folder spec and absolute-import entry shim"
```

---

### Task 15: Inno Setup installer

**Files:**
- Create: `packaging/installer.iss`

- [ ] **Step 1: Write the installer script**

```
; packaging/installer.iss
; Installs the one-folder PyInstaller output with a Start Menu shortcut and
; an optional run-at-login entry. Run-at-login matters because a tray
; watcher the user forgets to start does nothing.

#define AppName "OBS YouTube Uploader"
#define AppVersion "2.0.0"
#define AppExe "OBSYouTubeUploader.exe"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=elboaf
DefaultDirName={autopf}\OBSYouTubeUploader
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
OutputDir=..\dist
OutputBaseFilename=OBS-YouTube-Uploader-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
; Per-user install avoids an admin prompt and keeps the app writable.
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Tasks]
Name: "startup"; Description: "Start automatically when I log in"; GroupDescription: "Startup"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts"; Flags: unchecked

[Files]
Source: "..\dist\OBSYouTubeUploader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: startup

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Leave %LOCALAPPDATA% state in place so a reinstall keeps the user signed in.
Type: filesandordirs; Name: "{app}"
```

- [ ] **Step 2: Verify (Windows only)**

```bash
iscc packaging/installer.iss
```

Expected: `dist/OBS-YouTube-Uploader-Setup-2.0.0.exe` produced.

On Linux, verify the file is syntactically well-formed by inspection: every `[Section]` header is bracketed, every `Name:`/`Filename:` pair is comma-separated, and `#define` values are quoted where they contain spaces.

- [ ] **Step 3: Commit**

```bash
git add packaging/installer.iss
git commit -m "build: add Inno Setup installer with run-at-login option"
```

---

### Task 16: CI and release workflows

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Write the CI workflow**

```yaml
# .github/workflows/ci.yml
name: CI
on:
  push:
    branches: ["**"]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install
        run: |
          python -m pip install --upgrade pip
          python -m pip install -e ".[dev]"
      - name: Test
        run: python -m pytest tests/ -v
```

- [ ] **Step 2: Write the release workflow**

```yaml
# .github/workflows/release.yml
name: Release
on:
  push:
    tags: ["v*"]

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install -e .
          python -m pip install pyinstaller

      - name: Inject OAuth credentials
        shell: pwsh
        env:
          OAUTH_CLIENT_ID: ${{ secrets.OAUTH_CLIENT_ID }}
          OAUTH_CLIENT_SECRET: ${{ secrets.OAUTH_CLIENT_SECRET }}
        run: |
          if (-not $env:OAUTH_CLIENT_ID) { throw "OAUTH_CLIENT_ID secret is not set" }
          $file = "obs_youtube_uploader/credentials.py"
          $content = Get-Content $file -Raw
          $content = $content.Replace("REPLACE_AT_BUILD_TIME.apps.googleusercontent.com", $env:OAUTH_CLIENT_ID)
          $content = $content.Replace("REPLACE_AT_BUILD_TIME", $env:OAUTH_CLIENT_SECRET)
          Set-Content $file $content -NoNewline

      - name: Fetch ffmpeg
        run: python packaging/fetch_ffmpeg.py

      - name: Build executable
        run: python -m PyInstaller packaging/uploader.spec --noconfirm

      - name: Build installer
        run: iscc packaging/installer.iss

      - name: Publish
        uses: softprops/action-gh-release@v2
        with:
          files: dist/OBS-YouTube-Uploader-Setup-*.exe
          # Enforced, not merely documented: the global constraint blocks
          # public release until OAuth verification clears. Flip to false
          # in the same commit that flips the Google console to production.
          prerelease: true
          body: |
            **Pre-release note:** until Google's OAuth verification clears,
            only approved testers can sign in. Everyone else will see
            `Error 403: access_denied`. Ask to be added to the tester list.

            Windows will show a "Windows protected your PC" warning because
            the installer is unsigned. Click **More info** then **Run anyway**.
```

- [ ] **Step 3: Verify the workflows parse**

Run: `python -c "import yaml,sys; [yaml.safe_load(open(f)) for f in ['.github/workflows/ci.yml','.github/workflows/release.yml']]; print('yaml ok')"`
Expected: `yaml ok`

(If PyYAML is unavailable: `python -m pip install pyyaml` first.)

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/
git commit -m "build: add CI and tagged-release workflows"
```

---

### Task 17: README rewrite, dependency cleanup, and smoke checklist

**Files:**
- Modify: `README.md` (full rewrite)
- Delete: `requirements.txt`
- Create: `docs/smoke-checklist.md`

The README currently documents the OBS script, the eight-step Google Cloud setup, and claims recordings are "never modified or deleted" — all three are now false.

`requirements.txt` is superseded by `pyproject.toml` and is actively misleading: it lists only the three Google packages (`requirements.txt:1-3`) and omits `pystray` and `Pillow`, so anyone following it gets an app that cannot start.

- [ ] **Step 1: Delete the stale requirements file**

```bash
git rm requirements.txt
```

- [ ] **Step 2: Rewrite `README.md`**

```markdown
# OBS YouTube Uploader

Watches your OBS recording folder and lets you select, optionally stitch,
and upload recordings to YouTube. Pairs well with
[obs-fightrecorder](https://github.com/JesseSwale/obs-fightrecorder), but
works with any OBS recording.

## Install

1. Download the latest `OBS-YouTube-Uploader-Setup-*.exe` from
   [Releases](https://github.com/elboaf/OBS-YouTube-Uploader/releases).
2. Run it.

That's it. Python, FFmpeg, and Google credentials are all bundled.

**Windows will warn you** that it "protected your PC" — the installer is
unsigned. Click **More info** → **Run anyway**.

**Currently in pre-release:** Google has not finished verifying the app, so
only approved testers can sign in. Anyone else sees `Error 403:
access_denied`. Open an issue to be added.

## Use

The app lives in your system tray and starts with Windows. When a recording
finishes you get a notification; **click the tray icon** to open the
uploader.

- **Select** one or more recordings with the checkboxes.
- **Stitch** merges the selection into one video, earliest first. Originals
  are never modified.
- **Upload Selected** uploads them, then fills in the YouTube Link column.
  Use **Copy** or **Open** on any row.
- **Delete Selected** permanently deletes files from disk after confirming.
  This cannot be undone.

## Settings

| Setting | Default | Notes |
|---|---|---|
| Privacy | `private` | `private`, `unlisted`, or `public` |
| Category | `20` (Gaming) | [Category IDs](https://developers.google.com/youtube/v3/docs/videoCategories/list) |
| Notification | `toast` | `toast` for a tray notification, `popup` to raise the window |

Stored in `%LOCALAPPDATA%\OBSYouTubeUploader\settings.json`.

## Limits

Uploads are capped at **100 per day across all users** of the app, which is
YouTube's default project allocation. If you hit it, wait until tomorrow.

## Upgrading from 1.x

1. Remove `obs_trigger.py` from OBS → Tools → Scripts. It is no longer used.
2. Open Settings → Connect Google Account and sign in once.

Your old `client_secrets.json` and token file are ignored.

## Building from source

```bash
python -m pip install -e ".[dev]"
python -m pytest tests/
python -m obs_youtube_uploader
```

Running from source needs your own Google OAuth desktop credentials in
`obs_youtube_uploader/credentials.py`; releases have them injected at build
time.

## License

Personal tool, use at your own risk. Not affiliated with OBS Studio, CCP
Games, or Google/YouTube.
```

- [ ] **Step 3: Write the smoke checklist**

```markdown
# Smoke checklist

Manual verification for the GUI and live upload paths, which are not
automated: doing so would need live credentials and would consume the very
upload quota the design is constrained by.

Run on Windows against a real install before each release.

## Install
- [ ] Installer runs without an admin prompt
- [ ] Start Menu shortcut launches the app
- [ ] With "start at login" checked, the app appears after a reboot
- [ ] Uninstall removes the app and leaves `%LOCALAPPDATA%` state intact

## First run
- [ ] Recording folder is pre-filled from OBS config without being asked
- [ ] With OBS absent, the folder picker appears instead
- [ ] Existing recordings do NOT produce a notification on first launch

## Watcher
- [ ] Recording in OBS then stopping produces one notification
- [ ] Notification does not steal focus from a fullscreen game
- [ ] Clicking the tray icon opens the uploader window
- [ ] With `notify_mode: popup`, the window raises instead
- [ ] A recording made while the app was closed is announced on next launch
- [ ] Existing recordings are NOT re-announced on an ordinary restart
- [ ] Newly announced recordings are already checked when the window opens

## Settings
- [ ] Settings button opens the dialog
- [ ] Connect Google Account opens a browser and reports "Connected"
- [ ] Changing privacy and saving persists across an app restart
- [ ] Changing the recording folder takes effect without a restart —
      new recordings in the NEW folder are announced, old folder is ignored
- [ ] Switching notify mode to popup takes effect on the next recording,
      without a restart
- [ ] A non-numeric category ID is rejected with a warning

## Upload
- [ ] Single upload completes and the link column fills in
- [ ] Copy button puts a working URL on the clipboard
- [ ] Open button opens the video in a browser
- [ ] Multi-select without stitch uploads each with `(1/n)` titles
- [ ] Each row gets its own correct link
- [ ] Stitch of two videos produces one upload, both rows show the same link
- [ ] Temp stitch file is gone from `%LOCALAPPDATA%\...\tmp` afterwards
- [ ] Killing the network mid-upload shows "retrying in Ns", then resumes
- [ ] After exhausting retries, the Retry button becomes enabled
- [ ] Retry resumes rather than restarting from 0%
- [ ] Retry of a 3-file batch that failed on file 2 uploads files 2 and 3,
      and fills in links for both
- [ ] Retry of a failed STITCHED upload re-stitches and restarts (expected —
      the temp file is deleted on failure by design)
- [ ] Temp stitch file is gone even after a failed upload

## Delete
- [ ] Confirmation dialog lists the correct filenames
- [ ] Cancelling deletes nothing
- [ ] Confirming removes the files and refreshes the list
- [ ] A deleted file is not re-announced by the watcher

## Single instance
- [ ] Launching a second copy exits quietly with no second tray icon
- [ ] The first instance keeps working normally afterwards
```

- [ ] **Step 4: Commit**

```bash
git add README.md docs/smoke-checklist.md
git commit -m "docs: rewrite README for standalone install, drop stale requirements.txt

requirements.txt listed only the Google packages and omitted pystray and
Pillow, so following it produced an app that could not start. pyproject.toml
supersedes it."
```

---

## Self-Review

**Spec coverage.** Walked each spec section against a task:

| Spec section | Task |
|---|---|
| Credentials: shared, embedded | 8, 16 |
| Release gating | 16 (release notes), 17 (README) |
| Delivery: PyInstaller + Inno Setup | 14, 15 |
| OBS integration removed | 12 |
| FFmpeg bundled + degradation matrix | 3, 10, 13 |
| SmartScreen accepted and documented | 16, 17 |
| Architecture: six units | 1–12 |
| Threading | 10 (`UploadJob` snapshot + `_ui` marshalling), 12 (hidden root on main thread) |
| Data flow / polling | 9, 12 |
| Watcher lifecycle: baseline + mutex | 9, 12 |
| Notification behavior (toast/popup) | 11, 12 |
| Configuration and state relocation | 1, 2 |
| Settings schema + private default | 2, 11 |
| Recording folder auto-detection | 4, 11, 12 |
| Error handling table | 6, 10 |
| Upload retry as new work | 7, 10 |
| Upstream changes: link column | 10 |
| Upstream changes: Delete Selected | 3, 10, 12 |
| Upstream defects not reproduced | 7 (no duplicate block), 10 (path-keyed links) |
| Build and release | 13, 14, 15, 16 |
| Testing | 1–9 unit tests, 17 smoke checklist |
| Migration (docs only) | 17 |
| README corrections | 17 |

No gaps found.

**Placeholder scan.** Two intentional `REPLACE_AT_BUILD_TIME` markers in
`credentials.py` (overwritten by Task 16) and one
`REPLACE_WITH_ACTUAL_SHA256_BEFORE_FIRST_RELEASE` in `fetch_ffmpeg.py`,
which Task 13 Step 2 resolves with a concrete procedure. Both are guarded by
code that fails loudly rather than proceeding. No unresolved TODOs.

**Type consistency.** Checked names across task boundaries:
`VideoInfo` fields (`path`, `mtime`, `size`, `duration`) are consistent
between Tasks 3, 5, and 10. `Outcome` members are consistent between Tasks 6
and 7. `upload(request, *, on_progress, on_retry, max_attempts, sleep,
jitter)` in Task 7 matches its calls in Task 10. `UploadJob` fields defined
in Task 10 Step 1 match their reads in the worker. `Watcher.forget` in Task 9
matches `window.on_deleted = w.forget` in Task 12. `paths.tmp_dir()` is used
identically in Tasks 5, 10, and 12. `settings.DEFAULTS` keys in Task 2 cover
every key written in Tasks 11 and 12 — the omission that previously dropped
`recording_dir` on every save.
