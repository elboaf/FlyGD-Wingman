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
