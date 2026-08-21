import datetime
import os
from pathlib import Path

import pytest

from obs_youtube_uploader import combatlog

UTC = datetime.timezone.utc

# Real logs are CRLF. A \n-only fixture would not catch a parser that leaves
# a trailing \r on the character name.
HEADER = (
    "------------------------------------------------------------\r\n"
    "  Gamelog\r\n"
    "  Listener: Miguel Aurgnet\r\n"
    "  Session Started: 2026.08.20 20:42:50\r\n"
    "------------------------------------------------------------\r\n"
    "[ 2026.08.20 20:42:52 ] (hint) Attempting to join a channel\r\n"
)


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_bytes(text.encode("utf-8"))
    return p


def test_parses_listener_and_session_start(tmp_path):
    h = combatlog.parse_header(_write(tmp_path, "a.txt", HEADER))
    assert h is not None
    assert h.listener == "Miguel Aurgnet"
    assert h.session_start == datetime.datetime(2026, 8, 20, 20, 42, 50, tzinfo=UTC)


def test_session_start_is_timezone_aware_utc(tmp_path):
    h = combatlog.parse_header(_write(tmp_path, "a.txt", HEADER))
    assert h.session_start.tzinfo is not None
    assert h.session_start.utcoffset() == datetime.timedelta(0)


def test_listener_has_no_trailing_carriage_return(tmp_path):
    h = combatlog.parse_header(_write(tmp_path, "a.txt", HEADER))
    assert "\r" not in h.listener
    assert not h.listener.endswith(" ")


def test_returns_none_without_listener(tmp_path):
    """47% of a real folder is header-only stubs with no character."""
    stub = (
        "------------------------------------------------------------\r\n"
        "  Gamelog\r\n"
        "  Session Started: 2026.08.20 21:46:48\r\n"
        "------------------------------------------------------------\r\n"
    )
    assert combatlog.parse_header(_write(tmp_path, "a.txt", stub)) is None


def test_returns_none_without_session_start(tmp_path):
    text = "  Gamelog\r\n  Listener: Someone\r\n"
    assert combatlog.parse_header(_write(tmp_path, "a.txt", text)) is None


def test_returns_none_on_malformed_timestamp(tmp_path):
    text = HEADER.replace("2026.08.20 20:42:50", "not-a-date")
    assert combatlog.parse_header(_write(tmp_path, "a.txt", text)) is None


def test_returns_none_on_empty_file(tmp_path):
    assert combatlog.parse_header(_write(tmp_path, "a.txt", "")) is None


def test_returns_none_on_missing_file(tmp_path):
    assert combatlog.parse_header(tmp_path / "nope.txt") is None


def test_tolerates_undecodable_bytes(tmp_path):
    """errors='replace': a stray byte in a chat line must not abort a scan."""
    p = tmp_path / "a.txt"
    p.write_bytes(HEADER.encode("utf-8") + b"[ 2026.08.20 20:43:00 ] \xff\xfe junk\r\n")
    h = combatlog.parse_header(p)
    assert h is not None and h.listener == "Miguel Aurgnet"


def test_stops_reading_after_header(tmp_path):
    """A 1.6MB log must not be read in full just to get its header."""
    big = HEADER + ("[ 2026.08.20 20:44:00 ] (combat) filler\r\n" * 50000)
    h = combatlog.parse_header(_write(tmp_path, "a.txt", big))
    assert h is not None and h.listener == "Miguel Aurgnet"


def test_finds_gamelogs_under_documents(tmp_path):
    d = tmp_path / "Documents" / "EVE" / "logs" / "Gamelogs"
    d.mkdir(parents=True)
    assert combatlog.find_gamelogs_dir(tmp_path) == d


def test_finds_gamelogs_under_onedrive_documents(tmp_path):
    """Redirected Documents folders are common and would otherwise present
    as 'no logs found'."""
    d = tmp_path / "OneDrive" / "Documents" / "EVE" / "logs" / "Gamelogs"
    d.mkdir(parents=True)
    assert combatlog.find_gamelogs_dir(tmp_path) == d


