import json
import os
from pathlib import Path

from wingman import watcher


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
    watcher.save_seen(
        seen_path, {str(tmp_path / "ghost.mkv"): watcher.SeenEntry(1, 1.0)}
    )
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


def test_poll_once_survives_save_failure_and_still_reports_ready_files(
    tmp_path, monkeypatch
):
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
    p.write_text(
        json.dumps(
            {
                "good.mkv": {"size": 10, "mtime": 1.0},
                "bad.mkv": {
                    "size": "not-a-number"
                },  # missing mtime, and unconvertible size
            }
        )
    )
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


# --- Files the writer still has open -----------------------------------
#
# The bug these cover: OBS's muxer does not grow the file smoothly. On NTFS
# the size only advances when it flushes -- measured at 17-20s apart on the
# recording that produced this fix -- while poll_once needs just three quiet
# polls (9s at POLL_SECONDS=3.0) to call a file finished. Size AND mtime are
# byte-identical between flushes, so the seen-set's unchanged check did not
# suppress it either: every flush re-entered _pending and re-announced the
# same still-recording file, once per flush, for the length of the recording.


def _fake_probe(states):
    """is_closed seam driven by a name -> bool map, read at call time."""
    return lambda path: states.get(Path(path).name, True)


def test_file_still_held_open_by_the_writer_is_never_announced(tmp_path):
    """The reported bug: a recording in progress announced over and over.

    Size holds constant across far more polls than stable_polls here, which
    is exactly what a flush gap looks like from the watcher's side.
    """
    states = {"recording.mkv": False}
    w = watcher.Watcher(tmp_path, tmp_path / "seen.json", is_closed=_fake_probe(states))
    w.baseline()
    _write(tmp_path / "recording.mkv", 10)
    for _ in range(12):
        assert w.poll_once() == []


def test_file_is_announced_once_the_writer_closes_it(tmp_path):
    states = {"recording.mkv": False}
    w = watcher.Watcher(tmp_path, tmp_path / "seen.json", is_closed=_fake_probe(states))
    w.baseline()
    f = _write(tmp_path / "recording.mkv", 10)
    _settle(w, f)
    assert w.poll_once() == []
    states["recording.mkv"] = True  # OBS stopped; the handle is gone
    assert [p.name for p in w.poll_once()] == ["recording.mkv"]
    assert w.poll_once() == []  # and exactly once


def test_an_open_file_does_not_hide_a_finished_one(tmp_path):
    """A still-recording file must not suppress its neighbours: OBS writes
    the replay buffer and the recording into the same folder."""
    states = {"recording.mkv": False, "Fight 2026.mkv": True}
    w = watcher.Watcher(tmp_path, tmp_path / "seen.json", is_closed=_fake_probe(states))
    w.baseline()
    _write(tmp_path / "recording.mkv", 10)
    _write(tmp_path / "Fight 2026.mkv", 20)
    assert [p.name for p in _settle(w, None)] == ["Fight 2026.mkv"]


def test_probe_runs_only_on_files_that_have_settled(tmp_path):
    """One open per candidate per settle, not one per file per poll: the
    folder holds a back catalogue this would otherwise open on a
    three-second loop forever."""
    calls = []

    def counting(path):
        calls.append(Path(path).name)
        return True

    w = watcher.Watcher(tmp_path, tmp_path / "seen.json", is_closed=counting)
    w.baseline()
    _write(tmp_path / "old.mkv", 10)
    _settle(w, None)
    calls.clear()
    for _ in range(5):
        w.poll_once()  # nothing changed; nothing should be probed
    assert calls == []


# --- The Windows probe itself ------------------------------------------


def test_windows_probe_reports_open_when_the_share_is_violated():
    """ERROR_SHARING_VIOLATION is the whole signal: another process holds a
    handle, so a share-mode-0 open is refused. Measured against a live OBS
    recording, which returned exactly this while two finished files in the
    same folder opened cleanly."""
    assert (
        watcher.windows_file_is_closed("x.mkv", _create_file=lambda p: (False, 32))
        is False
    )


def test_windows_probe_reports_open_on_a_lock_violation():
    assert (
        watcher.windows_file_is_closed("x.mkv", _create_file=lambda p: (False, 33))
        is False
    )


def test_windows_probe_reports_closed_when_the_open_succeeds():
    assert (
        watcher.windows_file_is_closed("x.mkv", _create_file=lambda p: (True, 0))
        is True
    )


def test_windows_probe_fails_open_on_an_unrelated_error():
    """Fails open deliberately. A probe that cannot answer -- permissions on
    a mapped drive, an antivirus filter -- must not silently stop every
    notification the app makes. The worst case of guessing "closed" is the
    behaviour this fix replaced, which is annoying rather than silent; the
    same trade _save() makes with its swallowed OSError."""
    assert (
        watcher.windows_file_is_closed("x.mkv", _create_file=lambda p: (False, 5))
        is True
    )  # ERROR_ACCESS_DENIED


