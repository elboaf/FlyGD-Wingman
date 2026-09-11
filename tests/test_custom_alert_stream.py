"""Custom matching uses the shared producer's real file and delivery boundaries."""

import datetime
import os
import threading
from dataclasses import fields

import pytest

from tests.test_telemetry_gamelogs import (
    DAMAGE_LINE,
    HEADER,
    MAX_AGE,
    NOW,
    OUTGOING_DAMAGE_LINE,
    SCRAMBLE_LINE,
    _AttemptSignallingLock,
    _log,
    _stream,
)
from wingman import settings
from wingman.alerts import custom
from wingman.alerts.custom import prepare_alert_snapshot
from wingman.telemetry import gamelogs
from wingman.telemetry.model import CombatFact, SourceLifecycle


def test_custom_lines_obey_eof_and_newline(tmp_path):
    preview = settings.validated_preview(
        {
            "enabled": True,
            "alerts": {
                "enabled": True,
                "custom_rules": [
                    {
                        "id": "r1",
                        "name": "Fleet",
                        "search": "fleet invite",
                        "enabled": True,
                    }
                ],
            },
        }
    )
    snapshot = prepare_alert_snapshot(preview)
    path = _log(tmp_path, "Alice", "(notify) fleet invite\n")
    stream = _stream(custom_snapshot=lambda: snapshot)
    batches = []
    stream.subscribe_batches(batches.append)
    try:
        stream.start(tmp_path)
        stream.scan_once(NOW)
        assert not [m for b in batches for m in b.custom_matches]
        with path.open("a", encoding="utf-8") as output:
            output.write("(notify) FLEET INVITE")
        stream.scan_once(NOW)
        assert not [m for b in batches for m in b.custom_matches]
        with path.open("a", encoding="utf-8") as output:
            output.write("\n")
        stream.scan_once(NOW)
        matches = [m for b in batches for m in b.custom_matches]
        assert [(m.character, m.rule_id) for m in matches] == [("Alice", "r1")]
        assert matches[0].generation == snapshot.custom_rules[0].generation
        lifecycle = next(
            e for b in batches for e in b.events if isinstance(e, SourceLifecycle)
        )
        assert matches[0].source_id == lifecycle.source_id
        assert matches[0].source_generation == lifecycle.generation
        assert matches[0].activation_epoch == snapshot.activation_epoch
        assert {field.name for field in fields(matches[0])} == {
            "character",
            "source_generation",
            "source_id",
            "rule_id",
            "generation",
            "activation_epoch",
        }
        stream.scan_once(NOW)
        assert [m for b in batches for m in b.custom_matches] == matches
    finally:
        stream.stop()


def _preview(search="fleet invite"):
    return settings.validated_preview(
        {
            "enabled": True,
            "alerts": {
                "enabled": True,
                "custom_rules": [
                    {"id": "r1", "name": "Fleet", "search": search, "enabled": True}
                ],
            },
        }
    )


def _append(path, text):
    with path.open("a", encoding="utf-8") as output:
        output.write(text)


def _matches(batches):
    return [match for batch in batches for match in batch.custom_matches]


def _events(batches):
    return [event for batch in batches for event in batch.events]


@pytest.mark.parametrize(
    "prefix, character, suffix, cut, search",
    [
        ("Stra", "ß", "e", 1, "STRASSE"),
        ("ISK ", "€", "100", 1, "ISK €100"),
        ("ISK ", "€", "100", 2, "ISK €100"),
        ("fleet ", "🚀", "", 1, "fleet 🚀"),
        ("fleet ", "🚀", "", 2, "fleet 🚀"),
        ("fleet ", "🚀", "", 3, "fleet 🚀"),
    ],
)
def test_split_utf8_matches_only_after_the_complete_line(
    tmp_path, prefix, character, suffix, cut, search
):
    snapshot = prepare_alert_snapshot(_preview(search))
    stream = _stream(custom_snapshot=lambda: snapshot)
    path = _log(tmp_path, "Alice")
    batches = []
    stream.subscribe_batches(batches.append)
    encoded = character.encode("utf-8")
    try:
        stream.start(tmp_path)
        stream.scan_once(NOW)
        with path.open("ab") as output:
            output.write(("(notify) " + prefix).encode("utf-8") + encoded[:cut])
        stream.scan_once(NOW)
        stream.scan_once(NOW)  # Idle EOF is not the end of an encoded character.
        assert not _matches(batches)
        with path.open("ab") as output:
            output.write(encoded[cut:] + suffix.encode("utf-8"))
        stream.scan_once(NOW)
        assert not _matches(batches)
        _append(path, "\n")
        stream.scan_once(NOW)
        assert [(m.character, m.rule_id) for m in _matches(batches)] == [
            ("Alice", "r1")
        ]
        stream.scan_once(NOW)
        assert len(_matches(batches)) == 1
        assert stream._tracked["Alice"].partial == ""
    finally:
        stream.stop()