def test_plain_documents_wins_when_both_exist(tmp_path):
    plain = tmp_path / "Documents" / "EVE" / "logs" / "Gamelogs"
    onedrive = tmp_path / "OneDrive" / "Documents" / "EVE" / "logs" / "Gamelogs"
    plain.mkdir(parents=True)
    onedrive.mkdir(parents=True)
    assert combatlog.find_gamelogs_dir(tmp_path) == plain


def test_returns_none_when_absent(tmp_path):
    assert combatlog.find_gamelogs_dir(tmp_path) is None


def test_ignores_a_file_named_gamelogs(tmp_path):
    d = tmp_path / "Documents" / "EVE" / "logs"
    d.mkdir(parents=True)
    (d / "Gamelogs").write_text("not a directory")
    assert combatlog.find_gamelogs_dir(tmp_path) is None


def _log(tmp_path, name, listener, started, mtime_epoch, body_lines=1):
    """Write a gamelog whose filename encodes its session start, as EVE does."""
    text = (
        "------------------------------------------------------------\r\n"
        "  Gamelog\r\n"
        f"  Listener: {listener}\r\n"
        f"  Session Started: {started}\r\n"
        "------------------------------------------------------------\r\n"
        + "[ 2026.08.20 20:42:52 ] (combat) hit\r\n" * body_lines
    )
    p = tmp_path / name
    p.write_bytes(text.encode("utf-8"))
    os.utime(p, (mtime_epoch, mtime_epoch))
    return p


def _utc(y, mo, d, h, mi, s=0):
    return datetime.datetime(y, mo, d, h, mi, s, tzinfo=UTC)


def _epoch(dt):
    return dt.timestamp()


def test_rejects_naive_datetime(tmp_path):
    """The whole point of the UTC-only interface: a naive datetime is the
    bug this prevents, so it must not be silently accepted."""
    with pytest.raises(ValueError):
        combatlog.select_logs(tmp_path, datetime.datetime(2026, 8, 20, 20, 0),
                              _utc(2026, 8, 20, 21, 0))


def test_rejects_non_utc_datetime(tmp_path):
    other = datetime.timezone(datetime.timedelta(hours=-4))
    with pytest.raises(ValueError):
        combatlog.select_logs(tmp_path, datetime.datetime(2026, 8, 20, 16, 0, tzinfo=other),
                              _utc(2026, 8, 20, 21, 0))


def test_selects_a_log_overlapping_the_window(tmp_path):
    _log(tmp_path, "20260820_204250_1.txt", "Pilot A",
         "2026.08.20 20:42:50", _epoch(_utc(2026, 8, 20, 21, 55)))
    sel = combatlog.select_logs(tmp_path, _utc(2026, 8, 20, 21, 0), _utc(2026, 8, 20, 21, 30))
    assert [s.listener for s in sel.logs] == ["Pilot A"]


def test_reversed_bounds_are_swapped(tmp_path):
    """select_logs swaps the bounds when end precedes start.

    That swap is real behaviour with no coverage: without it a caller who
    passed the window backwards would get an empty selection and be told
    "no logs overlap that window", which reads as a data problem rather
    than a caller bug.
    """
    _log(tmp_path, "20260820_204250_1.txt", "Pilot A",
         "2026.08.20 20:42:50", _epoch(_utc(2026, 8, 20, 21, 55)))
    sel = combatlog.select_logs(tmp_path, _utc(2026, 8, 20, 21, 30),
                                _utc(2026, 8, 20, 21, 0))
    assert [s.listener for s in sel.logs] == ["Pilot A"]


def test_skips_log_that_ended_before_the_window(tmp_path):
    """The predicate that does the real work: a log starting long ago still
    satisfies start <= window_end, so only last-write excludes it."""
    _log(tmp_path, "20260819_100000_1.txt", "Old Pilot",
         "2026.08.19 10:00:00", _epoch(_utc(2026, 8, 19, 11, 0)))
    sel = combatlog.select_logs(tmp_path, _utc(2026, 8, 20, 21, 0), _utc(2026, 8, 20, 21, 30))
    assert sel.logs == []


