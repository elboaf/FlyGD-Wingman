"""Source-aware shared gamelog stream — tests.

Most tests use ``_noop_thread_factory`` so ``start()`` sets up state without
spawning a real thread, and ``scan_once()`` is called synchronously.  Only
``TestWorker`` uses real threads.
"""

import datetime
import threading
import time

from wingman.telemetry.gamelogs import (
    POLL_INTERVAL_S,
    GameLogStream,
    _noop_thread_factory,
)
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


def _stream():
    """Create a GameLogStream with the noop thread factory for synchronous tests."""
    return GameLogStream(_thread_factory=_noop_thread_factory)


def _collect(stream):
    """Subscribe and return a list that accumulates dispatched events."""
    received = []
    stream.subscribe(lambda event: received.append(event))
    return received


# ---------------------------------------------------------------------------
# Source lifecycle and ordering
# ---------------------------------------------------------------------------


class TestSourceLifecycleAndOrdering:
    def test_first_scan_emits_active_lifecycle(self, tmp_path):
        _log(
            tmp_path,
            "Alice",
            OUTGOING_DAMAGE_LINE,
            stem="20260825_113000_456",
            session="2026.08.25 11:30:00",
        )
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
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

    def test_new_file_after_first_scan_reads_from_zero(self, tmp_path):
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)  # empty first scan
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
        assert len(facts) == 1
        assert facts[0].source_generation == lifecycles[0].generation
        assert facts[0].source_id == lifecycles[0].source_id

    def test_lifecycle_before_facts_in_event_stream(self, tmp_path):
        """Activation lifecycle must appear before any CombatFact."""
        stream = _stream()
        received = _collect(stream)
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
        lc_idx = next(
            i for i, e in enumerate(received) if isinstance(e, SourceLifecycle)
        )
        fact_idx = next(i for i, e in enumerate(received) if isinstance(e, CombatFact))
        assert lc_idx < fact_idx
        stream.stop()

    def test_facts_carry_matching_source_generation_and_id(self, tmp_path):
        stream = _stream()
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
        assert len(facts) == 1
        assert facts[0].source_generation == lc.generation
        assert facts[0].source_id == lc.source_id
        assert facts[0].character == "Alice"

    def test_one_active_source_per_character(self, tmp_path):
        _log(tmp_path, "Alice", stem="20260825_100000_1", session="2026.08.25 10:00:00")
        _log(tmp_path, "Alice", stem="20260825_113000_1", session="2026.08.25 11:30:00")
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        active = [e for e in received if isinstance(e, SourceLifecycle) and e.active]
        assert len(active) == 1
        assert active[0].source_id.session_start_utc == datetime.datetime(
            2026, 8, 25, 11, 30, 0, tzinfo=UTC
        )

    def test_preexisting_file_baselines_at_eof(self, tmp_path):
        _log(tmp_path, "Alice", OUTGOING_DAMAGE_LINE)
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        assert [e for e in received if isinstance(e, CombatFact)] == []

    def test_partial_line_is_buffered(self, tmp_path):
        stream = _stream()
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
        assert [e for e in received if isinstance(e, CombatFact)] == []
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(tail)
        stream.scan_once(NOW)
        facts = [e for e in received if isinstance(e, CombatFact)]
        assert len(facts) == 1

    def test_truncation_retires_old_activates_new_generation(self, tmp_path):
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        # Give it a long body so truncation is detectable.
        path = _log(
            tmp_path,
            "Alice",
            OUTGOING_DAMAGE_LINE * 10,
            stem="20260825_113000_456",
            session="2026.08.25 11:30:00",
        )
        stream.scan_once(NOW)
        lc_orig = next(e for e in received if isinstance(e, SourceLifecycle))
        orig_gen = lc_orig.generation
        assert len([e for e in received if isinstance(e, CombatFact)]) >= 1
        received.clear()
        # Truncate and rewrite shorter.
        path.write_text(
            HEADER.format(name="Alice", session="2026.08.25 11:30:00")
            + OUTGOING_DAMAGE_LINE,
            encoding="utf-8",
        )
        stream.scan_once(NOW)
        lifecycles = [e for e in received if isinstance(e, SourceLifecycle)]
        assert len(lifecycles) == 2
        assert lifecycles[0].active is False
        assert lifecycles[0].generation == orig_gen
        assert lifecycles[1].active is True
        assert lifecycles[1].generation > orig_gen
        assert received.index(lifecycles[0]) < received.index(lifecycles[1])
        facts = [e for e in received if isinstance(e, CombatFact)]
        assert len(facts) >= 1
        for f in facts:
            assert f.source_generation == lifecycles[1].generation
        stream.stop()

    def test_retirement_before_replacement(self, tmp_path):
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        _log(tmp_path, "Alice", stem="20260825_100000_1", session="2026.08.25 10:00:00")
        stream.scan_once(NOW)
        orig_gen = next(
            e for e in received if isinstance(e, SourceLifecycle) and e.active
        ).generation
        received.clear()
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
        assert lifecycles[0].active is False
        assert lifecycles[0].generation == orig_gen
        assert lifecycles[1].active is True
        assert lifecycles[1].generation > orig_gen
        assert received.index(lifecycles[0]) < received.index(lifecycles[1])
        stream.stop()

    def test_eve_listener_excluded(self, tmp_path):
        _log(tmp_path, "EVE")
        stream = _stream()
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
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        assert [e for e in received if isinstance(e, SourceLifecycle)] == []
        stream.stop()

    def test_tied_session_start_breaks_on_mtime(self, tmp_path):
        import os

        _log(tmp_path, "Alice", stem="20260825_100000_1")
        _log(tmp_path, "Alice", stem="20260825_100000_2")
        old_time = (NOW - datetime.timedelta(minutes=10)).timestamp()
        new_time = (NOW - datetime.timedelta(minutes=1)).timestamp()
        os.utime(tmp_path / "20260825_100000_1.txt", (old_time, old_time))
        os.utime(tmp_path / "20260825_100000_2.txt", (new_time, new_time))
        stream = _stream()
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
    def test_folder_loss_retires_all_sources(self, tmp_path):
        import shutil

        folder = tmp_path / "gamelogs"
        folder.mkdir()
        _log(folder, "Alice")
        stream = _stream()
        received = _collect(stream)
        stream.start(folder)
        stream.scan_once(NOW)
        active_gen = next(
            e for e in received if isinstance(e, SourceLifecycle) and e.active
        ).generation
        received.clear()
        shutil.rmtree(folder)
        stream.scan_once(NOW)
        lifecycles = [e for e in received if isinstance(e, SourceLifecycle)]
        assert len(lifecycles) == 1
        assert lifecycles[0].active is False
        assert lifecycles[0].generation == active_gen
        stream.stop()

    def test_folder_recovery_baselines_at_eof_no_replay(self, tmp_path):
        import shutil

        folder = tmp_path / "gamelogs"
        folder.mkdir()
        _log(folder, "Alice", OUTGOING_DAMAGE_LINE)
        stream = _stream()
        received = _collect(stream)
        stream.start(folder)
        stream.scan_once(NOW)
        received.clear()
        shutil.rmtree(folder)
        stream.scan_once(NOW)
        received.clear()
        folder.mkdir()
        _log(folder, "Alice", OUTGOING_DAMAGE_LINE)
        stream.scan_once(NOW)
        assert [e for e in received if isinstance(e, CombatFact)] == []
        assert (
            len([e for e in received if isinstance(e, SourceLifecycle) and e.active])
            == 1
        )
        stream.stop()

    def test_cap_eviction_then_reappearance_does_not_replay(self, tmp_path):
        from wingman.telemetry.gamelogs import MAX_FILES

        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        _log(
            tmp_path,
            "Alice",
            OUTGOING_DAMAGE_LINE,
            stem="20260825_050000_999",
            session="2026.08.25 05:00:00",
        )
        for i in range(MAX_FILES):
            h, m = 11 + i // 60, i % 60
            _log(
                tmp_path,
                f"Char{i:03d}",
                stem=f"20260825_{h:02d}{m:02d}00_{i:03d}",
                session=f"2026.08.25 {h:02d}:{m:02d}:00",
            )
        stream.scan_once(NOW)
        active_chars = {
            e.character for e in received if isinstance(e, SourceLifecycle) and e.active
        }
        assert "Alice" not in active_chars
        received.clear()
        for i in range(MAX_FILES):
            h, m = 11 + i // 60, i % 60
            (tmp_path / f"20260825_{h:02d}{m:02d}00_{i:03d}.txt").unlink()
        stream.scan_once(NOW)
        assert [
            e for e in received if isinstance(e, CombatFact) and e.character == "Alice"
        ] == []
        assert (
            len(
                [
                    e
                    for e in received
                    if isinstance(e, SourceLifecycle)
                    and e.character == "Alice"
                    and e.active
                ]
            )
            == 1
        )
        stream.stop()

    def test_transient_stat_failure_then_recovery_no_replay(self, tmp_path):
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        alice_path = _log(
            tmp_path,
            "Alice",
            OUTGOING_DAMAGE_LINE,
            stem="20260825_113000_100",
            session="2026.08.25 11:30:00",
        )
        real_data = alice_path.read_bytes()
        alice_path.unlink()
        alice_path.symlink_to(tmp_path / "broken_target")
        stream.scan_once(NOW)
        assert [
            e
            for e in received
            if isinstance(e, SourceLifecycle) and e.character == "Alice"
        ] == []
        received.clear()
        alice_path.unlink()
        alice_path.write_bytes(real_data)
        stream.scan_once(NOW)
        assert [
            e for e in received if isinstance(e, CombatFact) and e.character == "Alice"
        ] == []
        assert (
            len(
                [
                    e
                    for e in received
                    if isinstance(e, SourceLifecycle)
                    and e.character == "Alice"
                    and e.active
                ]
            )
            == 1
        )
        stream.stop()

    def test_baseline_stat_failure_defers_activation_then_recovers(self, tmp_path):
        """If EOF cannot be established for a known path, the source is NOT
        activated.  On the next scan when stat succeeds, activate at
        current EOF with no historical facts."""
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        # First scan: file present, baselined at EOF.
        alice_path = _log(tmp_path, "Alice", OUTGOING_DAMAGE_LINE)
        stream.scan_once(NOW)
        assert (
            len([e for e in received if isinstance(e, SourceLifecycle) and e.active])
            == 1
        )
        received.clear()
        # Simulate stat failure by replacing with a broken symlink.
        real_data = alice_path.read_bytes()
        alice_path.unlink()
        alice_path.symlink_to(tmp_path / "gone")
        stream.scan_once(NOW)
        # The source should be retired because the file is gone from
        # candidates (stat failed).
        retired = [
            e for e in received if isinstance(e, SourceLifecycle) and not e.active
        ]
        assert len(retired) == 1
        received.clear()
        # Restore with MORE content (so replaying would be visible).
        alice_path.unlink()
        alice_path.write_bytes(real_data + OUTGOING_DAMAGE_LINE.encode("utf-8") * 5)
        stream.scan_once(NOW)
        # Activated at EOF — no facts replayed.
        assert [e for e in received if isinstance(e, CombatFact)] == []
        assert (
            len([e for e in received if isinstance(e, SourceLifecycle) and e.active])
            == 1
        )
        stream.stop()

    def test_genuinely_new_file_reads_from_zero(self, tmp_path):
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
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
        assert len(facts) == 1

    def test_per_source_read_error_does_not_suppress_others(self, tmp_path):
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        _log(
            tmp_path, "Alice", stem="20260825_113000_100", session="2026.08.25 11:30:00"
        )
        _log(tmp_path, "Bob", stem="20260825_113000_200", session="2026.08.25 11:30:00")
        stream.scan_once(NOW)
        received.clear()
        with open(tmp_path / "20260825_113000_200.txt", "a", encoding="utf-8") as fh:
            fh.write(OUTGOING_DAMAGE_LINE)
        (tmp_path / "20260825_113000_100.txt").unlink()
        stream.scan_once(NOW)
        bob_facts = [
            e for e in received if isinstance(e, CombatFact) and e.character == "Bob"
        ]
        assert len(bob_facts) == 1
        stream.stop()

    def test_subscriber_exception_does_not_stop_later_subscribers(self, tmp_path):
        stream = _stream()
        good = []
        stream.subscribe(lambda e: (_ for _ in ()).throw(RuntimeError("crash")))
        stream.subscribe(lambda e: good.append(e))
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
        assert len(good) > 0
        stream.stop()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_stopped(self, tmp_path):
        assert _stream().health().state == "stopped"

    def test_running(self, tmp_path):
        stream = _stream()
        stream.start(tmp_path)
        stream.scan_once(NOW)
        assert stream.health().state in ("running", "active")
        stream.stop()

    def test_missing_folder(self, tmp_path):
        stream = _stream()
        stream.start(tmp_path / "nonexistent")
        stream.scan_once(NOW)
        assert stream.health().state == "missing_folder"
        stream.stop()

    def test_scan_error_then_clear_after_full_success(self, tmp_path):
        folder = tmp_path / "gamelogs"
        folder.mkdir()
        stream = _stream()
        stream.start(folder)
        stream.scan_once(NOW)
        broken = folder / "20260825_110000_bad.txt"
        broken.symlink_to(folder / "nonexistent_target")
        stream.scan_once(NOW)
        assert stream.health().state == "error"
        broken.unlink()
        stream.scan_once(NOW)
        assert stream.health().state != "error"
        stream.stop()

    def test_poll_error_is_recorded(self, tmp_path):
        """A stat failure during poll is recorded in health.

        We create Alice, scan to discover her, then delete the file
        and call _poll() directly (bypassing rescan which would retire
        her) to trigger a stat error.
        """
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        path = _log(
            tmp_path, "Alice", stem="20260825_113000_100", session="2026.08.25 11:30:00"
        )
        stream.scan_once(NOW)
        received.clear()
        # Delete Alice so poll's stat() fails — but skip rescan so she
        # remains in _tracked.
        path.unlink()
        with stream._op_lock:
            stream._poll()
        h = stream.health()
        assert h.state == "error"
        assert "source error" in h.detail
        stream.stop()

    def test_stale_after_three_poll_intervals(self, tmp_path):
        mono = [0.0]
        stream = GameLogStream(
            _thread_factory=_noop_thread_factory,
            _clock=lambda: mono[0],
        )
        _collect(stream)
        stream.start(tmp_path)
        _log(tmp_path, "Alice")
        stream.scan_once(NOW)
        # After a successful poll, health is active.
        assert stream.health().state == "active"
        # Advance clock past stale threshold.
        mono[0] = POLL_INTERVAL_S * 3 + 0.1
        assert stream.health().state == "stale"
        stream.stop()

    def test_stale_clears_after_successful_poll(self, tmp_path):
        mono = [0.0]
        stream = GameLogStream(
            _thread_factory=_noop_thread_factory,
            _clock=lambda: mono[0],
        )
        _collect(stream)
        stream.start(tmp_path)
        _log(tmp_path, "Alice")
        stream.scan_once(NOW)
        mono[0] = POLL_INTERVAL_S * 3 + 0.1
        assert stream.health().state == "stale"
        # Run another successful poll.
        stream.scan_once(NOW)
        assert stream.health().state == "active"
        stream.stop()


