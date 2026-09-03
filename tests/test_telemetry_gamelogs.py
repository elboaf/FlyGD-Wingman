"""Source-aware shared gamelog stream — tests.

Most tests use ``_noop_thread_factory`` so ``start()`` sets up state without
spawning a real thread, and ``scan_once()`` is called synchronously.  Only
``TestWorker`` uses real threads.
"""

import datetime
import os
import threading
import time

from wingman.telemetry.gamelogs import (
    MAX_AGE,
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


def _stream(**kw):
    """GameLogStream with noop thread factory for synchronous tests."""
    kw.setdefault("_thread_factory", _noop_thread_factory)
    return GameLogStream(**kw)


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
        lcs = [e for e in received if isinstance(e, SourceLifecycle)]
        assert len(lcs) == 1
        assert lcs[0].active is True
        assert lcs[0].character == "Alice"
        assert lcs[0].source_id.session_start_utc == datetime.datetime(
            2026, 8, 25, 11, 30, 0, tzinfo=UTC
        )
        stream.stop()

    def test_new_file_reads_from_zero(self, tmp_path):
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        _log(
            tmp_path,
            "Bravo",
            OUTGOING_DAMAGE_LINE,
            stem="20260825_113000_456",
            session="2026.08.25 11:30:00",
        )
        stream.scan_once(NOW)
        lcs = [e for e in received if isinstance(e, SourceLifecycle)]
        facts = [e for e in received if isinstance(e, CombatFact)]
        assert len(lcs) == 1 and lcs[0].active
        assert len(facts) == 1
        assert facts[0].source_generation == lcs[0].generation

    def test_lifecycle_before_facts(self, tmp_path):
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
        lc_i = next(i for i, e in enumerate(received) if isinstance(e, SourceLifecycle))
        f_i = next(i for i, e in enumerate(received) if isinstance(e, CombatFact))
        assert lc_i < f_i

    def test_facts_carry_matching_generation(self, tmp_path):
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

    def test_one_active_per_character(self, tmp_path):
        _log(tmp_path, "Alice", stem="20260825_100000_1", session="2026.08.25 10:00:00")
        _log(tmp_path, "Alice", stem="20260825_113000_1", session="2026.08.25 11:30:00")
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        active = [e for e in received if isinstance(e, SourceLifecycle) and e.active]
        assert len(active) == 1

    def test_preexisting_baselines_at_eof(self, tmp_path):
        _log(tmp_path, "Alice", OUTGOING_DAMAGE_LINE)
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        assert [e for e in received if isinstance(e, CombatFact)] == []

    def test_partial_line_buffered(self, tmp_path):
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        path = _log(
            tmp_path, "Alice", stem="20260825_113000_456", session="2026.08.25 11:30:00"
        )
        stream.scan_once(NOW)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(OUTGOING_DAMAGE_LINE[:40])
        stream.scan_once(NOW)
        assert [e for e in received if isinstance(e, CombatFact)] == []
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(OUTGOING_DAMAGE_LINE[40:])
        stream.scan_once(NOW)
        assert len([e for e in received if isinstance(e, CombatFact)]) == 1

    def test_truncation_retires_old_activates_new(self, tmp_path):
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        path = _log(
            tmp_path,
            "Alice",
            OUTGOING_DAMAGE_LINE * 10,
            stem="20260825_113000_456",
            session="2026.08.25 11:30:00",
        )
        stream.scan_once(NOW)
        orig_gen = next(
            e for e in received if isinstance(e, SourceLifecycle)
        ).generation
        received.clear()
        path.write_text(
            HEADER.format(name="Alice", session="2026.08.25 11:30:00")
            + OUTGOING_DAMAGE_LINE,
            encoding="utf-8",
        )
        stream.scan_once(NOW)
        lcs = [e for e in received if isinstance(e, SourceLifecycle)]
        assert len(lcs) == 2
        assert lcs[0].active is False and lcs[0].generation == orig_gen
        assert lcs[1].active is True and lcs[1].generation > orig_gen
        assert received.index(lcs[0]) < received.index(lcs[1])
        for f in [e for e in received if isinstance(e, CombatFact)]:
            assert f.source_generation == lcs[1].generation
        stream.stop()

    def test_retirement_before_replacement(self, tmp_path):
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        _log(tmp_path, "Alice", stem="20260825_100000_1", session="2026.08.25 10:00:00")
        stream.scan_once(NOW)
        orig = next(
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
        lcs = [e for e in received if isinstance(e, SourceLifecycle)]
        assert len(lcs) == 2
        assert lcs[0].active is False and lcs[0].generation == orig
        assert lcs[1].active is True and lcs[1].generation > orig
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
        path = _log(tmp_path, "Alice", OUTGOING_DAMAGE_LINE)
        old = (NOW - datetime.timedelta(hours=13)).timestamp()
        os.utime(path, (old, old))
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        assert [e for e in received if isinstance(e, SourceLifecycle)] == []

    def test_tied_session_breaks_on_mtime(self, tmp_path):
        _log(tmp_path, "Alice", stem="20260825_100000_1")
        _log(tmp_path, "Alice", stem="20260825_100000_2")
        os.utime(
            tmp_path / "20260825_100000_1.txt",
            ((NOW - datetime.timedelta(minutes=10)).timestamp(),) * 2,
        )
        os.utime(
            tmp_path / "20260825_100000_2.txt",
            ((NOW - datetime.timedelta(minutes=1)).timestamp(),) * 2,
        )
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        lcs = [e for e in received if isinstance(e, SourceLifecycle)]
        assert len(lcs) == 1
        assert "20260825_100000_2" in lcs[0].source_id.normalized_path


# ---------------------------------------------------------------------------
# Replay prevention and failure isolation
# ---------------------------------------------------------------------------


class TestReplayPrevention:
    def test_folder_loss_retires(self, tmp_path):
        import shutil

        folder = tmp_path / "gamelogs"
        folder.mkdir()
        _log(folder, "Alice")
        stream = _stream()
        received = _collect(stream)
        stream.start(folder)
        stream.scan_once(NOW)
        gen = next(
            e for e in received if isinstance(e, SourceLifecycle) and e.active
        ).generation
        received.clear()
        shutil.rmtree(folder)
        stream.scan_once(NOW)
        lcs = [e for e in received if isinstance(e, SourceLifecycle)]
        assert len(lcs) == 1 and not lcs[0].active and lcs[0].generation == gen

    def test_folder_recovery_no_replay(self, tmp_path):
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

    def test_cap_eviction_no_replay(self, tmp_path):
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
                f"C{i:03d}",
                stem=f"20260825_{h:02d}{m:02d}00_{i:03d}",
                session=f"2026.08.25 {h:02d}:{m:02d}:00",
            )
        stream.scan_once(NOW)
        assert "Alice" not in {
            e.character for e in received if isinstance(e, SourceLifecycle) and e.active
        }
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

    def test_stat_failure_then_recovery_no_replay(self, tmp_path):
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        alice = _log(
            tmp_path,
            "Alice",
            OUTGOING_DAMAGE_LINE,
            stem="20260825_113000_100",
            session="2026.08.25 11:30:00",
        )
        data = alice.read_bytes()
        alice.unlink()
        alice.symlink_to(tmp_path / "broken")
        stream.scan_once(NOW)
        assert [
            e
            for e in received
            if isinstance(e, SourceLifecycle) and e.character == "Alice"
        ] == []
        received.clear()
        alice.unlink()
        alice.write_bytes(data)
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

    def test_baseline_eof_stat_failure_defers_then_recovers(self, tmp_path):
        """Injected _get_file_size fails ONLY during EOF baseline for a
        known path.  Discovery stat (mtime) succeeds.  No activation, no
        retirement of old source.  On recovery, baseline at current EOF."""
        call_count = [0]
        real_size = GameLogStream.__init__.__kwdefaults__["_get_file_size"]

        def fail_second(path):
            call_count[0] += 1
            # Fail baseline calls (the ones inside the _lock reconcile).
            # Discovery stat happens via path.stat().st_mtime, not this seam.
            if call_count[0] == 1:
                raise OSError("injected baseline failure")
            return real_size(path)

        stream = _stream(_get_file_size=fail_second)
        received = _collect(stream)
        stream.start(tmp_path)
        # File present on first scan — known, needs EOF baseline via seam.
        _log(tmp_path, "Alice", OUTGOING_DAMAGE_LINE)
        stream.scan_once(NOW)
        # Baseline failed → not activated, no retirement, scan error recorded.
        assert [
            e for e in received if isinstance(e, SourceLifecycle) and e.active
        ] == []
        assert stream.health().state == "error"
        received.clear()
        # Second scan: seam succeeds → activated at EOF, no facts.
        stream.scan_once(NOW)
        assert [e for e in received if isinstance(e, CombatFact)] == []
        assert (
            len([e for e in received if isinstance(e, SourceLifecycle) and e.active])
            == 1
        )
        stream.stop()

    def test_failed_replacement_baseline_keeps_old_source(self, tmp_path):
        """If the replacement source's baseline stat fails, the old source
        stays tracked and no retirement is published."""
        calls = [0]
        real_size = GameLogStream.__init__.__kwdefaults__["_get_file_size"]

        def fail_third(path):
            # Call 1: old Alice EOF baseline on first scan.
            # Call 2: new Alice EOF baseline on second scan (skip).
            # (new Alice is known because her file existed during first scan
            #  but had the wrong header then; now it has the right one.)
            calls[0] += 1
            if calls[0] == 2:
                raise OSError("injected")
            return real_size(path)

        stream = _stream(_get_file_size=fail_third)
        received = _collect(stream)
        stream.start(tmp_path)
        # Create both files. Old Alice is valid; new one starts with EVE
        # listener (excluded from candidates but its path is tombstoned).
        _log(tmp_path, "Alice", stem="20260825_100000_1", session="2026.08.25 10:00:00")
        newer = tmp_path / "20260825_113000_1.txt"
        newer.write_text(
            HEADER.format(name="EVE", session="2026.08.25 11:30:00"),
            encoding="utf-8",
        )
        stream.scan_once(NOW)
        # Only old Alice activated (gen 1). newer was excluded (EVE).
        orig_gen = next(
            e for e in received if isinstance(e, SourceLifecycle) and e.active
        ).generation
        received.clear()
        # Rewrite the newer file with a real character — it is now known
        # (its path was in paths_this_scan on scan 1).
        newer.write_text(
            HEADER.format(name="Alice", session="2026.08.25 11:30:00")
            + OUTGOING_DAMAGE_LINE,
            encoding="utf-8",
        )
        stream.scan_once(NOW)
        # Baseline of the replacement fails (call #2) → no retirement.
        assert [
            e for e in received if isinstance(e, SourceLifecycle) and not e.active
        ] == []
        assert stream._tracked["Alice"].generation == orig_gen
        stream.stop()

    def test_genuinely_new_reads_from_zero(self, tmp_path):
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        _log(
            tmp_path,
            "New",
            OUTGOING_DAMAGE_LINE,
            stem="20260825_113000_NEW",
            session="2026.08.25 11:30:00",
        )
        stream.scan_once(NOW)
        assert (
            len(
                [
                    e
                    for e in received
                    if isinstance(e, CombatFact) and e.character == "New"
                ]
            )
            == 1
        )

    def test_per_source_error_does_not_suppress_others(self, tmp_path):
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
        assert (
            len(
                [
                    e
                    for e in received
                    if isinstance(e, CombatFact) and e.character == "Bob"
                ]
            )
            == 1
        )

    def test_subscriber_exception_isolation(self, tmp_path):
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

    def test_scan_error_clear_after_success(self, tmp_path):
        folder = tmp_path / "gamelogs"
        folder.mkdir()
        stream = _stream()
        stream.start(folder)
        stream.scan_once(NOW)
        broken = folder / "20260825_110000_bad.txt"
        broken.symlink_to(folder / "gone")
        stream.scan_once(NOW)
        assert stream.health().state == "error"
        broken.unlink()
        stream.scan_once(NOW)
        assert stream.health().state != "error"
        stream.stop()

    def test_header_exception_is_scan_error(self, tmp_path):
        """An injected header reader that raises is recorded as a scan error,
        distinct from a valid characterless stub returning None."""

        def exploding_header(path):
            raise OSError("injected header read failure")

        stream = _stream(_read_header=exploding_header)
        _collect(stream)
        stream.start(tmp_path)
        _log(tmp_path, "Alice")
        stream.scan_once(NOW)
        h = stream.health()
        assert h.state == "error"
        assert "scan error" in h.detail
        stream.stop()

    def test_baseline_stat_error_is_scan_error(self, tmp_path):
        def failing_size(path):
            raise OSError("injected baseline failure")

        stream = _stream(_get_file_size=failing_size)
        _collect(stream)
        stream.start(tmp_path)
        _log(tmp_path, "Alice")
        stream.scan_once(NOW)
        h = stream.health()
        assert h.state == "error"
        assert "scan error" in h.detail
        stream.stop()

    def test_poll_error_recorded(self, tmp_path):
        stream = _stream()
        _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        path = _log(
            tmp_path, "Alice", stem="20260825_113000_100", session="2026.08.25 11:30:00"
        )
        stream.scan_once(NOW)
        path.unlink()
        # Call _poll directly to bypass rescan which would retire Alice.
        stream._poll()
        stream._drain_queue()
        h = stream.health()
        assert h.state == "error" and "source error" in h.detail
        stream.stop()

    def test_poll_error_clears_after_success(self, tmp_path):
        stream = _stream()
        _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        path = _log(
            tmp_path, "Alice", stem="20260825_113000_100", session="2026.08.25 11:30:00"
        )
        stream.scan_once(NOW)
        path.unlink()
        stream._poll()
        stream._drain_queue()
        assert stream.health().state == "error"
        # Restore and do a full scan_once (rescan will retire Alice,
        # poll will have no errors).
        _log(
            tmp_path, "Alice", stem="20260825_113000_100", session="2026.08.25 11:30:00"
        )
        stream.scan_once(NOW)
        assert stream.health().state != "error"
        stream.stop()

    def test_stale_after_three_intervals(self, tmp_path):
        mono = [0.0]
        stream = _stream(_clock=lambda: mono[0])
        _collect(stream)
        stream.start(tmp_path)
        _log(tmp_path, "Alice")
        stream.scan_once(NOW)
        assert stream.health().state == "active"
        mono[0] = POLL_INTERVAL_S * 3 + 0.1
        assert stream.health().state == "stale"
        stream.stop()

    def test_stale_before_first_successful_poll(self, tmp_path):
        """Staleness works even before any successful poll by comparing
        against start time."""
        mono = [0.0]
        stream = _stream(_clock=lambda: mono[0])
        _collect(stream)
        stream.start(tmp_path)
        # No scan_once — no poll has ever succeeded.
        mono[0] = POLL_INTERVAL_S * 3 + 0.1
        assert stream.health().state == "stale"
        stream.stop()

    def test_stale_clears_after_poll(self, tmp_path):
        mono = [0.0]
        stream = _stream(_clock=lambda: mono[0])
        _collect(stream)
        stream.start(tmp_path)
        _log(tmp_path, "Alice")
        stream.scan_once(NOW)
        mono[0] = POLL_INTERVAL_S * 3 + 0.1
        assert stream.health().state == "stale"
        stream.scan_once(NOW)
        assert stream.health().state == "active"
        stream.stop()


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------


class TestInterface:
    def test_unsubscribe(self, tmp_path):
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

    def test_stop_idempotent(self, tmp_path):
        stream = _stream()
        stream.start(tmp_path)
        stream.stop()
        stream.stop()

    def test_start_idempotent(self, tmp_path):
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
        assert len(lcs) == 1 and lcs[0].active

    def test_request_source_unknown(self, tmp_path):
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        stream.request_source("Unknown")
        lcs = [e for e in received if isinstance(e, SourceLifecycle)]
        assert len(lcs) == 1 and not lcs[0].available


# ---------------------------------------------------------------------------
# Dedup-before-cap
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


# ---------------------------------------------------------------------------
# Combat fact parsing
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
        assert len(facts) == 1 and facts[0].kind == "incoming_damage"

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
        assert len(facts) == 1 and facts[0].amount == 299

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
            fh.write(b"\xff\xfe garbage\n" + OUTGOING_DAMAGE_LINE.encode("utf-8"))
        stream.scan_once(NOW)
        assert len([e for e in received if isinstance(e, CombatFact)]) >= 1


# ---------------------------------------------------------------------------
# Worker lifecycle (real threads)
# ---------------------------------------------------------------------------


class TestWorker:
    def test_non_daemon(self, tmp_path):
        stream = GameLogStream()
        stream.start(tmp_path)
        assert stream._worker is not None and not stream._worker.daemon
        stream.stop()

    def test_stop_joins(self, tmp_path):
        stream = GameLogStream()
        stream.start(tmp_path)
        w = stream._worker
        stream.stop(timeout=3.0)
        assert not w.is_alive()

    def test_fresh_stop_event(self, tmp_path):
        stream = GameLogStream()
        stream.start(tmp_path)
        ev1 = stream._stop_event
        stream.stop()
        assert ev1.is_set()
        stream.start(tmp_path)
        assert stream._stop_event is not ev1 and not stream._stop_event.is_set()
        stream.stop()

    def test_worker_polls(self, tmp_path):
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

    def test_start_stop_cycle(self, tmp_path):
        stream = GameLogStream()
        for _ in range(2):
            stream.start(tmp_path)
            assert stream._worker.is_alive()
            stream.stop()

    def test_timeout_retains_worker(self, tmp_path):
        gate = threading.Event()

        def blocking(*, target, args, name, daemon):
            def wrapper():
                gate.wait(timeout=10)
                target(*args)

            return threading.Thread(target=wrapper, name=name, daemon=daemon)

        stream = GameLogStream(_thread_factory=blocking)
        stream.start(tmp_path)
        stream.stop(timeout=0.01)
        assert stream._worker is not None and stream._worker.is_alive()
        gate.set()
        stream._worker.join(timeout=5)

    def test_timeout_blocks_start(self, tmp_path):
        """After a timed-out stop, start() refuses to launch a second worker."""
        gate = threading.Event()

        def blocking(*, target, args, name, daemon):
            def wrapper():
                gate.wait(timeout=10)
                target(*args)

            return threading.Thread(target=wrapper, name=name, daemon=daemon)

        stream = GameLogStream(_thread_factory=blocking)
        stream.start(tmp_path)
        w1 = stream._worker
        stream.stop(timeout=0.01)
        assert stream._worker is w1  # retained
        stream.start(tmp_path)  # refused — worker alive
        assert stream._worker is w1  # same worker
        gate.set()
        w1.join(timeout=5)
        # Now worker is dead; start succeeds.
        stream.start(tmp_path)
        assert stream._worker is not w1
        stream.stop()

    def test_timed_out_stop_cleared_by_retry_then_fresh_start(self, tmp_path):
        """A timed-out stop retains the worker; a later stop (after the worker
        can finish) clears it, and only then does start create exactly one new
        worker and one new stop event.  The retained worker is never joined
        manually here — the retry stop must do it."""
        gate = threading.Event()
        created = []

        def blocking(*, target, args, name, daemon):
            def wrapper():
                gate.wait(timeout=10)
                target(*args)

            thread = threading.Thread(target=wrapper, name=name, daemon=daemon)
            created.append(thread)
            return thread

        stream = GameLogStream(_thread_factory=blocking)
        stream.start(tmp_path)
        w1 = stream._worker
        ev1 = stream._stop_event
        stream.stop(timeout=0.01)
        assert stream._worker is w1 and w1.is_alive()  # retained on timeout
        assert len(created) == 1

        # Release the worker and retry stop: the retry must join and clear it.
        gate.set()
        stream.stop(timeout=5.0)
        assert stream._worker is None
        assert not w1.is_alive()
        assert len(created) == 1  # stop never creates a worker

        # Fresh start: exactly one new worker, one new unset stop event.
        stream.start(tmp_path)
        w2 = stream._worker
        assert w2 is not None and w2 is not w1 and w2.is_alive()
        assert len(created) == 2
        assert stream._stop_event is not ev1 and not stream._stop_event.is_set()

        stream.start(tmp_path)  # idempotent: still exactly one worker
        assert stream._worker is w2 and len(created) == 2
        stream.stop(timeout=5.0)
        assert stream._worker is None

    def test_cadence(self, tmp_path):
        mono = [0.0]
        rescan_t, poll_t, waits = [], [], []

        class _FakeEv:
            def is_set(self):
                return mono[0] >= 8.5

            def set(self):
                pass

            def wait(self, t):
                pass

        orig_rescan = GameLogStream._rescan
        orig_poll = GameLogStream._poll
        GameLogStream._rescan = lambda self, u: rescan_t.append(mono[0])
        GameLogStream._poll = lambda self: poll_t.append(mono[0])

        def fake_wait(ev, t):
            waits.append(t)
            mono[0] += t

        stream = _stream(
            _clock=lambda: mono[0], _utc_now=lambda: NOW, _wait_fn=fake_wait
        )
        stream._folder = tmp_path
        stream._started = True
        try:
            stream._run(_FakeEv())
        finally:
            GameLogStream._rescan = orig_rescan
            GameLogStream._poll = orig_poll

        assert rescan_t[0] == 0.0
        assert rescan_t[1] == 5.0
        assert all(w == POLL_INTERVAL_S for w in waits)
        assert len(poll_t) == 9


# ---------------------------------------------------------------------------
# Thread safety and publication order
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_subscribe_concurrent(self, tmp_path):
        stream = _stream()
        stream.start(tmp_path)
        _log(tmp_path, "Alice")
        barrier = threading.Event()

        def sub_unsub():
            barrier.wait(timeout=2)
            for _ in range(50):
                stream.subscribe(lambda e: None)()

        t = threading.Thread(target=sub_unsub)
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
        assert len(results) == 50
        stream.stop()

    def test_no_facts_after_retirement(self, tmp_path):
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        path = _log(
            tmp_path, "Alice", stem="20260825_113000_100", session="2026.08.25 11:30:00"
        )
        stream.scan_once(NOW)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(OUTGOING_DAMAGE_LINE)
        path.unlink()
        received.clear()
        stream.scan_once(NOW)
        retired = [
            e for e in received if isinstance(e, SourceLifecycle) and not e.active
        ]
        assert len(retired) == 1
        assert [
            e for e in received if isinstance(e, CombatFact) and e.character == "Alice"
        ] == []

    def test_reentrant_callback_cannot_precede_later_activations(self, tmp_path):
        """Two sources activate in one batch.  A subscriber that reenters
        request_source/scan_once on the FIRST activation must not cause the
        fact batch to be published before the second activation."""
        stream = _stream()
        received = _collect(stream)
        reentered = []

        def reentrant_sub(event):
            if isinstance(event, SourceLifecycle) and event.active and not reentered:
                reentered.append(True)
                stream.request_source("Unknown")
                stream.scan_once(NOW)

        stream.subscribe(reentrant_sub)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        _log(
            tmp_path,
            "Alice",
            OUTGOING_DAMAGE_LINE,
            stem="20260825_113000_1",
            session="2026.08.25 11:30:00",
        )
        _log(
            tmp_path,
            "Bravo",
            OUTGOING_DAMAGE_LINE,
            stem="20260825_113000_2",
            session="2026.08.25 11:30:00",
        )
        stream.scan_once(NOW)
        assert reentered  # the reentrant path really ran
        activations = [
            i
            for i, e in enumerate(received)
            if isinstance(e, SourceLifecycle) and e.active
        ]
        facts = [i for i, e in enumerate(received) if isinstance(e, CombatFact)]
        assert len(activations) == 2
        assert len(facts) == 2
        assert max(activations) < min(facts)
        # The reentrant request_source publishes strictly after both batches.
        unknown_i = next(
            i
            for i, e in enumerate(received)
            if isinstance(e, SourceLifecycle) and e.character == "Unknown"
        )
        assert unknown_i > max(facts)

    def test_single_drainer_under_concurrent_callers(self, tmp_path):
        """Two threads run operations concurrently: exactly one drains, the
        batches stay FIFO, and the second caller's batch is not stranded."""
        stream = _stream()
        delivered = []
        drainer_idents = set()
        entered = threading.Event()
        proceed = threading.Event()

        def blocking_sub(event):
            drainer_idents.add(threading.get_ident())
            delivered.append(event)
            if (
                isinstance(event, SourceLifecycle)
                and event.character == "Alice"
                and event.active
            ):
                entered.set()
                proceed.wait(timeout=5)

        stream.subscribe(blocking_sub)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        _log(
            tmp_path,
            "Alice",
            OUTGOING_DAMAGE_LINE,
            stem="20260825_113000_1",
            session="2026.08.25 11:30:00",
        )

        a_ident = []

        def caller_a():
            a_ident.append(threading.get_ident())
            stream.scan_once(NOW)

        ta = threading.Thread(target=caller_a)
        ta.start()
        assert entered.wait(timeout=5)

        # Caller B runs a whole operation while A owns delivery.  B must
        # enqueue and return without publishing anything itself.
        _log(
            tmp_path,
            "Bravo",
            OUTGOING_DAMAGE_LINE,
            stem="20260825_113000_2",
            session="2026.08.25 11:30:00",
        )
        stream.scan_once(NOW)
        assert [e for e in delivered if e.character == "Bravo"] == []

        proceed.set()
        ta.join(timeout=5)
        assert not ta.is_alive()
        # One drainer only, and B's batches were delivered (not stranded).
        assert drainer_idents == {a_ident[0]}
        assert [(type(e).__name__, e.character) for e in delivered] == [
            ("SourceLifecycle", "Alice"),
            ("CombatFact", "Alice"),
            ("SourceLifecycle", "Bravo"),
            ("CombatFact", "Bravo"),
        ]
        stream.stop()

    def test_no_fact_after_retirement_under_contention(self, tmp_path):
        """A poll gated between rescan and poll holds the operation lock while
        another thread tries to retire the same source.  Whoever acquires
        first publishes first, and no old-source fact may follow its
        retirement in external order."""
        stream = _stream()
        received = _collect(stream)
        stream.start(tmp_path)
        stream.scan_once(NOW)
        path = _log(
            tmp_path, "Alice", stem="20260825_113000_1", session="2026.08.25 11:30:00"
        )
        stream.scan_once(NOW)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(OUTGOING_DAMAGE_LINE)
        received.clear()

        in_poll = threading.Event()
        release = threading.Event()
        real_poll = stream._poll

        def gated_poll():
            in_poll.set()
            release.wait(timeout=5)
            real_poll()

        stream._poll = gated_poll
        b_done = threading.Event()

        def retire_caller():
            stream.scan_once(NOW)
            b_done.set()

        ta = threading.Thread(target=lambda: stream.scan_once(NOW))
        ta.start()
        assert in_poll.wait(timeout=5)
        # A is past its rescan, holding the operation lock in the gate.  Age
        # Alice out so B's rescan retires her while A's facts are unpublished.
        old = (NOW - MAX_AGE - datetime.timedelta(minutes=1)).timestamp()
        os.utime(path, (old, old))
        tb = threading.Thread(target=retire_caller)
        tb.start()
        time.sleep(0.1)
        # B cannot have finished: it is blocked on the operation lock A holds.
        assert not b_done.is_set()
        release.set()
        ta.join(timeout=5)
        tb.join(timeout=5)
        assert not ta.is_alive() and not tb.is_alive()

        retire_i = next(
            i
            for i, e in enumerate(received)
            if isinstance(e, SourceLifecycle)
            and e.character == "Alice"
            and not e.active
        )
        fact_i = [
            i
            for i, e in enumerate(received)
            if isinstance(e, CombatFact) and e.character == "Alice"
        ]
        assert fact_i, "the gated poll should still have published its fact"
        assert max(fact_i) < retire_i
        stream.stop()

    def test_reentrant_request_source_during_dispatch(self, tmp_path):
        """A subscriber that calls request_source during dispatch must not
        interleave its events into the current batch.  The request_source
        lifecycle must appear after the current batch in external order."""
        stream = _stream()
        received = _collect(stream)
        requested = []

        def reentrant_sub(event):
            if isinstance(event, SourceLifecycle) and event.active and not requested:
                requested.append(True)
                stream.request_source("Unknown")

        stream.subscribe(reentrant_sub)
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
        # The request_source lifecycle for "Unknown" must appear after
        # Alice's activation and fact, not interleaved.
        alice_lc_i = next(
            i
            for i, e in enumerate(received)
            if isinstance(e, SourceLifecycle) and e.character == "Alice" and e.active
        )
        alice_fact_i = next(
            i
            for i, e in enumerate(received)
            if isinstance(e, CombatFact) and e.character == "Alice"
        )
        unknown_i = next(
            i
            for i, e in enumerate(received)
            if isinstance(e, SourceLifecycle) and e.character == "Unknown"
        )
        assert alice_lc_i < alice_fact_i < unknown_i
        stream.stop()