def test_skips_log_that_started_after_the_window(tmp_path):
    _log(tmp_path, "20260821_100000_1.txt", "Future Pilot",
         "2026.08.21 10:00:00", _epoch(_utc(2026, 8, 21, 11, 0)))
    sel = combatlog.select_logs(tmp_path, _utc(2026, 8, 20, 21, 0), _utc(2026, 8, 20, 21, 30))
    assert sel.logs == []


def test_skips_listenerless_stub_even_when_it_overlaps(tmp_path):
    p = tmp_path / "20260820_210000.txt"
    p.write_bytes(
        b"------------------------------------------------------------\r\n"
        b"  Gamelog\r\n"
        b"  Session Started: 2026.08.20 21:00:00\r\n"
        b"------------------------------------------------------------\r\n"
    )
    os.utime(p, (_epoch(_utc(2026, 8, 20, 21, 10)),) * 2)
    sel = combatlog.select_logs(tmp_path, _utc(2026, 8, 20, 21, 0), _utc(2026, 8, 20, 21, 30))
    assert sel.logs == []


def test_padding_pulls_in_a_log_just_outside_the_window(tmp_path):
    """WINDOW_PADDING is 5 minutes each side."""
    _log(tmp_path, "20260820_205600_1.txt", "Edge Pilot",
         "2026.08.20 20:56:00", _epoch(_utc(2026, 8, 20, 20, 58)))
    sel = combatlog.select_logs(tmp_path, _utc(2026, 8, 20, 21, 0), _utc(2026, 8, 20, 21, 30))
    assert [s.listener for s in sel.logs] == ["Edge Pilot"]


def test_unparseable_filename_still_reads_the_header(tmp_path):
    """Degrade to the reference's behaviour rather than silently skipping."""
    _log(tmp_path, "weird-name.txt", "Odd Pilot",
         "2026.08.20 21:05:00", _epoch(_utc(2026, 8, 20, 21, 10)))
    sel = combatlog.select_logs(tmp_path, _utc(2026, 8, 20, 21, 0), _utc(2026, 8, 20, 21, 30))
    assert [s.listener for s in sel.logs] == ["Odd Pilot"]


def test_caps_at_max_files_and_reports_dropped(tmp_path):
    for i in range(5):
        _log(tmp_path, f"20260820_2100{i:02d}_{i}.txt", f"Pilot {i}",
             "2026.08.20 21:00:00", _epoch(_utc(2026, 8, 20, 21, 10 + i)))
    sel = combatlog.select_logs(tmp_path, _utc(2026, 8, 20, 21, 0),
                                _utc(2026, 8, 20, 21, 30), max_files=3)
    assert len(sel.logs) == 3
    assert sel.dropped == 2


def test_cap_keeps_the_newest_by_last_write(tmp_path):
    for i in range(4):
        _log(tmp_path, f"20260820_2100{i:02d}_{i}.txt", f"Pilot {i}",
             "2026.08.20 21:00:00", _epoch(_utc(2026, 8, 20, 21, 10 + i)))
    sel = combatlog.select_logs(tmp_path, _utc(2026, 8, 20, 21, 0),
                                _utc(2026, 8, 20, 21, 30), max_files=2)
    assert sorted(s.listener for s in sel.logs) == ["Pilot 2", "Pilot 3"]


def test_missing_directory_yields_nothing(tmp_path):
    sel = combatlog.select_logs(tmp_path / "nope", _utc(2026, 8, 20, 21, 0),
                                _utc(2026, 8, 20, 21, 30))
    assert sel.logs == [] and sel.dropped == 0