# ---------------------------------------------------------------------------
# Interface contracts
# ---------------------------------------------------------------------------


class TestInterface:
    def test_subscribe_returns_unsubscribe_callable(self, tmp_path):
        stream = _stream()
        received = []
        unsub = stream.subscribe(lambda e: received.append(e))
        stream.start(tmp_path)
        _log(tmp_path, "Alice")
        stream.scan_once(NOW)
        unsub()
        count = len(received)
        _log(tmp_path, "Bob", stem="20260825_113000_456", session="2026.08.25 11:30:00")
        stream.scan_once(NOW)
        assert len(received) == count

    def test_stop_is_idempotent(self, tmp_path):
        stream = _stream()
        stream.start(tmp_path)
        stream.stop()
        stream.stop()

    def test_start_is_idempotent(self, tmp_path):
        stream = _stream()
        stream.start(tmp_path)
        w1 = stream._worker
        stream.start(tmp_path)
        assert stream._worker is w1
        stream.stop()

    def test_request_source_known(self, tmp_path):
        _log(tmp_path, "Alice")
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        received.clear()
        stream.request_source("Alice")
        lcs = [e for e in received if isinstance(e, SourceLifecycle)]
        assert len(lcs) == 1
        assert lcs[0].active is True
        stream.stop()

    def test_request_source_unknown(self, tmp_path):
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        stream.request_source("Unknown")
        lcs = [e for e in received if isinstance(e, SourceLifecycle)]
        assert len(lcs) == 1
        assert lcs[0].available is False
        stream.stop()


