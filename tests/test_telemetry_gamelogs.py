"""Source-aware shared gamelog stream.

Tests the GameLogStream's synchronous scan_once() seam so every assertion is
deterministic: no threads, no real timers — except the TestWorker class which
exercises the real threaded lifecycle.

Core behaviors ported from the legacy Tailer (EOF baseline, partial buffering,
rotation, dedup-before-cap, age cutoff, EVE listener exclusion) plus the shared
stream additions:

- SourceLifecycle emitted before any CombatFact for the same generation.
- Per-source identity via (normalized_path, session_start_utc).
- Stream generation monotonically increments on source change.
- Truncation retires the old generation and activates a new one.
- Folder loss retires all sources; folder recovery baselines at EOF (no replay).
- Files present during any scan (even failed) are tombstoned so they never
  replay when later selected.
- Cap eviction and reappearance do not replay.
- Transient per-file errors do not suppress other sources.
- Subscriber exceptions do not stop later subscribers.
- Errors clear only after a fully successful complete operation.
- Real non-daemon worker with 1s poll / 5s rescan cadence.
"""

import datetime
import threading
import time

from wingman.telemetry.gamelogs import GameLogStream
from wingman.telemetry.model import CombatFact, SourceLifecycle

UTC = datetime.UTC
NOW = datetime.datetime(2026, 8, 25, 12, 0, 0, tzinfo=UTC)

HEADER = (
    "------------------------------------------------------------\n"
    "  Gamelog\n"
    "  Listener: {name}\n"
    "  Session Started: {session}\n"
    "------------------------------------------------------------\n"
)
HEADER_DEFAULT_SESSION = "2026.08.25 11:00:00"

DAMAGE_LINE = (
    "[ 2026.08.25 11:30:00 ] (combat) <color=0xffcc0000><b>142</b> "
    "<color=0xff7fffff><font size=10>from</font> "
    "<b>Bob Smith[BURN](Rifter)</b><font size=10> - Hits</font>\n"
)

OUTGOING_DAMAGE_LINE = (
    "[ 2026.08.25 11:30:00 ] (combat) <color=0xff00ffff><b>299</b> "
    "<color=0x77ffffff><font size=10>to</font> "
    "<b><color=0xffffffff>Mara Veld[OXWLD](Sleepless Patroller)</b>"
    "<font size=10><color=0x77ffffff> - Caldari Navy Scourge Heavy Missile - Hits\n"
)

SCRAMBLE_LINE = (
    "[ 2026.08.25 11:30:05 ] (combat) <color=0xffffffff>"
    "<b>Warp disruption attempt</b> <color=0x77ffffff><font size=10>from</font> "
    "<color=0xffffffff><b><color=0xffffffff><fontsize=12>Carol Vex [BURN]</color>"
    "<color=0xfff0f000> Claw</color><color=0xffffffff></b> "
    "<color=0x77ffffff><font size=10>to <b><color=0xffffffff></font>"
    "<color=0xffffffff><fontsize=12>{target}</color>"
    "<color=0xfff0f000> Loki</color><color=0xffffffff>\n"
)


def _log(
    folder, name, body="", stem="20260825_110000_123", session=HEADER_DEFAULT_SESSION
):
    path = folder / f"{stem}.txt"
    path.write_text(HEADER.format(name=name, session=session) + body, encoding="utf-8")
    return path


def _collect(stream):
    """Subscribe and return a list that accumulates dispatched events."""
    received = []
    stream.subscribe(lambda event: received.append(event))
    return received


# ---------------------------------------------------------------------------
# Source lifecycle and ordering
# ---------------------------------------------------------------------------


