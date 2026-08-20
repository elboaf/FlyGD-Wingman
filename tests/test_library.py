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
    """Race condition: file gone by stat() time must be skipped, not crash discover()."""
    old = _touch(tmp_path / "old.mkv", mtime=1000)
    disappeared = _touch(tmp_path / "disappeared.mkv", mtime=1500)
    new = _touch(tmp_path / "new.mkv", mtime=2000)

    original_stat = Path.stat

    def stat_with_race(self):
        if self == disappeared:
            raise FileNotFoundError(f"{self} deleted between iterdir and stat")
        return original_stat(self)

    monkeypatch.setattr(Path, "stat", stat_with_race)
    found = [p.name for p in library.discover(tmp_path)]
    # Should return old and new in mtime order, skipping disappeared
    assert found == ["new.mkv", "old.mkv"]


def test_format_size_zero_bytes():
    assert library.format_size(0) == "0.0 B"


def test_format_size_exactly_1024_rolls_over_to_next_unit():
    assert library.format_size(1024) == "1.0 KB"


def test_format_size_very_large_value_falls_through_to_tb():
    """No PB unit exists past GB, so anything >=1024 TB still prints as TB
    with a number over 1024 -- cosmetic, but the fallthrough must not raise
    or truncate silently."""
    assert library.format_size(1024**5) == "1024.0 TB"


def test_probe_duration_returns_none_on_success_with_empty_stdout(tmp_path):
    f = _touch(tmp_path / "a.mkv")

    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    assert library.probe_duration(f, "ffprobe", runner=fake_run) is None


def test_probe_duration_returns_none_on_non_numeric_stdout(tmp_path):
    f = _touch(tmp_path / "a.mkv")

    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout="N/A\n", stderr="")

    assert library.probe_duration(f, "ffprobe", runner=fake_run) is None


def test_build_info_propagates_stat_error(tmp_path):
    """build_info() does not guard path.stat(); a missing file must raise
    rather than silently returning bogus info."""
    missing = tmp_path / "gone.mkv"
    with pytest.raises(OSError):
        library.build_info(missing, None)


def test_delete_empty_list_is_a_noop():
    assert library.delete([]) == (0, [])


def test_discover_orders_deterministically_when_mtimes_tie(tmp_path):
    """Python's sort is stable, so files sharing an mtime keep a consistent
    relative order rather than shuffling between calls."""
    _touch(tmp_path / "a.mkv", mtime=1000)
    _touch(tmp_path / "b.mkv", mtime=1000)
    first = [p.name for p in library.discover(tmp_path)]
    second = [p.name for p in library.discover(tmp_path)]
    assert set(first) == {"a.mkv", "b.mkv"}
    assert first == second