# ---------------------------------------------------------------------------
# Dedup-before-cap (ported from Tailer)
# ---------------------------------------------------------------------------


class TestDedupBeforeCap:
    def test_dedup_runs_before_cap(self, tmp_path):
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
        stream = _stream()
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
    def test_incoming_damage(self, tmp_path):
        stream = _stream()
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

    def test_outgoing_damage(self, tmp_path):
        stream = _stream()
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

    def test_tackle_with_ownership(self, tmp_path):
        stream = _stream()
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
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(SCRAMBLE_LINE.format(target="Alice Renn [OXWLD]"))
        stream.scan_once(NOW)
        tackle = [
            e
            for e in received
            if isinstance(e, CombatFact) and e.kind == "incoming_tackle"
        ]
        assert len(tackle) == 1
        assert tackle[0].character == "Alice Renn"
        stream.stop()

    def test_fleet_broadcast_bystander(self, tmp_path):
        stream = _stream()
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
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(SCRAMBLE_LINE.format(target="Dave Kord [KVOS]"))
        stream.scan_once(NOW)
        assert [
            e
            for e in received
            if isinstance(e, CombatFact) and e.kind == "incoming_tackle"
        ] == []
        stream.stop()

    def test_undecodable_bytes(self, tmp_path):
        stream = _stream()
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
        assert len([e for e in received if isinstance(e, CombatFact)]) >= 1
        stream.stop()


