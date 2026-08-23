"""One writer per file prevents conflicting WRITES. It does nothing about a
reader observing a half-written file, and every one of these files is polled
by another process on a 2s or 10s timer."""
from pathlib import Path
import pytest
from obs_youtube_uploader import atomicio


def test_writes_the_content(tmp_path):
    target = tmp_path / "out.json"
    atomicio.write_atomic(target, '{"a": 1}')
    assert target.read_text(encoding="utf-8") == '{"a": 1}'


def test_overwrites_existing(tmp_path):
    target = tmp_path / "out.json"
    target.write_text("old")
    atomicio.write_atomic(target, "new")
    assert target.read_text() == "new"


def test_creates_parent_directories(tmp_path):
    target = tmp_path / "nested" / "deep" / "out.json"
    atomicio.write_atomic(target, "x")
    assert target.read_text() == "x"


def test_no_temp_files_are_left_behind(tmp_path):
    target = tmp_path / "out.json"
    atomicio.write_atomic(target, "x")
    assert [p.name for p in tmp_path.iterdir()] == ["out.json"]


def test_a_failed_write_leaves_the_old_content_intact(tmp_path, monkeypatch):
    """The point of temp-plus-rename: a reader either sees the whole old
    file or the whole new one, never a truncated file."""
    target = tmp_path / "out.json"
    target.write_text("good")

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(atomicio.os, "replace", boom)
    with pytest.raises(OSError):
        atomicio.write_atomic(target, "partial")
    assert target.read_text() == "good"
    assert [p.name for p in tmp_path.iterdir()] == ["out.json"]


def test_temp_file_is_on_the_same_directory(tmp_path, monkeypatch):
    """os.replace is only atomic within a filesystem. A temp in /tmp would
    silently degrade to a copy across a volume boundary."""
    seen = {}
    real = atomicio.tempfile.mkstemp

    def spy(**kwargs):
        seen.update(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(atomicio.tempfile, "mkstemp", spy)
    atomicio.write_atomic(tmp_path / "out.json", "x")
    assert Path(seen["dir"]) == tmp_path
