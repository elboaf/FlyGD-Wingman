"""Following the Gamelogs folder.

Every awkward case here is one TriffView hit in production: replaying an
old fight on enable, a read landing mid-write, and a log rotating under
the reader.
"""

import datetime

from obs_youtube_uploader.alerts import tailer

UTC = datetime.UTC
NOW = datetime.datetime(2026, 8, 25, 12, 0, 0, tzinfo=UTC)

HEADER = (
    "------------------------------------------------------------\n"
    "  Gamelog\n"
    "  Listener: {name}\n"
    "  Session Started: 2026.08.25 11:00:00\n"
    "------------------------------------------------------------\n"
)
DAMAGE = (
    "[ 2026.08.25 11:30:00 ] (combat) <color=0xffcc0000><b>142</b> "
    "<color=0xff7fffff><font size=10>from</font> "
    "<b>Bob Smith[BURN](Rifter)</b><font size=10> - Hits</font>\n"
)


def _log(folder, name, body="", stem="20260825_110000_123"):
    path = folder / f"{stem}.txt"
    path.write_text(HEADER.format(name=name) + body, encoding="utf-8")
    return path


def test_a_preexisting_file_is_opened_at_its_end(tmp_path):
    """Ticking Enable must not replay this morning's fight as a burst of
    alerts. This is the single most user-visible rule in the module."""
    _log(tmp_path, "Alice", DAMAGE)
    t = tailer.Tailer(tmp_path)
    t.rescan(NOW)
    assert t.poll() == []


def test_lines_appended_after_the_first_rescan_are_emitted(tmp_path):
    path = _log(tmp_path, "Alice")
    t = tailer.Tailer(tmp_path)
    t.rescan(NOW)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(DAMAGE)
    events = t.poll()
    assert [(e.character, e.event) for e in events] == [("Alice", "combat")]


def test_a_file_appearing_later_is_read_from_the_start(tmp_path):
    """A client that logs in mid-session is live, so its whole log is new
    -- unlike one that was already there when alerts were switched on."""
    t = tailer.Tailer(tmp_path)
    t.rescan(NOW)
    _log(tmp_path, "Bravo", DAMAGE, stem="20260825_113000_456")
    t.rescan(NOW)
    assert [e.character for e in t.poll()] == ["Bravo"]


def test_a_partial_trailing_line_is_buffered_until_its_newline(tmp_path):
    """A poll can land mid-write. Emitting half a line drops the event,
    because the colour code and the source are at opposite ends of it."""
    path = _log(tmp_path, "Alice")
    t = tailer.Tailer(tmp_path)
    t.rescan(NOW)
    head, tail = DAMAGE[:40], DAMAGE[40:]
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(head)
    assert t.poll() == []
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(tail)
    assert len(t.poll()) == 1


def test_truncation_resets_the_read_position(tmp_path):
    """If the file shrank it rotated. Without the reset the reader sits
    past the end and never emits again for that character."""
    path = _log(tmp_path, "Alice")
    t = tailer.Tailer(tmp_path)
    t.rescan(NOW)
    path.write_text(HEADER.format(name="Alice") + DAMAGE, encoding="utf-8")
    assert len(t.poll()) == 1


def test_files_older_than_the_cutoff_are_ignored(tmp_path):
    import os

    path = _log(tmp_path, "Alice", DAMAGE)
    old = (NOW - datetime.timedelta(hours=13)).timestamp()
    os.utime(path, (old, old))
    t = tailer.Tailer(tmp_path)
    t.rescan(NOW)
    assert t.characters() == []


def test_a_listener_of_EVE_is_not_a_character(tmp_path):
    """A client sitting at character-select writes a log with no pilot.
    Treating it as one produces a character nothing can ever alert."""
    _log(tmp_path, "EVE", DAMAGE)
    t = tailer.Tailer(tmp_path)
    t.rescan(NOW)
    assert t.characters() == []


def test_the_newest_session_wins_when_one_character_has_several_logs(tmp_path):
    """A relog leaves the old log on disk. Reading both would alert twice
    for one event, and the stale one never gets new lines anyway."""
    _log(tmp_path, "Alice", stem="20260825_100000_1")
    newer = _log(tmp_path, "Alice", stem="20260825_113000_1")
    t = tailer.Tailer(tmp_path)
    t.rescan(NOW)
    with open(newer, "a", encoding="utf-8") as fh:
        fh.write(DAMAGE)
    assert len(t.poll()) == 1


def test_undecodable_bytes_do_not_kill_the_tailer(tmp_path):
    """One bad byte must cost one line, not the feature for the session."""
    path = _log(tmp_path, "Alice")
    t = tailer.Tailer(tmp_path)
    t.rescan(NOW)
    with open(path, "ab") as fh:
        fh.write(b"\xff\xfe garbage\n")
        fh.write(DAMAGE.encode("utf-8"))
    assert len(t.poll()) == 1


def test_a_missing_folder_is_not_an_error(tmp_path):
    """The folder can be deleted or unmounted while running; that is a
    quiet tailer, not a crashed one."""
    t = tailer.Tailer(tmp_path / "gone")
    t.rescan(NOW)
    assert t.poll() == [] and t.characters() == []


def _log_at(folder, name, session_started, stem):
    """Like _log, but with a header naming its own Session Started time,
    so distinct sessions for the same character sort distinctly."""
    header = (
        "------------------------------------------------------------\n"
        "  Gamelog\n"
        f"  Listener: {name}\n"
        f"  Session Started: {session_started}\n"
        "------------------------------------------------------------\n"
    )
    path = folder / f"{stem}.txt"
    path.write_text(header, encoding="utf-8")
    return path


def test_dedup_runs_before_the_file_cap_not_after(tmp_path):
    """One character with more sessions than MAX_FILES inside the window
    (a client stuck in a relog loop) must not consume the whole cap and
    silently starve every other character. Busy's sessions are all more
    recent than Alice's and Bravo's single sessions, so a cap-first pass
    -- take the MAX_FILES newest candidates, then dedup -- fills the
    entire budget with nothing but Busy's own history and never even
    reaches Alice's or Bravo's, which is the failure mode this pins."""
    busy_newest = NOW - datetime.timedelta(minutes=1)
    for i in range(tailer.MAX_FILES + 20):
        started = busy_newest - datetime.timedelta(minutes=i)
        _log_at(
            tmp_path,
            "Busy",
            started.strftime("%Y.%m.%d %H:%M:%S"),
            stem=f"busy_{i:03d}",
        )
    # Older than every Busy session above, but still inside the 12h window.
    older = NOW - datetime.timedelta(hours=5)
    _log_at(tmp_path, "Alice", older.strftime("%Y.%m.%d %H:%M:%S"), stem="alice_0")
    _log_at(
        tmp_path,
        "Bravo",
        (older - datetime.timedelta(minutes=1)).strftime("%Y.%m.%d %H:%M:%S"),
        stem="bravo_0",
    )

    t = tailer.Tailer(tmp_path)
    t.rescan(NOW)

    assert set(t.characters()) == {"Busy", "Alice", "Bravo"}