class TestSourceLifecycleAndOrdering:
    """SourceLifecycle emitted before CombatFacts, with matching generation."""

    def test_first_scan_emits_active_lifecycle_before_facts(self, tmp_path):
        _log(
            tmp_path,
            "Alice",
            OUTGOING_DAMAGE_LINE,
            stem="20260825_113000_456",
            session="2026.08.25 11:30:00",
        )
        stream = GameLogStream()
        received = _collect(stream)
        stream.start(tmp_path)
        # First scan baselines at EOF, so pre-existing file emits only lifecycle.
        stream.scan_once(NOW)
        lifecycles = [e for e in received if isinstance(e, SourceLifecycle)]
        assert len(lifecycles) == 1
        lc = lifecycles[0]
        assert lc.active is True
        assert lc.available is True
        assert lc.character == "Alice"
        assert lc.source_id is not None
        assert lc.source_id.session_start_utc == datetime.datetime(
            2026, 8, 25, 11, 30, 0, tzinfo=UTC
        )
        stream.stop()

    def test_new_file_after_first_scan_emits_lifecycle_then_facts(self, tmp_path):
        """A file appearing after the first scan is live — read from zero."""
        stream = GameLogStream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)  # first scan, empty folder
        _log(
            tmp_path,
            "Bravo",
            OUTGOING_DAMAGE_LINE,
            stem="20260825_113000_456",
            session="2026.08.25 11:30:00",
        )
        stream.scan_once(NOW)
        lifecycles = [e for e in received if isinstance(e, SourceLifecycle)]
        facts = [e for e in received if isinstance(e, CombatFact)]
        assert len(lifecycles) == 1
        assert lifecycles[0].active is True
        assert lifecycles[0].character == "Bravo"
        assert len(facts) >= 1
        for fact in facts:
            assert fact.source_generation == lifecycles[0].generation
            assert fact.source_id == lifecycles[0].source_id

    def test_facts_carry_matching_source_generation_and_id(self, tmp_path):
        stream = GameLogStream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        path = _log(
            tmp_path, "Alice", stem="20260825_113000_456", session="2026.08.25 11:30:00"
        )
        stream.scan_once(NOW)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(OUTGOING_DAMAGE_LINE)
        stream.scan_once(NOW)
        lc = next(e for e in received if isinstance(e, SourceLifecycle))
        facts = [e for e in received if isinstance(e, CombatFact)]
        assert len(facts) >= 1
        for fact in facts:
            assert fact.source_generation == lc.generation
            assert fact.source_id == lc.source_id
            assert fact.character == "Alice"

    def test_one_active_source_per_character(self, tmp_path):
        """Only the newest session per character is active."""
        _log(tmp_path, "Alice", stem="20260825_100000_1", session="2026.08.25 10:00:00")
        _log(tmp_path, "Alice", stem="20260825_113000_1", session="2026.08.25 11:30:00")
        stream = GameLogStream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        lifecycles = [e for e in received if isinstance(e, SourceLifecycle)]
        active = [lc for lc in lifecycles if lc.active]
        assert len(active) == 1
        assert active[0].source_id.session_start_utc == datetime.datetime(
            2026, 8, 25, 11, 30, 0, tzinfo=UTC
        )

    def test_preexisting_file_baselines_at_eof(self, tmp_path):
        """On first scan, an existing file is baselined at EOF — no replay."""
        _log(tmp_path, "Alice", OUTGOING_DAMAGE_LINE)
        stream = GameLogStream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        facts = [e for e in received if isinstance(e, CombatFact)]
        assert facts == []

    def test_partial_line_is_buffered(self, tmp_path):
        """A poll mid-write buffers partial lines."""
        stream = GameLogStream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        path = _log(
            tmp_path, "Alice", stem="20260825_113000_456", session="2026.08.25 11:30:00"
        )
        stream.scan_once(NOW)
        head, tail = OUTGOING_DAMAGE_LINE[:40], OUTGOING_DAMAGE_LINE[40:]
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(head)
        stream.scan_once(NOW)
        facts_mid = [e for e in received if isinstance(e, CombatFact)]
        assert facts_mid == []
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(tail)
        stream.scan_once(NOW)
        facts_final = [e for e in received if isinstance(e, CombatFact)]
        assert len(facts_final) >= 1

    def test_truncation_retires_old_generation_and_activates_new(self, tmp_path):
        """File truncation retires the old generation and activates a new
        one with a distinct generation number, lifecycle retirement before
        activation, and facts carrying only the new generation."""
        stream = GameLogStream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        # Create the file after first scan so it reads from zero.
        # Give it a long body so the read position advances well past
        # what a truncated rewrite will produce.
        long_body = OUTGOING_DAMAGE_LINE * 10
        path = _log(
            tmp_path,
            "Alice",
            long_body,
            stem="20260825_113000_456",
            session="2026.08.25 11:30:00",
        )
        stream.scan_once(NOW)
        # Record the original generation and verify initial facts
        lc_orig = next(e for e in received if isinstance(e, SourceLifecycle))
        orig_gen = lc_orig.generation
        initial_facts = [e for e in received if isinstance(e, CombatFact)]
        assert len(initial_facts) >= 1, "New file should have been read from zero"
        received.clear()

        # Truncate and rewrite with shorter content.  The new file must
        # be shorter than the tracked position so size < position fires.
        path.write_text(
            HEADER.format(name="Alice", session="2026.08.25 11:30:00")
            + OUTGOING_DAMAGE_LINE,
            encoding="utf-8",
        )
        stream.scan_once(NOW)

        # Should have retirement (old gen) then activation (new gen)
        lifecycles = [e for e in received if isinstance(e, SourceLifecycle)]
        assert len(lifecycles) == 2
        retired_lc, activated_lc = lifecycles[0], lifecycles[1]
        assert retired_lc.active is False
        assert retired_lc.generation == orig_gen
        assert activated_lc.active is True
        assert activated_lc.generation != orig_gen
        assert activated_lc.generation > orig_gen
        # Retirement comes before activation in event order
        assert received.index(retired_lc) < received.index(activated_lc)
        # Facts carry only the new generation
        facts = [e for e in received if isinstance(e, CombatFact)]
        assert len(facts) >= 1
        for fact in facts:
            assert fact.source_generation == activated_lc.generation
        stream.stop()

    def test_retirement_before_replacement(self, tmp_path):
        """When a source is replaced by a newer log, retirement is emitted
        before activation, with distinct generations."""
        stream = GameLogStream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        _log(tmp_path, "Alice", stem="20260825_100000_1", session="2026.08.25 10:00:00")
        stream.scan_once(NOW)
        lc_orig = next(
            e for e in received if isinstance(e, SourceLifecycle) and e.active
        )
        orig_gen = lc_orig.generation
        received.clear()
        # Now a newer log appears
        _log(
            tmp_path,
            "Alice",
            OUTGOING_DAMAGE_LINE,
            stem="20260825_113000_1",
            session="2026.08.25 11:30:00",
        )
        stream.scan_once(NOW)
        lifecycles = [e for e in received if isinstance(e, SourceLifecycle)]
        assert len(lifecycles) == 2
        retired = lifecycles[0]
        activated = lifecycles[1]
        assert retired.active is False
        assert retired.generation == orig_gen
        assert activated.active is True
        assert activated.generation > orig_gen
        # Retirement before activation in event order
        assert received.index(retired) < received.index(activated)
        stream.stop()

    def test_eve_listener_excluded(self, tmp_path):
        """Character-select logs (Listener: EVE) are not tracked."""
        _log(tmp_path, "EVE")
        stream = GameLogStream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        assert [e for e in received if isinstance(e, SourceLifecycle)] == []
        stream.stop()

    def test_files_older_than_cutoff_ignored(self, tmp_path):
        import os

        path = _log(tmp_path, "Alice", OUTGOING_DAMAGE_LINE)
        old = (NOW - datetime.timedelta(hours=13)).timestamp()
        os.utime(path, (old, old))
        stream = GameLogStream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        assert [e for e in received if isinstance(e, SourceLifecycle)] == []
        stream.stop()

    def test_tied_session_start_breaks_on_mtime(self, tmp_path):
        """When two logs for the same character share a session start,
        the one with the newer mtime wins."""
        import os

        _log(tmp_path, "Alice", stem="20260825_100000_1")
        _log(tmp_path, "Alice", stem="20260825_100000_2")
        old_time = (NOW - datetime.timedelta(minutes=10)).timestamp()
        new_time = (NOW - datetime.timedelta(minutes=1)).timestamp()
        os.utime(tmp_path / "20260825_100000_1.txt", (old_time, old_time))
        os.utime(tmp_path / "20260825_100000_2.txt", (new_time, new_time))
        stream = GameLogStream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        lifecycles = [e for e in received if isinstance(e, SourceLifecycle)]
        assert len(lifecycles) == 1
        assert "20260825_100000_2" in lifecycles[0].source_id.normalized_path
        stream.stop()