@pytest.mark.parametrize("newline, retained_cr", [(b"\n", ""), (b"\r\n", "\r")])
def test_split_utf8_decoder_is_source_local_and_malformed_bytes_still_replace(
    tmp_path, newline, retained_cr
):
    snapshot = prepare_alert_snapshot(_preview("Straße"))
    lines = []

    def observe(line, projection):
        lines.append(line)
        return custom.match_line(line, projection)

    stream = _stream(custom_snapshot=lambda: snapshot, custom_matcher=observe)
    alice = _log(tmp_path, "Alice", stem="alice")
    bob = _log(tmp_path, "Bob", stem="bob")
    batches = []
    stream.subscribe_batches(batches.append)
    try:
        stream.start(tmp_path)
        stream.scan_once(NOW)
        with alice.open("ab") as output:
            output.write(b"(notify) Stra\xc3")
        stream.scan_once(NOW)
        with bob.open("ab") as output:
            output.write(b"\x9fe\ninvalid \xff\xe2")
        stream.scan_once(NOW)
        assert lines == ["�e"]
        # Match the exact bytes under test, not the host's text-mode newline.
        with bob.open("ab") as output:
            output.write(newline)
        stream.scan_once(NOW)
        assert lines == ["�e", "invalid ��" + retained_cr]
        assert not _matches(batches)
        with alice.open("ab") as output:
            output.write(b"\x9fe\n")
        stream.scan_once(NOW)
        assert lines[-1] == "(notify) Straße"
        assert [(m.character, m.rule_id) for m in _matches(batches)] == [
            ("Alice", "r1")
        ]
    finally:
        stream.stop()


@pytest.mark.parametrize("newline, retained_cr", [(b"\n", ""), (b"\r\n", "\r")])
@pytest.mark.parametrize("reset", ["truncated", "known", "new", "retired", "restart"])
def test_pending_utf8_and_partial_text_reset_at_source_boundaries(
    tmp_path, reset, newline, retained_cr
):
    snapshot = prepare_alert_snapshot(_preview("fleet invite"))
    lines = []

    def observe(line, projection):
        lines.append(line)
        return custom.match_line(line, projection)

    stream = _stream(custom_snapshot=lambda: snapshot, custom_matcher=observe)
    path = _log(tmp_path, "Alice", "fleet invite\n" * 20)
    if reset == "known":
        _log(tmp_path, "EVE", stem="replacement", session="2026.08.25 11:30:00")
    batches = []
    stream.subscribe_batches(batches.append)
    try:
        stream.start(tmp_path)
        stream.scan_once(NOW)
        with path.open("ab") as output:
            output.write(b"old partial\xc3")
        stream.scan_once(NOW)
        assert lines == []
        if reset == "truncated":
            path.write_text(
                HEADER.format(name="Alice", session="2026.08.25 11:00:00"),
                encoding="utf-8",
            )
        elif reset == "restart":
            assert stream.stop()
            assert stream.start(tmp_path)
        elif reset == "retired":
            expired = (NOW - MAX_AGE - datetime.timedelta(minutes=1)).timestamp()
            os.utime(path, (expired, expired))
            stream.scan_once(NOW)
            os.utime(path, (NOW.timestamp(), NOW.timestamp()))
        else:
            path = _log(
                tmp_path, "Alice", stem="replacement", session="2026.08.25 11:30:00"
            )
        stream.scan_once(NOW)
        lines.clear()  # New-path headers retain their existing byte-zero behavior.
        assert not _matches(batches)
        with path.open("ab") as output:
            output.write(b"fleet invite" + newline)
        stream.scan_once(NOW)
        assert lines == ["fleet invite" + retained_cr]
        assert len(_matches(batches)) == 1
    finally:
        stream.stop()


