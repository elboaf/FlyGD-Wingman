"""One writer per file prevents conflicting WRITES. It does nothing about a
reader observing a half-written file, and every one of these files is polled
by another process on a 2s or 10s timer."""
import os
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


def test_content_is_flushed_to_disk_before_the_rename(tmp_path, monkeypatch):
    """Without fsync the rename can be visible while the content is still
    only in the page cache. No existing test would catch its removal."""
    synced = []
    monkeypatch.setattr(atomicio.os, "fsync", lambda fd: synced.append(fd))
    atomicio.write_atomic(tmp_path / "out.json", "x")
    assert synced


def test_a_locked_destination_is_retried_then_succeeds(tmp_path):
    """A Windows reader holding the target open raises PermissionError from
    os.replace. The reads are brief, so retrying clears it."""
    target = tmp_path / "out.json"
    target.write_text("old")
    calls = []
    real = atomicio.os.replace

    def flaky(src, dst):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError("sharing violation")
        return real(src, dst)

    atomicio.os.replace = flaky
    try:
        atomicio.write_atomic(target, "new", sleep=lambda _s: None)
    finally:
        atomicio.os.replace = real
    assert target.read_text() == "new"
    assert len(calls) == 3


def test_a_permanently_locked_destination_raises_and_leaves_no_debris(tmp_path):
    """Retrying forever would hang the save; giving up must still leave the
    old file intact and no .tmp behind."""
    target = tmp_path / "out.json"
    target.write_text("old")
    real = atomicio.os.replace

    def always(src, dst):
        raise PermissionError("sharing violation")

    atomicio.os.replace = always
    try:
        with pytest.raises(PermissionError):
            atomicio.write_atomic(target, "new", attempts=3,
                                  sleep=lambda _s: None)
    finally:
        atomicio.os.replace = real
    assert target.read_text() == "old"
    assert [p.name for p in tmp_path.iterdir()] == ["out.json"]


def test_copy_atomic_writes_bytes(tmp_path):
    source = tmp_path / "src.dat"
    source.write_bytes(b"\x00\x01\x02payload")
    target = tmp_path / "dst.dat"
    atomicio.copy_atomic(source, target)
    assert target.read_bytes() == b"\x00\x01\x02payload"


def test_copy_atomic_overwrites_existing(tmp_path):
    source = tmp_path / "src.dat"
    source.write_bytes(b"new")
    target = tmp_path / "dst.dat"
    target.write_bytes(b"old")
    atomicio.copy_atomic(source, target)
    assert target.read_bytes() == b"new"


def test_copy_atomic_creates_parent_directories(tmp_path):
    source = tmp_path / "src.dat"
    source.write_bytes(b"x")
    target = tmp_path / "nested" / "deep" / "dst.dat"
    atomicio.copy_atomic(source, target)
    assert target.read_bytes() == b"x"


def test_copy_atomic_leaves_target_intact_when_source_is_missing(tmp_path):
    target = tmp_path / "dst.dat"
    target.write_bytes(b"original")
    with pytest.raises(OSError):
        atomicio.copy_atomic(tmp_path / "absent.dat", target)
    assert target.read_bytes() == b"original"


def test_copy_atomic_leaves_no_temp_files_behind(tmp_path):
    target = tmp_path / "dst.dat"
    target.write_bytes(b"original")
    with pytest.raises(OSError):
        atomicio.copy_atomic(tmp_path / "absent.dat", target)
    assert [p.name for p in tmp_path.iterdir()] == ["dst.dat"]


def test_copy_atomic_retries_a_locked_destination(tmp_path):
    """Windows raises PermissionError from os.replace when the destination
    is held open without FILE_SHARE_DELETE. EVE holds core_*.dat open."""
    source = tmp_path / "src.dat"
    source.write_bytes(b"x")
    target = tmp_path / "dst.dat"
    slept = []
    calls = []
    real_replace = os.replace

    def flaky(tmp_name, dest):
        calls.append(dest)
        if len(calls) < 3:
            raise PermissionError(32, "in use")
        real_replace(tmp_name, dest)

    monkey = pytest.MonkeyPatch()
    monkey.setattr(atomicio.os, "replace", flaky)
    try:
        atomicio.copy_atomic(source, target, sleep=slept.append)
    finally:
        monkey.undo()
    assert target.read_bytes() == b"x"
    assert len(calls) == 3 and len(slept) == 2


def test_copy_atomic_gives_up_after_the_attempt_budget(tmp_path):
    source = tmp_path / "src.dat"
    source.write_bytes(b"x")
    target = tmp_path / "dst.dat"
    target.write_bytes(b"original")

    def always_locked(tmp_name, dest):
        raise PermissionError(32, "in use")

    monkey = pytest.MonkeyPatch()
    monkey.setattr(atomicio.os, "replace", always_locked)
    try:
        with pytest.raises(PermissionError):
            atomicio.copy_atomic(source, target, attempts=3, sleep=lambda _: None)
    finally:
        monkey.undo()
    assert target.read_bytes() == b"original"
    assert [p.name for p in tmp_path.iterdir()] == ["dst.dat", "src.dat"]