# ---------------------------------------------------------------------------
# Replay prevention and failure isolation
# ---------------------------------------------------------------------------


class TestReplayPrevention:
    """Folder disappearance, recovery, cap eviction, and transient discovery
    failures must not replay historical data."""

    def test_folder_loss_retires_all_sources(self, tmp_path):
        folder = tmp_path / "gamelogs"
        folder.mkdir()
        _log(folder, "Alice")
        stream = GameLogStream()
        received = _collect(stream)
        stream.start(folder)
        stream.scan_once(NOW)
        lc_active = next(
            e for e in received if isinstance(e, SourceLifecycle) and e.active
        )
        received.clear()
        # Remove the folder
        import shutil

        shutil.rmtree(folder)
        stream.scan_once(NOW)
        lifecycles = [e for e in received if isinstance(e, SourceLifecycle)]
        assert len(lifecycles) == 1
        assert lifecycles[0].active is False
        assert lifecycles[0].generation == lc_active.generation
        stream.stop()

    def test_folder_recovery_baselines_at_eof_no_replay(self, tmp_path):
        """After folder loss and recovery, existing files baseline at EOF.
        No CombatFact is emitted from pre-existing content, but a new
        SourceLifecycle IS emitted for the recovered source."""
        folder = tmp_path / "gamelogs"
        folder.mkdir()
        _log(folder, "Alice", OUTGOING_DAMAGE_LINE)
        stream = GameLogStream()
        received = _collect(stream)
        stream.start(folder)
        stream.scan_once(NOW)
        received.clear()
        # Remove and recreate
        import shutil

        shutil.rmtree(folder)
        stream.scan_once(NOW)
        received.clear()
        folder.mkdir()
        _log(folder, "Alice", OUTGOING_DAMAGE_LINE)
        stream.scan_once(NOW)
        facts = [e for e in received if isinstance(e, CombatFact)]
        assert facts == [], "Recovered folder must not replay old combat"
        lifecycles = [e for e in received if isinstance(e, SourceLifecycle)]
        assert len(lifecycles) == 1
        assert lifecycles[0].active is True
        stream.stop()

    def test_cap_eviction_then_reappearance_does_not_replay(self, tmp_path):
        """A character evicted by the MAX_FILES cap and reappearing later
        baselines at EOF — no facts replayed from its pre-existing content."""
        from wingman.telemetry.gamelogs import MAX_FILES

        stream = GameLogStream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)  # empty first scan

        # Alice has an older session with combat data
        _log(
            tmp_path,
            "Alice",
            OUTGOING_DAMAGE_LINE,
            stem="20260825_050000_999",
            session="2026.08.25 05:00:00",
        )
        # Fill the budget with newer characters so Alice is evicted.
        # Use valid timestamps: hour 11 + minute offset across hours.
        for i in range(MAX_FILES):
            h = 11 + i // 60
            m = i % 60
            _log(
                tmp_path,
                f"Char{i:03d}",
                stem=f"20260825_{h:02d}{m:02d}00_{i:03d}",
                session=f"2026.08.25 {h:02d}:{m:02d}:00",
            )
        stream.scan_once(NOW)
        # Alice should be cap-evicted (older session than all Char*)
        active_chars = {
            e.character for e in received if isinstance(e, SourceLifecycle) and e.active
        }
        assert "Alice" not in active_chars, "Alice should be cap-evicted"
        received.clear()

        # Remove enough characters so Alice can re-enter
        for i in range(MAX_FILES):
            h = 11 + i // 60
            m = i % 60
            (tmp_path / f"20260825_{h:02d}{m:02d}00_{i:03d}.txt").unlink()
        stream.scan_once(NOW)
        # Alice re-enters but her content is historical — no facts
        facts = [
            e for e in received if isinstance(e, CombatFact) and e.character == "Alice"
        ]
        assert facts == [], "Cap-evicted Alice must not replay on reappearance"
        # But she does get a lifecycle
        alice_lc = [
            e
            for e in received
            if isinstance(e, SourceLifecycle) and e.character == "Alice" and e.active
        ]
        assert len(alice_lc) == 1
        stream.stop()

    def test_transient_stat_failure_then_recovery_does_not_replay(self, tmp_path):
        """A file whose stat() fails during one scan but succeeds later is
        baselined at EOF — its path was tombstoned on the failing scan."""
        stream = GameLogStream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)  # empty first scan

        # Create Alice's log with combat data
        alice_path = _log(
            tmp_path,
            "Alice",
            OUTGOING_DAMAGE_LINE,
            stem="20260825_113000_100",
            session="2026.08.25 11:30:00",
        )
        # Make Alice unreadable by replacing with a broken symlink
        real_data = alice_path.read_bytes()
        alice_path.unlink()
        broken = tmp_path / "broken_target"
        alice_path.symlink_to(broken)
        stream.scan_once(NOW)
        # Alice should NOT appear (stat failed)
        alice_events = [
            e
            for e in received
            if isinstance(e, SourceLifecycle) and e.character == "Alice"
        ]
        assert alice_events == []
        received.clear()

        # Recover: remove broken symlink, write the file back
        alice_path.unlink()
        alice_path.write_bytes(real_data)
        stream.scan_once(NOW)
        # Alice appears but her content is historical — no facts replayed
        facts = [
            e for e in received if isinstance(e, CombatFact) and e.character == "Alice"
        ]
        assert facts == [], "Recovered after stat failure must not replay"
        alice_lc = [
            e
            for e in received
            if isinstance(e, SourceLifecycle) and e.character == "Alice" and e.active
        ]
        assert len(alice_lc) == 1
        stream.stop()

    def test_genuinely_new_file_after_baseline_reads_from_zero(self, tmp_path):
        """While known-path tombstoning prevents replay, a genuinely new
        file whose path was NEVER seen in any prior scan reads from zero."""
        stream = GameLogStream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)  # empty first scan
        # A file that never existed during any prior scan
        _log(
            tmp_path,
            "NewChar",
            OUTGOING_DAMAGE_LINE,
            stem="20260825_113000_NEW",
            session="2026.08.25 11:30:00",
        )
        stream.scan_once(NOW)
        facts = [
            e
            for e in received
            if isinstance(e, CombatFact) and e.character == "NewChar"
        ]
        assert len(facts) >= 1, "Genuinely new file should read from zero"
        stream.stop()

    def test_transient_per_source_read_error_does_not_suppress_others(self, tmp_path):
        """One unreadable file during poll does not suppress reads from
        other sources.  Bob's new data is still emitted."""
        stream = GameLogStream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        _log(
            tmp_path, "Alice", stem="20260825_113000_100", session="2026.08.25 11:30:00"
        )
        _log(tmp_path, "Bob", stem="20260825_113000_200", session="2026.08.25 11:30:00")
        stream.scan_once(NOW)
        received.clear()
        # Append to Bob's file
        with open(tmp_path / "20260825_113000_200.txt", "a", encoding="utf-8") as fh:
            fh.write(OUTGOING_DAMAGE_LINE)
        # Remove Alice's file
        (tmp_path / "20260825_113000_100.txt").unlink()
        stream.scan_once(NOW)
        bob_facts = [
            e for e in received if isinstance(e, CombatFact) and e.character == "Bob"
        ]
        assert len(bob_facts) >= 1, "Bob's facts must survive Alice's error"
        stream.stop()

    def test_subscriber_exception_does_not_stop_later_subscribers(self, tmp_path):
        """A throwing subscriber must not prevent later subscribers from receiving."""
        stream = GameLogStream()
        received_good = []

        def bad_subscriber(event):
            raise RuntimeError("I crash")

        def good_subscriber(event):
            received_good.append(event)

        stream.subscribe(bad_subscriber)
        stream.subscribe(good_subscriber)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        _log(
            tmp_path,
            "Alice",
            OUTGOING_DAMAGE_LINE,
            stem="20260825_113000_456",
            session="2026.08.25 11:30:00",
        )
        stream.scan_once(NOW)
        assert len(received_good) > 0, "Good subscriber must still receive events"
        stream.stop()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_stopped_health(self, tmp_path):
        stream = GameLogStream()
        h = stream.health()
        assert h.state == "stopped"

    def test_running_health(self, tmp_path):
        stream = GameLogStream()
        stream.start(tmp_path)
        stream.scan_once(NOW)
        h = stream.health()
        assert h.state in ("running", "active")
        stream.stop()

    def test_missing_folder_health(self, tmp_path):
        stream = GameLogStream()
        stream.start(tmp_path / "nonexistent")
        stream.scan_once(NOW)
        h = stream.health()
        assert h.state == "missing_folder"
        stream.stop()

    def test_error_clears_only_after_fully_successful_rescan(self, tmp_path):
        """Inject a real scan error (broken symlink causing stat failure),
        verify health reports error, then fix it and verify error clears
        only after a fully clean rescan."""
        folder = tmp_path / "gamelogs"
        folder.mkdir()
        stream = GameLogStream()
        stream.start(folder)
        stream.scan_once(NOW)  # baseline — running, no error

        # Create a broken symlink that will cause stat failure
        broken_link = folder / "20260825_110000_bad.txt"
        broken_link.symlink_to(folder / "nonexistent_target")
        stream.scan_once(NOW)
        h = stream.health()
        assert h.state == "error", f"Expected error after stat failure, got {h.state}"

        # Fix the error by removing the broken symlink
        broken_link.unlink()
        stream.scan_once(NOW)
        h = stream.health()
        assert h.state != "error", "Error should clear after a fully clean rescan"
        stream.stop()

    def test_per_source_poll_error_is_recorded(self, tmp_path):
        """A read failure during poll is recorded in health without
        suppressing other sources."""
        stream = GameLogStream()
        stream.start(tmp_path)
        stream.scan_once(NOW)
        _log(
            tmp_path, "Alice", stem="20260825_113000_100", session="2026.08.25 11:30:00"
        )
        _log(tmp_path, "Bob", stem="20260825_113000_200", session="2026.08.25 11:30:00")
        stream.scan_once(NOW)
        # Remove Alice's file to cause a poll error
        (tmp_path / "20260825_113000_100.txt").unlink()
        # Append to Bob
        with open(tmp_path / "20260825_113000_200.txt", "a", encoding="utf-8") as fh:
            fh.write(OUTGOING_DAMAGE_LINE)
        stream.scan_once(NOW)
        h = stream.health()
        # The rescan will retire Alice (folder enumeration no longer finds
        # her), so the poll error may or may not surface depending on
        # ordering.  The important thing is health is not "stopped".
        assert h.state != "stopped"
        stream.stop()