@pytest.mark.parametrize(
    "inactive", ["preview", "alerts", "rules", "blank", "no_provider"]
)
def test_inactive_matching_never_normalizes_but_fleet_still_reads(
    tmp_path, monkeypatch, inactive
):
    preview = _preview()
    if inactive == "preview":
        preview["enabled"] = False
    elif inactive == "alerts":
        preview["alerts"]["enabled"] = False
    elif inactive == "rules":
        preview["alerts"]["custom_rules"][0]["enabled"] = False
    elif inactive == "blank":
        preview["alerts"]["custom_rules"][0].update(search="", enabled=False)
    snapshot = prepare_alert_snapshot(preview)
    calls = []
    normalize = custom.normalize_visible

    def spy(line):
        calls.append(line)
        return normalize(line)

    monkeypatch.setattr(custom, "normalize_visible", spy)
    stream = _stream(
        custom_snapshot=None if inactive == "no_provider" else lambda: snapshot
    )
    path = _log(tmp_path, "Alice")
    batches = []
    stream.subscribe_batches(batches.append)
    try:
        stream.start(tmp_path)
        stream.scan_once(NOW)
        _append(path, OUTGOING_DAMAGE_LINE)
        stream.scan_once(NOW)
        assert [e.amount for e in _events(batches) if isinstance(e, CombatFact)] == [
            299
        ]
        assert not _matches(batches)
        assert calls == []
        assert stream.custom_health().state == "inactive"
    finally:
        stream.stop()


def test_matcher_failure_is_private_and_semantics_continue_then_zero_match_recovers(
    tmp_path, caplog
):
    snapshot = prepare_alert_snapshot(_preview())
    failing = [True]
    notifications = []

    def matcher(line, projection):
        if failing[0]:
            raise RuntimeError("PRIVATE SEARCH AND LINE " + line)
        return custom.match_line(line, projection)

    stream = _stream(
        custom_snapshot=lambda: snapshot,
        custom_matcher=matcher,
        on_matcher_health=notifications.append,
    )
    path = _log(tmp_path, "Alice")
    batches, legacy = [], []
    stream.subscribe_batches(batches.append)
    stream.subscribe(legacy.append)
    try:
        assert stream.custom_health().state == "waiting"
        stream.start(tmp_path)
        stream.scan_once(NOW)
        _append(path, OUTGOING_DAMAGE_LINE + DAMAGE_LINE)
        stream.scan_once(NOW)
        assert [e.kind for e in legacy if isinstance(e, CombatFact)] == [
            "outgoing_damage",
            "incoming_damage",
        ]
        assert _events(batches) == legacy
        assert stream.health().state == "active"
        assert stream.custom_health().state == "degraded"
        assert stream.custom_health().detail == "Custom matching failed."
        assert "PRIVATE" not in caplog.text
        assert "Bob Smith" not in caplog.text
        assert [h.state for h in notifications] == ["degraded"]
        stream.scan_once(NOW)
        assert stream.custom_health().state == "degraded"
        failing[0] = False
        _append(path, "(notify) unrelated visible text\n")
        stream.scan_once(NOW)
        assert not _matches(batches)
        assert stream.custom_health().state == "active"
        assert [h.state for h in notifications] == ["degraded", "active"]
        stream.scan_once(NOW)
        assert len(notifications) == 2
    finally:
        stream.stop()


def test_committed_edit_and_inactivity_do_not_recover_degradation(tmp_path):
    document = {"preview": _preview()}
    reader = settings.committed_preview(document)
    failing = [True]

    def matcher(line, snapshot):
        if failing[0]:
            raise ValueError("private")
        return custom.match_line(line, snapshot)

    stream = _stream(custom_snapshot=reader.alerts_snapshot, custom_matcher=matcher)
    path = _log(tmp_path, "Alice")
    try:
        stream.start(tmp_path)
        stream.scan_once(NOW)
        _append(path, "(notify) fleet invite\n")
        stream.scan_once(NOW)
        assert stream.custom_health().state == "degraded"
        with settings.update(document, tmp_path / "settings.json"):
            document["preview"]["alerts"]["custom_rules"][0]["search"] = "new query"
        stream.scan_once(NOW)
        assert stream.custom_health().state == "degraded"
        with settings.update(document, tmp_path / "settings.json"):
            document["preview"]["alerts"]["enabled"] = False
        assert stream.custom_health().state == "inactive"
        stream.scan_once(NOW)
        with settings.update(document, tmp_path / "settings.json"):
            document["preview"]["alerts"]["enabled"] = True
        assert stream.custom_health().state == "degraded"
        failing[0] = False
        _append(path, "unrelated\n")
        stream.scan_once(NOW)
        assert stream.custom_health().state == "active"
        with settings.update(document, tmp_path / "settings.json"):
            document["preview"]["alerts"]["custom_rules"][0]["name"] = "Renamed"
        assert stream.custom_health().state == "waiting"
    finally:
        stream.stop()