def test_stat_guard_still_excludes_a_log_that_would_be_excluded_anyway(tmp_path):
    """MAX_SESSION_SPAN skips stat() for a filename this far before the
    window, but the log's mtime is also long before the window, so the
    existing last-write predicate would have excluded it regardless --
    the guard changes performance, not the result."""
    _log(tmp_path, "20260601_100000_1.txt", "Ancient Pilot",
         "2026.06.01 10:00:00", _epoch(_utc(2026, 6, 1, 11, 0)))
    sel = combatlog.select_logs(tmp_path, _utc(2026, 8, 20, 21, 0), _utc(2026, 8, 20, 21, 30))
    assert sel.logs == []


def test_session_just_inside_the_guard_boundary_is_still_selected(tmp_path):
    """A session almost MAX_SESSION_SPAN old, still being written during the
    window, must not be dropped by the guard -- this is the off-by-one that
    would silently drop a real (if implausibly long-running) log."""
    _log(tmp_path, "20260721_205600_1.txt", "Marathon Pilot",
         "2026.07.21 20:56:00", _epoch(_utc(2026, 8, 20, 21, 10)))
    sel = combatlog.select_logs(tmp_path, _utc(2026, 8, 20, 21, 0), _utc(2026, 8, 20, 21, 30))
    assert [s.listener for s in sel.logs] == ["Marathon Pilot"]


import json
import zipfile


def _selection(tmp_path, count=2):
    logs = []
    for i in range(count):
        p = _log(tmp_path, f"20260820_2100{i:02d}_{i}.txt", f"Pilot {i}",
                 "2026.08.20 21:00:00", _epoch(_utc(2026, 8, 20, 21, 10 + i)))
        logs.append(combatlog.SelectedLog(
            path=p, listener=f"Pilot {i}",
            span_start=_utc(2026, 8, 20, 21, 0), span_end=_utc(2026, 8, 20, 21, 10 + i)))
    return combatlog.Selection(logs=logs, dropped=0)


def test_archive_contains_every_selected_log(tmp_path):
    sel = _selection(tmp_path)
    out = tmp_path / "out.zip"
    combatlog.build_archive(sel, out, _utc(2026, 8, 20, 21, 0), _utc(2026, 8, 20, 21, 30))
    with zipfile.ZipFile(out) as z:
        names = set(z.namelist())
    for log in sel.logs:
        assert log.path.name in names


def test_archive_contains_a_manifest(tmp_path):
    sel = _selection(tmp_path)
    out = tmp_path / "out.zip"
    combatlog.build_archive(sel, out, _utc(2026, 8, 20, 21, 0), _utc(2026, 8, 20, 21, 30))
    with zipfile.ZipFile(out) as z:
        manifest = json.loads(z.read(combatlog.MANIFEST_NAME))
    assert manifest["characters"] == ["Pilot 0", "Pilot 1"]
    assert manifest["file_count"] == 2
    assert manifest["dropped"] == 0
    assert manifest["window_start"].startswith("2026-08-20T21:00:00")


def test_manifest_records_dropped_count(tmp_path):
    sel = _selection(tmp_path)
    sel = combatlog.Selection(logs=sel.logs, dropped=7)
    out = tmp_path / "out.zip"
    result = combatlog.build_archive(sel, out, _utc(2026, 8, 20, 21, 0),
                                     _utc(2026, 8, 20, 21, 30))
    assert result.dropped == 7
    with zipfile.ZipFile(out) as z:
        assert json.loads(z.read(combatlog.MANIFEST_NAME))["dropped"] == 7


