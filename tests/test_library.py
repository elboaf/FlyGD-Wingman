import datetime
import os
import subprocess
from pathlib import Path

import pytest

from wingman import library


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


def test_stat_info_costs_no_subprocess(tmp_path):
    """The whole point of the split: drawing a row must not spawn ffprobe."""
    f = _touch(tmp_path / "a.mkv", size=2048, mtime=1000)

    def explode(*a, **kw):
        raise AssertionError("stat_info must not run a subprocess")

    original, subprocess.run = subprocess.run, explode
    try:
        info = library.stat_info(f)
    finally:
        subprocess.run = original

    assert info.size == 2048 and info.mtime == 1000
    assert info.duration is None and info.probed is False


def test_duration_str_shows_pending_while_unprobed(tmp_path):
    """An unprobed row must not read "?" -- that is the display for a probe
    that ran and failed, and the two must stay tellable apart on screen."""
    info = library.stat_info(_touch(tmp_path / "a.mkv"))
    assert info.duration_str == "…"


def test_duration_str_tells_no_verdict_apart_from_an_unreadable_file(tmp_path):
    """Uploader 5 and 10. probe() already separates "ffprobe ran and could
    not read this" from "ffprobe never reached a verdict" -- it has to, or
    one antivirus quarantine of ffprobe.exe would be cached under a
    (size, mtime) key that never changes and pin the row to "?" forever.

    The COLUMN did not make that distinction, and both rendered "?". On an
    install where ffprobe was never found at all -- packaging/bin is
    gitignored and fetched at build time, so a source run has none -- every
    row therefore accused its own recording of being unreadable, and the
    selection summary printed a confident "0:00:00" for a 108.8 MB file.

    Three states, and the two Nones are not the same None.
    """
    f = _touch(tmp_path / "a.mkv")
    unreadable = library.VideoInfo(
        path=f, mtime=0.0, size=1, duration=None, probed=True, answered=True
    )
    never_measured = library.VideoInfo(
        path=f, mtime=0.0, size=1, duration=None, probed=True, answered=False
    )
    assert unreadable.duration_str == "?"
    assert never_measured.duration_str == "—"
    assert unreadable.duration_str != never_measured.duration_str


def test_a_no_verdict_probe_is_what_produces_the_unmeasured_state(tmp_path):
    """Ties the flag to its one producer. probe() returns definitive=False
    with no ffprobe configured; that False is what rows.set_duration hands
    to `answered`, so this is the whole chain from a missing binary to the
    glyph."""
    f = _touch(tmp_path / "a.mkv")
    duration, definitive = library.probe(f, None)
    assert (duration, definitive) == (None, False)
    info = library.stat_info(f)
    info.duration, info.probed, info.answered = duration, True, definitive
    assert info.duration_str == "—"


def test_build_info_results_are_marked_probed(tmp_path):
    f = _touch(tmp_path / "a.mkv")
    assert library.build_info(f, None).probed is True


# --- probe(): definitive verdict vs. probe that never ran ----------------
# Both return a None duration, but only the first may be cached: the cache
# key is (size, mtime), which never changes again for a finished recording,
# so caching an environmental failure pins that file to "?" permanently and
# blocks its combat-log upload even after the cause is fixed.


def test_probe_reports_a_duration_as_definitive(tmp_path):
    f = _touch(tmp_path / "a.mkv")

    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout="125", stderr="")

    assert library.probe(f, "ffprobe", runner=fake_run) == (125.0, True)


def test_probe_reports_a_nonzero_exit_as_definitive(tmp_path):
    """ffprobe ran and said it cannot read this file. Worth remembering."""
    f = _touch(tmp_path / "a.mkv")

    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="bad")

    assert library.probe(f, "ffprobe", runner=fake_run) == (None, True)


def test_probe_reports_unparseable_output_as_definitive(tmp_path):
    f = _touch(tmp_path / "a.mkv")

    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout="N/A", stderr="")

    assert library.probe(f, "ffprobe", runner=fake_run) == (None, True)


def test_probe_reports_a_missing_binary_as_not_definitive(tmp_path):
    f = _touch(tmp_path / "a.mkv")
    assert library.probe(f, None) == (None, False)


def test_probe_reports_a_timeout_as_not_definitive(tmp_path):
    """A 15s timeout under disk load says nothing about the file. Caching
    it would pin a perfectly good recording to "?" forever."""
    f = _touch(tmp_path / "a.mkv")

    def fake_run(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 15)

    assert library.probe(f, "ffprobe", runner=fake_run) == (None, False)


def test_probe_reports_a_launch_failure_as_not_definitive(tmp_path):
    """The binary vanished after startup (antivirus quarantine). Must not
    be recorded as "this recording is unreadable"."""
    f = _touch(tmp_path / "a.mkv")

    def fake_run(cmd, **kw):
        raise OSError("No such file or directory")

    assert library.probe(f, "ffprobe", runner=fake_run) == (None, False)


def test_probe_duration_still_returns_just_the_duration(tmp_path):
    f = _touch(tmp_path / "a.mkv")

    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout="125", stderr="")

    assert library.probe_duration(f, "ffprobe", runner=fake_run) == 125.0


def test_duration_str_formats_minutes_and_seconds(tmp_path):
    f = _touch(tmp_path / "a.mkv")

    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout="125", stderr="")

    info = library.build_info(f, "ffprobe", runner=fake_run)
    assert info.duration_str == "2:05"