@pytest.mark.parametrize("stale_fails", [False, True])
def test_outcome_from_edited_invocation_is_not_current(tmp_path, stale_fails):
    preview = _preview()
    current = [prepare_alert_snapshot(preview)]
    entered, release = threading.Event(), threading.Event()
    mode = ["fail"]

    def matcher(line, snapshot):
        if mode[0] == "block":
            entered.set()
            assert release.wait(5)
            if stale_fails:
                raise ValueError("private old query")
            return custom.match_line(line, snapshot)
        if mode[0] == "fail":
            raise ValueError("private")
        return ()

    stream = _stream(custom_snapshot=lambda: current[0], custom_matcher=matcher)
    path = _log(tmp_path, "Alice")
    batches = []
    stream.subscribe_batches(batches.append)
    worker = None
    try:
        stream.start(tmp_path)
        stream.scan_once(NOW)
        _append(path, "fleet invite\n")
        stream.scan_once(NOW)
        assert stream.custom_health().state == "degraded"
        mode[0] = "block"
        _append(path, "fleet invite\n")
        worker = threading.Thread(target=lambda: stream.scan_once(NOW))
        worker.start()
        assert entered.wait(5)
        preview["alerts"]["custom_rules"][0]["name"] = "Changed"
        current[0] = prepare_alert_snapshot(preview, current[0])
        release.set()
        worker.join(5)
        assert not worker.is_alive()
        assert stream.custom_health().state == "degraded"
        assert not _matches(batches)
        mode[0] = "success"
        _append(path, "unrelated\n")
        stream.scan_once(NOW)
        health = stream.custom_health()
        assert health.state == "active"
        assert health.rules_revision == current[0].rules_revision
    finally:
        release.set()
        if worker is not None:
            worker.join(5)
        stream.stop()


@pytest.mark.parametrize("change", ["revision", "epoch"])
def test_commit_while_health_acceptance_waits_rejects_stale_success(tmp_path, change):
    preview = _preview()
    current = [prepare_alert_snapshot(preview)]
    entered, release = threading.Event(), threading.Event()
    recovering = [False]

    def matcher(line, snapshot):
        if not recovering[0]:
            raise ValueError("private")
        gate.watch(threading.get_ident())
        entered.set()
        assert release.wait(5)
        return ()

    stream = _stream(custom_snapshot=lambda: current[0], custom_matcher=matcher)
    gate = _AttemptSignallingLock(stream._dispatch_lock)
    stream._dispatch_lock = gate
    path = _log(tmp_path, "Alice")
    worker = None
    try:
        stream.start(tmp_path)
        stream.scan_once(NOW)
        _append(path, "fleet invite\n")
        stream.scan_once(NOW)
        assert stream.custom_health().state == "degraded"
        recovering[0] = True
        _append(path, "no match\n")
        worker = threading.Thread(target=lambda: stream.scan_once(NOW))
        worker.start()
        assert entered.wait(5)
        with gate:
            release.set()
            assert gate.attempted.wait(5)
            if change == "revision":
                preview["alerts"]["custom_rules"][0]["name"] = "Changed"
            else:
                preview["alerts"]["enabled"] = False
                current[0] = prepare_alert_snapshot(preview, current[0])
                preview["alerts"]["enabled"] = True
            current[0] = prepare_alert_snapshot(preview, current[0])
        worker.join(5)
        assert not worker.is_alive()
        assert stream.custom_health().state == "degraded"
    finally:
        release.set()
        if worker is not None:
            worker.join(5)
        stream.stop()