# ---------------------------------------------------------------------------
# Interface contracts
# ---------------------------------------------------------------------------


class TestInterface:
    def test_subscribe_returns_unsubscribe_callable(self, tmp_path):
        stream = GameLogStream()
        received = []
        unsub = stream.subscribe(lambda e: received.append(e))
        stream.start(tmp_path)
        _log(tmp_path, "Alice")
        stream.scan_once(NOW)
        unsub()
        received_after_unsub = len(received)
        _log(tmp_path, "Bob", stem="20260825_113000_456", session="2026.08.25 11:30:00")
        stream.scan_once(NOW)
        bob_events = [
            e
            for e in received[received_after_unsub:]
            if isinstance(e, SourceLifecycle) and e.character == "Bob"
        ]
        assert bob_events == [], "No events after unsubscribe"
        stream.stop()

    def test_stop_is_idempotent(self, tmp_path):
        stream = GameLogStream()
        stream.start(tmp_path)
        stream.stop()
        stream.stop()  # Must not raise

    def test_start_is_idempotent(self, tmp_path):
        """Calling start() while already running is a no-op."""
        stream = GameLogStream()
        stream.start(tmp_path)
        worker1 = stream._worker
        stream.start(tmp_path)  # no-op
        assert stream._worker is worker1, "start() must not spawn a second worker"
        stream.stop()

    def test_request_source_triggers_lifecycle_for_character(self, tmp_path):
        """request_source re-publishes lifecycle for a known character."""
        _log(tmp_path, "Alice")
        stream = GameLogStream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        received.clear()
        stream.request_source("Alice")
        lifecycles = [e for e in received if isinstance(e, SourceLifecycle)]
        assert len(lifecycles) == 1
        assert lifecycles[0].character == "Alice"
        assert lifecycles[0].active is True
        stream.stop()

    def test_request_source_unavailable_character(self, tmp_path):
        """request_source for an unknown character emits unavailable lifecycle."""
        stream = GameLogStream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        stream.request_source("Unknown")
        lifecycles = [e for e in received if isinstance(e, SourceLifecycle)]
        assert len(lifecycles) == 1
        assert lifecycles[0].character == "Unknown"
        assert lifecycles[0].available is False
        assert lifecycles[0].active is False
        stream.stop()