def test_default_probe_is_a_noop_off_windows(monkeypatch):
    monkeypatch.setattr(watcher.sys, "platform", "linux")
    assert watcher.file_is_closed("/nonexistent/whatever.mkv") is True


def _poll_a_flushing_writer(w, f, polls=30, flush_every=6):
    """Drive *w* over a writer that flushes slower than the settle window.

    A constant size does NOT reproduce the defect: the first announcement
    puts the file in the seen-set, and an unchanged size and mtime are
    suppressed there forever after. The repeat needs the size to keep
    CHANGING -- which is precisely what a flush is -- so each one re-enters
    _pending and settles again. Anything that reproduces this bug has to
    flush; measured cadence on the recording that prompted the fix was one
    flush per 17-20s against a 9s settle.
    """
    announced = 0
    for poll in range(polls):
        if poll % flush_every == 0:
            _write(f, 100 * (poll + 1))
        announced += len(w.poll_once())
    return announced


def test_a_flushing_writer_is_announced_once_per_flush_without_the_probe(tmp_path):
    """Executable documentation of the defect, not a wish: this is what the
    watcher did before the handle probe, and it is why a bigger
    stable_polls could not have fixed it -- the flush gap is unbounded, so
    any threshold below it still settles."""
    w = watcher.Watcher(
        tmp_path, tmp_path / "seen.json", is_closed=lambda p: True
    )  # the pre-fix contract: a quiet size is taken as proof
    w.baseline()
    assert _poll_a_flushing_writer(w, tmp_path / "recording.mkv") > 1


def test_a_flushing_writer_is_not_announced_at_all_while_it_is_open(tmp_path):
    """The fix, against the same writer. Verified end to end on Windows
    against a real held handle: 5 announcements before, 0 after, and
    exactly 1 on the first poll once the handle closed."""
    states = {"recording.mkv": False}
    w = watcher.Watcher(tmp_path, tmp_path / "seen.json", is_closed=_fake_probe(states))
    w.baseline()
    f = tmp_path / "recording.mkv"
    assert _poll_a_flushing_writer(w, f) == 0
    states["recording.mkv"] = True  # OBS stopped
    assert [p.name for p in w.poll_once()] == ["recording.mkv"]


# --- rename ----------------------------------------------------------------
# THE regression this method exists to prevent: a renamed recording is the
# same file, and the seen-set is keyed by path. Without the migration the
# next poll finds a path it has never seen, announces it as a finished
# recording and preselects it -- days after the rename, reading as a bug
# about OBS rather than about the rename.


def test_rename_moves_the_seen_entry(tmp_path):
    seen_path = tmp_path / "seen.json"
    old = tmp_path / "a.mkv"
    old.write_bytes(b"x" * 10)
    w = watcher.Watcher(tmp_path, seen_path)
    w.baseline()
    new = tmp_path / "b.mkv"
    old.rename(new)
    w.rename(old, new)
    assert str(old) not in w.seen
    assert str(new) in w.seen
    assert str(new) in watcher.load_seen(seen_path)


def test_a_renamed_recording_is_not_announced_as_new(tmp_path):
    """The whole point. poll_once must stay silent about a file that has
    only changed its name."""
    seen_path = tmp_path / "seen.json"
    old = tmp_path / "a.mkv"
    old.write_bytes(b"x" * 10)
    w = watcher.Watcher(tmp_path, seen_path, stable_polls=1)
    w.baseline()
    new = tmp_path / "b.mkv"
    old.rename(new)
    w.rename(old, new)
    assert w.poll_once() == []


def test_rename_without_the_migration_would_announce_it(tmp_path):
    """The control for the test above: same steps, no rename() call. If
    this ever stops announcing, the test above proves nothing."""
    seen_path = tmp_path / "seen.json"
    old = tmp_path / "a.mkv"
    old.write_bytes(b"x" * 10)
    w = watcher.Watcher(tmp_path, seen_path, stable_polls=1)
    w.baseline()
    new = tmp_path / "b.mkv"
    old.rename(new)
    assert w.poll_once() == [new]


def test_rename_carries_a_pending_entry(tmp_path):
    """A file part-way through its settle must not have its stability
    count reset by a rename, or it waits out another full settle."""
    seen_path = tmp_path / "seen.json"
    old = tmp_path / "a.mkv"
    old.write_bytes(b"x" * 10)
    w = watcher.Watcher(tmp_path, seen_path, stable_polls=3)
    w.poll_once()
    assert str(old) in w._pending
    new = tmp_path / "b.mkv"
    old.rename(new)
    w.rename(old, new)
    assert str(old) not in w._pending
    assert str(new) in w._pending


def test_rename_of_an_unseen_path_does_not_invent_an_entry(tmp_path):
    """Renaming a recording the watcher has never seen must not add one --
    that would suppress the announcement of a genuinely new file."""
    seen_path = tmp_path / "seen.json"
    w = watcher.Watcher(tmp_path, seen_path)
    w.rename(tmp_path / "a.mkv", tmp_path / "b.mkv")
    assert w.seen == {}