def test_visible_matching_uses_all_listeners_not_semantic_target_or_pve_filter(
    tmp_path,
):
    preview = _preview("warp scramble attempt")
    preview["alerts"]["custom_rules"].append(
        {**preview["alerts"]["custom_rules"][0], "id": "r2", "search": "misses you"}
    )
    snapshot = prepare_alert_snapshot(preview)
    stream = _stream(custom_snapshot=lambda: snapshot)
    batches = []
    stream.subscribe_batches(batches.append)
    paths = [_log(tmp_path, name, stem=name) for name in ("Alice", "Bravo")]
    try:
        stream.start(tmp_path)
        stream.scan_once(NOW)
        for path in paths:
            _append(
                path,
                SCRAMBLE_LINE.format(target="Alice [OXWLD]")
                + "[ 2026.02.30 12:34:56 ] (combat) Sleepless Patroller misses you\n",
            )
        stream.scan_once(NOW)
        assert {(m.character, m.rule_id) for m in _matches(batches)} == {
            ("Alice", "r1"),
            ("Alice", "r2"),
            ("Bravo", "r1"),
            ("Bravo", "r2"),
        }
        facts = [e for e in _events(batches) if isinstance(e, CombatFact)]
        assert [(e.character, e.kind) for e in facts if e.kind == "incoming_scram"] == [
            ("Alice", "incoming_scram")
        ]
        misses = [e for e in facts if e.kind == "incoming_miss"]
        assert len(misses) == 2 and all(e.occurred_at is None for e in misses)
    finally:
        stream.stop()


@pytest.mark.parametrize("replacement", ["truncated", "known", "new", "retired"])
def test_source_replacement_keeps_existing_replay_rules(tmp_path, replacement):
    snapshot = prepare_alert_snapshot(_preview())
    stream = _stream(custom_snapshot=lambda: snapshot)
    batches = []
    stream.subscribe_batches(batches.append)
    old = _log(tmp_path, "Alice", "fleet invite\n" * 20)
    if replacement == "known":
        _log(tmp_path, "EVE", stem="replacement", session="2026.08.25 11:30:00")
    try:
        stream.start(tmp_path)
        stream.scan_once(NOW)
        original = _events(batches)[0]
        batches.clear()
        if replacement == "truncated":
            path = old
            old.write_text(
                HEADER.format(name="Alice", session="2026.08.25 11:00:00")
                + "fleet invite\n",
                encoding="utf-8",
            )
        elif replacement == "retired":
            path = old
            expired = (NOW - MAX_AGE - datetime.timedelta(minutes=1)).timestamp()
            os.utime(old, (expired, expired))
            stream.scan_once(NOW)
            _append(old, "fleet invite\n")
        else:
            path = _log(
                tmp_path,
                "Alice",
                "fleet invite\n",
                stem="replacement",
                session="2026.08.25 11:30:00",
            )
        stream.scan_once(NOW)
        assert len(_matches(batches)) == (1 if replacement == "new" else 0)
        lifecycles = [e for e in _events(batches) if isinstance(e, SourceLifecycle)]
        assert [e.active for e in lifecycles] == [False, True]
        assert lifecycles[0].generation == original.generation
        assert lifecycles[1].generation > original.generation
        batches.clear()
        _append(path, "fleet invite\n")
        stream.scan_once(NOW)
        match = _matches(batches)[0]
        assert match.source_generation == lifecycles[1].generation
        assert match.source_id == lifecycles[1].source_id
        stream.request_source("Alice")
        stream.scan_once(NOW)
        assert _matches(batches) == [match]
    finally:
        stream.stop()


def test_batch_callbacks_are_additive_reentrant_and_failure_isolated(tmp_path, caplog):
    snapshot = prepare_alert_snapshot(_preview("hits"))
    stream = _stream(custom_snapshot=lambda: snapshot)
    batches, legacy, failures = [], [], []

    def fail(batch):
        failures.append(True)
        raise RuntimeError("PRIVATE callback data")

    def reenter(batch):
        if batch.custom_matches:
            stream.request_source("Unknown")
            stream.scan_once(NOW)

    stream.subscribe(legacy.append)
    unsub = stream.subscribe_batches(fail)
    stream.subscribe_batches(reenter)
    stream.subscribe_batches(batches.append)
    try:
        stream.start(tmp_path)
        stream.scan_once(NOW)
        _log(tmp_path, "Alice", OUTGOING_DAMAGE_LINE)
        stream.scan_once(NOW)
        assert [type(e) for e in legacy] == [
            SourceLifecycle,
            CombatFact,
            SourceLifecycle,
        ]
        assert legacy[-1].character == "Unknown"
        assert _events(batches) == legacy
        assert len(_matches(batches)) == 1
        assert "PRIVATE" not in caplog.text
        count = len(failures)
        unsub()
        unsub()
        stream.request_source("Alice")
        assert len(failures) == count
    finally:
        stream.stop()