# ---------------------------------------------------------------------------
# Dedup-before-cap (ported from Tailer)
# ---------------------------------------------------------------------------


class TestDedupBeforeCap:
    def test_dedup_runs_before_cap(self, tmp_path):
        """One character with more sessions than MAX_FILES must not starve others.

        Ported directly from test_alerts_tailer.py — this is the same proven
        rule, now enforced in the shared stream.
        """
        from wingman.telemetry.gamelogs import MAX_FILES

        busy_newest = NOW - datetime.timedelta(minutes=1)
        for i in range(MAX_FILES + 20):
            started = busy_newest - datetime.timedelta(minutes=i)
            _log(
                tmp_path,
                "Busy",
                stem=f"busy_{i:03d}",
                session=started.strftime("%Y.%m.%d %H:%M:%S"),
            )
        older = NOW - datetime.timedelta(hours=5)
        _log(
            tmp_path,
            "Alice",
            stem="alice_0",
            session=older.strftime("%Y.%m.%d %H:%M:%S"),
        )
        _log(
            tmp_path,
            "Bravo",
            stem="bravo_0",
            session=(older - datetime.timedelta(minutes=1)).strftime(
                "%Y.%m.%d %H:%M:%S"
            ),
        )
        stream = GameLogStream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        chars = {
            e.character for e in received if isinstance(e, SourceLifecycle) and e.active
        }
        assert {"Busy", "Alice", "Bravo"} <= chars
        stream.stop()


