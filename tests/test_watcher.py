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


def _break_save(monkeypatch):
    """Make every write through _save() fail as if the disk rejected it."""
    def _raise(*a, **kw):
        raise OSError("disk full")
    monkeypatch.setattr(watcher, "save_seen", _raise)


def test_baseline_survives_save_failure(tmp_path, monkeypatch, caplog):
    """The R17 resilience fix: an unwritable seen.json must not raise out of
    baseline(), and the in-memory seen-set must still reflect reality so the
    session behaves correctly even though nothing reached disk."""
    f = _write(tmp_path / "old.mkv", 10)
    w = watcher.Watcher(tmp_path, tmp_path / "seen.json")
    _break_save(monkeypatch)
    with caplog.at_level("WARNING"):
        w.baseline()  # must not raise
    assert str(f) in w.seen
    assert any("seen-set" in r.message for r in caplog.records)


def test_poll_once_survives_save_failure_and_still_reports_ready_files(tmp_path, monkeypatch):
    w = watcher.Watcher(tmp_path, tmp_path / "seen.json")
    w.baseline()
    f = _write(tmp_path / "new.mkv", 10)
    _break_save(monkeypatch)
    ready = _settle(w, f)
    assert [p.name for p in ready] == ["new.mkv"]
    assert str(f) in w.seen  # in-memory state still advanced despite the failed write


def test_rebind_survives_save_failure(tmp_path, monkeypatch):
    old = tmp_path / "old"
    new = tmp_path / "new"
    old.mkdir()
    new.mkdir()
    b = _write(new / "b.mkv", 10)
    w = watcher.Watcher(old, tmp_path / "seen.json")
    w.baseline()
    _break_save(monkeypatch)
    w.rebind(new)  # must not raise
    assert str(b) in w.seen
    assert w.directory == new


def test_forget_survives_save_failure(tmp_path, monkeypatch):
    f = _write(tmp_path / "a.mkv", 10)
    w = watcher.Watcher(tmp_path, tmp_path / "seen.json")
    w.baseline()
    _break_save(monkeypatch)
    w.forget(f)  # must not raise
    assert str(f) not in w.seen


def test_prune_survives_save_failure(tmp_path, monkeypatch):
    f = _write(tmp_path / "a.mkv", 10)
    w = watcher.Watcher(tmp_path, tmp_path / "seen.json")
    w.baseline()
    f.unlink()
    _break_save(monkeypatch)
    assert w.prune() == 1  # must not raise, and must still report the correct count
    assert str(f) not in w.seen


def test_load_seen_rejects_non_dict_json(tmp_path):
    p = tmp_path / "seen.json"
    p.write_text("[1, 2, 3]")
    assert watcher.load_seen(p) == {}


def test_load_seen_skips_a_malformed_per_key_entry(tmp_path):
    p = tmp_path / "seen.json"
    p.write_text(json.dumps({
        "good.mkv": {"size": 10, "mtime": 1.0},
        "bad.mkv": {"size": "not-a-number"},  # missing mtime, and unconvertible size
    }))
    seen = watcher.load_seen(p)
    assert seen.keys() == {"good.mkv"}
    assert seen["good.mkv"] == watcher.SeenEntry(size=10, mtime=1.0)


def test_rebind_to_nonexistent_directory_does_not_raise(tmp_path):
    w = watcher.Watcher(tmp_path, tmp_path / "seen.json")
    w.baseline()
    w.rebind(tmp_path / "nope")  # must not raise
    assert w.poll_once() == []


def test_file_deleted_then_recreated_at_same_path_is_reannounced(tmp_path):
    w = watcher.Watcher(tmp_path, tmp_path / "seen.json")
    w.baseline()
    f = tmp_path / "a.mkv"
    _write(f, 10)
    assert [p.name for p in _settle(w, f)] == ["a.mkv"]
    assert w.poll_once() == []  # confirmed settled
    f.unlink()
    assert w.poll_once() == []  # gone from disk, nothing to report
    _write(f, 10)
    # Force a distinct mtime: on some filesystems a fast delete+recreate in
    # the same test can land on an identical mtime, which would make this
    # assertion flaky for a reason unrelated to what it is testing.
    os.utime(f, (0, 0))
    assert [p.name for p in _settle(w, f)] == ["a.mkv"]