def test_health_callbacks_run_outside_all_stream_locks_and_cannot_break_delivery(
    tmp_path, caplog
):
    snapshot = prepare_alert_snapshot(_preview())
    notifications, batches, unlocked = [], [], []

    def health_changed(health):
        for lock in (stream._op_lock, stream._lock, stream._dispatch_lock):
            acquired = lock.acquire(blocking=False)
            unlocked.append(acquired)
            if acquired:
                lock.release()
        notifications.append(health)
        stream.request_source("Unknown")
        raise ValueError("PRIVATE health exception")

    stream = _stream(custom_snapshot=lambda: snapshot, on_matcher_health=health_changed)
    path = _log(tmp_path, "Alice")
    stream.subscribe_batches(batches.append)
    try:
        stream.start(tmp_path)
        stream.scan_once(NOW)
        _append(path, "fleet invite\n")
        stream.scan_once(NOW)
        assert [h.state for h in notifications] == ["active"]
        assert unlocked == [True, True, True]
        assert len(_matches(batches)) == 1
        assert _events(batches)[-1].character == "Unknown"
        assert "PRIVATE" not in caplog.text
    finally:
        stream.stop()


def test_stalled_drainer_coalesces_globally_and_never_precedes_semantic_siblings(
    tmp_path,
):
    snapshot = prepare_alert_snapshot(_preview("hits"))
    stream = _stream(custom_snapshot=lambda: snapshot)
    batches, legacy, callback_threads, semantic_counts = [], [], set(), []
    entered, release = threading.Event(), threading.Event()

    def block(event):
        callback_threads.add(threading.get_ident())
        legacy.append(event)
        if isinstance(event, SourceLifecycle) and event.character == "Alice":
            entered.set()
            assert release.wait(5)

    def batch_callback(batch):
        callback_threads.add(threading.get_ident())
        batches.append(batch)
        if batch.custom_matches:
            semantic_counts.append(sum(isinstance(e, CombatFact) for e in legacy))

    stream.subscribe(block)
    stream.subscribe_batches(batch_callback)
    worker = None
    try:
        stream.start(tmp_path)
        stream.scan_once(NOW)
        path = _log(tmp_path, "Alice", OUTGOING_DAMAGE_LINE)
        worker = threading.Thread(target=lambda: stream.scan_once(NOW))
        worker.start()
        assert entered.wait(5)
        for _ in range(19):
            _append(path, OUTGOING_DAMAGE_LINE)
            stream.scan_once(NOW)
            assert len(stream._pending_custom) == 1
            assert all(not hasattr(b, "custom_matches") for b in stream._dispatch_queue)
        assert not _matches(batches)
        release.set()
        worker.join(5)
        assert not worker.is_alive()
        assert len(callback_threads) == 1
        assert len(_matches(batches)) == 1
        assert _events(batches) == legacy
        assert len(legacy) == 21
        assert semantic_counts == [20]
        assert stream._pending_custom == {}
    finally:
        release.set()
        if worker is not None:
            worker.join(5)
        stream.stop()


def test_poll_and_stream_maps_refuse_excess_keys_without_dropping_semantics(
    tmp_path, monkeypatch
):
    # Exercise the cap with actual files, not a synthetic per-line input queue.
    monkeypatch.setattr(gamelogs, "_CUSTOM_PENDING_MAX", 2)
    snapshot = prepare_alert_snapshot(_preview("hits"))
    stream = _stream(custom_snapshot=lambda: snapshot)
    batches, sizes = [], []
    stream.subscribe_batches(batches.append)
    read = stream._read_source

    def observe(character, tracked, pending, stop_event):
        result = read(character, tracked, pending, stop_event)
        sizes.append(len(pending))
        return result

    monkeypatch.setattr(stream, "_read_source", observe)
    entered, release = threading.Event(), threading.Event()

    def block(event):
        if not entered.is_set():
            entered.set()
            assert release.wait(5)

    stream.subscribe(block)
    worker = None
    try:
        stream.start(tmp_path)
        stream.scan_once(NOW)
        for name in ("Alice", "Bravo", "Charlie"):
            _log(tmp_path, name, OUTGOING_DAMAGE_LINE * 10, stem=name)
        worker = threading.Thread(target=lambda: stream.scan_once(NOW))
        worker.start()
        assert entered.wait(5)
        assert sizes and max(sizes) == 2
        assert len(stream._pending_custom) == 2
        for name in ("Delta", "Echo"):
            _log(tmp_path, name, OUTGOING_DAMAGE_LINE, stem=name)
            stream.scan_once(NOW)
            assert len(stream._pending_custom) == 2
        release.set()
        worker.join(5)
        assert not worker.is_alive()
        assert len(_matches(batches)) == 2
        assert sum(isinstance(e, CombatFact) for e in _events(batches)) == 32
    finally:
        release.set()
        if worker is not None:
            worker.join(5)
        stream.stop()