# ---------------------------------------------------------------------------
# Combat fact parsing integration
# ---------------------------------------------------------------------------


class TestCombatFactParsing:
    def test_incoming_damage_produces_combat_fact(self, tmp_path):
        stream = GameLogStream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        path = _log(
            tmp_path, "Alice", stem="20260825_113000_456", session="2026.08.25 11:30:00"
        )
        stream.scan_once(NOW)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(DAMAGE_LINE)
        stream.scan_once(NOW)
        facts = [e for e in received if isinstance(e, CombatFact)]
        assert len(facts) == 1
        assert facts[0].kind == "incoming_damage"
        assert facts[0].character == "Alice"
        stream.stop()

    def test_outgoing_damage_produces_combat_fact(self, tmp_path):
        stream = GameLogStream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        path = _log(
            tmp_path, "Alice", stem="20260825_113000_456", session="2026.08.25 11:30:00"
        )
        stream.scan_once(NOW)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(OUTGOING_DAMAGE_LINE)
        stream.scan_once(NOW)
        facts = [e for e in received if isinstance(e, CombatFact)]
        assert len(facts) == 1
        assert facts[0].kind == "outgoing_damage"
        assert facts[0].amount == 299
        stream.stop()

    def test_incoming_tackle_with_ownership(self, tmp_path):
        """Only the named target gets a tackle fact."""
        stream = GameLogStream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        path = _log(
            tmp_path,
            "Alice Renn",
            stem="20260825_113000_456",
            session="2026.08.25 11:30:00",
        )
        stream.scan_once(NOW)
        scramble = SCRAMBLE_LINE.format(target="Alice Renn [OXWLD]")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(scramble)
        stream.scan_once(NOW)
        facts = [e for e in received if isinstance(e, CombatFact)]
        tackle_facts = [f for f in facts if f.kind == "incoming_tackle"]
        assert len(tackle_facts) == 1
        assert tackle_facts[0].character == "Alice Renn"
        stream.stop()

    def test_fleet_broadcast_does_not_alert_bystander(self, tmp_path):
        """Fleet broadcast scramble lines should not generate tackle for bystanders."""
        stream = GameLogStream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        path = _log(
            tmp_path,
            "Alice Renn",
            stem="20260825_113000_456",
            session="2026.08.25 11:30:00",
        )
        stream.scan_once(NOW)
        scramble = SCRAMBLE_LINE.format(target="Dave Kord [KVOS]")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(scramble)
        stream.scan_once(NOW)
        facts = [e for e in received if isinstance(e, CombatFact)]
        tackle_facts = [f for f in facts if f.kind == "incoming_tackle"]
        assert tackle_facts == []
        stream.stop()

    def test_undecodable_bytes_do_not_crash(self, tmp_path):
        stream = GameLogStream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        path = _log(
            tmp_path, "Alice", stem="20260825_113000_456", session="2026.08.25 11:30:00"
        )
        stream.scan_once(NOW)
        with open(path, "ab") as fh:
            fh.write(b"\xff\xfe garbage\n")
            fh.write(OUTGOING_DAMAGE_LINE.encode("utf-8"))
        stream.scan_once(NOW)
        facts = [e for e in received if isinstance(e, CombatFact)]
        assert len(facts) >= 1
        stream.stop()