def test_result_reports_characters_sorted_and_deduped(tmp_path):
    p = _log(tmp_path, "20260820_210000_1.txt", "Zed",
             "2026.08.20 21:00:00", _epoch(_utc(2026, 8, 20, 21, 10)))
    q = _log(tmp_path, "20260820_210001_2.txt", "Zed",
             "2026.08.20 21:00:00", _epoch(_utc(2026, 8, 20, 21, 11)))
    r = _log(tmp_path, "20260820_210002_3.txt", "Alice",
             "2026.08.20 21:00:00", _epoch(_utc(2026, 8, 20, 21, 12)))
    logs = [combatlog.SelectedLog(path=x, listener=n,
                                  span_start=_utc(2026, 8, 20, 21, 0),
                                  span_end=_utc(2026, 8, 20, 21, 12))
            for x, n in ((p, "Zed"), (q, "Zed"), (r, "Alice"))]
    out = tmp_path / "out.zip"
    result = combatlog.build_archive(combatlog.Selection(logs=logs, dropped=0), out,
                                     _utc(2026, 8, 20, 21, 0), _utc(2026, 8, 20, 21, 30))
    assert result.characters == ["Alice", "Zed"]


def test_no_staging_file_survives_success(tmp_path):
    sel = _selection(tmp_path)
    out = tmp_path / "out.zip"
    combatlog.build_archive(sel, out, _utc(2026, 8, 20, 21, 0), _utc(2026, 8, 20, 21, 30))
    assert list(tmp_path.glob("*.tmp")) == []


def test_failure_leaves_no_truncated_archive(tmp_path, monkeypatch):
    """A run that dies partway must not leave a file that reads as complete."""
    sel = _selection(tmp_path)
    out = tmp_path / "out.zip"

    def explode(self, filename, *a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(zipfile.ZipFile, "write", explode)
    with pytest.raises(OSError):
        combatlog.build_archive(sel, out, _utc(2026, 8, 20, 21, 0), _utc(2026, 8, 20, 21, 30))
    assert not out.exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_overwrites_an_existing_archive(tmp_path):
    sel = _selection(tmp_path)
    out = tmp_path / "out.zip"
    out.write_bytes(b"stale")
    combatlog.build_archive(sel, out, _utc(2026, 8, 20, 21, 0), _utc(2026, 8, 20, 21, 30))
    with zipfile.ZipFile(out) as z:
        assert combatlog.MANIFEST_NAME in z.namelist()


def test_dropped_note_is_none_when_nothing_dropped():
    assert combatlog.dropped_note(0) is None


def test_dropped_note_singular():
    assert combatlog.dropped_note(1) == f"1 older log omitted (cap {combatlog.MAX_FILES})"


def test_dropped_note_plural():
    assert combatlog.dropped_note(393) == (
        f"393 older logs omitted (cap {combatlog.MAX_FILES})")


def _archive_result(file_count, characters, dropped):
    return combatlog.ArchiveResult(
        path=Path("archive.zip"), file_count=file_count, characters=characters,
        raw_bytes=0, zip_bytes=0, dropped=dropped)


def test_summarize_archive_omits_drop_clause_when_nothing_dropped():
    archive = _archive_result(2, ["Alice", "Zed"], 0)
    summary = combatlog.summarize_archive(
        archive, _utc(2026, 8, 20, 21, 0), _utc(2026, 8, 20, 21, 30))
    assert summary == "Combat logs 2026-08-20 21:00–21:30 UTC · 2 file(s) · Alice, Zed"
    assert "omitted" not in summary


def test_summarize_archive_reports_one_dropped_log():
    archive = _archive_result(64, ["Alice"], 1)
    summary = combatlog.summarize_archive(
        archive, _utc(2026, 8, 20, 21, 0), _utc(2026, 8, 20, 21, 30))
    assert summary.endswith(f"1 older log omitted (cap {combatlog.MAX_FILES})")


def test_summarize_archive_reports_many_dropped_logs():
    archive = _archive_result(64, ["Alice"], 393)
    summary = combatlog.summarize_archive(
        archive, _utc(2026, 8, 20, 21, 0), _utc(2026, 8, 20, 21, 30))
    assert summary.endswith(f"393 older logs omitted (cap {combatlog.MAX_FILES})")


def test_summarize_archive_falls_back_when_no_characters():
    archive = _archive_result(0, [], 0)
    summary = combatlog.summarize_archive(
        archive, _utc(2026, 8, 20, 21, 0), _utc(2026, 8, 20, 21, 30))
    assert "unknown pilots" in summary