def test_stalled_old_health_success_cannot_clear_newer_degradation(tmp_path):
    current = [prepare_alert_snapshot(_preview())]
    mode = [False]
    entered, release = threading.Event(), threading.Event()
    notifications = []

    def matcher(line, snapshot):
        if mode[0]:
            raise RuntimeError("private")
        return custom.match_line(line, snapshot)

    stream = _stream(
        custom_snapshot=lambda: current[0],
        custom_matcher=matcher,
        on_matcher_health=notifications.append,
    )

    def block(event):
        if not entered.is_set():
            entered.set()
            assert release.wait(5)

    stream.subscribe(block)
    worker = None
    try:
        stream.start(tmp_path)
        stream.scan_once(NOW)
        path = _log(tmp_path, "Alice", "fleet invite\n")
        worker = threading.Thread(target=lambda: stream.scan_once(NOW))
        worker.start()
        assert entered.wait(5)
        preview = _preview("new query")
        current[0] = prepare_alert_snapshot(preview, current[0])
        mode[0] = True
        _append(path, "new query\n")
        stream.scan_once(NOW)
        release.set()
        worker.join(5)
        assert not worker.is_alive()
        assert stream.custom_health().state == "degraded"
        assert [h.state for h in notifications] == ["degraded"]
        assert notifications[0].rules_revision == current[0].rules_revision
    finally:
        release.set()
        if worker is not None:
            worker.join(5)
        stream.stop()


def test_stop_discards_pending_custom_and_restart_rebaselines(tmp_path):
    snapshot = prepare_alert_snapshot(_preview("hits"))
    stream = _stream(custom_snapshot=lambda: snapshot)
    entered, release = threading.Event(), threading.Event()
    batches = []

    def block(event):
        if not entered.is_set():
            entered.set()
            assert release.wait(5)

    stream.subscribe(block)
    stream.subscribe_batches(batches.append)
    worker = None
    try:
        stream.start(tmp_path)
        stream.scan_once(NOW)
        path = _log(tmp_path, "Alice", OUTGOING_DAMAGE_LINE)
        worker = threading.Thread(target=lambda: stream.scan_once(NOW))
        worker.start()
        assert entered.wait(5)
        assert stream._pending_custom
        assert stream.stop()
        assert not stream._pending_custom
        release.set()
        worker.join(5)
        assert not worker.is_alive()
        assert not _matches(batches)
        _append(path, OUTGOING_DAMAGE_LINE)
        assert stream.start(tmp_path)
        stream.scan_once(NOW)
        assert not _matches(batches)
        _append(path, OUTGOING_DAMAGE_LINE)
        stream.scan_once(NOW)
        assert len(_matches(batches)) == 1
    finally:
        release.set()
        if worker is not None:
            worker.join(5)
        stream.stop()


def test_custom_only_backlog_does_not_grow_semantic_queue(tmp_path):
    snapshot = prepare_alert_snapshot(_preview())
    stream = _stream(custom_snapshot=lambda: snapshot)
    entered, release = threading.Event(), threading.Event()
    batches = []

    def block(event):
        if not entered.is_set():
            entered.set()
            assert release.wait(5)

    stream.subscribe(block)
    stream.subscribe_batches(batches.append)
    path = _log(tmp_path, "Alice")
    worker = None
    try:
        stream.start(tmp_path)
        worker = threading.Thread(target=lambda: stream.scan_once(NOW))
        worker.start()
        assert entered.wait(5)
        for _ in range(30):
            _append(path, "fleet invite\n")
            stream.scan_once(NOW)
        assert len(stream._pending_custom) == 1
        # No per-poll notification queue hiding behind the bounded match map.
        assert len(stream._dispatch_queue) <= 1
        release.set()
        worker.join(5)
        assert not worker.is_alive()
        assert len(_matches(batches)) == 1
    finally:
        release.set()
        if worker is not None:
            worker.join(5)
        stream.stop()