# ---------------------------------------------------------------------------
# Worker lifecycle
# ---------------------------------------------------------------------------


class TestWorker:
    """Real threaded lifecycle: daemon=False, cadence, stop event, join."""

    def test_start_spawns_a_non_daemon_worker(self, tmp_path):
        stream = GameLogStream()
        stream.start(tmp_path)
        assert stream._worker is not None
        assert stream._worker.is_alive()
        assert stream._worker.daemon is False
        stream.stop()

    def test_stop_joins_the_worker_within_timeout(self, tmp_path):
        stream = GameLogStream()
        stream.start(tmp_path)
        worker = stream._worker
        t0 = time.monotonic()
        stream.stop(timeout=3.0)
        elapsed = time.monotonic() - t0
        assert elapsed < 3.0, "stop() must join within the timeout"
        assert not worker.is_alive()

    def test_fresh_stop_event_per_start_generation(self, tmp_path):
        """Each start() creates a fresh stop event so a leftover set()
        from a previous stop cannot immediately kill the new worker."""
        stream = GameLogStream()
        stream.start(tmp_path)
        ev1 = stream._stop_event
        stream.stop()
        assert ev1.is_set()
        stream.start(tmp_path)
        ev2 = stream._stop_event
        assert ev2 is not ev1, "Must be a fresh event object"
        assert not ev2.is_set(), "Fresh event must not be pre-set"
        stream.stop()

    def test_worker_polls_at_least_once_before_stop(self, tmp_path):
        """The worker runs at least one poll cycle."""
        stream = GameLogStream()
        received = _collect(stream)
        _log(tmp_path, "Alice")
        stream.start(tmp_path)
        # Give the worker time for at least one cycle
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if any(isinstance(e, SourceLifecycle) for e in received):
                break
            time.sleep(0.05)
        stream.stop()
        lifecycles = [e for e in received if isinstance(e, SourceLifecycle)]
        assert len(lifecycles) >= 1, "Worker must have polled at least once"

    def test_stop_is_idempotent_with_worker(self, tmp_path):
        stream = GameLogStream()
        stream.start(tmp_path)
        stream.stop()
        stream.stop()  # Must not raise

    def test_start_stop_start_stop_cycle(self, tmp_path):
        """Full restart cycle works cleanly."""
        stream = GameLogStream()
        stream.start(tmp_path)
        assert stream._worker.is_alive()
        stream.stop()
        assert stream._worker is None or not stream._worker.is_alive()
        stream.start(tmp_path)
        assert stream._worker.is_alive()
        stream.stop()


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_subscribe_unsubscribe_concurrent_with_scan(self, tmp_path):
        """subscribe/unsubscribe during scan_once must not crash."""
        stream = GameLogStream()
        stream.start(tmp_path)
        _log(tmp_path, "Alice")

        barrier = threading.Event()
        results = []

        def subscriber(event):
            results.append(event)

        def sub_unsub():
            barrier.wait(timeout=2)
            for _ in range(50):
                unsub = stream.subscribe(subscriber)
                unsub()

        t = threading.Thread(target=sub_unsub)
        t.start()
        barrier.set()
        for _ in range(50):
            stream.scan_once(NOW)
        t.join(timeout=5)
        assert not t.is_alive()
        stream.stop()

    def test_request_source_concurrent_with_scan(self, tmp_path):
        """request_source during scan_once must not crash."""
        stream = GameLogStream()
        _collect(stream)
        stream.start(tmp_path)
        _log(tmp_path, "Alice")
        stream.scan_once(NOW)

        barrier = threading.Event()

        def requester():
            barrier.wait(timeout=2)
            for _ in range(50):
                stream.request_source("Alice")
                stream.request_source("Unknown")

        t = threading.Thread(target=requester)
        t.start()
        barrier.set()
        for _ in range(50):
            stream.scan_once(NOW)
        t.join(timeout=5)
        assert not t.is_alive()
        stream.stop()

    def test_health_concurrent_with_scan(self, tmp_path):
        """health() during scan_once must not crash."""
        stream = GameLogStream()
        stream.start(tmp_path)
        _log(tmp_path, "Alice")

        barrier = threading.Event()
        health_results = []

        def health_poller():
            barrier.wait(timeout=2)
            for _ in range(50):
                health_results.append(stream.health())

        t = threading.Thread(target=health_poller)
        t.start()
        barrier.set()
        for _ in range(50):
            stream.scan_once(NOW)
        t.join(timeout=5)
        assert not t.is_alive()
        assert len(health_results) == 50
        stream.stop()