def test_duration_str_is_the_shared_format_and_not_a_second_copy_of_it(tmp_path):
    """It was a second copy, and it was the one with no hours field, so a
    two-hour recording rendered "127:07" in the Length column."""
    f = _touch(tmp_path / "a.mkv")

    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout="7627", stderr="")

    info = library.build_info(f, "ffprobe", runner=fake_run)
    assert info.duration_str == library.format_duration(7627)
    assert info.duration_str == "2:07:07"


def test_format_duration_omits_the_hour_only_when_there_is_none():
    assert library.format_duration(0) == "0:00"
    assert library.format_duration(5) == "0:05"
    assert library.format_duration(65) == "1:05"
    assert library.format_duration(1027) == "17:07"
    # The boundary in both directions: 59:59 keeps two fields, 1:00:00
    # gains the third rather than rolling minutes past 60.
    assert library.format_duration(3599) == "59:59"
    assert library.format_duration(3600) == "1:00:00"
    assert library.format_duration(360000) == "100:00:00"


def test_format_duration_truncates_rather_than_rounding():
    """ffprobe returns a float. A total that rounded up could print a
    second the recording does not contain, and the selection summary sums
    these before formatting."""
    assert library.format_duration(59.9) == "0:59"


def test_size_str_is_human_readable(tmp_path):
    f = _touch(tmp_path / "a.mkv", size=2048)
    assert library.build_info(f, None).size_str == "2.0 KB"


NOW = datetime.datetime(2026, 8, 21, 12, 0)  # noqa: DTZ001 - local wall-clock, matching format_date's own convention


def _ago(**delta):
    """An mtime that far before NOW."""
    return (NOW - datetime.timedelta(**delta)).timestamp()


@pytest.mark.parametrize(
    "delta,expected",
    [
        ({"seconds": 5}, "just now"),
        ({"seconds": 89}, "just now"),
        ({"seconds": 90}, "1m ago"),
        ({"minutes": 45}, "45m ago"),
        ({"minutes": 59}, "59m ago"),
        ({"hours": 1}, "1h ago"),
        ({"hours": 23}, "23h ago"),
        ({"hours": 25}, "yesterday"),
        ({"days": 2}, "2d ago"),
        ({"days": 6}, "6d ago"),
    ],
)
def test_format_date_is_relative_for_the_last_week(delta, expected):
    """The column answers "is this recent?", and precision degrades with age
    on purpose: minutes matter for this session's recording and are noise
    for last month's."""
    assert library.format_date(_ago(**delta), now=NOW) == expected


def test_format_date_falls_back_to_a_calendar_date_after_a_week():
    assert library.format_date(_ago(days=8), now=NOW) == "Aug 13"


def test_format_date_prefixes_the_year_only_outside_the_current_one():
    """The year is the least informative part for a recording made this
    year, and this is the tightest non-elastic column in the list."""
    older = datetime.datetime(2025, 11, 2, 22, 11).timestamp()  # noqa: DTZ001 - local wall-clock, matching format_date's own convention
    assert library.format_date(older, now=NOW) == "2025 Nov 02"


def test_format_date_prefers_recency_over_the_calendar_year():
    """Dec 31 23:59 viewed at Jan 1 00:01 is two minutes old, and saying so
    beats naming the year. This reverses the pre-relative rule deliberately:
    the calendar year now only decides the >= 7 day fallback."""
    mtime = datetime.datetime(2025, 12, 31, 23, 59).timestamp()  # noqa: DTZ001 - local wall-clock, matching format_date's own convention
    now = datetime.datetime(2026, 1, 1, 0, 1)  # noqa: DTZ001 - local wall-clock, matching format_date's own convention
    assert library.format_date(mtime, now=now) == "2m ago"


def test_format_date_does_not_render_a_negative_age():
    """A future mtime is real -- a clock correction, an archive, a file off
    a machine with a skewed clock -- and must not produce "-3h ago"."""
    future = (NOW + datetime.timedelta(hours=3)).timestamp()
    assert library.format_date(future, now=NOW) == "Aug 21"


def test_format_date_defaults_now_to_the_clock():
    """The default path is exercised for real; only the injected `now`
    branches above pin literal strings, so this cannot become a time bomb."""
    mtime = datetime.datetime.now().timestamp()  # noqa: DTZ005 - local wall-clock, matching format_date's own convention
    assert library.format_date(mtime) == library.format_date(
        mtime,
        now=datetime.datetime.now(),  # noqa: DTZ005 - local wall-clock, matching format_date's own convention
    )


def test_date_str_delegates_to_format_date(tmp_path):
    f = _touch(tmp_path / "a.mkv", mtime=1000)
    info = library.build_info(f, None)
    assert info.date_str == library.format_date(1000)


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
    _touch(tmp_path / "old.mkv", mtime=1000)
    disappeared = _touch(tmp_path / "disappeared.mkv", mtime=1500)
    _touch(tmp_path / "new.mkv", mtime=2000)

    original_stat = Path.stat

    # *args/**kwargs are load-bearing, not defensive: CPython 3.13's pathlib
    # calls self.stat(follow_symlinks=...) internally from is_dir()/exists(),
    # so a fake that takes only `self` raises TypeError there -- and pytest
    # then hits the same TypeError while formatting the traceback, taking
    # the whole run down with an INTERNALERROR rather than one failure.
    def stat_with_race(self, *args, **kwargs):
        if self == disappeared:
            raise FileNotFoundError(f"{self} deleted between iterdir and stat")
        return original_stat(self, *args, **kwargs)

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