def test_pending_new_tokens_replace_old_and_late_old_tokens_are_refused(tmp_path):
    from wingman.telemetry.model import CustomMatch, SourceId

    source = SourceId(str(tmp_path / "source.txt"), NOW)
    pending = {}
    old = CustomMatch("Alice", 1, source, "r1", 1, 1)
    edited = CustomMatch("Alice", 1, source, "r1", 2, 1)
    reactivated = CustomMatch("Alice", 1, source, "r1", 2, 3)
    replaced = CustomMatch("Alice", 2, source, "r1", 2, 3)
    for number, match in enumerate((old, edited, reactivated, replaced), 1):
        gamelogs._stage_custom(pending, number, match)
        assert list(pending.values()) == [(number, match)]
    for match in (old, edited, reactivated):
        gamelogs._stage_custom(pending, 5, match)
        assert list(pending.values()) == [(4, replaced)]


def test_reentrant_stop_fences_custom_already_extracted_for_semantic_batch(tmp_path):
    snapshot = prepare_alert_snapshot(_preview("hits"))
    stream = _stream(custom_snapshot=lambda: snapshot)
    batches = []
    stopped = []

    def stop_on_fact(event):
        if isinstance(event, CombatFact):
            stopped.append(stream.stop())

    stream.subscribe(stop_on_fact)
    stream.subscribe_batches(batches.append)
    try:
        stream.start(tmp_path)
        stream.scan_once(NOW)
        _log(tmp_path, "Alice", OUTGOING_DAMAGE_LINE)
        stream.scan_once(NOW)
        assert stopped == [True]
        assert sum(isinstance(e, CombatFact) for e in _events(batches)) == 1
        assert not _matches(batches)
    finally:
        stream.stop()


def test_stop_fences_health_already_taken_by_drainer(tmp_path, monkeypatch):
    snapshot = prepare_alert_snapshot(_preview())
    entered, release = threading.Event(), threading.Event()
    notifications = []
    stream = _stream(
        custom_snapshot=lambda: snapshot, on_matcher_health=notifications.append
    )
    path = _log(tmp_path, "Alice")
    health = stream.custom_health

    def gated_health():
        entered.set()
        assert release.wait(5)
        return health()

    monkeypatch.setattr(stream, "custom_health", gated_health)
    worker = None
    try:
        stream.start(tmp_path)
        stream.scan_once(NOW)
        _append(path, "no match\n")
        worker = threading.Thread(target=lambda: stream.scan_once(NOW))
        worker.start()
        assert entered.wait(5)
        assert stream.stop()
        release.set()
        worker.join(5)
        assert not worker.is_alive()
        assert notifications == []
    finally:
        release.set()
        if worker is not None:
            worker.join(5)
        stream.stop()


def test_custom_callback_timeout_retains_sole_worker_until_retry_stop(tmp_path):
    snapshot = prepare_alert_snapshot(_preview())
    entered, release, scanned = threading.Event(), threading.Event(), threading.Event()
    batches = []

    def wait(stop_event, timeout):
        scanned.set()
        stop_event.wait(timeout)

    def block(batch):
        batches.append(batch)
        if batch.custom_matches:
            entered.set()
            assert release.wait(5)

    stream = gamelogs.GameLogStream(
        custom_snapshot=lambda: snapshot, _utc_now=lambda: NOW, _wait_fn=wait
    )
    stream.subscribe_batches(block)
    path = _log(tmp_path, "Alice")
    try:
        assert stream.start(tmp_path)
        assert scanned.wait(5)
        _append(path, "fleet invite\n")
        assert entered.wait(5)
        owner = stream._worker
        assert stream.stop(timeout=0.01) is False
        assert stream._worker is owner and owner.is_alive()
        assert stream.start(tmp_path) is False
        release.set()
        assert stream.stop(timeout=5) is True
        assert not owner.is_alive()
        assert len(_matches(batches)) == 1
        assert stream.start(tmp_path)
        assert stream._worker is not owner
    finally:
        release.set()
        stream.stop(timeout=5)