# ---------------------------------------------------------------------------
# Worker lifecycle (real threads)
# ---------------------------------------------------------------------------


class TestWorker:
    def test_start_spawns_non_daemon_worker(self, tmp_path):
        stream = GameLogStream()
        stream.start(tmp_path)
        assert stream._worker is not None
        assert stream._worker.is_alive()
        assert stream._worker.daemon is False
        stream.stop()

    def test_stop_joins_within_timeout(self, tmp_path):
        stream = GameLogStream()
        stream.start(tmp_path)
        w = stream._worker
        t0 = time.monotonic()
        stream.stop(timeout=3.0)
        assert time.monotonic() - t0 < 3.0
        assert not w.is_alive()

    def test_fresh_stop_event_per_generation(self, tmp_path):
        stream = GameLogStream()
        stream.start(tmp_path)
        ev1 = stream._stop_event
        stream.stop()
        assert ev1.is_set()
        stream.start(tmp_path)
        ev2 = stream._stop_event
        assert ev2 is not ev1
        assert not ev2.is_set()
        stream.stop()

    def test_worker_polls_at_least_once(self, tmp_path):
        stream = GameLogStream()
        received = _collect(stream)
        _log(tmp_path, "Alice")
        stream.start(tmp_path)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if any(isinstance(e, SourceLifecycle) for e in received):
                break
            time.sleep(0.05)
        stream.stop()
        assert any(isinstance(e, SourceLifecycle) for e in received)

    def test_stop_idempotent_with_worker(self, tmp_path):
        stream = GameLogStream()
        stream.start(tmp_path)
        stream.stop()
        stream.stop()

    def test_start_stop_start_stop(self, tmp_path):
        stream = GameLogStream()
        stream.start(tmp_path)
        assert stream._worker.is_alive()
        stream.stop()
        stream.start(tmp_path)
        assert stream._worker.is_alive()
        stream.stop()

    def test_stop_retains_worker_on_timeout(self, tmp_path):
        """On timed-out join the worker is retained, not forgotten."""
        gate = threading.Event()

        def blocking_factory(*, target, args, name, daemon):
            def wrapper():
                gate.wait(timeout=10)
                target(*args)

            return threading.Thread(target=wrapper, name=name, daemon=daemon)

        stream = GameLogStream(_thread_factory=blocking_factory)
        stream.start(tmp_path)
        stream.stop(timeout=0.01)
        # Worker still alive and retained.
        assert stream._worker is not None
        assert stream._worker.is_alive()
        gate.set()
        stream._worker.join(timeout=5)

    def test_cadence_immediate_rescan_then_intervals(self, tmp_path):
        """Verify immediate rescan, 1s polls, 5s rescan via injected seams."""
        mono = [0.0]
        rescan_times = []
        poll_times = []
        waits = []
        stop_after = [8.5]

        class _FakeEvent:
            def __init__(self):
                self._set = False

            def is_set(self):
                return mono[0] >= stop_after[0]

            def set(self):
                self._set = True

            def wait(self, t):
                pass

        original_rescan = GameLogStream._rescan
        original_poll = GameLogStream._poll

        def patched_rescan(self, now_utc):
            rescan_times.append(mono[0])

        def patched_poll(self):
            poll_times.append(mono[0])

        def fake_wait(ev, t):
            waits.append(t)
            mono[0] += t

        stream = GameLogStream(
            _thread_factory=_noop_thread_factory,
            _clock=lambda: mono[0],
            _utc_now=lambda: NOW,
            _wait_fn=fake_wait,
        )
        stream._folder = tmp_path
        stream._started = True
        stop_ev = _FakeEvent()

        # Monkey-patch to track calls without I/O.
        GameLogStream._rescan = patched_rescan
        GameLogStream._poll = patched_poll
        try:
            stream._run(stop_ev)
        finally:
            GameLogStream._rescan = original_rescan
            GameLogStream._poll = original_poll

        # First rescan at t=0 (immediate).
        assert rescan_times[0] == 0.0
        # Polls at every iteration.
        assert poll_times[0] == 0.0
        # All waits are 1s.
        assert all(w == POLL_INTERVAL_S for w in waits)
        # Second rescan at t=5.
        assert rescan_times[1] == 5.0
        # Total iterations: 0,1,2,3,4,5,6,7,8 (stops at 8.5).
        assert len(poll_times) == 9


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_subscribe_unsubscribe_concurrent(self, tmp_path):
        stream = _stream()
        stream.start(tmp_path)
        _log(tmp_path, "Alice")
        barrier = threading.Event()

        def sub_unsub():
            barrier.wait(timeout=2)
            for _ in range(50):
                unsub = stream.subscribe(lambda e: None)
                unsub()

        t = threading.Thread(target=sub_unsub)
        t.start()
        barrier.set()
        for _ in range(50):
            stream.scan_once(NOW)
        t.join(timeout=5)
        assert not t.is_alive()
        stream.stop()

    def test_request_source_concurrent(self, tmp_path):
        stream = _stream()
        _collect(stream)
        stream.start(tmp_path)
        _log(tmp_path, "Alice")
        stream.scan_once(NOW)
        barrier = threading.Event()

        def requester():
            barrier.wait(timeout=2)
            for _ in range(50):
                stream.request_source("Alice")

        t = threading.Thread(target=requester)
        t.start()
        barrier.set()
        for _ in range(50):
            stream.scan_once(NOW)
        t.join(timeout=5)
        assert not t.is_alive()
        stream.stop()

    def test_health_concurrent(self, tmp_path):
        stream = _stream()
        stream.start(tmp_path)
        _log(tmp_path, "Alice")
        barrier = threading.Event()
        results = []

        def poller():
            barrier.wait(timeout=2)
            for _ in range(50):
                results.append(stream.health())

        t = threading.Thread(target=poller)
        t.start()
        barrier.set()
        for _ in range(50):
            stream.scan_once(NOW)
        t.join(timeout=5)
        assert not t.is_alive()
        assert len(results) == 50
        stream.stop()

    def test_no_facts_after_retirement(self, tmp_path):
        """After rescan retires a source, poll must not emit facts from it.
        The _op_lock serializes rescan then poll within scan_once, so
        retirement invalidates the tracked entry before poll reads it."""
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        path = _log(
            tmp_path, "Alice", stem="20260825_113000_100", session="2026.08.25 11:30:00"
        )
        stream.scan_once(NOW)
        # Append data that would produce a fact.
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(OUTGOING_DAMAGE_LINE)
        # Now remove the file so the rescan retires Alice before poll
        # gets to read.  In scan_once, rescan runs first (under _op_lock),
        # retiring Alice, then poll runs and finds Alice gone from _tracked.
        path.unlink()
        received.clear()
        stream.scan_once(NOW)
        retired = [
            e for e in received if isinstance(e, SourceLifecycle) and not e.active
        ]
        assert len(retired) == 1
        assert retired[0].character == "Alice"
        # No facts for Alice after her retirement.
        alice_facts = [
            e for e in received if isinstance(e, CombatFact) and e.character == "Alice"
        ]
        assert alice_facts == []
        stream.stop()
